from __future__ import annotations

import pytest

from govee_relay.lifecycle import CleanupRegistry


def test_cleanup_runs_once_in_reverse_order():
    events: list[str] = []
    forced: list[int] = []
    cleanup = CleanupRegistry(force_exit=forced.append)
    cleanup.add(lambda: events.append("first"))
    cleanup.add(lambda: events.append("second"))

    cleanup.signal_handler(15, None)
    assert cleanup.shutdown_requested.is_set()
    assert events == []
    cleanup.close()

    assert events == ["second", "first"]
    assert forced == []
    with pytest.raises(RuntimeError, match="already run"):
        cleanup.add(lambda: None)


def test_cleanup_reports_all_failures():
    cleanup = CleanupRegistry()
    cleanup.add(lambda: (_ for _ in ()).throw(RuntimeError("one")))
    cleanup.add(lambda: (_ for _ in ()).throw(ValueError("two")))

    with pytest.raises(ExceptionGroup) as captured:
        cleanup.close()

    assert {type(error) for error in captured.value.exceptions} == {
        RuntimeError,
        ValueError,
    }


def test_second_signal_forces_exit_without_locking():
    forced: list[int] = []
    cleanup = CleanupRegistry(force_exit=forced.append)
    cleanup.signal_handler(15, None)
    cleanup.signal_handler(2, None)
    assert forced == [130]
