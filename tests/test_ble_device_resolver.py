import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDBusError

from custom_components.ha_govee_led_ble.ble_connection import (
    async_clear_gatt_cache,
    async_establish_ble_connection,
    async_validate_ble_connection,
    clear_stale_gatt_recovery,
    is_stale_gatt_error,
    mark_stale_gatt_recovery,
    stale_gatt_recovery_pending,
)
from custom_components.ha_govee_led_ble.ble_device_resolver import (
    BLEDeviceResolution,
    BLEDeviceResolver,
)
from custom_components.ha_govee_led_ble.const import DOMAIN

M = "custom_components.ha_govee_led_ble.ble_device_resolver"
CONNECTION_M = "custom_components.ha_govee_led_ble.ble_connection"
ADDRESS = "AA:BB:CC:DD:EE:FF"


def _device() -> BLEDevice:
    return BLEDevice(ADDRESS, "Govee_H617A_EEFF", {})


def _resolution() -> BLEDeviceResolution:
    return BLEDeviceResolution(_device(), type("WrappedClient", (), {}))


async def test_production_cache_uses_wrapped_client(hass):
    device = _device()
    resolver = BLEDeviceResolver()
    wrapped_client = type("WrappedClient", (), {})

    with (
        patch(f"{M}.bluetooth.async_ble_device_from_address", return_value=device) as cache,
        patch(f"{M}.bleak.BleakClient", wrapped_client),
    ):
        resolution = await resolver.async_resolve(hass, ADDRESS)

    assert resolution == BLEDeviceResolution(device, wrapped_client)
    cache.assert_called_once_with(hass, ADDRESS, connectable=True)


async def test_cache_miss_returns_none(hass):
    resolver = BLEDeviceResolver()

    with patch(f"{M}.bluetooth.async_ble_device_from_address", return_value=None):
        assert await resolver.async_resolve(hass, ADDRESS) is None


async def test_connection_establishment_reuses_resolution_retry_contract(hass):
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolution = _resolution()
    resolver.async_resolve = AsyncMock(side_effect=[None, resolution])
    client = MagicMock()
    establish = AsyncMock(return_value=client)
    sleep = AsyncMock()

    assert (
        await async_establish_ble_connection(
            hass,
            ADDRESS,
            resolver=resolver,
            establish=establish,
            sleep=sleep,
        )
        is client
    )

    assert resolver.async_resolve.await_count == 2
    sleep.assert_awaited_once_with(2)
    establish.assert_awaited_once_with(
        resolution.client_class,
        resolution.device,
        ADDRESS,
        use_services_cache=True,
    )


async def test_connection_establishment_passes_disconnected_callback(hass):
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolution = _resolution()
    resolver.async_resolve = AsyncMock(return_value=resolution)
    establish = AsyncMock(return_value=MagicMock())
    disconnected_callback = MagicMock()

    await async_establish_ble_connection(
        hass,
        ADDRESS,
        resolver=resolver,
        establish=establish,
        disconnected_callback=disconnected_callback,
    )

    establish.assert_awaited_once_with(
        resolution.client_class,
        resolution.device,
        ADDRESS,
        disconnected_callback=disconnected_callback,
        use_services_cache=True,
    )


async def test_connection_establishment_can_bypass_service_cache(hass):
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolution = _resolution()
    resolver.async_resolve = AsyncMock(return_value=resolution)
    establish = AsyncMock(return_value=MagicMock())

    await async_establish_ble_connection(
        hass,
        ADDRESS,
        resolver=resolver,
        establish=establish,
        use_services_cache=False,
    )

    establish.assert_awaited_once_with(
        resolution.client_class,
        resolution.device,
        ADDRESS,
        use_services_cache=False,
    )


@pytest.mark.parametrize(
    "error",
    [
        BleakError("Characteristic 0000 not found"),
        BleakError("GATT service is not available"),
        BleakError("invalid handle for attribute write"),
        KeyError("org.bluez.GattService1"),
        BleakDBusError(
            "org.freedesktop.DBus.Error.UnknownObject", ["Unknown object /org/bluez/hci0/dev_AA/service001"]
        ),
        BleakDBusError("org.bluez.Error.DoesNotExist", ["GATT characteristic disappeared"]),
    ],
)
def test_stale_gatt_error_detection(error):
    assert is_stale_gatt_error(error)


