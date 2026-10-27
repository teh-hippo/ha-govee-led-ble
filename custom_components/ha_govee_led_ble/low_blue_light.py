"""Profile-qualified native setting with opaque sibling preservation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from .const import ModelProfile
from .control_arbiter import ControlIntent, async_control_intent
from .protocol_core import ProtocolParseResult, _parse_xor_frame, _serialize_xor, new_child

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator

Setting = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6072_low_blue_light").H6072LowBlueLight,
)


@dataclass(frozen=True)
class LowBlueLightState:
    enabled: bool
    sibling_1: int
    sibling_2: int
    level: int


def require_low_blue_light(profile: ModelProfile) -> None:
    if profile.setting_grammar != "H6072" or not profile.supports_low_blue_light:
        raise ValueError("Device profile does not support low-blue-light control")


def parse_setting(frame: bytes, profile: ModelProfile, kind: str = "status") -> ProtocolParseResult:
    return _parse_xor_frame(
        frame,
        kind if profile.setting_grammar == "H6072" else None,
        {
            "envelope": ("h6072_low_blue_light.envelope", Setting.Envelope),
            "status": ("h6072_low_blue_light", Setting),
            "write": ("h6072_low_blue_light.write", Setting.Write),
            "query": ("h6072_low_blue_light.query", Setting.Query),
        },
    )


def setting_state(parsed: Any) -> LowBlueLightState | None:
    body = parsed.body
    if not body.is_supported:
        return None
    return LowBlueLightState(bool(body.enabled), body.sibling_1, body.sibling_2, body.level)


def build_query(profile: ModelProfile) -> bytes:
    require_low_blue_light(profile)
    root = Setting.Query()
    root.header, root.opcode = Setting.Prefix.status, Setting.Operation.low_blue_light
    root.method = Setting.Method.scale
    root.padding = bytes(16)
    return _serialize_xor(root)


def build_setting(state: LowBlueLightState, profile: ModelProfile) -> bytes:
    require_low_blue_light(profile)
    if type(state.enabled) is not bool or type(state.level) is not int:
        raise ValueError("Low-blue-light requires a boolean enable and integer level")
    root = Setting.Write()
    root.header, root.opcode = Setting.Prefix.write, Setting.Operation.low_blue_light
    root.body = new_child(Setting.State, root)
    root.body.method = Setting.Method.scale
    root.body.enabled = int(state.enabled)
    root.body.sibling_1, root.body.sibling_2, root.body.level = state.sibling_1, state.sibling_2, state.level
    root.padding = bytes(12)
    if not root.body.is_supported:
        raise ValueError("Low-blue-light level is outside the supported range")
    return _serialize_xor(root)


async def async_set_setting(
    coordinator: GoveeBLECoordinator, *, enabled: bool | None = None, level: int | None = None
) -> None:
    from dataclasses import replace

    require_low_blue_light(coordinator.profile)
    bounds = Setting.State()
    if (
        (enabled is None and level is None)
        or (enabled is not None and type(enabled) is not bool)
        or (level is not None and (type(level) is not int or not bounds.minimum_level <= level <= bounds.maximum_level))
    ):
        raise ValueError("Specify a boolean low-blue-light enable or an integer level within its supported range")
    async with async_control_intent(coordinator, ControlIntent.USER):
        await coordinator._async_supersede_effect_preview()
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            profile = coordinator.profile
            generation, token = coordinator._profile_generation, coordinator._notification_token

            def guard() -> None:
                require_low_blue_light(coordinator.profile)
                if (
                    coordinator.profile != profile
                    or coordinator._profile_generation != generation
                    or coordinator._notification_token is not token
                    or coordinator._client is not client
                    or not client.is_connected
                    or not coordinator.identity_fields_confirmed(frozenset({"fw_version"}))
                ):
                    raise ValueError("Low-blue-light connection or profile changed")

            guard()
            query = build_query(profile)

            async def read() -> LowBlueLightState:
                if not await coordinator._async_read_setting_fields(
                    client, query, ("low_blue_light",), deadline=time.monotonic() + 4.0, write_guard=guard
                ):
                    raise ValueError("Device did not provide fresh low-blue-light readback")
                guard()
                state = coordinator.low_blue_light
                if state is None:
                    raise ValueError("Device returned an unknown low-blue-light setting")
                return state

            state = await read()
            expected = replace(
                state,
                enabled=state.enabled if enabled is None else enabled,
                level=state.level if level is None else level,
            )
            await coordinator._async_write_packet(client, build_setting(expected, profile), before_write=guard)
            if await read() != expected:
                raise ValueError("Device did not confirm low-blue-light and its sibling fields")
