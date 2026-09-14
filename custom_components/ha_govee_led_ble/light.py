"""Light entity for HA Govee LED BLE."""

# fmt: off
import logging
from collections.abc import Awaitable, Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID, uuid4

from homeassistant.components.light import (  # type: ignore[attr-defined]
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EFFECT_CATEGORIES,
    EFFECT_CATEGORY_REACTIVE,
    EFFECT_CATEGORY_SCENES,
    EFFECT_CATEGORY_VIDEO,
    EFFECT_FAMILY_MUSIC,
    EFFECT_FAMILY_SCENES,
    EFFECT_FAMILY_VIDEO,
    MUSIC_MODE_SLUGS,
    ModelProfile,
    effect_category_for_content_kind,
)
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .coordinator_status import ParsedMode
from .effect_backend import EffectBackend
from .effect_compiler import CompiledMusicProfile, CompiledVideoProfile, compile_application
from .effect_contracts import CapabilityWorkflow, require_effect_route
from .effect_deployments import DeploymentRecord
from .effect_diagnostics import DiagnosticOutcome, DiagnosticStage
from .effect_domain import EffectValidationError, LibraryItem, MusicProfile, effect_content_to_dict
from .effect_runtime import (
    active_workspace_matches,
    async_apply_compiled_profile,
    observable_signatures_for_coordinator,
)
from .effect_scenes import scene_default_for
from .effect_selector import (
    EffectSelectorEntry,
    effect_selector_entries,
    normalise_effect_name,
    resolve_effect_selector,
)
from .effect_setup import get_effect_backend
from .effect_storage import (
    EffectNotFoundError,
    EffectVersionConflictError,
    LibrarySnapshot,
)
from .entity import GoveeBLEEntity
from .generated_protocol_adapter import build_brightness, build_power
from .light_commands import build_color_rgb, build_color_temp, kelvin_to_rgb
from .light_services import (
    _GoveeLightServicesMixin,
)
from .music_commands import prepare_music_request
from .music_semantics import music_variant
from .native_profile_controls import apply_active_video_mode as apply_active_video_mode
from .native_scenes import build_native_scene_packets
from .scenes import MODEL_SCENES
from .video_applicability import validate_video_request

# fmt: on

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _StaticColorRestoreData(ExtraStoredData):
    color_mode: ColorMode
    rgb_color: tuple[int, int, int] | None = None
    color_temp_kelvin: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            ATTR_COLOR_MODE: self.color_mode.value,
            ATTR_RGB_COLOR: list(self.rgb_color) if self.rgb_color is not None else None,
            ATTR_COLOR_TEMP_KELVIN: self.color_temp_kelvin,
        }


def _coerce_rgb(raw: Any) -> tuple[int, int, int] | None:
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        return None
    try:
        red, green, blue = (int(channel) for channel in raw)
    except TypeError, ValueError:
        return None
    return (
        max(0, min(255, red)),
        max(0, min(255, green)),
        max(0, min(255, blue)),
    )


def _coerce_static_color(
    attributes: Mapping[str, Any],
    profile: ModelProfile,
) -> _StaticColorRestoreData | None:
    raw_mode = attributes.get(ATTR_COLOR_MODE)
    if isinstance(raw_mode, ColorMode):
        restored_mode = raw_mode
    elif isinstance(raw_mode, str):
        try:
            restored_mode = ColorMode(raw_mode)
        except ValueError:
            return None
    else:
        return None
    if restored_mode is ColorMode.RGB:
        if not profile.supports_rgb or (restored_rgb := _coerce_rgb(attributes.get(ATTR_RGB_COLOR))) is None:
            return None
        return _StaticColorRestoreData(restored_mode, rgb_color=restored_rgb)
    if restored_mode is not ColorMode.COLOR_TEMP or not profile.supports_color_temperature:
        return None
    try:
        restored_kelvin = int(attributes[ATTR_COLOR_TEMP_KELVIN])
    except KeyError, TypeError, ValueError:
        return None
    return _StaticColorRestoreData(
        restored_mode,
        color_temp_kelvin=max(
            profile.min_color_temp_kelvin,
            min(profile.max_color_temp_kelvin, restored_kelvin),
        ),
    )


