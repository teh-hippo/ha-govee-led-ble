"""H6179 browser-derived reactive RGB protocol contract."""

from __future__ import annotations

import pytest

from custom_components.ha_govee_led_ble.h6179_reactive_protocol import (
    H6179_REACTIVE_MAX_UPDATE_HZ,
    H6179_REACTIVE_MIN_UPDATE_INTERVAL,
    H6179_REACTIVE_SESSION_TIMEOUT,
    RGB,
    H6179ReactiveRoute,
    H6179ReactiveSession,
    ReactivePayloadError,
    ReactiveSessionError,
    ReactiveSessionExpiredError,
    ReactiveSessionOwnershipError,
    ReactiveSessionState,
    ReactiveStopReason,
    UnresolvedReactiveFirmwareError,
    build_h6179_reactive_frame,
    select_h6179_reactive_route,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum


@pytest.mark.parametrize(
    ("firmware", "expected"),
    [
        (None, H6179ReactiveRoute.UNRESOLVED),
        ("", H6179ReactiveRoute.UNRESOLVED),
        ("1.0.2", H6179ReactiveRoute.UNRESOLVED),
        ("1.00.01", H6179ReactiveRoute.MUSIC_STREAM),
        ("1.00.02", H6179ReactiveRoute.MUSIC_STREAM),
        ("1.00.99", H6179ReactiveRoute.MUSIC_STREAM),
        ("1.01.00", H6179ReactiveRoute.MUSIC_STREAM),
        ("2.00.00", H6179ReactiveRoute.MUSIC_STREAM),
    ],
)
def test_route_selection_fails_closed_at_firmware_boundaries(
    firmware: str | None,
    expected: H6179ReactiveRoute,
) -> None:
    assert select_h6179_reactive_route(firmware) is expected


@pytest.mark.parametrize(
    ("firmware", "expected"),
    [
        ("1.00.01", H6179ReactiveRoute.UNRESOLVED),
        ("1.00.02", H6179ReactiveRoute.LEGACY_STATIC_COLOUR),
        ("1.00.99", H6179ReactiveRoute.LEGACY_STATIC_COLOUR),
        ("1.01.00", H6179ReactiveRoute.UNRESOLVED),
    ],
)
def test_legacy_colour_order_is_explicit_and_firmware_bounded(
    firmware: str,
    expected: H6179ReactiveRoute,
) -> None:
    assert select_h6179_reactive_route(firmware, legacy_colour_order=True) is expected


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (
            H6179ReactiveRoute.LEGACY_STATIC_COLOUR,
            "33050d560000000000000000000000000000006d",
        ),
        (H6179ReactiveRoute.MUSIC_STREAM, "a5028356000080"),
    ],
)
def test_exact_reactive_frame_vectors(route: H6179ReactiveRoute, expected: str) -> None:
    frame = build_h6179_reactive_frame(route, RGB(0x56, 0, 0))
    assert frame == bytes.fromhex(expected)
    if route is H6179ReactiveRoute.LEGACY_STATIC_COLOUR:
        assert len(frame) == 20
        assert xor_checksum(frame[:19]) == frame[19]
    else:
        assert len(frame) == 7
        assert sum(frame[:6]) & 0xFF == frame[6]


@pytest.mark.parametrize(
    ("rgb", "static_checksum", "stream_checksum"),
    [
        (RGB(0, 0, 0), 0x3B, 0x2A),
        (RGB(255, 255, 255), 0xC4, 0x27),
        (RGB(1, 2, 3), 0x3B, 0x30),
    ],
)
def test_checksum_vectors(rgb: RGB, static_checksum: int, stream_checksum: int) -> None:
    static = build_h6179_reactive_frame(H6179ReactiveRoute.LEGACY_STATIC_COLOUR, rgb)
    stream = build_h6179_reactive_frame(H6179ReactiveRoute.MUSIC_STREAM, rgb)
    assert static[19] == static_checksum
    assert stream[6] == stream_checksum


