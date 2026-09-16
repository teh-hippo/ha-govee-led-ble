"""Native cache and real crypto recovery regressions; no hardware qualification."""

import json
import traceback
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aioesphomeapi import (
    APIClient,
    APIVersion,
    BluetoothDeviceClearCache,
    BluetoothGATTCharacteristic,
    BluetoothGATTService,
    BluetoothGATTServices,
    BluetoothProxyFeature,
    DeviceInfo,
)
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection
from bleak_esphome.backend.client import ESPHomeClient, ESPHomeClientData
from bleak_esphome.backend.device import ESPHomeBluetoothDevice
from bleak_esphome.backend.scanner import ESPHomeScanner
from bleak_retry_connector import establish_connection
from bluetooth_data_tools import mac_to_int
from habluetooth import BluetoothManager
from habluetooth.central_manager import CentralBluetoothManager
from habluetooth.wrappers import HaBleakClientWrapper

from custom_components.ha_govee_led_ble.ble_connection import async_clear_gatt_cache, stale_gatt_recovery_pending
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.govee_encryption import GoveeCryptoError
from custom_components.ha_govee_led_ble.govee_encryption.session import GoveeEncryptionSession
from custom_components.ha_govee_led_ble.transport import ENCRYPTION_UUID, READ_UUID, WRITE_UUID
from tests.test_govee_encryption import M, client

ADDRESS = "AA:BB:CC:DD:EE:FF"
ADDRESS_INT = mac_to_int(ADDRESS)
SOURCE = "11:22:33:44:55:66"
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"


@pytest.fixture
async def native_proxy(monkeypatch):
    """Use native device/cache/scanner/client, substituting only the proxy API."""
    monkeypatch.setattr(CentralBluetoothManager, "manager", BluetoothManager())
    proxy = ESPHomeBluetoothDevice("test-proxy", SOURCE, ble_connections_free=1)
    services = BleakGATTServiceCollection()
    service = BleakGATTService(None, 1, SERVICE_UUID)
    services.add_service(service)
    services.add_characteristic(BleakGATTCharacteristic(None, 2, WRITE_UUID, ["write"], lambda: 20, service))
    proxy.cache.set_gatt_services_cache(ADDRESS_INT, services)
    proxy.cache.set_gatt_mtu_cache(ADDRESS_INT, 23)

    api = Mock(spec=APIClient)

    async def connect(_address, on_state, **_kwargs):
        on_state(True, 100, 0)
        return Mock()

    api.bluetooth_device_connect = AsyncMock(side_effect=connect)
    api.bluetooth_device_disconnect = AsyncMock()
    api.bluetooth_device_clear_cache = AsyncMock(return_value=BluetoothDeviceClearCache(ADDRESS_INT, True))
    api.bluetooth_gatt_get_services = AsyncMock(
        return_value=BluetoothGATTServices(
            address=ADDRESS_INT,
            services=[
                BluetoothGATTService(
                    uuid=SERVICE_UUID,
                    handle=10,
                    characteristics=[BluetoothGATTCharacteristic(uuid=WRITE_UUID, handle=20, properties=8)],
                )
            ],
        )
    )
    data = ESPHomeClientData(
        bluetooth_device=proxy,
        client=api,
        device_info=DeviceInfo(
            name="test-proxy",
            bluetooth_proxy_feature_flags=(
                BluetoothProxyFeature.ACTIVE_CONNECTIONS
                | BluetoothProxyFeature.REMOTE_CACHING
                | BluetoothProxyFeature.CACHE_CLEARING
            ),
        ),
        api_version=APIVersion(1, 10),
        title="test-proxy",
        scanner=ESPHomeScanner(SOURCE, SOURCE, connectable=True),
    )
    device = BLEDevice(ADDRESS, "Govee", {"source": SOURCE, "address_type": 0})
    return device, data, api, services


async def test_esphome_cache_bypass_requires_native_clear_before_reconnect(native_proxy):
    device, data, api, stale_services = native_proxy
    cache = data.bluetooth_device.cache
    # Exercise retry-connector's actual use_services_cache -> dangerous_use_bleak_cache mapping.
    connection = await establish_connection(
        BleakClient, device, "test", use_services_cache=False, backend=ESPHomeClient, client_data=data
    )
    try:
        api.bluetooth_device_connect.assert_awaited_once()
        assert api.bluetooth_device_connect.await_args.kwargs["has_cache"] is False
        assert connection.is_connected
        assert connection.services is stale_services
        assert connection.services.get_characteristic(WRITE_UUID).handle == 2
        assert connection.mtu_size == 23  # Even the new link's MTU=100 was ignored.
        api.bluetooth_gatt_get_services.assert_not_awaited()

        # HA's public method dispatches to the selected connected native backend.
        wrapper = object.__new__(HaBleakClientWrapper)
        wrapper._backend = connection._backend
        assert await async_clear_gatt_cache(wrapper) is True
        api.bluetooth_device_clear_cache.assert_awaited_once_with(ADDRESS_INT)
        assert cache.get_gatt_services_cache(ADDRESS_INT) is None
        assert cache.get_gatt_mtu_cache(ADDRESS_INT) is None
        # Native clearing evicts host caches, not the current connection's objects.
        assert connection.services is stale_services
        assert connection.mtu_size == 23
        api.bluetooth_device_disconnect.assert_not_awaited()
    finally:
        await connection.disconnect()

    fresh = await establish_connection(
        BleakClient, device, "test", use_services_cache=False, backend=ESPHomeClient, client_data=data
    )
    try:
        assert fresh.is_connected
        assert fresh.services is not stale_services
        assert fresh.services.get_service(SERVICE_UUID).handle == 10
        assert fresh.services.get_characteristic(WRITE_UUID).handle == 20
        assert fresh.services.get_characteristic(2) is None
        assert fresh.mtu_size == 100
        assert cache.get_gatt_services_cache(ADDRESS_INT) is fresh.services
        assert cache.get_gatt_mtu_cache(ADDRESS_INT) == 100
        api.bluetooth_gatt_get_services.assert_awaited_once_with(ADDRESS_INT)
        assert [call.kwargs["has_cache"] for call in api.bluetooth_device_connect.await_args_list] == [False, False]
    finally:
        await fresh.disconnect()


