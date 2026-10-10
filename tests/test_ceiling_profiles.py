"""Exact ceiling profiles and conservative revision gates."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import (
    ReadDomain,
    SupportQuality,
    device_profile,
    get_profile,
    model_from_ble_name,
    resolve_model,
    supported_effect_categories,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness, require_profile_packet
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_segment_color


@pytest.mark.parametrize("model", ["H60A1", "H60A6", "H601C"])
def test_manual_exact_experimental_profiles_have_no_catalogue_inheritance(model):
    p = get_profile(model)
    assert resolve_model(model.lower()) == model and p.support_quality is SupportQuality.EXPERIMENTAL
    assert model_from_ble_name(f"Govee_{model}_test") is None
    assert p.command_operations == {"power", "brightness", "static"}
    assert supported_effect_categories(model) == ()
    assert p.effect_grammar is None and p.scene_catalogue_sku is None
    assert not p.supports_segment_brightness and not p.supports_segment_color_temperature
    assert not p.supports_custom_effects and not p.supports_music_mode and not p.supports_scenes
    assert not p.static_readback_echoes_color or model == "H601C"
    require_profile_packet(build_brightness(50, model), p)
    assert resolve_model("H60C1") is None


@pytest.mark.parametrize(
    ("model", "pact", "hardware", "firmware", "segmented"),
    [
        ("H60A1", (None, None), None, None, False),
        ("H60A1", (2, 1), None, None, True),
        ("H60A1", (1, 1), "1.04.03", "1.02.20", True),
        ("H60A1", (1, 1), None, None, False),
        ("H60A1", (1, 1), "1.04.03", "1.02.21", False),
        ("H60A1", (3, 1), "1.04.03", "1.02.20", False),
        ("H60A1", (None, None), "1.04.03", "1.02.20", True),
        ("H60A1", (None, None), "1.04.04", "1.02.20", False),
        ("H60A1", (None, None), "1.04.03", "1.02.21", False),
        ("H60A6", (None, None), None, None, False),
        ("H60A6", (1, 1), "1.04.03", "1.00.41", False),
        ("H60A6", (1, 2), None, None, True),
        ("H60A6", (1, 3), None, None, True),
        ("H60A6", (None, None), "1.04.03", "1.00.41", True),
        ("H60A6", (None, None), "1.04.03", "1.00.42", False),
        ("H60A6", (None, 2), "1.04.03", "1.00.41", False),
        ("H60A6", (1, None), "1.04.03", "1.00.41", False),
        ("H60A6", (2, 1), None, None, False),
    ],
)
def test_geometry_requires_positive_revision_evidence(model, pact, hardware, firmware, segmented):
    p = device_profile(model, *pact, hardware=hardware, firmware=firmware)
    assert p.supports_segments is segmented and p.supports_rgb is segmented
    assert p.can_read(ReadDomain.SEGMENTS) is segmented
    assert p.segment_count == (14 if model == "H60A1" else 1 if pact == (1, 1) else 13)
    assert p.segment_group_count == (4 if segmented else 0)
    assert not p.can_read(ReadDomain.BRIGHTNESS) and not p.supports_color_mode_readback
    assert not p.supports_color_temperature and not p.supports_segment_color_temperature
    if segmented:
        require_profile_packet(build_segment_color([p.segment_count], 1, 2, 3, model, profile=p), p)
        with pytest.raises(ValueError, match="out of range"):
            build_segment_color([p.segment_count + 1], 1, 2, 3, model, profile=p)
    else:
        with pytest.raises(ValueError, match="RGB"):
            build_color_rgb(1, 2, 3, model, profile=p)
        with pytest.raises(ValueError, match="per-segment"):
            build_segment_color([1], 1, 2, 3, model, profile=p)


@pytest.mark.parametrize(
    ("hardware", "minimum"), [(None, 2700), ("bad", 2700), ("1.04.02", 2200), ("1.04.03", 2700), ("1.05.00", 2700)]
)
def test_h60a1_kelvin_bounds_track_hardware_without_authorizing_writes(hardware, minimum):
    p = device_profile("H60A1", 2, 1, hardware=hardware)
    assert (p.min_color_temp_kelvin, p.max_color_temp_kelvin) == (minimum, 6500)
    assert not p.supports_color_temperature


@pytest.mark.parametrize("pact", [(None, None), (1, 1), (2, 1), (2, 2), (3, 1)])
def test_h601c_basic_app_encoding_has_no_artificial_revision_restriction(pact):
    p = device_profile("H601C", *pact)
    assert p == get_profile("H601C") and p.command_grammar == p.status_grammar == "H601C"
    assert p.supports_rgb and p.supports_color_temperature and p.whole_device_mask == 1
    assert (p.min_color_temp_kelvin, p.max_color_temp_kelvin) == (2700, 6500)
    assert p.read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.COLOUR_MODE,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
    }
    assert p.static_readback_echoes_color and p.static_readback_kelvin and p.static_readback_zero_kelvin_is_rgb
    assert not p.supports_segments
    require_profile_packet(build_color_rgb(1, 2, 3, "H601C"), p)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_late_identity_and_pact_revalidate_prepared_segment_write(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.config_entry = MagicMock(entry_id="test-entry")
    assert not c.profile.supports_segments
    c._note_identity(hw_version="1.04.03")
    assert not c.profile.supports_segments
    c._note_identity(fw_version="1.02.20" if model == "H60A1" else "1.00.41")
    assert c.profile.supports_segments and c._profile_generation == 1
    packet = build_segment_color([1], 1, 2, 3, model, profile=c.profile)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    # Drop the tuple before selecting the unqualified legacy advertisement.
    c._note_identity(fw_version="1.00.00")
    assert not c.profile.supports_segments and c._profile_generation == 2
    c._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 1, 1, 0))}))
    assert not c.profile.supports_segments and c._profile_generation == (3 if model == "H60A6" else 2)
    before = c.capture_effect_control_state()
    with pytest.raises(ValueError):
        await c._async_write_packet(client, packet, arm_expected=True)
    assert c.control_write_attempts == 0 and c.capture_effect_control_state() == before
    client.write_gatt_char.assert_not_awaited()
    assert not await c.async_refresh_segments(timeout=0.01)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
@pytest.mark.parametrize("qualified", [False, True])
async def test_ceiling_entity_panel_brightness_is_one_write_without_readback(hass, monkeypatch, model, qualified):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    if qualified:
        c.pact_type, c.pact_code = (2, 1) if model == "H60A1" else (1, 2)
        c._resolve_device_profile()
    c.is_on = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(c, "refresh_state", AsyncMock(side_effect=AssertionError("brightness is write-only")))
    light = GoveeBLELight(c)
    light.async_write_ha_state = MagicMock()
    assert light.supported_color_modes == {ColorMode.RGB if qualified else ColorMode.BRIGHTNESS}
    assert light.color_mode in light.supported_color_modes
    await light.async_turn_on(brightness=128)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [build_brightness(50, model)]
    assert light.brightness == 128 and c.brightness_pct == 50
    assert c._field_revisions == {} and c.control_write_attempts == 1
    c.refresh_state.assert_not_awaited()
    before = c.capture_effect_control_state()
    client.write_gatt_char.side_effect = RuntimeError("failed write")
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(brightness=200)
    assert c.capture_effect_control_state() == before


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_reconnect_revokes_cached_tuple_before_await(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.02.20" if model == "H60A1" else "1.00.41"
    c._resolve_device_profile()
    packet = build_segment_color([1], 1, 2, 3, model, profile=c.profile)

    async def establish(*args, **kwargs):
        assert c.hw_version is None and c.fw_version is None
        assert not c.profile.supports_rgb and not c.profile.supports_segments
        with pytest.raises(ValueError):
            require_profile_packet(packet, c.profile)
        raise RuntimeError("stop before connecting")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", establish)
    with pytest.raises(RuntimeError, match="stop before connecting"):
        await c._ensure_connected()
    assert c.control_write_attempts == 0


@pytest.mark.parametrize("model", ["H60A1", "H60A6", "H601C"])
async def test_invalid_basic_request_precedes_preview_and_power(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    light = GoveeBLELight(c)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(c, "send_command", AsyncMock())
    before = c.capture_effect_control_state()
    request = {"brightness": 128, "color_temp_kelvin": 2750}
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(**request)
    light._async_supersede_preview.assert_not_awaited()
    c.send_command.assert_not_awaited()
    assert c.capture_effect_control_state() == before


@pytest.mark.parametrize("stored", [128, None, "128", -1, 256, True])
async def test_write_only_brightness_restores_as_retained_knowledge(hass, monkeypatch, stored):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A1", configuration_url=None)
    light = GoveeBLELight(c)
    monkeypatch.setattr(
        light, "async_get_last_state", AsyncMock(return_value=SimpleNamespace(attributes={"brightness": stored}))
    )
    await light._async_restore_brightness()
    expected = 50 if type(stored) is int and stored == 128 else 100
    assert c.brightness_pct == expected and c._field_revisions == {}
    c.pact_type, c.pact_code = 2, 1
    c._resolve_device_profile()
    assert c.brightness_pct == expected


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_exact_segment_restoration_fails_before_appearance_writes(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.pact_type, c.pact_code = (2, 1) if model == "H60A1" else (1, 2)
    c._resolve_device_profile()
    c.is_on = True
    c.segment_state_source = "observed"
    state = c.capture_effect_control_state()
    monkeypatch.setattr(c, "send_command", AsyncMock())
    assert not await c.async_restore_effect_control_state(state, overwritten_diy_code=None)
    c.send_command.assert_not_awaited()


@pytest.mark.parametrize("blocked", ["existing", "during_restore", "readable"])
async def test_brightness_restore_never_overwrites_current_control(hass, monkeypatch, blocked):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A1", configuration_url=None)
    light = GoveeBLELight(c)
    c.brightness_pct = 25
    if blocked == "existing":
        c.control_write_attempts = 1
    if blocked == "readable":
        c.profile = replace(c.profile, read_domains=c.profile.read_domains | {ReadDomain.BRIGHTNESS})

    async def stored():
        if blocked == "during_restore":
            c.control_write_attempts += 1
        return SimpleNamespace(attributes={"brightness": 128})

    monkeypatch.setattr(light, "async_get_last_state", stored)
    await light._async_restore_brightness()
    assert c.brightness_pct == 25 and c._field_revisions == {}