@pytest.mark.parametrize(
    "error",
    [
        BleakError("Device AA:BB:CC:DD:EE:FF not found"),
        BleakError("connection timed out"),
        BleakError("already shutdown"),
        BleakError("org.freedesktop.DBus.Error.UnknownObject"),
        BleakDBusError("org.bluez.Error.DoesNotExist", ["Device does not exist"]),
        BleakDBusError("org.freedesktop.DBus.Error.UnknownObject", ["Unknown object /org/bluez/hci0/dev_AA"]),
        KeyError("org.bluez.Device1"),
        KeyError("org.bluez.GattCharacteristic1"),
        KeyError("org.bluez.GattService1", "unrelated"),
        RuntimeError("org.bluez.GattService1"),
    ],
)
def test_stale_gatt_error_detection_rejects_connection_failures(error):
    assert not is_stale_gatt_error(error)


def test_stale_gatt_error_detection_follows_both_links_and_cycles():
    error = BleakError("connection failed")
    error.__cause__ = RuntimeError("unrelated")
    error.__cause__.__context__ = error
    error.__context__ = KeyError("org.bluez.GattService1")
    error.__context__.__cause__ = error
    assert is_stale_gatt_error(error)
    error.__context__ = error
    assert not is_stale_gatt_error(error)


def test_pending_recovery_is_case_normalized_and_isolated(hass):
    other_address = "11:22:33:44:55:66"
    other_hass = SimpleNamespace(data={})
    hass.data.setdefault(DOMAIN, {})["other_state"] = "kept"
    clear_stale_gatt_recovery(other_hass, ADDRESS)
    assert other_hass.data == {}
    assert not stale_gatt_recovery_pending(hass, ADDRESS)
    mark_stale_gatt_recovery(hass, ADDRESS.lower())
    mark_stale_gatt_recovery(hass, ADDRESS)
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert not stale_gatt_recovery_pending(hass, other_address)
    assert not stale_gatt_recovery_pending(other_hass, ADDRESS)
    mark_stale_gatt_recovery(hass, other_address)
    clear_stale_gatt_recovery(hass, ADDRESS.lower())
    assert not stale_gatt_recovery_pending(hass, ADDRESS)
    assert stale_gatt_recovery_pending(hass, other_address)
    assert hass.data[DOMAIN]["other_state"] == "kept"


@pytest.mark.parametrize("result", [True, False])
async def test_native_cache_clear_returns_public_api_result(result):
    client = MagicMock(clear_cache=AsyncMock(return_value=result))
    assert await async_clear_gatt_cache(client) is result
    client.clear_cache.assert_awaited_once_with()


@pytest.mark.parametrize("error", [BleakError(ADDRESS), RuntimeError(ADDRESS), AttributeError(ADDRESS)])
async def test_native_cache_clear_failure_is_safe(error, caplog):
    client = MagicMock(clear_cache=AsyncMock(side_effect=error))
    assert not await async_clear_gatt_cache(client)
    assert ADDRESS not in caplog.text


async def test_native_cache_clear_without_public_api_fails():
    assert not await async_clear_gatt_cache(SimpleNamespace())


async def _never_finishes(*_args, **_kwargs):
    await asyncio.Event().wait()


async def test_native_cache_clear_is_bounded():
    client = MagicMock(clear_cache=AsyncMock(side_effect=_never_finishes))
    with patch(f"{CONNECTION_M}.GATT_CACHE_CLEAR_TIMEOUT", 0.001):
        async with asyncio.timeout(1):
            assert not await async_clear_gatt_cache(client)


async def test_native_cache_clear_propagates_cancellation():
    client = MagicMock(clear_cache=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await async_clear_gatt_cache(client)


async def test_other_address_pending_does_not_force_recovery(hass):
    mark_stale_gatt_recovery(hass, "11:22:33:44:55:66")
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    client = MagicMock()
    establish = AsyncMock(return_value=client)
    assert await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish) is client
    assert establish.await_count == 1
    assert establish.call_args.kwargs == {"use_services_cache": True}
    client.clear_cache.assert_not_called()


