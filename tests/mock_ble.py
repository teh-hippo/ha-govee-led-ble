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
    SEGMENT_COUNT,
    ParsedColorModeResponse,
    build_segment_brightness,
    build_segment_color,
    decode_status_frame,
    parse_generated_color_mode,
)
from tools.ble.mock_ble.mock_device import RGB, FakeGoveeClient, GoveeDeviceSim

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


def _segments_from_mask(mask: int) -> list[int]:
    return [index + 1 for index in range(SEGMENT_COUNT) if mask & (1 << index)]


def segment_color_packet(rgb: RGB, mask: int) -> bytes:
    """Build a per-segment RGB write, addressed by raw mask rather than segment indices."""
    return build_segment_color(_segments_from_mask(mask), *rgb)


def segment_brightness_packet(brightness: int, mask: int) -> bytes:
    """Build a per-segment brightness write with an arbitrary segment mask."""
    return build_segment_brightness(_segments_from_mask(mask), brightness)


def parse_color_reply(sim: GoveeDeviceSim) -> ParsedColorModeResponse:
    """Round-trip the sim's aa 05 reply back through the production decoder."""
    (frame,) = sim.handle_write(COLOR_MODE_QUERY)
    decoded = decode_status_frame(frame, sim.model)
    assert decoded is not None
    return parse_generated_color_mode(decoded.generated, sim.model)


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
