"""H6179 light projection and write verification semantics."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light import ColorMode

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    encode_h6179_brightness,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.transport import xor_checksum


def _status(domain: int, body: bytes) -> bytes:
    packet = bytearray((0xAA, domain))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


@pytest.fixture
def h6179_light(hass) -> tuple[GoveeBLELight, GoveeBLECoordinator]:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )
    coordinator.profile = replace(
        coordinator.profile,
        supports_power=True,
        supports_brightness=True,
        supports_rgb=True,
        supports_color_temperature=True,
        supports_color_mode_readback=True,
    )
    light = GoveeBLELight(coordinator)
    object.__setattr__(light, "async_write_ha_state", MagicMock())
    return light, coordinator


def test_h6179_user_facing_colour_capabilities_are_enabled_by_default(hass) -> None:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )
    light = GoveeBLELight(coordinator)

    assert light.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    assert len(light.effect_list) == 86


async def test_h6179_power_mismatch_retries_until_an_accepted_field_revision(
    h6179_light: tuple[GoveeBLELight, GoveeBLECoordinator],
) -> None:
    light, coordinator = h6179_light
    replies = iter((b"\x00", b"\x01"))

    async def send(packet: bytes) -> None:
        coordinator._arm_expected(packet)

    async def refresh(**_kwargs) -> bool:
        coordinator._notify_callback(None, bytearray(_status(0x01, next(replies))))
        return True

    send_command = AsyncMock(side_effect=send)
    refresh_state = AsyncMock(side_effect=refresh)
    coordinator.is_on = False

    with (
        patch.object(coordinator, "send_command", send_command),
        patch.object(coordinator, "refresh_state", refresh_state),
    ):
        await light.async_turn_on()

    assert send_command.await_args_list[0].args[0] == build_power(True, "H6179")
    assert send_command.await_count == 2
    assert refresh_state.await_count == 2
    assert coordinator._field_revisions["is_on"] == 1
    assert coordinator.is_on is True


async def test_h6179_brightness_mismatch_retries_without_exposing_raw_brightness(
    h6179_light: tuple[GoveeBLELight, GoveeBLECoordinator],
) -> None:
    light, coordinator = h6179_light
    replies = iter((encode_h6179_brightness(100), encode_h6179_brightness(50)))

    async def send(packet: bytes) -> None:
        coordinator._arm_expected(packet)

    async def refresh(**_kwargs) -> bool:
        coordinator._notify_callback(None, bytearray(_status(0x04, bytes((next(replies),)))))
        return True

    send_command = AsyncMock(side_effect=send)
    refresh_state = AsyncMock(side_effect=refresh)
    coordinator.is_on = True

    with (
        patch.object(coordinator, "send_command", send_command),
        patch.object(coordinator, "refresh_state", refresh_state),
    ):
        await light.async_turn_on(brightness=128)

    assert send_command.await_args_list[0].args[0] == build_brightness(50, "H6179")
    assert send_command.await_count == 2
    assert coordinator._field_revisions["brightness_pct"] == 1
    assert coordinator.brightness_pct == 50
    assert light.brightness == 128
    assert not hasattr(coordinator, "raw_brightness")


@pytest.mark.parametrize(
    ("kwargs", "field", "expected"),
    [
        ({"rgb_color": (12, 34, 56)}, "rgb_color", (12, 34, 56)),
        ({"color_temp_kelvin": 4200}, "color_temp_kelvin", 4200),
    ],
)
async def test_h6179_static_write_keeps_optimistic_state_when_optional_mode_reply_is_missing(
    h6179_light: tuple[GoveeBLELight, GoveeBLECoordinator],
    kwargs: dict[str, object],
    field: str,
    expected: object,
) -> None:
    light, coordinator = h6179_light

    async def send(packet: bytes) -> None:
        coordinator._arm_expected(packet)

    send_command = AsyncMock(side_effect=send)
    refresh_status = AsyncMock(return_value=False)
    coordinator.is_on = True

    with (
        patch.object(coordinator, "send_command", send_command),
        patch.object(coordinator, "async_refresh_status_domains", refresh_status),
    ):
        await light.async_turn_on(**kwargs)

    assert send_command.await_count == 1
    assert getattr(coordinator, field) == expected
    refresh_status.assert_awaited_once_with(
        frozenset({"mode"}),
        required_domains=frozenset({"mode"}),
    )


@pytest.mark.parametrize(
    ("attributes", "expected_mode", "expected_rgb", "expected_kelvin"),
    [
        (
            {"effect": "off", "color_mode": "rgb", "rgb_color": [12, 34, 56]},
            ColorMode.RGB,
            (12, 34, 56),
            None,
        ),
        (
            {"effect": "off", "color_mode": "color_temp", "color_temp_kelvin": 4200},
            ColorMode.COLOR_TEMP,
            (255, 255, 255),
            4200,
        ),
    ],
)
async def test_h6179_restart_restores_last_static_presentation_while_off(
    h6179_light: tuple[GoveeBLELight, GoveeBLECoordinator],
    attributes: dict[str, object],
    expected_mode: ColorMode,
    expected_rgb: tuple[int, int, int],
    expected_kelvin: int | None,
) -> None:
    light, coordinator = h6179_light
    coordinator.is_on = False
    coordinator.color_mode = None

    with (
        patch.object(
            light,
            "async_get_last_state",
            AsyncMock(return_value=SimpleNamespace(attributes=attributes)),
        ),
        patch.object(light, "async_get_last_extra_data", AsyncMock(return_value=None)),
    ):
        await light._async_restore_static_color()

    assert light.color_mode is expected_mode
    assert coordinator.rgb_color == expected_rgb
    assert coordinator.color_temp_kelvin == expected_kelvin
    assert coordinator.is_on is False


async def test_existing_model_refresh_retry_behaviour_is_unchanged(
    mock_coordinator,
) -> None:
    light = GoveeBLELight(mock_coordinator)
    retry = AsyncMock()
    refresh_state = AsyncMock(side_effect=(False, True))

    with patch.object(mock_coordinator, "refresh_state", refresh_state):
        await light._refresh_with_retry(expected_on=True, retry_command=retry)

    assert refresh_state.await_count == 2
    retry.assert_awaited_once()


async def test_existing_model_static_writes_do_not_gain_readback(
    mock_coordinator,
) -> None:
    light = GoveeBLELight(mock_coordinator)
    object.__setattr__(light, "async_write_ha_state", MagicMock())
    mock_coordinator.is_on = True

    await light.async_turn_on(rgb_color=(12, 34, 56))

    mock_coordinator.refresh_state.assert_not_awaited()
