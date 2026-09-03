import json
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_CATEGORIES,
    CONF_MODEL,
    CONF_PREFIX_EFFECT_NAMES,
    DOMAIN,
    MODEL_PROFILES,
    StaticWriteVerificationPolicy,
    default_effect_categories,
    model_from_ble_name,
    protocol_model,
    resolve_model,
    wire_model,
)

_CONFIG_FLOW = "custom_components.ha_govee_led_ble.config_flow"
_ADDRESS = "11:22:33:44:55:66"
_PREFIXES = ("ihoment", "Govee", "GBK", "GVH")
_SERVICE_INFO = BluetoothServiceInfo("Govee_H6179_ABCD", _ADDRESS, -60, {}, {}, [], "local")


@pytest.fixture(autouse=True)
async def mock_bluetooth(hass, enable_custom_integrations):
    hass.config.components |= {"bluetooth", "bluetooth_adapters"}


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_h6179_model_resolution_is_exact(prefix: str):
    assert model_from_ble_name(f"{prefix}_H6179_ABCD") == "H6179"
    assert model_from_ble_name(f"{prefix}_H6179") == "H6179"
    assert model_from_ble_name(f"{prefix}_H61790_ABCD") is None
    assert model_from_ble_name(f"{prefix}_H6179A_ABCD") is None
    assert model_from_ble_name(f"Other_{prefix}_H6179_ABCD") is None


def test_h6179_manifest_matching_is_exact():
    manifest = json.loads(
        (Path(__file__).parents[1] / "custom_components/ha_govee_led_ble/manifest.json").read_text(encoding="utf-8")
    )
    patterns = [matcher["local_name"] for matcher in manifest["bluetooth"]]
    expected = {f"{prefix}_H6179_*" for prefix in _PREFIXES}

    assert set(pattern for pattern in patterns if "H6179" in pattern) == expected
    for prefix in _PREFIXES:
        assert any(fnmatchcase(f"{prefix}_H6179_ABCD", pattern) for pattern in patterns)
        assert not any(fnmatchcase(f"{prefix}_H61790_ABCD", pattern) for pattern in patterns)
        assert not any(fnmatchcase(f"{prefix}_H6179A_ABCD", pattern) for pattern in patterns)


def test_h6179_profile_enables_only_approved_broad_capabilities():
    profile = MODEL_PROFILES["H6179"]

    assert resolve_model(" h6179 ") == "H6179"
    assert wire_model("H6179") == "H6179"
    assert protocol_model("H6179") == "H6179"
    assert profile.name == "H6179 RGB TV Backlight"
    assert profile.wire_model == "H6179"
    assert not profile.state_readable
    assert profile.supports_notifications
    assert profile.queryable_status_domains == {
        "power",
        "brightness",
        "firmware",
        "hardware",
        "mode",
        "schedules",
        "sleep",
        "wake",
        "limit",
    }
    assert profile.setup_required_status_domains == {"power", "brightness"}
    assert profile.provisional_status_domains == {"mode", "schedules", "sleep", "wake", "limit"}
    assert profile.static_write_verification is StaticWriteVerificationPolicy.OPTIONAL
    assert profile.connection_idle_timeout is None
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2000, 9000)
    assert all(
        (
            profile.supports_power,
            profile.supports_brightness,
            profile.supports_rgb,
            profile.supports_color_temperature,
            profile.supports_color_mode_readback,
            profile.supports_custom_effects,
            profile.supports_scenes,
            profile.supports_music_mode,
            profile.supports_music_color,
            profile.supports_multi_layered_effects,
            profile.supports_clock_sync,
            profile.supports_schedules,
            profile.supports_sleep,
            profile.supports_wake,
            profile.supports_limit_control,
            profile.supports_reactive_rgb,
        )
    )
    assert profile.music_modes == ("mode_0", "mode_1")
    assert not any(
        (
            profile.supports_video_mode,
            profile.supports_video_sound_effects,
            profile.supports_advanced_effects,
            profile.supports_white_balance,
            profile.supports_relative_brightness,
            profile.supports_blank_screen,
            profile.supports_segments,
        )
    )
    assert default_effect_categories("H6179") == (
        "scenes",
        "effects",
        "multi_layered",
        "reactive",
    )


def test_state_readable_remains_replaceable_during_status_migration():
    profile = MODEL_PROFILES["H617A"]

    replaced = replace(profile, state_readable=False)

    assert profile.state_readable
    assert not replaced.state_readable
    assert replaced.supports_notifications == profile.supports_notifications
    assert replaced.queryable_status_domains == profile.queryable_status_domains


def test_existing_model_profiles_retain_their_behaviour():
    assert MODEL_PROFILES["H617E"] is MODEL_PROFILES["H617A"]
    assert {
        model: (
            wire_model(model),
            protocol_model(model),
            profile.state_readable,
            profile.supports_power,
            profile.supports_brightness,
            profile.supports_rgb,
            profile.supports_color_temperature,
            profile.supports_color_mode_readback,
            profile.supports_scenes,
            profile.supports_music_mode,
            profile.supports_video_mode,
            profile.supports_segments,
            profile.connection_idle_timeout,
            default_effect_categories(model),
        )
        for model, profile in MODEL_PROFILES.items()
        if model != "H6179"
    } == {
        "H617A": (
            "H617A",
            "H617A",
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            True,
            3.0,
            ("scenes", "effects", "multi_layered", "reactive", "advanced"),
        ),
        "H617E": (
            "H617A",
            "H617A",
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            True,
            3.0,
            ("scenes", "effects", "multi_layered", "reactive", "advanced"),
        ),
        "H6076": ("H617A", "H6076", True, True, True, True, True, False, False, False, False, False, None, ()),
        "H6199": (
            "H6199",
            "H6199",
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            None,
            ("video", "scenes", "effects", "reactive", "advanced"),
        ),
    }


async def test_h6179_bluetooth_discovery(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=_SERVICE_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"model": "H6179"}

    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["title"] == "Govee H6179"
    assert created["data"] == {CONF_MODEL: "H6179"}


async def test_h6179_reconfiguration_preserves_entry_identity(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Govee H617A",
        data={CONF_MODEL: "H617A"},
        options={
            CONF_EFFECT_CATEGORIES: ["scenes", "effects"],
            CONF_PREFIX_EFFECT_NAMES: True,
            CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True,
        },
        unique_id=_ADDRESS,
    )
    entry.add_to_hass(hass)
    original_entry_id = entry.entry_id

    with (
        patch(f"{_CONFIG_FLOW}.bluetooth.async_last_service_info", return_value=_SERVICE_INFO),
        patch.object(hass.config_entries, "async_schedule_reload") as reload_entry,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        updated = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MODEL: "H6179"})

    assert updated["type"] is FlowResultType.ABORT
    assert updated["reason"] == "reconfigure_successful"
    assert entry.entry_id == original_entry_id
    assert entry.unique_id == _ADDRESS
    assert entry.title == "Govee H6179"
    assert entry.data == {CONF_MODEL: "H6179"}
    assert entry.options == {}
    reload_entry.assert_called_once_with(entry.entry_id)
