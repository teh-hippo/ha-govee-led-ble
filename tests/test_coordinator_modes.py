import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble import effect_contracts
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS, ModelProfile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow, release_capability
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_music_mode,
    build_power,
    build_scene_activation,
    build_video_mode,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
)
from custom_components.ha_govee_led_ble.light_services import apply_active_video_mode
from custom_components.ha_govee_led_ble.music_commands import build_music_params
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets, resolve_native_scene_body
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENE_ENTRIES, scene_selector_code
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
from tests.coordinator_test_support import _CONFIGURATION_URL
from tests.test_effect_preview import _known_static_baseline
from tests.test_h617a_review_proof import frame
from tests.test_music_commands import _music_transport


@pytest.fixture
def h6199(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url=_CONFIGURATION_URL,
    )
    coordinator.fw_version, coordinator.hw_version = "1.10.04", "3.02.01"
    coordinator.subordinate_20_version, coordinator.subordinate_21_version = "1.03.00", "1.00.33"
    coordinator.pact_type, coordinator.pact_code = 2, 1
    coordinator._confirmed_identity_fields.update(
        {"pact", "fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"}
    )
    coordinator._resolve_device_profile()
    return coordinator


@pytest.fixture
def coord(coord):
    coord._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic() - 1
    coord._notify_callback(None, frame(1, [0]))
    coord._notify_callback(None, frame(4, [100]))
    coord._notify_callback(None, frame(5, [0x15, 0]))
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    return coord


def _sent(sc):
    return [call.args[0] for call in sc.await_args_list]


def _off_readback(coord, mode=(0x13, 3, 88, 1), *, verified=False):
    async def refresh(request):
        if request.required_domains is not None:
            coord._notify_callback(None, frame(5, list(mode)))
            return True
        return verified

    return AsyncMock(side_effect=refresh)


@pytest.mark.parametrize("grammar", ["H617A", "H6199"])
@pytest.mark.parametrize("scene_type", [0, 1, 2])
@pytest.mark.parametrize("intent", [ControlIntent.USER, ControlIntent.PREVIEW])
async def test_native_scene_application_requires_exact_capability_and_grammar(
    coord, monkeypatch, grammar, scene_type, intent
):
    model = "H9999"
    scene = next(entry for entry in SCENE_ENTRIES[grammar] if entry.scene_type == scene_type)
    profile = ModelProfile("Synthetic", command_grammar=grammar, supports_scenes=True)
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    monkeypatch.setitem(MODEL_SCENES, model, {"synthetic": scene})
    coord.model, coord.profile = model, profile
    coord.is_on = False
    # Packet encoding needs grammar, not application permission, even for uploaded scenes.
    packets = build_native_scene_packets(model, scene)
    with pytest.raises(ValueError, match="native_scenes application is not supported"):
        await coord.async_apply_native_scene("synthetic", verify=False, intent=intent)

    capability = release_capability(grammar, CapabilityWorkflow.NATIVE_SCENES)
    assert capability is not None
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model=model)),
    )
    for effect_grammar in (None, "unknown"):
        coord.profile = replace(profile, effect_grammar=effect_grammar)
        monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
        with pytest.raises(ValueError, match="grammar and activation route"):
            await coord.async_apply_native_scene("synthetic", scene_entry=scene, verify=False, intent=intent)
    assert coord.is_on is False
    assert coord.effect is None

    coord.profile = replace(profile, effect_grammar=grammar)
    monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
    with _music_transport(coord) as transport:
        await coord.async_apply_native_scene("synthetic", verify=False, intent=intent)
    assert [entry.args[1] for entry in transport.await_args_list] == [build_power(True, model), *packets]
    assert coord.effect == "synthetic"


async def test_h6179_native_scene_uses_wire_selector_for_verification_and_state(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:77",
        "H6179",
        configuration_url=_CONFIGURATION_URL,
    )
    scene = MODEL_SCENES["H6179"]["karst cave"]
    selector = scene_selector_code("H6179", scene)
    coordinator.is_on = True
    with (
        _music_transport(coordinator) as transport,
        patch.object(coordinator, "async_observe_effect", new_callable=AsyncMock, return_value=True) as observe,
    ):
        await coordinator.async_apply_native_scene(
            "karst cave",
            scene_entry=scene,
            verify=True,
        )

    assert [entry.args[1] for entry in transport.await_args_list] == [build_scene_activation("H6179", selector)]
    observe.assert_awaited_once_with({"scene_code": selector})
    assert coordinator._scene_code == selector


