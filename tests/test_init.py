from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir

from custom_components.ha_govee_led_ble import (
    _async_cleanup_legacy_entities,
    _effect_studio_sidebar_visible,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_MODEL,
    CONF_PACT_CODE,
    CONF_PACT_TYPE,
    DOMAIN,
    MODEL_PROFILES,
)
from custom_components.ha_govee_led_ble.coordinator import AVAILABILITY_UNAVAILABLE_DATA_KEY
from custom_components.ha_govee_led_ble.editor import (
    EDITOR_PANEL_PATH,
    EDITOR_ROUTE_SEGMENT,
    editor_url,
)


@pytest.fixture(autouse=True)
def mock_last_service_info():
    with patch("custom_components.ha_govee_led_ble.bluetooth.async_last_service_info", return_value=None):
        yield


def _entry(**kw):
    d = dict(
        entry_id="test_entry_id",
        unique_id="AA:BB:CC:DD:EE:FF",
        data={CONF_MODEL: "H617A"},
        options={},
        disabled_by=None,
    )
    return MagicMock(**({**d, "domain": DOMAIN, "state": ConfigEntryState.LOADED, "runtime_data": None} | kw))


async def test_setup_entry(hass: HomeAssistant):
    entry = _entry(options={CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True})
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch(
            "custom_components.ha_govee_led_ble.editor_url",
            return_value="homeassistant://ha-govee-led-ble/editor/test_entry_id",
        ) as build_url,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock) as cleanup,
        patch("custom_components.ha_govee_led_ble._async_update_editor_panel", new_callable=AsyncMock) as update_panel,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        cls.return_value.profile = MODEL_PROFILES["H617A"]
        assert await async_setup_entry(hass, entry) is True
    cls.assert_called_once_with(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H617A",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test_entry_id",
        effect_families=frozenset({"scenes", "music"}),
        effect_categories=frozenset(
            {"scenes", "effects", "multi_layered", "reactive", "advanced"},
        ),
        prefix_effect_names=False,
        always_include_custom_effects=True,
    )
    build_url.assert_called_once_with(entry.entry_id)
    assert entry.runtime_data is cls.return_value
    cleanup.assert_awaited_once_with(hass, entry)
    fwd.assert_awaited_once()
    update_panel.assert_awaited_once_with(hass)


async def test_setup_entry_omits_editor_link_for_h6076(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6076"})
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        cls.return_value.profile = MODEL_PROFILES["H6076"]

        assert await async_setup_entry(hass, entry) is True

    assert cls.call_args.kwargs["configuration_url"] is None


async def test_setup_entry_accepts_supported_h6125_identity(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125", CONF_PACT_TYPE: 10, CONF_PACT_CODE: 1})
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=True)
        coordinator.refresh_state = AsyncMock(return_value=True)
        coordinator.profile = MODEL_PROFILES["H6125"]
        coordinator.supports_brightness = True
        coordinator.fw_version = "1.06.00"
        coordinator.hw_version = "1.00.03"

        assert await async_setup_entry(hass, entry) is True

    coordinator.async_refresh_identity.assert_awaited_once_with()
    coordinator.refresh_state.assert_awaited_once_with(refresh_brightness=True)
    cls.assert_called_once_with(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H6125",
        configuration_url=None,
        effect_families=frozenset(),
        effect_categories=frozenset(),
        prefix_effect_names=False,
        always_include_custom_effects=False,
        pact_type=10,
        pact_code=1,
    )
    assert entry.runtime_data is coordinator
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_version_{entry.entry_id}") is None
    fwd.assert_awaited_once()


async def test_setup_entry_accepts_captured_older_h6125_firmware(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=True)
        coordinator.refresh_state = AsyncMock(return_value=True)
        coordinator.disconnect = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]
        coordinator.supports_brightness = True
        coordinator.fw_version = "1.00.11"
        coordinator.hw_version = "1.00.01"

        assert await async_setup_entry(hass, entry) is True

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_version_{entry.entry_id}") is None
    coordinator.refresh_state.assert_awaited_once_with(refresh_brightness=True)


