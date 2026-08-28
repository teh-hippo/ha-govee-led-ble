"""Test doubles for repository storage ports."""

from __future__ import annotations

import copy

from custom_components.ha_govee_led_ble.effect_store import EffectDocument, EffectDocumentFactory


class InMemoryVersionedDocumentStore:
    """In-memory versioned document store with controllable delayed writes."""

    def __init__(self, data: EffectDocument | None = None) -> None:
        self.data = copy.deepcopy(data)
        self.delayed_data_func: EffectDocumentFactory | None = None
        self.delayed_seconds: float | None = None
        self.save_count = 0

    async def async_load(self) -> EffectDocument | None:
        return copy.deepcopy(self.data)

    async def async_save(self, data: EffectDocument) -> None:
        self.data = copy.deepcopy(data)
        self.save_count += 1

    def async_delay_save(self, data_func: EffectDocumentFactory, delay: float) -> None:
        self.delayed_data_func = data_func
        self.delayed_seconds = delay

    async def async_fire_delayed_save(self) -> None:
        if self.delayed_data_func is None:
            return
        data_func = self.delayed_data_func
        self.delayed_data_func = None
        self.delayed_seconds = None
        await self.async_save(data_func())