def _coerce_segment_colors(raw: Any, count: int) -> list[tuple[int, int, int]] | None:
    """Validate a restored ``segment_colors`` attribute into RGB tuples, or None if malformed."""
    if not isinstance(raw, list) or len(raw) != count:
        return None
    colors: list[tuple[int, int, int]] = []
    for item in raw:
        if not isinstance(item, list | tuple) or len(item) != 3:
            return None
        try:
            r, g, b = int(item[0]), int(item[1]), int(item[2])
        except TypeError, ValueError:
            return None
        colors.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
    return colors


def _coerce_segment_brightness(raw: Any, count: int) -> list[int] | None:
    if not isinstance(raw, list | tuple) or len(raw) != count:
        return None
    values: list[int] = []
    for value in raw:
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        values.append(max(0, min(100, value)))
    return values


_STATE_FIELDS = (
    "is_on brightness_pct rgb_color color_temp_kelvin effect video_saturation "
    "rgb_color_source color_temp_kelvin_source "
    "segment_colors video_full_screen video_sound_effects video_sound_effects_softness "
    "white_brightness music_sensitivity "
    "music_calm music_color diy_code music_mode video_mode"
).split()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            GoveeBLELight(
                config_entry.runtime_data,
                config_entry_id=config_entry.entry_id,
                effect_backend=get_effect_backend(hass),
            )
        ]
    )


