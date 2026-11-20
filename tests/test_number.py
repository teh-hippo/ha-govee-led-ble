"""Shared native number validation and device dispatch."""

from types import SimpleNamespace
from unittest.mock import call

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.number import GoveeBLELowBlueLightLevel, GoveeBLERippleSpeed


@pytest.mark.parametrize(
    ("entity_type", "method", "suffix"),
    [
        (GoveeBLELowBlueLightLevel, "async_set_low_blue_light", "low_blue_light_level"),
        (GoveeBLERippleSpeed, "async_set_source_value", "ripple_speed"),
    ],
)
async def test_native_level_validation_and_dispatch(mock_coordinator, entity_type, method, suffix, caplog):
    entity = entity_type(SimpleNamespace(runtime_data=mock_coordinator))
    writer = getattr(mock_coordinator, method)
    assert entity.unique_id == f"aabbccddeeff_{suffix}"
    for value in (entity.native_min_value, entity.native_max_value):
        await entity.async_set_native_value(value)
        expected = (
            call(level=int(value)) if suffix == "low_blue_light_level" else call("top", "ripple_speed", int(value))
        )
        assert writer.await_args == expected
    writer.reset_mock()
    for value in (entity.native_min_value - 1, entity.native_max_value + 1, entity.native_min_value + 0.5):
        with pytest.raises(ServiceValidationError):
            await entity.async_set_native_value(value)
    writer.assert_not_awaited()
    for error in (BleakError, ValueError, TimeoutError):
        caplog.clear()
        writer.side_effect = error("device failure")
        with pytest.raises(HomeAssistantError) as caught:
            await entity.async_set_native_value(entity.native_min_value)
        assert caught.value.translation_key == "device_command_failed"
        expected = f"operation={entity_type.__name__} model={mock_coordinator.model} failure={error.__name__}"
        assert expected in caplog.text
        assert "device failure" not in caplog.text and mock_coordinator.address not in caplog.text
