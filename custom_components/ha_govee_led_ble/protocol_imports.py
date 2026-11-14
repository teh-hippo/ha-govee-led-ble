"""Shared loading boundary for generated Kaitai classes."""

from importlib import import_module
from typing import Any


def load_generated_class(module_name: str, class_name: str) -> Any:
    return getattr(import_module(f"{__package__}.generated_protocol.{module_name}"), class_name)
