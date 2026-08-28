"""Light entity for HA Govee LED BLE."""

# fmt: off
import logging
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
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
from homeassistant.helpers.restore_state import RestoreEntity
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
    effect_category_for_content_kind,
)
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .coordinator_status import ParsedMode
from .effect_backend import EffectBackend
from .effect_compiler import CompiledMusicProfile, CompiledVideoProfile, compile_application
from .effect_deployments import DeploymentRecord
from .effect_diagnostics import DiagnosticOutcome, DiagnosticStage
from .effect_domain import EffectValidationError, LibraryItem, effect_content_to_dict
from .effect_runtime import async_apply_compiled_profile, observable_signature_for_coordinator
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
from .native_profile_controls import apply_active_video_mode as apply_active_video_mode
from .scenes import MODEL_SCENES

# fmt: on

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000


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
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

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
        self._attr_color_mode = ColorMode.RGB
        self._config_entry_id = config_entry_id
        self._effect_backend = effect_backend
        self._library_snapshot = (
            effect_backend.application.library_snapshot() if effect_backend is not None else LibrarySnapshot(())
        )

    @contextmanager
    def _rollback(self) -> Generator[None]:
        snap = {f: getattr(self.coordinator, f) for f in _STATE_FIELDS}
        mode_snap = self._attr_color_mode
        try:
            yield
        except Exception as err:
            for f, v in snap.items():
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
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self.coordinator.rgb_color if self._attr_color_mode == ColorMode.RGB else None

    @property
    def color_temp_kelvin(self) -> int | None:
        return self.coordinator.color_temp_kelvin if self._attr_color_mode == ColorMode.COLOR_TEMP else None

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
        observable_signature = observable_signature_for_coordinator(self.coordinator)
        if self._matching_active_workspace() is not None:
            return None
        if hint.observable_signature != observable_signature:
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
        observable_signature = observable_signature_for_coordinator(self.coordinator)
        if (
            workspace is None
            or workspace.model != self.coordinator.model
            or workspace.observable_signature != observable_signature
        ):
            return None
        return workspace

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

    async def _async_restore_static_color(self) -> None:
        coordinator = self.coordinator
        if coordinator.color_mode not in (None, ParsedMode.COLOUR):
            return
        if (
            coordinator.effect is not None
            or coordinator.diy_code is not None
            or coordinator.music_mode != "off"
            or coordinator.video_mode != "off"
        ):
            return
        if (last_state := await self.async_get_last_state()) is None:
            return
        if last_state.attributes.get(ATTR_EFFECT):
            return
        raw_mode = last_state.attributes.get(ATTR_COLOR_MODE)
        if isinstance(raw_mode, ColorMode):
            restored_mode = raw_mode
        elif isinstance(raw_mode, str):
            try:
                restored_mode = ColorMode(raw_mode)
            except ValueError:
                return
        else:
            return
        restored_rgb: tuple[int, int, int] | None = None
        restored_kelvin: int | None = None
        if restored_mode is ColorMode.RGB:
            restored_rgb = _coerce_rgb(last_state.attributes.get(ATTR_RGB_COLOR))
            if restored_rgb is None:
                return
        elif restored_mode is ColorMode.COLOR_TEMP:
            try:
                restored_kelvin = int(last_state.attributes[ATTR_COLOR_TEMP_KELVIN])
            except KeyError, TypeError, ValueError:
                return
            if not MIN_COLOR_TEMP_KELVIN <= restored_kelvin <= MAX_COLOR_TEMP_KELVIN:
                return
        else:
            return
        if coordinator.segment_state_source == "observed":
            if (
                restored_kelvin is not None
                and coordinator.segment_colors
                and len(set(coordinator.segment_colors)) == 1
                and coordinator.segment_colors[0] == kelvin_to_rgb(restored_kelvin)
            ):
                coordinator.color_temp_kelvin = restored_kelvin
                self._attr_color_mode = restored_mode
                coordinator.async_set_updated_data(coordinator.data or {})
            else:
                self._attr_color_mode = ColorMode.RGB
            return
        if restored_rgb is not None:
            coordinator.rgb_color = restored_rgb
            coordinator.color_temp_kelvin = None
        else:
            coordinator.color_temp_kelvin = restored_kelvin
        self._attr_color_mode = restored_mode
        coordinator.async_set_updated_data(coordinator.data or {})

    async def _async_restore_segments(self) -> None:
        coordinator = self.coordinator
        count = coordinator.profile.segment_count
        if not count or coordinator.segment_state_source != "initial":
            return
        if coordinator.color_mode not in (None, ParsedMode.COLOUR):
            return
        if coordinator.music_mode != "off" or coordinator.video_mode != "off" or coordinator.diy_code is not None:
            return
        if coordinator.effect is not None:
            return
        if (last_state := await self.async_get_last_state()) is None:
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

    async def _async_apply_template_default(self, template_id: str) -> bool:
        template_defaults = (
            getattr(self._effect_backend, "template_defaults", None) if self._effect_backend is not None else None
        )
        if template_defaults is None or self._config_entry_id is None:
            return False
        stored = template_defaults.get(self._config_entry_id, template_id)
        if stored is None or stored.model != self.coordinator.model:
            return False
        item = LibraryItem.new(template_id, stored.content)
        compiled = compile_application(item, self.coordinator.model)
        if not isinstance(compiled, CompiledMusicProfile | CompiledVideoProfile):
            raise RuntimeError("native selector template default did not compile to a native profile")
        await async_apply_compiled_profile(self.coordinator, compiled)
        return True

    async def _apply_effect(self, effect_name: str) -> None:
        key = normalise_effect_name(effect_name)
        coordinator = self.coordinator
        if key == EFFECT_OFF:
            if coordinator.color_temp_kelvin is not None:
                await coordinator.send_command(
                    build_color_temp(
                        coordinator.color_temp_kelvin,
                        coordinator.model,
                    )
                )
                self._attr_color_mode = ColorMode.COLOR_TEMP
                coordinator.mark_segment_state_optimistic(
                    colours=[kelvin_to_rgb(coordinator.color_temp_kelvin)] * len(coordinator.segment_colors),
                )
            else:
                await coordinator.send_command(
                    build_color_rgb(
                        *coordinator.rgb_color,
                        coordinator.model,
                    )
                )
                self._attr_color_mode = ColorMode.RGB
                coordinator.mark_segment_state_optimistic(
                    colours=[coordinator.rgb_color] * len(coordinator.segment_colors),
                )
            coordinator._enter_static_mode()
            return
        if key == normalise_effect_name("Custom") and self._matching_active_workspace() is not None:
            return
        try:
            selected = resolve_effect_selector(self._selector_entries(), effect_name)
        except EffectValidationError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={"effect": effect_name},
            ) from exc
        if selected is not None and selected.source == "scene":
            scene = MODEL_SCENES[coordinator.model][selected.value]
            scene_default = (
                self._effect_backend.scene_defaults.get(
                    self._config_entry_id,
                    scene.scene_id,
                    scene.effect_id,
                )
                if self._effect_backend is not None and self._config_entry_id is not None
                else None
            )
            await coordinator._async_apply_native_scene_locked(
                selected.value,
                speed_index=scene_default.speed_index if scene_default is not None else None,
                canonical_body=scene_default.canonical_body if scene_default is not None else None,
                writer=None,
                verify=False,
                intent=ControlIntent.USER,
            )
            return
        if selected is not None and selected.source == "video":
            if await self._async_apply_template_default(f"template:video:{selected.value}"):
                return
            await self._async_set_video_mode(
                mode=selected.value,
                saturation=coordinator.video_saturation,
                full_screen=coordinator.video_full_screen,
                sound_effects=(coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects),
                sound_effects_softness=coordinator.video_sound_effects_softness,
            )
            return
        if selected is not None and selected.source == "music":
            if await self._async_apply_template_default(f"template:music:{selected.value}"):
                return
            await coordinator.async_select_music_slug(selected.value)
            return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_effect",
            translation_placeholders={"effect": key},
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
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
        await self._async_supersede_preview()
        if ATTR_EFFECT in kwargs and (item := self._saved_effect(str(kwargs[ATTR_EFFECT]))) is not None:
            remaining = {key: value for key, value in kwargs.items() if key != ATTR_EFFECT}
            await self._async_apply_saved_item(
                item,
                turn_on_kwargs=remaining,
            )
            return
        clear_workspace = active_workspace is not None and (
            ATTR_RGB_COLOR in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs or ATTR_EFFECT in kwargs
        )
        async with async_control_intent(
            self.coordinator,
            ControlIntent.USER,
        ):
            await self._async_turn_on(
                clear_workspace_on_success=clear_workspace,
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
                expected_version=item.version,
            ) as current:
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
        await self._async_supersede_preview()
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
                r, g, b = kwargs[ATTR_RGB_COLOR]
                await self.coordinator.send_command(build_color_rgb(r, g, b, self.coordinator.model))
                self.coordinator.rgb_color = (r, g, b)
                self.coordinator.mark_segment_state_optimistic(
                    colours=[(r, g, b)] * len(self.coordinator.segment_colors),
                )
                self._attr_color_mode, self.coordinator.color_temp_kelvin = ColorMode.RGB, None
                self.coordinator._enter_static_mode()
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                await self.coordinator.send_command(build_color_temp(kelvin, self.coordinator.model))
                self.coordinator.color_temp_kelvin = kelvin
                self.coordinator.mark_segment_state_optimistic(
                    colours=[kelvin_to_rgb(kelvin)] * len(self.coordinator.segment_colors),
                )
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self.coordinator._enter_static_mode()
            if ATTR_EFFECT in kwargs:
                await self._apply_effect(str(kwargs[ATTR_EFFECT]))
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
