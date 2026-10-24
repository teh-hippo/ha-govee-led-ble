"""Segment painting and per-segment brightness for the Govee BLE coordinator."""

import asyncio
import logging
import time

from .const import ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .light_commands import (
    SegmentColorGroup,
    build_segment_brightness,
    build_segment_paint,
    kelvin_companion_rgb,
    parse_static_write,
)

_LOGGER = logging.getLogger(__name__)


class _SegmentMixin(_CoordinatorBase):
    async def async_set_segment_kelvin(self, packet: bytes, *, requested_kelvin: int) -> None:
        """Confirm settled rendering on the original subscription, without replaying the write."""
        profile = self.profile
        static = parse_static_write(packet, self.model, profile=profile)
        if static is None or static.kelvin is None or static.segment_mask is None:
            raise ValueError("Expected a masked Kelvin command")
        selected = {index for index in range(profile.segment_count) if static.segment_mask & (1 << index)}
        if not selected or static.segment_mask & ~profile.whole_device_mask:
            raise ValueError("Kelvin mask is outside the current geometry")
        expected = kelvin_companion_rgb(static.kelvin, profile)
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
                            if profile.segment_kelvin_renders_device_rgb:
                                rendered = next(iter(selected_colors))
                                matches = len(selected_colors) == 1 and rendered[0] >= 200 and rendered[1] >= 100
                                if static.whole_strip:
                                    matches = matches and (
                                        self.color_temp_kelvin_source == "observed"
                                        and self._field_revisions.get("color_temp_kelvin", 0) > kelvin_revision
                                        and self.color_temp_kelvin == static.kelvin
                                    )
                            else:
                                matches = selected_colors == {expected}
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
                        and not profile.segment_kelvin_renders_device_rgb
                        and self.profile == profile
                        and self.segment_state_source == "observed"
                        and self.color_temp_kelvin_source != "observed"
                        and set(self.segment_colors) != {expected}
                    ):
                        self._expected_state.pop("color_temp_kelvin", None)
                        self.color_temp_kelvin = None
                        self.color_temp_kelvin_source = "initial"
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

    async def async_paint_segments(self, groups: list[SegmentColorGroup]) -> None:
        async with self.async_mask_transaction():
            await self._async_paint_segments(groups)

    async def _async_paint_segments(self, groups: list[SegmentColorGroup]) -> None:
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
                if (
                    not await self.async_refresh_segments()
                    or any(self.segment_colors[index] != rgb for index, rgb in expected_colors.items())
                    or (expected_brightness is not None and self.segment_brightness != expected_brightness)
                ):
                    raise RuntimeError("Failed to confirm segment paint")
            finally:
                if attempted:
                    self.async_set_updated_data(self.data or {})

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        async with self.async_mask_transaction():
            await self._async_set_segment_brightness(segments, brightness)

    async def _async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        segments = list(segments)
        value = max(0, min(100, brightness))
        packet = build_segment_brightness(segments, value, self.model, profile=self.profile)
        expected_brightness = {segment - 1: value for segment in segments}
        expected_colors: list[tuple[int, int, int]] | None = None
        attempted = False

        def before_write() -> None:
            nonlocal attempted, expected_colors, expected_brightness
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
                if (
                    not await self.async_refresh_segments()
                    or any(self.segment_brightness[index] != value for index, value in expected_brightness.items())
                    or (expected_colors is not None and self.segment_colors != expected_colors)
                ):
                    raise RuntimeError("Failed to confirm segment brightness")
            finally:
                if attempted:
                    self.async_set_updated_data(self.data or {})
