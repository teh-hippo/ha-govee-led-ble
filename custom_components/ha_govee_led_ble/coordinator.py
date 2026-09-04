"""DataUpdateCoordinator for HA Govee LED BLE."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from bleak import BleakClient, BleakError  # type: ignore[attr-defined]
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import UpdateFailed

from .ble_connection import RETRY_BACKOFF_SECONDS, async_establish_ble_connection
from .ble_device_resolver import BLEDeviceResolver
from .const import (
    DOMAIN,
    MUSIC_MODE_SLUGS,
    ReadDomain,
    default_effect_categories,
    default_effect_families,
    get_profile,
)
from .control_arbiter import BLEControlArbiter, ControlIntent, PreviewAdmission, async_control_intent
from .coordinator_expectations import expectations_from_packet
from .coordinator_modes import PreModeSnapshot, _ActiveModeMixin
from .coordinator_status import ParsedMode, StatusDomain, decode_status_frame_result, parse_color_mode
from .effect_commands import build_h617a_diy_activation
from .effect_contracts import CapabilityState
from .effect_deployments import PriorControlState
from .generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h6199_subordinate_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_relative_brightness_query,
    build_segment_query,
    build_white_balance_query,
    parse_command_ack_result,
    parse_command_result,
)
from .govee_encryption import GoveeEncryptionSession
from .h6199_calibration import WHITE_BALANCE_RESET
from .light_commands import (
    SegmentColorGroup,
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_paint,
    kelvin_to_rgb,
)
from .music_commands import prepare_music_profile_writes
from .music_semantics import capture_music_parameters, music_params_for_mode, music_variant
from .native_profile_controls import (
    apply_active_video_mode,
    apply_blank_screen,
    apply_relative_brightness,
    apply_white_balance,
)
from .native_scenes import build_native_scene_packets
from .scenes import MODEL_SCENES, canonical_scene_key, resolve_scene_code, scene_code_is_ambiguous
from .transport import READ_UUID, WRITE_UUID
from .video_applicability import identity_version, video_control_states

EFFECT_SEQUENCE_ATTEMPTS = 3
EFFECT_SEQUENCE_CONNECT_TIMEOUT = 8.0

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 15
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
RX_STALE_TIMEOUT = KEEP_ALIVE_INTERVAL * 4
IDENTITY_RETRY_TICKS = 6
PACKET_LOG_LIMIT = 50
PACKET_LOG_RAW_BYTES_LIMIT = 512
EXPECTED_STATE_TTL = 2.0
AVAILABILITY_UNAVAILABLE_DATA_KEY = "availability_unavailable"

_CORE_STATE_FIELDS = (
    "is_on",
    "brightness_pct",
    "rgb_color",
    "color_temp_kelvin",
    "effect",
    "diy_code",
)
_COLOR_MODE_FIELDS = (
    "video_full_screen",
    "video_saturation",
    "video_sound_effects",
    "video_sound_effects_softness",
    "music_sensitivity",
    "music_calm",
    "music_color",
    "white_brightness",
)
_COLOR_EXPECTATION_FIELDS = frozenset(
    (
        "color_mode",
        "effect",
        "scene_code",
        "unknown_scene_code",
        "rgb_color",
        "color_temp_kelvin",
        "music_mode",
        "video_mode",
        *_COLOR_MODE_FIELDS,
    )
)


class GoveeBLECoordinator(_ActiveModeMixin):
    """Manages BLE connection lifecycle for a Govee device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        model: str,
        *,
        configuration_url: str | None,
        effect_families: frozenset[str] | None = None,
        effect_categories: frozenset[str] | None = None,
        prefix_effect_names: bool = False,
        always_include_custom_effects: bool = False,
        device_resolver: BLEDeviceResolver | None = None,
    ) -> None:
        profile = get_profile(model)
        super().__init__(
            hass,
            _LOGGER,
            name=f"Govee {model} ({address})",
            update_interval=(
                timedelta(seconds=30) if profile.state_readable and profile.connection_idle_timeout is None else None
            ),
        )
        self.address, self.model, self.profile = address, model, profile
        self.configuration_url = configuration_url
        self.effect_families = default_effect_families(model) if effect_families is None else effect_families
        self.effect_categories = (
            frozenset(default_effect_categories(model)) if effect_categories is None else effect_categories
        )
        self.prefix_effect_names = prefix_effect_names
        self.always_include_custom_effects = always_include_custom_effects
        self._device_resolver = BLEDeviceResolver() if device_resolver is None else device_resolver
        self._client: BleakClient | None = None
        # Connection-scoped.  Inert until a device asks for encryption, and reset on every
        # disconnect so a reconnect renegotiates rather than reusing a dead session.
        self._encryption = GoveeEncryptionSession(address)
        self._lock = asyncio.Lock()
        self._control_arbiter = BLEControlArbiter()
        self._control_lock = self._control_arbiter
        self._cancel_disconnect: CALLBACK_TYPE | None = None
        self._disconnect_generation = 0
        self._intentional_disconnect_client: BleakClient | None = None
        self._keep_alive_task: asyncio.Task[None] | None = None
        self._keep_alive_ticks = 0
        self._identity_retries = 0
        self.is_on = False
        self.brightness_pct = 100
        self.rgb_color: tuple[int, int, int] = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.rgb_color_source = self.color_temp_kelvin_source = "initial"
        self.effect: str | None = None
        # Device identity from the aa 06/aa 07 handshake replies; None until first read.
        self.fw_version: str | None = None
        self.hw_version: str | None = None
        self.subordinate_20_version: str | None = None
        self.subordinate_21_version: str | None = None
        self.music_mode = "off"
        self.video_mode = "off"
        self.diy_code: int | None = None
        self.color_mode: ParsedMode | None = None
        self._scene_code: int | None = None
        self._pre_mode_snapshot = PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
        self.segment_colors: list[tuple[int, int, int]] = [self.rgb_color] * profile.segment_count
        self.segment_brightness: list[int] = [100] * profile.segment_count
        self.segment_state_source = "initial"
        self.segment_state_observed_at: str | None = None
        self._segment_groups_observed: set[int] = set()
        self._segment_query_colors: list[tuple[int, int, int]] | None = None
        self._segment_query_brightness: list[int] | None = None
        self.video_saturation = self.white_brightness = 100
        self.music_sensitivity = 99
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 100
        self.music_color: tuple[int, int, int] | None = None
        # H6199 display settings and edge brightness. None means the first read has not landed.
        self.white_balance_red: int | None = None
        self.control_write_attempts = 0
        self.white_balance_blue: int | None = None
        self.white_balance_scalar: int | None = None
        self.relative_brightness: int | None = None
        self.relative_brightness_left: int | None = None
        self.relative_brightness_top: int | None = None
        self.relative_brightness_right: int | None = None
        self.relative_brightness_bottom: int | None = None
        self.relative_brightness_strip_left: int | None = None
        self.relative_brightness_strip_right: int | None = None
        self.blank_screen: bool | None = None
        self.blank_screen_detection: int | None = None
        self.blank_screen_low_brightness_duration_seconds: int | None = None
        self.blank_screen_same_tone_duration_seconds: int | None = None
        self.music_separation_point = 1
        self.music_separation_gradient = True
        self.music_hopping_brightness = 50
        self.music_piano_key_count = 15
        self.music_fountain_direction = "clockwise"
        self.music_daynight_segments = 1
        self.music_daynight_speed = 10
        self.music_daynight_gradient = False
        for variant in self.profile.music_variants:
            for spec in music_params_for_mode(variant.mode_code, self.profile):
                setattr(self, spec.key, spec.default)
        self.packet_log: list[dict[str, Any]] = []
        self._expected_state: dict[str, tuple[Any, float]] = {}
        self._notify_started_monotonic: float | None = None
        self._last_rx_monotonic: float | None = None
        self._domain_revisions: dict[StatusDomain, int] = {}
        self._field_revisions: dict[str, int] = {}
        self._revision_event = asyncio.Event()
        # BLE presence (advertisement-driven) and first-refresh gate for ConfigEntryNotReady.
        self._present = False
        self._first_refresh_done = False
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop)

    @property
    def device_info(self) -> dr.DeviceInfo:
        # No `connections`: the BLE MAC is PII and must not surface in the device UI (OD1).
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=f"Govee {self.model}",
            manufacturer="Govee",
            model=self.model,
            configuration_url=self.configuration_url,
            sw_version=self.fw_version,
            hw_version=self.hw_version,
        )

    def capture_effect_control_state(self) -> PriorControlState:
        return PriorControlState(
            mode=self.active_mode,
            is_on=self.is_on,
            brightness_pct=self.brightness_pct,
            rgb_color=self.rgb_color,
            color_temp_kelvin=self.color_temp_kelvin,
            effect=self.effect,
            scene_code=self.scene_code,
            diy_code=self.diy_code,
            music_mode=self.music_mode,
            music_model=self.model,
            music_parameters=capture_music_parameters(self, self.profile, self.music_mode),
            video_mode=self.video_mode,
            music_sensitivity=self.music_sensitivity,
            music_calm=self.music_calm,
            music_color=self.music_color,
            music_separation_point=self.music_separation_point,
            music_separation_gradient=self.music_separation_gradient,
            music_hopping_brightness=self.music_hopping_brightness,
            music_piano_key_count=self.music_piano_key_count,
            music_fountain_direction=self.music_fountain_direction,
            music_daynight_segments=self.music_daynight_segments,
            music_daynight_speed=self.music_daynight_speed,
            music_daynight_gradient=self.music_daynight_gradient,
            video_full_screen=self.video_full_screen,
            video_saturation=self.video_saturation,
            video_sound_effects=self.video_sound_effects,
            video_sound_effects_softness=self.video_sound_effects_softness,
            white_balance_red=self.white_balance_red,
            white_balance_blue=self.white_balance_blue,
            white_balance_scalar=self.white_balance_scalar,
            relative_brightness=self.relative_brightness,
            relative_brightness_left=self.relative_brightness_left,
            relative_brightness_top=self.relative_brightness_top,
            relative_brightness_right=self.relative_brightness_right,
            relative_brightness_bottom=self.relative_brightness_bottom,
            relative_brightness_strip_left=self.relative_brightness_strip_left,
            relative_brightness_strip_right=self.relative_brightness_strip_right,
            blank_screen=self.blank_screen,
            blank_screen_detection=self.blank_screen_detection,
            blank_screen_low_brightness_duration_seconds=self.blank_screen_low_brightness_duration_seconds,
            blank_screen_same_tone_duration_seconds=self.blank_screen_same_tone_duration_seconds,
        )

    async def async_restore_effect_control_state(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
    ) -> bool:
        music_writes: tuple[tuple[bytes, dict[str, Any]], ...] = ()
        if state.mode == "music" and state.is_on:
            if state.music_model is not None and state.music_model != self.model:
                raise ValueError("music recovery model does not match device")
            if state.music_mode not in self.profile.music_modes:
                return False
            variant = music_variant(self.profile, MUSIC_MODE_SLUGS[state.music_mode])
            # Legacy snapshots retain style across modes even when the active selector
            # has no style byte semantics. Do not reinterpret that retained value.
            music_calm = state.music_calm if variant and variant.supports_style else False
            music_parameters = (
                dict(state.music_parameters)
                if state.music_parameters is not None
                else capture_music_parameters(state, self.profile, state.music_mode) or {}
            )
            music_writes = prepare_music_profile_writes(
                self.model,
                state.music_mode,
                state.music_sensitivity,
                state.music_color,
                music_calm,
                music_parameters,
            )
        states = video_control_states(self.profile, self)
        permitted = {
            control
            for control, status in states.items()
            if status is CapabilityState.SUPPORTED
            and (state.video_restore_controls is None or control in state.video_restore_controls)
        }
        needed = {
            control
            for control, fields in (
                (
                    "white_balance",
                    ("white_balance_scalar",)
                    if self.profile.video_white_balance_representation == "scalar"
                    else ("white_balance_red", "white_balance_blue"),
                ),
                (
                    "relative_brightness",
                    tuple(f"relative_brightness_{zone}" for zone in self.profile.video_brightness_zones),
                ),
                ("blank_screen", ("blank_screen",)),
            )
            if (state.video_restore_controls is None or control in state.video_restore_controls)
            and any(
                getattr(state, field) is not None and getattr(self, field) != getattr(state, field) for field in fields
            )
        }
        complete = not (needed - permitted)
        if (
            "white_balance" in permitted & needed
            and state.white_balance_scalar is not None
            and self.profile.video_white_balance_representation == "scalar"
        ):
            await apply_white_balance(self, (state.white_balance_scalar,))
        if (
            "white_balance" in permitted & needed
            and self.profile.video_white_balance_representation == "position"
            and state.white_balance_red is not None
            and state.white_balance_blue is not None
        ):
            await apply_white_balance(self, (state.white_balance_red, state.white_balance_blue))
        if (
            "relative_brightness" in permitted & needed
            and state.relative_brightness_left is not None
            and state.relative_brightness_top is not None
            and state.relative_brightness_right is not None
            and state.relative_brightness_bottom is not None
        ):
            await apply_relative_brightness(
                self,
                tuple(getattr(state, f"relative_brightness_{zone}") for zone in self.profile.video_brightness_zones),
            )
        if "blank_screen" in permitted & needed and state.blank_screen is not None:
            await apply_blank_screen(self, state.blank_screen)
        if not state.is_on:
            await self.send_command(build_power(False, self.model))
            self.is_on = False
            return self.profile.state_readable and await self.refresh_state(expected_on=False) and complete
        if state.mode == "custom":
            if (
                state.diy_code is None
                or (overwritten_diy_code is not None and state.diy_code == overwritten_diy_code)
                or not self.profile.supports_custom_effects
                or self.profile.effect_grammar != "H617A"
                or self.profile.command_grammar != "H617A"
            ):
                return False
            await self.send_command(build_h617a_diy_activation(state.diy_code))
            self.diy_code = state.diy_code
            return await self.async_observe_effect({"is_on": True, "diy_code": state.diy_code}) is True and complete
        if state.mode == "scene" and (state.effect is not None or state.scene_code is not None):
            resolved = (
                resolve_scene_code(
                    self.model,
                    state.scene_code,
                    preferred_key=state.effect,
                )
                if state.scene_code is not None
                else None
            )
            if resolved is not None:
                scene_name, scene = resolved
            elif state.effect is not None:
                scene_name = canonical_scene_key(self.model, state.effect)
                candidate = MODEL_SCENES.get(self.model, {}).get(scene_name)
                if candidate is None:
                    return False
                scene = candidate
            else:
                return False
            packets = build_native_scene_packets(self.model, scene)
            for packet in packets:
                await self.send_command(packet)
            self.is_on = True
            self.color_mode = ParsedMode.SCENE
            self.effect = scene_name
            self._scene_code = scene.code
            self.diy_code = None
            self.music_mode = self.video_mode = "off"
            return self.profile.state_readable and await self.refresh_state(expected_scene_code=scene.code) and complete
        if state.mode == "music" and state.music_mode in self.profile.music_modes:
            for packet, state_values in music_writes:
                await self.send_command(packet, state_values=state_values)
            return (
                self.profile.state_readable
                and await self.refresh_state(expected_music_mode=state.music_mode)
                and complete
            )
        if state.mode == "video" and state.video_mode in {"movie", "game"} and self.profile.supports_video_mode:
            for field, control in (
                ("full_screen", "capture_region"),
                ("saturation", "saturation"),
                ("sound_effects", "sound_effects"),
                ("sound_effects_softness", "sound_effects"),
            ):
                if (
                    state.video_restore_controls is None or control in state.video_restore_controls
                ) and control not in permitted:
                    complete = complete and getattr(self, f"video_{field}") == getattr(state, f"video_{field}")
            restored = frozenset(
                field
                for field, control in (
                    ("full_screen", "capture_region"),
                    ("saturation", "saturation"),
                    ("sound_effects", "sound_effects"),
                    ("sound_effects_softness", "sound_effects"),
                )
                if control in permitted
            )
            return (
                await apply_active_video_mode(
                    self,
                    mode=state.video_mode,
                    requested_values={field: getattr(state, f"video_{field}") for field in restored},
                )
                and complete
            )
        if state.mode != "colour":
            return False
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        # Durable recovery stores values, not their original observation provenance.
        self.install_static_color(rgb=state.rgb_color, kelvin=state.color_temp_kelvin)
        if state.color_temp_kelvin is not None:
            await self.send_command(build_color_temp(state.color_temp_kelvin, self.model))
        else:
            await self.send_command(build_color_rgb(*state.rgb_color, self.model))
        self.is_on = True
        self.brightness_pct = state.brightness_pct
        self._enter_static_mode()
        static_expectations: dict[str, Any] = {}
        if state.color_temp_kelvin is not None and self.profile.static_readback_kelvin:
            static_expectations["expected_color_temp_kelvin"] = state.color_temp_kelvin
        elif state.color_temp_kelvin is None and self.profile.static_readback_echoes_color:
            static_expectations["expected_rgb_color"] = state.rgb_color
        return (
            self.profile.state_readable
            and await self.refresh_state(**static_expectations)
            and self.active_mode == "colour"
            and complete
        )

    @callback
    def _note_identity(self, *, fw_version: str | None = None, hw_version: str | None = None) -> None:
        # Entities snapshot device_info at construction, before the first identity reply lands,
        # so a newly learned version must be pushed to the registry or the device page stays blank (#97).
        changed = False
        if fw_version is not None and fw_version != self.fw_version:
            self.fw_version, changed = fw_version, True
        if hw_version is not None and hw_version != self.hw_version:
            self.hw_version, changed = hw_version, True
        if not changed:
            return
        assert self.config_entry is not None
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier((DOMAIN, self.address), self.config_entry.entry_id)
        if device is not None:
            registry.async_update_device(device.id, sw_version=self.fw_version, hw_version=self.hw_version)

    @property
    def white_balance(self) -> tuple[int, int]:
        """The gain pair to write, filling an unknown axis with the app's own neutral.

        Both bytes go out together. The H6199 read-back populates both during startup; neutral is
        retained only for the pre-read window and for models on firmware that does not answer it.
        """
        reset_red, reset_blue = WHITE_BALANCE_RESET
        return (
            reset_red if self.white_balance_red is None else self.white_balance_red,
            reset_blue if self.white_balance_blue is None else self.white_balance_blue,
        )

    @property
    def scene_code(self) -> int | None:
        return self._scene_code if self.color_mode is ParsedMode.SCENE else None

    @property
    def unknown_scene_code(self) -> int | None:
        """The raw scene id when the device is running a scene this build cannot name.

        ``effect`` stays None for these, because Home Assistant rejects a value outside
        ``effect_list`` and we could not re-activate the scene anyway. Reporting the id keeps
        the state honest about the light running something.
        """
        if self.color_mode is ParsedMode.SCENE and self.effect is None:
            return self._scene_code
        return None

    @property
    def available(self) -> bool:
        """Whether the device is reachable: a live BLE link or a recent advertisement."""
        if self._client is not None and self._client.is_connected:
            return True
        return self._present

    async def _async_setup(self) -> None:
        """Register BLE presence tracking once, before the first refresh (HA idiom)."""
        self._present = bluetooth.async_address_present(self.hass, self.address, connectable=True)
        unsubs = (
            bluetooth.async_register_callback(
                self.hass,
                self._async_on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE,
            ),
            bluetooth.async_track_unavailable(self.hass, self._async_on_unavailable, self.address, connectable=True),
        )
        for unsub in unsubs:
            if self.config_entry is not None:
                self.config_entry.async_on_unload(unsub)

    @callback
    def _async_on_advertisement(
        self, _service_info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        self._set_present(True)

    @callback
    def _async_on_unavailable(self, _service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        self._set_present(False)

    @callback
    def _set_present(self, present: bool) -> None:
        if self._present != present:
            self._present = present
            self._log_availability_transition()
            self.async_update_listeners()

    def _log_availability_transition(self) -> None:
        if self.hass.is_stopping:
            return
        unavailable = cast(
            set[str],
            self.hass.data.setdefault(DOMAIN, {}).setdefault(AVAILABILITY_UNAVAILABLE_DATA_KEY, set()),
        )
        if self.available:
            if self.address in unavailable:
                _LOGGER.info("Govee %s is back online", self.model)
                unavailable.discard(self.address)
        elif self.address not in unavailable:
            _LOGGER.info("Govee %s is unavailable", self.model)
            unavailable.add(self.address)

    @callback
    def _handle_hass_stop(self, _event: Event) -> None:
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _async_update_data(self) -> dict[str, Any]:
        first_refresh = not self._first_refresh_done
        self._first_refresh_done = True
        if self.hass.is_stopping:
            return self._state_snapshot()
        if self.profile.state_readable:
            try:
                async with async_control_intent(self, ControlIntent.BACKGROUND, wait=False) as acquired:
                    if not acquired:
                        return self._state_snapshot()
                    previous_client = self._client
                    refreshed = await self.refresh_state(
                        refresh_all=True,
                        required_domains=self.profile.setup_required_read_domains,
                    )
                    client = self._client
                    if not refreshed or client is None:
                        if client is not None:
                            await self._disconnect_if_current_locked(client)
                        raise BleakError(f"State query failed for {self.address}")
                    if client is not previous_client:
                        await self._disconnect_if_current_locked(client)
            except BleakError as err:
                # ConfigEntryNotReady on first setup only; steady-state refreshes degrade silently
                # and presence-driven availability tracks the running state.
                self._log_availability_transition()
                if first_refresh:
                    raise UpdateFailed(f"{self.address} unreachable at setup") from err
                _LOGGER.debug("State refresh skipped for %s", self.address)
        elif first_refresh and not self._present:
            self._log_availability_transition()
            raise UpdateFailed(f"{self.address} not advertising at setup")
        return self._state_snapshot()

    def _state_snapshot(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _CORE_STATE_FIELDS}

    async def _ensure_connected(self) -> BleakClient:
        if self._client and self._client.is_connected:
            if not self._receive_is_stale():
                self._renew_foreground_lease()
                return self._client
            _LOGGER.debug("Reconnecting stale notification stream for %s", self.address)
        # Invalidate authorization before reconnect can yield; unrelated display identity stays cached.
        for condition in self.profile.video_firmware_conditions:
            setattr(self, condition.identity_field, None)
        if self._client and self._client.is_connected:
            await self._disconnect_locked()
        self._client = await async_establish_ble_connection(
            self.hass,
            self.address,
            resolver=self._device_resolver,
            establish=establish_connection,
            sleep=asyncio.sleep,
            disconnected_callback=self._disconnected_callback,
        )
        self._reset_disconnect_timer()
        if self.profile.requires_notifications:
            try:
                await self._start_notify()
                await self._send_identity_queries()
            except BleakError, ValueError:
                await self._disconnect_locked()
                raise
        self._log_availability_transition()
        return self._client

    def _renew_foreground_lease(self) -> None:
        if self._control_arbiter.current_task_intent is not ControlIntent.BACKGROUND:
            self._reset_disconnect_timer()

    def _reset_disconnect_timer(self) -> None:
        if self._cancel_disconnect:
            self._cancel_disconnect()
        self._disconnect_generation += 1
        generation = self._disconnect_generation

        @callback
        def _on_timeout(_now: datetime) -> None:
            self.hass.async_create_task(self._async_disconnect_on_timeout(generation))

        delay = self.profile.connection_idle_timeout
        self._cancel_disconnect = async_call_later(
            self.hass,
            DISCONNECT_DELAY if delay is None else delay,
            _on_timeout,
        )

    async def _async_disconnect_on_timeout(self, generation: int) -> None:
        if generation != self._disconnect_generation:
            return
        async with async_control_intent(self, ControlIntent.BACKGROUND, wait=False) as acquired:
            if not acquired:
                if generation == self._disconnect_generation:
                    self._reset_disconnect_timer()
                return
            if generation != self._disconnect_generation:
                return
            await self._disconnect_locked()

    @callback
    def _disconnected_callback(self, client: BleakClient) -> None:
        if self._client is not client or self._intentional_disconnect_client is client:
            return
        self._clear_client_state(client)
        self._log_availability_transition()
        self.async_update_listeners()

    def _clear_client_state(self, client: BleakClient | None) -> None:
        if self._client is not client:
            return
        self._client = None
        self._encryption.reset()
        self._notify_started_monotonic = None
        self._last_rx_monotonic = None
        self._expected_state.clear()
        self._stop_keep_alive()
        self._disconnect_generation += 1
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _start_notify(self) -> None:
        if not (self._client and self._client.is_connected):
            return
        await self._client.start_notify(READ_UUID, self._notify_callback)
        # The device answers the handshake on the notify characteristic, so this has to run
        # after start_notify.  A device that does not want encryption, or fails to negotiate,
        # leaves the session inactive and stays on the plaintext path.
        await self._encryption.async_negotiate(self._client)
        self._notify_started_monotonic = time.monotonic()
        self._last_rx_monotonic = None
        if self.profile.state_readable:
            self._start_keep_alive()

    def _receive_is_stale(self) -> bool:
        baseline = self._last_rx_monotonic
        if baseline is None:
            baseline = self._notify_started_monotonic
        return baseline is not None and time.monotonic() - baseline >= RX_STALE_TIMEOUT

    def _mark_received(self, domain: StatusDomain, *fields: str) -> None:
        self._domain_revisions[domain] = self._domain_revisions.get(domain, 0) + 1
        for field in fields:
            self._field_revisions[field] = self._field_revisions.get(field, 0) + 1
        self._revision_event.set()

    @property
    def _segment_group_count(self) -> int:
        return self.profile.segment_group_count

    def mark_segment_state_optimistic(
        self,
        *,
        colours: list[tuple[int, int, int]] | None = None,
        brightness: list[int] | None = None,
    ) -> None:
        if colours is not None:
            self.segment_colors = colours
            if self.rgb_color_source == "observed":
                self.rgb_color_source = "retained"
            if self.color_temp_kelvin_source == "observed":
                self.color_temp_kelvin_source = "retained"
        if brightness is not None:
            self.segment_brightness = brightness
        self.segment_state_source = "optimistic"
        self.segment_state_observed_at = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = None
        self._segment_query_brightness = None

    def mark_segment_state_restored(
        self,
        colours: list[tuple[int, int, int]],
        brightness: list[int],
    ) -> None:
        self.segment_colors = colours
        self.segment_brightness = brightness
        self.segment_state_source = "restored"
        self.segment_state_observed_at = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = None
        self._segment_query_brightness = None

    def _apply_segment_group(self, generated: Any) -> tuple[str, ...]:
        group = getattr(generated.body, "group", None)
        records = getattr(generated.body, "segments", None)
        count = getattr(generated.body, "num_segments", None)
        group_size = self.profile.segment_group_size
        if type(group) is not int or not 1 <= group <= self._segment_group_count:
            raise ValueError("invalid segment group for model")
        offset = (group - 1) * group_size
        expected_count = min(group_size, self.profile.segment_count - offset)
        if type(count) is not int or count != expected_count or not isinstance(records, list) or len(records) != count:
            raise ValueError("segment record count does not match model page")
        # Convert the entire page before touching an in-progress observation.
        try:
            page_colours = [(int(r.colour.red), int(r.colour.green), int(r.colour.blue)) for r in records]
            page_brightness = [int(r.brightness) for r in records]
        except (AttributeError, TypeError, ValueError) as err:
            raise ValueError("malformed segment record") from err
        colours = self._segment_query_colors
        brightness = self._segment_query_brightness
        if colours is None or brightness is None:
            colours = list(self.segment_colors)
            brightness = list(self.segment_brightness)
            self._segment_query_colors = colours
            self._segment_query_brightness = brightness
        colours[offset : offset + count] = page_colours
        brightness[offset : offset + count] = page_brightness
        self._segment_groups_observed.add(group)
        if len(self._segment_groups_observed) != self._segment_group_count:
            return ()
        self.segment_colors = colours
        self.segment_brightness = brightness
        self._segment_query_colors = None
        self._segment_query_brightness = None
        self._segment_groups_observed.clear()
        self.segment_state_source = "observed"
        self.segment_state_observed_at = datetime.now().astimezone().isoformat()
        observed = ["segment_colors", "segment_brightness"]
        # Direct static readback outranks rendered segments; a matching white point
        # can retain last-known Kelvin but never proves a fresh Kelvin measurement.
        if (
            self.color_mode is ParsedMode.COLOUR
            and len(set(self.segment_colors)) == 1
            and self.rgb_color_source != "observed"
            and self.color_temp_kelvin_source != "observed"
        ):
            rendered = self.segment_colors[0]
            kelvin = self.color_temp_kelvin
            if kelvin is not None and rendered != kelvin_to_rgb(kelvin):
                kelvin = None
            if self._accept_expected_values({"rgb_color": rendered, "color_temp_kelvin": kelvin}):
                self.rgb_color = rendered
                self.rgb_color_source = "segment"
                if kelvin is None:
                    self.color_temp_kelvin = None
                    self.color_temp_kelvin_source = "initial"
                observed.append("rgb_color")
        return tuple(observed)

    def _arm_expected(self, packet: bytes) -> None:
        expectations = expectations_from_packet(
            packet,
            self.model,
            static_echoes_color=self.profile.static_readback_echoes_color,
        )
        if "color_mode" in expectations:
            if expectations["color_mode"][0] is not ParsedMode.COLOUR:
                if self.rgb_color_source == "observed":
                    self.rgb_color_source = "retained"
                if self.color_temp_kelvin_source == "observed":
                    self.color_temp_kelvin_source = "retained"
            for field in _COLOR_EXPECTATION_FIELDS:
                self._expected_state.pop(field, None)
        self._arm_expected_values(expectations)

    def _arm_expected_values(self, expectations: dict[str, Any]) -> None:
        """Protect optimistic fields from reordered replies until their verification window ends."""
        deadline = time.monotonic() + EXPECTED_STATE_TTL
        for field, value in expectations.items():
            self._expected_state[field] = (value, deadline)

    def _accept_expected_values(self, values: dict[str, Any]) -> bool:
        """Accept a composite reply atomically; one stale sibling rejects the whole group."""
        return all(self._accept_expected(field, value) for field, value in values.items())

    def _accept_expected(self, field: str, value: Any) -> bool:
        """Consult the optimistic window for `field`.

        Returns True when the reply agrees or the deadline has passed; returns False to
        drop a stale reply that still disagrees in-window. Matching expectations remain
        authoritative until the deadline so a later reordered reply cannot overwrite them.
        """
        expectation = self._expected_state.get(field)
        if expectation is None:
            return True
        expected, deadline = expectation
        if time.monotonic() >= deadline:
            del self._expected_state[field]
            return True
        if value == expected:
            return True
        _LOGGER.debug("Ignoring stale %s for %s: %r (expecting %r)", field, self.address, value, expected)
        return False

    def _apply_color_mode_payload(
        self,
        generated: Any,
    ) -> tuple[str, ...]:
        parsed = parse_color_mode(generated, self.model)
        if parsed.mode is ParsedMode.DIY:
            mode_detail = parsed.diy_code
        elif parsed.mode is ParsedMode.COLOUR and self.profile.static_readback_echoes_color:
            mode_detail = parsed.multi_effect_flag
        else:
            mode_detail = None
        observed_color_mode = parsed.mode, mode_detail
        if not self._accept_expected("color_mode", observed_color_mode):
            return ()
        if parsed.mode is not ParsedMode.COLOUR or self.color_mode is not ParsedMode.COLOUR:
            # Direct authority belongs to one uninterrupted static-mode interval.
            # Keep the values as last-known knowledge, not current readback evidence.
            if self.rgb_color_source == "observed":
                self.rgb_color_source = "retained"
            if self.color_temp_kelvin_source == "observed":
                self.color_temp_kelvin_source = "retained"
        self.color_mode = parsed.mode
        # Track the device's scene independently from Home Assistant's configured effect-list projection.
        scene_effect = parsed.effect if parsed.effect in self.scene_name_set else None
        # A scene we cannot name still leaves the light running something, and effect has to stay
        # None because HA rejects one outside effect_list.
        unknown_scene_code = parsed.scene_code if scene_effect is None else None
        observed: list[str] = ["color_mode"]
        accept_parameters = True
        # Readback mirror of _enter_static_mode: committing one mode clears the others.
        if parsed.mode is ParsedMode.MUSIC:
            self._scene_code = None
            if parsed.music_mode is not None and self._accept_expected("music_mode", parsed.music_mode):
                self.music_mode = parsed.music_mode
                self.video_mode, self.effect = "off", None
                self.diy_code = None
                observed.append("music_mode")
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.VIDEO:
            self._scene_code = None
            if parsed.video_mode is not None and self._accept_expected("video_mode", parsed.video_mode):
                self.video_mode = parsed.video_mode
                self.music_mode, self.effect = "off", None
                self.diy_code = None
                observed.append("video_mode")
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.DIY:
            self._scene_code = None
            if self._accept_expected("effect", None):
                self.effect = None
                self.music_mode = self.video_mode = "off"
                self.diy_code = parsed.diy_code
                observed.extend(("effect", "diy_code"))
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.SCENE:
            values = {
                "effect": scene_effect,
                "scene_code": parsed.scene_code,
                "unknown_scene_code": unknown_scene_code,
            }
            if self._accept_expected_values(values):
                self.effect = scene_effect
                self._scene_code = parsed.scene_code
                self.music_mode, self.video_mode = "off", "off"
                self.diy_code = None
                observed.extend(values)
        elif parsed.mode is ParsedMode.COLOUR:
            self._scene_code = None
            if self._accept_expected("effect", None):
                self.effect, self.music_mode, self.video_mode = None, "off", "off"
                self.diy_code = None
                observed.append("effect")
        else:
            self._scene_code = None
            self.effect = None
            self.diy_code = None
            self.music_mode = self.video_mode = "off"
            observed.append("effect")
        if accept_parameters:
            if parsed.mode is ParsedMode.MUSIC and parsed.music_color is None:
                if self._accept_expected("music_color", None):
                    self.music_color = None
                    observed.append("music_color")
            for attr in _COLOR_MODE_FIELDS:
                if (value := getattr(parsed, attr)) is not None:
                    if self._accept_expected(attr, value):
                        setattr(self, attr, value)
                        observed.append(attr)
        if parsed.mode is ParsedMode.COLOUR:
            static_values: dict[str, Any] = {}
            if parsed.rgb_color is not None and self.profile.static_readback_echoes_color:
                static_values["rgb_color"] = parsed.rgb_color
            if parsed.color_temp_kelvin is not None and self.profile.static_readback_kelvin:
                static_values["color_temp_kelvin"] = parsed.color_temp_kelvin
            accepted_values = dict(static_values)
            if "rgb_color" in static_values and "color_temp_kelvin" not in static_values:
                kelvin = self.color_temp_kelvin
                if kelvin is None or static_values["rgb_color"] != kelvin_to_rgb(kelvin):
                    accepted_values["color_temp_kelvin"] = None
            if self._accept_expected_values(accepted_values):
                for attr, value in accepted_values.items():
                    setattr(self, attr, value)
                    setattr(self, f"{attr}_source", "observed" if attr in static_values else "initial")
                if (
                    "rgb_color" in static_values
                    and "color_temp_kelvin" not in static_values
                    and self.color_temp_kelvin_source == "observed"
                ):
                    self.color_temp_kelvin_source = "retained"
                observed.extend(static_values)
        return tuple(observed)

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        # None means the frame was the encryption handshake, or failed its tag check.
        if (frame := self._encryption.decode(bytes(data))) is None:
            return
        self._last_rx_monotonic = time.monotonic()
        if frame[:1] == b"\x33":
            command = parse_command_ack_result(frame, self.model)
            reason = "command_ack_parsed"
            if command.parsed is None:
                command = parse_command_result(frame, self.model)
                reason = "command_echo_parsed"
            outcome = "parsed" if command.parsed is not None else "rejected"
            if command.rejection is not None:
                reason = command.rejection.value
            self._record_packet(
                "rx",
                frame,
                outcome=outcome,
                reason=reason,
                parser=command.parser,
            )
            _LOGGER.debug(
                "rx %s command response parser=%s outcome=%s raw=%s",
                self.model,
                command.parser,
                outcome,
                frame.hex(),
            )
            return
        result = decode_status_frame_result(frame, self.model)
        decoded = result.parsed
        if decoded is None:
            reason = result.rejection.value if result.rejection is not None else "schema_rejected"
            self._record_packet(
                "rx",
                frame,
                outcome="rejected",
                reason=reason,
                parser=result.parser,
                domain=frame[1] if len(frame) > 1 and frame[0] == 0xAA else None,
            )
            _LOGGER.debug(
                "Rejected %s status frame parser=%s reason=%s raw=%s",
                self.model,
                result.parser,
                reason,
                frame.hex(),
            )
            return
        domain, payload = decoded.domain, decoded.payload
        generated = decoded.generated
        packet_entry = self._record_packet(
            "rx",
            frame,
            outcome="parsed",
            reason="status_parsed",
            parser=result.parser,
            domain=decoded.raw_domain,
        )
        _LOGGER.debug("rx %s domain=0x%02x payload=%s", self.model, decoded.raw_domain, payload.hex())
        try:
            observed: tuple[str, ...] = ()
            if domain is StatusDomain.POWER:
                value = bool(generated.body.is_on)
                if self._accept_expected("is_on", value):
                    self.is_on = value
                    observed = ("is_on",)
            elif domain is StatusDomain.BRIGHTNESS:
                brightness_value = (
                    int(generated.body.percent)
                    if self.profile.status_grammar == "H6199"
                    else int(generated.body.brightness_pct)
                )
                if self._accept_expected("brightness_pct", brightness_value):
                    self.brightness_pct = brightness_value
                    observed = ("brightness_pct",)
            elif domain is StatusDomain.COLOUR_MODE:
                if not self.profile.supports_color_mode_readback:
                    return
                observed = self._apply_color_mode_payload(generated)
            elif domain is StatusDomain.DISPLAY_SETTING:
                if generated.body.setting == 6 and self.profile.video_white_balance_representation == "scalar":
                    scalar_value = int(generated.body.payload.value)
                    if self._accept_expected("white_balance_scalar", scalar_value):
                        self.white_balance_scalar = scalar_value
                        observed = ("white_balance_scalar",)
                current_white_balance: tuple[int, int] | None
                if generated.body.setting == 0 and self.profile.video_white_balance_representation == "position":
                    red = int(generated.body.payload.current_red)
                    blue = int(generated.body.payload.current_blue)
                    current_white_balance = (red, blue)
                else:
                    current_white_balance = None
                if current_white_balance is not None:
                    red, blue = current_white_balance
                    values = {"white_balance_red": red, "white_balance_blue": blue}
                    if self._accept_expected_values(values):
                        self.white_balance_red, self.white_balance_blue = red, blue
                        observed = tuple(values)
                else:
                    blank_screen = bool(generated.body.payload.is_enabled) if generated.body.setting == 10 else None
                    if blank_screen is not None:
                        payload = generated.body.payload
                        self.blank_screen_detection = int(payload.detection)
                        self.blank_screen_low_brightness_duration_seconds = int(payload.low_brightness_duration_seconds)
                        self.blank_screen_same_tone_duration_seconds = int(payload.same_tone_duration_seconds)
                        if self._accept_expected("blank_screen", blank_screen):
                            self.blank_screen = blank_screen
                            observed = (
                                "blank_screen",
                                "blank_screen_detection",
                                "blank_screen_low_brightness_duration_seconds",
                                "blank_screen_same_tone_duration_seconds",
                            )
            elif domain is StatusDomain.RELATIVE_BRIGHTNESS:
                zones = self.profile.video_brightness_zones
                if generated.body.edge_count != len(zones):
                    raise ValueError("relative-brightness topology mismatch")
                edges = tuple(int(getattr(generated.body, f"{zone}_percent")) for zone in zones)
                aggregate = edges[0] if len(set(edges)) == 1 else None
                edge_values: dict[str, Any] = {
                    "relative_brightness": aggregate,
                    **{f"relative_brightness_{zone}": value for zone, value in zip(zones, edges, strict=True)},
                }
                if self._accept_expected_values(edge_values):
                    for field, value in edge_values.items():
                        setattr(self, field, value)
                    observed = tuple(edge_values)
            elif domain is StatusDomain.SEGMENTS:
                if not self.profile.supports_segments:
                    return
                observed = self._apply_segment_group(generated)
            elif domain is StatusDomain.FIRMWARE:
                self._note_identity(fw_version=generated.body.text or None)
            elif domain is StatusDomain.HARDWARE:
                self._note_identity(hw_version=generated.body.text or None)
            elif domain is StatusDomain.SUBORDINATE_20:
                self.subordinate_20_version = generated.body.text or None
            elif domain is StatusDomain.SUBORDINATE_21:
                self.subordinate_21_version = generated.body.text or None
            self._mark_received(domain, *observed)
            self.async_set_updated_data(self.data or {})
        except IndexError, ValueError:
            packet_entry["outcome"] = "rejected"
            packet_entry["reason"] = "semantic_rejected"
            _LOGGER.debug(
                "Rejected %s status frame parser=%s reason=semantic_rejected raw=%s",
                self.model,
                result.parser,
                frame.hex(),
            )

    async def _async_write_packet(
        self,
        client: BleakClient,
        packet: bytes,
        *,
        arm_expected: bool = False,
        before_write: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
    ) -> None:
        """Write on the caller's connection without changing its transaction policy."""
        wire_packet = packet
        if (transform := self.profile.outbound_transform) is not None:
            wire_packet = transform(packet)
            if not isinstance(wire_packet, bytes) or not wire_packet:
                raise ValueError("Outbound transform must return non-empty bytes")
        if before_write is not None:
            before_write()
        if state_values is not None:
            for field, value in state_values.items():
                setattr(self, field, value)
        if arm_expected:
            self._arm_expected(packet)
        if expected_values is not None:
            self._arm_expected_values(dict(expected_values))
        if arm_expected:
            self.control_write_attempts += 1
        encrypted_packet = self._encryption.encode(wire_packet)
        await client.write_gatt_char(WRITE_UUID, encrypted_packet, response=False)
        self._record_packet("tx", encrypted_packet, outcome="sent", reason="write_succeeded")

    async def _send_state_queries(
        self,
        *,
        query_power: bool = True,
        query_brightness: bool = True,
        query_color_mode: bool = True,
        query_white_balance: bool | None = None,
        query_blank_screen: bool | None = None,
        query_relative_brightness: bool | None = None,
        query_segments: bool | None = None,
    ) -> bool:
        client = self._client
        if client is None or not client.is_connected:
            return False
        try:
            queries: list[bytes] = []
            if query_power and self.profile.can_read(ReadDomain.POWER):
                queries.append(build_power_query(self.model))
            if query_brightness and self.profile.can_read(ReadDomain.BRIGHTNESS):
                queries.append(build_brightness_query(self.model))
            if query_color_mode and self.profile.supports_color_mode_readback:
                queries.append(build_colour_mode_query(self.model))
            full_query = query_power and query_brightness and query_color_mode
            if (
                self.profile.can_read(ReadDomain.DISPLAY_SETTING)
                and self.profile.supports_white_balance
                and (query_white_balance if query_white_balance is not None else full_query)
            ):
                queries.append(build_white_balance_query(self.model))
            if (
                self.profile.can_read(ReadDomain.DISPLAY_SETTING)
                and self.profile.supports_blank_screen
                and (query_blank_screen if query_blank_screen is not None else full_query)
            ):
                queries.append(build_blank_screen_query(self.model))
            if (
                self.profile.can_read(ReadDomain.RELATIVE_BRIGHTNESS)
                and self.profile.supports_relative_brightness
                and (query_relative_brightness if query_relative_brightness is not None else full_query)
            ):
                queries.append(build_relative_brightness_query(self.model))
            if (
                self.profile.can_read(ReadDomain.SEGMENTS)
                and self.profile.supports_segments
                and (query_segments if query_segments is not None else full_query)
            ):
                self._segment_groups_observed.clear()
                self._segment_query_colors = list(self.segment_colors)
                self._segment_query_brightness = list(self.segment_brightness)
                queries.extend(
                    build_segment_query(group, self.model) for group in range(1, self._segment_group_count + 1)
                )
            for query in queries:
                await self._async_write_packet(client, query)
            return True
        except BleakError:
            return False

    async def _send_identity_queries(self) -> None:
        """Query missing identity and invalid condition-bearing versions.

        Replies can be missed right after connect while notifications are starting, so the
        keep-alive loop retries unknown values up to ``IDENTITY_RETRY_TICKS``.
        """
        client = self._client
        if client is None or not client.is_connected:
            return
        candidates: list[tuple[bytes, str]] = []
        if self.profile.can_read(ReadDomain.HARDWARE):
            candidates.append((build_hardware_query(self.model), "hw_version"))
        if self.profile.can_read(ReadDomain.FIRMWARE):
            candidates.append((build_firmware_query(self.model), "fw_version"))
        if self.profile.can_read(ReadDomain.SUBORDINATE_20):
            candidates.append((build_h6199_subordinate_query(0x20), "subordinate_20_version"))
        if self.profile.can_read(ReadDomain.SUBORDINATE_21):
            candidates.append((build_h6199_subordinate_query(0x21), "subordinate_21_version"))
        queries = [q for q, field in candidates if self._identity_field_incomplete(field)]
        try:
            for query in queries:
                await self._async_write_packet(client, query)
        except BleakError:
            _LOGGER.debug("Identity query failed for %s", self.address)

    def _identity_field_incomplete(self, field: str) -> bool:
        value = getattr(self, field)
        return value is None or (
            any(condition.identity_field == field for condition in self.profile.video_firmware_conditions)
            and identity_version(value) is None
        )

    def _identity_incomplete(self) -> bool:
        return any(
            self._identity_field_incomplete(field)
            for domain, field in (
                (ReadDomain.FIRMWARE, "fw_version"),
                (ReadDomain.HARDWARE, "hw_version"),
                (ReadDomain.SUBORDINATE_20, "subordinate_20_version"),
                (ReadDomain.SUBORDINATE_21, "subordinate_21_version"),
            )
            if self.profile.can_read(domain)
        )

    async def _wait_for_revisions(
        self,
        field_baselines: Mapping[str, int],
        domain_baselines: Mapping[StatusDomain, int],
        deadline: float,
        *,
        expectations: Mapping[str, Any] | None = None,
    ) -> bool:
        def received() -> bool:
            # Segment RGB revisions update presentation, not direct static readback.
            fresh_fields = {
                field
                for field, baseline in field_baselines.items()
                if self._field_revisions.get(field, 0) > baseline
                and (
                    field not in {"rgb_color", "color_temp_kelvin"}
                    or (self.color_mode is ParsedMode.COLOUR and getattr(self, f"{field}_source") == "observed")
                )
            }
            if expectations is not None and any(
                field != "effect" and field in fresh_fields and getattr(self, field) != expected
                for field, expected in expectations.items()
            ):
                return True
            if field_baselines:
                return fresh_fields == field_baselines.keys()
            return all(
                self._domain_revisions.get(domain, 0) > baseline for domain, baseline in domain_baselines.items()
            )

        while not received():
            self._revision_event.clear()
            if received():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(self._revision_event.wait(), timeout=remaining)
            except TimeoutError:
                return False
        return True

    async def refresh_state(
        self,
        *,
        expected_effect: str | None = None,
        expected_scene_code: int | None = None,
        expected_on: bool | None = None,
        expected_brightness: int | None = None,
        expected_rgb_color: tuple[int, int, int] | None = None,
        expected_color_temp_kelvin: int | None = None,
        expected_music_mode: str | None = None,
        expected_music_sensitivity: int | None = None,
        expected_music_calm: bool | None = None,
        expected_music_color: tuple[int, int, int] | None = None,
        expected_music_auto_color: bool = False,
        expected_video_mode: str | None = None,
        expected_video_full_screen: bool | None = None,
        expected_video_saturation: int | None = None,
        expected_video_sound_effects: bool | None = None,
        expected_video_sound_effects_softness: int | None = None,
        expected_white_brightness: int | None = None,
        expected_white_balance: tuple[int, ...] | None = None,
        expected_blank_screen: bool | None = None,
        expected_relative_brightness: tuple[int, ...] | None = None,
        refresh_display_settings: bool | frozenset[str] = False,
        refresh_relative_brightness: bool = False,
        refresh_all: bool = False,
        required_domains: frozenset[ReadDomain] | None = None,
        timeout: float = 2.0,
    ) -> bool:
        if not self.profile.state_readable:
            return False
        if expected_rgb_color is not None and not self.profile.static_readback_echoes_color:
            return False
        if expected_color_temp_kelvin is not None and not self.profile.static_readback_kelvin:
            return False
        expectations: dict[str, Any] = {
            field: value
            for field, value in (
                ("effect", expected_effect),
                ("scene_code", expected_scene_code),
                ("is_on", expected_on),
                ("brightness_pct", expected_brightness),
                ("rgb_color", expected_rgb_color),
                ("color_temp_kelvin", expected_color_temp_kelvin),
                ("music_mode", expected_music_mode),
                ("music_sensitivity", expected_music_sensitivity),
                ("music_calm", expected_music_calm),
                ("music_color", expected_music_color),
                ("video_mode", expected_video_mode),
                ("video_full_screen", expected_video_full_screen),
                ("video_saturation", expected_video_saturation),
                ("video_sound_effects", expected_video_sound_effects),
                ("video_sound_effects_softness", expected_video_sound_effects_softness),
                ("white_brightness", expected_white_brightness),
            )
            if value is not None
        }
        if expected_music_auto_color:
            expectations["music_color"] = None
        if expected_rgb_color is not None or expected_color_temp_kelvin is not None:
            expectations["color_mode"] = ParsedMode.COLOUR
        if expected_white_balance is not None:
            fields = (
                ("white_balance_scalar",)
                if self.profile.video_white_balance_representation == "scalar"
                else ("white_balance_red", "white_balance_blue")
            )
            expectations.update(zip(fields, expected_white_balance, strict=True))
        if expected_blank_screen is not None:
            expectations["blank_screen"] = expected_blank_screen
        if expected_relative_brightness is not None:
            expectations["relative_brightness"] = (
                expected_relative_brightness[0] if len(set(expected_relative_brightness)) == 1 else None
            )
            expectations.update(
                (f"relative_brightness_{zone}", value)
                for zone, value in zip(self.profile.video_brightness_zones, expected_relative_brightness, strict=True)
            )
        color_expectations = (
            expected_rgb_color,
            expected_color_temp_kelvin,
            expected_effect,
            expected_scene_code,
            expected_music_mode,
            expected_music_sensitivity,
            expected_music_calm,
            expected_music_color,
            expected_video_mode,
            expected_video_full_screen,
            expected_video_saturation,
            expected_video_sound_effects,
            expected_video_sound_effects_softness,
            expected_white_brightness,
        )
        if not self.profile.supports_color_mode_readback and (
            expected_music_auto_color or any(value is not None for value in color_expectations)
        ):
            return False
        query_power = expected_on is not None
        query_brightness = expected_brightness is not None
        query_color = self.profile.supports_color_mode_readback and (
            expected_music_auto_color or any(value is not None for value in color_expectations)
        )
        display_settings = (
            frozenset({"white_balance", "blank_screen"})
            if refresh_display_settings is True
            else frozenset()
            if refresh_display_settings is False
            else refresh_display_settings
        )
        if not display_settings <= {"white_balance", "blank_screen"}:
            raise ValueError("unknown display setting requested for refresh")
        query_white_balance = expected_white_balance is not None or "white_balance" in display_settings
        query_blank_screen = expected_blank_screen is not None or "blank_screen" in display_settings
        query_relative_brightness = expected_relative_brightness is not None or refresh_relative_brightness
        if refresh_all:
            query_power = query_brightness = True
            query_color = self.profile.supports_color_mode_readback
            query_white_balance = self.profile.supports_white_balance
            query_blank_screen = self.profile.supports_blank_screen
            query_relative_brightness = self.profile.supports_relative_brightness
        if not any(
            (
                query_power,
                query_brightness,
                query_color,
                query_white_balance,
                query_blank_screen,
                query_relative_brightness,
            )
        ):
            query_power = True
            query_color = self.profile.supports_color_mode_readback
        queried_domains = {
            domain
            for domain, enabled in (
                (ReadDomain.POWER, query_power),
                (ReadDomain.BRIGHTNESS, query_brightness),
                (ReadDomain.COLOUR_MODE, query_color),
                (ReadDomain.DISPLAY_SETTING, query_white_balance or query_blank_screen),
                (ReadDomain.RELATIVE_BRIGHTNESS, query_relative_brightness),
            )
            if enabled and self.profile.can_read(domain)
        }
        awaited_domains = queried_domains if required_domains is None else queried_domains & required_domains
        initial_domain_baselines = {domain: self._domain_revisions.get(domain, 0) for domain in awaited_domains}
        current_intent = self._control_arbiter.current_task_intent
        intent = ControlIntent.USER if current_intent is None else current_intent
        async with async_control_intent(self, intent):
            async with self._lock:
                client = await self._ensure_connected()
            deadline = time.monotonic() + timeout
            for attempt in range(2):
                field_baselines = {field: self._field_revisions.get(field, 0) for field in expectations}
                if refresh_display_settings:
                    display_fields: list[str] = []
                    if self.profile.supports_white_balance and "white_balance" in display_settings:
                        display_fields.extend(
                            ("white_balance_scalar",)
                            if self.profile.video_white_balance_representation == "scalar"
                            else ("white_balance_red", "white_balance_blue")
                        )
                    if self.profile.supports_blank_screen and "blank_screen" in display_settings:
                        display_fields.extend(
                            (
                                "blank_screen",
                                "blank_screen_detection",
                                "blank_screen_low_brightness_duration_seconds",
                                "blank_screen_same_tone_duration_seconds",
                            )
                        )
                    field_baselines.update((field, self._field_revisions.get(field, 0)) for field in display_fields)
                if refresh_relative_brightness:
                    field_baselines.update(
                        (f"relative_brightness_{zone}", self._field_revisions.get(f"relative_brightness_{zone}", 0))
                        for zone in self.profile.video_brightness_zones
                    )
                domain_baselines = {domain: self._domain_revisions.get(domain, 0) for domain in awaited_domains}
                async with self._lock:
                    if self._client is not client:
                        return False
                    if query_white_balance or query_blank_screen or query_relative_brightness:
                        ok = await self._send_state_queries(
                            query_power=query_power,
                            query_brightness=query_brightness,
                            query_color_mode=query_color,
                            query_white_balance=query_white_balance,
                            query_blank_screen=query_blank_screen,
                            query_relative_brightness=query_relative_brightness,
                        )
                    else:
                        ok = await self._send_state_queries(
                            query_power=query_power,
                            query_brightness=query_brightness,
                            query_color_mode=query_color,
                        )
                if not ok:
                    await self._disconnect_if_current_locked(client)
                    return False
                attempt_deadline = (
                    deadline if attempt else time.monotonic() + max(0.0, (deadline - time.monotonic()) / 2)
                )
                if await self._wait_for_revisions(field_baselines, domain_baselines, attempt_deadline):
                    if not expectations or all(
                        getattr(self, field) == expected for field, expected in expectations.items()
                    ):
                        return True
                if time.monotonic() >= deadline:
                    break
            if any(
                self._domain_revisions.get(domain, 0) <= baseline
                for domain, baseline in initial_domain_baselines.items()
            ):
                await self._disconnect_if_current_locked(client)
            return False

    async def async_preview_preflight(self, *, timeout: float = 8.0) -> None:
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        deadline = asyncio.get_running_loop().time() + timeout

        async def disconnect_failed_client(client: BleakClient) -> None:
            try:
                async with asyncio.timeout_at(deadline):
                    await client.disconnect()
            except BleakError, TimeoutError:
                pass

        attempt_timeout = timeout / 2
        for attempt in range(2):
            cleanup_task: asyncio.Task[None] | None = None
            try:
                attempt_deadline = min(
                    deadline,
                    asyncio.get_running_loop().time() + attempt_timeout,
                )
                async with asyncio.timeout_at(attempt_deadline):
                    async with async_control_intent(self, ControlIntent.PREVIEW):
                        async with self._lock:
                            try:
                                await self._ensure_connected()
                            except BleakError, TimeoutError, asyncio.CancelledError:
                                failed_client = self._client
                                self._clear_client_state(failed_client)
                                if failed_client is not None and failed_client.is_connected:
                                    cleanup_task = self.hass.async_create_task(disconnect_failed_client(failed_client))
                                raise
                return
            except BleakError, TimeoutError:
                if cleanup_task is not None:
                    await asyncio.shield(cleanup_task)
                if attempt == 1 or asyncio.get_running_loop().time() >= deadline:
                    raise

    def admit_preview(self) -> PreviewAdmission:
        return self._control_arbiter.admit_preview()

    def invalidate_previews(self) -> None:
        self._control_arbiter.invalidate_previews()

    async def async_refresh_segments(self, *, timeout: float = 2.0) -> bool:
        if not self.profile.state_readable or not self.profile.supports_segments:
            return False
        async with async_control_intent(self, ControlIntent.USER):
            baseline = self._field_revisions.get("segment_colors", 0)
            async with self._lock:
                client = await self._ensure_connected()
                ok = await self._send_state_queries(
                    query_power=False,
                    query_brightness=False,
                    query_color_mode=False,
                    query_segments=True,
                )
            if not ok:
                return False
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._client is not client:
                    return False
                if self._field_revisions.get("segment_colors", 0) > baseline:
                    return True
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(min(0.05, remaining))
            return False

    async def async_preview_write(
        self,
        packet: bytes,
        *,
        before_write: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
    ) -> None:
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        async with async_control_intent(self, ControlIntent.PREVIEW):
            async with self._lock:
                client = self._client
                if client is None or not client.is_connected:
                    raise BleakError(f"Device {self.address} disconnected during preview")
                await self._async_write_packet(
                    client,
                    packet,
                    arm_expected=True,
                    before_write=before_write,
                    state_values=state_values,
                    expected_values=expected_values,
                )
                self._renew_foreground_lease()

    async def async_write_effect_sequence(
        self,
        packets: Sequence[bytes],
        *,
        intent: ControlIntent,
        before_write: Callable[[], Awaitable[None]] | None = None,
        write_guard: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
        attempt_started: Callable[[int], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        """Write one complete effect transaction, restarting from frame zero after reconnect."""
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        if not packets:
            raise ValueError("effect sequence must contain at least one packet")
        async with async_control_intent(self, intent):
            async with self._lock:
                for attempt in range(1, EFFECT_SEQUENCE_ATTEMPTS + 1):
                    try:
                        async with asyncio.timeout(EFFECT_SEQUENCE_CONNECT_TIMEOUT):
                            client = await self._ensure_connected()
                        if attempt_started is not None:
                            await attempt_started(attempt)
                        if before_write is not None:
                            await before_write()
                        for index, packet in enumerate(packets, start=1):
                            await self._async_write_packet(
                                client,
                                packet,
                                arm_expected=True,
                                before_write=write_guard,
                                state_values=state_values,
                                expected_values=expected_values,
                            )
                            self._renew_foreground_lease()
                            if progress is not None:
                                await progress(index)
                        return
                    except (BleakError, TimeoutError) as err:
                        await self._disconnect_locked()
                        if self.hass.is_stopping:
                            raise RuntimeError("Home Assistant is stopping") from err
                        if attempt == EFFECT_SEQUENCE_ATTEMPTS:
                            raise
                        error = str(err).lower()
                        if isinstance(err, TimeoutError) or "already shutdown" in error or "not found" in error:
                            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    async def async_observe_effect(
        self,
        expectations: Mapping[str, Any],
        *,
        timeout: float = 4.0,
    ) -> bool | None:
        if not self.profile.state_readable or not expectations:
            return None
        if ("rgb_color" in expectations and not self.profile.static_readback_echoes_color) or (
            "color_temp_kelvin" in expectations and not self.profile.static_readback_kelvin
        ):
            return None
        if {"rgb_color", "color_temp_kelvin"} & expectations.keys() and not self.profile.supports_color_mode_readback:
            return None
        expectations = dict(expectations)
        if {"rgb_color", "color_temp_kelvin"} & expectations.keys():
            expectations["color_mode"] = ParsedMode.COLOUR
        for field, mode in (
            ("diy_code", ParsedMode.DIY),
            ("scene_code", ParsedMode.SCENE),
            ("unknown_scene_code", ParsedMode.SCENE),
            ("music_mode", ParsedMode.MUSIC),
            ("video_mode", ParsedMode.VIDEO),
        ):
            if expectations.get(field) is not None:
                expectations["color_mode"] = mode
                break
        query_power = "is_on" in expectations
        query_brightness = "brightness_pct" in expectations
        query_color = bool(
            set(expectations).intersection(
                {
                    "color_mode",
                    "rgb_color",
                    "color_temp_kelvin",
                    "effect",
                    "scene_code",
                    "unknown_scene_code",
                    "diy_code",
                    "music_mode",
                    "music_sensitivity",
                    "music_calm",
                    "music_color",
                    "video_mode",
                    "video_full_screen",
                    "video_saturation",
                    "video_sound_effects",
                    "video_sound_effects_softness",
                    "white_brightness",
                }
            )
        )
        query_white_balance = bool(
            set(expectations).intersection({"white_balance_red", "white_balance_blue", "white_balance_scalar"})
        )
        query_blank_screen = "blank_screen" in expectations
        query_relative_brightness = bool(
            set(expectations).intersection(
                {
                    "relative_brightness",
                    "relative_brightness_left",
                    "relative_brightness_top",
                    "relative_brightness_right",
                    "relative_brightness_bottom",
                    "relative_brightness_strip_left",
                    "relative_brightness_strip_right",
                }
            )
        )
        current_intent = self._control_arbiter.current_task_intent
        intent = ControlIntent.PREVIEW if current_intent is None else current_intent
        async with async_control_intent(self, intent):
            async with self._lock:
                client = self._client
                if client is None or not client.is_connected:
                    return None
                field_baselines = {field: self._field_revisions.get(field, 0) for field in expectations}
                ok = await self._send_state_queries(
                    query_power=query_power,
                    query_brightness=query_brightness,
                    query_color_mode=query_color,
                    query_white_balance=query_white_balance,
                    query_blank_screen=query_blank_screen,
                    query_relative_brightness=query_relative_brightness,
                )
        if not ok or self._client is not client:
            return None
        if not await self._wait_for_revisions(
            field_baselines,
            {},
            time.monotonic() + timeout,
            expectations=expectations,
        ):
            return None
        # A fresh contradiction is a mismatch even if sibling fields never arrived.
        if any(
            field != "effect"
            and self._field_revisions.get(field, 0) > field_baselines[field]
            and (
                field not in {"rgb_color", "color_temp_kelvin"}
                or (self.color_mode is ParsedMode.COLOUR and getattr(self, f"{field}_source") == "observed")
            )
            and getattr(self, field) != expected
            for field, expected in expectations.items()
        ):
            return False
        scene_code = expectations.get("scene_code")
        if scene_code is not None and scene_code_is_ambiguous(self.model, scene_code):
            # Catalogue names are derived from this same selector, not independent readback.
            return None
        return all(getattr(self, field) == expected for field, expected in expectations.items())

    def _start_keep_alive(self) -> None:
        self._stop_keep_alive()
        self._identity_retries = 0
        self._keep_alive_task = self.hass.async_create_background_task(
            self._keep_alive_loop(), name=f"{DOMAIN} keep-alive {self.address}"
        )

    def _stop_keep_alive(self) -> None:
        if self._keep_alive_task and not self._keep_alive_task.done():
            if self._keep_alive_task is not asyncio.current_task():
                self._keep_alive_task.cancel()
            self._keep_alive_task = None

    async def _keep_alive_loop(self) -> None:
        try:
            while self._client and self._client.is_connected:
                await asyncio.sleep(KEEP_ALIVE_INTERVAL)
                if not (self._client and self._client.is_connected):
                    break
                if self._receive_is_stale():
                    _LOGGER.debug("Disconnecting unresponsive notification stream for %s", self.address)
                    client = self._client
                    self.hass.async_create_task(self._disconnect_if_current(client))
                    break
                self._keep_alive_ticks += 1
                async with async_control_intent(self, ControlIntent.BACKGROUND, wait=False) as acquired:
                    if not acquired:
                        continue
                    if self._identity_incomplete() and self._identity_retries < IDENTITY_RETRY_TICKS:
                        self._identity_retries += 1
                        async with self._lock:
                            await self._send_identity_queries()
                    full = self._keep_alive_ticks % STATE_QUERY_EVERY_N_KEEP_ALIVES == 0
                    async with self._lock:
                        client = self._client
                        ok = await self._send_state_queries(
                            query_power=True,
                            query_brightness=full,
                            query_color_mode=full and self.profile.supports_color_mode_readback,
                        )
                    if not ok:
                        if client is not None:
                            await self._disconnect_if_current(client)
                        break
        except asyncio.CancelledError:
            pass

    async def _disconnect_if_current(self, client: BleakClient) -> None:
        async with async_control_intent(
            self,
            ControlIntent.BACKGROUND,
            wait=False,
        ) as acquired:
            if acquired:
                await self._disconnect_if_current_locked(client)

    async def _disconnect_if_current_locked(self, client: BleakClient) -> None:
        if self._client is client:
            await self._disconnect_locked()

    async def send_command(
        self,
        packet: bytes,
        *,
        write_guard: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
    ) -> None:
        if self.hass.is_stopping:
            _LOGGER.debug("Ignoring command during shutdown for %s", self.address)
            return
        current_intent = self._control_arbiter.current_task_intent
        intent = ControlIntent.USER if current_intent is None else current_intent
        async with async_control_intent(self, intent):
            async with self._lock:
                for attempt in range(3):
                    try:
                        client = await self._ensure_connected()
                        await self._async_write_packet(
                            client, packet, arm_expected=True, before_write=write_guard, state_values=state_values
                        )
                        self._renew_foreground_lease()
                        return
                    except BleakError as err:
                        await self._disconnect_locked()
                        if attempt == 2:
                            _LOGGER.error("Failed to send to %s after 3 attempts", self.address)
                            raise
                        s = str(err).lower()
                        if "already shutdown" in s or "not found" in s:
                            await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    async def async_paint_segments(self, groups: list[SegmentColorGroup]) -> None:
        """Optimistically paint colour groups onto the segment slots.

        Each group pairs 1-based segment indices with an RGB colour. The device does not
        publish segment state after writes, so the complete segment query verifies the
        optimistic state without resending or rolling back a completed write.
        """
        resolved: list[SegmentColorGroup] = [(list(segments), rgb) for segments, rgb in groups]
        packets = build_segment_paint(resolved, self.model, profile=self.profile)
        previous = list(self.segment_colors)
        previous_source = self.segment_state_source
        previous_static_sources = self.rgb_color_source, self.color_temp_kelvin_source
        previous_static_revisions = {
            field: self._field_revisions.get(field, 0) for field in ("rgb_color", "color_temp_kelvin")
        }
        previous_observed_at = self.segment_state_observed_at
        previous_groups = set(self._segment_groups_observed)
        previous_query_colors = self._segment_query_colors
        previous_query_brightness = self._segment_query_brightness
        updated = list(previous)
        try:
            for segments, rgb in resolved:
                for segment in segments:
                    updated[segment - 1] = rgb
            self.mark_segment_state_optimistic(colours=updated)
            for packet in packets:
                await self.send_command(packet)
        except Exception:
            self.segment_colors = previous
            self.segment_state_source = previous_source
            if all(
                self._field_revisions.get(field, 0) == revision for field, revision in previous_static_revisions.items()
            ):
                self.rgb_color_source, self.color_temp_kelvin_source = previous_static_sources
            self.segment_state_observed_at = previous_observed_at
            self._segment_groups_observed = previous_groups
            self._segment_query_colors = previous_query_colors
            self._segment_query_brightness = previous_query_brightness
            raise
        self._enter_static_mode()
        await self.async_refresh_segments()
        self.async_set_updated_data(self.data or {})

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        segments = list(segments)
        value = max(0, min(100, brightness))
        packet = build_segment_brightness(segments, value, self.model, profile=self.profile)
        updated = list(self.segment_brightness)
        for segment in segments:
            updated[segment - 1] = value
        await self.send_command(packet)
        self.mark_segment_state_optimistic(brightness=updated)
        self._enter_static_mode()
        await self.async_refresh_segments()
        self.async_set_updated_data(self.data or {})

    def _record_packet(
        self,
        direction: str,
        data: bytes,
        *,
        outcome: str,
        reason: str,
        parser: str | None = None,
        domain: int | None = None,
    ) -> dict[str, Any]:
        if not data:
            return {}
        header = data[0]
        action = data[1] if len(data) > 1 else None
        entry = {
            "ts": datetime.now().isoformat(),
            "dir": direction,
            "header": f"0x{header:02x}",
            "action": f"0x{action:02x}" if action is not None else None,
            "domain": f"0x{domain:02x}" if domain is not None else None,
            "outcome": outcome,
            "reason": reason,
            "parser": parser,
            "raw": data[:PACKET_LOG_RAW_BYTES_LIMIT].hex(),
            "truncated": len(data) > PACKET_LOG_RAW_BYTES_LIMIT,
        }
        self.packet_log.append(entry)
        if len(self.packet_log) > PACKET_LOG_LIMIT:
            del self.packet_log[:-PACKET_LOG_LIMIT]
        return entry

    async def disconnect(
        self,
        *,
        intent: ControlIntent = ControlIntent.USER,
    ) -> None:
        async with async_control_intent(self, intent):
            await self._disconnect_locked()

    async def _disconnect_locked(self) -> None:
        client = self._client
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        self._intentional_disconnect_client = client
        try:
            if client and client.is_connected:
                await client.disconnect()
        except BleakError, TimeoutError:
            _LOGGER.debug("Error disconnecting from %s", self.address)
        finally:
            self._clear_client_state(client)
            if self._intentional_disconnect_client is client:
                self._intentional_disconnect_client = None


def clear_availability_log_state(hass: HomeAssistant, address: str) -> None:
    """Forget deduplication state when a config entry is removed."""
    unavailable = hass.data.get(DOMAIN, {}).get(AVAILABILITY_UNAVAILABLE_DATA_KEY)
    if isinstance(unavailable, set):
        unavailable.discard(address)