@pytest.mark.parametrize("sources", [("proxy_a", "proxy_a"), ("proxy_a", "proxy_b")])
async def test_recovery_bootstraps_clears_disconnects_then_qualifies(hass, sources):
    mark_stale_gatt_recovery(hass, ADDRESS)
    resolutions = [_resolution(), _resolution()]
    for resolution, source in zip(resolutions, sources, strict=True):
        resolution.device.details["source"] = source
    events = []
    bootstrap = SimpleNamespace()

    async def clear_cache():
        events.append("clear")
        return True

    async def disconnect():
        events.append("disconnect")

    bootstrap.clear_cache = clear_cache
    bootstrap.disconnect = disconnect
    qualified = MagicMock()
    callback = MagicMock()

    async def resolve(*_args):
        events.append("resolve")
        return resolutions[0] if len(events) == 1 else resolutions[1]

    async def establish(client_class, device, address, **kwargs):
        assert address == ADDRESS
        assert kwargs["use_services_cache"] is False
        if len(events) == 1:
            events.append("bootstrap")
            assert "disconnected_callback" not in kwargs
            assert device is resolutions[0].device
            assert device.details["source"] == sources[0]
            return bootstrap
        events.append("qualify")
        assert device is resolutions[1].device
        assert device.details["source"] == sources[1]
        assert kwargs["disconnected_callback"] is callback
        return qualified

    resolver = SimpleNamespace(async_resolve=resolve)
    assert (
        await async_establish_ble_connection(
            hass, ADDRESS, resolver=resolver, establish=establish, disconnected_callback=callback
        )
        is qualified
    )
    assert events == ["resolve", "bootstrap", "clear", "disconnect", "resolve", "qualify"]
    callback.assert_not_called()
    qualified.clear_cache.assert_not_called()
    assert stale_gatt_recovery_pending(hass, ADDRESS)


@pytest.mark.parametrize("stage", ["bootstrap", "clear_false", "clear_error", "disconnect", "qualification"])
async def test_recovery_failure_retains_pending_and_sanitizes_errors(hass, stage, caplog):
    mark_stale_gatt_recovery(hass, ADDRESS)
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())
    establish = AsyncMock(side_effect=[bootstrap, MagicMock()])
    if stage == "bootstrap":
        establish.side_effect = RuntimeError(ADDRESS)
    elif stage == "clear_false":
        bootstrap.clear_cache.return_value = False
    elif stage == "clear_error":
        bootstrap.clear_cache.side_effect = RuntimeError(ADDRESS)
    elif stage == "disconnect":
        bootstrap.disconnect.side_effect = RuntimeError(ADDRESS)
    else:
        establish.side_effect = [bootstrap, RuntimeError(ADDRESS)]

    with pytest.raises(BleakError, match="Failed to recover the GATT cache") as caught:
        await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert ADDRESS not in str(caught.value)
    assert caught.value.__suppress_context__
    assert ADDRESS not in caplog.text
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert establish.await_count == (2 if stage == "qualification" else 1)
    assert bootstrap.disconnect.await_count == (0 if stage == "bootstrap" else 1)


@pytest.mark.parametrize("stage", ["resolve", "bootstrap", "clear", "disconnect", "qualification"])
async def test_recovery_is_bounded_at_every_await(hass, stage):
    mark_stale_gatt_recovery(hass, ADDRESS)
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())

    async def establish(*_args, **_kwargs):
        if stage == "bootstrap" or (stage == "qualification" and bootstrap.disconnect.await_count):
            await _never_finishes()
        return bootstrap

    if stage == "resolve":
        resolver.async_resolve.side_effect = _never_finishes
    elif stage == "clear":
        bootstrap.clear_cache.side_effect = _never_finishes
    elif stage == "disconnect":
        bootstrap.disconnect.side_effect = _never_finishes
    with (
        patch(f"{CONNECTION_M}.STALE_GATT_RECOVERY_TIMEOUT", 0.01),
        patch(f"{CONNECTION_M}.GATT_CACHE_CLEAR_TIMEOUT", 0.005),
        patch(f"{CONNECTION_M}.VALIDATION_DISCONNECT_TIMEOUT", 0.005),
    ):
        async with asyncio.timeout(1):
            with pytest.raises(BleakError, match="Failed to recover the GATT cache"):
                await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert bootstrap.disconnect.await_count == (0 if stage in {"resolve", "bootstrap"} else 1)


