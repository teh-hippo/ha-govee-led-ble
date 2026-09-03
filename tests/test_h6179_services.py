"""H6179 light entity actions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import DOMAIN, ModelProfile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import parse_h6179_schedule_write
from custom_components.ha_govee_led_ble.h6179_schedule import (
    LimitState,
    ScheduleAction,
    ScheduleSlot,
    ScheduleState,
    ScheduleValidationError,
    SleepState,
    WakeState,
)
from custom_components.ha_govee_led_ble.h6179_services import (
    H6179_ENTITY_SERVICES,
    REPEAT_EVERY_DAY,
    REPEAT_ONE_TIME,
    REPEAT_SELECTED_DAYS,
    SERVICE_CONFIGURE_SCHEDULE_SLOT,
    SERVICE_CONFIGURE_SLEEP,
    SERVICE_CONFIGURE_WAKE,
    SERVICE_DISABLE_SCHEDULE_SLOT,
    SERVICE_DISABLE_SLEEP,
    SERVICE_DISABLE_WAKE,
    SERVICE_RESYNC_CLOCK,
    SERVICE_SET_LIMIT_CONTROL,
    async_configure_schedule_slot,
    async_configure_sleep,
    async_configure_wake,
    async_disable_schedule_slot,
    async_disable_sleep,
    async_disable_wake,
    async_register_h6179_services,
    async_set_limit_control,
)
from custom_components.ha_govee_led_ble.light_services import _GoveeLightServicesMixin


class FakeH6179Coordinator:
    def __init__(self, state: ScheduleState | None = None) -> None:
        self.model = "H6179"
        self.h6179_schedule_state = ScheduleState.neutral()
        self.h6179_schedule_slot_one_time = (False, False, False, False)
        self.h6179_wake_one_time = False
        self.device_state = ScheduleState.neutral() if state is None else state
        self.device_slot_one_time = (False, False, False, False)
        self.device_wake_one_time = False
        self.sent: list[bytes] = []
        self.refreshes: list[str] = []
        self.write_acceptance: list[bool] = []
        self._control_lock = asyncio.Lock()

    async def send_command(self, packet: bytes) -> None:
        assert self._control_lock.locked()
        self.sent.append(packet)
        parsed = parse_h6179_schedule_write(packet)
        assert parsed is not None
        if self.write_acceptance and not self.write_acceptance.pop(0):
            return
        values = parsed.values
        if parsed.operation == "timer":
            slot = int(values["slot"])
            updated = self.device_state.updated_slot(
                slot,
                enabled=bool(values["enabled"]),
                action=ScheduleAction(str(values["action"])),
                time=time(int(values["hour"]), int(values["minute"])),
                repeat_day_mask=int(values["repeat_day_mask"]),
            )
            one_time = list(self.device_slot_one_time)
            one_time[slot] = bool(values["one_time"])
            self.device_state = updated
            self.device_slot_one_time = (
                one_time[0],
                one_time[1],
                one_time[2],
                one_time[3],
            )
        elif parsed.operation == "sleep":
            self.device_state = replace(
                self.device_state,
                sleep=SleepState(
                    bool(values["enabled"]),
                    int(values["start_brightness"]),
                    int(values["duration_minutes"]),
                    int(values["remaining_minutes"]),
                ),
            )
        elif parsed.operation == "wake":
            self.device_state = replace(
                self.device_state,
                wake=WakeState(
                    bool(values["enabled"]),
                    time(int(values["hour"]), int(values["minute"])),
                    int(values["repeat_day_mask"]),
                    int(values["duration_minutes"]),
                    int(values["target_brightness"]),
                ),
            )
            self.device_wake_one_time = bool(values["one_time"])
        elif parsed.operation == "limit":
            self.device_state = replace(
                self.device_state,
                limit_state=LimitState(bool(values["enabled"])),
            )

    async def async_refresh_status_domains(
        self,
        domains: frozenset[str],
        *,
        required_domains: frozenset[str] | None = None,
        timeout: float = 2.0,
    ) -> bool:
        del required_domains, timeout
        assert self._control_lock.locked()
        assert len(domains) == 1
        domain = next(iter(domains))
        self.refreshes.append(domain)
        if domain == "schedules":
            self.h6179_schedule_state = replace(
                self.h6179_schedule_state,
                schedule_slots=self.device_state.schedule_slots,
            )
            self.h6179_schedule_slot_one_time = self.device_slot_one_time
        elif domain == "sleep":
            self.h6179_schedule_state = replace(
                self.h6179_schedule_state,
                sleep=self.device_state.sleep,
            )
        elif domain == "wake":
            self.h6179_schedule_state = replace(
                self.h6179_schedule_state,
                wake=self.device_state.wake,
            )
            self.h6179_wake_one_time = self.device_wake_one_time
        elif domain == "limit":
            self.h6179_schedule_state = replace(
                self.h6179_schedule_state,
                limit_state=self.device_state.limit_state,
            )
        return True


class H6179ServiceLight(_GoveeLightServicesMixin):
    def __init__(self, coordinator: FakeH6179Coordinator, **capabilities: bool) -> None:
        self.coordinator = cast(GoveeBLECoordinator, cast(Any, coordinator))
        self.coordinator.profile = cast(
            ModelProfile,
            SimpleNamespace(
                supports_clock_sync=capabilities.get("clock", True),
                supports_schedules=capabilities.get("schedules", True),
                supports_sleep=capabilities.get("sleep", True),
                supports_wake=capabilities.get("wake", True),
                supports_limit_control=capabilities.get("limit", True),
            ),
        )
        self.notifications = 0
        self.superseded = 0

    async def _async_supersede_preview(self) -> None:
        self.superseded += 1

    def _notify_state_changed(self) -> None:
        self.notifications += 1

    def _require_support(self, service: str, *, supported: bool) -> None:
        if not supported:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
                translation_placeholders={
                    "service": service,
                    "model": self.coordinator.model,
                },
            )


def _schemas() -> dict[str, vol.Schema]:
    return {name: vol.Schema(schema) for name, schema, _method in H6179_ENTITY_SERVICES}


def _parsed_last(coordinator: FakeH6179Coordinator):
    parsed = parse_h6179_schedule_write(coordinator.sent[-1])
    assert parsed is not None
    return parsed


def test_registers_h6179_entity_actions(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ha_govee_led_ble.h6179_services.service.async_register_platform_entity_service"
    ) as register:
        async_register_h6179_services(hass)

    assert [call.args[2] for call in register.call_args_list] == [
        SERVICE_RESYNC_CLOCK,
        SERVICE_CONFIGURE_SCHEDULE_SLOT,
        SERVICE_DISABLE_SCHEDULE_SLOT,
        SERVICE_CONFIGURE_SLEEP,
        SERVICE_DISABLE_SLEEP,
        SERVICE_CONFIGURE_WAKE,
        SERVICE_DISABLE_WAKE,
        SERVICE_SET_LIMIT_CONTROL,
    ]
    assert all(call.kwargs["func"].startswith("async_") for call in register.call_args_list)


@pytest.mark.parametrize(
    ("service_name", "payload"),
    [
        (SERVICE_CONFIGURE_SCHEDULE_SLOT, {"slot": 0}),
        (SERVICE_CONFIGURE_SCHEDULE_SLOT, {"slot": 5}),
        (SERVICE_CONFIGURE_SCHEDULE_SLOT, {"slot": True}),
        (SERVICE_CONFIGURE_SLEEP, {"start_brightness": 101}),
        (SERVICE_CONFIGURE_SLEEP, {"duration_minutes": 256}),
        (SERVICE_CONFIGURE_WAKE, {"duration_minutes": 9}),
        (SERVICE_CONFIGURE_WAKE, {"duration_minutes": 61}),
        (SERVICE_CONFIGURE_WAKE, {"target_brightness": 9}),
        (SERVICE_CONFIGURE_WAKE, {"target_brightness": 101}),
        (SERVICE_CONFIGURE_WAKE, {"weekdays": []}),
    ],
)
def test_service_schemas_reject_out_of_range_payloads(
    service_name: str,
    payload: dict[str, object],
) -> None:
    with pytest.raises(vol.Invalid):
        _schemas()[service_name](payload)


async def test_light_rejects_unsupported_model_before_io() -> None:
    coordinator = FakeH6179Coordinator()
    coordinator.model = "H617A"
    light = H6179ServiceLight(coordinator)

    with pytest.raises(ServiceValidationError) as error:
        await light.async_set_limit_control(True)

    assert error.value.translation_key == "unsupported_model"
    assert coordinator.sent == []
    assert coordinator.refreshes == []


async def test_schedule_partial_update_reads_and_preserves_other_fields() -> None:
    existing = ScheduleSlot(1, False, ScheduleAction.OFF, time(6, 15), 0x11)
    state = ScheduleState.neutral().updated_slot(
        1,
        enabled=existing.enabled,
        action=existing.action,
        time=existing.time,
        repeat_day_mask=existing.repeat_day_mask,
    )
    coordinator = FakeH6179Coordinator(state)

    await async_configure_schedule_slot(
        coordinator,
        slot=2,
        schedule_time=time(7, 45),
    )

    updated = coordinator.device_state.schedule_slots[1]
    assert updated == ScheduleSlot(1, True, ScheduleAction.OFF, time(7, 45), 0x11)
    assert coordinator.refreshes == ["schedules", "schedules"]
    assert coordinator.device_state.schedule_slots[0] == state.schedule_slots[0]


@pytest.mark.parametrize(
    ("repeat", "weekdays", "mask", "one_time"),
    [
        (REPEAT_ONE_TIME, None, 0, True),
        (REPEAT_EVERY_DAY, None, 0, False),
        (
            REPEAT_SELECTED_DAYS,
            ["monday", "wednesday", "sunday"],
            0x45,
            False,
        ),
    ],
)
async def test_schedule_repeat_modes(
    repeat: str,
    weekdays: list[str] | None,
    mask: int,
    one_time: bool,
) -> None:
    coordinator = FakeH6179Coordinator()

    await async_configure_schedule_slot(
        coordinator,
        slot=1,
        repeat=repeat,
        weekdays=weekdays,
    )

    parsed = _parsed_last(coordinator)
    assert parsed.values["repeat_day_mask"] == mask
    assert parsed.values["one_time"] is one_time


async def test_schedule_rejects_inconsistent_repeat_fields() -> None:
    coordinator = FakeH6179Coordinator()

    with pytest.raises(ScheduleValidationError, match="cannot include"):
        await async_configure_schedule_slot(
            coordinator,
            slot=1,
            repeat=REPEAT_ONE_TIME,
            weekdays=["monday"],
        )

    assert coordinator.sent == []


async def test_disabling_slot_preserves_action_time_repeat_and_one_time() -> None:
    state = ScheduleState.neutral().updated_slot(
        2,
        enabled=True,
        action=ScheduleAction.ON,
        time=time(22, 40),
        repeat_day_mask=0,
    )
    coordinator = FakeH6179Coordinator(state)
    coordinator.device_slot_one_time = (False, False, True, False)

    await async_disable_schedule_slot(coordinator, slot=3)

    parsed = _parsed_last(coordinator)
    assert parsed.values == {
        "slot": 2,
        "enabled": False,
        "action": "on",
        "hour": 22,
        "minute": 40,
        "repeat_day_mask": 0,
        "one_time": True,
    }


async def test_sleep_actions_preserve_hidden_fields() -> None:
    state = replace(
        ScheduleState.neutral(),
        sleep=SleepState(False, 63, 45, 17),
    )
    coordinator = FakeH6179Coordinator(state)

    await async_configure_sleep(coordinator, duration_minutes=30)
    configured = _parsed_last(coordinator)
    assert configured.values == {
        "enabled": True,
        "start_brightness": 63,
        "duration_minutes": 30,
        "remaining_minutes": 30,
    }

    await async_disable_sleep(coordinator)
    disabled = _parsed_last(coordinator)
    assert disabled.values == {
        "enabled": False,
        "start_brightness": 63,
        "duration_minutes": 30,
        "remaining_minutes": 30,
    }


async def test_wake_actions_preserve_fields_and_one_time() -> None:
    state = replace(
        ScheduleState.neutral(),
        wake=WakeState(False, time(6, 20), 0, 25, 70),
    )
    coordinator = FakeH6179Coordinator(state)
    coordinator.device_wake_one_time = True

    await async_configure_wake(coordinator, target_brightness=85)
    configured = _parsed_last(coordinator)
    assert configured.values == {
        "enabled": True,
        "target_brightness": 85,
        "hour": 6,
        "minute": 20,
        "repeat_day_mask": 0,
        "one_time": True,
        "duration_minutes": 25,
    }

    await async_disable_wake(coordinator)
    assert _parsed_last(coordinator).values["enabled"] is False
    assert coordinator.device_wake_one_time is True


async def test_limit_control_sets_both_boolean_states() -> None:
    coordinator = FakeH6179Coordinator()

    await async_set_limit_control(coordinator, enabled=True)
    assert coordinator.device_state.limit_state == LimitState(True)

    await async_set_limit_control(coordinator, enabled=False)
    assert coordinator.device_state.limit_state == LimitState(False)
    writes = [parse_h6179_schedule_write(packet) for packet in coordinator.sent]
    assert all(write is not None for write in writes)
    assert [write.values["enabled"] for write in writes if write is not None] == [True, False]


async def test_light_clock_resync_uses_home_assistant_timezone() -> None:
    coordinator = FakeH6179Coordinator()
    light = H6179ServiceLight(coordinator)
    local_time = datetime(
        2026,
        9,
        3,
        20,
        26,
        35,
        242000,
        tzinfo=timezone(timedelta(hours=9, minutes=30)),
    )

    with patch(
        "custom_components.ha_govee_led_ble.light_services.dt_util.now",
        return_value=local_time,
    ):
        await light.async_resync_clock()

    parsed = _parsed_last(coordinator)
    assert parsed.values["timezone_offset_minutes"] == 570
    assert parsed.values["second"] == 35
    assert coordinator.h6179_schedule_state.clock_sync is not None
    assert coordinator.h6179_schedule_state.clock_sync.local_time.microsecond == 0
    assert light.notifications == light.superseded == 1


async def test_failed_verification_retries_the_write() -> None:
    coordinator = FakeH6179Coordinator()
    coordinator.write_acceptance = [False, True]

    await async_set_limit_control(coordinator, enabled=True)

    assert len(coordinator.sent) == 2
    assert coordinator.refreshes == ["limit", "limit", "limit"]
    assert coordinator.h6179_schedule_state.limit_state == LimitState(True)


async def test_failed_verification_rolls_back_all_optimistic_fields() -> None:
    state = ScheduleState.neutral().updated_slot(
        0,
        enabled=False,
        action=ScheduleAction.OFF,
        time=time(8, 10),
        repeat_day_mask=0,
    )
    coordinator = FakeH6179Coordinator(state)
    coordinator.device_slot_one_time = (True, False, False, False)
    coordinator.write_acceptance = [False, False]

    with pytest.raises(RuntimeError, match="confirm"):
        await async_configure_schedule_slot(
            coordinator,
            slot=1,
            action="on",
            schedule_time=time(9, 20),
            repeat=REPEAT_SELECTED_DAYS,
            weekdays=["tuesday", "thursday"],
        )

    assert coordinator.h6179_schedule_state == state
    assert coordinator.h6179_schedule_slot_one_time == (True, False, False, False)
    assert len(coordinator.sent) == 2


async def test_light_maps_invalid_payload_and_transport_failure() -> None:
    coordinator = FakeH6179Coordinator()
    light = H6179ServiceLight(coordinator)

    with pytest.raises(ServiceValidationError) as invalid:
        await light.async_configure_wake(
            repeat=REPEAT_SELECTED_DAYS,
            weekdays=None,
        )
    assert invalid.value.translation_key == "invalid_h6179_schedule"

    coordinator.write_acceptance = [False, False]
    with pytest.raises(HomeAssistantError) as failed:
        await light.async_set_limit_control(True)
    assert failed.value.translation_key == "device_command_failed"


def test_h6179_service_translations_match_english_catalogue() -> None:
    root = Path(__file__).parents[1] / "custom_components" / "ha_govee_led_ble"
    strings = json.loads((root / "strings.json").read_text())
    english = json.loads((root / "translations" / "en.json").read_text())
    service_names = {name for name, _schema, _method in H6179_ENTITY_SERVICES}

    assert strings == english
    assert service_names <= strings["services"].keys()
    assert strings["exceptions"]["invalid_h6179_schedule"]["message"]