async def test_setup_entry_rejects_unrecognised_h6125_hardware_family(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=True)
        coordinator.refresh_state = AsyncMock(return_value=True)
        coordinator.disconnect = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]
        coordinator.fw_version = "1.06.00"
        coordinator.hw_version = "4.00.00"

        assert await async_setup_entry(hass, entry) is False

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_version_{entry.entry_id}")
    assert issue is not None
    coordinator.disconnect.assert_awaited_once_with()


async def test_setup_entry_retries_when_h6125_identity_is_unavailable(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=False)
        coordinator.refresh_state = AsyncMock()
        coordinator.disconnect = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]

        with pytest.raises(ConfigEntryNotReady, match="did not report firmware"):
            await async_setup_entry(hass, entry)

    coordinator.disconnect.assert_awaited_once_with()


async def test_setup_entry_retries_when_h6125_identity_connection_fails(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(side_effect=BleakError("down"))
        coordinator.disconnect = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]

        with pytest.raises(ConfigEntryNotReady, match="identity query could not connect"):
            await async_setup_entry(hass, entry)

    coordinator.disconnect.assert_awaited_once_with()


async def test_setup_entry_retries_when_h6125_brightness_connection_fails(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=True)
        coordinator.refresh_state = AsyncMock(side_effect=BleakError("down"))
        coordinator.disconnect = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]
        coordinator.supports_brightness = True
        coordinator.fw_version = "1.06.00"
        coordinator.hw_version = "1.00.03"

        with pytest.raises(ConfigEntryNotReady, match="brightness query could not connect"):
            await async_setup_entry(hass, entry)

    coordinator.disconnect.assert_awaited_once_with()


async def test_setup_entry_skips_brightness_for_non_telink_h6125(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H6125"})
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        coordinator = cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_refresh_identity = AsyncMock(return_value=True)
        coordinator.refresh_state = AsyncMock()
        coordinator.profile = MODEL_PROFILES["H6125"]
        coordinator.supports_brightness = False
        coordinator.fw_version = "2.06.15"
        coordinator.hw_version = "2.01.00"

        assert await async_setup_entry(hass, entry) is True

    coordinator.refresh_state.assert_not_awaited()


async def test_setup_entry_reconciles_loaded_coordinator_with_effect_cache(hass: HomeAssistant):
    entry = _entry()
    backend = MagicMock(
        engine=MagicMock(),
        preview=MagicMock(async_load_device=AsyncMock()),
    )
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble.get_effect_backend", return_value=backend),
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        cls.return_value.profile = MODEL_PROFILES["H617A"]

        assert await async_setup_entry(hass, entry) is True

    backend.engine.reconcile_current.assert_called_once()
    backend.preview.async_load_device.assert_awaited_once_with(entry.entry_id)
    assert backend.engine.reconcile_current.call_args.args == (cls.return_value,)
    assert backend.engine.reconcile_current.call_args.kwargs["config_entry_id"] == entry.entry_id
    assert backend.engine.reconcile_current.call_args.kwargs["refreshed"] is True


@pytest.mark.parametrize("data", [{}, {CONF_MODEL: "H9999"}])
async def test_setup_entry_rejects_unknown_model(hass: HomeAssistant, data):
    entry = _entry(data=data)
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        assert await async_setup_entry(hass, entry) is False
    cls.assert_not_called()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_model_{entry.entry_id}")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR


async def test_setup_entry_rejects_known_advertised_model_mismatch(hass: HomeAssistant):
    entry = _entry(data={CONF_MODEL: "H617A"})
    service_info = MagicMock()
    service_info.name = "Govee_H617E_ABCD"
    with (
        patch("custom_components.ha_govee_led_ble.bluetooth.async_last_service_info", return_value=service_info),
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
    ):
        assert await async_setup_entry(hass, entry) is False
    cls.assert_not_called()


@pytest.mark.parametrize("unload_ok,disc", [(True, "assert_awaited_once"), (False, "assert_not_awaited")])
async def test_unload_entry(hass: HomeAssistant, unload_ok, disc):
    entry = _entry(runtime_data=MagicMock(disconnect=AsyncMock()))
    with (
        patch("custom_components.ha_govee_led_ble._async_update_editor_panel", new_callable=AsyncMock) as update_panel,
        patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=unload_ok),
    ):
        assert await async_unload_entry(hass, entry) is unload_ok
    getattr(entry.runtime_data.disconnect, disc)()
    if unload_ok:
        update_panel.assert_awaited_once_with(hass)
    else:
        update_panel.assert_not_awaited()