async def test_authored_palette_clears_origin_at_first_physical_write(coord, monkeypatch):
    model = "H6159"
    profile = replace(MODEL_PROFILES[model], profile_identity_fields=frozenset())
    scene = next(entry for entry in SCENE_ENTRIES[model] if entry.scene_type == 1)
    body, speed_index = resolve_native_scene_body(scene, target=model)
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    coord.model, coord.profile = model, profile
    coord.pact_type, coord.pact_code = 1, 1
    coord.fw_version, coord.hw_version = "1.07.02", "1.00.01"
    coord._confirmed_identity_fields.update({"pact", "fw_version", "hw_version"})
    coord.is_on = True
    origin_cleared = MagicMock()

    with _music_transport(coord) as transport:
        await coord.async_apply_native_scene(
            scene.name,
            scene_entry=scene,
            speed_index=speed_index,
            canonical_body=body,
            authored_palette=True,
            verify=False,
            on_write=origin_cleared,
        )

    assert origin_cleared.call_count == 1
    assert [entry.args[1] for entry in transport.await_args_list] == build_native_scene_packets(
        model,
        scene,
        speed_index=speed_index,
        canonical_body=body,
        profile=profile,
        authored_palette=True,
    )
    assert coord.effect is None
    assert coord._scene_code == profile.authored_palette_scene_selector


@pytest.mark.parametrize("model", ["H6159", "H617A"])
async def test_authored_palette_state_matches_selector_authority(coord, model):
    profile = replace(MODEL_PROFILES[model], profile_identity_fields=frozenset())
    scene = next(entry for entry in SCENE_ENTRIES[model] if entry.scene_type == 1)
    body, speed_index = resolve_native_scene_body(scene, target=model)
    coord.model, coord.profile = model, profile
    if model == "H6159":
        coord.pact_type, coord.pact_code = 1, 1
        coord.fw_version, coord.hw_version = "1.07.02", "1.00.01"
        coord._confirmed_identity_fields.update({"pact", "fw_version", "hw_version"})
    else:
        coord.fw_version, coord.hw_version = "1.00.00", "1.00.00"
        coord._confirmed_identity_fields.update({"fw_version", "hw_version"})
    coord.is_on = True
    coord.async_observe_effect = AsyncMock(return_value=True)

    with _music_transport(coord):
        await coord.async_apply_native_scene(
            scene.name,
            scene_entry=scene,
            speed_index=speed_index,
            canonical_body=body,
            authored_palette=True,
        )

    selector = scene_selector_code(model, scene, profile=profile, authored=True)
    coord.async_observe_effect.assert_awaited_once_with({"scene_code": selector})
    assert coord._scene_code == selector
    assert coord.effect == (None if profile.authored_palette_scene_selector == selector else scene.name)


async def test_select_music_slug_sends_power_then_music_and_sets_state(coord):
    coord.is_on, coord.effect = True, "prior effect"
    coord.diy_code = 0xF0

    async def transmit(_uuid, packet, **_kwargs):
        assert coord._control_arbiter.current_task_intent is ControlIntent.USER
        if packet == build_power(True):
            assert coord.effect == "prior effect" and coord.diy_code == 0xF0
            assert coord.music_mode == "off"
        else:
            assert coord.effect is None and coord.diy_code is None
            assert coord.music_mode == "rhythm"

    with (
        _music_transport(coord) as sc,
        patch.object(coord, "async_write_effect_sequence", wraps=coord.async_write_effect_sequence) as sequence,
    ):
        sc.side_effect = transmit
        await coord.async_select_music_slug("rhythm")
    sequence.assert_awaited_once()
    assert callable(sequence.await_args.kwargs["write_guard"])
    assert sequence.await_args.kwargs["packet_state_values"][0] == {"is_on": True}
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 99, None, False),
    ]
    assert coord.is_on is True
    assert (coord.music_mode, coord.video_mode) == ("rhythm", "off")
    assert coord.effect is None
    assert coord.diy_code is None


async def test_h6199_music_reapply_preserves_fixed_colour(h6199):
    h6199.music_color = (1, 2, 3)
    with _music_transport(h6199) as sc:
        await h6199.async_select_music_slug("rhythm")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        build_music_mode(
            MUSIC_MODE_SLUGS["rhythm"],
            h6199.music_sensitivity,
            (1, 2, 3),
            False,
            "H6199",
        ),
    ]


