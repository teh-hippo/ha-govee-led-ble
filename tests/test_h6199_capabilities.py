"""H6199 software revision routing and qualified music semantics, not hardware qualification."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, device_profile, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_power_query,
    build_relative_brightness_query,
    build_segment_query,
    build_subordinate_query,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.music_commands import resolve_music_profile
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.protocol_h6199 import build_h6199_control_query
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, scene_supported
from custom_components.ha_govee_led_ble.transport import xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import (
    camera_controls_state,
    video_control_states,
    video_identity_fields,
)

QUALIFIED = dict(
    fw_version="1.10.04",
    hw_version="3.02.01",
    subordinate_20_version="1.03.00",
    subordinate_21_version="1.00.33",
    pact_type=2,
    pact_code=1,
)


def set_qualified_identity(coordinator):
    vars(coordinator).update(QUALIFIED)
    confirmed = getattr(coordinator, "_confirmed_identity_fields", None)
    if confirmed is None:
        confirmed = coordinator._confirmed_identity_fields = set()
    confirmed.update(video_identity_fields(coordinator.profile))
    if not callable(getattr(coordinator, "identity_fields_confirmed", None)):
        coordinator.identity_fields_confirmed = lambda fields: fields <= confirmed


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "uploaded"),
    [
        ((2, 1), "1.06.00", "1.00.01", False),
        ((2, 1), "1.06.01", "1.00.01", True),
        ((2, 1), "1.07.01", "3.02.01", False),
        ((2, 1), "1.07.02", "3.02.01", True),
        ((2, 1), "9.99.99", "3.04.01", False),
        ((2, 1), "9.99.99", "2.01.01", False),
        ((2, 1), None, "1.00.01", False),
        ((2, 1), "1.06.01", None, False),
        ((3, 1), "1.00.01", "1.00.01", True),
        ((4, 1), "1.00.01", "1.00.01", True),
    ],
)
def test_pact2_uploaded_scene_revision_boundary(pact, firmware, hardware, uploaded):
    profile = device_profile("H6199", *pact, firmware=firmware, hardware=hardware)
    residents = tuple(scene for scene in SCENE_ENTRIES["H6199"] if scene_supported(scene, profile))

    assert profile.profile_identity_fields == frozenset({"fw_version", "hw_version"})
    assert profile.supports_advanced_effects is uploaded
    assert (profile.selector_only_scene_bits is None) is uploaded
    assert (profile.scene_codes is None) is uploaded
    assert profile.scene_upload_subtypes == frozenset({1, 2, 3})
    if uploaded:
        assert len(residents) == 240
    else:
        assert tuple(sorted(scene.code for scene in residents)) == (0, 1, 4, 5, 7, 8, 9, 10, 15, 16, 21, 22)
        assert all(scene.scene_type == 0 for scene in residents)


def test_pact2_scene_profile_transitions_with_fresh_identity(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 2, 1, 0))}))
    coordinator._observe_identity_field("hw_version", "1.00.01")

    coordinator._observe_identity_field("fw_version", "1.06.00")
    assert coordinator.profile.scene_codes is not None
    old_generation = coordinator._profile_generation

    coordinator._observe_identity_field("fw_version", "1.06.01")
    assert coordinator.profile.scene_codes is None
    assert coordinator._profile_generation > old_generation
    full_generation = coordinator._profile_generation

    coordinator._observe_identity_field("fw_version", "1.06.00")
    assert coordinator.profile.scene_codes is not None
    assert coordinator._profile_generation > full_generation


@pytest.mark.parametrize("subtype", [2, 3])
def test_old_pact2_resident_scene_packets_survive_but_uploaded_scene_packets_do_not(subtype):
    full = device_profile("H6199", 2, 1, firmware="1.06.01", hardware="1.00.01")
    old = device_profile("H6199", 2, 1, firmware="1.06.00", hardware="1.00.01")
    entry = next(
        scene
        for scene in SCENE_ENTRIES["H6199"]
        if (content := decode_catalogue_palette_scene("H6199", scene)) is not None
        and compile_effect(LibraryItem.new("Uploaded", content), "H6199", profile=full).upload_packets[0][2:5]
        == bytes((1, subtype, 1))
    )
    compiled = compile_effect(
        LibraryItem.new("Uploaded", decode_catalogue_palette_scene("H6199", entry)),
        "H6199",
        profile=full,
    )
    resident = next(scene for scene in SCENE_ENTRIES["H6199"] if scene.code == 1)

    for packet in build_native_scene_packets("H6199", resident, profile=old):
        require_profile_packet(packet, old)
    for packet in compiled.upload_packets:
        require_profile_packet(packet, full)
    with pytest.raises(ValueError, match="scene upload"):
        require_profile_packet(compiled.upload_packets[0], old)
    with pytest.raises(ValueError, match="scene selector"):
        require_profile_packet(compiled.activation_packet, old)


@pytest.mark.parametrize("transition_at", ["admission", "upload", "activation"])
async def test_old_pact2_scene_identity_transition_blocks_upload_and_activation(hass, monkeypatch, transition_at):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 2, 1, 0))}))
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    coordinator._observe_identity_field("hw_version", "1.00.01")
    coordinator._observe_identity_field("fw_version", "1.06.00" if transition_at == "admission" else "1.06.01")
    full = device_profile("H6199", 2, 1, firmware="1.06.01", hardware="1.00.01")
    entry = next(scene for scene in SCENE_ENTRIES["H6199"] if decode_catalogue_palette_scene("H6199", scene))
    compiled = compile_effect(
        LibraryItem.new("Uploaded", decode_catalogue_palette_scene("H6199", entry)),
        "H6199",
        profile=full,
    )
    transition_packet = (
        compiled.upload_packets[0]
        if transition_at == "upload"
        else compiled.upload_packets[-1]
        if transition_at == "activation"
        else None
    )
    written = []

    async def write(_uuid, packet, **_kwargs):
        written.append(packet)
        if packet == transition_packet:
            coordinator._observe_identity_field("fw_version", "1.06.00")

    client.write_gatt_char.side_effect = write
    with pytest.raises(ValueError):
        await coordinator.async_write_effect_sequence(
            compiled.packets,
            intent=ControlIntent.USER,
        )

    expected_writes = (
        0 if transition_at == "admission" else 1 if transition_at == "upload" else len(compiled.upload_packets)
    )
    assert len(written) == expected_writes
    assert compiled.activation_packet not in written
    assert not coordinator.profile.supports_advanced_effects


def test_compound_static_recovery_is_limited_to_the_captured_h6199_revision():
    assert device_profile(
        "H6199",
        pact_type=QUALIFIED["pact_type"],
        pact_code=QUALIFIED["pact_code"],
        hardware=QUALIFIED["hw_version"],
        firmware=QUALIFIED["fw_version"],
    ).supports_compound_static_recovery

    for pact, hardware, firmware in (
        ((1, 1), QUALIFIED["hw_version"], QUALIFIED["fw_version"]),
        ((2, 1), "3.02.02", QUALIFIED["fw_version"]),
        ((2, 1), QUALIFIED["hw_version"], "1.10.05"),
        ((2, 2), QUALIFIED["hw_version"], QUALIFIED["fw_version"]),
        ((None, None), None, None),
    ):
        assert not device_profile(
            "H6199",
            pact_type=pact[0],
            pact_code=pact[1],
            hardware=hardware,
            firmware=firmware,
        ).supports_compound_static_recovery


def test_compound_static_recovery_remains_default_gated_for_neighbouring_profiles():
    models = {
        "H6022",
        "H60A1",
        "H617C",
        "H617E",
        "H617F",
        "H6072",
        "H6076",
        "H6102",
        "H612A",
        "H6125",
        "H7020",
        "H7025",
    }
    assert all(not MODEL_PROFILES[model].supports_compound_static_recovery for model in models)


@pytest.mark.parametrize("mode,colour", [("energetic", False), ("rhythm", True), ("spectrum", True), ("rolling", True)])
@pytest.mark.parametrize("sensitivity", [0, 100])
def test_catalogue_matches_music_backend(mode, colour, sensitivity):
    metadata = MODEL_EFFECT_CATALOGUES["H6199"].to_dict()["music_settings"][mode]
    assert metadata["colour"] is colour
    assert metadata["style"] is (mode == "rhythm")
    assert metadata["available"]
    resolve_music_profile("H6199", mode, sensitivity, None, None, {})
    if colour:
        _, _, packets = resolve_music_profile("H6199", mode, sensitivity, (32, 96, 160), None, {})
        assert packets[-1][4:10] == bytes((sensitivity, 0, 1, 32, 96, 160))
    else:
        with pytest.raises(ValueError, match="fixed music colour"):
            resolve_music_profile("H6199", mode, sensitivity, (32, 96, 160), None, {})


@pytest.mark.parametrize("sensitivity", [-1, 101, True])
def test_music_rejects_out_of_bounds(sensitivity):
    with pytest.raises(ValueError, match="sensitivity"):
        resolve_music_profile("H6199", "spectrum", sensitivity, None, None, {})


@pytest.mark.parametrize(
    "changes,control,expected",
    [
        ({}, "relative_brightness", "supported"),
        ({"hw_version": "3.02.10"}, "blank_screen", "supported"),
        ({"hw_version": "3.02.11"}, "relative_brightness", "unsupported"),
        ({"subordinate_20_version": "1.03.01"}, "blank_screen", "unsupported"),
        ({"fw_version": "1.10.01"}, "relative_brightness", "unsupported"),
        ({"subordinate_21_version": "1.00.29"}, "relative_brightness", "unsupported"),
        ({"fw_version": "1.10.02", "subordinate_21_version": "1.00.30"}, "relative_brightness", "supported"),
        ({"fw_version": "1.08.10"}, "white_balance", "unsupported"),
        ({"fw_version": "1.08.11", "subordinate_21_version": "1.00.23"}, "white_balance", "supported"),
        ({"subordinate_20_version": "1.00.01"}, "white_balance", "unsupported"),
        ({"hw_version": None}, "white_balance", "evidence_gap"),
        ({"hw_version": None, "fw_version": "1.00.01"}, "white_balance", "unsupported"),
        ({"hw_version": "malformed"}, "relative_brightness", "evidence_gap"),
        ({"hw_version": "1.00.01", "fw_version": "1.06.01"}, "sound_effects", "supported"),
        ({"hw_version": "1.00.01", "fw_version": "1.06.00"}, "sound_effects", "unsupported"),
        ({"fw_version": "1.07.02"}, "sound_effects", "supported"),
        ({"fw_version": "1.07.01"}, "sound_effects", "unsupported"),
        ({"pact_type": 3, "fw_version": None, "hw_version": None}, "sound_effects", "supported"),
        ({"pact_type": None, "fw_version": "1.00.01"}, "sound_effects", "evidence_gap"),
    ],
)
def test_revision_gates(changes, control, expected):
    identity = SimpleNamespace(**(QUALIFIED | changes))
    states = video_control_states(MODEL_PROFILES["H6199"], identity)
    assert states[control] == expected
    assert states["capture_region"] is CapabilityState.SUPPORTED
    assert states["black_border"] is CapabilityState.UNSUPPORTED
    narrowed = replace(MODEL_PROFILES["H6199"], supports_white_balance=False)
    assert video_control_states(narrowed, identity)["white_balance"] is CapabilityState.UNSUPPORTED


def test_unknown_and_exact_camera_qualification():
    profile = MODEL_PROFILES["H6199"]
    assert video_control_states(profile, SimpleNamespace())["blank_screen"] is CapabilityState.EVIDENCE_GAP
    assert camera_controls_state(profile, SimpleNamespace(**QUALIFIED)) is CapabilityState.SUPPORTED
    assert camera_controls_state(profile, SimpleNamespace()) is CapabilityState.EVIDENCE_GAP
    assert camera_controls_state(get_profile("H6099"), SimpleNamespace(**QUALIFIED)) is CapabilityState.UNSUPPORTED
    assert (
        camera_controls_state(profile, SimpleNamespace(**(QUALIFIED | {"fw_version": "1.11.00"})))
        is CapabilityState.EVIDENCE_GAP
    )
    assert (
        camera_controls_state(profile, SimpleNamespace(**(QUALIFIED | {"fw_version": "1.00.01"})))
        is CapabilityState.EVIDENCE_GAP
    )
    assert set(QUALIFIED) - {"pact_type", "pact_code"} == video_identity_fields(profile)
    assert profile.dreamview_max_sub_devices == 5


def test_shared_video_control_grammar_does_not_grant_h6199_revision_policy():
    identity = SimpleNamespace(
        **(
            QUALIFIED
            | {
                "fw_version": "1.00.01",
                "hw_version": "1.00.01",
                "subordinate_20_version": "1.00.01",
                "subordinate_21_version": "1.00.01",
            }
        )
    )
    h6199 = video_control_states(get_profile("H6199"), identity)
    h605c = video_control_states(get_profile("H605C"), identity)

    assert get_profile("H6199").video_control_grammar is None
    assert get_profile("H605C").video_control_grammar == "H6199"
    assert h6199["white_balance"] is CapabilityState.UNSUPPORTED
    assert h605c["white_balance"] is CapabilityState.SUPPORTED
    assert camera_controls_state(get_profile("H605C"), identity) is CapabilityState.UNSUPPORTED


def test_pact1_profile_does_not_grant_native_camera_controls():
    from custom_components.ha_govee_led_ble.const import H6199_PACT1_PROFILE

    assert camera_controls_state(H6199_PACT1_PROFILE, SimpleNamespace(**QUALIFIED)) is CapabilityState.UNSUPPORTED


@pytest.mark.parametrize("revision", ["old", "qualified", "unknown"])
async def test_basic_setup_survives_optional_silence(hass, monkeypatch, revision, virtual_clock):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00020100")}))
    assert (coordinator.pact_type, coordinator.pact_code) == (2, 1)
    assert not coordinator._advertised_encryption
    if revision != "unknown":
        # Identity values are synthetic routing input, not an older-hardware test.
        for field, value in QUALIFIED.items():
            setattr(coordinator, field, value)
        coordinator._confirmed_identity_fields.update(video_identity_fields(coordinator.profile))
        if revision == "old":
            coordinator.fw_version = "1.00.01"
    replies = {
        build_power_query("H6199"): "aa0100",
        build_brightness_query("H6199"): "aa0432",
        build_colour_mode_query("H6199"): "aa051500",
    }
    packets = []

    async def transmit(_uuid, packet, **kwargs):
        packets.append(packet)
        if packet in replies:
            frame = bytes.fromhex(replies[packet]).ljust(19, b"\x00")
            coordinator._notify_callback(None, frame + bytes((xor_checksum(frame),)))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    await coordinator._async_update_data()
    assert coordinator.available
    assert coordinator._first_refresh_done
    assert coordinator.profile.setup_required_read_domains == {ReadDomain.POWER}
    optional = {
        build_white_balance_query("H6199"),
        build_blank_screen_query("H6199"),
        build_relative_brightness_query("H6199"),
    }
    assert bool(optional & set(packets)) is (revision == "qualified")
    if revision == "old":
        prior = replace(
            coordinator.capture_effect_control_state(), blank_screen=True, video_restore_controls=("blank_screen",)
        )
        monkeypatch.setattr(coordinator, "send_command", AsyncMock())
        monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
        assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
        assert coordinator.send_command.await_count == 1  # Power only, no newer register recovery.


async def test_only_queried_optional_controls_expire_after_silence(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    set_qualified_identity(coordinator)
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator.strip_direction = 1
    coordinator.camera_position = 1
    coordinator.gradient = 1
    coordinator.camera_status = "healthy"
    coordinator.white_balance_red = 22
    optional_baselines = {}

    await coordinator._send_state_queries(optional_baselines=optional_baselines, query_segments=False)

    assert {"strip_direction", "camera_position", "gradient", "camera_status"} <= optional_baselines.keys()
    assert "is_on" not in optional_baselines and "white_balance_red" not in optional_baselines
    coordinator._expire_optional_observations(optional_baselines)
    assert coordinator.strip_direction is coordinator.camera_position is coordinator.gradient is None
    assert coordinator.camera_status == "unknown"
    assert coordinator.white_balance_red == 22


async def test_missing_basic_reply_still_fails_setup(hass, monkeypatch):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_send_state_queries", AsyncMock(return_value=True))
    monkeypatch.setattr(coordinator, "_wait_for_revisions", AsyncMock(return_value=False))
    disconnect = AsyncMock()
    monkeypatch.setattr(coordinator, "_disconnect_if_current_locked", disconnect)
    with pytest.raises(UpdateFailed, match="unreachable at setup"):
        await coordinator._async_update_data()
    disconnect.assert_awaited()


async def test_reconnect_invalidates_all_h6199_revision_authorization(hass, monkeypatch, virtual_clock):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    vars(coordinator).update(QUALIFIED)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    async def connect(*args, **kwargs):
        assert all(
            getattr(coordinator, field) == QUALIFIED[field] for field in video_identity_fields(coordinator.profile)
        )
        assert not coordinator.identity_fields_confirmed()
        assert camera_controls_state(coordinator.profile, coordinator) is CapabilityState.SUPPORTED
        return client

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert client.write_gatt_char.await_count == 4
        assert coordinator._identity_incomplete()
        assert (coordinator.pact_type, coordinator.pact_code) == (2, 1)
    finally:
        await coordinator.disconnect()


@pytest.fixture
async def lifecycle(hass, monkeypatch, request, virtual_clock):
    """Only the radio is fake: connection, subscriptions, parsing, guards and polling are real."""
    from homeassistant.config_entries import current_entry
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.ha_govee_led_ble.const import DOMAIN
    from tests.test_h6199_native_controls import frame

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    target = getattr(request, "param", "H6199")
    model, pact = target if isinstance(target, tuple) else (target, 1 if target in {"H6139", "H6159", "H6182"} else 2)
    with current_entry.set(entry):
        c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url="test")
    c._present = True
    c._note_advertisement(
        SimpleNamespace(
            manufacturer_data={34818: bytes([0xEC, 0, pact, 1, 0])},
            source="test",
            time=hass.loop.time(),
        )
    )
    replies = {
        build_hardware_query("H6199"): frame("aa0703" + b"3.02.01".hex()),
        build_firmware_query("H6199"): frame("aa06" + b"1.10.04".hex()),
        build_subordinate_query(0x20, "H6199"): frame("aa20" + b"1.03.00".hex()),
        build_subordinate_query(0x21, "H6199"): frame("aa21" + b"1.00.33".hex()),
        build_power_query("H6199"): frame("aa0101"),
        build_brightness_query("H6199"): frame("aa0432"),
        build_colour_mode_query("H6199"): frame("aa051500"),
        build_white_balance_query("H6199"): frame("aaa90006011003011003"),
        build_h6199_control_query("strip_direction"): frame("aa3001"),
        build_h6199_control_query("camera_position"): frame("aa3101"),
        build_h6199_control_query("gradient"): frame("aaa301"),
        build_h6199_control_query("camera_status"): frame("aa3201"),
    }
    replies.update(
        {
            build_segment_query(group, "H6199"): frame("aaa5" + bytes([group, *([100, 1, 2, 3] * 4)]).hex())
            for group in range(1, c.profile.segment_group_count + 1)
        }
    )
    if c.model in {"H6139", "H6159", "H6182"}:
        later = c.model == "H6139" and pact == 10
        replies = {
            build_hardware_query(c.model): frame(
                "aa0703" + (b"2.01.01" if later else b"1.00.01" if c.model == "H6139" else b"1.00.02").hex()
            ),
            build_firmware_query(c.model): frame("aa06" + (b"2.04.00" if later else b"1.07.02").hex()),
            build_power_query(c.model): frame("aa0101"),
            build_brightness_query(c.model): frame("aa0432" if later else "aa0480"),
            build_colour_mode_query(c.model): frame("aa050d0c223800000000" if later else "aa05020c223800000000"),
        }
    clients, packets, timers = [], [], []

    async def connect(*args, **kwargs):
        client = MagicMock(is_connected=True)
        clients.append(client)
        receive = None
        next_notification = asyncio.get_running_loop().time()

        async def subscribe(_uuid, callback):
            nonlocal receive
            receive = callback

        async def transmit(_uuid, packet, **kwargs):
            nonlocal next_notification
            packets.append(packet)
            if packet[:3] == b"\x33\x05\x00":
                replies[build_colour_mode_query(c.model)] = frame("aa" + packet[1:-1].hex())
            if c.model == "H6199" and c.pact_type == 1 and packet[:2] == b"\x33\x05":
                replies[frame("aa0501")] = frame("aa050b00") if packet[2] == 0x0B else frame("aa" + packet[1:-1].hex())
            if c.model in {"H6139", "H6182"}:
                if packet[:2] == b"\x33\x04":
                    replies[build_brightness_query(c.model)] = frame("aa04" + packet[2:3].hex())
                elif packet[:2] == b"\x33\x05" and (c.model == "H6139" or packet[2] != 0x0D):
                    replies[build_colour_mode_query(c.model)] = frame("aa" + packet[1:-1].hex())
            if packet in replies:
                # A GATT write completes before the separate BLE notification arrives.
                loop = asyncio.get_running_loop()
                next_notification = max(loop.time() + 0.02, next_notification + 0.001)
                timers.append(loop.call_at(next_notification, receive, None, bytearray(replies[packet])))

        async def disconnect():
            client.is_connected = False
            kwargs["disconnected_callback"](client)

        client.start_notify = AsyncMock(side_effect=subscribe)
        client.write_gatt_char = AsyncMock(side_effect=transmit)
        client.disconnect = AsyncMock(side_effect=disconnect)
        return client

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.IDENTITY_QUERY_TIMEOUT", 0.08)
    monkeypatch.setattr(c, "_start_keep_alive", MagicMock())
    try:
        yield c, replies, clients, packets
    finally:
        await c.disconnect()
        for timer in timers:
            timer.cancel()


async def test_poll_preserves_delayed_native_replies_until_next_query(lifecycle, monkeypatch, virtual_clock):
    from custom_components.ha_govee_led_ble.light import GoveeBLELight
    from custom_components.ha_govee_led_ble.select import GoveeBLEControlSelect
    from custom_components.ha_govee_led_ble.sensor import GoveeBLECameraStatus

    c, replies, clients, _ = lifecycle
    entry = SimpleNamespace(runtime_data=c, entry_id="test")
    selects = [GoveeBLEControlSelect(entry, field) for field in ("strip_direction", "camera_position", "gradient")]
    sensor = GoveeBLECameraStatus(c)
    monkeypatch.setattr(sensor, "async_write_ha_state", Mock())
    remove = c.async_add_listener(sensor._handle_coordinator_update)
    light = GoveeBLELight(c)
    try:
        await c._async_update_data()
        assert c._client is None and not clients[-1].is_connected
        assert c.segment_state_source == "observed" and not c._segment_query_incomplete
        assert [entity.current_option for entity in selects] == ["anticlockwise", "bottom", "on"]
        assert sensor.native_value == "healthy" and light.available
        for control in ("strip_direction", "camera_position", "gradient", "camera_status"):
            del replies[build_h6199_control_query(control)]
        # Avoid the static-mode gradient companion answering the independent missing query.
        from tests.test_h6199_native_controls import frame

        replies[build_colour_mode_query("H6199")] = frame("aa05000100640064")
        await c._async_update_data()
        assert len(clients) == 2 and c._client is None
        assert all(entity.current_option is None for entity in selects)
        assert sensor.native_value == "healthy" and light.available
        assert c.camera_status == "unknown" and c.is_on and c._first_refresh_done
    finally:
        remove()


async def test_basic_setup_with_missing_identity_uses_real_lifecycle(lifecycle):
    c, replies, clients, _ = lifecycle
    del replies[build_firmware_query("H6199")]
    await c._async_update_data()
    assert c.is_on and c.available and c.camera_status == "unknown"
    assert c._client is None and clients[-1].disconnect.await_count == 1
    assert camera_controls_state(c.profile, c) is CapabilityState.EVIDENCE_GAP


@pytest.mark.parametrize("revision", ["reported", "modern"])
@pytest.mark.parametrize(
    "missing_domains",
    [(), ("power",), ("brightness",), ("colour_mode",), ("brightness", "colour_mode")],
)
async def test_issue_293_setup_requires_fresh_power_readback(lifecycle, revision, missing_domains, virtual_clock):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from tests.test_h6199_native_controls import frame

    c, replies, clients, packets = lifecycle
    # The newer controller's exact revision was not supplied.
    if revision == "reported":
        c.pact_type = c.pact_code = None
        replies[build_hardware_query("H6199")] = frame("aa0703" + b"1.00.01".hex())
        replies[build_firmware_query("H6199")] = frame("aa06" + b"1.07.02".hex())
    basic = {
        "power": build_power_query("H6199"),
        "brightness": build_brightness_query("H6199"),
        "colour_mode": build_colour_mode_query("H6199"),
    }
    allowed = {build_hardware_query("H6199"), build_firmware_query("H6199"), *basic.values()}
    for query in list(replies):
        if query not in allowed or query in {basic[domain] for domain in missing_domains}:
            del replies[query]

    if "power" not in missing_domains:
        await c._async_update_data()
        assert c.available and c.is_on and c._state_read_available
        if "brightness" not in missing_domains:
            assert c.brightness_pct == 50
        for domain in missing_domains:
            assert basic[domain] in packets
        connections = len(clients)
        await c._async_update_data()
        assert c.available and c._state_read_available
        assert len(clients) > connections
    else:
        c.is_on = True
        with pytest.raises(UpdateFailed, match="unreachable at setup"):
            await c._async_update_data()
        assert not c._state_read_available

    if revision == "reported":
        assert c.hw_version == "1.00.01" and c.fw_version == "1.07.02"
    assert c.subordinate_20_version is c.subordinate_21_version is None
    states = video_control_states(c.profile, c)
    assert all(
        states[control] is not CapabilityState.SUPPORTED
        for control in ("white_balance", "relative_brightness", "blank_screen")
    )
    assert not any(packet[0] == 0x33 or packet[1] in (0xA9, 0xAE, 0x30, 0x31, 0x32, 0xA3) for packet in packets)
    assert c._client is None and clients[-1].disconnect.await_count == 1


@pytest.mark.parametrize("domain", ["brightness", "colour_mode"])
async def test_optional_setup_readback_remains_required_when_requested(lifecycle, domain, virtual_clock):
    c, replies, _, _ = lifecycle
    queries = {
        "brightness": build_brightness_query("H6199"),
        "colour_mode": build_colour_mode_query("H6199"),
    }
    del replies[queries[domain]]
    await c._async_update_data()
    assert c._state_read_available

    assert not await c.refresh_state(
        RefreshRequest(refresh_all=True, required_domains=frozenset({ReadDomain(domain)}), query_segments=False),
    )
