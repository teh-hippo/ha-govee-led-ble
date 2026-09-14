from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.ha_govee_led_ble import effect_contracts
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS, ModelProfile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import PreModeSnapshot
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow, release_capability
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_h6199_video,
    build_music_mode,
    build_power,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_white_brightness,
)
from custom_components.ha_govee_led_ble.light_services import apply_active_video_mode
from custom_components.ha_govee_led_ble.music_commands import build_music_params
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import WRITE_UUID

_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H617A",
        configuration_url=_CONFIGURATION_URL,
    )


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url=_CONFIGURATION_URL,
    )


def _sent(sc):
    return [call.args[0] for call in sc.await_args_list]


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
    writer = AsyncMock()
    # Packet encoding needs grammar, not application permission, even for uploaded scenes.
    packets = build_native_scene_packets(model, scene)
    with pytest.raises(ValueError, match="native_scenes application is not supported"):
        await coord.async_apply_native_scene("synthetic", writer=writer, verify=False, intent=intent)

    capability = release_capability(grammar, CapabilityWorkflow.NATIVE_SCENES)
    assert capability is not None
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model=model)),
    )
    for effect_grammar in (None, "unknown", "H6199" if grammar == "H617A" else "H617A"):
        coord.profile = replace(profile, effect_grammar=effect_grammar)
        monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
        with pytest.raises(ValueError, match="grammar and activation route"):
            await coord.async_apply_native_scene(
                "synthetic", scene_entry=scene, writer=writer, verify=False, intent=intent
            )
    writer.assert_not_awaited()
    assert coord.is_on is False
    assert coord.effect is None

    coord.profile = replace(profile, effect_grammar=grammar)
    monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
    await coord.async_apply_native_scene("synthetic", writer=writer, verify=False, intent=intent)
    assert _sent(writer) == [build_power(True, model), *packets]
    assert coord.effect == "synthetic"


async def test_select_music_slug_sends_power_then_music_and_sets_state(coord):
    coord.is_on, coord.effect = True, "prior effect"
    coord.diy_code = 0xF0
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 99, None, False),
    ]
    assert coord.is_on is True
    assert (coord.music_mode, coord.video_mode) == ("rhythm", "off")
    assert coord.effect is None
    assert coord.diy_code is None


async def test_h6199_music_reapply_preserves_fixed_colour(h6199):
    h6199.music_color = (1, 2, 3)
    with patch.object(h6199, "send_command", new_callable=AsyncMock) as sc:
        await h6199.async_select_music_slug("rhythm")
    assert _sent(sc) == [
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
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="color_temp", kelvin=4000)


async def test_entering_music_from_rgb_captures_rgb_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin, coord.rgb_color = True, None, (7, 8, 9)
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("bloom")
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="rgb", rgb=(7, 8, 9))


async def test_entering_music_from_active_mode_preserves_snapshot(coord):
    coord.is_on, coord.music_mode = True, "rhythm"
    original = PreModeSnapshot(kind="color_temp", kelvin=6000)
    coord._pre_mode_snapshot, coord.color_temp_kelvin = original, 4000
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot is original


async def test_music_style_applies_to_rhythm_bloom_and_shiny(coord):
    coord.is_on, coord.music_calm, coord.music_sensitivity = True, True, 80

    # Rhythm carries Dynamic/Calm in the base frame only (no a3 companion).
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 80, None, True),
    ]

    # A mode without a style keeps calm out of the base frame and sends no companion.
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("hopping")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["hopping"], 80, None, False),
    ]

    # Shiny sets the base-frame STYLE and its a3 companion [20,21] to the Calm values.
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("shiny")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["shiny"], 80, None, True),
        *build_music_params(0x31, {}, profile=coord.profile, calm=True),
    ]

    # Bloom's Calm companion is [27].
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("bloom")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["bloom"], 80, None, True),
        *build_music_params(0x30, {}, profile=coord.profile, calm=True),
    ]

    # Dynamic Shiny writes the template's baseline companion values.
    coord.music_calm = False
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("shiny")
    assert _sent(sc) == [
        build_power(True),
        build_music_mode(MUSIC_MODE_SLUGS["shiny"], 80, None, False),
        *build_music_params(0x31, {}, profile=coord.profile),
    ]


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (PreModeSnapshot(kind="rgb", rgb=(1, 2, 3)), build_color_rgb(1, 2, 3)),
        (PreModeSnapshot(kind="color_temp", kelvin=3500), build_color_temp(3500)),
        (PreModeSnapshot(kind="white", level=42), build_white_brightness(42)),
    ],
)
async def test_restore_pre_mode_re_emits_matching_builder(coord, snapshot, expected):
    coord._pre_mode_snapshot = snapshot
    coord.music_mode, coord.video_mode = "rhythm", "movie"
    coord.effect = "leftover"
    coord.diy_code = 0xF0
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_restore_pre_mode()
    assert _sent(sc) == [expected]
    assert (coord.music_mode, coord.video_mode) == ("off", "off")
    assert coord.effect is None
    assert coord.diy_code is None


async def test_select_off_routes_to_restore_and_clears_music_mode(coord):
    coord.music_mode = "rhythm"
    coord._pre_mode_snapshot = PreModeSnapshot(kind="color_temp", kelvin=5000)
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("off")
    assert _sent(sc) == [build_color_temp(5000)]
    assert coord.music_mode == "off"


async def test_fresh_off_falls_back_to_white_rgb(coord):
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("off")
    assert _sent(sc) == [build_color_rgb(255, 255, 255)]
    assert (coord.music_mode, coord.video_mode) == ("off", "off")


async def test_apply_active_video_mode_noop_when_video_off(coord):
    coord.is_on, coord.video_mode = True, "off"
    with patch.object(coord, "async_write_effect_sequence", new_callable=AsyncMock) as write:
        assert await apply_active_video_mode(coord, mode="off", requested_values={}) is False
    write.assert_not_awaited()


async def test_apply_active_video_mode_requires_readback(h6199):
    h6199.is_on = True
    values = {"full_screen": False, "saturation": 63, "sound_effects": True, "sound_effects_softness": 27}
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await apply_active_video_mode(h6199, mode="game", requested_values=values) is True
    client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, build_h6199_video(False, True, 63, True, 27), response=False
    )
    assert h6199.video_mode == "game"
    assert {field: getattr(h6199, f"video_{field}") for field in values} == values
    refresh.assert_awaited_once_with(
        expected_on=True,
        expected_video_mode="game",
        expected_video_full_screen=False,
        expected_video_saturation=63,
        expected_video_sound_effects=True,
        expected_video_sound_effects_softness=27,
    )


async def test_apply_active_video_mode_powers_on_and_raises_after_retry(h6199):
    h6199.is_on, h6199.video_mode = False, "movie"
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=False) as refresh,
        pytest.raises(RuntimeError, match="Video-mode write was not confirmed"),
    ):
        await apply_active_video_mode(h6199, mode="movie", requested_values={})

    assert [entry.args[1] for entry in client.write_gatt_char.await_args_list] == [
        build_power(True, "H6199"),
        build_h6199_video(True, False, 100, False, 100),
        build_h6199_video(True, False, 100, False, 100),
    ]
    assert h6199.is_on is True
    assert refresh.await_args_list == [call(expected_on=True, expected_video_mode="movie")] * 2