async def test_unload_entry_stops_preview_before_platforms_and_disconnect(hass: HomeAssistant):
    order = []
    preview = MagicMock()
    preview.async_unload_device = AsyncMock(side_effect=lambda _entry_id: order.append("preview"))
    preview.async_load_device = AsyncMock()
    entry = _entry(runtime_data=MagicMock())
    entry.runtime_data.disconnect = AsyncMock(side_effect=lambda: order.append("disconnect"))

    async def unload_platforms(_entry, _platforms):
        order.append("platforms")
        return True

    with (
        patch(
            "custom_components.ha_govee_led_ble.get_effect_backend",
            return_value=MagicMock(preview=preview),
        ),
        patch.object(hass.config_entries, "async_unload_platforms", side_effect=unload_platforms),
    ):
        assert await async_unload_entry(hass, entry) is True

    assert order == ["preview", "platforms", "disconnect"]


async def test_remove_entry_purges_all_device_scoped_effect_state(hass: HomeAssistant):
    entry = _entry()
    hass.data.setdefault(DOMAIN, {})[AVAILABILITY_UNAVAILABLE_DATA_KEY] = {entry.unique_id}
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"unsupported_model_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="unsupported_model",
        translation_placeholders={"model": "H6125"},
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"unsupported_version_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="unsupported_version",
        translation_placeholders={
            "model": "H6125",
            "firmware": "1.00.00",
            "hardware": "1.00.00",
        },
    )
    backend = MagicMock()
    backend.scene_defaults.async_delete_device = AsyncMock()
    backend.template_defaults.async_delete_device = AsyncMock()
    backend.active_workspaces.async_delete_device = AsyncMock()
    backend.device_cache.async_delete_device = AsyncMock()
    backend.deployments.async_delete_device = AsyncMock()
    backend.user_state.async_clear_config_entry = AsyncMock()

    with (
        patch(
            "custom_components.ha_govee_led_ble.get_effect_backend",
            return_value=backend,
        ),
        patch("custom_components.ha_govee_led_ble._async_update_editor_panel", new_callable=AsyncMock) as update_panel,
    ):
        await async_remove_entry(hass, entry)

    backend.scene_defaults.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.template_defaults.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.active_workspaces.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.device_cache.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.deployments.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.user_state.async_clear_config_entry.assert_awaited_once_with(entry.entry_id)
    assert hass.data[DOMAIN][AVAILABILITY_UNAVAILABLE_DATA_KEY] == set()
    update_panel.assert_awaited_once_with(hass, excluding_entry_id=entry.entry_id)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"unsupported_model_{entry.entry_id}") is None
    assert registry.async_get_issue(DOMAIN, f"unsupported_version_{entry.entry_id}") is None


@pytest.mark.parametrize(
    ("models", "disabled", "visible"),
    [
        ([], set(), False),
        (["H6076"], set(), False),
        (["H617A"], set(), True),
        (["H6076", "H6199"], set(), True),
        (["H617A"], {0}, False),
    ],
)
def test_effect_studio_sidebar_visibility_uses_enabled_configured_capabilities(
    models,
    disabled,
    visible,
):
    hass = MagicMock()
    entries = [
        _entry(
            entry_id=f"entry-{index}",
            data={CONF_MODEL: model},
            disabled_by=ConfigEntryDisabler.USER if index in disabled else None,
        )
        for index, model in enumerate(models)
    ]
    hass.config_entries.async_entries.return_value = entries

    assert _effect_studio_sidebar_visible(hass) is visible