@pytest.mark.parametrize("stage", ["bootstrap", "clear", "disconnect", "qualification"])
async def test_recovery_cancellation_retains_pending_and_cleans_bootstrap(hass, stage):
    mark_stale_gatt_recovery(hass, ADDRESS)
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())
    establish = AsyncMock(side_effect=[bootstrap, MagicMock()])
    if stage == "bootstrap":
        establish.side_effect = asyncio.CancelledError
    elif stage == "clear":
        bootstrap.clear_cache.side_effect = asyncio.CancelledError
        bootstrap.disconnect.side_effect = RuntimeError(ADDRESS)
    elif stage == "disconnect":
        bootstrap.disconnect.side_effect = asyncio.CancelledError
    else:
        establish.side_effect = [bootstrap, asyncio.CancelledError]
    with pytest.raises(asyncio.CancelledError):
        await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert bootstrap.disconnect.await_count == (0 if stage == "bootstrap" else 1)


async def test_task_cancellation_during_clear_still_bounds_disconnect(hass):
    mark_stale_gatt_recovery(hass, ADDRESS)
    clearing = asyncio.Event()

    async def clear_cache():
        clearing.set()
        await _never_finishes()

    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(
        clear_cache=AsyncMock(side_effect=clear_cache), disconnect=AsyncMock(side_effect=_never_finishes)
    )
    establish = AsyncMock(return_value=bootstrap)
    with patch(f"{CONNECTION_M}.VALIDATION_DISCONNECT_TIMEOUT", 0.001):
        async with asyncio.timeout(1):
            task = asyncio.create_task(
                async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
            )
            await clearing.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    bootstrap.disconnect.assert_awaited_once_with()
    assert establish.await_count == 1
    assert stale_gatt_recovery_pending(hass, ADDRESS)


async def test_recovery_deadline_includes_bootstrap_and_qualification(hass):
    mark_stale_gatt_recovery(hass, ADDRESS)
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())
    deadlines = []
    timeout = asyncio.timeout

    def track_deadline(seconds):
        deadline = timeout(seconds)
        if seconds == 0.01:
            deadlines.append(deadline)
        return deadline

    async def establish(*_args, **_kwargs):
        assert len(deadlines) == 1
        assert not deadlines[0].expired()
        if not bootstrap.disconnect.await_count:
            return bootstrap
        await _never_finishes()

    with (
        patch(f"{CONNECTION_M}.STALE_GATT_RECOVERY_TIMEOUT", 0.01),
        patch(f"{CONNECTION_M}.asyncio.timeout", side_effect=track_deadline),
    ):
        async with asyncio.timeout(1):
            with pytest.raises(BleakError, match="Failed to recover the GATT cache"):
                await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert len(deadlines) == 1
    assert deadlines[0].expired()
    bootstrap.disconnect.assert_awaited_once_with()
    assert stale_gatt_recovery_pending(hass, ADDRESS)


async def test_manual_validation_marks_chained_stale_failure_then_recovers_without_clearing(hass):
    failure = BleakError("connection failed")
    failure.__cause__ = KeyError("org.bluez.GattService1")
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())
    qualified = MagicMock(disconnect=AsyncMock())
    establish = AsyncMock(side_effect=[failure, bootstrap, qualified])

    async def validation_establish(hass, address):
        return await async_establish_ble_connection(hass, address, establish=establish)

    with (
        patch(f"{CONNECTION_M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{CONNECTION_M}.async_establish_ble_connection", side_effect=validation_establish),
        patch(f"{CONNECTION_M}.clear_cache", return_value=True),
    ):
        with pytest.raises(BleakError, match="connection failed"):
            await async_validate_ble_connection(hass, ADDRESS)
        assert stale_gatt_recovery_pending(hass, ADDRESS)
        await async_validate_ble_connection(hass, ADDRESS)
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    qualified.disconnect.assert_awaited_once_with()
    assert stale_gatt_recovery_pending(hass, ADDRESS)


@pytest.mark.parametrize("stage", ["resolve", "establish"])
@pytest.mark.parametrize("stale", [False, True])
async def test_shared_establishment_marks_only_stale_failures(hass, stage, stale):
    failure = BleakError("connection failed")
    failure.__context__ = KeyError("org.bluez.GattService1" if stale else "org.bluez.Device1")
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    establish = AsyncMock(side_effect=failure)
    if stage == "resolve":
        resolver.async_resolve.side_effect = failure
    with patch(f"{CONNECTION_M}.clear_cache", return_value=True), pytest.raises(BleakError) as caught:
        await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert caught.value is failure
    assert stale_gatt_recovery_pending(hass, ADDRESS) is stale
    assert establish.await_count == (1 if stage == "establish" else 0)


