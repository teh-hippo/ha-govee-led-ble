"""Notification decoding and expected-state tracking for the Govee BLE coordinator."""

import logging
import time
from dataclasses import replace
from math import ceil
from typing import Any

from bleak import BleakClient

from .const import (
    PERCENT_BRIGHTNESS_STATUS_GRAMMARS,
    ReadDomain,
    get_profile,
)
from .coordinator_base import _CoordinatorBase
from .coordinator_expectations import expectations_from_packet
from .coordinator_status import (
    ParsedMode,
    StatusDomain,
    decode_status_frame_result,
    parse_color_mode,
    status_is_authorized,
)
from .generated_protocol_adapter import (
    BulkStatusCollector,
    build_bulk_status_query,
    is_bulk_status_frame,
    parse_command_ack_result,
    parse_command_result,
    parse_physical_ic_count,
    parse_zone_notification,
    upload_ack_success,
)
from .h6099_controls import h6099_control_status
from .light_commands import (
    kelvin_companion_rgb,
)
from .music_semantics import (
    music_body_params_for_mode,
)
from .protocol_core import decode_wire_brightness
from .protocol_h6179 import ParsedH6179Status
from .protocol_h6199 import parse_h6199_control

_LOGGER = logging.getLogger(__name__)

EXPECTED_STATE_TTL = 2.0
_COLOR_MODE_FIELDS = (
    "video_full_screen",
    "video_parameters",
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

_OPTIONAL_CONTROL_DOMAINS = frozenset({ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH})


class _NotificationMixin(_CoordinatorBase):
    """Decodes status notifications and reconciles them with recently written values."""

    def _arm_expected(self, packet: bytes) -> None:
        expectations = expectations_from_packet(
            packet,
            self.model,
            static_echoes_color=self.profile.static_readback_echoes_color,
            profile=self.profile,
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
        parsed = parse_color_mode(generated, self.model, profile=self.profile)
        if (
            parsed.mode is ParsedMode.COLOUR
            and self.profile.static_readback_gradual
            and parsed.multi_effect_flag not in (0, 1)
        ):
            raise ValueError("invalid static gradual flag")
        if parsed.mode is ParsedMode.DIY:
            mode_detail = parsed.diy_code
        elif parsed.mode is ParsedMode.COLOUR and self.profile.static_readback_echoes_color:
            mode_detail = parsed.raw_mode if self.profile.status_grammar == "H6179" else parsed.multi_effect_flag
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
            if parsed.music_mode is None:
                self.music_mode = "off"
                self.effect = self.diy_code = None
                self.video_mode = "off"
                observed.extend(("effect", "diy_code"))
                accept_parameters = False
            elif self._accept_expected("music_mode", parsed.music_mode):
                if parsed.music_mode != self.music_mode:
                    self._music_palette = self._music_body = None
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
        if self.music_mode == "off":
            self._music_palette = self._music_body = None
        if accept_parameters:
            if parsed.mode is ParsedMode.MUSIC and parsed.music_color_present and parsed.music_color is None:
                if self._accept_expected("music_color", None):
                    self.music_color = None
                    observed.append("music_color")
            for attr in _COLOR_MODE_FIELDS:
                if attr == "music_color" and not parsed.music_color_present:
                    continue
                if (value := getattr(parsed, attr)) is not None:
                    if self._accept_expected(attr, value):
                        setattr(self, attr, value)
                        observed.append(attr)
        if parsed.mode is ParsedMode.COLOUR:
            if self.profile.static_readback_gradual:
                # AA05 describes the colour mode; only AAA3 confirms a setting write.
                self.static_gradual = bool(parsed.multi_effect_flag)
                observed.append("static_gradual")
            if self.profile.status_grammar == "H6199":
                values = parse_h6199_control(generated)
                for field, value in values.items():
                    setattr(self, field, value)
                observed.extend(values)
            static_values: dict[str, Any] = {}
            if parsed.rgb_color is not None and self.profile.static_readback_echoes_color:
                static_values["rgb_color"] = parsed.rgb_color
            if self.profile.static_readback_kelvin and (
                parsed.color_temp_kelvin is not None or self.profile.static_readback_zero_kelvin_is_rgb
            ):
                static_values["color_temp_kelvin"] = parsed.color_temp_kelvin
            accepted_values = dict(static_values)
            if "rgb_color" in static_values and "color_temp_kelvin" not in static_values:
                kelvin = self.color_temp_kelvin
                if kelvin is None or static_values["rgb_color"] != kelvin_companion_rgb(kelvin, self.profile):
                    accepted_values["color_temp_kelvin"] = None
            if self._accept_expected_values(accepted_values):
                if (
                    self.profile.status_grammar == "H601C"
                    and parsed.color_temp_kelvin is not None
                    and self.rgb_color_source == "observed"
                ):
                    self.rgb_color_source = "retained"
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

    def _handle_bulk_notification(self, frame: bytes) -> bool:
        if not is_bulk_status_frame(frame, self.profile):
            return False
        collector = self._bulk_collector
        if collector is None:
            self._record_packet("rx", frame, outcome="rejected", reason="unsolicited_bulk_status", parser="h60a_bulk")
            return True
        if self._bulk_query_deadline is not None and time.monotonic() >= self._bulk_query_deadline:
            self._bulk_collector = None
            self._record_packet("rx", frame, outcome="rejected", reason="expired_bulk_status", parser="h60a_bulk")
            return True
        result = collector.feed(frame)
        entry = self._record_packet(
            "rx",
            frame,
            outcome="rejected" if result.rejection else "parsed",
            reason=result.rejection.value if result.rejection else "bulk_status_fragment",
            parser=result.parser,
        )
        if result.parsed is None:
            return True
        try:
            records = result.parsed.records
            for record in records:
                domain = getattr(record.domain, "name", None)
                if domain == "colour_mode":
                    parse_color_mode(record, self.model, profile=self.profile)
                elif domain == "power" and record.body.is_on not in (0, 1):
                    raise ValueError("Bulk power flag is invalid")
                elif domain == "brightness" and not 0 <= record.body.percent <= 100:
                    raise ValueError("Bulk brightness is outside percentage bounds")
                elif domain == "power_on_behaviour" and getattr(record.body.state, "name", None) is None:
                    raise ValueError("Bulk power-on behaviour is unknown")
            for record in records:
                domain = getattr(record.domain, "name", None)
                if domain == "colour_mode" and self.profile.supports_color_mode_readback:
                    self._mark_received(StatusDomain.COLOUR_MODE, *self._apply_color_mode_payload(record))
                elif domain == "power" and self.profile.can_read(ReadDomain.POWER):
                    value = bool(record.body.is_on)
                    if self._accept_expected("is_on", value):
                        self.is_on = value
                        self._mark_received(StatusDomain.POWER, "is_on")
                elif domain == "brightness" and self.profile.can_read(ReadDomain.BRIGHTNESS):
                    percent = int(record.body.percent)
                    if self._accept_expected("brightness_pct", percent):
                        self.brightness_pct = percent
                        self._mark_received(StatusDomain.BRIGHTNESS, "brightness_pct")
                elif domain == "zone_enable":
                    zone_values: dict[str, bool] = {
                        name: bool(getattr(record.body, name))
                        for name in ("panel_enabled", "ring_enabled")
                        if name in self.profile.boolean_controls
                    }
                    self.boolean_control_state.update(zone_values)
                    self._mark_received(StatusDomain.OTHER, *(f"boolean_{name}" for name in zone_values))
                elif domain == "power_on_behaviour" and self.profile.supports_power_on_behaviour:
                    self.power_on_behaviour = record.body.state.name
                    self._mark_received(StatusDomain.OTHER, "power_on_behaviour")
            self._bulk_query_incomplete = False
            self._bulk_collector = None
            self._mark_received(StatusDomain.OTHER, "bulk_status")
            self.async_set_updated_data(self.data or {})
        except ValueError:
            collector.failed = True
            entry.update(outcome="rejected", reason="semantic_rejected")
            _LOGGER.debug("Rejected complete bulk status for %s", self.model, exc_info=True)
        return True

    async def _async_read_bulk_status(
        self, client: BleakClient, *, deadline: float, domains: tuple[str, ...] | None = None
    ) -> bool:
        if self._bulk_query_incomplete:
            return False
        packet = build_bulk_status_query(self._authorization_profile(), domains=domains)
        baseline = {"bulk_status": self._field_revisions.get("bulk_status", 0)}
        generation, token = self._profile_generation, self._notification_token
        attempted = succeeded = False

        def before_write() -> None:
            nonlocal attempted
            attempted = True
            self._bulk_collector = BulkStatusCollector()
            self._bulk_query_deadline = deadline
            self._bulk_query_incomplete = True

        try:
            await self._async_write_packet(client, packet, before_write=before_write, cleanup_deadline=deadline)
            succeeded = (
                await self._wait_for_revisions(baseline, {}, deadline)
                and generation == self._profile_generation
                and self._client is client
                and client.is_connected
                and self._notification_token is token
                and not self._bulk_query_incomplete
            )
            return succeeded
        finally:
            if attempted and self._client is client and self._notification_token is token:
                self._bulk_collector = None
                self._bulk_query_deadline = None
                self._bulk_query_incomplete = not succeeded

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        frame = bytes(data)
        if self._encryption is not None:
            decoded_frame = self._encryption.decode(frame)
            if decoded_frame is None:
                return
            frame = decoded_frame
        self._last_rx_monotonic = time.monotonic()
        if self._handle_bulk_notification(frame):
            return
        zone_result = parse_zone_notification(frame, self.profile)
        if zone_result.parsed is not None:
            status = zone_result.parsed
            zone_values: dict[str, bool] = {
                name: bool(getattr(status, name))
                for name in ("panel_enabled", "ring_enabled")
                if name in self.profile.boolean_controls
            }
            self.boolean_control_state.update(zone_values)
            self._mark_received(StatusDomain.OTHER, *(f"boolean_{name}" for name in zone_values))
            if self.profile.can_read(ReadDomain.POWER) and self._accept_expected("is_on", bool(status.is_on)):
                self.is_on = bool(status.is_on)
                self._mark_received(StatusDomain.POWER, "is_on")
            self._record_packet("rx", frame, outcome="parsed", reason="native_zone_status", parser=zone_result.parser)
            self.async_set_updated_data(self.data or {})
            return
        ack = parse_command_ack_result(frame, self.model, profile=self.profile)
        if ack.parsed is not None:
            setting = self._setting_ack
            if setting is not None:
                client, token, opcode, future = setting
                if (
                    not ack.parsed.is_upload
                    and int(ack.parsed.opcode) == opcode
                    and self._client is client
                    and client.is_connected
                    and self._notification_token is token
                    and not future.done()
                ):
                    future.set_result(bool(ack.parsed.is_success))
            pending = self._upload_ack
            if pending is not None:
                client, token, generation, subtype, ack_mode, protocol, future = pending
                ack_success = upload_ack_success(ack.parsed, subtype, ack_mode, protocol=protocol)
                if (
                    ack_success is not None
                    and self._client is client
                    and client.is_connected
                    and self._notification_token is token
                    and self._profile_generation == generation
                    and not future.done()
                ):
                    future.set_result(ack_success)
            self._record_packet("rx", frame, outcome="parsed", reason="command_ack_parsed", parser=ack.parser)
            return
        if self._handle_dreamview_notification(frame):
            self._record_packet(
                "rx", frame, outcome="parsed", reason="dreamview_status_parsed", parser="h6099_dreamview_frame"
            )
            return
        if frame[:1] == b"\x33":
            command = parse_command_result(frame, self.model, profile=self.profile)
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
                "" if self._dreamview_private_write else frame.hex(),
            )
            return
        result = decode_status_frame_result(frame, self.model, profile=self.profile)
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
                "" if self._dreamview_private_write else frame.hex(),
            )
            return
        domain, payload = decoded.domain, decoded.payload
        if not status_is_authorized(decoded, self.profile):
            self._record_packet(
                "rx",
                frame,
                outcome="rejected",
                reason="unsupported_domain",
                parser=result.parser,
                domain=decoded.raw_domain,
            )
            return
        generated = decoded.generated
        packet_entry = self._record_packet(
            "rx",
            frame,
            outcome="parsed",
            reason="status_parsed",
            parser=result.parser,
            domain=decoded.raw_domain,
        )
        _LOGGER.debug(
            "rx %s domain=0x%02x payload=%s",
            self.model,
            decoded.raw_domain,
            "" if self._dreamview_private_write else payload.hex(),
        )
        try:
            observed: tuple[str, ...] = ()
            if self.profile.boolean_controls:
                from .generated_protocol_adapter import parse_boolean_control

                boolean_values = parse_boolean_control(generated, self.model, profile=self.profile)
                self.boolean_control_state.update(boolean_values)
                observed = tuple(f"boolean_{key}" for key in boolean_values)
            if self.profile.status_grammar == "H6199" and domain is not StatusDomain.COLOUR_MODE:
                values = parse_h6199_control(generated)
                if "gradient" in values:
                    # AA05 is a display observation, not confirmation of an A3 register write.
                    values["gradient_register"] = values["gradient"]
                for field, value in values.items():
                    setattr(self, field, value)
                observed = tuple(values)
            if getattr(generated.domain, "name", None) == "power_on_behaviour":
                value = getattr(generated.body.state, "name", None)
                if not generated.body.availability or value is None:
                    raise ValueError("Power-on behaviour is unavailable or unknown")
                self.power_on_behaviour = value
                observed = ("power_on_behaviour",)
            elif domain is StatusDomain.CONFIGURED_STRINGS:
                self._apply_configured_strings(int(generated.body.count))
                observed = ("configured_strings",)
            elif domain is StatusDomain.POWER:
                value = (
                    bool(generated.values["is_on"])
                    if isinstance(generated, ParsedH6179Status)
                    else bool(generated.body.is_on)
                )
                if self._accept_expected("is_on", value):
                    self.is_on = value
                    observed = ("is_on",)
            elif domain is StatusDomain.BRIGHTNESS:
                if not self.profile.can_read(ReadDomain.BRIGHTNESS):
                    return
                brightness_value = (
                    int(generated.values["brightness_pct"])
                    if isinstance(generated, ParsedH6179Status)
                    else int(generated.body.percent)
                    if self.profile.status_grammar in PERCENT_BRIGHTNESS_STATUS_GRAMMARS
                    else int(generated.body.register)
                    if hasattr(generated.body, "register")
                    else int(generated.body.brightness_pct)
                )
                if self.profile.brightness_wire_range is not None:
                    brightness_value = decode_wire_brightness(brightness_value, self.profile.brightness_wire_range)
                if not 0 <= brightness_value <= 100:
                    raise ValueError("brightness outside percentage range")
                if self._accept_expected("brightness_pct", brightness_value):
                    self.brightness_pct = brightness_value
                    observed = ("brightness_pct",)
            elif domain in {StatusDomain.COLOUR_MODE, StatusDomain.MODE}:
                if not self.profile.supports_color_mode_readback:
                    return
                observed = self._apply_color_mode_payload(generated)
            elif domain is StatusDomain.DISPLAY_SETTING:
                if generated.body.setting == 6 and self.profile.video_white_balance_representation == "scalar":
                    scalar_value = int(generated.body.payload.value)
                    if self._accept_expected("white_balance_scalar", scalar_value):
                        self.white_balance_scalar = scalar_value
                        observed = ("white_balance_scalar",)
                if generated.body.setting == 0 and self.profile.video_white_balance_representation == "position":
                    payload = generated.body.payload
                    values = {
                        "white_balance_flag": int(payload.current_flag),
                        "white_balance_red": int(payload.current_red),
                        "white_balance_blue": int(payload.current_blue),
                        "white_balance_default_flag": int(payload.reset_flag),
                        "white_balance_default_red": int(payload.reset_red),
                        "white_balance_default_blue": int(payload.reset_blue),
                    }
                    if self._accept_expected_values(values):
                        for field, value in values.items():
                            setattr(self, field, value)
                        observed = tuple(values)
                else:
                    blank_screen = (
                        bool(generated.body.payload.is_enabled)
                        if getattr(generated.body.setting, "name", None) == "blank_screen"
                        else None
                    )
                    if blank_screen is not None:
                        payload = generated.body.payload
                        values = {
                            "blank_screen": blank_screen,
                            "blank_screen_detection": int(payload.detection),
                            "blank_screen_low_brightness_duration_seconds": int(
                                payload.low_brightness_duration_seconds
                            ),
                            "blank_screen_same_tone_duration_seconds": int(payload.same_tone_duration_seconds),
                        }
                        # A filtered reply is not fresh state, but still invalidates recovery's write guard.
                        self._blank_screen_notification_revision += 1
                        # Legacy H6199 toggle writes retain live policy, even when the
                        # enable echo is stale. Full policy writes remain atomic.
                        if self.profile.status_grammar == "H6199" and not any(
                            field in self._expected_state for field in values if field != "blank_screen"
                        ):
                            for field, setting_value in values.items():
                                if field != "blank_screen":
                                    setattr(self, field, setting_value)
                        if self._accept_expected_values(values):
                            for field, setting_value in values.items():
                                setattr(self, field, setting_value)
                            observed = tuple(values)
                if (
                    getattr(generated.body.setting, "name", None) == "black_border"
                    and self.profile.supports_black_border
                ):
                    border = bool(generated.body.payload.is_enabled)
                    if self._accept_expected("black_border", border):
                        self.black_border = border
                        observed = ("black_border",)
            elif domain is StatusDomain.RELATIVE_BRIGHTNESS:
                zones = self.profile.video_brightness_zones
                if generated.body.edge_count != len(zones):
                    raise ValueError("relative-brightness topology mismatch")
                edges = tuple(int(getattr(generated.body, f"{zone}_percent")) for zone in zones)
                if any(not 0 <= value <= 100 for value in edges):
                    raise ValueError("relative-brightness edge is outside percentage bounds")
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
                version = (
                    generated.values["version"] if isinstance(generated, ParsedH6179Status) else generated.body.text
                )
                if self._observe_identity_field("fw_version", version):
                    observed = ("fw_version",)
            elif domain is StatusDomain.HARDWARE:
                version = (
                    generated.values["version"] if isinstance(generated, ParsedH6179Status) else generated.body.text
                )
                if self._observe_identity_field("hw_version", version):
                    observed = ("hw_version",)
            elif domain is StatusDomain.SUBORDINATE_20:
                if self._observe_identity_field("subordinate_20_version", generated.body.text or None):
                    observed = ("subordinate_20_version",)
            elif domain is StatusDomain.SUBORDINATE_21:
                if self._observe_identity_field("subordinate_21_version", generated.body.text or None):
                    observed = ("subordinate_21_version",)
            elif domain in _OPTIONAL_CONTROL_DOMAINS:
                control_values = h6099_control_status(decoded, self.profile)
                if not control_values:
                    return
                for field, control_value in control_values.items():
                    setattr(self, field, control_value)
                observed = tuple(control_values)
            elif domain is StatusDomain.PHYSICAL_IC_COUNT:
                if (count := parse_physical_ic_count(generated)) is not None:
                    self._observed_physical_ic_count = count
                    if self._client is not None and self._client.is_connected:
                        self._physical_ic_count_confirmed = True
                    if self.profile.physical_ic_count != count:
                        if self.profile.ic_per_segment is not None:
                            segments = min(
                                get_profile(self.model).segment_count,
                                max(1, ceil(count / self.profile.ic_per_segment)),
                            )
                            self.profile = replace(
                                self.profile,
                                physical_ic_count=count,
                                segment_count=segments,
                                whole_device_mask=(1 << segments) - 1,
                            )
                            if len(self.segment_colors) != segments:
                                self._profile_generation += 1
                                self._segment_query_generation = None
                                self._expected_state.clear()
                                self.segment_colors = [(255, 255, 255)] * segments
                                self.segment_brightness = [100] * segments
                                self.segment_state_source = "initial"
                                self.segment_state_observed_at = None
                                self.segment_brightness_readable = False
                                self._segment_groups_observed.clear()
                                self._segment_query_colors = self._segment_query_brightness = None
                        else:
                            self.profile = replace(self.profile, physical_ic_count=count)
                    for variant in self.profile.music_variants:
                        for spec in music_body_params_for_mode(variant.mode_code, self.profile):
                            if spec.key not in self._initialized_music_parameters:
                                setattr(self, spec.key, spec.default)
                                self._initialized_music_parameters.add(spec.key)
            self._mark_received(domain, *observed)
            self.async_set_updated_data(self.data or {})
        except IndexError, ValueError:
            packet_entry["outcome"] = "rejected"
            packet_entry["reason"] = "semantic_rejected"
            _LOGGER.debug(
                "Rejected %s status frame parser=%s reason=semantic_rejected raw=%s",
                self.model,
                result.parser,
                "" if self._dreamview_private_write else frame.hex(),
            )
