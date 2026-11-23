from pathlib import Path

import pytest

from tests.pytest_lock import acquire_checkout_lock


def test_checkout_lock_excludes_another_process(tmp_path: Path) -> None:
    lock_path = tmp_path / ".pytest-lock"

    first = acquire_checkout_lock(lock_path)
    try:
        with pytest.raises(RuntimeError, match="Another pytest process owns this checkout"):
            acquire_checkout_lock(lock_path)
    finally:
        first.close()

    second = acquire_checkout_lock(lock_path)
    second.close()
