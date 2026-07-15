from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.scenes import get_scene_names
from custom_components.ha_govee_led_ble.sensor import GoveeActiveModeSensor, async_setup_entry


@pytest.fixture
def h617a(hass):
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199")


def test_native_value_off(h617a):
    h617a.is_on = False
    assert GoveeActiveModeSensor(h617a).native_value == "off"


def test_native_value_colour(h617a):
    h617a.is_on, h617a.effect, h617a.music_mode, h617a.video_mode = True, None, "off", "off"
    assert GoveeActiveModeSensor(h617a).native_value == "colour"


def test_native_value_scene(h617a):
    h617a.is_on, h617a.effect = True, get_scene_names()[0]
    assert GoveeActiveModeSensor(h617a).native_value == "scene"


def test_native_value_music(h617a):
    h617a.is_on, h617a.effect, h617a.music_mode = True, None, "rhythm"
    assert GoveeActiveModeSensor(h617a).native_value == "music"


def test_native_value_video(h6199):
    h6199.is_on, h6199.effect, h6199.music_mode, h6199.video_mode = True, None, "off", "movie"
    assert GoveeActiveModeSensor(h6199).native_value == "video"


def test_native_value_custom_from_sticky_id(h617a):
    h617a.is_on, h617a.effect, h617a.active_custom_id = True, get_scene_names()[0], "flame"
    assert GoveeActiveModeSensor(h617a).native_value == "custom"


def test_native_value_custom_from_diy_slot(h617a):
    h617a.is_on, h617a.diy_slot = True, 0xEF
    assert GoveeActiveModeSensor(h617a).native_value == "custom"


def test_scene_name_set_h617a_uses_catalogue(h617a):
    assert h617a.scene_name_set == frozenset(get_scene_names())
    assert h617a.scene_name_set


def test_scene_name_set_h6199_is_empty(h6199):
    assert h6199.scene_name_set == frozenset()


def test_h6199_effect_never_reads_as_scene(h6199):
    h6199.is_on, h6199.effect, h6199.music_mode, h6199.video_mode = True, get_scene_names()[0], "off", "off"
    assert GoveeActiveModeSensor(h6199).native_value == "colour"


def test_enum_options_and_category(h617a):
    sensor = GoveeActiveModeSensor(h617a)
    assert sensor.options == ["off", "colour", "scene", "music", "video", "custom"]
    assert sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.translation_key == "active_mode"


def test_unique_id_scheme(h617a):
    assert GoveeActiveModeSensor(h617a).unique_id == "aabbccddeeff_active_mode"


async def test_setup_adds_single_sensor(h6199):
    add = MagicMock()
    await async_setup_entry(MagicMock(), MagicMock(runtime_data=h6199), add)
    entities = add.call_args.args[0]
    assert len(entities) == 1 and isinstance(entities[0], GoveeActiveModeSensor)


def test_entity_available_tracks_coordinator_presence(h617a):
    sensor = GoveeActiveModeSensor(h617a)
    h617a._client, h617a._present = None, False
    assert sensor.available is False
    h617a._present = True
    assert sensor.available is True
    h617a.last_update_success = False
    assert sensor.available is False