class GoveeBLELight(_GoveeLightServicesMixin, GoveeBLEEntity, RestoreEntity, LightEntity):
    _attr_name = None

    def __init__(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        config_entry_id: str | None = None,
        effect_backend: EffectBackend | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address.replace(":", "").lower()
        self._attr_device_info = coordinator.device_info
        supported_color_modes: set[ColorMode] = set()
        if coordinator.profile.supports_rgb:
            supported_color_modes.add(ColorMode.RGB)
        if coordinator.profile.supports_color_temperature:
            supported_color_modes.add(ColorMode.COLOR_TEMP)
        if not supported_color_modes:
            supported_color_modes.add(ColorMode.ONOFF)
        self._attr_supported_color_modes = supported_color_modes
        self._attr_min_color_temp_kelvin = coordinator.profile.min_color_temp_kelvin
        self._attr_max_color_temp_kelvin = coordinator.profile.max_color_temp_kelvin
        self._attr_color_mode = (
            ColorMode.RGB
            if ColorMode.RGB in supported_color_modes
            else ColorMode.COLOR_TEMP
            if ColorMode.COLOR_TEMP in supported_color_modes
            else ColorMode.ONOFF
        )
        self._config_entry_id = config_entry_id
        self._effect_backend = effect_backend
        self._library_snapshot = (
            effect_backend.application.library_snapshot() if effect_backend is not None else LibrarySnapshot(())
        )

    @contextmanager
    def _rollback(self) -> Generator[None]:
        snap = {f: getattr(self.coordinator, f) for f in _STATE_FIELDS}
        revisions = dict(self.coordinator._field_revisions)
        mode_snap = self._attr_color_mode
        try:
            yield
        except Exception as err:
            for f, v in snap.items():
                field = f.removesuffix("_source")
                if field in {"rgb_color", "color_temp_kelvin"} and any(
                    self.coordinator._field_revisions.get(key, 0) != revisions.get(key, 0)
                    for key in ("rgb_color", "color_temp_kelvin")
                ):
                    continue
                setattr(self.coordinator, f, v)
            self._attr_color_mode = mode_snap
            if isinstance(err, HomeAssistantError):
                raise
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_command_failed",
            ) from err

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_on

    @property
    def brightness(self) -> int | None:
        return round(self.coordinator.brightness_pct * 255 / 100)

    @property
    def color_mode(self) -> ColorMode | None:
        coordinator = self.coordinator
        if coordinator.color_mode in (None, ParsedMode.COLOUR):
            if coordinator.color_temp_kelvin is not None and coordinator.color_temp_kelvin_source != "initial":
                return ColorMode.COLOR_TEMP
            if coordinator.rgb_color_source != "initial":
                return ColorMode.RGB
        return self._attr_color_mode

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self.coordinator.rgb_color if self.color_mode == ColorMode.RGB else None

    @property
    def color_temp_kelvin(self) -> int | None:
        return self.coordinator.color_temp_kelvin if self.color_mode == ColorMode.COLOR_TEMP else None

    @property
    def effect(self) -> str | None:
        active_workspace = self._matching_active_workspace()
        if active_workspace is not None:
            return "Custom"
        entries = self._selector_entries(active_custom=False)
        if active_saved := self._active_saved_effect():
            return next(
                (
                    entry.display_label
                    for entry in entries
                    if entry.source == "saved" and entry.item is not None and entry.item.id == active_saved.id
                ),
                EFFECT_OFF,
            )
        active = next(
            (
                entry
                for entry in entries
                if (entry.source == "video" and entry.value == self.coordinator.video_mode)
                or (entry.source == "music" and entry.value == self.coordinator.music_mode)
                or (entry.source == "scene" and entry.value == self.coordinator.effect)
            ),
            None,
        )
        if active is not None:
            return active.display_label
        return EFFECT_OFF if self.effect_list else None

    @property
    def supported_features(self) -> LightEntityFeature:
        return LightEntityFeature.EFFECT if self.effect_list else LightEntityFeature(0)

    @property
    def effect_list(self) -> list[str]:
        active_custom = self._matching_active_workspace() is not None
        entries = self._selector_entries(active_custom=active_custom)
        if not entries and not active_custom and not self._effect_categories:
            return []
        custom = ["Custom"] if active_custom else []
        return [
            EFFECT_OFF,
            *custom,
            *(entry.display_label for entry in entries),
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if (scene_code := self.coordinator.unknown_scene_code) is not None:
            attrs["unknown_scene_code"] = scene_code
        if self.coordinator.profile.supports_segments:
            attrs["segment_colors"] = [list(color) for color in self.coordinator.segment_colors]
            attrs["segment_brightness"] = list(self.coordinator.segment_brightness)
            attrs["segment_state_source"] = self.coordinator.segment_state_source
        return attrs

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        if self.color_mode is ColorMode.COLOR_TEMP and self.coordinator.color_temp_kelvin is not None:
            return _StaticColorRestoreData(
                ColorMode.COLOR_TEMP,
                color_temp_kelvin=self.coordinator.color_temp_kelvin,
            )
        if self.color_mode is ColorMode.RGB:
            return _StaticColorRestoreData(ColorMode.RGB, rgb_color=self.coordinator.rgb_color)
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._effect_backend is not None:
            application = self._effect_backend.application
            self.async_on_remove(
                application.subscribe_library(
                    self._library_updated,
                )
            )
            self._library_updated(application.library_snapshot())
        await self._async_restore_static_color()
        await self._async_restore_segments()

    def _library_updated(self, snapshot: LibrarySnapshot) -> None:
        self._library_snapshot = snapshot
        self.async_write_ha_state()

    def _active_saved_effect(self) -> LibraryItem | None:
        if self._effect_backend is None or self._config_entry_id is None:
            return None
        observed = self._effect_backend.device_cache.get(self._config_entry_id)
        hint = observed.active_effect if observed is not None else None
        if hint is None or hint.source_kind != "saved_effect" or hint.item_id is None:
            return None
        if self._matching_active_workspace() is not None:
            return None
        if hint.observable_signature not in observable_signatures_for_coordinator(self.coordinator):
            return None
        item = next(
            (
                item
                for item in self._library_snapshot.items
                if item.id == hint.item_id and item.content_hash == hint.content_hash
            ),
            None,
        )
        return item if item is not None and self._saved_effect_visible(item) else None

    def _selector_entries(self, *, active_custom: bool | None = None) -> tuple[EffectSelectorEntry, ...]:
        if active_custom is None:
            active_custom = self._matching_active_workspace() is not None
        return effect_selector_entries(
            self.coordinator.model,
            self._effect_categories,
            self._library_snapshot.items,
            prefix_effect_names=getattr(self.coordinator, "prefix_effect_names", False) is True,
            always_include_custom_effects=getattr(self.coordinator, "always_include_custom_effects", False) is True,
            active_custom=active_custom,
            native_categories=self._native_selector_categories,
        )

    def _matching_active_workspace(self) -> Any | None:
        if self._effect_backend is None or self._config_entry_id is None:
            return None
        active_workspaces = getattr(self._effect_backend, "active_workspaces", None)
        workspace = active_workspaces.get(self._config_entry_id) if active_workspaces is not None else None
        return workspace if active_workspace_matches(self.coordinator, workspace) else None

    def _saved_effect_visible(self, item: LibraryItem) -> bool:
        content_kind = effect_content_to_dict(item.content).get("kind")
        category = effect_category_for_content_kind(str(content_kind))
        return category is not None and (
            category in self._effect_categories
            or getattr(self.coordinator, "always_include_custom_effects", False) is True
        )

    @property
    def _effect_categories(self) -> frozenset[str]:
        categories = getattr(self.coordinator, "effect_categories", None)
        return categories if isinstance(categories, frozenset) else frozenset(EFFECT_CATEGORIES)

    @property
    def _native_selector_categories(self) -> frozenset[str]:
        categories = set(self._effect_categories)
        families = getattr(self.coordinator, "effect_families", None)
        if isinstance(families, frozenset):
            if EFFECT_FAMILY_SCENES not in families:
                categories.discard(EFFECT_CATEGORY_SCENES)
            if EFFECT_FAMILY_MUSIC not in families:
                categories.discard(EFFECT_CATEGORY_REACTIVE)
            if EFFECT_FAMILY_VIDEO not in families:
                categories.discard(EFFECT_CATEGORY_VIDEO)
        return frozenset(categories)

    @property
    def _can_restore_static_color(self) -> bool:
        coordinator = self.coordinator
        return (
            coordinator.color_mode in (None, ParsedMode.COLOUR)
            and coordinator.effect is None
            and coordinator.diy_code is None
            and coordinator.music_mode == "off"
            and coordinator.video_mode == "off"
            and coordinator.segment_state_source != "optimistic"
            and coordinator.rgb_color_source not in {"observed", "optimistic"}
            and coordinator.color_temp_kelvin_source not in {"observed", "optimistic"}
        )

    async def _async_restore_static_color(self) -> None:
        coordinator = self.coordinator
        if not self._can_restore_static_color:
            return
        mode_revision = coordinator._field_revisions.get("color_mode", 0)
        if (last_state := await self.async_get_last_state()) is None:
            return
        if not self._can_restore_static_color or coordinator._field_revisions.get("color_mode", 0) != mode_revision:
            return
        if last_state.attributes.get(ATTR_EFFECT) not in (None, EFFECT_OFF):
            return
        restored = _coerce_static_color(last_state.attributes, coordinator.profile)
        if restored is None and (extra_data := await self.async_get_last_extra_data()) is not None:
            restored = _coerce_static_color(extra_data.as_dict(), coordinator.profile)
        if (
            restored is None
            or not self._can_restore_static_color
            or coordinator._field_revisions.get("color_mode", 0) != mode_revision
        ):
            return
        restored_mode = restored.color_mode
        restored_rgb = restored.rgb_color
        restored_kelvin = restored.color_temp_kelvin
        if coordinator.segment_state_source == "observed":
            if (
                restored_kelvin is not None
                and coordinator.segment_colors
                and len(set(coordinator.segment_colors)) == 1
                and coordinator.segment_colors[0] == kelvin_to_rgb(restored_kelvin)
            ):
                coordinator.color_temp_kelvin = restored_kelvin
                coordinator.color_temp_kelvin_source = "restored"
                self._attr_color_mode = restored_mode
                coordinator.async_set_updated_data(coordinator.data or {})
            else:
                self._attr_color_mode = ColorMode.RGB
            return
        coordinator.install_static_color(rgb=restored_rgb, kelvin=restored_kelvin, source="restored")
        self._attr_color_mode = restored_mode
        coordinator.async_set_updated_data(coordinator.data or {})

    async def _async_restore_segments(self) -> None:
        coordinator = self.coordinator
        count = coordinator.profile.segment_count
        if not count or coordinator.segment_state_source != "initial":
            return
        if not self._can_restore_static_color:
            return
        mode_revision = coordinator._field_revisions.get("color_mode", 0)
        if (last_state := await self.async_get_last_state()) is None:
            return
        if (
            not self._can_restore_static_color
            or coordinator.segment_state_source != "initial"
            or coordinator._field_revisions.get("color_mode", 0) != mode_revision
        ):
            return
        restored = _coerce_segment_colors(last_state.attributes.get("segment_colors"), count)
        brightness = _coerce_segment_brightness(last_state.attributes.get("segment_brightness"), count)
        if restored is None or brightness is None:
            return
        coordinator.mark_segment_state_restored(restored, brightness)
        coordinator.async_set_updated_data(coordinator.data or {})

    async def _refresh_with_retry(
        self,
        *,
        expected_on: bool | None = None,
        expected_brightness: int | None = None,
        expected_rgb_color: tuple[int, int, int] | None = None,
        expected_color_temp_kelvin: int | None = None,
        expected_video_mode: str | None = None,
        expected_video_full_screen: bool | None = None,
        expected_video_saturation: int | None = None,
        expected_video_sound_effects: bool | None = None,
        expected_video_sound_effects_softness: int | None = None,
        retry_command: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if not self.coordinator.profile.state_readable:
            return
        confirm = partial(
            self.coordinator.refresh_state,
            expected_on=expected_on,
            expected_brightness=expected_brightness,
            expected_rgb_color=expected_rgb_color,
            expected_color_temp_kelvin=expected_color_temp_kelvin,
            expected_video_mode=expected_video_mode,
            expected_video_full_screen=expected_video_full_screen,
            expected_video_saturation=expected_video_saturation,
            expected_video_sound_effects=expected_video_sound_effects,
            expected_video_sound_effects_softness=expected_video_sound_effects_softness,
        )
        if await confirm():
            return
        if retry_command is not None:
            await retry_command()
        if not await confirm():
            raise RuntimeError(f"Failed to confirm state for {self.coordinator.model}")

    def _notify_state_changed(self) -> None:
        self.async_write_ha_state()
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    async def _async_supersede_preview(self) -> None:
        preview = getattr(self._effect_backend, "preview", None) if self._effect_backend is not None else None
        if preview is not None and self._config_entry_id is not None:
            await preview.async_supersede_device(
                self._config_entry_id,
                reason="home_assistant_control",
            )

    def _clear_active_workspace(self) -> None:
        active_workspaces = (
            getattr(self._effect_backend, "active_workspaces", None) if self._effect_backend is not None else None
        )
        if active_workspaces is not None and self._config_entry_id is not None:
            active_workspaces.clear(self._config_entry_id)

    def _require_support(self, service: str, *, supported: bool) -> None:
        if supported:
            return
        model = self.coordinator.model
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"service": service, "model": model},
        )

    def _compile_template_default(self, template_id: str) -> CompiledMusicProfile | CompiledVideoProfile | None:
        template_defaults = (
            getattr(self._effect_backend, "template_defaults", None) if self._effect_backend is not None else None
        )
        if template_defaults is None or self._config_entry_id is None:
            return None
        stored = template_defaults.get(self._config_entry_id, template_id)
        if stored is None or stored.model != self.coordinator.model:
            return None
        item = LibraryItem.new(template_id, stored.content)
        compiled = compile_application(item, self.coordinator.model)
        validate_video_request(self.coordinator, item.content)
        if not isinstance(compiled, CompiledMusicProfile | CompiledVideoProfile):
            raise RuntimeError("native selector template default did not compile to a native profile")
        return compiled

    def _prepare_effect(self, effect_name: str) -> Callable[[], Awaitable[None]]:
        key = normalise_effect_name(effect_name)
        coordinator = self.coordinator
        if key == EFFECT_OFF:
            return self._async_clear_effect
        try:
            selected = resolve_effect_selector(self._selector_entries(), effect_name)
        except EffectValidationError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={"effect": effect_name},
            ) from exc
        if selected is not None and selected.source == "scene":
            require_effect_route(coordinator.model, CapabilityWorkflow.NATIVE_SCENES)
            scene = MODEL_SCENES[coordinator.model][selected.value]
            scene_default = (
                scene_default_for(
                    self._effect_backend.scene_defaults,
                    self._config_entry_id,
                    coordinator.model,
                    selected.value,
                    scene,
                )
                if self._effect_backend is not None and self._config_entry_id is not None
                else None
            )
            build_native_scene_packets(
                coordinator.model,
                scene,
                speed_index=scene_default.speed_index if scene_default is not None else None,
                canonical_body=scene_default.canonical_body if scene_default is not None else None,
            )
            return partial(
                coordinator._async_apply_native_scene_locked,
                selected.value,
                scene_entry=scene,
                speed_index=scene_default.speed_index if scene_default is not None else None,
                canonical_body=scene_default.canonical_body if scene_default is not None else None,
                writer=None,
                verify=False,
                intent=ControlIntent.USER,
            )
        if selected is not None and selected.source == "video":
            compiled = self._compile_template_default(f"template:video:{selected.value}")
            if compiled is not None:
                return partial(async_apply_compiled_profile, coordinator, compiled)
            return partial(
                self._async_set_video_mode,
                mode=selected.value,
                saturation=coordinator.video_saturation,
                full_screen=coordinator.video_full_screen,
                sound_effects=(coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects),
                sound_effects_softness=coordinator.video_sound_effects_softness,
            )
        if selected is not None and selected.source == "music":
            compiled = self._compile_template_default(f"template:music:{selected.value}")
            if compiled is not None:
                return partial(async_apply_compiled_profile, coordinator, compiled)
            return partial(coordinator.async_select_music_slug, selected.value)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_effect",
            translation_placeholders={"effect": key},
        )

    async def _async_clear_effect(self) -> None:
        coordinator = self.coordinator
        coordinator.install_static_color(rgb=coordinator.rgb_color, kelvin=coordinator.color_temp_kelvin)
        if coordinator.color_temp_kelvin is not None:
            packet = build_color_temp(coordinator.color_temp_kelvin, coordinator.model)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            colour = kelvin_to_rgb(coordinator.color_temp_kelvin)
        else:
            packet = build_color_rgb(*coordinator.rgb_color, coordinator.model)
            self._attr_color_mode = ColorMode.RGB
            colour = coordinator.rgb_color
        coordinator.mark_segment_state_optimistic(colours=[colour] * len(coordinator.segment_colors))
        await coordinator.send_command(packet)
        coordinator._enter_static_mode()

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_EFFECT in kwargs:
            try:
                selected = resolve_effect_selector(self._selector_entries(), str(kwargs[ATTR_EFFECT]))
            except EffectValidationError:
                selected = None
            if selected is not None and selected.item is not None and isinstance(selected.item.content, MusicProfile):
                compile_application(selected.item, self.coordinator.model)
            elif selected is not None and selected.source == "music":
                defaults = getattr(self._effect_backend, "template_defaults", None) if self._effect_backend else None
                stored = (
                    defaults.get(self._config_entry_id, f"template:music:{selected.value}")
                    if defaults is not None and self._config_entry_id is not None
                    else None
                )
                if stored is not None and stored.model == self.coordinator.model:
                    compile_application(LibraryItem.new("Music", stored.content), self.coordinator.model)
                else:
                    variant = music_variant(self.coordinator.profile, MUSIC_MODE_SLUGS[selected.value])
                    prepare_music_request(
                        self.coordinator.model,
                        selected.value,
                        self.coordinator.music_sensitivity,
                        self.coordinator.music_color if self.coordinator.profile.supports_music_color else None,
                        self.coordinator.music_calm if variant and variant.supports_style else False,
                        {},
                        include_parameters=bool(variant and variant.supports_style),
                    )
        active_workspace = self._matching_active_workspace()
        custom_requested = (
            ATTR_EFFECT in kwargs
            and normalise_effect_name(str(kwargs[ATTR_EFFECT])) == normalise_effect_name("Custom")
            and active_workspace is not None
        )
        if custom_requested:
            kwargs = {key: value for key, value in kwargs.items() if key != ATTR_EFFECT}
            if not kwargs:
                return
        if ATTR_EFFECT in kwargs and (item := self._saved_effect(str(kwargs[ATTR_EFFECT]))) is not None:
            remaining = {key: value for key, value in kwargs.items() if key != ATTR_EFFECT}
            await self._async_apply_saved_item(
                item,
                turn_on_kwargs=remaining,
            )
            return
        prepared_effect = self._prepare_effect(str(kwargs[ATTR_EFFECT])) if ATTR_EFFECT in kwargs else None
        await self._async_supersede_preview()
        clear_workspace = active_workspace is not None and (
            ATTR_RGB_COLOR in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs or ATTR_EFFECT in kwargs
        )
        async with async_control_intent(
            self.coordinator,
            ControlIntent.USER,
        ):
            await self._async_turn_on(
                clear_workspace_on_success=clear_workspace,
                prepared_effect=prepared_effect,
                **kwargs,
            )

    async def _async_apply_saved_item(
        self,
        item: LibraryItem,
        *,
        operation_id: UUID | None = None,
        turn_on_kwargs: dict[str, Any] | None = None,
    ) -> DeploymentRecord:
        assert self._effect_backend is not None
        assert self._config_entry_id is not None
        try:
            async with self._effect_backend.application.saved_effect_for_apply(
                str(item.id),
                model=self.coordinator.model,
                expected_version=item.version,
            ) as current:
                validate_video_request(self.coordinator, current.content)
                await self._async_supersede_preview()
                async with async_control_intent(
                    self.coordinator,
                    ControlIntent.USER,
                ):
                    if turn_on_kwargs is not None:
                        await self._async_turn_on(**turn_on_kwargs)
                    if operation_id is None:
                        return await self._effect_backend.engine.async_apply_saved(
                            self.coordinator,
                            current,
                            config_entry_id=self._config_entry_id,
                            updated_at=dt_util.utcnow().isoformat(),
                        )
                    return await self._effect_backend.engine.async_apply_saved(
                        self.coordinator,
                        current,
                        config_entry_id=self._config_entry_id,
                        updated_at=dt_util.utcnow().isoformat(),
                        operation_id=operation_id,
                    )
        except (EffectNotFoundError, EffectVersionConflictError) as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={"effect": item.name},
            ) from exc
        except HomeAssistantError:
            raise
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="effect_apply_failed",
            ) from exc

    async def async_apply_custom_effect(
        self,
        effect: str | None = None,
        effect_id: str | None = None,
    ) -> dict[str, Any]:
        if self._effect_backend is None or self._config_entry_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="effect_storage_unavailable",
            )
        if (effect is None) == (effect_id is None):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_custom_effect",
            )
        operation_id = uuid4()
        self._record_custom_effect_service(
            DiagnosticOutcome.STARTED,
            "apply_request_received",
            operation_id,
        )
        item: LibraryItem | None
        if effect is not None:
            item = self._saved_effect(effect)
        else:
            try:
                item = self._effect_backend.application.get_saved_effect(
                    str(UUID(effect_id or "")),
                )
            except ValueError, EffectNotFoundError:
                item = None
            if item is not None and not self._saved_effect_visible(item):
                item = None
        if item is None:
            self._record_custom_effect_service(
                DiagnosticOutcome.FAILED,
                "invalid_effect",
                operation_id,
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_custom_effect",
            )
        try:
            deployment = await self._async_apply_saved_item(
                item,
                operation_id=operation_id,
            )
        except Exception:
            self._record_custom_effect_service(
                DiagnosticOutcome.FAILED,
                "apply_failed",
                operation_id,
            )
            raise
        self._record_custom_effect_service(
            DiagnosticOutcome.SUCCEEDED,
            "apply_completed",
            operation_id,
        )
        return deployment.to_public_dict()

    def _record_custom_effect_service(
        self,
        outcome: DiagnosticOutcome,
        code: str,
        operation_id: UUID,
    ) -> None:
        diagnostics = getattr(self._effect_backend, "diagnostics", None) if self._effect_backend is not None else None
        if diagnostics is not None:
            diagnostics.record(
                DiagnosticStage.API_SERVICE,
                outcome,
                code,
                correlation_id=str(operation_id),
                config_entry_id=self._config_entry_id,
                operation_id=str(operation_id),
            )

    def _saved_effect(self, effect_name: str) -> LibraryItem | None:
        try:
            selected = resolve_effect_selector(self._selector_entries(), effect_name)
            return selected.item if selected is not None and selected.source == "saved" else None
        except EffectValidationError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={"effect": effect_name},
            ) from exc

    async def _async_turn_on(
        self,
        *,
        clear_workspace_on_success: bool = False,
        prepared_effect: Callable[[], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> None:
        power_on = partial(
            self.coordinator.send_command,
            build_power(True, self.coordinator.model),
        )
        with self._rollback():
            if not self.coordinator.is_on:
                await power_on()
                self.coordinator.is_on = True
                await self._refresh_with_retry(expected_on=True, retry_command=power_on)
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, min(100, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))

                async def apply_brightness() -> None:
                    await self.coordinator.send_command(build_brightness(pct, self.coordinator.model))

                await apply_brightness()
                self.coordinator.brightness_pct = pct
                await self._refresh_with_retry(
                    expected_brightness=pct,
                    retry_command=apply_brightness,
                )
            if ATTR_RGB_COLOR in kwargs:
                self._require_support("RGB colour", supported=self.coordinator.profile.supports_rgb)
                r, g, b = kwargs[ATTR_RGB_COLOR]
                packet = build_color_rgb(r, g, b, self.coordinator.model)
                self.coordinator.install_static_color(rgb=(r, g, b))
                self.coordinator.mark_segment_state_optimistic(
                    colours=[(r, g, b)] * len(self.coordinator.segment_colors),
                )
                self._attr_color_mode = ColorMode.RGB
                self.coordinator._enter_static_mode()
                await self.coordinator.send_command(packet)
                if self.coordinator.profile.static_readback_echoes_color:
                    await self._refresh_with_retry(
                        expected_rgb_color=(r, g, b),
                        retry_command=partial(self.coordinator.send_command, packet),
                    )
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                self._require_support(
                    "colour temperature",
                    supported=self.coordinator.profile.supports_color_temperature,
                )
                kelvin = max(
                    self.coordinator.profile.min_color_temp_kelvin,
                    min(self.coordinator.profile.max_color_temp_kelvin, kwargs[ATTR_COLOR_TEMP_KELVIN]),
                )
                packet = build_color_temp(kelvin, self.coordinator.model)
                self.coordinator.install_static_color(kelvin=kelvin)
                self.coordinator.mark_segment_state_optimistic(
                    colours=[kelvin_to_rgb(kelvin)] * len(self.coordinator.segment_colors),
                )
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self.coordinator._enter_static_mode()
                await self.coordinator.send_command(packet)
                if self.coordinator.profile.static_readback_kelvin:
                    await self._refresh_with_retry(
                        expected_color_temp_kelvin=kelvin,
                        retry_command=partial(self.coordinator.send_command, packet),
                    )
            if prepared_effect is not None:
                await prepared_effect()
        if clear_workspace_on_success:
            self._clear_active_workspace()
        self._notify_state_changed()

    async def async_turn_off(self, **kwargs: Any) -> None:
        clear_workspace = self._matching_active_workspace() is not None
        await self._async_supersede_preview()
        async with async_control_intent(
            self.coordinator,
            ControlIntent.USER,
        ):
            await self._async_turn_off(
                clear_workspace_on_success=clear_workspace,
                **kwargs,
            )

    async def _async_turn_off(
        self,
        *,
        clear_workspace_on_success: bool = False,
        **kwargs: Any,
    ) -> None:
        power_off = partial(
            self.coordinator.send_command,
            build_power(False, self.coordinator.model),
        )
        with self._rollback():
            await power_off()
            self.coordinator.is_on = False
            await self._refresh_with_retry(expected_on=False, retry_command=power_off)
        if clear_workspace_on_success:
            self._clear_active_workspace()
        self._notify_state_changed()