async def test_entering_music_from_color_temp_captures_color_temp_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin = True, 4000
    before = coord.capture_effect_control_state()
    with _music_transport(coord):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot == before


async def test_entering_music_from_rgb_captures_rgb_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin, coord.rgb_color = True, None, (7, 8, 9)
    before = coord.capture_effect_control_state()
    with _music_transport(coord):
        await coord.async_select_music_slug("bloom")
    assert coord._pre_mode_snapshot == before


async def test_entering_music_from_active_mode_preserves_snapshot(coord):
    coord.is_on, coord.music_mode = True, "rhythm"
    original = PriorControlState("colour", True, 50, (1, 2, 3), color_temp_kelvin=6000)
    coord._pre_mode_snapshot, coord.color_temp_kelvin = original, 4000
    with _music_transport(coord):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot is original


async def test_failed_music_power_attempt_does_not_publish_transition_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin = True, 4000
    original = PriorControlState("colour", True, 50, (1, 2, 3), color_temp_kelvin=6000)
    coord._pre_mode_snapshot = original
    with _music_transport(coord) as physical:
        physical.side_effect = RuntimeError("failed power attempt")
        with pytest.raises(RuntimeError, match="failed power attempt"):
            await coord.async_select_music_slug("rhythm")
    assert coord._pre_mode_snapshot is original
    assert coord._mode_transition is None
    assert coord.music_mode == "off"


async def test_music_style_applies_to_rhythm_bloom_and_shiny(coord):
    coord.is_on, coord.music_calm, coord.music_sensitivity = True, True, 80

    # Rhythm carries Dynamic/Calm in the base frame only (no a3 companion).
    with _music_transport(coord) as sc:
        await coord.async_select_music_slug("rhythm")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 80, None, True),
    ]

    # Destination presets upload before the selector, including modes without style.
    with _music_transport(coord) as sc:
        await coord.async_select_music_slug("hopping")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        *build_music_params(0x33, {}, profile=coord.profile),
        build_music_mode(MUSIC_MODE_SLUGS["hopping"], 80, None, False),
    ]

    # Shiny style belongs solely to the A3 companion.
    coord.music_calm = True
    with _music_transport(coord) as sc:
        await coord.async_select_music_slug("shiny")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        *build_music_params(0x31, {}, profile=coord.profile, calm=True),
        build_music_mode(MUSIC_MODE_SLUGS["shiny"], 80, None, True),
    ]

    # Bloom's Calm companion is [27].
    with _music_transport(coord) as sc:
        await coord.async_select_music_slug("bloom")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        *build_music_params(0x30, {}, profile=coord.profile, calm=True),
        build_music_mode(MUSIC_MODE_SLUGS["bloom"], 80, None, True),
    ]

    # Dynamic Shiny writes the template's baseline companion values.
    coord.music_calm = False
    with _music_transport(coord) as sc:
        await coord.async_select_music_slug("shiny")
    assert [entry.args[1] for entry in sc.await_args_list] == [
        build_power(True),
        *build_music_params(0x31, {}, profile=coord.profile),
        build_music_mode(MUSIC_MODE_SLUGS["shiny"], 80, None, False),
    ]


@pytest.mark.parametrize("confirmed", [False, True])
async def test_select_off_delegates_complete_state_without_replaying_unconfirmed_delivery(coord, confirmed):
    coord.music_mode = "rhythm"
    prior = _known_static_baseline(coord)
    coord._pre_mode_snapshot = prior
    with (
        patch.object(coord, "refresh_state", _off_readback(coord)),
        patch.object(coord, "async_restore_effect_control_state", AsyncMock(return_value=confirmed)) as restore,
    ):
        if confirmed:
            await coord.async_select_music_slug("off")
        else:
            with pytest.raises(ValueError, match="complete static state"):
                await coord.async_select_music_slug("off")
    restore.assert_awaited_once()
    assert restore.await_args.args[0].state == prior
    assert restore.await_args.kwargs == {"overwritten_diy_code": None}


