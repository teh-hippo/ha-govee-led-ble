"""Software-only checks for the temporary #532 hardware-testing surface."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import current_entry
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble import button, number, select, switch
from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.dreamview import build_dreamview_command, build_dreamview_query
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_video_mode, parse_command
from custom_components.ha_govee_led_ble.video_test_controls import (
    GoveeBLEVideoTestNumber,
    GoveeBLEVideoTestSelect,
    GoveeBLEVideoTestSwitch,
)
from tests.test_h6199_native_controls import frame, qualify


@pytest.fixture
def test_device(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={"address": "11:22:33:44:55:66", "model": "H6199"})
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    qualify(c)
    c._resolve_device_profile()
    c._notification_token = object()
    c._client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=c._client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    state = {
        "effect": build_video_mode("game", True, 75, False, 80, "H6199"),
        "saturation": build_dreamview_command("saturation", {"saturation": 25}, c.profile),
        "video_settings": build_dreamview_command("video_settings", {"apply_area": 1, "content_mode": 0}, c.profile),
        "sound": build_dreamview_command("sound", {"enabled": True, "softness": 30}, c.profile),
    }
    missing = set()
    writes = []

    async def respond(_uuid, packet, **kwargs):
        if packet[0] == 0x33:
            writes.append(packet)
            if packet[1] == 5:
                state["effect"] = packet
            else:
                for setting in ("saturation", "video_settings", "sound"):
                    if packet[1] == state[setting][1]:
                        state[setting] = packet
            return
        reply = {frame("aa01"): frame("aa0101"), frame("aa04"): frame("aa0464")}.get(packet)
        if packet == frame("aa05") and "effect" not in missing:
            reply = frame("aa" + state["effect"][1:-1].hex())
        for setting in ("saturation", "video_settings", "sound"):
            if packet == build_dreamview_query(setting, c.profile) and setting not in missing:
                reply = frame("aa" + state[setting][1:-1].hex())
        if reply is not None:
            c._notify_callback(None, bytearray(reply))

    c._client.write_gatt_char.side_effect = respond
    wrapped_entry = SimpleNamespace(runtime_data=c, entry_id=entry.entry_id, async_on_unload=Mock())
    return c, wrapped_entry, state, missing, writes


def entity(kind, entry, control, hass):
    result = kind(entry, control)
    result.hass = hass
    return result


async def test_platforms_expose_both_banks_only_for_h6199(test_device, hass):
    c, entry, _, _, _ = test_device
    added = []
    for platform in (button, number, select, switch):
        await platform.async_setup_entry(hass, entry, added.extend)
    controls = [e for e in added if "_video_test_" in e.unique_id]
    assert len(controls) == 11
    assert all(e.available and e.entity_registry_enabled_default for e in controls)
    assert len({e.unique_id for e in controls}) == 11
    c.model = "H617A"
    assert all(not e.available for e in controls)
    added.clear()
    for platform in (button, number, select, switch):
        await platform.async_setup_entry(hass, entry, added.extend)
    assert not any("_video_test_" in e.unique_id for e in added)
    for call in entry.async_on_unload.call_args_list:
        call.args[0]()


async def test_both_banks_readback_and_missing_replies_are_not_remembered(test_device, hass, virtual_clock):
    c, entry, _, missing, writes = test_device
    read = button.GoveeBLEVideoTestReadButton(c)
    effect = entity(GoveeBLEVideoTestNumber, entry, "effect_saturation", hass)
    device = entity(GoveeBLEVideoTestNumber, entry, "device_saturation", hass)
    assert effect.native_value is device.native_value is None
    await read.async_press()
    assert effect.native_value == 75 and device.native_value == 25
    attrs = read.extra_state_attributes
    assert attrs["effect"]["mode"] == "game" and attrs["effect_missing_reads"] == []
    assert attrs["device"]["observed"]["video_settings"]["apply_area"] == "part"
    assert "member_connect" in attrs["device"]["missing_reads"]
    assert not any(key.startswith("_") for key in attrs) and writes == []
    missing.update(("effect", "saturation"))
    await read.async_press()
    assert effect.native_value is device.native_value is None
    assert "saturation" in read.extra_state_attributes["effect_missing_reads"]
    assert "saturation" in read.extra_state_attributes["device"]["missing_reads"]
    c._notification_token = object()
    assert not read.extra_state_attributes["current_subscription"]


@pytest.mark.parametrize(
    ("kind", "control", "value", "expected_prefix"),
    [
        (GoveeBLEVideoTestNumber, "device_saturation", 0, "335100"),
        (GoveeBLEVideoTestNumber, "device_softness", 0, "33530100"),
        (GoveeBLEVideoTestSwitch, "device_enabled", False, "3353001e"),
        (GoveeBLEVideoTestSelect, "device_apply_area", "all", "33520000"),
        (GoveeBLEVideoTestSelect, "device_content_mode", "movie", "33520101"),
        (GoveeBLEVideoTestNumber, "effect_saturation", 1, "3305000101010050"),
        (GoveeBLEVideoTestNumber, "effect_sound_effects_softness", 1, "33050001014b0001"),
        (GoveeBLEVideoTestSwitch, "effect_sound_effects", True, "33050001014b0150"),
        (GoveeBLEVideoTestSelect, "effect_full_screen", "part", "33050000014b0050"),
        (GoveeBLEVideoTestSelect, "effect_mode", "movie", "33050001004b0050"),
    ],
)
async def test_writes_touch_only_one_bank_and_preserve_siblings(
    test_device, hass, virtual_clock, kind, control, value, expected_prefix
):
    c, entry, state, _, writes = test_device
    before = dict(state)
    control_entity = entity(kind, entry, control, hass)
    if kind is GoveeBLEVideoTestNumber:
        await control_entity.async_set_native_value(value)
        assert control_entity.native_value == value
    elif kind is GoveeBLEVideoTestSelect:
        await control_entity.async_select_option(value)
        assert control_entity.current_option == value
    elif value:
        await control_entity.async_turn_on()
        assert control_entity.is_on
    else:
        await control_entity.async_turn_off()
        assert control_entity.is_on is False
    assert len(writes) == 1 and writes[0].startswith(bytes.fromhex(expected_prefix))
    if control.startswith("effect_"):
        assert {key: packet for key, packet in state.items() if key != "effect"} == {
            key: packet for key, packet in before.items() if key != "effect"
        }
    else:
        assert state["effect"] == before["effect"]
    assert c.video_test_readback["read_at"]


async def test_missing_siblings_and_invalid_values_never_write(test_device, hass, virtual_clock):
    _, entry, _, missing, writes = test_device
    softness = entity(GoveeBLEVideoTestNumber, entry, "device_softness", hass)
    missing.add("sound")
    with pytest.raises(ServiceValidationError):
        await softness.async_set_native_value(20)
    assert writes == []
    effect = entity(GoveeBLEVideoTestNumber, entry, "effect_saturation", hass)
    for value in (0, 101, 2.5, float("nan")):
        with pytest.raises(ServiceValidationError):
            await effect.async_set_native_value(value)
    assert writes == []


async def test_effect_activation_has_explicit_baseline(test_device, hass, virtual_clock):
    c, entry, state, _, writes = test_device
    state["effect"] = frame("33051500")
    mode = entity(GoveeBLEVideoTestSelect, entry, "effect_mode", hass)
    await mode.async_select_option("game")
    parsed = parse_command(writes[0], "H6199").body.detail
    assert (parsed.region.name, parsed.saturation, parsed.sound_effects, parsed.softness) == ("all", 100, 0, 100)
    assert c.video_test_readback["effect"]["mode"] == "game"


async def test_connection_change_before_device_write_preserves_both_banks(
    test_device, hass, monkeypatch, virtual_clock
):
    c, entry, _, _, writes = test_device
    control = entity(GoveeBLEVideoTestNumber, entry, "device_softness", hass)
    original = c._async_write_dreamview

    async def reconnect(*args, **kwargs):
        c._notification_token = object()
        await original(*args, **kwargs)

    monkeypatch.setattr(c, "_async_write_dreamview", reconnect)
    with pytest.raises(ServiceValidationError):
        await control.async_set_native_value(20)
    assert writes == []


async def test_read_transport_failure_surfaces_as_ha_error(test_device):
    c, _, _, _, _ = test_device
    c._client.write_gatt_char.side_effect = RuntimeError("transport failed")
    with pytest.raises(HomeAssistantError):
        await button.GoveeBLEVideoTestReadButton(c).async_press()
    assert c.video_test_readback is None
