from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.ha_govee_led_ble import (
    _async_cleanup_legacy_entities,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_MODEL,
    DOMAIN,
    MODEL_PROFILES,
)
from custom_components.ha_govee_led_ble.coordinator import AVAILABILITY_UNAVAILABLE_DATA_KEY
from custom_components.ha_govee_led_ble.editor import (
    EDITOR_ELEMENT_NAME,
    EDITOR_PANEL_PATH,
    EDITOR_ROUTE_SEGMENT,
    _editor_module_url,
    editor_url,
)


def _entry(**kw):
    d = dict(entry_id="test_entry_id", unique_id="AA:BB:CC:DD:EE:FF", data={CONF_MODEL: "H617A"}, options={})
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


@pytest.mark.parametrize("unload_ok,disc", [(True, "assert_awaited_once"), (False, "assert_not_awaited")])
async def test_unload_entry(hass: HomeAssistant, unload_ok, disc):
    entry = _entry(runtime_data=MagicMock(disconnect=AsyncMock()))
    with patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=unload_ok):
        assert await async_unload_entry(hass, entry) is unload_ok
    getattr(entry.runtime_data.disconnect, disc)()


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
    backend = MagicMock()
    backend.scene_defaults.async_delete_device = AsyncMock()
    backend.template_defaults.async_delete_device = AsyncMock()
    backend.active_workspaces.async_delete_device = AsyncMock()
    backend.device_cache.async_delete_device = AsyncMock()
    backend.deployments.async_delete_device = AsyncMock()
    backend.user_state.async_clear_config_entry = AsyncMock()

    with patch(
        "custom_components.ha_govee_led_ble.get_effect_backend",
        return_value=backend,
    ):
        await async_remove_entry(hass, entry)

    backend.scene_defaults.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.template_defaults.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.active_workspaces.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.device_cache.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.deployments.async_delete_device.assert_awaited_once_with(entry.entry_id)
    backend.user_state.async_clear_config_entry.assert_awaited_once_with(entry.entry_id)
    assert hass.data[DOMAIN][AVAILABILITY_UNAVAILABLE_DATA_KEY] == set()


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


async def test_async_setup_registers_effect_studio_sidebar_panel():
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
    hass.http.async_register_static_paths.assert_awaited_once()
    (static_path,) = hass.http.async_register_static_paths.await_args.args[0]
    assert static_path.url_path == f"/{DOMAIN}_static"
    assert static_path.path.endswith("custom_components/ha_govee_led_ble/frontend")
    assert static_path.cache_headers is False
    register.assert_called_once_with(
        hass,
        component_name="custom",
        sidebar_title="Govee Effect Studio",
        sidebar_icon="mdi:palette",
        sidebar_default_visible=True,
        frontend_url_path=EDITOR_PANEL_PATH,
        config={
            "configuration_path": f"/config/integrations/integration/{DOMAIN}",
            "_panel_custom": {
                "name": EDITOR_ELEMENT_NAME,
                "module_url": _editor_module_url(),
                "embed_iframe": False,
                "trust_external": False,
            },
        },
        require_admin=False,
        show_in_sidebar=True,
        update=True,
    )


def test_editor_device_url_path_matches_registered_panel():
    url = editor_url("test_entry_id")

    assert url == f"homeassistant://{EDITOR_PANEL_PATH}/{EDITOR_ROUTE_SEGMENT}/test_entry_id"