@pytest.mark.parametrize("entrypoint", ["light", "music"])
@pytest.mark.parametrize("target", ["missing", "incomplete", "profile_changed"])
async def test_unavailable_restoration_rejects_before_power_or_brightness(coord, entrypoint, target):
    from custom_components.ha_govee_led_ble.light import GoveeBLELight

    coord.is_on = False
    coord.music_mode = "rhythm"
    if target != "missing":
        coord._pre_mode_snapshot = replace(coord.capture_effect_control_state(), mode="colour")
        coord._pre_mode_profile = coord.profile
        if target == "profile_changed":
            coord.profile = replace(coord.profile, segment_count=12)
    with (
        patch.object(coord, "refresh_state", _off_readback(coord)),
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
    ):
        with pytest.raises(HomeAssistantError):
            if entrypoint == "light":
                await GoveeBLELight(coord).async_turn_on(effect="off", brightness=100)
            else:
                await coord.async_select_music_slug("off")
    sc.assert_not_awaited()


async def test_already_static_off_does_not_restore_stale_snapshot(coord):
    coord.is_on = True
    coord.color_mode = ParsedMode.COLOUR
    coord._pre_mode_snapshot = coord.capture_effect_control_state()
    with (
        patch.object(coord, "refresh_state", _off_readback(coord, (0x15, 0))),
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
    ):
        await coord.async_select_music_slug("off")
    send.assert_not_awaited()
    assert coord._pre_mode_snapshot is None


@pytest.mark.parametrize("kelvin", [None, 4200])
@pytest.mark.parametrize("known", [False, True])
async def test_unsegmented_mode_exit_preserves_known_native_intent_without_segment_reads(hass, kelvin, known):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6179", configuration_url=None)
    coord.is_on, coord.color_mode, coord.brightness_pct = True, ParsedMode.COLOUR, 37
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic() - 1
    if known:
        coord.install_static_color(rgb=(12, 34, 56), kelvin=kelvin)
    else:
        coord._pre_mode_snapshot = PriorControlState("colour", True, 50, (200, 100, 50))
    with _music_transport(coord) as physical:
        if known:
            await coord.send_command(build_power(True, coord.model))
            await coord.send_command(build_brightness(37, coord.model))
            await coord.send_command(
                build_color_temp(kelvin, coord.model) if kelvin else build_color_rgb(12, 34, 56, coord.model)
            )
        await coord.async_select_music_slug("mode_0")
        physical.reset_mock()
        coord.refresh_state = _off_readback(coord, (0x0E, 0, 50, 0), verified=True)
        if known:
            await coord.async_select_music_slug("off")
            colour = build_color_temp(kelvin, "H6179") if kelvin else build_color_rgb(12, 34, 56, "H6179")
            assert [entry.args[1] for entry in physical.await_args_list] == [
                build_power(True, "H6179"),
                build_brightness(37, "H6179"),
                colour,
            ]
        else:
            with pytest.raises(HomeAssistantError):
                await coord.async_select_music_slug("off")
            physical.assert_not_awaited()


@pytest.mark.parametrize("change", ["profile", "subscription", "owner", "observation"])
async def test_mode_exit_revalidates_before_first_physical_attempt(coord, change):
    from tests.test_h617a_review_proof import frame, observe_segments

    coord.is_on, coord.color_mode = True, ParsedMode.COLOUR
    observe_segments(coord, [(1, 2, 3)] * 15, [30] * 15)
    coord._notification_token = object()
    with _music_transport(coord) as physical:
        await coord.async_select_music_slug("rhythm")
        coord._expected_state.clear()
        physical.reset_mock()
        changed = False

        async def connect():
            nonlocal changed
            if not changed:
                changed = True
                if change == "profile":
                    coord.profile = replace(coord.profile, segment_count=12)
                elif change == "subscription":
                    coord._notification_token = object()
                elif change == "owner":

                    async def supersede():
                        coord._control_arbiter.invalidate_previews()

                    await asyncio.create_task(supersede())
                else:
                    coord._notify_callback(None, frame(5, [0x15, 0]))
                    observe_segments(coord, [(4, 5, 6)] * 15, [70] * 15)
            return coord._client

        with (
            patch.object(coord, "refresh_state", _off_readback(coord)),
            patch.object(coord, "_ensure_connected", AsyncMock(side_effect=connect)),
        ):
            with pytest.raises((ValueError, HomeAssistantError)):
                await coord.async_select_music_slug("off")
        physical.assert_not_awaited()
    if change == "observation":
        assert coord.segment_colors == [(4, 5, 6)] * 15
        assert coord.segment_brightness == [70] * 15
        assert coord.color_mode is ParsedMode.COLOUR