async def test_cleanup_legacy_entities(hass: HomeAssistant):
    entry = _entry()
    registry = MagicMock()
    stale = MagicMock(unique_id="112233445566_video_brightness", entity_id="number.govee_video_brightness")
    stale2 = MagicMock(unique_id="112233445566_white_brightness", entity_id="number.govee_white_brightness")
    stale4 = MagicMock(unique_id="112233445566_music_calm", entity_id="switch.govee_music_calm")
    removed_surface = [
        MagicMock(unique_id="112233445566_effect_preview", entity_id="image.govee_effect_preview"),
        MagicMock(unique_id="112233445566_reduce_motion", entity_id="switch.govee_reduce_motion"),
        MagicMock(unique_id="112233445566_scene_speed", entity_id="number.govee_scene_speed"),
        MagicMock(unique_id="112233445566_white_balance_red", entity_id="number.govee_white_balance_red"),
        MagicMock(unique_id="112233445566_white_balance_blue", entity_id="number.govee_white_balance_blue"),
        MagicMock(unique_id="112233445566_white_balance_preset", entity_id="select.govee_white_balance"),
        MagicMock(unique_id="112233445566_video_saturation", entity_id="number.govee_video_saturation"),
        MagicMock(unique_id="112233445566_video_sound_effects", entity_id="switch.govee_video_sound_effects"),
        MagicMock(
            unique_id="112233445566_video_sound_effects_softness",
            entity_id="number.govee_video_sound_effects_softness",
        ),
        MagicMock(unique_id="112233445566_video_capture_region", entity_id="select.govee_video_capture_region"),
        MagicMock(unique_id="112233445566_white_balance", entity_id="number.govee_white_balance"),
        MagicMock(unique_id="112233445566_blank_screen", entity_id="switch.govee_blank_screen"),
        MagicMock(unique_id="112233445566_relative_brightness", entity_id="number.govee_relative_brightness"),
        MagicMock(
            unique_id="112233445566_relative_brightness_left",
            entity_id="number.govee_relative_brightness_left",
        ),
        MagicMock(
            unique_id="112233445566_relative_brightness_top",
            entity_id="number.govee_relative_brightness_top",
        ),
        MagicMock(
            unique_id="112233445566_relative_brightness_right",
            entity_id="number.govee_relative_brightness_right",
        ),
        MagicMock(
            unique_id="112233445566_relative_brightness_bottom",
            entity_id="number.govee_relative_brightness_bottom",
        ),
    ]
    retired = MagicMock(unique_id="112233445566_music_sensitivity", entity_id="number.govee_music_sensitivity")
    with (
        patch("custom_components.ha_govee_led_ble.er.async_get", return_value=registry),
        patch(
            "custom_components.ha_govee_led_ble.er.async_entries_for_config_entry",
            return_value=[stale, stale2, stale4, *removed_surface, retired],
        ),
    ):
        await _async_cleanup_legacy_entities(hass, entry)
    registry.async_remove.assert_has_calls(
        [
            call("number.govee_video_brightness"),
            call("number.govee_white_brightness"),
            call("switch.govee_music_calm"),
            *[call(entity.entity_id) for entity in removed_surface],
            call(retired.entity_id),
        ]
    )
    assert registry.async_remove.call_count == 4 + len(removed_surface)


async def test_async_setup_skips_effect_studio_without_capable_device():
    hass = MagicMock()
    hass.data = {}
    hass.async_add_executor_job = AsyncMock()
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch("custom_components.ha_govee_led_ble.editor.frontend.async_register_built_in_panel") as register,
        patch("custom_components.ha_govee_led_ble.async_register_light_services") as register_services,
        patch(
            "custom_components.ha_govee_led_ble.async_setup_effects",
            new_callable=AsyncMock,
        ) as setup_effects,
    ):
        assert await async_setup(hass, {}) is True

    register_services.assert_called_once_with(hass)
    setup_effects.assert_awaited_once_with(hass)
    hass.http.async_register_static_paths.assert_not_awaited()
    register.assert_not_called()


def test_editor_device_url_path_matches_registered_panel():
    url = editor_url("test_entry_id")

    assert url == f"homeassistant://{EDITOR_PANEL_PATH}/{EDITOR_ROUTE_SEGMENT}/test_entry_id"
