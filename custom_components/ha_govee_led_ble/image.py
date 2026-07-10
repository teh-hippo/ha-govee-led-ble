"""Image entity that serves a server-rendered preview of the currently-selected look.

Rendering is pure and lives in ``preview`` (no BLE, nothing sent to the device). Encoded bytes are
cached in ``hass.data`` keyed by ``(look_id, reduce_motion, palette_hash)`` so repeated fetches are
free; ``image_last_updated`` only advances when that key changes (a look change, a custom
content edit/rename, or a reduce-motion toggle), never on unrelated coordinator updates or polling.
"""

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import preview
from .const import DOMAIN
from .coordinator import GoveeBLECoordinator
from .custom_effects import SegmentContent
from .entity import GoveeBLEEntity
from .preview import PreviewImage, PreviewLook
from .scenes import SCENES

PARALLEL_UPDATES = 0

_CACHE_KEY = "preview_cache"

type _LookKey = tuple[str, bool, str]


def _resolve_look(coordinator: GoveeBLECoordinator) -> tuple[str, PreviewLook]:
    """Map coordinator state to a cache id and the look to render (custom, else scene, else colour)."""
    active_id = coordinator.active_custom_id
    if active_id is not None and (effect := coordinator.custom_effects.get(active_id)) is not None:
        return f"custom:{active_id}:{effect.name_key}", effect.content
    if coordinator.effect is not None and (scene := SCENES.get(coordinator.effect)) is not None:
        return f"scene:{scene.code}", scene
    return "colour", SegmentContent(colors=tuple(coordinator.segment_colors))


class GoveeEffectPreviewImage(GoveeBLEEntity, ImageEntity):
    """Diagnostic image of the selected look; a still under reduce-motion, otherwise an animated GIF."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "effect_preview"

    def __init__(self, coordinator: GoveeBLECoordinator, hass: HomeAssistant) -> None:
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_effect_preview"
        self._attr_device_info = coordinator.device_info
        self._attr_image_last_updated = dt_util.utcnow()
        self._look_key = self._current_key()

    def _current_key(self) -> _LookKey:
        look_id, look = _resolve_look(self.coordinator)
        segment_count = max(1, self.coordinator.profile.segment_count)
        return look_id, self.coordinator.preview_reduce_motion, preview.look_hash(look, segment_count)

    def _cache(self) -> dict[_LookKey, PreviewImage]:
        store: dict[str, dict[_LookKey, PreviewImage]] = self.hass.data.setdefault(DOMAIN, {})
        return store.setdefault(_CACHE_KEY, {})

    @callback
    def _handle_coordinator_update(self) -> None:
        key = self._current_key()
        if key != self._look_key:
            self._look_key = key
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        look_id, look = _resolve_look(self.coordinator)
        segment_count = max(1, self.coordinator.profile.segment_count)
        reduce_motion = self.coordinator.preview_reduce_motion
        key: _LookKey = (look_id, reduce_motion, preview.look_hash(look, segment_count))
        cache = self._cache()
        image = cache.get(key)
        if image is None:
            image = await self.hass.async_add_executor_job(
                preview.render_preview_image, look, segment_count, reduce_motion
            )
            cache[key] = image
        self._attr_content_type = image.content_type
        return image.data


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GoveeEffectPreviewImage(config_entry.runtime_data, hass)])