async def test_restoration_does_not_replay_a_partially_delivered_static_batch(coord):
    from bleak import BleakError

    from tests.test_h617a_review_proof import frame, observe_segments

    coord.is_on, coord.color_mode = True, ParsedMode.COLOUR
    observe_segments(coord, [(1, 2, 3)] * 15, [30] * 15)
    with _music_transport(coord) as physical:
        await coord.async_select_music_slug("rhythm")
        physical.reset_mock()
        writes = 0

        async def transmit(_uuid, packet, **_kwargs):
            nonlocal writes
            if packet[0] == 0x33:
                writes += 1
                if writes == 3:
                    raise BleakError("static command may have applied")
            elif packet[:2] == b"\xaa\x01":
                coord._notify_callback(None, frame(1, [1]))
            elif packet[:2] == b"\xaa\x04":
                coord._notify_callback(None, frame(4, [coord.brightness_pct]))

        physical.side_effect = transmit
        coord.refresh_state = _off_readback(coord)
        with pytest.raises(BleakError, match="may have applied"):
            await coord.async_select_music_slug("off")
        assert writes == 3


async def test_restoration_preserves_new_static_observation_after_leading_power(coord):
    from tests.test_h617a_review_proof import frame, observe_segments

    coord.is_on, coord.color_mode = True, ParsedMode.COLOUR
    observe_segments(coord, [(1, 2, 3)] * 15, [30] * 15)
    with _music_transport(coord) as physical:
        await coord.async_select_music_slug("rhythm")
        physical.reset_mock()

        async def transmit(_uuid, packet, **_kwargs):
            if packet[:2] == b"\xaa\x01":
                coord._notify_callback(None, frame(1, [1]))
                return
            coord._expected_state.clear()
            coord._notify_callback(None, frame(5, [0x15, 0]))
            observe_segments(coord, [(4, 5, 6)] * 15, [70] * 15)

        physical.side_effect = transmit
        coord.refresh_state = _off_readback(coord)
        with pytest.raises(ValueError, match="Static restoration"):
            await coord.async_select_music_slug("off")
        assert sum(entry.args[1][0] == 0x33 for entry in physical.await_args_list) == 1
    assert coord.segment_colors == [(4, 5, 6)] * 15
    assert coord.segment_brightness == [70] * 15
    assert coord.color_mode is ParsedMode.COLOUR


@pytest.mark.parametrize("conflicting", [False, True])
async def test_restoration_accepts_only_matching_intermediate_segment_observations(coord, conflicting):
    from custom_components.ha_govee_led_ble.light_commands import parse_static_write
    from tests.test_h617a_review_proof import frame, observe_segments

    original = [(255, 0, 0)] * 7 + [(0, 0, 255)] * 8
    coord.is_on, coord.color_mode, coord.brightness_pct = True, ParsedMode.COLOUR, 20
    observe_segments(coord, original, [30] * 7 + [70] * 8)
    with _music_transport(coord) as physical:
        await coord.async_select_music_slug("rhythm")
        observe_segments(coord, [(0, 255, 0)] * 15, [60] * 15)
        physical.reset_mock()
        static_attempts = 0
        observed = None

        async def transmit(_uuid, packet, **_kwargs):
            nonlocal static_attempts, observed
            if parse_static_write(packet) is not None:
                static_attempts += 1
                if static_attempts == 1:
                    observed = list(coord.segment_colors)
                    if conflicting:
                        observed[-1] = (9, 8, 7)
                    coord._notify_callback(None, frame(5, [0x15, 0]))
                    observe_segments(coord, observed, list(coord.segment_brightness))
            elif packet[:2] == b"\xaa\x01":
                coord._notify_callback(None, frame(1, [1]))
            elif packet[:2] == b"\xaa\x04":
                coord._notify_callback(None, frame(4, [20]))

        physical.side_effect = transmit
        coord.refresh_state = _off_readback(coord)
        with patch.object(coord, "async_refresh_segments", AsyncMock(return_value=False)):
            if conflicting:
                with pytest.raises(ValueError, match="Static restoration"):
                    await coord.async_select_music_slug("off")
                assert static_attempts == 1
                assert coord.segment_colors == observed
                assert coord.segment_state_source == "observed"
            else:
                with pytest.raises(ValueError, match="No complete static state"):
                    await coord.async_select_music_slug("off")
                assert static_attempts == 4
                assert coord.segment_colors == original
                assert coord.segment_brightness == [30] * 7 + [70] * 8


