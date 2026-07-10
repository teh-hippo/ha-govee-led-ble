"""Reusable BLE-simulator test fixtures wiring a real coordinator to the sim."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.protocol import (
    COLOR_MODE_QUERY,
    COLOR_MODE_STATIC,
    COLOR_PACKET_TYPE,
    COMMAND_HEADER,
    ParsedColorModeResponse,
    build_packet,
    parse_color_mode_response,
)
from tools.ble.mock_ble.mock_device import RGB, STATIC_SUB, WHITE_SUB, FakeGoveeClient, GoveeDeviceSim

_COORDINATOR = "custom_components.ha_govee_led_ble.coordinator"
TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
MODELS = ("H617A", "H6199")


def make_ble_device(address: str = TEST_ADDRESS) -> BLEDevice:
    return BLEDevice(address, f"Govee_mock_{address}", {})


@contextmanager
def patch_transport(sim: GoveeDeviceSim, address: str = TEST_ADDRESS) -> Iterator[FakeGoveeClient]:
    client = FakeGoveeClient(sim)
    with (
        patch(f"{_COORDINATOR}.establish_connection", return_value=client),
        patch(f"{_COORDINATOR}.bluetooth.async_ble_device_from_address", return_value=make_ble_device(address)),
    ):
        yield client


def segment_color_packet(rgb: RGB, mask: int) -> bytes:
    """Build a per-segment RGB write (protocol has no builder for this yet)."""
    r, g, b = rgb
    params = [COLOR_MODE_STATIC, STATIC_SUB, r, g, b, 0, 0, 0, 0, 0, mask & 0xFF, (mask >> 8) & 0xFF]
    return build_packet(COMMAND_HEADER, COLOR_PACKET_TYPE, params)


def segment_brightness_packet(brightness: int, mask: int) -> bytes:
    """Build a per-segment brightness write with an arbitrary segment mask."""
    params = [COLOR_MODE_STATIC, WHITE_SUB, brightness, mask & 0xFF, (mask >> 8) & 0xFF]
    return build_packet(COMMAND_HEADER, COLOR_PACKET_TYPE, params)


def parse_color_reply(sim: GoveeDeviceSim) -> ParsedColorModeResponse:
    """Round-trip the sim's aa 05 reply back through the production decoder."""
    (frame,) = sim.handle_write(COLOR_MODE_QUERY)
    return parse_color_mode_response(frame[2:-1])


@dataclass
class MockBle:
    sim: GoveeDeviceSim
    coordinator: GoveeBLECoordinator
    client: FakeGoveeClient


@pytest.fixture(params=MODELS, name="mock_ble")
async def mock_ble_fixture(request, hass) -> AsyncIterator[MockBle]:
    model = request.param
    sim = GoveeDeviceSim(model)
    coordinator = GoveeBLECoordinator(hass, TEST_ADDRESS, model)
    with patch_transport(sim) as client:
        yield MockBle(sim=sim, coordinator=coordinator, client=client)
        await coordinator.disconnect()
        await coordinator.async_shutdown()


@pytest.fixture(name="mock_ble_h6199")
async def mock_ble_h6199_fixture(hass) -> AsyncIterator[MockBle]:
    sim = GoveeDeviceSim("H6199")
    coordinator = GoveeBLECoordinator(hass, TEST_ADDRESS, "H6199")
    with patch_transport(sim) as client:
        yield MockBle(sim=sim, coordinator=coordinator, client=client)
        await coordinator.disconnect()
        await coordinator.async_shutdown()
