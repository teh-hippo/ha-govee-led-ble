"""Config-entry migrations and replacement repair issues."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble import async_migrate_entry
from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_CATEGORIES,
    CONF_MODEL,
    CONF_PREFIX_EFFECT_NAMES,
    DOMAIN,
)

_ADDR = "AA:BB:CC:DD:EE:FF"


def _v1_entry(hass: HomeAssistant, **kw) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=1, data={CONF_MODEL: "H617A"}, **kw)
    entry.add_to_hass(hass)
    return entry


async def test_migrate_bumps_version_and_strips_experimental(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": {"timers": True}, "keep_me": 1})

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert dict(entry.options) == {
        "keep_me": 1,
        CONF_EFFECT_CATEGORIES: ["scenes", "effects", "multi_layered", "reactive", "advanced"],
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }


async def test_clean_install_migrates(hass: HomeAssistant):
    entry = _v1_entry(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert entry.options == {
        CONF_EFFECT_CATEGORIES: ["scenes", "effects", "multi_layered", "reactive", "advanced"],
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }


async def test_migrate_current_entry_bumps_to_v8(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, data={CONF_MODEL: "H617A"})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert entry.options[CONF_PREFIX_EFFECT_NAMES] is False
    assert entry.options[CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS] is False


async def test_migrate_preserves_existing_prefix_preference(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=_ADDR,
        version=6,
        data={CONF_MODEL: "H617A"},
        options={
            CONF_PREFIX_EFFECT_NAMES: True,
            CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True,
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert entry.options[CONF_PREFIX_EFFECT_NAMES] is True
    assert entry.options[CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS] is True


async def test_migrate_v7_preserves_options_and_defaults_custom_visibility(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=_ADDR,
        version=7,
        data={CONF_MODEL: "H617A"},
        options={
            CONF_EFFECT_CATEGORIES: [],
            CONF_PREFIX_EFFECT_NAMES: True,
            "keep_me": 1,
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert entry.options == {
        CONF_EFFECT_CATEGORIES: [],
        CONF_PREFIX_EFFECT_NAMES: True,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
        "keep_me": 1,
    }


async def test_migrate_recovers_model_from_legacy_title(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, title="Govee H6199", data={})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 8
    assert entry.data == {CONF_MODEL: "H6199"}
    assert entry.options == {
        CONF_EFFECT_CATEGORIES: ["video", "scenes", "effects", "reactive", "advanced"],
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }
