"""Dotted-decimal firmware version parsing and comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, order=True, slots=True)
class FirmwareVersion:
    """A numerically comparable dotted-decimal firmware version."""

    _components: tuple[int, ...]

    @classmethod
    def parse(cls, value: object, *, strict: bool = True) -> Self | None:
        """Parse device major.xx.xx; permissive comparison requires explicit opt-in.

        Old configured values such as 3.2.2 remain stored but are unqualified:
        re-enter 3.02.02 or obtain fresh standard-format identity from BLE.
        """
        if not isinstance(value, str):
            return None
        if strict and re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}\.[0-9]{2}", value) is None:
            return None
        raw_components = value.split(".")
        if any(not component.isascii() or not component.isdecimal() for component in raw_components):
            return None

        components = [int(component) for component in raw_components]
        while len(components) > 1 and components[-1] == 0:
            components.pop()
        return cls(tuple(components))

    def identity_number(self) -> int:
        """Return the base-100 identity value after strict format validation."""
        major, minor, patch = (*self._components, 0, 0)[:3]
        return major * 10000 + minor * 100 + patch