def test_rgb_payload_accepts_only_exact_browser_colour_objects() -> None:
    assert RGB.from_payload({"r": 1, "g": 2, "b": 3}) == RGB(1, 2, 3)

    invalid_payloads = [
        b"\x00\x01",
        [1, 2, 3],
        {"pcm": [1, 2, 3]},
        {"audio": "base64"},
        {"r": 1, "g": 2, "b": 3, "samples": []},
        {"r": True, "g": 2, "b": 3},
        {"r": 1.0, "g": 2, "b": 3},
        {"r": -1, "g": 2, "b": 3},
        {"r": 1, "g": 2, "b": 256},
    ]
    for payload in invalid_payloads:
        with pytest.raises(ReactivePayloadError):
            RGB.from_payload(payload)

    with pytest.raises(ReactivePayloadError):
        build_h6179_reactive_frame(H6179ReactiveRoute.MUSIC_STREAM, b"\x01\x02\x03")


def test_unresolved_route_and_session_are_explicit() -> None:
    with pytest.raises(UnresolvedReactiveFirmwareError):
        build_h6179_reactive_frame(H6179ReactiveRoute.UNRESOLVED, RGB(1, 2, 3))
    with pytest.raises(UnresolvedReactiveFirmwareError):
        H6179ReactiveSession("unknown")
    with pytest.raises(UnresolvedReactiveFirmwareError):
        H6179ReactiveSession("1.01.00", legacy_colour_order=True)


@pytest.mark.parametrize(
    ("firmware", "expected_frame"),
    [
        ("1.00.01", bytes.fromhex("a5028356000080")),
        ("1.01.00", bytes.fromhex("a5028356000080")),
    ],
)
def test_start_first_update_and_stop_lifecycle(firmware: str, expected_frame: bytes) -> None:
    session = H6179ReactiveSession(firmware)

    started = session.start("browser-a", 10.0)
    assert started.state is ReactiveSessionState.ACTIVE
    assert started.frame is None
    assert started.next_due == 10.0 + H6179_REACTIVE_SESSION_TIMEOUT

    updated = session.update("browser-a", RGB(0x56, 0, 0), 10.0)
    assert updated.frame == expected_frame
    assert updated.next_due == 10.0 + H6179_REACTIVE_SESSION_TIMEOUT

    stopped = session.stop("browser-a")
    assert stopped.state is ReactiveSessionState.IDLE
    assert stopped.frame is None
    assert stopped.stop_reason is ReactiveStopReason.REQUESTED
    assert session.last_stop_reason is ReactiveStopReason.REQUESTED
    with pytest.raises(ReactiveSessionError):
        session.update("browser-a", RGB(1, 2, 3), 10.1)


def test_explicit_legacy_session_uses_static_colour_order() -> None:
    session = H6179ReactiveSession("1.00.02", legacy_colour_order=True)
    session.start("browser-a", 0)

    assert session.update("browser-a", RGB(0x56, 0, 0), 0).frame == bytes.fromhex(
        "33050d560000000000000000000000000000006d"
    )


def test_updates_are_capped_at_twenty_hertz_and_latest_only() -> None:
    assert H6179_REACTIVE_MAX_UPDATE_HZ == 20
    assert H6179_REACTIVE_MIN_UPDATE_INTERVAL == 0.05
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)

    first = session.update("browser-a", RGB(255, 0, 0), 0)
    queued_green = session.update("browser-a", RGB(0, 255, 0), 0.01)
    queued_blue = session.update("browser-a", RGB(0, 0, 255), 0.02)
    early = session.tick(0.049)
    flushed = session.tick(0.05)

    assert first.frame == bytes.fromhex("a50283ff000029")
    assert queued_green.frame is None and queued_green.coalesced
    assert queued_blue.frame is None and queued_blue.coalesced
    assert early.frame is None and early.coalesced
    assert flushed.frame == bytes.fromhex("a502830000ff29")
    assert flushed.next_due == 0.02 + H6179_REACTIVE_SESSION_TIMEOUT


