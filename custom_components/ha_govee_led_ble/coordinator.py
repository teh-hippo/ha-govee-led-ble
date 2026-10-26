"""DataUpdateCoordinator for HA Govee LED BLE."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, nullcontext
from dataclasses import replace
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

from .advertisement import parse_govee_advertisement
from .ble_connection import (
    CONNECTION_SETUP_TIMEOUT,
    RETRY_BACKOFF_SECONDS,
    VALIDATION_DISCONNECT_TIMEOUT,
    async_clear_gatt_cache,
    async_establish_ble_connection,
    clear_stale_gatt_recovery,
    is_stale_gatt_error,
    mark_stale_gatt_recovery,
    stale_gatt_recovery_pending,
)
from .ble_device_resolver import BLEDeviceResolver
from .const import (
    CONNECTION_MODE_HOLD,
    CONNECTION_MODE_RELEASE,
    DOMAIN,
    ModelProfile,
    ReadDomain,
    SupportQuality,
    default_effect_categories,
    default_effect_families,
    device_profile,
    get_profile,
    model_from_ble_name,
    supported_effect_categories,
)
from .control_arbiter import BLEControlArbiter, ControlIntent, PreviewAdmission, async_control_intent
from .coordinator_dreamview import DreamviewClaimedError, _DreamviewMixin, is_dreamview_claimed
from .coordinator_expectations import expectations_from_packet
from .coordinator_h6102 import _H6102Mixin
from .coordinator_modes import PreModeSnapshot, _ActiveModeMixin
from .coordinator_notifications import _OPTIONAL_CONTROL_DOMAINS, _NotificationMixin
from .coordinator_recovery import _RecoveryMixin
from .coordinator_segments import _SegmentMixin
from .coordinator_status import (
    ParsedMode,
    StatusDomain,
)
from .effect_contracts import CapabilityState
from .effect_deployments import PriorControlState
from .generated_protocol_adapter import (
    BulkStatusCollector,
    build_black_border_query,
    build_blank_screen_query,
    build_brightness_query,
    build_colour_mode_query,
    build_configured_strings,
    build_configured_strings_query,
    build_firmware_query,
    build_hardware_query,
    build_physical_ic_count_query,
    build_power_on_behaviour,
    build_power_query,
    build_relative_brightness_query,
    build_segment_query,
    build_subordinate_query,
    build_white_balance_query,
    parse_command_result,
    require_profile_packet,
    upload_ack_mode,
    upload_ack_subtype,
)
from .govee_encryption import GoveeCryptoError
from .govee_encryption.session import GoveeEncryptionSession
from .h6099_controls import h6099_control_queries
from .h6102_capabilities import (
    H6102FirmwareSource,
    resolve_h6102_capabilities,
)
from .light_commands import (
    kelvin_companion_rgb,
    parse_static_write,
)
from .music_semantics import (
    capture_music_parameters,
    music_body_params_for_mode,
)
from .native_profile_controls import (
    ProfileWriter,
)
from .protocol_h6199 import H6199_NATIVE_CONTROLS, build_h6199_control, build_h6199_control_query
from .scenes import (
    scene_code_is_ambiguous,
)
from .transport import READ_UUID, WRITE_UUID
from .video_applicability import (
    h6199_camera_controls_state,
    identity_version,
    video_control_states,
    video_identity_fields,
    white_balance_readback_state,
)

EFFECT_SEQUENCE_ATTEMPTS = 3
UPLOAD_ACK_TIMEOUT = 2.0

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 15
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
RX_STALE_TIMEOUT = KEEP_ALIVE_INTERVAL * 4
IDENTITY_RETRY_TICKS = 6
IDENTITY_QUERY_TIMEOUT = 1.0
PACKET_LOG_LIMIT = 50
PACKET_LOG_RAW_BYTES_LIMIT = 512
AVAILABILITY_UNAVAILABLE_DATA_KEY = "availability_unavailable"
_CORE_STATE_FIELDS = (
    "is_on",
    "brightness_pct",
    "rgb_color",
    "color_temp_kelvin",
    "effect",
    "diy_code",
)
_WHITE_BALANCE_GAIN_FIELDS = (
    "white_balance_flag",
    "white_balance_red",
    "white_balance_blue",
    "white_balance_default_flag",
    "white_balance_default_red",
    "white_balance_default_blue",
)
_BLANK_SCREEN_POLICY_FIELDS = (
    "blank_screen_detection",
    "blank_screen_low_brightness_duration_seconds",
    "blank_screen_same_tone_duration_seconds",
)


class GoveeBLECoordinator(
    _DreamviewMixin, _ActiveModeMixin, _NotificationMixin, _RecoveryMixin, _H6102Mixin, _SegmentMixin
):
    """Manages BLE connection lifecycle for a Govee device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        model: str,
        *,
        configuration_url: str | None,
        connection_mode: str = "release",
        effect_families: frozenset[str] | None = None,
        effect_categories: frozenset[str] | None = None,
        prefix_effect_names: bool = False,
        always_include_custom_effects: bool = False,
        device_resolver: BLEDeviceResolver | None = None,
        h6102_firmware: str | None = None,
        h6102_firmware_source: H6102FirmwareSource | None = None,
        h6102_hardware: str | None = None,
        h6102_pact: str | None = None,
    ) -> None:
        profile = get_profile(model)
        if model == "H7020":
            profile = device_profile(model, None, None)
        resolution = resolve_h6102_capabilities(h6102_firmware, h6102_firmware_source) if model == "H6102" else None
        if resolution is not None:
            profile = resolution.profile
        super().__init__(
            hass,
            _LOGGER,
            name=f"Govee {model} ({address})",
            update_interval=timedelta(seconds=30) if profile.state_readable else None,
        )
        self.address, self.model, self.profile = address, model, profile
        self._init_h6102(
            resolution,
            firmware=h6102_firmware,
            firmware_source=h6102_firmware_source,
            hardware=h6102_hardware,
            pact=h6102_pact,
        )
        self._profile_generation = 0
        self._configuration_url = configuration_url
        self.effect_families = default_effect_families(model) if effect_families is None else effect_families
        self.effect_categories = (
            frozenset(default_effect_categories(model)) if effect_categories is None else effect_categories
        )
        self.prefix_effect_names = prefix_effect_names
        self.always_include_custom_effects = always_include_custom_effects
        self.connection_mode = (
            CONNECTION_MODE_HOLD if connection_mode == CONNECTION_MODE_HOLD else CONNECTION_MODE_RELEASE
        )
        self._device_resolver = BLEDeviceResolver() if device_resolver is None else device_resolver
        self._client: BleakClient | None = None
        self._encryption: GoveeEncryptionSession | None = None
        self._advertised_encryption = False
        self._advertised_plaintext = False
        self._connection_initializing = False
        self._notification_token: object | None = None
        self._confirmed_identity_fields: set[str] = set()
        self._observed_physical_ic_count: int | None = None
        self._physical_ic_count_confirmed = False
        self._authorization_generation = 0
        self._upload_ack: tuple[BleakClient, object | None, int, int, int | None, int, asyncio.Future[bool]] | None = (
            None
        )
        self._setting_ack: tuple[BleakClient, object | None, int, asyncio.Future[bool]] | None = None
        self._lock = asyncio.Lock()
        self._control_arbiter = BLEControlArbiter()
        self._control_lock = self._control_arbiter
        self._cancel_disconnect: CALLBACK_TYPE | None = None
        self._disconnect_generation = 0
        self._intentional_disconnect_client: BleakClient | None = None
        self.fresh_service_discovery_forced = False
        self.last_connected_at: str | None = None
        self.last_disconnected_at: str | None = None
        self.last_failure_type: str | None = None
        self._keep_alive_task: asyncio.Task[None] | None = None
        self._keep_alive_ticks = 0
        self._identity_retries = 0
        self.is_on = False
        self.brightness_pct = 100
        self.rgb_color: tuple[int, int, int] = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self._pending_kelvin: int | None = None
        self._static_rgb_known = False
        self.static_gradual: bool | None = None
        self.rgb_color_source = self.color_temp_kelvin_source = "initial"
        self.effect: str | None = None
        # Device identity from the aa 06/aa 07 handshake replies; None until first read.
        self.fw_version: str | None = None
        self.hw_version: str | None = None
        self.subordinate_20_version: str | None = None
        self.subordinate_21_version: str | None = None
        self.pact_type: int | None = None
        self.pact_code: int | None = None
        self.boolean_control_state: dict[str, bool] = {}
        self.power_on_behaviour: str | None = None
        self._bulk_collector: BulkStatusCollector | None = None
        self._bulk_query_deadline: float | None = None
        self._bulk_query_incomplete = False
        self.configured_strings: int | None = None
        self._configured_strings_confirmed = False
        self._mask_transaction: tuple[asyncio.Task[Any] | None, object | None, int] | None = None
        self._segment_query_generation: int | None = None
        self.installation_direction: int | None = None
        self.camera_health = "unknown"
        self.strip_direction: int | None = None
        self.camera_position: int | None = None
        self.gradient: int | None = None
        self.camera_status = "unknown"
        self.music_mode = "off"
        self.video_mode = "off"
        self.diy_code: int | None = None
        self.color_mode: ParsedMode | None = None
        self._scene_code: int | None = None
        self._pre_mode_snapshot = PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
        self.segment_colors: list[tuple[int, int, int]] = [self.rgb_color] * profile.segment_count
        self.segment_brightness: list[int] = [100] * profile.segment_count
        self.segment_brightness_readable = False
        self.segment_state_source = "initial"
        self.segment_state_observed_at: str | None = None
        self._segment_groups_observed: set[int] = set()
        self._segment_query_colors: list[tuple[int, int, int]] | None = None
        self._segment_query_brightness: list[int] | None = None
        self._segment_query_incomplete = False
        self.video_saturation = self.white_brightness = 100
        self.music_sensitivity = 99
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 100
        self.video_parameters: dict[str, Any] | None = None
        self.music_color: tuple[int, int, int] | None = None
        # H6199 display settings and edge brightness. None means the first read has not landed.
        self.white_balance_red: int | None = None
        self.control_write_attempts = 0
        self._static_write_attempts = 0
        self.white_balance_blue: int | None = None
        self.white_balance_flag: int | None = None
        self.white_balance_default_flag: int | None = None
        self.white_balance_default_red: int | None = None
        self.white_balance_default_blue: int | None = None
        self.white_balance_scalar: int | None = None
        self.relative_brightness: int | None = None
        self.relative_brightness_left: int | None = None
        self.relative_brightness_top: int | None = None
        self.relative_brightness_right: int | None = None
        self.relative_brightness_bottom: int | None = None
        self.relative_brightness_strip_left: int | None = None
        self.relative_brightness_strip_right: int | None = None
        self.blank_screen: bool | None = None
        self.black_border: bool | None = None
        self.blank_screen_detection: int | None = None
        self.blank_screen_low_brightness_duration_seconds: int | None = None
        self.blank_screen_same_tone_duration_seconds: int | None = None
        self._blank_screen_notification_revision = 0
        self.music_separation_point = 1
        self.music_separation_gradient = True
        self.music_hopping_brightness = 50
        self.music_piano_key_count = 15
        self.music_fountain_direction = "clockwise"
        self.music_daynight_segments = 1
        self.music_daynight_speed = 10
        self.music_daynight_gradient = False
        self._initialized_music_parameters: set[str] = set()
        for variant in profile.music_variants:
            for spec in music_body_params_for_mode(variant.mode_code, profile):
                setattr(self, spec.key, spec.default)
                if not profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) or not (
                    variant.requires_physical_ic_count or spec.requires_physical_ic_count
                ):
                    self._initialized_music_parameters.add(spec.key)
            for spec in variant.selector_parameters:
                setattr(self, spec.key, None)
        self.packet_log: list[dict[str, Any]] = []
        self._expected_state: dict[str, tuple[Any, float]] = {}
        self._notify_started_monotonic: float | None = None
        self._last_rx_monotonic: float | None = None
        self._domain_revisions: dict[StatusDomain, int] = {}
        self._field_revisions: dict[str, int] = {}
        self._field_received_at: dict[str, float] = {}
        self._domain_received_at: dict[StatusDomain, float] = {}
        self._revision_event = asyncio.Event()
        # Successful polling survives intentional release independently of advertisement presence.
        self._present = False
        self._state_read_available = False
        self._first_refresh_done = False
        self._model_reload_scheduled = False
        self._cancel_hass_stop: CALLBACK_TYPE | None = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop
        )
        self._init_dreamview()
        self._apply_h6102_context(firmware=h6102_firmware, firmware_source=h6102_firmware_source, pact=h6102_pact)
        self._resolve_device_profile()

    @property
    def configuration_url(self) -> str | None:
        return self._configuration_url if supported_effect_categories(self.model, profile=self.profile) else None

    @property
    def device_info(self) -> dr.DeviceInfo:
        # No `connections`: the BLE MAC is PII and must not surface in the device UI (OD1).
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=f"Govee {self.model}",
            manufacturer="Govee",
            model=f"{self.model} (Experimental)"
            if self.profile.support_quality is SupportQuality.EXPERIMENTAL
            else self.model,
            model_id=self.model,
            configuration_url=self.configuration_url,
            sw_version=self.fw_version,
            hw_version=self.hw_version,
        )

    def capture_effect_control_state(self) -> PriorControlState:
        zone_flags = {
            name: value
            for name, value in self.boolean_control_state.items()
            if name in {"panel_enabled", "ring_enabled"}
            and self._notify_started_monotonic is not None
            and self._field_received_at.get(f"boolean_{name}", -1) >= self._notify_started_monotonic
        }
        # active_mode hides the resident mode while powered off and maps unknown to colour.
        mode = (
            "unknown"
            if self.color_mode is ParsedMode.UNKNOWN
            else "custom"
            if self.diy_code is not None
            else "scene"
            if self.effect is not None or self.scene_code is not None
            else "music"
            if self.color_mode is ParsedMode.MUSIC or self.music_mode not in (None, "off")
            else "video"
            if self.video_mode not in (None, "off")
            else "colour"
        )
        return PriorControlState(
            mode=mode,
            is_on=self.is_on,
            brightness_pct=self.brightness_pct,
            rgb_color=self.rgb_color,
            color_temp_kelvin=self.color_temp_kelvin,
            static_rgb_known=self._static_rgb_known and self.segment_state_source == "observed",
            static_gradual=self.static_gradual if self.color_mode is ParsedMode.COLOUR else None,
            panel_enabled=zone_flags.get("panel_enabled"),
            ring_enabled=zone_flags.get("ring_enabled"),
            segment_colors=tuple(self.segment_colors) if self.segment_state_source == "observed" else None,
            segment_brightness=tuple(self.segment_brightness)
            if self.segment_state_source == "observed" and self.segment_brightness_readable
            else None,
            effect=self.effect,
            scene_code=self.scene_code,
            diy_code=self.diy_code,
            music_mode=self.music_mode,
            music_model=self.model,
            music_parameters=capture_music_parameters(self, self.profile, self.music_mode),
            music_palette=self.music_palette,
            music_body=self.music_body,
            video_mode=self.video_mode,
            video_parameters=dict(self.video_parameters) if self.video_parameters is not None else None,
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
            white_balance_flag=self.white_balance_flag,
            white_balance_default_flag=self.white_balance_default_flag,
            white_balance_default_red=self.white_balance_default_red,
            white_balance_default_blue=self.white_balance_default_blue,
            white_balance_scalar=self.white_balance_scalar,
            relative_brightness=self.relative_brightness,
            relative_brightness_left=self.relative_brightness_left,
            relative_brightness_top=self.relative_brightness_top,
            relative_brightness_right=self.relative_brightness_right,
            relative_brightness_bottom=self.relative_brightness_bottom,
            relative_brightness_strip_left=self.relative_brightness_strip_left,
            relative_brightness_strip_right=self.relative_brightness_strip_right,
            blank_screen=self.blank_screen,
            black_border=self.black_border,
            blank_screen_detection=self.blank_screen_detection,
            blank_screen_low_brightness_duration_seconds=self.blank_screen_low_brightness_duration_seconds,
            blank_screen_same_tone_duration_seconds=self.blank_screen_same_tone_duration_seconds,
        )

    @callback
    def _note_identity(self, *, fw_version: str | None = None, hw_version: str | None = None) -> None:
        # Entities snapshot device_info at construction, before the first identity reply lands.
        authorization_fields = self._authorization_identity_fields()
        changed_fields: set[str] = set()
        if fw_version is not None and identity_version(fw_version) is not None and fw_version != self.fw_version:
            self.fw_version = fw_version
            changed_fields.add("fw_version")
            self._forget_configured_identity("fw_version")
        if hw_version is not None and identity_version(hw_version) is not None and hw_version != self.hw_version:
            self.hw_version = hw_version
            changed_fields.add("hw_version")
            self._forget_configured_identity("hw_version")
        if changed_fields:
            if changed_fields & authorization_fields:
                self._authorization_generation += 1
            if self.profile.profile_identity_fields:
                self._resolve_device_profile()
            if self.config_entry is not None:
                registry = dr.async_get(self.hass)
                device = registry.async_get_device_by_identifier((DOMAIN, self.address), self.config_entry.entry_id)
                if device is not None:
                    registry.async_update_device(device.id, sw_version=self.fw_version, hw_version=self.hw_version)

    @callback
    def _observe_identity_field(self, field: str, value: str | None) -> bool:
        """Cache a valid identity observation and confirm it for this notification session."""
        confirmed = field in self._confirmed_identity_fields
        parseable = identity_version(value) is not None
        current_connection = self._client is not None and self._client.is_connected
        if field in self._authorization_identity_fields():
            if parseable and current_connection:
                self._confirmed_identity_fields.add(field)
            else:
                self._confirmed_identity_fields.discard(field)
        if confirmed != (field in self._confirmed_identity_fields):
            self._authorization_generation += 1
        if not parseable or value is None:
            return False
        previous = getattr(self, field)
        if field == "fw_version":
            self._note_identity(fw_version=value)
        elif field == "hw_version":
            self._note_identity(hw_version=value)
        elif previous != value:
            setattr(self, field, value)
            if field in self._authorization_identity_fields():
                self._authorization_generation += 1
        return bool(previous != value)

    def identity_fields_confirmed(self, fields: frozenset[str] | None = None) -> bool:
        """Return whether required condition identity was observed on this connection."""
        required = self._authorization_identity_fields() if fields is None else fields
        return required <= self._confirmed_identity_fields

    def _sync_device_configuration_url(self) -> None:
        """Push support presentation and Studio access after profile resolution."""
        if self.config_entry is None:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier((DOMAIN, self.address), self.config_entry.entry_id)
        if device is not None:
            registry.async_update_device(
                device.id,
                model=self.device_info["model"],
                model_id=self.model,
                configuration_url=self.configuration_url,
            )

    @property
    def white_balance(self) -> tuple[int, int] | None:
        """Retained gains only; unknown state is not the calibration-table neutral."""
        if self.white_balance_red is None or self.white_balance_blue is None:
            return None
        return self.white_balance_red, self.white_balance_blue

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
        """Reachability from a live link, advertisements or the latest validated state poll."""
        if self._client is not None and self._client.is_connected:
            return True
        return self._present or (self.profile.state_readable and self._state_read_available)

    async def _async_setup(self) -> None:
        """Register BLE presence tracking once, before the first refresh (HA idiom)."""
        self._present = bluetooth.async_address_present(self.hass, self.address, connectable=True)
        self._note_advertisement(bluetooth.async_last_service_info(self.hass, self.address, connectable=True))
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
        previous_pact = self.pact_type, self.pact_code
        was_present = self._present
        self._note_advertisement(_service_info)
        self._set_present(True)
        if was_present and previous_pact != (self.pact_type, self.pact_code):
            self.async_update_listeners()

    def _note_advertisement(self, service_info: bluetooth.BluetoothServiceInfoBleak | None) -> None:
        if service_info is None:
            return
        name = getattr(service_info, "name", None)
        advertised_model = model_from_ble_name(name) if isinstance(name, str) else None
        if advertised_model is not None and advertised_model != self.model:
            if (
                not self._model_reload_scheduled
                and self.config_entry is not None
                and self.hass.config_entries.async_get_entry(self.config_entry.entry_id) is not None
            ):
                self._model_reload_scheduled = True
                self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            return
        if isinstance(service_info.manufacturer_data, Mapping):
            advertisement = parse_govee_advertisement(service_info.manufacturer_data)
            if advertisement is not None:
                pact = advertisement.pact_type, advertisement.pact_code
                if pact != (self.pact_type, self.pact_code):
                    self.pact_type, self.pact_code = pact
                    self._authorization_generation += 1
                self._resolve_device_profile()
                if advertisement.supports_encryption:
                    self._advertised_encryption = True
                    if self._encryption is not None and self._encryption.version == 0:
                        self._encryption.reset()
                else:
                    self._advertised_plaintext = True

    def _resolve_device_profile(self) -> None:
        declared = get_profile(self.model)
        if (
            not declared.profile_identity_fields
            and not declared.profile_pact_dependent
            and declared.video_revision_policy is None
            and not declared.configured_string_counts
        ):
            return
        if self.model == "H6102":
            profile, context_changed = self._resolve_h6102_profile()
        else:
            context_changed = False
            profile = device_profile(
                self.model, self.pact_type, self.pact_code, firmware=self.fw_version, hardware=self.hw_version
            )
            if (
                self._observed_physical_ic_count is not None
                and profile.can_read(ReadDomain.PHYSICAL_IC_COUNT)
                and profile.physical_ic_count != self._observed_physical_ic_count
            ):
                profile = replace(profile, physical_ic_count=self._observed_physical_ic_count)
            elif (
                profile is get_profile(self.model)
                and profile.physical_ic_count is None
                and self.profile.physical_ic_count is not None
            ):
                profile = replace(profile, physical_ic_count=self.profile.physical_ic_count)
            if profile.configured_string_counts and self.configured_strings in profile.configured_string_counts:
                bulbs = self.configured_strings * profile.bulbs_per_string
                profile = replace(profile, segment_count=bulbs, whole_device_mask=(1 << bulbs) - 1)
        if profile == self.profile:
            if context_changed:
                self._profile_generation += 1
                self._expected_state.clear()
            return
        self.profile = profile
        for variant in profile.music_variants:
            for spec in variant.selector_parameters:
                setattr(self, spec.key, None)
        self._configured_strings_confirmed = False
        self._segment_query_generation = None
        self.boolean_control_state = {
            key: value for key, value in self.boolean_control_state.items() if key in profile.boolean_controls
        }
        self._profile_generation += 1
        self._expected_state.clear()
        self._sync_device_configuration_url()
        if self.model not in {"H60A1", "H60A6"}:
            self.brightness_pct = 100
        self.color_mode = None
        self.effect = self.diy_code = self._scene_code = None
        self.music_mode = self.video_mode = "off"
        self.music_sensitivity = 99
        self.music_color = self._music_palette = self._music_body = None
        self.music_calm = False
        self.video_saturation = self.video_sound_effects_softness = 100
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_parameters = None
        self.rgb_color_source = self.color_temp_kelvin_source = "initial"
        self.color_temp_kelvin = None
        self.static_gradual = None
        self._static_rgb_known = False
        self.segment_colors = [(255, 255, 255)] * profile.segment_count
        self.segment_brightness = [100] * profile.segment_count
        self.segment_brightness_readable = False
        self.segment_state_source = "initial"
        self.segment_state_observed_at = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = self._segment_query_brightness = None
        for field in vars(self):
            if field.startswith(("white_balance_", "relative_brightness", "blank_screen")):
                setattr(self, field, None)

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
        self._cancel_hass_stop = None
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def async_shutdown(self) -> None:
        """Release entry-owned BLE work after unload or failed setup."""
        await super().async_shutdown()
        if self._cancel_hass_stop is not None:
            self._cancel_hass_stop()
            self._cancel_hass_stop = None
        self._stop_keep_alive()
        if self._cancel_disconnect is not None:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        try:
            async with asyncio.timeout(VALIDATION_DISCONNECT_TIMEOUT):
                await self.disconnect()
        except TimeoutError:
            _LOGGER.warning("Timed out cleaning up the Govee %s connection", self.model)

    async def _async_update_data(self) -> dict[str, Any]:
        first_refresh = not self._first_refresh_done
        self._first_refresh_done = True
        if self.hass.is_stopping:
            return self._state_snapshot()
        if self.profile.state_readable:
            if (
                self.connection_mode == CONNECTION_MODE_HOLD
                and not first_refresh
                and self._client is not None
                and self._client.is_connected
                and (self._encryption is None or self._encryption.ready)
                and not self._receive_is_stale()
                and not self._segment_query_incomplete
                and not self._bulk_query_incomplete
                and not is_dreamview_claimed(
                    self.hass, self.config_entry.entry_id if self.config_entry is not None else None, self
                )
            ):
                return self._state_snapshot()
            try:
                self._require_not_dreamview_claimed()
                async with async_control_intent(self, ControlIntent.BACKGROUND, wait=False) as acquired:
                    if not acquired:
                        return self._state_snapshot()
                    previous_client = self._client
                    read_succeeded = False
                    try:
                        for _ in range(2):
                            generation = self._profile_generation
                            authorization_generation = self._authorization_generation
                            refreshed = await self.refresh_state(
                                refresh_all=True,
                                required_domains=self.profile.setup_required_read_domains,
                            )
                            if generation == self._profile_generation and (
                                refreshed
                                or authorization_generation == self._authorization_generation
                                or self._client is None
                            ):
                                break
                        else:
                            refreshed = False
                        client = self._client
                        if not refreshed or client is None:
                            if client is not None:
                                await self._disconnect_if_current_locked(client)
                            raise BleakError(f"State query failed for {self.address}")
                        read_succeeded = True
                    finally:
                        self._state_read_available = read_succeeded
                    if client is not previous_client and self.connection_mode != CONNECTION_MODE_HOLD:
                        await self._disconnect_if_current_locked(client)
            except BleakError as err:
                # Missing state revokes read-based reachability, not independent advertisement evidence.
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

    def _require_not_shutdown(self) -> None:
        if self._shutdown_requested:
            raise BleakError("Govee coordinator has been shut down")

    async def _ensure_connected(self) -> BleakClient:
        self._require_not_shutdown()
        try:
            self._require_not_dreamview_claimed()
        except BleakError:
            if self._client and self._client.is_connected:
                await self._disconnect_locked()
            raise
        if self._connection_initializing:
            raise GoveeCryptoError("connection_setup_in_progress")
        if self._client and self._client.is_connected:
            if (
                (self._encryption is None or self._encryption.ready)
                and not self._receive_is_stale()
                and not self._segment_query_incomplete
                and not self._bulk_query_incomplete
            ):
                self._renew_foreground_lease()
                return self._client
            _LOGGER.debug("Reconnecting stale notification stream for %s", self.address)
        # Cached identity remains presentation data; only current-connection confirmation is revoked.
        self._confirmed_identity_fields.clear()
        self._physical_ic_count_confirmed = False
        self._authorization_generation += 1
        self._music_palette = self._music_body = None
        self.video_parameters = None
        self._configured_strings_confirmed = False
        if self.profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) and get_profile(self.model).physical_ic_count is None:
            self._observed_physical_ic_count = None
            self.profile = replace(self.profile, physical_ic_count=None)
        if self._client and self._client.is_connected:
            await self._disconnect_locked()
        elif self._client is not None:
            self._clear_client_state(self._client)
        self._require_not_shutdown()
        self._require_not_dreamview_claimed()
        force_fresh_services = self.fresh_services_required
        self._connection_initializing = True
        if self._encryption is None:
            self._encryption = GoveeEncryptionSession()
        self._encryption.reset()
        try:
            self._client = client = await async_establish_ble_connection(
                self.hass,
                self.address,
                resolver=self._device_resolver,
                establish=establish_connection,
                sleep=asyncio.sleep,
                disconnected_callback=self._disconnected_callback,
                use_services_cache=not force_fresh_services,
            )
            self._require_not_shutdown()
            self._require_not_dreamview_claimed()
            self._reset_disconnect_timer()
            await self._encryption.async_select(
                client,
                advertised=self._advertised_encryption,
                plaintext_evidence=self._advertised_plaintext and not self._advertised_encryption,
            )
            self._require_not_shutdown()
            self._require_not_dreamview_claimed()
            if self._client is not client or not client.is_connected:
                raise GoveeCryptoError("disconnected_during_selection")
            if self.profile.requires_notifications or self._encryption.version:
                await self._start_notify()
                self._require_not_shutdown()
                self._require_not_dreamview_claimed()
            await self._encryption.async_negotiate(client)
            self._require_not_shutdown()
            self._require_not_dreamview_claimed()
            if self._client is not client or not client.is_connected:
                raise GoveeCryptoError("disconnected_during_setup")
            if self.profile.requires_notifications:
                identity_baselines = {
                    domain: self._domain_revisions.get(domain, 0)
                    for domain, field in (
                        (ReadDomain.FIRMWARE, "fw_version"),
                        (ReadDomain.HARDWARE, "hw_version"),
                        (ReadDomain.SUBORDINATE_20, "subordinate_20_version"),
                        (ReadDomain.SUBORDINATE_21, "subordinate_21_version"),
                    )
                    if field in self._authorization_identity_fields() and self.profile.can_read(domain)
                }
                await self._send_identity_queries()
                self._require_not_shutdown()
                self._require_not_dreamview_claimed()
                # Reconnect invalidates authorization. Let real notifications requalify
                # guards before returning, but missing identity must not fail basic setup.
                await self._wait_for_revisions({}, identity_baselines, time.monotonic() + IDENTITY_QUERY_TIMEOUT)
                self._require_not_shutdown()
                self._require_not_dreamview_claimed()
                if self.profile.configured_string_counts:
                    await self._read_configured_strings(client, deadline=time.monotonic() + IDENTITY_QUERY_TIMEOUT)
                    self._require_not_shutdown()
                    self._require_not_dreamview_claimed()
            if self._client is not client or not client.is_connected or not self._encryption.ready:
                raise GoveeCryptoError("disconnected_during_setup")
            if self.profile.state_readable and self._notify_started_monotonic is not None:
                self._start_keep_alive()
        except BaseException as err:
            stale_gatt = False if isinstance(err, DreamviewClaimedError) else self._record_ble_failure(err)
            await self._disconnect_locked(clear_cache=stale_gatt)
            if (
                isinstance(err, Exception)
                and self._encryption.version
                and not isinstance(err, (GoveeCryptoError, DreamviewClaimedError))
            ):
                raise GoveeCryptoError("encrypted_setup_failed") from None
            raise
        finally:
            self._connection_initializing = False
        clear_stale_gatt_recovery(self.hass, self.address)
        self.fresh_service_discovery_forced = force_fresh_services
        self.last_connected_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._log_availability_transition()
        return client

    @property
    def fresh_services_required(self) -> bool:
        """Return whether the next connection must bypass cached GATT services."""
        return stale_gatt_recovery_pending(self.hass, self.address)

    def _record_ble_failure(self, err: BaseException) -> bool:
        """Record a BLE failure and retain fresh-discovery state when appropriate."""
        self.last_failure_type = type(err).__name__
        stale_gatt = is_stale_gatt_error(err)
        if stale_gatt:
            mark_stale_gatt_recovery(self.hass, self.address)
        return stale_gatt

    def _renew_foreground_lease(self) -> None:
        if (
            self.connection_mode != CONNECTION_MODE_HOLD
            and self._control_arbiter.current_task_intent is not ControlIntent.BACKGROUND
        ):
            self._reset_disconnect_timer()

    def _reset_disconnect_timer(self) -> None:
        if self.connection_mode == CONNECTION_MODE_HOLD:
            if self._cancel_disconnect:
                self._cancel_disconnect()
                self._cancel_disconnect = None
            return
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
        if self.connection_mode == CONNECTION_MODE_HOLD or generation != self._disconnect_generation:
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
        self._static_rgb_known = False
        self._music_palette = self._music_body = None
        self._notification_token = None
        self.video_parameters = None
        self._confirmed_identity_fields.clear()
        self._authorization_generation += 1
        self._configured_strings_confirmed = False
        self._segment_query_generation = None
        if self._encryption is not None:
            self._encryption.reset()
        if client is not None:
            self.last_disconnected_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._notify_started_monotonic = None
        self._last_rx_monotonic = None
        self._expected_state.clear()
        self._segment_query_incomplete = False
        self._bulk_query_incomplete = False
        self._bulk_collector = None
        self._bulk_query_deadline = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = self._segment_query_brightness = None
        if client is None or self._intentional_disconnect_client is not client:
            self.installation_direction, self.camera_health = None, "unknown"
            self.strip_direction = self.camera_position = self.gradient = None
            self.camera_status = "unknown"
            self.boolean_control_state.clear()
            self.power_on_behaviour = None
        self._physical_ic_count_confirmed = False
        if self.profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) and get_profile(self.model).physical_ic_count is None:
            self._observed_physical_ic_count = None
            self.profile = replace(self.profile, physical_ic_count=None)
        self._stop_keep_alive()
        self._disconnect_generation += 1
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _start_notify(self) -> None:
        if not (self._client and self._client.is_connected):
            return
        client = self._client
        token = self._notification_token = object()

        def receive(sender: Any, data: bytearray) -> None:
            if self._client is client and self._notification_token is token and client.is_connected:
                self._notify_callback(sender, data)

        await client.start_notify(READ_UUID, receive)
        if self._client is not client or self._notification_token is not token:
            raise GoveeCryptoError("disconnected_during_subscription")
        self._notify_started_monotonic = time.monotonic()
        self._last_rx_monotonic = None

    def _receive_is_stale(self) -> bool:
        baseline = self._last_rx_monotonic
        if baseline is None:
            baseline = self._notify_started_monotonic
        return baseline is not None and time.monotonic() - baseline >= RX_STALE_TIMEOUT

    def _mark_received(self, domain: StatusDomain, *fields: str) -> None:
        received_at = time.monotonic()
        self._domain_revisions[domain] = self._domain_revisions.get(domain, 0) + 1
        self._domain_received_at[domain] = received_at
        for field in fields:
            self._field_revisions[field] = self._field_revisions.get(field, 0) + 1
            self._field_received_at[field] = received_at
        self._revision_event.set()

    @callback
    def _expire_optional_observations(self, baselines: Mapping[str, int]) -> None:
        changed = False
        for field, baseline in baselines.items():
            if self._field_revisions.get(field, 0) > baseline:
                continue
            if field in {"is_on", "brightness_pct", "color_mode", "segment_colors", "segment_brightness"}:
                # A missing optional basic reply leaves cached presentation, not a new observation.
                continue
            if field.startswith("boolean_"):
                changed |= self.boolean_control_state.pop(field.removeprefix("boolean_"), None) is not None
            else:
                value = "unknown" if field in {"camera_health", "camera_status"} else None
                if getattr(self, field, None) != value:
                    setattr(self, field, value)
                    changed = True
        if changed:
            self.async_set_updated_data(self.data or {})

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
        self._static_rgb_known = False
        self.segment_colors = colours
        self.segment_brightness = brightness
        self.segment_state_source = "restored"
        self.segment_state_observed_at = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = None
        self._segment_query_brightness = None

    def _apply_segment_group(self, generated: Any) -> tuple[str, ...]:
        if (
            self.profile.configured_string_counts
            and (not self._configured_strings_confirmed or self._segment_query_generation != self._profile_generation)
        ) or (
            self.profile.ic_per_segment is not None
            and self._segment_query_generation not in (None, self._profile_generation)
        ):
            raise ValueError("segment page has no current configured layout")
        group = getattr(generated.body, "group", None)
        records = getattr(generated.body, "segments", None)
        count = getattr(generated.body, "num_segments", None)
        group_size = self.profile.segment_group_size
        if type(group) is not int or not 1 <= group <= self._segment_group_count:
            raise ValueError("invalid segment group for model")
        offset = (group - 1) * group_size
        expected_count = min(group_size, self.profile.segment_count - offset)
        if (
            type(count) is int
            and isinstance(records, list)
            and len(records) == count
            and expected_count < count <= group_size
            and self.profile.segment_count < get_profile(self.model).segment_count
        ):
            records = records[:expected_count]
            count = expected_count
        if type(count) is not int or count != expected_count or not isinstance(records, list) or len(records) != count:
            raise ValueError("segment record count does not match model page")
        # Convert the entire page before touching an in-progress observation.
        try:
            page_colours = [(int(r.colour.red), int(r.colour.green), int(r.colour.blue)) for r in records]
            brightness_fields = [hasattr(record, "brightness") for record in records]
            if any(brightness_fields) and not all(brightness_fields):
                raise ValueError("inconsistent segment brightness fields")
            page_brightness = [int(r.brightness) for r in records] if all(brightness_fields) else None
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
        if page_brightness is not None:
            brightness[offset : offset + count] = page_brightness
        self._segment_groups_observed.add(group)
        if len(self._segment_groups_observed) != self._segment_group_count:
            return ()
        if self._static_rgb_known and self.segment_colors != colours:
            self._static_rgb_known = False
        self.segment_colors = colours
        if page_brightness is not None:
            self.segment_brightness = brightness
        self.segment_brightness_readable = page_brightness is not None
        self._segment_query_colors = None
        self._segment_query_brightness = None
        self._segment_groups_observed.clear()
        self.segment_state_source = "observed"
        self.segment_state_observed_at = datetime.now().astimezone().isoformat()
        observed = ["segment_colors"]
        if page_brightness is not None:
            observed.append("segment_brightness")
        if (
            self.color_mode is ParsedMode.COLOUR
            and len(set(self.segment_colors)) != 1
            and self.color_temp_kelvin_source != "observed"
        ):
            self.color_temp_kelvin = None
            self.color_temp_kelvin_source = "initial"
        # Direct static readback outranks rendered segments; a matching white point
        # can retain last-known Kelvin but never proves a fresh Kelvin measurement.
        if (
            self.color_mode is ParsedMode.COLOUR
            and len(set(self.segment_colors)) == 1
            and self.rgb_color_source != "observed"
            and (self.color_temp_kelvin is None or self.color_temp_kelvin_source != "observed")
        ):
            rendered = self.segment_colors[0]
            kelvin = self.color_temp_kelvin
            if (
                kelvin is not None
                and self._pending_kelvin != kelvin
                and not (self.profile.segment_kelvin_renders_device_rgb and rendered[0] >= 200 and rendered[1] >= 100)
                and rendered != kelvin_companion_rgb(kelvin, self.profile)
            ):
                kelvin = None
            if self._accept_expected_values({"rgb_color": rendered, "color_temp_kelvin": kelvin}):
                self.rgb_color = rendered
                self.rgb_color_source = "segment"
                if kelvin is None and self.color_temp_kelvin_source != "observed":
                    self.color_temp_kelvin = None
                    self.color_temp_kelvin_source = "initial"
                observed.append("rgb_color")
        return tuple(observed)

    async def _async_write_packet(
        self,
        client: BleakClient,
        packet: bytes,
        *,
        arm_expected: bool = False,
        before_write: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
        cleanup_deadline: float | None = None,
        packet_validator: Callable[[bytes, ModelProfile], None] = require_profile_packet,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        """Write on the caller's connection without changing its transaction policy."""
        try:
            self._require_not_shutdown()
            self._require_not_dreamview_claimed()
        except BleakError:
            await self._disconnect_locked()
            raise
        if arm_expected and (self._segment_query_incomplete or self._bulk_query_incomplete):
            # The caller owns reconnect/retry policy; never write across an abandoned query.
            query_kind = "segment" if self._segment_query_incomplete else "bulk"
            raise BleakError(f"Incomplete {query_kind} query requires a new connection")
        packet_validator(packet, self.profile)
        self._validate_authorized_packet(packet, packet_validator)
        if (
            arm_expected
            and self.profile.configured_string_counts
            and parse_static_write(packet, self.model, profile=self.profile) is not None
        ):
            self._require_mask_transaction()
        generation = self._profile_generation
        authorization_generation = self._authorization_generation
        wire_packet = packet
        if (transform := self.profile.outbound_transform) is not None:
            wire_packet = transform(packet)
            if not isinstance(wire_packet, bytes) or not wire_packet:
                raise ValueError("Outbound transform must return non-empty bytes")
        if self._encryption is not None:
            if self._client is not client or not client.is_connected:
                raise GoveeCryptoError("stale_connection")
            wire_packet = self._encryption.encode(wire_packet)
        if before_write is not None:
            before_write()
        try:
            self._require_not_shutdown()
            self._require_not_dreamview_claimed()
        except BleakError:
            await self._disconnect_locked()
            raise
        packet_validator(packet, self.profile)
        self._validate_authorized_packet(packet, packet_validator)
        if (
            arm_expected
            and self.profile.configured_string_counts
            and parse_static_write(packet, self.model, profile=self.profile) is not None
        ):
            self._require_mask_transaction()
        if arm_expected and generation != self._profile_generation:
            raise ValueError("Device profile changed before control write; refresh and retry")
        if arm_expected and authorization_generation != self._authorization_generation:
            raise ValueError("Device identity changed before control write; refresh and retry")
        requested = expectations_from_packet(packet, self.model, profile=self.profile)
        if (music_mode := requested.get("music_mode")) is not None and music_mode not in self.profile.music_modes:
            raise ValueError("Device profile does not support the requested music mode")
        if arm_expected:
            for field in ("is_on", "brightness_pct"):
                if field in requested:
                    setattr(self, field, requested[field])
        if state_values is not None:
            for field, value in state_values.items():
                setattr(self, field, value)
        if arm_expected:
            self._arm_expected(packet)
        if expected_values is not None:
            self._arm_expected_values(dict(expected_values))
        rgb_intent: tuple[int, int, int] | None = None
        if arm_expected:
            self.control_write_attempts += 1
            static = parse_static_write(packet, self.model, profile=self.profile)
            if static is not None:
                self._static_write_attempts += 1
                if static.kelvin is not None:
                    self._static_rgb_known = False
                elif static.rgb is not None and static.whole_strip:
                    self._static_rgb_known = False
                    rgb_intent = static.rgb
                rgb = static.rgb or static.kelvin_companion_rgb
                if static.whole_strip and rgb is not None:
                    self.install_static_color(rgb=static.rgb, kelvin=static.kelvin)
                if static.segment_mask is not None:
                    self.mark_segment_state_optimistic(
                        colours=[
                            rgb if rgb is not None and static.segment_mask & (1 << index) else colour
                            for index, colour in enumerate(self.segment_colors)
                        ],
                        brightness=[
                            static.brightness_pct
                            if static.brightness_pct is not None and static.segment_mask & (1 << index)
                            else value
                            for index, value in enumerate(self.segment_brightness)
                        ],
                    )
                self._enter_static_mode()
        if on_write is not None:
            on_write()
        token = self._notification_token
        try:
            await client.write_gatt_char(WRITE_UUID, wire_packet, response=False)
            self._require_not_shutdown()
        except asyncio.CancelledError:
            if self._encryption is not None:
                try:
                    # The expired query timeout cannot cancel its own cleanup again.
                    # Invalidation and final client clearing live in _disconnect_locked.
                    async with asyncio.timeout_at(
                        cleanup_deadline
                        if cleanup_deadline is not None
                        else time.monotonic() + VALIDATION_DISCONNECT_TIMEOUT
                    ):
                        await self._disconnect_locked()
                except TimeoutError:
                    pass
            raise
        except Exception as err:
            stale_gatt = self._record_ble_failure(err)
            encrypted = self._encryption is not None and self._encryption.version
            if stale_gatt or encrypted or self._shutdown_requested:
                await self._disconnect_locked(clear_cache=stale_gatt)
            if encrypted:
                if isinstance(err, BleakError):
                    raise BleakError("encrypted_write_failed") from None
                raise GoveeCryptoError("encrypted_write_failed") from None
            raise
        packet_entry = self._record_packet("tx", wire_packet, outcome="sent", reason="write_succeeded")
        _LOGGER.debug("tx %s raw=%s", self.model, packet_entry["raw"])
        if arm_expected and generation != self._profile_generation:
            raise ValueError("Device profile changed during control write; refresh and retry")
        if arm_expected and authorization_generation != self._authorization_generation:
            raise ValueError("Device identity changed during control write; refresh and retry")
        if (
            rgb_intent is not None
            and self._client is client
            and client.is_connected
            and self._notification_token is token
        ):
            self._static_rgb_known = self.segment_colors == [rgb_intent] * self.profile.segment_count

    async def _send_state_queries(
        self,
        *,
        query_power: bool = True,
        query_brightness: bool = True,
        query_color_mode: bool = True,
        query_white_balance: bool | None = None,
        query_blank_screen: bool | None = None,
        query_black_border: bool | None = None,
        query_relative_brightness: bool | None = None,
        query_segments: bool | None = None,
        required_domains: frozenset[ReadDomain] | None = None,
        optional_baselines: dict[str, int] | None = None,
        deadline: float | None = None,
    ) -> bool:
        client = self._client
        if client is None or not client.is_connected or self._segment_query_incomplete or self._bulk_query_incomplete:
            return False
        token = self._notification_token
        if deadline is None:
            deadline = time.monotonic() + 2.0
        full_query = query_power and query_brightness and query_color_mode
        if self.profile.configured_string_counts and (full_query or query_segments is True):
            if not self._has_mask_transaction():
                # Missing optional geometry must leave time for topology-independent reads.
                count_deadline = deadline if query_segments is True else (time.monotonic() + deadline) / 2
                await self._read_configured_strings(client, deadline=count_deadline)
            if query_segments is True and not self._configured_strings_confirmed:
                return False
        generation = self._profile_generation
        authorization_generation = self._authorization_generation
        profile = self._authorization_profile()
        segment_baseline: dict[str, int] = {}
        try:
            queries: list[tuple[bytes, ReadDomain, tuple[str, ...]]] = []
            states = video_control_states(self.profile, self)
            video_identity_ready = self.identity_fields_confirmed(video_identity_fields(self.profile))
            confirmed_controls = {
                control
                for control in states
                if self.identity_fields_confirmed(video_identity_fields(self.profile, (control,)))
            }
            if query_power and profile.can_read(ReadDomain.POWER):
                queries.append((build_power_query(self.model, profile=profile), ReadDomain.POWER, ("is_on",)))
            if query_brightness and profile.can_read(ReadDomain.BRIGHTNESS):
                queries.append(
                    (
                        build_brightness_query(self.model, profile=profile),
                        ReadDomain.BRIGHTNESS,
                        ("brightness_pct",),
                    )
                )
            if query_color_mode and profile.supports_color_mode_readback:
                color_domain = ReadDomain.COLOUR_MODE if profile.can_read(ReadDomain.COLOUR_MODE) else ReadDomain.MODE
                queries.append((build_colour_mode_query(self.model, profile=profile), color_domain, ("color_mode",)))
            if (
                "white_balance" in confirmed_controls
                and profile.can_read(ReadDomain.DISPLAY_SETTING)
                and white_balance_readback_state(self.profile, self) is CapabilityState.SUPPORTED
                and (query_white_balance if query_white_balance is not None else full_query)
            ):
                queries.append(
                    (
                        build_white_balance_query(self.model, profile=profile),
                        ReadDomain.DISPLAY_SETTING,
                        ("white_balance_scalar",)
                        if self.profile.video_white_balance_representation == "scalar"
                        else _WHITE_BALANCE_GAIN_FIELDS,
                    )
                )
            if (
                "blank_screen" in confirmed_controls
                and profile.can_read(ReadDomain.DISPLAY_SETTING)
                and states["blank_screen"] is CapabilityState.SUPPORTED
                and (query_blank_screen if query_blank_screen is not None else full_query)
            ):
                queries.append(
                    (
                        build_blank_screen_query(self.model, profile=profile),
                        ReadDomain.DISPLAY_SETTING,
                        ("blank_screen", *_BLANK_SCREEN_POLICY_FIELDS),
                    )
                )
            if (
                "black_border" in confirmed_controls
                and profile.can_read(ReadDomain.DISPLAY_SETTING)
                and states["black_border"] is CapabilityState.SUPPORTED
                and (query_black_border if query_black_border is not None else full_query)
            ):
                queries.append(
                    (
                        build_black_border_query(self.model, profile=profile),
                        ReadDomain.DISPLAY_SETTING,
                        ("black_border",),
                    )
                )
            if (
                "relative_brightness" in confirmed_controls
                and profile.can_read(ReadDomain.RELATIVE_BRIGHTNESS)
                and states["relative_brightness"] is CapabilityState.SUPPORTED
                and (query_relative_brightness if query_relative_brightness is not None else full_query)
            ):
                queries.append(
                    (
                        build_relative_brightness_query(self.model, profile=profile),
                        ReadDomain.RELATIVE_BRIGHTNESS,
                        tuple(f"relative_brightness_{zone}" for zone in self.profile.video_brightness_zones),
                    )
                )
            if (
                profile.can_read(ReadDomain.SEGMENTS)
                and profile.supports_segments
                and (not self.profile.configured_string_counts or self._configured_strings_confirmed)
                and (query_segments if query_segments is not None else full_query)
            ):
                segment_baseline = {"segment_colors": self._field_revisions.get("segment_colors", 0)}
                self._segment_groups_observed.clear()
                self._segment_query_colors = list(self.segment_colors)
                self._segment_query_brightness = list(self.segment_brightness)
                self._segment_query_generation = generation
                queries.extend(
                    (
                        build_segment_query(group, self.model, profile=profile),
                        ReadDomain.SEGMENTS,
                        ("segment_colors", "segment_brightness"),
                    )
                    for group in range(1, profile.segment_group_count + 1)
                )
            if full_query:
                queries.extend(
                    (query, domain, (domain.value,))
                    for query, domain in zip(
                        h6099_control_queries(self.model, profile),
                        (
                            domain
                            for domain in (ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH)
                            if profile.can_read(domain)
                        ),
                        strict=True,
                    )
                )
            if full_query and video_identity_ready:
                if h6199_camera_controls_state(self.model, self) is CapabilityState.SUPPORTED:
                    queries.extend(
                        (build_h6199_control_query(control), ReadDomain.OTHER, (control,))
                        for control in H6199_NATIVE_CONTROLS
                    )
            if full_query and profile.boolean_controls and profile.setting_grammar != "H60A6":
                from .generated_protocol_adapter import build_boolean_control_query

                queries.extend(
                    (
                        build_boolean_control_query(control, self.model, profile=profile),
                        ReadDomain.OTHER,
                        (f"boolean_{control}",),
                    )
                    for control in sorted(profile.boolean_controls)
                )
            if full_query and profile.supports_power_on_behaviour and profile.bulk_status_grammar is None:
                from .generated_protocol_adapter import build_power_on_behaviour_query

                queries.append((build_power_on_behaviour_query(profile), ReadDomain.OTHER, ("power_on_behaviour",)))
            required = (
                required_domains
                if required_domains is not None
                else frozenset(
                    {
                        ReadDomain.POWER,
                        ReadDomain.BRIGHTNESS,
                        ReadDomain.COLOUR_MODE,
                        ReadDomain.DISPLAY_SETTING,
                        ReadDomain.RELATIVE_BRIGHTNESS,
                    }
                )
            ) & profile.read_domains
            if query_segments is True and profile.supports_segments:
                required |= {ReadDomain.SEGMENTS}
            for index, (query, domain, fields) in enumerate(queries):
                if (
                    generation != self._profile_generation
                    or authorization_generation != self._authorization_generation
                    or self._client is not client
                    or not client.is_connected
                ):
                    return False
                if time.monotonic() >= deadline:
                    return all(d not in required for _, d, _ in queries[index:])
                baselines = {field: self._field_revisions.get(field, 0) for field in fields}
                if domain is ReadDomain.COLOUR_MODE and profile.bulk_status_grammar is not None:
                    if optional_baselines is not None and domain not in required:
                        for field, revision in baselines.items():
                            optional_baselines.setdefault(field, revision)
                    if not await self._async_read_bulk_status(client, deadline=deadline):
                        return domain not in required and all(d not in required for _, d, _ in queries[index + 1 :])
                    continue

                def before_segment_write() -> None:
                    # A rejected transform has not started a batch. Once any page is
                    # attempted, later failures must leave the connection non-reusable.
                    self._segment_query_incomplete = True

                try:
                    async with asyncio.timeout_at(deadline) as write_timeout:
                        await self._async_write_packet(
                            client,
                            query,
                            before_write=before_segment_write if domain is ReadDomain.SEGMENTS else None,
                            cleanup_deadline=deadline,
                        )
                except TimeoutError:
                    if not write_timeout.expired():
                        raise
                    return (
                        authorization_generation == self._authorization_generation
                        and self._client is client
                        and client.is_connected
                        and all(d not in required for _, d, _ in queries[index:])
                    )
                except BleakError:
                    if domain in required or self._client is not client or not client.is_connected:
                        return False
                    _LOGGER.debug("Optional %s query failed for %s", domain.value, self.address, exc_info=True)
                    continue
                if optional_baselines is not None and (
                    domain not in required or domain in _OPTIONAL_CONTROL_DOMAINS | {ReadDomain.OTHER}
                ):
                    for field, revision in baselines.items():
                        optional_baselines.setdefault(field, revision)
                if time.monotonic() >= deadline:
                    return authorization_generation == self._authorization_generation and all(
                        d not in required for _, d, _ in queries[index:]
                    )
            if (
                generation != self._profile_generation
                or authorization_generation != self._authorization_generation
                or self._client is not client
                or not client.is_connected
            ):
                return False
            if segment_baseline:
                # All producers hold the existing control intent through this collection.
                # Buffer resets cannot distinguish an older in-flight reply on this wire.
                # ponytail: no wire query IDs; collection prevents local overlap, not
                # indistinguishable unsolicited/duplicate batches from the same subscription.
                complete = await self._wait_for_revisions(segment_baseline, {}, deadline)
                complete = complete and time.monotonic() < deadline
                if (
                    generation != self._profile_generation
                    or authorization_generation != self._authorization_generation
                    or self._client is not client
                    or not client.is_connected
                    or self._notification_token is not token
                ):
                    return False
                self._segment_query_incomplete = not complete
                if not complete and ReadDomain.SEGMENTS in required:
                    return False
            return True
        except BleakError:
            return False

    async def async_set_h6199_control(self, control: str, value: int, *, timeout: float = 2.0) -> None:
        """Write one register and require a fresh reply, never an ACK or cached value."""
        packet = build_h6199_control(control, value)

        def qualified() -> None:
            if (
                not self.identity_fields_confirmed(video_identity_fields(self.profile))
                or h6199_camera_controls_state(self.model, self) is not CapabilityState.SUPPORTED
            ):
                raise ValueError("H6199 control is not qualified for this device revision")

        async with async_control_intent(self, ControlIntent.USER):
            try:
                async with asyncio.timeout(CONNECTION_SETUP_TIMEOUT + timeout):
                    async with self._lock:
                        await self._ensure_connected()
                    qualified()
                    await self.async_write_effect_sequence(
                        (packet,),
                        intent=ControlIntent.USER,
                        write_guard=qualified,
                        state_values={control: None},
                    )
            finally:
                self.async_set_updated_data(self.data or {})
            async with self._lock:
                client = self._client
                if client is None or not client.is_connected:
                    raise BleakError("Device disconnected before control readback")
                qualified()
                observation = "gradient_register" if control == "gradient" else control
                baseline = {observation: self._field_revisions.get(observation, 0)}
                setattr(self, control, None)
                deadline = time.monotonic() + timeout
                try:
                    async with asyncio.timeout_at(deadline):
                        await self._async_write_packet(
                            client, build_h6199_control_query(control), cleanup_deadline=deadline
                        )
                        fresh = await self._wait_for_revisions(baseline, {}, deadline)
                finally:
                    self.async_set_updated_data(self.data or {})
                if not fresh or getattr(self, observation, None) != value:
                    raise ValueError("Device did not confirm the requested H6199 control")

    async def _send_identity_queries(self) -> None:
        """Query missing identity and invalid condition-bearing versions.

        Replies can be missed right after connect while notifications are starting, so the
        keep-alive loop retries unknown values up to ``IDENTITY_RETRY_TICKS``.
        """
        client = self._client
        if client is None or not client.is_connected:
            return
        try:
            for _ in range(2):
                generation = self._profile_generation
                candidates: list[tuple[bytes, str]] = []
                if self.profile.can_read(ReadDomain.HARDWARE):
                    candidates.append((build_hardware_query(self.model, profile=self.profile), "hw_version"))
                if self.profile.can_read(ReadDomain.FIRMWARE):
                    candidates.append((build_firmware_query(self.model, profile=self.profile), "fw_version"))
                if self.profile.can_read(ReadDomain.SUBORDINATE_20):
                    candidates.append((build_subordinate_query(0x20, self.model), "subordinate_20_version"))
                if self.profile.can_read(ReadDomain.SUBORDINATE_21):
                    candidates.append((build_subordinate_query(0x21, self.model), "subordinate_21_version"))
                queries = [q for q, field in candidates if self._identity_field_incomplete(field)]
                if self.profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) and not self._physical_ic_count_confirmed:
                    queries.append(build_physical_ic_count_query(self.model, profile=self.profile))
                for query in queries:
                    if generation != self._profile_generation:
                        break
                    if self._client is not client or not client.is_connected:
                        return
                    await self._async_write_packet(client, query)
                if generation == self._profile_generation:
                    return
        except BleakError:
            if self._client is not client or not client.is_connected:
                raise
            _LOGGER.debug("Identity query failed for %s", self.address)

    def _identity_field_incomplete(self, field: str) -> bool:
        value = getattr(self, field)
        if field in self._authorization_identity_fields():
            return field not in self._confirmed_identity_fields or identity_version(value) is None
        return value is None

    def _authorization_identity_fields(self) -> frozenset[str]:
        return self.profile.profile_identity_fields | frozenset(video_identity_fields(self.profile))

    def _authorization_profile(self) -> ModelProfile:
        fields = self.profile.profile_identity_fields
        if not fields or self.identity_fields_confirmed(fields):
            return self.profile
        if self.model == "H6102":
            return self._h6102_authorization_profile()
        return device_profile(self.model, self.pact_type, self.pact_code, firmware=None, hardware=None)

    def _validate_authorized_packet(
        self, packet: bytes, validator: Callable[[bytes, ModelProfile], None] = require_profile_packet
    ) -> None:
        profile = self._authorization_profile()
        if profile != self.profile:
            validator(packet, profile)

    def _apply_configured_strings(self, count: int) -> None:
        if count not in self.profile.configured_string_counts:
            raise ValueError("unsupported configured string count")
        if self.configured_strings == count:
            return
        self.configured_strings = count
        self._configured_strings_confirmed = False
        bulbs = count * self.profile.bulbs_per_string
        self.profile = replace(self.profile, segment_count=bulbs, whole_device_mask=(1 << bulbs) - 1)
        self._profile_generation += 1
        self._expected_state.clear()
        self._segment_query_generation = None
        self._segment_groups_observed.clear()
        self._segment_query_colors = self._segment_query_brightness = None
        self.segment_colors = [(255, 255, 255)] * bulbs
        self.segment_brightness = [100] * bulbs
        self.segment_brightness_readable = False
        self._static_rgb_known = False
        self.segment_state_source = "initial"
        self.segment_state_observed_at = None
        self.color_temp_kelvin = None
        self.rgb_color_source = self.color_temp_kelvin_source = "initial"

    async def _read_configured_strings(self, client: BleakClient, *, deadline: float) -> bool:
        self._configured_strings_confirmed = False
        baseline = {"configured_strings": self._field_revisions.get("configured_strings", 0)}
        token = self._notification_token
        try:
            async with asyncio.timeout_at(deadline):
                await self._async_write_packet(
                    client, build_configured_strings_query(self.profile), cleanup_deadline=deadline
                )
                received = await self._wait_for_revisions(baseline, {}, deadline)
        except TimeoutError:
            received = False
        self._configured_strings_confirmed = (
            received and self._client is client and client.is_connected and self._notification_token is token
        )
        if not self._configured_strings_confirmed:
            _LOGGER.debug("Configured string count could not be confirmed")
        return self._configured_strings_confirmed

    def _has_mask_transaction(self) -> bool:
        return self._mask_transaction == (asyncio.current_task(), self._notification_token, self._profile_generation)

    def _require_mask_transaction(self) -> None:
        if not self._configured_strings_confirmed or not self._has_mask_transaction():
            raise ValueError("Configured bulb layout changed or is unknown; refresh and retry")

    @asynccontextmanager
    async def async_mask_transaction(self) -> AsyncIterator[None]:
        """Confirm configuration once before building a mask-dependent request."""
        if not self.profile.configured_string_counts:
            yield
            return
        if self._mask_transaction is not None and self._mask_transaction[0] is asyncio.current_task():
            self._require_mask_transaction()
            yield
            return
        intent = self._control_arbiter.current_task_intent or ControlIntent.USER
        async with async_control_intent(self, intent):
            async with self._lock:
                client = await self._ensure_connected()
                if not await self._read_configured_strings(client, deadline=time.monotonic() + 2.0):
                    raise ValueError("Cannot confirm configured bulb layout; refresh and retry")
            self._mask_transaction = (asyncio.current_task(), self._notification_token, self._profile_generation)
            try:
                yield
            finally:
                self._mask_transaction = None

    async def async_set_configured_strings(self, count: int) -> None:
        packet = build_configured_strings(count, self.profile)
        command = parse_command_result(packet, self.model, profile=self.profile).parsed
        if command is None:
            raise ValueError("Invalid configured string command")
        opcode = int(command.opcode)
        async with async_control_intent(self, ControlIntent.USER):
            if self.config_entry is not None:
                from .effect_setup import get_effect_backend

                if backend := get_effect_backend(self.hass):
                    await backend.preview.async_supersede_device(
                        self.config_entry.entry_id, reason="home_assistant_control"
                    )
            async with self._lock:
                client = await self._ensure_connected()
                future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
                token = self._notification_token

                def before_write() -> None:
                    self._configured_strings_confirmed = False
                    self._setting_ack = (client, token, opcode, future)

                try:
                    async with asyncio.timeout(4.0):
                        await self._async_write_packet(client, packet, arm_expected=True, before_write=before_write)
                        if not await future:
                            raise ValueError("Device rejected configured string count")
                    if not await self._read_configured_strings(client, deadline=time.monotonic() + 2.0):
                        raise ValueError("Device did not provide fresh configured string count")
                    if self.configured_strings != count:
                        raise ValueError("Device did not confirm requested string count")
                finally:
                    self._setting_ack = None
                    future.cancel()
            if not await self.async_refresh_segments():
                raise ValueError("Configured strings changed but bulb state could not be read")

    async def async_set_boolean_control(self, control: str, enabled: bool) -> None:
        await self._async_set_verified_setting(control, enabled)

    async def async_set_power_on_behaviour(self, value: str) -> None:
        await self._async_set_verified_setting("power_on_behaviour", value)

    async def _async_set_verified_setting(self, control: str, value: bool | str) -> None:
        from .generated_protocol_adapter import (
            build_boolean_control,
            build_boolean_control_query,
            build_power_on_behaviour_query,
        )

        def qualified() -> None:
            if not (
                self.profile.supports_power_on_behaviour
                if control == "power_on_behaviour"
                else control in self.profile.boolean_controls
            ):
                raise ValueError("Device profile does not support this setting")

        qualified()
        if control == "power_on_behaviour":
            if not isinstance(value, str):
                raise ValueError("Power-on behaviour requires an option")
            packet = build_power_on_behaviour(value, self.profile)
        else:
            if type(value) is not bool:
                raise ValueError("Boolean setting requires a boolean")
            packet = build_boolean_control(control, value, self.model, profile=self.profile)
        async with async_control_intent(self, ControlIntent.USER):
            async with self._lock:
                await self._ensure_connected()
            qualified()
            if self.config_entry is not None:
                from .effect_setup import get_effect_backend

                if backend := get_effect_backend(self.hass):
                    await backend.preview.async_supersede_device(
                        self.config_entry.entry_id, reason="home_assistant_control"
                    )
            generation = self._profile_generation
            field = control if control == "power_on_behaviour" else f"boolean_{control}"
            baseline = {field: self._field_revisions.get(field, 0)}
            await self.send_command(packet, write_guard=qualified)
            async with self._lock:
                qualified()
                client = self._client
                if client is None or not client.is_connected:
                    raise BleakError("Device disconnected before setting readback")
                if generation != self._profile_generation:
                    raise ValueError("Device profile changed during setting write")
                deadline = time.monotonic() + 4.0
                if self.profile.setting_grammar == "H60A6":
                    if self._field_revisions.get(field, 0) <= baseline[field]:
                        domain = "power_on_behaviour" if control == "power_on_behaviour" else "zone_enable"
                        if not await self._async_read_bulk_status(client, deadline=deadline, domains=(domain,)):
                            raise ValueError("Device did not provide complete setting readback")
                else:
                    await self._async_write_packet(
                        client,
                        build_power_on_behaviour_query(self.profile)
                        if control == "power_on_behaviour"
                        else build_boolean_control_query(control, self.model, profile=self.profile),
                    )
                if not await self._wait_for_revisions(baseline, {}, deadline) or generation != self._profile_generation:
                    raise ValueError("Device did not provide fresh setting readback")
                actual = (
                    self.power_on_behaviour
                    if control == "power_on_behaviour"
                    else self.boolean_control_state.get(control)
                )
                if actual != value:
                    raise ValueError("Device did not confirm the requested setting")

    @property
    def physical_ic_count_source(self) -> str:
        if self.profile.physical_ic_count is None:
            return "unknown"
        if (
            self._observed_physical_ic_count is not None
            and self.profile.physical_ic_count == self._observed_physical_ic_count
        ):
            return "observed"
        return "declared" if self.profile.physical_ic_count == get_profile(self.model).physical_ic_count else "unknown"

    def _identity_incomplete(self) -> bool:
        return (self.profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) and not self._physical_ic_count_confirmed) or any(
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
            # Collection of optional domains can consume the budget after basic replies
            # arrived. Accept those timely observations, never a late callback that won
            # the event-loop race against the timeout waiter.
            # Segment RGB revisions update presentation, not direct static readback.
            fresh_fields = {
                field
                for field, baseline in field_baselines.items()
                if self._field_revisions.get(field, 0) > baseline
                and self._field_received_at.get(field, float("inf")) <= deadline
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
            if field_baselines and fresh_fields != field_baselines.keys():
                return False
            return all(
                self._domain_revisions.get(domain, 0) > baseline
                and self._domain_received_at.get(domain, float("inf")) <= deadline
                for domain, baseline in domain_baselines.items()
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

    async def refresh_state(self, **kwargs: Any) -> bool:
        """Resolve connection identity before constructing queries and freshness baselines."""
        if not self.profile.state_readable:
            return False
        if kwargs.get("expected_rgb_color") is not None and not self.profile.static_readback_echoes_color:
            return False
        if kwargs.get("expected_color_temp_kelvin") is not None and not self.profile.static_readback_kelvin:
            return False
        if kwargs.get("expected_zero_kelvin") and not self.profile.static_readback_zero_kelvin_is_rgb:
            return False
        if (
            kwargs.get("expected_black_border") is not None
            and video_control_states(self.profile, self)["black_border"] is not CapabilityState.SUPPORTED
        ):
            return False
        if not self.profile.supports_color_mode_readback and any(
            value is not None
            and key.startswith(
                (
                    "expected_effect",
                    "expected_scene",
                    "expected_rgb",
                    "expected_color_temp",
                    "expected_music",
                    "expected_video",
                    "expected_white_brightness",
                )
            )
            for key, value in kwargs.items()
        ):
            return False
        current_intent = self._control_arbiter.current_task_intent
        async with async_control_intent(self, ControlIntent.USER if current_intent is None else current_intent):
            async with self._lock:
                await self._ensure_connected()
            return await self._refresh_connected_state(**kwargs)

    async def _refresh_connected_state(
        self,
        *,
        expected_effect: str | None = None,
        expected_scene_code: int | None = None,
        expected_on: bool | None = None,
        expected_brightness: int | None = None,
        expected_rgb_color: tuple[int, int, int] | None = None,
        expected_color_temp_kelvin: int | None = None,
        expected_zero_kelvin: bool = False,
        expected_music_mode: str | None = None,
        expected_music_sensitivity: int | None = None,
        expected_music_calm: bool | None = None,
        expected_music_color: tuple[int, int, int] | None = None,
        expected_music_auto_color: bool = False,
        expected_video_mode: str | None = None,
        expected_video_parameters: Mapping[str, Any] | None = None,
        expected_video_full_screen: bool | None = None,
        expected_video_saturation: int | None = None,
        expected_video_sound_effects: bool | None = None,
        expected_video_sound_effects_softness: int | None = None,
        expected_white_brightness: int | None = None,
        expected_white_balance: tuple[int, ...] | None = None,
        expected_white_balance_flag: int | None = None,
        expected_blank_screen: bool | None = None,
        expected_blank_screen_policy: tuple[int, int, int] | None = None,
        expected_black_border: bool | None = None,
        expected_relative_brightness: tuple[int, ...] | None = None,
        refresh_display_settings: bool | frozenset[str] = False,
        refresh_relative_brightness: bool = False,
        refresh_all: bool = False,
        query_segments: bool | None = None,
        required_domains: frozenset[ReadDomain] | None = None,
        timeout: float = 2.0,
    ) -> bool:
        if not self.profile.state_readable:
            return False
        generation = self._profile_generation
        if expected_rgb_color is not None and not self.profile.static_readback_echoes_color:
            return False
        if expected_color_temp_kelvin is not None and not self.profile.static_readback_kelvin:
            return False
        if expected_zero_kelvin and (
            not self.profile.static_readback_zero_kelvin_is_rgb or expected_color_temp_kelvin is not None
        ):
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
                ("video_parameters", expected_video_parameters),
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
        if expected_zero_kelvin:
            expectations["color_temp_kelvin"] = None
        if expected_rgb_color is not None or expected_color_temp_kelvin is not None or expected_zero_kelvin:
            expectations["color_mode"] = ParsedMode.COLOUR
        if expected_white_balance is not None:
            fields = (
                ("white_balance_scalar",)
                if self.profile.video_white_balance_representation == "scalar"
                else ("white_balance_red", "white_balance_blue")
            )
            expectations.update(zip(fields, expected_white_balance, strict=True))
        if expected_white_balance_flag is not None:
            expectations["white_balance_flag"] = expected_white_balance_flag
        if expected_blank_screen is not None:
            expectations["blank_screen"] = expected_blank_screen
        if expected_blank_screen_policy is not None:
            expectations.update(zip(_BLANK_SCREEN_POLICY_FIELDS, expected_blank_screen_policy, strict=True))
        if expected_black_border is not None:
            expectations["black_border"] = expected_black_border
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
            expected_video_parameters,
            expected_video_full_screen,
            expected_video_saturation,
            expected_video_sound_effects,
            expected_video_sound_effects_softness,
            expected_white_brightness,
        )
        if not self.profile.supports_color_mode_readback and (
            expected_zero_kelvin or expected_music_auto_color or any(value is not None for value in color_expectations)
        ):
            return False
        query_power = expected_on is not None
        query_brightness = expected_brightness is not None
        query_color = self.profile.supports_color_mode_readback and (
            expected_zero_kelvin or expected_music_auto_color or any(value is not None for value in color_expectations)
        )
        display_settings = (
            frozenset({"white_balance", "blank_screen"})
            | (
                {"black_border"}
                if video_control_states(self.profile, self)["black_border"] is CapabilityState.SUPPORTED
                else set()
            )
            if refresh_display_settings is True
            else frozenset()
            if refresh_display_settings is False
            else refresh_display_settings
        )
        if not display_settings <= {"white_balance", "blank_screen", "black_border"}:
            raise ValueError("unknown display setting requested for refresh")
        query_white_balance = (
            expected_white_balance is not None
            or expected_white_balance_flag is not None
            or "white_balance" in display_settings
        )
        query_blank_screen = (
            expected_blank_screen is not None
            or expected_blank_screen_policy is not None
            or "blank_screen" in display_settings
        )
        query_black_border = expected_black_border is not None or "black_border" in display_settings
        if (
            query_black_border
            and video_control_states(self.profile, self)["black_border"] is not CapabilityState.SUPPORTED
        ):
            return False
        query_relative_brightness = expected_relative_brightness is not None or refresh_relative_brightness
        if refresh_all:
            query_power = query_brightness = True
            query_color = self.profile.supports_color_mode_readback
        if not any(
            (
                query_power,
                query_brightness,
                query_color,
                query_white_balance,
                query_blank_screen,
                query_black_border,
                query_relative_brightness,
            )
        ):
            query_power = True
            query_color = self.profile.supports_color_mode_readback
        current_intent = self._control_arbiter.current_task_intent
        intent = ControlIntent.USER if current_intent is None else current_intent
        async with async_control_intent(self, intent):
            client = self._client
            if client is None or not client.is_connected or generation != self._profile_generation:
                return False
            authorization_generation = self._authorization_generation
            profile = self._authorization_profile()
            states = video_control_states(self.profile, self)
            states["white_balance"] = white_balance_readback_state(self.profile, self)
            confirmed_controls = {
                control
                for control in states
                if self.identity_fields_confirmed(video_identity_fields(self.profile, (control,)))
            }
            requested_registers = display_settings | {
                control
                for control, requested in (
                    ("white_balance", expected_white_balance is not None or expected_white_balance_flag is not None),
                    ("blank_screen", expected_blank_screen is not None or expected_blank_screen_policy is not None),
                    ("black_border", expected_black_border is not None),
                    ("relative_brightness", expected_relative_brightness is not None or refresh_relative_brightness),
                )
                if requested
            }
            if any(states[control] is not CapabilityState.SUPPORTED for control in requested_registers):
                return False
            if requested_registers - confirmed_controls:
                return False
            if refresh_all:
                query_white_balance = (
                    "white_balance" in confirmed_controls and states["white_balance"] is CapabilityState.SUPPORTED
                )
                query_blank_screen = (
                    "blank_screen" in confirmed_controls and states["blank_screen"] is CapabilityState.SUPPORTED
                )
                query_black_border = (
                    "black_border" in confirmed_controls and states["black_border"] is CapabilityState.SUPPORTED
                )
                query_relative_brightness = (
                    "relative_brightness" in confirmed_controls
                    and states["relative_brightness"] is CapabilityState.SUPPORTED
                )
            query_power = query_power and profile.can_read(ReadDomain.POWER)
            query_brightness = query_brightness and profile.can_read(ReadDomain.BRIGHTNESS)
            query_color = query_color and profile.supports_color_mode_readback
            queried_domains = {
                domain
                for domain, enabled in (
                    (ReadDomain.POWER, query_power),
                    (ReadDomain.BRIGHTNESS, query_brightness),
                    (
                        ReadDomain.COLOUR_MODE if profile.can_read(ReadDomain.COLOUR_MODE) else ReadDomain.MODE,
                        query_color,
                    ),
                    (ReadDomain.DISPLAY_SETTING, query_white_balance or query_blank_screen or query_black_border),
                    (ReadDomain.RELATIVE_BRIGHTNESS, query_relative_brightness),
                )
                if enabled and profile.can_read(domain)
            }
            if required_domains is not None:
                queried_domains.update(required_domains & profile.read_domains & _OPTIONAL_CONTROL_DOMAINS)
            awaited_domains = queried_domains if required_domains is None else queried_domains & required_domains
            initial_domain_baselines = {domain: self._domain_revisions.get(domain, 0) for domain in awaited_domains}
            deadline = time.monotonic() + timeout
            optional_baselines: dict[str, int] = {}
            for attempt in range(2):
                if time.monotonic() >= deadline:
                    break
                query_options: dict[str, Any] = {"deadline": deadline}
                if refresh_all or required_domains is not None:
                    query_options = {
                        "deadline": deadline,
                        "required_domains": frozenset(awaited_domains)
                        | (
                            {ReadDomain.DISPLAY_SETTING}
                            if requested_registers & {"white_balance", "blank_screen", "black_border"}
                            else set()
                        )
                        | ({ReadDomain.RELATIVE_BRIGHTNESS} if "relative_brightness" in requested_registers else set()),
                        "optional_baselines": optional_baselines,
                    }
                if query_segments is not None:
                    query_options["query_segments"] = query_segments
                field_baselines = {field: self._field_revisions.get(field, 0) for field in expectations}
                if refresh_all and query_black_border and required_domains is None:
                    field_baselines["black_border"] = self._field_revisions.get("black_border", 0)
                if refresh_display_settings:
                    display_fields: list[str] = []
                    if query_black_border and "black_border" in display_settings:
                        display_fields.append("black_border")
                    if query_white_balance and "white_balance" in display_settings:
                        display_fields.extend(
                            ("white_balance_scalar",)
                            if self.profile.video_white_balance_representation == "scalar"
                            else _WHITE_BALANCE_GAIN_FIELDS
                        )
                    if self.profile.supports_blank_screen and "blank_screen" in display_settings:
                        display_fields.extend(("blank_screen", *_BLANK_SCREEN_POLICY_FIELDS))
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
                    if query_white_balance or query_blank_screen or query_black_border or query_relative_brightness:
                        ok = await self._send_state_queries(
                            query_power=query_power,
                            query_brightness=query_brightness,
                            query_color_mode=query_color,
                            query_white_balance=query_white_balance,
                            query_blank_screen=query_blank_screen,
                            query_black_border=query_black_border,
                            query_relative_brightness=query_relative_brightness,
                            **query_options,
                        )
                    else:
                        ok = await self._send_state_queries(
                            query_power=query_power,
                            query_brightness=query_brightness,
                            query_color_mode=query_color,
                            **query_options,
                        )
                if not ok:
                    if (
                        generation == self._profile_generation
                        and authorization_generation == self._authorization_generation
                    ):
                        await self._disconnect_if_current_locked(client)
                    return False
                attempt_deadline = deadline if attempt else min(deadline, (time.monotonic() + deadline) / 2)
                if await self._wait_for_revisions(field_baselines, domain_baselines, attempt_deadline):
                    if not expectations or all(
                        getattr(self, field) == expected for field, expected in expectations.items()
                    ):
                        # A background poll closes its connection on return. Collect delayed
                        # optional replies first; their silence never rejects the basic poll.
                        if optional_baselines and not await self._wait_for_revisions(optional_baselines, {}, deadline):
                            self._expire_optional_observations(optional_baselines)
                        return (
                            generation == self._profile_generation
                            and authorization_generation == self._authorization_generation
                            and self._client is client
                            and client.is_connected
                        )
                if generation != self._profile_generation or authorization_generation != self._authorization_generation:
                    return False
                if time.monotonic() >= deadline:
                    break
            if optional_baselines:
                self._expire_optional_observations(optional_baselines)
            if any(
                self._domain_revisions.get(domain, 0) <= baseline
                for domain, baseline in initial_domain_baselines.items()
                if domain not in _OPTIONAL_CONTROL_DOMAINS
            ):
                await self._disconnect_if_current_locked(client)
            return False

    async def async_preview_preflight(self, *, timeout: float = 2 * CONNECTION_SETUP_TIMEOUT) -> None:
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        deadline = asyncio.get_running_loop().time() + timeout

        async def disconnect_failed_client(client: BleakClient) -> None:
            try:
                async with asyncio.timeout_at(deadline):
                    await client.disconnect()
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("Disconnect of failed BLE client did not complete: %s", type(err).__name__)

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
            async with self._lock:
                client = await self._ensure_connected()
                baseline = self._field_revisions.get("segment_colors", 0)
                ok = await self._send_state_queries(
                    query_power=False,
                    query_brightness=False,
                    query_color_mode=False,
                    query_segments=True,
                    deadline=time.monotonic() + timeout,
                )
            return (
                ok
                and self._client is client
                and client.is_connected
                and not self._segment_query_incomplete
                and self._field_revisions.get("segment_colors", 0) > baseline
            )

    async def async_preview_write(
        self,
        packet: bytes,
        *,
        before_write: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        async with async_control_intent(self, ControlIntent.PREVIEW):
            async with self._lock:
                self._require_not_dreamview_claimed()
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
                    on_write=on_write,
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
        retry_allowed: Callable[[], bool] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        packet_state_values: Sequence[Mapping[str, Any]] | None = None,
        packet_write_guard: Callable[[int], None] | None = None,
        packet_on_write: Callable[[int], None] | None = None,
        require_upload_ack: bool = False,
        upload_ack_index: int | None = None,
        writer: ProfileWriter | None = None,
        packet_validator: Callable[[bytes, ModelProfile], None] = require_profile_packet,
        final_packet: bytes | None = None,
        before_final: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Write a transaction; an injected writer owns its connection and never retries.

        ACKs correlate by subscription, profile generation and completed subtype.
        The wire has no transaction ID: a late same-subtype ACK arriving during a
        later final attempt cannot be distinguished from that attempt's response.
        """
        if self.hass.is_stopping:
            raise RuntimeError("Home Assistant is stopping")
        if not packets:
            raise ValueError("effect sequence must contain at least one packet")
        if packet_state_values is not None and len(packet_state_values) != len(packets):
            raise ValueError("packet state must match the effect sequence length")
        subtype = ack_mode = None
        protocol = 0
        if require_upload_ack:
            if type(upload_ack_index) is not int or not 0 <= upload_ack_index < len(packets):
                raise ValueError("Upload ACK requires a valid final packet index")
            subtype = upload_ack_subtype(packets, upload_ack_index, self.model, profile=self.profile)
            ack_mode = upload_ack_mode(packets, upload_ack_index, self.model, profile=self.profile)
            protocol = packets[upload_ack_index][0]
        elif upload_ack_index is not None:
            raise ValueError("Upload ACK index requires require_upload_ack")
        async with async_control_intent(self, intent):
            # Preview writers acquire _lock themselves. The existing control intent
            # still owns the entire upload/ACK/selector transaction.
            async with self._lock if writer is None else nullcontext():
                self._require_not_dreamview_claimed()
                attempts = EFFECT_SEQUENCE_ATTEMPTS if writer is None else 1
                upload_attempted = False
                for attempt in range(1, attempts + 1):
                    future: asyncio.Future[bool] | None = None
                    try:
                        if writer is None:
                            async with asyncio.timeout(CONNECTION_SETUP_TIMEOUT):
                                client = await self._ensure_connected()
                        else:
                            if self._client is None or not self._client.is_connected:
                                raise BleakError("Device disconnected during preview")
                            client = self._client
                        token, generation = self._notification_token, self._profile_generation
                        self._require_not_dreamview_claimed()

                        def check_connection(
                            client: BleakClient = client,
                            token: object | None = token,
                            generation: int = generation,
                        ) -> None:
                            self._require_not_dreamview_claimed()
                            if (
                                self._client is not client
                                or not client.is_connected
                                or self._notification_token is not token
                            ):
                                raise BleakError("Device disconnected during effect upload")
                            if self._profile_generation != generation:
                                raise ValueError("Device profile changed during effect upload")

                        if attempt_started is not None:
                            await attempt_started(attempt)
                        self._require_not_dreamview_claimed()
                        if before_write is not None:
                            await before_write()
                        for index, packet in enumerate(packets, start=1):
                            if (
                                index > 1
                                and self.profile.packet_write_delay > 0
                                and not (require_upload_ack and index - 2 == upload_ack_index)
                            ):
                                await asyncio.sleep(self.profile.packet_write_delay)

                            def guard(
                                index: int = index,
                                client: BleakClient = client,
                                token: object | None = token,
                                generation: int = generation,
                            ) -> None:
                                nonlocal future, upload_attempted
                                self._require_not_dreamview_claimed()
                                if self._profile_generation != generation:
                                    raise ValueError("Device profile changed during effect upload")
                                if require_upload_ack or writer is not None:
                                    check_connection()
                                if write_guard is not None:
                                    write_guard()
                                if packet_write_guard is not None:
                                    packet_write_guard(index - 1)
                                if require_upload_ack and packets[index - 1][0] == protocol:
                                    upload_attempted = True
                                if subtype is not None and index - 1 == upload_ack_index:
                                    # After transforms and guards, immediately before the
                                    # final physical attempt: synchronous replies are valid.
                                    future = asyncio.get_running_loop().create_future()
                                    self._upload_ack = (client, token, generation, subtype, ack_mode, protocol, future)

                            values = state_values if packet_state_values is None else packet_state_values[index - 1]

                            def commit(index: int = index) -> None:
                                if packet_on_write is not None:
                                    packet_on_write(index - 1)

                            if writer is None:
                                await self._async_write_packet(
                                    client,
                                    packet,
                                    arm_expected=True,
                                    before_write=guard,
                                    state_values=values,
                                    expected_values=expected_values,
                                    packet_validator=packet_validator,
                                    on_write=commit if packet_on_write is not None else None,
                                )
                            else:
                                await writer(
                                    packet,
                                    write_guard=guard,
                                    state_values=values,
                                    expected_values=expected_values,
                                    **({"on_write": commit} if packet_on_write is not None else {}),
                                )
                            self._renew_foreground_lease()
                            if require_upload_ack and index - 1 == upload_ack_index:
                                if future is None:
                                    raise RuntimeError("Upload writer did not run the physical-write guard")
                                async with asyncio.timeout(UPLOAD_ACK_TIMEOUT):
                                    while not future.done():
                                        check_connection()
                                        await asyncio.wait((future,), timeout=0.05)
                                check_connection()
                                if not future.result():
                                    raise RuntimeError(f"Device rejected {protocol:02X} upload")
                                self._upload_ack = None
                            if progress is not None:
                                await progress(index)
                        break
                    except asyncio.CancelledError:
                        if writer is None and self._encryption is not None:
                            await self._disconnect_locked()
                        raise
                    except (BleakError, TimeoutError) as err:
                        if writer is not None:
                            raise
                        self._upload_ack = None
                        await self._disconnect_locked()
                        if isinstance(err, DreamviewClaimedError):
                            raise
                        if self.hass.is_stopping:
                            raise RuntimeError("Home Assistant is stopping") from err
                        if (
                            attempt == attempts
                            or (upload_attempted and not self.profile.effect_retry_after_upload)
                            or (retry_allowed is not None and not retry_allowed())
                        ):
                            raise
                        error = str(err).lower()
                        if isinstance(err, TimeoutError) or "already shutdown" in error or "not found" in error:
                            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    finally:
                        self._upload_ack = None
                        if future is not None:
                            future.cancel()
                if final_packet is not None:
                    if not require_upload_ack and self.profile.packet_write_delay > 0:
                        await asyncio.sleep(self.profile.packet_write_delay)
                    if before_final is not None:
                        await before_final()

                    def final_guard() -> None:
                        check_connection()
                        if write_guard is not None:
                            write_guard()

                    if writer is None:
                        await self._async_write_packet(
                            client,
                            final_packet,
                            arm_expected=True,
                            before_write=final_guard,
                            expected_values=expected_values,
                            packet_validator=packet_validator,
                        )
                    else:
                        await writer(
                            final_packet,
                            write_guard=final_guard,
                            expected_values=expected_values,
                        )
                    self._renew_foreground_lease()
                    if progress is not None:
                        await progress(len(packets) + 1)

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
                    "video_parameters",
                    "video_full_screen",
                    "video_saturation",
                    "video_sound_effects",
                    "video_sound_effects_softness",
                    "white_brightness",
                }
            )
        )
        query_white_balance = any(field.startswith("white_balance_") for field in expectations)
        query_blank_screen = any(field.startswith("blank_screen") for field in expectations)
        query_black_border = "black_border" in expectations
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
                deadline = time.monotonic() + timeout
                ok = await self._send_state_queries(
                    query_power=query_power,
                    query_brightness=query_brightness,
                    query_color_mode=query_color,
                    query_white_balance=query_white_balance,
                    query_blank_screen=query_blank_screen,
                    query_black_border=query_black_border,
                    query_relative_brightness=query_relative_brightness,
                    deadline=deadline,
                )
        if not ok or self._client is not client:
            return None
        if not await self._wait_for_revisions(
            field_baselines,
            {},
            deadline,
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
        self._require_not_shutdown()
        self._stop_keep_alive()
        self._identity_retries = 0
        name = f"{DOMAIN} keep-alive {self.address}"
        if self.config_entry is not None:
            self._keep_alive_task = self.config_entry.async_create_background_task(
                self.hass, self._keep_alive_loop(), name
            )
        else:
            self._keep_alive_task = self.hass.async_create_background_task(self._keep_alive_loop(), name)

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
                            try:
                                await self._send_identity_queries()
                            except BleakError:
                                client = self._client
                                if client is not None:
                                    await self._disconnect_if_current_locked(client)
                                break
                    full = self._keep_alive_ticks % STATE_QUERY_EVERY_N_KEEP_ALIVES == 0
                    client = self._client
                    generation = self._profile_generation
                    authorization_generation = self._authorization_generation
                    if self.connection_mode == CONNECTION_MODE_HOLD and full:
                        ok = await self._refresh_connected_state(
                            refresh_all=True,
                            query_segments=False,
                            required_domains=self.profile.setup_required_read_domains,
                        )
                    else:
                        async with self._lock:
                            ok = await self._send_state_queries(
                                query_power=True,
                                query_brightness=full,
                                query_color_mode=full and self.profile.supports_color_mode_readback,
                                required_domains=(
                                    frozenset({ReadDomain.POWER})
                                    if self.connection_mode == CONNECTION_MODE_HOLD
                                    else self.profile.setup_required_read_domains
                                ),
                            )
                    if not ok:
                        if (
                            generation != self._profile_generation
                            or authorization_generation != self._authorization_generation
                        ):
                            continue
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
        attempts = self._static_write_attempts
        try:
            await self._async_send_command(packet, write_guard=write_guard, state_values=state_values)
        except Exception:
            if self._static_write_attempts != attempts and self.profile.can_read(ReadDomain.SEGMENTS):
                try:
                    async with asyncio.timeout(2.0):
                        await self.async_refresh_segments()
                except Exception:
                    _LOGGER.debug("Static write reconciliation failed", exc_info=True)
            raise

    async def _async_send_command(
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
                self._require_not_dreamview_claimed()
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
                        if isinstance(err, DreamviewClaimedError):
                            raise
                        if attempt == 2:
                            _LOGGER.error("Failed to send to %s after 3 attempts", self.address)
                            raise
                        s = str(err).lower()
                        if "already shutdown" in s or "not found" in s:
                            await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

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
            "raw": "" if self._dreamview_private_write else data[:PACKET_LOG_RAW_BYTES_LIMIT].hex(),
            "redacted": self._dreamview_private_write,
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
            async with self._lock:
                await self._disconnect_locked()

    async def _disconnect_locked(self, *, clear_cache: bool = False) -> None:
        client = self._client
        self._static_rgb_known = False
        # Invalidate callbacks and keys before disconnect can yield or be cancelled.
        self._music_palette = self._music_body = None
        self.video_parameters = None
        self._notification_token = None
        if self._encryption is not None:
            self._encryption.reset()
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        self._intentional_disconnect_client = client
        try:
            try:
                if clear_cache and client is not None:
                    # Reject poisoned-client writes and callbacks before native clearing yields.
                    self._clear_client_state(client)
                    await async_clear_gatt_cache(client)
            finally:
                if client and client.is_connected:
                    if clear_cache:
                        try:
                            async with asyncio.timeout(VALIDATION_DISCONNECT_TIMEOUT):
                                await client.disconnect()
                        except Exception:
                            _LOGGER.debug("Error disconnecting during GATT recovery for %s", self.address)
                    else:
                        await client.disconnect()
        except BleakError, TimeoutError:
            _LOGGER.debug("Error disconnecting from %s", self.address)
        finally:
            self._clear_client_state(client)
            if (
                client is not None
                and client.is_connected
                and is_dreamview_claimed(
                    self.hass, self.config_entry.entry_id if self.config_entry is not None else None, self
                )
            ):
                # Retain a failed physical link so handover cannot mistake cleared state for release.
                self._client = client
            if self._intentional_disconnect_client is client:
                self._intentional_disconnect_client = None


def clear_availability_log_state(hass: HomeAssistant, address: str) -> None:
    """Forget deduplication state when a config entry is removed."""
    unavailable = hass.data.get(DOMAIN, {}).get(AVAILABILITY_UNAVAILABLE_DATA_KEY)
    if isinstance(unavailable, set):
        unavailable.discard(address)
