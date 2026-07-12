"""3.0.0 config-entry migration: version bump, option strip, and the music_calm repair issue."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble import (
    _maybe_flag_music_calm_replaced,
    async_migrate_entry,
)
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN

_ADDR = "AA:BB:CC:DD:EE:FF"
_BASE = "aabbccddeeff"


def _v1_entry(hass: HomeAssistant, **kw) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=1, data={CONF_MODEL: "H617A"}, **kw)
    entry.add_to_hass(hass)
    return entry


def _stash_key(entry: MockConfigEntry) -> str:
    return f"{entry.entry_id}_music_calm_from"


async def test_migrate_bumps_version_strips_experimental_and_stashes_music_calm(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": {"timers": True}, "keep_me": 1})
    old = er.async_get(hass).async_get_or_create("switch", DOMAIN, f"{_BASE}_music_calm", config_entry=entry)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert dict(entry.options) == {"keep_me": 1}
    assert hass.data[DOMAIN][_stash_key(entry)] == old.entity_id


async def test_migrate_and_setup_emit_music_calm_replaced_with_both_ids(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": True})
    reg = er.async_get(hass)
    old = reg.async_get_or_create("switch", DOMAIN, f"{_BASE}_music_calm", config_entry=entry)

    await async_migrate_entry(hass, entry)
    # Platform setup registers the replacement select before the post-setup flag runs.
    new = reg.async_get_or_create("select", DOMAIN, f"{_BASE}_music_style", config_entry=entry)
    _maybe_flag_music_calm_replaced(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, "music_calm_replaced")
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_placeholders == {"old": old.entity_id, "new": new.entity_id}
    assert _stash_key(entry) not in hass.data.get(DOMAIN, {})


async def test_music_calm_replaced_falls_back_when_select_missing(hass: HomeAssistant):
    entry = _v1_entry(hass)
    old = er.async_get(hass).async_get_or_create("switch", DOMAIN, f"{_BASE}_music_calm", config_entry=entry)

    await async_migrate_entry(hass, entry)
    _maybe_flag_music_calm_replaced(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, "music_calm_replaced")
    assert issue is not None
    assert issue.translation_placeholders == {"old": old.entity_id, "new": "select.music_style"}


async def test_clean_install_migrates_without_issue(hass: HomeAssistant):
    entry = _v1_entry(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert _stash_key(entry) not in hass.data.get(DOMAIN, {})

    _maybe_flag_music_calm_replaced(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "music_calm_replaced") is None


async def test_migrate_strips_experimental_without_music_calm(hass: HomeAssistant):
    entry = _v1_entry(hass, options={"experimental": {"diy": True}})

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert dict(entry.options) == {}
    assert _stash_key(entry) not in hass.data.get(DOMAIN, {})

    _maybe_flag_music_calm_replaced(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "music_calm_replaced") is None


async def test_migrate_current_entry_bumps_to_v3(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, data={CONF_MODEL: "H617A"})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert _stash_key(entry) not in hass.data.get(DOMAIN, {})


async def test_migrate_recovers_model_from_legacy_title(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=_ADDR, version=2, title="Govee H6199", data={})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 3
    assert entry.data == {CONF_MODEL: "H6199"}