def test_return_to_last_sent_colour_cancels_a_pending_update() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)
    session.update("browser-a", RGB(1, 2, 3), 0)
    session.update("browser-a", RGB(4, 5, 6), 0.01)

    cancelled = session.update("browser-a", RGB(1, 2, 3), 0.02)
    assert cancelled.frame is None
    assert not cancelled.coalesced
    assert session.tick(0.05).frame is None


def test_duplicate_colours_keep_the_session_alive_without_writes() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)
    session.update("browser-a", RGB(1, 2, 3), 0)

    duplicate = session.update("browser-a", RGB(1, 2, 3), 1.5)
    assert duplicate.frame is None
    assert duplicate.next_due == 1.5 + H6179_REACTIVE_SESSION_TIMEOUT
    assert session.tick(2.1).state is ReactiveSessionState.ACTIVE


def test_timeout_discards_pending_colour_and_expires_ownership() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)
    session.update("browser-a", RGB(1, 2, 3), 0)
    session.update("browser-a", RGB(4, 5, 6), 0.01)

    timed_out = session.tick(2.01)
    assert timed_out.state is ReactiveSessionState.IDLE
    assert timed_out.frame is None
    assert timed_out.stop_reason is ReactiveStopReason.TIMEOUT
    assert session.last_stop_reason is ReactiveStopReason.TIMEOUT


def test_update_at_timeout_fails_and_cleans_up() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)

    with pytest.raises(ReactiveSessionExpiredError):
        session.update("browser-a", RGB(1, 2, 3), H6179_REACTIVE_SESSION_TIMEOUT)
    assert session.state is ReactiveSessionState.IDLE
    assert session.last_stop_reason is ReactiveStopReason.TIMEOUT


def test_normal_control_supersedes_and_invalidates_stale_session() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 0)
    session.update("browser-a", RGB(1, 2, 3), 0)
    session.update("browser-a", RGB(4, 5, 6), 0.01)

    superseded = session.supersede()
    assert superseded.stop_reason is ReactiveStopReason.SUPERSEDED
    assert superseded.frame is None
    with pytest.raises(ReactiveSessionError):
        session.update("browser-a", RGB(7, 8, 9), 0.02)

    session.start("browser-b", 0.03)
    with pytest.raises(ReactiveSessionOwnershipError):
        session.stop("browser-a")
    assert session.state is ReactiveSessionState.ACTIVE
    assert session.session_id == "browser-b"


def test_disconnect_discards_pending_state_without_a_write() -> None:
    session = H6179ReactiveSession("1.00.02", legacy_colour_order=True)
    session.start("browser-a", 0)
    session.update("browser-a", RGB(1, 2, 3), 0)
    session.update("browser-a", RGB(4, 5, 6), 0.01)

    disconnected = session.disconnect()
    assert disconnected.state is ReactiveSessionState.IDLE
    assert disconnected.frame is None
    assert disconnected.stop_reason is ReactiveStopReason.DISCONNECTED
    assert session.tick(0.05).frame is None


def test_session_rejects_parallel_owners_and_non_monotonic_time() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 1)
    with pytest.raises(ReactiveSessionError):
        session.start("browser-b", 1)
    with pytest.raises(ReactiveSessionOwnershipError):
        session.update("browser-b", RGB(1, 2, 3), 1)
    with pytest.raises(ReactiveSessionError, match="backwards"):
        session.tick(0.5)


def test_rejected_foreign_update_does_not_advance_session_time() -> None:
    session = H6179ReactiveSession("1.01.00")
    session.start("browser-a", 1)

    with pytest.raises(ReactiveSessionOwnershipError):
        session.update("browser-b", RGB(1, 2, 3), 1000)

    assert session.update("browser-a", RGB(4, 5, 6), 2).frame is not None
