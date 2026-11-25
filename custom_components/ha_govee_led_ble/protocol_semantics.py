"""Shared semantic command and status values produced by protocol adapters."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedProtocolCommand:
    operation: str
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedProtocolStatus:
    domain: str
    values: Mapping[str, Any]