async def test_effect_off_marks_failed_restore_power_uncertain_without_replay(coord):
    from bleak import BleakError

    from custom_components.ha_govee_led_ble.light import GoveeBLELight
    from tests.test_h617a_review_proof import observe_segments

    coord.is_on, coord.color_mode = True, ParsedMode.COLOUR
    observe_segments(coord, [(1, 2, 3)] * 15, [30] * 15)
    with _music_transport(coord) as physical:
        await coord.async_select_music_slug("rhythm")
        coord.is_on = False
        physical.reset_mock()
        physical.side_effect = BleakError("power may have applied")

        async def disconnect():
            coord._clear_client_state(coord._client)

        with (
            patch.object(coord, "_disconnect_locked", AsyncMock(side_effect=disconnect)),
            patch.object(coord, "refresh_state", _off_readback(coord)),
        ):
            with pytest.raises(HomeAssistantError) as error:
                await GoveeBLELight(coord).async_turn_on(effect="off")
        assert error.value.translation_key == "partial_command"
        physical.assert_awaited_once()
        assert physical.await_args.args[1] == build_power(True, coord.model)
        assert coord.control_state_uncertain("is_on")


async def test_new_subscription_does_not_capture_retained_segment_observations(coord):
    from tests.test_h617a_review_proof import frame, observe_segments

    coord.is_on, coord.color_mode = True, ParsedMode.COLOUR
    coord._notify_callback(None, frame(5, [0x15, 0]))
    observe_segments(coord, [(1, 2, 3)] * 15, [30] * 15)
    with _music_transport(coord) as physical:
        coord._client.start_notify = AsyncMock()
        await coord._start_notify()
        await coord.async_select_music_slug("rhythm")
        physical.reset_mock()
        with pytest.raises(HomeAssistantError):
            await coord.async_select_music_slug("off")
        physical.assert_not_awaited()


async def test_apply_active_video_mode_noop_when_video_off(coord):
    coord.is_on, coord.video_mode = True, "off"
    with patch.object(coord, "async_write_effect_sequence", new_callable=AsyncMock) as write:
        assert await apply_active_video_mode(coord, mode="off", requested_values={}) is False
    write.assert_not_awaited()


async def test_apply_active_video_mode_requires_readback(h6199):
    from tests.test_h6199_capabilities import set_qualified_identity

    set_qualified_identity(h6199)
    h6199.is_on = True
    values = {"full_screen": False, "saturation": 63, "sound_effects": True, "sound_effects_softness": 27}
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6199, "async_prepare_static_baseline", return_value=h6199.capture_effect_control_state()),
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await apply_active_video_mode(h6199, mode="game", requested_values=values) is True
    client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, build_video_mode("game", False, 63, True, 27, "H6199"), response=False
    )
    assert h6199.video_mode == "game"
    assert {field: getattr(h6199, f"video_{field}") for field in values} == values
    refresh.assert_awaited_once_with(
        RefreshRequest(
            on=True,
            video_mode="game",
            video_full_screen=False,
            video_saturation=63,
            video_sound_effects=True,
            video_sound_effects_softness=27,
        ),
    )


async def test_apply_active_video_mode_powers_on_and_raises_after_retry(h6199):
    from tests.test_h6199_capabilities import set_qualified_identity

    set_qualified_identity(h6199)
    h6199.is_on, h6199.video_mode = False, "movie"
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6199, "async_prepare_static_baseline", return_value=h6199.capture_effect_control_state()),
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=False) as refresh,
        pytest.raises(RuntimeError, match="Video-mode write was not confirmed"),
    ):
        await apply_active_video_mode(h6199, mode="movie", requested_values={})

    assert [entry.args[1] for entry in client.write_gatt_char.await_args_list] == [
        build_power(True, "H6199"),
        build_video_mode("movie", True, 100, False, 100, "H6199"),
        build_video_mode("movie", True, 100, False, 100, "H6199"),
    ]
    assert h6199.is_on is True
    assert (
        refresh.await_args_list
        == [
            call(
                RefreshRequest(
                    on=True,
                    video_mode="movie",
                    video_full_screen=True,
                    video_saturation=100,
                    video_sound_effects=False,
                    video_sound_effects_softness=100,
                ),
            )
        ]
        * 2
    )
