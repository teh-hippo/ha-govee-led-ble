"""H617A review regressions and remaining findings; never connect to a real radio."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _STATUS_ROOTS,
    MusicBody,
    StatusReply,
    build_segment_colour,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_temp,
    build_segment_color,
    kelvin_to_rgb,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.music_commands import resolve_music_profile
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def frame(domain, body):
    payload = bytes([0xAA, domain, *body]).ljust(19, b"\x00")
    return bytearray(payload + bytes([xor_checksum(payload)]))


def observe_segments(coordinator, colours, brightness):
    for offset in range(0, 15, 3):
        body = [offset // 3 + 1]
        for index in range(offset, offset + 3):
            body.extend([brightness[index], *colours[index]])
        coordinator._notify_callback(None, frame(0xA5, body))


@pytest.fixture
def coordinator(hass):
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")


@pytest.mark.parametrize("accept_colour", [True, False])
async def test_restoration_preserves_segments_and_rejects_wrong_readback(coordinator, accept_colour):
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.brightness_pct = 37
    coordinator.rgb_color = (10, 20, 30)
    original = [(10, 20, 30)] * 14 + [(90, 80, 70)]
    brightness = [30] * 14 + [70]
    observe_segments(coordinator, original, brightness)
    prior = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
    observe_segments(coordinator, [(1, 2, 3)] * 15, [100] * 15)
    assert coordinator.capture_effect_control_state() != prior  # uniform RGB can update the aggregate
    coordinator.rgb_color = prior.rgb_color
    observe_segments(coordinator, [(4, 5, 6)] * 14 + [(7, 8, 9)], [50] * 15)
    assert coordinator.capture_effect_control_state() != prior
    physical = list(original)
    if not accept_colour:
        physical = [(1, 2, 3)] * 15
    writes = []
    physical_brightness = [100] * 15

    async def transmit(_uuid, packet, **_kwargs):
        writes.append(packet)
        if packet[0] == 0x33:
            static = parse_static_write(packet)
            if static is not None and static.rgb is not None and accept_colour:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        physical[index] = static.rgb
            if static is not None and static.brightness_pct is not None:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        physical_brightness[index] = static.brightness_pct
        elif packet[1] == 1:
            coordinator._notify_callback(None, frame(1, [1]))
        elif packet[1] == 5:
            coordinator._notify_callback(None, frame(5, [0x15, 0]))
        elif packet[1] == 4:
            coordinator._notify_callback(None, frame(4, [37]))
        elif packet[1] == 0xA5 and packet[2] == 5:
            observe_segments(coordinator, physical, physical_brightness)

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    with (
        patch.object(coordinator, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coordinator, "_renew_foreground_lease"),
    ):
        assert await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None) is accept_colour
    assert any(packet[:2] == b"\xaa\xa5" for packet in writes)
    assert any(packet[:2] == b"\xaa\x04" for packet in writes)
    assert physical_brightness == brightness
    if accept_colour:
        assert physical == original
    else:
        assert physical == [(1, 2, 3)] * 15


async def test_whole_colour_failure_reconciles_uncertain_segments(coordinator):
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.COLOUR
    original = [(10, 20, 30)] * 15
    observe_segments(coordinator, original, [100] * 15)
    observed_at = coordinator.segment_state_observed_at
    physical = list(original)

    async def transmit(_uuid, packet, **_kwargs):
        static = parse_static_write(packet)
        assert static is not None and static.rgb == (90, 80, 70)
        physical[:] = [static.rgb] * 15
        raise BleakError("simulated write applied before transport error")

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    with (
        patch.object(coordinator, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coordinator, "_disconnect_locked", AsyncMock()),
        patch.object(coordinator, "async_refresh_segments", AsyncMock()) as refresh,
        pytest.raises(HomeAssistantError),
    ):
        await light.async_turn_on(rgb_color=(90, 80, 70))
    assert client.write_gatt_char.await_count == 3
    assert physical != original
    assert coordinator.segment_colors == physical
    assert coordinator.segment_state_source == "optimistic"
    assert coordinator.segment_state_observed_at is None
    assert observed_at is not None
    refresh.assert_awaited_once()


@pytest.mark.parametrize(
    "colour_request", [{"rgb_color": (90, 80, 70)}, {"color_temp_kelvin": 5000}, {"effect": "off"}]
)
@pytest.mark.parametrize("fresh_notification", [False, True])
async def test_static_connection_failure_preserves_observed_state(coordinator, colour_request, fresh_notification):
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.COLOUR
    original = [(10, 20, 30)] * 15
    observe_segments(coordinator, original, [70] * 15)
    before = coordinator.capture_effect_control_state()
    observed_at = coordinator.segment_state_observed_at
    revisions = dict(coordinator._field_revisions)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    async def connect():
        if fresh_notification:
            observe_segments(coordinator, [(1, 2, 3)] * 15, [40] * 15)
        raise BleakError("connection failed before physical write")

    light = GoveeBLELight(coordinator)
    with (
        patch.object(coordinator, "_ensure_connected", AsyncMock(side_effect=connect)),
        patch.object(coordinator, "_disconnect_locked", AsyncMock()),
        patch.object(coordinator, "async_refresh_segments", AsyncMock()) as refresh,
        pytest.raises(HomeAssistantError),
    ):
        coordinator._client = client
        await light.async_turn_on(**colour_request)
    client.write_gatt_char.assert_not_awaited()
    refresh.assert_not_awaited()
    assert coordinator.control_write_attempts == 0
    assert getattr(coordinator, "_static_write_attempts", 0) == 0
    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_state_observed_at is not None
    if fresh_notification:
        assert coordinator.segment_colors == [(1, 2, 3)] * 15
        assert coordinator.segment_brightness == [40] * 15
        assert coordinator.rgb_color == (1, 2, 3) and coordinator.rgb_color_source == "segment"
        assert coordinator._field_revisions["segment_colors"] > revisions["segment_colors"]
    else:
        assert coordinator.capture_effect_control_state() == before
        assert coordinator.segment_state_observed_at == observed_at
        assert coordinator._field_revisions == revisions


@pytest.mark.parametrize(
    "colour_request", [{"rgb_color": (90, 80, 70)}, {"color_temp_kelvin": 5000}, {"effect": "off"}]
)
@pytest.mark.parametrize("mixed", [False, True])
async def test_static_attempt_failure_keeps_new_segment_notification(coordinator, colour_request, mixed):
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.COLOUR
    observe_segments(coordinator, [(10, 20, 30)] * 15, [70] * 15)
    coordinator.install_static_color(kelvin=4000)
    revision = coordinator._field_revisions["segment_colors"]
    observed = [(1, 2, 3)] * 15
    if mixed:
        observed[0] = (9, 8, 7)

    async def transmit(_uuid, _packet, **_kwargs):
        assert coordinator.segment_state_source == "optimistic"
        assert coordinator.segment_state_observed_at is None
        coordinator._expected_state.clear()
        observe_segments(coordinator, observed, [40] * 15)
        raise RuntimeError("write failed after fresh notification")

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    with (
        patch.object(coordinator, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coordinator, "async_refresh_segments", AsyncMock()) as refresh,
        pytest.raises(HomeAssistantError),
    ):
        await GoveeBLELight(coordinator).async_turn_on(**colour_request)
    client.write_gatt_char.assert_awaited_once()
    refresh.assert_awaited_once()
    assert coordinator.control_write_attempts == 1
    assert coordinator.segment_colors == observed and coordinator.segment_brightness == [40] * 15
    assert coordinator.segment_state_source == "observed" and coordinator.segment_state_observed_at is not None
    if not mixed:
        assert coordinator.rgb_color == (1, 2, 3) and coordinator.rgb_color_source == "segment"
    assert coordinator.color_temp_kelvin is None
    assert coordinator._field_revisions["segment_colors"] == revision + 1


def test_nonuniform_segment_observation_invalidates_global_kelvin(coordinator):
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.install_static_color(kelvin=4000)
    colours = [kelvin_to_rgb(4000)] * 15
    observe_segments(coordinator, colours, [100] * 15)
    colours[0] = (0, 0, 255)
    observe_segments(coordinator, colours, [100] * 15)
    light = GoveeBLELight(coordinator)
    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_colors[0] == (0, 0, 255)
    assert light.color_mode is ColorMode.RGB
    assert light.color_temp_kelvin is None


@pytest.mark.parametrize("mode", ["spectrum", "rolling"])
def test_h617a_music_fixed_colour_compiler_and_catalogue_agree(mode):
    item = LibraryItem.new("Fixed music", MusicProfile("H617A", mode, 50, colour=(32, 96, 160)))
    compiled = compile_application(item, "H617A")
    assert compiled.colour == (32, 96, 160)
    assert len(compiled.packets) == 2
    assert MODEL_EFFECT_CATALOGUES["H617A"].to_dict()["music_settings"][mode]["colour"] is True
    assert compiled.packets[1][5:10] == bytes.fromhex("00012060a0")


def test_h617a_energetic_rejects_fixed_colour():
    item = LibraryItem.new("Fixed music", MusicProfile("H617A", "energetic", 50, colour=(32, 96, 160)))
    with pytest.raises(ValueError, match="fixed music colour"):
        compile_application(item, "H617A")
    assert MODEL_EFFECT_CATALOGUES["H617A"].to_dict()["music_settings"]["energetic"]["colour"] is False


@pytest.mark.parametrize(
    "mode,params,extra",
    [
        ("bloom", {}, {"palette": [(32, 96, 160), (160, 96, 32)]}),
        ("piano_keys", {"gradient": True}, {}),
        ("hopping", {"background": 0x2060A0}, {}),
    ],
)
def test_apk_reachable_music_fields_resolve_and_encode(mode, params, extra):
    calm, resolved, packets = resolve_music_profile("H617A", mode, 50, None, None, params, **extra)
    assert calm is False
    assert resolved.items() >= params.items()
    assert [packet[0] for packet in packets] == [0x33, *([0xA3] * (len(packets) - 2)), 0x33]
    body = MusicBody.from_bytes(reassemble_a3(packets[1:-1]))
    body._read()
    assert body.mode.name == mode
    if mode == "bloom":
        assert [(rgb.red, rgb.green, rgb.blue) for rgb in body.palette] == extra["palette"]
    elif mode == "piano_keys":
        assert body.tail.gradient == 1
    else:
        assert (body.tail.background.red, body.tail.background.green, body.tail.background.blue) == (32, 96, 160)


async def test_declared_read_only_segments_are_disabled_by_write_capability(hass, monkeypatch):
    model = "H9903"
    monkeypatch.setitem(_STATUS_ROOTS, "REVIEW_H617A_STATUS", ("status_reply", StatusReply))
    profile = ModelProfile(
        "Synthetic read-only segments",
        command_grammar="H617A",
        status_grammar="REVIEW_H617A_STATUS",
        read_domains=frozenset({ReadDomain.SEGMENTS}),
        segment_count=15,
        segment_group_size=3,
    )
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="test")
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    observe_segments(coordinator, [(10, 20, 30)] * 15, [100] * 15)
    assert coordinator.segment_state_source == "initial"
    assert await coordinator._send_state_queries(
        query_power=False, query_brightness=False, query_color_mode=False, query_segments=True
    )
    assert not await coordinator.async_refresh_segments()
    client.write_gatt_char.assert_not_awaited()
    assert coordinator._field_revisions == {}


def test_profile_kelvin_range_is_overridden_by_adapter_constant(monkeypatch):
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H9904",
        ModelProfile(
            "Synthetic wider Kelvin range",
            command_grammar="H617A",
            supports_color_temperature=True,
            min_color_temp_kelvin=1500,
            max_color_temp_kelvin=10000,
            whole_device_mask=0x7FFF,
        ),
    )
    parsed = parse_static_write(build_color_temp(1500, "H9904"), "H9904")
    assert parsed.kelvin == 2000
    assert parsed.kelvin_companion_rgb == kelvin_to_rgb(1500)


def test_declared_sixteenth_segment_encodes_but_semantic_builder_rejects(monkeypatch):
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H9905",
        ModelProfile(
            "Synthetic sixteen segment writer",
            command_grammar="H617A",
            segment_count=16,
            supports_segment_writes=True,
            whole_device_mask=0xFFFF,
        ),
    )
    wire = build_segment_colour(0x8000, 1, 2, 3, "H9905")
    assert parse_static_write(wire, "H9905").segment_mask == 0x8000
    with pytest.raises(ValueError, match="out of range 1..15"):
        build_segment_color([16], 1, 2, 3, "H9905")