@pytest.mark.parametrize("remote_clear", ["unsupported", "rejected", "disconnected"])
async def test_esphome_native_clear_limits(native_proxy, remote_clear, caplog):
    device, data, api, stale_services = native_proxy
    if remote_clear == "unsupported":
        data.device_info = DeviceInfo(
            name="test-proxy",
            bluetooth_proxy_feature_flags=BluetoothProxyFeature.REMOTE_CACHING,
        )
    backend = ESPHomeClient(device, client_data=data)
    await backend.connect(pair=False, dangerous_use_bleak_cache=False)
    try:
        if remote_clear == "disconnected":
            await backend.disconnect()
        api.bluetooth_device_clear_cache.return_value = BluetoothDeviceClearCache(ADDRESS_INT, False, 1)
        assert await async_clear_gatt_cache(backend) is (remote_clear == "unsupported")
        assert data.bluetooth_device.cache.get_gatt_services_cache(ADDRESS_INT) is None
        assert data.bluetooth_device.cache.get_gatt_mtu_cache(ADDRESS_INT) is None
        if remote_clear == "rejected":
            api.bluetooth_device_clear_cache.assert_awaited_once_with(ADDRESS_INT)
        else:
            api.bluetooth_device_clear_cache.assert_not_awaited()
        if remote_clear == "unsupported":
            assert "Only memory cache will be cleared" in caplog.text
            assert backend.services is stale_services
    finally:
        if backend.is_connected:
            await backend.disconnect()


@pytest.mark.parametrize(
    ("phase", "expected_error"),
    [("select", "encryption_selection_failed"), ("negotiate", "negotiation_failed")],
)
@pytest.mark.parametrize("chain", ["cause", "context"])
async def test_crypto_suppressed_stale_error_reaches_coordinator_recovery(hass, caplog, phase, expected_error, chain):
    coordinator = GoveeBLECoordinator(hass, ADDRESS, "H6076", configuration_url=None)
    replacement = GoveeBLECoordinator(hass, ADDRESS.lower(), "H6076", configuration_url=None)
    device = client(b"\x01\x01")
    stale = KeyError("org.bluez.GattService1")
    private_payload = "secret address/key payload"
    backend_error = RuntimeError(private_payload)
    events = []

    async def fail(*_args, **_kwargs):
        try:
            raise stale
        except KeyError:
            if chain == "cause":
                raise backend_error from stale
            raise backend_error from None

    async def clear():
        assert device.is_connected
        assert coordinator._client is None
        assert coordinator._notification_token is None
        assert not coordinator._encryption.ready
        assert stale_gatt_recovery_pending(hass, ADDRESS.lower())
        assert replacement.fresh_services_required
        events.append("clear")
        return True

    async def disconnect():
        assert events == ["clear"]
        events.append("disconnect")
        device.is_connected = False

    device.clear_cache = AsyncMock(side_effect=clear)
    device.disconnect.side_effect = disconnect
    failing_operation = device.read_gatt_char if phase == "select" else device.write_gatt_char
    failing_operation.side_effect = fail
    with patch(f"{M}.async_establish_ble_connection", return_value=device):
        with pytest.raises(GoveeCryptoError, match=f"^{expected_error}$") as error:
            await coordinator._ensure_connected()

    # These links were produced by real async_select/async_negotiate `raise ... from None`.
    assert isinstance(coordinator._encryption, GoveeEncryptionSession)
    assert error.value.__suppress_context__
    assert error.value.__cause__ is None
    assert error.value.__context__ is backend_error
    assert getattr(backend_error, f"__{chain}__") is stale
    assert stale.args == ("org.bluez.GattService1",)
    assert private_payload not in "".join(traceback.format_exception(error.value))
    assert private_payload not in caplog.text
    assert private_payload not in json.dumps(coordinator._encryption.diagnostics())
    assert events == ["clear", "disconnect"]
    device.clear_cache.assert_awaited_once_with()
    device.disconnect.assert_awaited_once_with()
    device.read_gatt_char.assert_awaited_once_with(ENCRYPTION_UUID)
    if phase == "select":
        device.start_notify.assert_not_awaited()
        device.write_gatt_char.assert_not_awaited()
    else:
        device.start_notify.assert_awaited_once()
        assert device.start_notify.await_args.args[0] == READ_UUID
        device.write_gatt_char.assert_awaited_once()
        assert device.write_gatt_char.await_args.args[0] == WRITE_UUID
    assert coordinator._client is None and not coordinator._connection_initializing
    assert coordinator._encryption._key is None and coordinator._encryption._handshake is None
    assert coordinator.packet_log == [] and coordinator.control_write_attempts == 0
    assert coordinator.last_failure_type == "GoveeCryptoError"
    assert coordinator.fresh_services_required and replacement.fresh_services_required
