"""Config-entry migrations and replacement repair issues."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble import (
    _restore_relative_brightness_enablement,
    async_migrate_entry,
)
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN

_ADDR = "AA:BB:CC:DD:EE:FF"
_BASE = "aabbccddeeff"


def _v1_entry(hass: HomeAssistant, **kw) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=1, data={CONF_MODEL: "H617A"}, **kw)
    entry.add_to_hass(hass)
    return entry


async def test_migrate_bumps_version_and_strips_experimental(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": {"timers": True}, "keep_me": 1})

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 4
    assert dict(entry.options) == {"keep_me": 1}


async def test_clean_install_migrates(hass: HomeAssistant):
    entry = _v1_entry(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 4


async def test_migrate_strips_experimental_without_music_calm(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": {"diy": True}})

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 4
    assert dict(entry.options) == {}


async def test_migrate_current_entry_bumps_to_v4(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, data={CONF_MODEL: "H617A"})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 4


async def test_migrate_recovers_model_from_legacy_title(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, title="Govee H6199", data={})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 4
    assert entry.data == {CONF_MODEL: "H6199"}


async def test_v4_migration_preserves_enabled_relative_brightness_entities(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=3, data={CONF_MODEL: "H6199"})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    enabled = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{_BASE}_relative_brightness_right",
        config_entry=entry,
    )

    assert await async_migrate_entry(hass, entry) is True
    registry.async_update_entity(enabled.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    _restore_relative_brightness_enablement(hass, entry)

    assert entry.version == 4
    restored = registry.async_get(enabled.entity_id)
    assert restored is not None and restored.disabled_by is None
