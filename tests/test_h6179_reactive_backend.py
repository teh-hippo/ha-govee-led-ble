"""Focused async backend coverage for H6179 reactive RGB."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, ControlIntent
from custom_components.ha_govee_led_ble.h6179_reactive_backend import (
    H6179ReactiveBackend,
    ReactiveBackendStopReason,
    ReactiveSessionBusyError,
    ReactiveSessionNotFoundError,
    ReactiveSessionSupersededError,
    ReactiveSessionUnauthorizedError,
    ReactiveTargetUnavailableError,
    ReactiveTargetUnsupportedError,
    ReactiveWriteError,
)
from custom_components.ha_govee_led_ble.h6179_reactive_protocol import (
    H6179_REACTIVE_SESSION_TIMEOUT,
    H6179ReactiveRoute,
    ReactivePayloadError,
    ReactiveSessionState,
    UnresolvedReactiveFirmwareError,
)
from custom_components.ha_govee_led_ble.h6179_reactive_service import (
    ReactiveErrorCode,
    reactive_error_code,
)


@dataclass
class _Coordinator:
    fw_version: str | None = "1.01.00"
    model: str = "H6179"
    frames: list[bytes] = field(default_factory=list)
    write_times: list[float] = field(default_factory=list)
    preflight_calls: int = 0
    fail_preflight: bool = False
    fail_writes: bool = False
    block_preflight: bool = False
    block_first_write: bool = False
    _control_arbiter: BLEControlArbiter = field(default_factory=BLEControlArbiter)
    preflight_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_preflight: asyncio.Event = field(default_factory=asyncio.Event)
    write_started: asyncio.Event = field(default_factory=asyncio.Event)
    release_write: asyncio.Event = field(default_factory=asyncio.Event)

    async def async_preview_preflight(self, *, timeout: float = 8.0) -> None:
        assert timeout > 0
        self.preflight_calls += 1
        if self.fail_preflight:
            raise TimeoutError
        if self.block_preflight:
            self.preflight_started.set()
            await self.release_preflight.wait()

    async def async_preview_write(self, packet: bytes) -> None:
        if self.fail_writes:
            raise OSError("BLE write failed")
        if self.block_first_write and not self.frames:
            self.write_started.set()
            await self.release_write.wait()
        self.frames.append(packet)
        self.write_times.append(asyncio.get_running_loop().time())


async def _start(
    backend: H6179ReactiveBackend,
    coordinator: _Coordinator,
    *,
    entry_id: str = "entry-a",
    owner: object = "owner-a",
    legacy_colour_order: bool = False,
) -> str:
    status = await backend.async_start(
        config_entry_id=entry_id,
        owner=owner,
        coordinator=coordinator,
        legacy_colour_order=legacy_colour_order,
    )
    assert status.session_id is not None
    return status.session_id


async def test_start_update_stop_lifecycle() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)

    updated = await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 0x56, "g": 0, "b": 0},
    )
    stopped = await backend.async_stop(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
    )

    assert updated.state is ReactiveSessionState.ACTIVE
    assert updated.route is H6179ReactiveRoute.MUSIC_STREAM
    assert coordinator.preflight_calls == 1
    assert coordinator.frames == [bytes.fromhex("a5028356000080")]
    assert stopped.stop_reason is ReactiveBackendStopReason.REQUESTED
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_owner_isolation_and_one_session_per_entry() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)

    with pytest.raises(ReactiveSessionUnauthorizedError):
        await backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-b",
            rgb_payload={"r": 1, "g": 2, "b": 3},
        )
    with pytest.raises(ReactiveSessionUnauthorizedError):
        await _start(backend, coordinator, owner="owner-b")
    with pytest.raises(ReactiveSessionBusyError):
        await _start(backend, coordinator)

    assert backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_config_entries_have_isolated_sessions_and_writes() -> None:
    backend = H6179ReactiveBackend()
    first = _Coordinator()
    second = _Coordinator()
    first_session = await _start(backend, first, entry_id="entry-a")
    second_session = await _start(backend, second, entry_id="entry-b")

    await asyncio.gather(
        backend.async_update(
            config_entry_id="entry-a",
            session_id=first_session,
            owner="owner-a",
            rgb_payload={"r": 1, "g": 2, "b": 3},
        ),
        backend.async_update(
            config_entry_id="entry-b",
            session_id=second_session,
            owner="owner-a",
            rgb_payload={"r": 4, "g": 5, "b": 6},
        ),
    )

    assert first.frames == [bytes.fromhex("a5028301020330")]
    assert second.frames == [bytes.fromhex("a5028304050639")]
    await backend.async_shutdown()


async def test_concurrent_updates_are_serialised_and_latest_only() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator(block_first_write=True)
    session_id = await _start(backend, coordinator)
    first = asyncio.create_task(
        backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-a",
            rgb_payload={"r": 255, "g": 0, "b": 0},
        )
    )
    await coordinator.write_started.wait()
    second = asyncio.create_task(
        backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-a",
            rgb_payload={"r": 0, "g": 255, "b": 0},
        )
    )
    await asyncio.sleep(0)
    third = asyncio.create_task(
        backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-a",
            rgb_payload={"r": 0, "g": 0, "b": 255},
        )
    )
    coordinator.release_write.set()
    await asyncio.gather(first, second, third)
    await asyncio.sleep(0.06)

    assert coordinator.frames == [
        bytes.fromhex("a50283ff000029"),
        bytes.fromhex("a502830000ff29"),
    ]
    assert coordinator.write_times[1] - coordinator.write_times[0] >= 0.045
    await backend.async_shutdown()


async def test_coalesced_update_is_written_by_one_due_tick() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)

    await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 1, "g": 2, "b": 3},
    )
    coalesced = await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 4, "g": 5, "b": 6},
    )

    assert coalesced.coalesced
    assert len(coordinator.frames) == 1
    await asyncio.sleep(0.06)
    assert coordinator.frames == [
        bytes.fromhex("a5028301020330"),
        bytes.fromhex("a5028304050639"),
    ]
    assert not backend._tasks
    await backend.async_shutdown()


async def test_write_failure_stops_and_discards_the_session() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator(fail_writes=True)
    session_id = await _start(backend, coordinator)

    with pytest.raises(ReactiveWriteError) as raised:
        await backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-a",
            rgb_payload={"r": 1, "g": 2, "b": 3},
        )

    assert reactive_error_code(raised.value) is ReactiveErrorCode.WRITE_FAILED
    assert backend.status("entry-a").stop_reason is ReactiveBackendStopReason.WRITE_FAILED
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_start_failure_does_not_create_a_session() -> None:
    backend = H6179ReactiveBackend()

    with pytest.raises(ReactiveTargetUnavailableError) as raised:
        await _start(backend, _Coordinator(fail_preflight=True))

    assert reactive_error_code(raised.value) is ReactiveErrorCode.TARGET_UNAVAILABLE
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_normal_control_supersedes_a_pending_start() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator(block_preflight=True)
    start = asyncio.create_task(_start(backend, coordinator))
    await coordinator.preflight_started.wait()

    async with coordinator._control_arbiter.hold(ControlIntent.USER):
        pass
    coordinator.release_preflight.set()

    with pytest.raises(ReactiveSessionSupersededError):
        await start
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_inactivity_timeout_stops_without_busy_polling() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    await _start(backend, coordinator)
    state = backend._entries["entry-a"]

    assert state.timer is not None
    assert state.tick_task is None
    await asyncio.sleep(H6179_REACTIVE_SESSION_TIMEOUT + 0.05)

    assert backend.status("entry-a").stop_reason is ReactiveBackendStopReason.TIMEOUT
    assert not backend.is_active("entry-a")
    assert not backend._tasks
    await backend.async_shutdown()


async def test_disconnect_stops_and_invalidates_session() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)

    disconnected = await backend.async_disconnect_device("entry-a")
    assert disconnected.stop_reason is ReactiveBackendStopReason.DISCONNECTED
    with pytest.raises(ReactiveSessionNotFoundError):
        await backend.async_update(
            config_entry_id="entry-a",
            session_id=session_id,
            owner="owner-a",
            rgb_payload={"r": 1, "g": 2, "b": 3},
        )
    await backend.async_shutdown()


async def test_unload_stops_blocks_restart_and_load_reenables_entry() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    await _start(backend, coordinator)

    unloaded = await backend.async_unload_device("entry-a")
    assert unloaded.stop_reason is ReactiveBackendStopReason.UNLOADED
    with pytest.raises(ReactiveTargetUnavailableError):
        await _start(backend, coordinator)

    await backend.async_load_device("entry-a")
    await _start(backend, coordinator)
    await backend.async_shutdown()


async def test_normal_control_intent_supersedes_pending_reactive_work() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)
    await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 1, "g": 2, "b": 3},
    )
    await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 4, "g": 5, "b": 6},
    )

    async with coordinator._control_arbiter.hold(ControlIntent.USER):
        pass
    await asyncio.sleep(0.06)

    assert coordinator.frames == [bytes.fromhex("a5028301020330")]
    assert backend.status("entry-a").stop_reason is ReactiveBackendStopReason.SUPERSEDED
    await backend.async_shutdown()


async def test_supersession_hook_stops_an_idle_active_session_immediately() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    await _start(backend, coordinator)

    superseded = await backend.async_supersede_device("entry-a")

    assert superseded.stop_reason is ReactiveBackendStopReason.SUPERSEDED
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_invalid_and_pcm_payloads_are_rejected_without_changing_session() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator()
    session_id = await _start(backend, coordinator)

    for payload in (
        {"pcm": [1, 2, 3]},
        {"audio": "AAAA"},
        {"r": 1, "g": 2, "b": 3, "pcm": []},
        [1, 2, 3],
        b"\x01\x02\x03",
    ):
        with pytest.raises(ReactivePayloadError) as raised:
            await backend.async_update(
                config_entry_id="entry-a",
                session_id=session_id,
                owner="owner-a",
                rgb_payload=payload,
            )
        assert reactive_error_code(raised.value) is ReactiveErrorCode.INVALID_PAYLOAD

    assert coordinator.frames == []
    assert backend.status("entry-a").state is ReactiveSessionState.ACTIVE
    await backend.async_shutdown()


async def test_unknown_firmware_fails_closed_with_stable_error() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator(fw_version=None)

    with pytest.raises(UnresolvedReactiveFirmwareError) as raised:
        await _start(backend, coordinator)

    assert reactive_error_code(raised.value) is ReactiveErrorCode.UNKNOWN_FIRMWARE
    assert not backend.is_active("entry-a")
    await backend.async_shutdown()


async def test_non_h6179_target_is_rejected() -> None:
    backend = H6179ReactiveBackend()

    with pytest.raises(ReactiveTargetUnsupportedError) as raised:
        await _start(backend, _Coordinator(model="H617A"))

    assert reactive_error_code(raised.value) is ReactiveErrorCode.TARGET_UNSUPPORTED
    await backend.async_shutdown()


async def test_explicit_legacy_route_is_bounded_and_opt_in() -> None:
    backend = H6179ReactiveBackend()
    coordinator = _Coordinator(fw_version="1.00.02")
    session_id = await _start(backend, coordinator, legacy_colour_order=True)

    await backend.async_update(
        config_entry_id="entry-a",
        session_id=session_id,
        owner="owner-a",
        rgb_payload={"r": 0x56, "g": 0, "b": 0},
    )
    assert coordinator.frames == [bytes.fromhex("33050d560000000000000000000000000000006d")]
    await backend.async_shutdown()

    unsupported = H6179ReactiveBackend()
    with pytest.raises(UnresolvedReactiveFirmwareError):
        await _start(
            unsupported,
            _Coordinator(fw_version="1.01.00"),
            legacy_colour_order=True,
        )
    await unsupported.async_shutdown()


async def test_stop_disconnect_unload_and_shutdown_leave_no_tasks() -> None:
    backend = H6179ReactiveBackend()
    first = _Coordinator()
    second = _Coordinator()
    third = _Coordinator()
    first_session = await _start(backend, first, entry_id="entry-a")
    await _start(backend, second, entry_id="entry-b")
    await _start(backend, third, entry_id="entry-c")

    await backend.async_stop(config_entry_id="entry-a", session_id=first_session, owner="owner-a")
    await backend.async_disconnect_device("entry-b")
    await backend.async_unload_device("entry-c")
    await backend.async_shutdown()
    await asyncio.sleep(0)

    assert backend._entries == {}
    assert backend._tasks == set()
