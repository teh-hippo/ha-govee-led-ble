"""Segment observations, refresh, painting and brightness for the Govee BLE coordinator."""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .const import ReadDomain, get_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .light_commands import (
    SegmentColorGroup,
    build_segment_brightness,
    build_segment_paint,
    kelvin_rendering_matches,
    parse_static_write,
)

_LOGGER = logging.getLogger(__name__)


class _SegmentMixin(_CoordinatorBase):
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
                and not kelvin_rendering_matches(rendered, kelvin, self.profile)
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

    async def async_refresh_segments(self, *, timeout: float = 2.0) -> bool:
        if (
            not self.profile.state_readable
            or not self.profile.supports_segments
            or not self.profile.can_read(ReadDomain.SEGMENTS)
        ):
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

    async def async_set_segment_kelvin(
        self, packet: bytes, *, requested_kelvin: int, write_guard: Callable[[], None] | None = None
    ) -> None:
        """Confirm settled rendering on the original subscription, without replaying the write."""
        profile = self.profile
        static = parse_static_write(packet, self.model, profile=profile)
        if static is None or static.kelvin is None or static.segment_mask is None:
            raise ValueError("Expected a masked Kelvin command")
        selected = {index for index in range(profile.segment_count) if static.segment_mask & (1 << index)}
        if not selected or static.segment_mask & ~profile.whole_device_mask:
            raise ValueError("Kelvin mask is outside the current geometry")
        if not profile.can_read(ReadDomain.SEGMENTS):
            if write_guard is None:
                await self.send_command(packet)
            else:
                await self.send_command(packet, write_guard=write_guard)
            return

        sent_kelvin = static.kelvin

        def rendering_matches(colors: set[tuple[int, int, int]]) -> bool:
            return len(colors) == 1 and kelvin_rendering_matches(next(iter(colors)), sent_kelvin, profile)

        started = time.monotonic()
        rounds = 0
        outcome = "failed"
        async with async_control_intent(self, ControlIntent.USER):
            if not await self.async_refresh_segments():
                raise RuntimeError("Failed to read segments before colour temperature write")
            client = self._client
            if client is None:
                raise RuntimeError("Kelvin transaction lost its connection")
            token = self._notification_token
            generation = self._profile_generation
            authorization = self._authorization_generation
            async with self._lock:

                def guard() -> None:
                    nonlocal outcome
                    if write_guard is not None:
                        write_guard()
                    if (
                        self._client is not client
                        or not client.is_connected
                        or self._notification_token is not token
                        or self.profile != profile
                        or self._profile_generation != generation
                        or self._authorization_generation != authorization
                    ):
                        outcome = "context_changed"
                        raise RuntimeError("Kelvin transaction connection or geometry changed")

                async def read_pages(deadline: float, *, mode: bool = False) -> None:
                    nonlocal outcome
                    guard()
                    baseline = {"color_mode": self._field_revisions.get("color_mode", 0)} if mode else {}
                    if not await self._send_state_queries(
                        query_power=False,
                        query_brightness=False,
                        query_color_mode=mode,
                        query_segments=True,
                        required_domains=frozenset({ReadDomain.SEGMENTS}),
                        deadline=deadline,
                    ) or (baseline and not await self._wait_for_revisions(baseline, {}, deadline)):
                        outcome = "incomplete_read"
                        raise RuntimeError("Failed to read complete Kelvin confirmation")
                    guard()

                try:
                    before_colors = list(self.segment_colors)
                    before_brightness = list(self.segment_brightness)
                    self._pending_kelvin = static.kelvin if static.whole_strip else None
                    guard()
                    attempts = self._static_write_attempts
                    deadline = time.monotonic() + 5.0
                    async with asyncio.timeout_at(deadline):
                        try:
                            await self._async_write_packet(
                                client, packet, arm_expected=True, before_write=guard, cleanup_deadline=deadline
                            )
                        except Exception:
                            outcome = "write_failed"
                            if self._static_write_attempts != attempts:
                                try:
                                    async with asyncio.timeout(2.0):
                                        await read_pages(min(deadline, time.monotonic() + 2.0))
                                except Exception:
                                    _LOGGER.debug("Failed Kelvin write reconciliation did not complete", exc_info=True)
                            raise
                        self._renew_foreground_lease()
                        while True:
                            kelvin_revision = self._field_revisions.get("color_temp_kelvin", 0)
                            await read_pages(deadline, mode=profile.kelvin_companion_uses_table)
                            rounds += 1
                            selected_colors = {self.segment_colors[index] for index in selected}
                            preserved = self.segment_brightness == before_brightness and all(
                                color == before_colors[index]
                                for index, color in enumerate(self.segment_colors)
                                if index not in selected
                            )
                            matches = rendering_matches(selected_colors)
                            if (
                                profile.segment_kelvin_renders_device_rgb
                                and static.whole_strip
                                and profile.static_readback_kelvin
                            ):
                                matches = matches and (
                                    self.color_temp_kelvin_source == "observed"
                                    and self._field_revisions.get("color_temp_kelvin", 0) > kelvin_revision
                                    and self.color_temp_kelvin == static.kelvin
                                )
                            mode_matches = (
                                not profile.kelvin_companion_uses_table or self.color_mode is ParsedMode.COLOUR
                            )
                            if preserved and matches and mode_matches:
                                if static.whole_strip and not profile.static_readback_kelvin:
                                    self.color_temp_kelvin = static.kelvin
                                    self.color_temp_kelvin_source = "retained"
                                outcome = (
                                    "confirmed_rendering"
                                    if not profile.static_readback_kelvin or not static.whole_strip
                                    else "confirmed"
                                )
                                return
                            outcome = "preservation_mismatch" if not preserved else "render_or_mode_mismatch"
                            await asyncio.sleep(0.25)
                finally:
                    self._pending_kelvin = None
                    if (
                        outcome not in {"confirmed", "confirmed_rendering"}
                        and static.whole_strip
                        and (not profile.segment_kelvin_renders_device_rgb or not profile.static_readback_kelvin)
                        and self.profile == profile
                        and self.segment_state_source == "observed"
                        and self.color_temp_kelvin_source != "observed"
                        and not rendering_matches(set(self.segment_colors))
                    ):
                        self._expected_state.pop("color_temp_kelvin", None)
                        self.color_temp_kelvin = None
                        self.color_temp_kelvin_source = "initial"
                        self.async_set_updated_data(self.data or {})
                    _LOGGER.debug(
                        "Kelvin verification model=%s requested=%s sent=%s mask=%x segments=%s table=%s "
                        "rounds=%s elapsed=%.3f outcome=%s",
                        self.model,
                        requested_kelvin,
                        static.kelvin,
                        static.segment_mask,
                        profile.segment_count,
                        profile.kelvin_companion_uses_table,
                        rounds,
                        time.monotonic() - started,
                        outcome,
                    )

    async def async_paint_segments(
        self, groups: list[SegmentColorGroup], *, write_guard: Callable[[], None] | None = None
    ) -> None:
        async with self.async_mask_transaction():
            await self._async_paint_segments(groups, write_guard=write_guard)

    async def _async_paint_segments(
        self, groups: list[SegmentColorGroup], *, write_guard: Callable[[], None] | None = None
    ) -> None:
        """Optimistically paint colour groups onto the segment slots.

        Each group pairs 1-based segment indices with an RGB colour. The device does not
        publish segment state after writes, so the complete segment query verifies the
        optimistic state without resending or rolling back a completed write.
        """
        resolved: list[SegmentColorGroup] = [(list(segments), rgb) for segments, rgb in groups]
        packets = build_segment_paint(resolved, self.model, profile=self.profile)
        expected_colors = {segment - 1: rgb for segments, rgb in resolved for segment in segments}
        expected_brightness: list[int] | None = None
        attempted = False
        async with async_control_intent(self, ControlIntent.USER):
            segment_revision = self._field_revisions.get("segment_colors", 0)
            try:
                for packet in packets:

                    def before_write() -> None:
                        nonlocal attempted, expected_colors, expected_brightness
                        if write_guard is not None:
                            write_guard()
                        # Historical observations cannot prove pre-write sibling state.
                        if (
                            not attempted
                            and self.segment_state_source == "observed"
                            and self._field_revisions.get("segment_colors", 0) > segment_revision
                        ):
                            expected_colors = dict(enumerate(self.segment_colors)) | expected_colors
                            expected_brightness = list(self.segment_brightness)
                        attempted = True

                    attempts = self._static_write_attempts
                    try:
                        await self.send_command(packet, write_guard=before_write)
                    except Exception:
                        # A later pre-write failure still leaves earlier groups applied.
                        if attempted and self._static_write_attempts == attempts:
                            try:
                                async with asyncio.timeout(2.0):
                                    await self.async_refresh_segments()
                            except Exception:
                                _LOGGER.debug("Partial segment paint reconciliation failed", exc_info=True)
                        raise
                if self.profile.can_read(ReadDomain.SEGMENTS) and (
                    not await self.async_refresh_segments()
                    or any(self.segment_colors[index] != rgb for index, rgb in expected_colors.items())
                    or (expected_brightness is not None and self.segment_brightness != expected_brightness)
                ):
                    raise RuntimeError("Failed to confirm segment paint")
            finally:
                if attempted:
                    self.async_set_updated_data(self.data or {})

    async def async_set_segment_brightness(
        self, segments: list[int], brightness: int, *, write_guard: Callable[[], None] | None = None
    ) -> None:
        async with self.async_mask_transaction():
            await self._async_set_segment_brightness(segments, brightness, write_guard=write_guard)

    async def _async_set_segment_brightness(
        self, segments: list[int], brightness: int, *, write_guard: Callable[[], None] | None = None
    ) -> None:
        segments = list(segments)
        value = max(0, min(100, brightness))
        packet = build_segment_brightness(segments, value, self.model, profile=self.profile)
        expected_brightness = {segment - 1: value for segment in segments}
        expected_colors: list[tuple[int, int, int]] | None = None
        attempted = False

        def before_write() -> None:
            nonlocal attempted, expected_colors, expected_brightness
            if write_guard is not None:
                write_guard()
            if (
                not attempted
                and self.segment_state_source == "observed"
                and self._field_revisions.get("segment_colors", 0) > segment_revision
            ):
                expected_brightness = dict(enumerate(self.segment_brightness)) | expected_brightness
                expected_colors = list(self.segment_colors)
            attempted = True

        async with async_control_intent(self, ControlIntent.USER):
            segment_revision = self._field_revisions.get("segment_colors", 0)
            try:
                await self.send_command(packet, write_guard=before_write)
                if self.profile.can_read(ReadDomain.SEGMENTS) and (
                    not await self.async_refresh_segments()
                    or any(self.segment_brightness[index] != value for index, value in expected_brightness.items())
                    or (expected_colors is not None and self.segment_colors != expected_colors)
                ):
                    raise RuntimeError("Failed to confirm segment brightness")
            finally:
                if attempted:
                    self.async_set_updated_data(self.data or {})