@pytest.mark.parametrize("pending", [False, True])
async def test_bluez_no_client_failure_clears_address_before_next_recovery(hass, pending, caplog):
    if pending:
        mark_stale_gatt_recovery(hass, ADDRESS)
    failure = BleakError(ADDRESS)
    failure.__cause__ = RuntimeError("wrapper")
    failure.__cause__.__context__ = KeyError("org.bluez.GattService1")
    failure.__cause__.__cause__ = failure
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    bootstrap = MagicMock(clear_cache=AsyncMock(return_value=True), disconnect=AsyncMock())
    qualified = MagicMock()
    events = []
    cleared = False

    async def clear_address(address):
        nonlocal cleared
        assert address == ADDRESS
        assert stale_gatt_recovery_pending(hass, address)
        events.append("address_clear")
        cleared = True
        return True

    async def establish(*_args, **kwargs):
        if not cleared:
            events.append("failed_lookup")
            raise failure
        assert kwargs["use_services_cache"] is False
        if not bootstrap.disconnect.await_count:
            events.append("bootstrap")
            return bootstrap
        events.append("qualification")
        return qualified

    with patch(f"{CONNECTION_M}.clear_cache", side_effect=clear_address) as address_clear:
        with pytest.raises(BleakError) as caught:
            await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
        assert events == ["failed_lookup", "address_clear"]
        if pending:
            assert str(caught.value) == "Failed to recover the GATT cache"
            assert caught.value.__suppress_context__
        else:
            assert caught.value is failure
        assert await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish) is qualified
    address_clear.assert_awaited_once_with(ADDRESS)
    assert events == ["failed_lookup", "address_clear", "bootstrap", "qualification"]
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert ADDRESS not in caplog.text


@pytest.mark.parametrize(
    ("failure", "expected_clear"),
    [
        (BleakDBusError("org.bluez.Error.DoesNotExist", ["GATT service missing"]), True),
        (
            BleakDBusError("org.freedesktop.DBus.Error.UnknownObject", ["/org/bluez/hci0/dev_AA/service001"]),
            True,
        ),
        (BleakError("ESPHome GATT service not found"), False),
        (BleakError("ESP_GATT_CONN_FAIL_ESTABLISH"), False),
        (BleakDBusError("org.bluez.Error.DoesNotExist", ["Device missing"]), False),
        (BleakDBusError("org.freedesktop.DBus.Error.UnknownObject", ["/org/bluez/hci0/dev_AA"]), False),
        (BleakDBusError("org.freedesktop.DBus.Error.UnknownObject", ["GATT service missing"]), False),
        (KeyError("org.bluez.Device1"), False),
        (KeyError("org.bluez.GattService1", "unrelated"), False),
    ],
)
async def test_address_clear_requires_specific_bluez_stale_evidence(hass, failure, expected_clear):
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    establish = AsyncMock(side_effect=failure)
    with patch(f"{CONNECTION_M}.clear_cache", return_value=True) as address_clear:
        with pytest.raises(type(failure)) as caught:
            await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert caught.value is failure
    assert address_clear.await_count == int(expected_clear)
    assert establish.await_count == 1


async def test_address_clear_does_not_combine_unrelated_bluez_and_proxy_errors(hass):
    failure = BleakError("ESPHome GATT service not found")
    failure.__cause__ = BleakDBusError("org.bluez.Error.DoesNotExist", ["Device missing"])
    failure.__cause__.__context__ = failure
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    establish = AsyncMock(side_effect=failure)
    with patch(f"{CONNECTION_M}.clear_cache") as address_clear:
        with pytest.raises(BleakError) as caught:
            await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    assert caught.value is failure
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    address_clear.assert_not_awaited()


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("result", [False, RuntimeError(ADDRESS), "timeout"])
async def test_address_clear_failure_preserves_original_failure_and_pending(hass, pending, result, caplog):
    if pending:
        mark_stale_gatt_recovery(hass, ADDRESS)
    failure = KeyError("org.bluez.GattService1")
    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    establish = AsyncMock(side_effect=failure)
    clear = AsyncMock(return_value=False)
    if isinstance(result, Exception):
        clear.side_effect = result
    elif result == "timeout":
        clear.side_effect = _never_finishes
    with patch(f"{CONNECTION_M}.clear_cache", clear), patch(f"{CONNECTION_M}.GATT_CACHE_CLEAR_TIMEOUT", 0.001):
        async with asyncio.timeout(1):
            with pytest.raises((KeyError, BleakError)) as caught:
                await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
    if pending:
        assert str(caught.value) == "Failed to recover the GATT cache"
        assert caught.value.__suppress_context__
    else:
        assert caught.value is failure
    clear.assert_awaited_once_with(ADDRESS)
    assert establish.await_count == 1
    assert stale_gatt_recovery_pending(hass, ADDRESS)
    assert ADDRESS not in caplog.text


