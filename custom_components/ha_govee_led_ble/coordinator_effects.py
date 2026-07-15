"""Custom-effect CRUD, sticky apply and per-entry Store for the Govee BLE coordinator."""

from dataclasses import replace
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator_base import _CoordinatorBase
from .custom_effects import (
    AuthorableContent,
    CustomEffect,
    EffectContent,
    EffectValidationError,
    SegmentContent,
    UnknownContent,
    content_from_dict,
    content_to_dict,
    new_effect_id,
    normalise_name,
    uses_diy_slot,
    validate_content,
)
from .protocol import DEFAULT_DIY_SLOT, build_custom_effect

STORE_VERSION = 2
STORE_MINOR_VERSION = 1


def effect_store_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}"


class EffectStore(Store[dict[str, Any]]):
    """Per-entry effect Store; v1 stored a single ``name`` that v2 splits into display/name_key."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        if old_major_version < STORE_VERSION:
            for effect in old_data.get("effects", {}).values():
                name = effect.pop("name", effect.get("display_name", ""))
                effect.setdefault("display_name", name)
                effect["name_key"] = normalise_name(effect["display_name"])
        return old_data


def build_effect_store(hass: HomeAssistant, entry_id: str) -> EffectStore:
    return EffectStore(hass, STORE_VERSION, effect_store_key(entry_id), minor_version=STORE_MINOR_VERSION)


class _CustomEffectMixin(_CoordinatorBase):
    """Loads, resolves and mutates stored custom effects, and applies them as a sticky mode."""

    def attach_effect_store(self, store: Store[dict[str, Any]]) -> None:
        self._effect_store = store

    def _ordered_effects(self) -> list[CustomEffect]:
        return sorted(self.custom_effects.values(), key=lambda effect: (effect.name_key, effect.id))

    def is_custom_effect_supported(self, effect: CustomEffect) -> bool:
        content = effect.content
        if isinstance(content, UnknownContent) or not self._is_supported_content(content):
            return False
        try:
            validate_content(content, segment_count=self.profile.segment_count)
        except EffectValidationError:
            return False
        return True

    def custom_effect_display_names(self) -> list[str]:
        return [effect.display_name for effect in self._ordered_effects() if self.is_custom_effect_supported(effect)]

    def custom_effect_index(self) -> dict[str, str]:
        return {
            effect.id: effect.display_name
            for effect in self._ordered_effects()
            if self.is_custom_effect_supported(effect)
        }

    def quarantined_custom_effect_index(self) -> dict[str, str]:
        return {
            effect.id: effect.display_name
            for effect in self._ordered_effects()
            if not self.is_custom_effect_supported(effect)
        }

    def resolve_custom(self, key_or_id: str) -> CustomEffect | None:
        if (direct := self.custom_effects.get(key_or_id)) is not None:
            return direct
        name_key = normalise_name(key_or_id)
        return next((effect for effect in self.custom_effects.values() if effect.name_key == name_key), None)

    @property
    def _scene_name_keys(self) -> frozenset[str]:
        return frozenset(normalise_name(name) for name in self.scene_name_set)

    def _scene_shadow_issue_id(self, effect_id: str) -> str:
        return f"custom_effect_scene_shadow_{self.address}_{effect_id}"

    def _unsupported_effect_issue_id(self, effect_id: str) -> str:
        return f"custom_effect_unsupported_model_{self.address}_{effect_id}"

    def _reconcile_scene_shadow(self, effect: CustomEffect) -> None:
        """Raise or clear the repair issue that flags a stored custom shadowing a built-in scene."""
        issue_id = self._scene_shadow_issue_id(effect.id)
        if not self.is_custom_effect_supported(effect):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        if effect.name_key in self._scene_name_keys:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="custom_effect_scene_shadow",
                translation_placeholders={"effect": effect.display_name},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _reconcile_effect_support(self, effect: CustomEffect) -> None:
        issue_id = self._unsupported_effect_issue_id(effect.id)
        if self.is_custom_effect_supported(effect):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="custom_effect_unsupported_model",
            translation_placeholders={"effect": effect.display_name, "model": self.model},
        )

    async def async_load_effects(self) -> None:
        async with self._store_lock:
            await self._reload_from_store()
        for effect in self.custom_effects.values():
            self._reconcile_effect_support(effect)
            self._reconcile_scene_shadow(effect)

    async def async_apply_custom_effect(self, effect_id: str) -> None:
        effect = self.custom_effects.get(effect_id)
        if effect is None:
            raise EffectValidationError("unknown_effect")
        if isinstance(effect.content, UnknownContent):
            raise EffectValidationError("unknown_kind_not_applyable")
        content = self._require_supported_kind(effect.content)
        validate_content(content, segment_count=self.profile.segment_count)
        for packet in build_custom_effect(effect.content, segment_count=self.profile.segment_count):
            await self.send_command(packet)
        self.active_custom_id = effect.id
        self.effect = effect.display_name
        self.diy_slot = DEFAULT_DIY_SLOT if uses_diy_slot(content) else None
        self._owned_diy_effect_id = effect.id if uses_diy_slot(content) else None
        self.music_mode = self.video_mode = "off"
        self._publish()

    async def async_save_effect(
        self, display_name: str, content: EffectContent | None = None, *, capture_current: bool = False
    ) -> str:
        async with self._store_lock:
            await self._reload_from_store()
            resolved = self._require_supported_kind(self._content_for_save(content, capture_current=capture_current))
            validate_content(resolved, segment_count=self.profile.segment_count)
            name_key = self._validated_name_key(display_name)
            effect_id = new_effect_id(self.custom_effects)
            self.custom_effects[effect_id] = CustomEffect(
                id=effect_id, display_name=display_name.strip(), name_key=name_key, content=resolved
            )
            await self._save_to_store()
            self._publish()
            return effect_id

    async def async_delete_effect(self, key_or_id: str) -> None:
        async with self._store_lock:
            await self._reload_from_store()
            effect = self.resolve_custom(key_or_id)
            if effect is None:
                raise EffectValidationError("unknown_effect")
            del self.custom_effects[effect.id]
            if self.active_custom_id == effect.id:
                self.active_custom_id = None
                self.effect = None
            if self._owned_diy_effect_id == effect.id:
                self._owned_diy_effect_id = None
            ir.async_delete_issue(self.hass, DOMAIN, self._scene_shadow_issue_id(effect.id))
            ir.async_delete_issue(self.hass, DOMAIN, self._unsupported_effect_issue_id(effect.id))
            await self._save_to_store()
            self._publish()

    async def async_rename_effect(self, key_or_id: str, to_name: str) -> None:
        async with self._store_lock:
            await self._reload_from_store()
            effect = self.resolve_custom(key_or_id)
            if effect is None:
                raise EffectValidationError("unknown_effect")
            name_key = self._validated_name_key(to_name, exclude_id=effect.id)
            renamed = replace(effect, display_name=to_name.strip(), name_key=name_key)
            self.custom_effects[effect.id] = renamed
            if self.active_custom_id == effect.id:
                self.effect = renamed.display_name
            self._reconcile_effect_support(renamed)
            self._reconcile_scene_shadow(renamed)
            await self._save_to_store()
            self._publish()

    async def async_update_effect(
        self, effect_id: str, *, display_name: str | None = None, content: EffectContent | None = None
    ) -> None:
        """Update a stored effect by its stable id, changing its display name, content, or both."""
        if display_name is None and content is None:
            raise EffectValidationError("update_needs_name_or_content")
        async with self._store_lock:
            await self._reload_from_store()
            effect = self.custom_effects.get(effect_id)
            if effect is None:
                raise EffectValidationError("unknown_effect")
            changes: dict[str, Any] = {}
            if content is not None:
                resolved = self._require_supported_kind(content)
                validate_content(resolved, segment_count=self.profile.segment_count)
                changes["content"] = resolved
            if display_name is not None:
                changes["name_key"] = self._validated_name_key(display_name, exclude_id=effect.id)
                changes["display_name"] = display_name.strip()
            updated = replace(effect, **changes)
            self.custom_effects[effect.id] = updated
            if self.active_custom_id == effect.id:
                self.effect = updated.display_name
            self._reconcile_effect_support(updated)
            self._reconcile_scene_shadow(updated)
            await self._save_to_store()
            self._publish()

    async def async_export_effect(self, effect_id: str) -> dict[str, Any]:
        """Return a portable snapshot of a stored effect resolved by its stable id."""
        async with self._store_lock:
            await self._reload_from_store()
            effect = self.custom_effects.get(effect_id)
            if effect is None:
                raise EffectValidationError("unknown_effect")
            return {
                "id": effect.id,
                "name": effect.display_name,
                "model": self.model,
                "segment_count": self.profile.segment_count,
                "content": content_to_dict(effect.content),
            }

    def _content_for_save(self, content: EffectContent | None, *, capture_current: bool) -> EffectContent:
        if capture_current:
            return SegmentContent(colors=tuple(self.segment_colors))
        if content is None:
            raise EffectValidationError("content_required")
        return content

    def _require_supported_kind(self, content: EffectContent) -> AuthorableContent:
        if isinstance(content, UnknownContent):
            raise EffectValidationError("unknown_kind_not_saveable")
        if not self._is_supported_content(content):
            if isinstance(content, SegmentContent):
                raise EffectValidationError("segments_unsupported")
            raise EffectValidationError("diy_unsupported")
        return content

    def _is_supported_content(self, content: EffectContent) -> bool:
        if isinstance(content, UnknownContent):
            return False
        if isinstance(content, SegmentContent):
            return self.profile.supports_segments
        return self.profile.supports_diy

    def _validated_name_key(self, display_name: str, *, exclude_id: str | None = None) -> str:
        name_key = normalise_name(display_name)
        if not name_key:
            raise EffectValidationError("empty_name")
        if name_key in self._scene_name_keys:
            raise EffectValidationError("scene_name_collision")
        if any(effect.name_key == name_key for eid, effect in self.custom_effects.items() if eid != exclude_id):
            raise EffectValidationError("duplicate_name")
        return name_key

    async def _reload_from_store(self) -> None:
        if self._effect_store is None:
            return
        self.custom_effects = self._parse_effects(await self._effect_store.async_load())

    async def _save_to_store(self) -> None:
        if self._effect_store is not None:
            await self._effect_store.async_save(self._serialise_effects())

    @staticmethod
    def _parse_effects(raw: dict[str, Any] | None) -> dict[str, CustomEffect]:
        if not raw:
            return {}
        parsed: dict[str, CustomEffect] = {}
        for effect_id, stored in raw.get("effects", {}).items():
            display_name = stored.get("display_name", "")
            parsed[effect_id] = CustomEffect(
                id=effect_id,
                display_name=display_name,
                name_key=stored.get("name_key") or normalise_name(display_name),
                content=content_from_dict(stored.get("content", {})),
            )
        return parsed

    def _serialise_effects(self) -> dict[str, Any]:
        return {
            "effects": {
                effect.id: {
                    "display_name": effect.display_name,
                    "name_key": effect.name_key,
                    "content": content_to_dict(effect.content),
                }
                for effect in self.custom_effects.values()
            }
        }

    def _publish(self) -> None:
        self.async_set_updated_data(self.data or {})
