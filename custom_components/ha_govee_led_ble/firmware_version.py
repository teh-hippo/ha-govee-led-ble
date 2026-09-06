"""Dotted-decimal firmware version parsing and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, order=True, slots=True)
class FirmwareVersion:
    """A numerically comparable dotted-decimal firmware version."""

    _components: tuple[int, ...]

    @classmethod
    def parse(cls, value: str | None) -> Self | None:
        """Parse a strict dotted-decimal version, returning None when invalid."""
        if value is None:
            return None
        raw_components = value.split(".")
        if any(not component.isascii() or not component.isdecimal() for component in raw_components):
            return None

        components = [int(component) for component in raw_components]
        while len(components) > 1 and components[-1] == 0:
            components.pop()
        return cls(tuple(components))