async def test_address_clear_propagates_task_cancellation(hass):
    clearing = asyncio.Event()

    async def clear_address(_address):
        clearing.set()
        await _never_finishes()

    resolver = SimpleNamespace(async_resolve=AsyncMock(return_value=_resolution()))
    establish = AsyncMock(side_effect=KeyError("org.bluez.GattService1"))
    with patch(f"{CONNECTION_M}.clear_cache", side_effect=clear_address):
        async with asyncio.timeout(1):
            task = asyncio.create_task(
                async_establish_ble_connection(hass, ADDRESS, resolver=resolver, establish=establish)
            )
            await clearing.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert establish.await_count == 1
    assert stale_gatt_recovery_pending(hass, ADDRESS)


async def test_connection_establishment_fails_after_bounded_cache_resolution(hass):
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=None)
    sleep = AsyncMock()

    with pytest.raises(BleakError, match="Device AA:BB:CC:DD:EE:FF not found"):
        await async_establish_ble_connection(hass, ADDRESS, resolver=resolver, sleep=sleep)

    assert resolver.async_resolve.await_count == 4
    assert sleep.await_count == 3


async def test_connection_validation_disconnects_established_client(hass):
    client = MagicMock(disconnect=AsyncMock())
    with (
        patch(f"{CONNECTION_M}.async_establish_ble_connection", new_callable=AsyncMock, return_value=client),
        patch.object(hass, "async_create_task") as create_task,
    ):
        await async_validate_ble_connection(hass, ADDRESS)
    client.disconnect.assert_awaited_once_with()
    create_task.assert_not_called()


async def test_connection_validation_surfaces_disconnect_failure(hass):
    client = MagicMock(disconnect=AsyncMock(side_effect=BleakError("disconnect failed")))
    with (
        patch(f"{CONNECTION_M}.async_establish_ble_connection", new_callable=AsyncMock, return_value=client),
        patch(f"{CONNECTION_M}.close_stale_connections_by_address", new_callable=AsyncMock) as close_stale,
    ):
        await async_validate_ble_connection(hass, ADDRESS)
    close_stale.assert_awaited_once_with(ADDRESS)


async def test_connection_validation_surfaces_cleanup_failure_without_address(hass):
    client = MagicMock(disconnect=AsyncMock(side_effect=BleakError("disconnect failed")))
    with (
        patch(f"{CONNECTION_M}.async_establish_ble_connection", new_callable=AsyncMock, return_value=client),
        patch(
            f"{CONNECTION_M}.close_stale_connections_by_address",
            new_callable=AsyncMock,
            side_effect=BleakError("cleanup failed"),
        ),
        pytest.raises(BleakError, match="Failed to close the validation connection") as exc,
    ):
        await async_validate_ble_connection(hass, ADDRESS)
    assert ADDRESS not in str(exc.value)


async def test_connection_validation_bounds_establishment_and_cleans_stale_connection(hass):
    async def never_connects(*_args, **_kwargs):
        await asyncio.Event().wait()

    with (
        patch(f"{CONNECTION_M}.VALIDATION_CONNECT_TIMEOUT", 0.001),
        patch(f"{CONNECTION_M}.async_establish_ble_connection", side_effect=never_connects),
        patch(f"{CONNECTION_M}.close_stale_connections_by_address", new_callable=AsyncMock) as close_stale,
        pytest.raises(BleakError, match="Timed out opening the validation connection") as exc,
    ):
        await async_validate_ble_connection(hass, ADDRESS)
    close_stale.assert_awaited_once_with(ADDRESS)
    assert ADDRESS not in str(exc.value)
