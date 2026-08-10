"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

from dataclasses import dataclass
from typing import Literal

from .const import EFFECT_FAMILY_SCENES, MUSIC_MODE_SLUGS
from .coordinator_base import _CoordinatorBase
from .protocol import (
    RHYTHM_MODE_ID,
    build_color_rgb,
    build_color_temp,
    build_music_mode_with_color,
    build_music_params_a3,
    build_power,
    build_scene_multi,
    build_white_brightness,
)
from .scenes import MODEL_SCENES, SceneEntry


@dataclass(frozen=True)
class PreModeSnapshot:
    """The typed static state to re-apply when leaving a music or video mode.

    ``kind`` selects which payload is meaningful; the others carry inert defaults so a fresh
    coordinator always has a defined state to restore.
    """

    kind: Literal["rgb", "color_temp", "white"] = "rgb"
    rgb: tuple[int, int, int] = (255, 255, 255)
    kelvin: int = 0
    level: int = 100


BLOOM_MODE_ID = MUSIC_MODE_SLUGS["bloom"]
SHINY_MODE_ID = MUSIC_MODE_SLUGS["shiny"]
# Modes whose govee_common::music_selector style byte carries Dynamic/Calm.
MUSIC_STYLE_MODE_IDS = frozenset({RHYTHM_MODE_ID, BLOOM_MODE_ID, SHINY_MODE_ID})
# Slugs for the style-carrying modes, derived so the set never drifts from the id set above.
MUSIC_STYLE_SLUGS = frozenset(slug for slug, mode_id in MUSIC_MODE_SLUGS.items() if mode_id in MUSIC_STYLE_MODE_IDS)
# Bloom and Shiny also carry Dynamic/Calm in their a3 movement companion; Rhythm rides byte 5 alone.
# Absolute a3 offsets keyed by ``calm``; the Dynamic (False) values equal the capture-pinned templates.
_MUSIC_STYLE_COMPANION: dict[int, dict[bool, dict[int, int]]] = {
    BLOOM_MODE_ID: {False: {27: 0x50}, True: {27: 0x14}},
    SHINY_MODE_ID: {False: {20: 0x05, 21: 0x64}, True: {20: 0x14, 21: 0x46}},
}


class _ActiveModeMixin(_CoordinatorBase):
    """Derives the coarse operating mode and routes music-mode entry/exit."""

    @property
    def scene_name_set(self) -> frozenset[str]:
        if EFFECT_FAMILY_SCENES not in self.effect_families:
            return frozenset()
        return frozenset(MODEL_SCENES[self.model])

    @property
    def active_mode(self) -> str:
        if not self.is_on:
            return "off"
        if self.diy_code is not None:
            return "custom"
        if self.effect in self.scene_name_set:
            return "scene"
        if self.music_mode not in (None, "off"):
            return "music"
        if self.video_mode not in (None, "off"):
            return "video"
        return "colour"

    @property
    def scene_speed_context(self) -> tuple[str, SceneEntry] | None:
        """Return the active H617A scene and its complete catalogue Speed metadata."""
        if not self.profile.supports_scene_speed or self.active_mode != "scene" or self.effect is None:
            return None
        scene = MODEL_SCENES[self.model].get(self.effect)
        if scene is None or scene.speed is None:
            return None
        _ = scene.speed.option_count
        return self.effect, scene

    def _sync_scene_speed(self, scene_name: str | None, *, speed_index: int | None = None) -> None:
        """Tie the optimistic speed position to one scene, defaulting on a scene change."""
        scene = (
            MODEL_SCENES[self.model].get(scene_name)
            if self.profile.supports_scene_speed and scene_name is not None
            else None
        )
        if scene is None or scene.speed is None:
            self.scene_speed_scene_code = self.scene_speed_index = None
            return
        count = scene.speed.option_count
        if (
            speed_index is None
            and self.scene_speed_scene_code == scene.code
            and self.scene_speed_index is not None
            and 0 <= self.scene_speed_index < count
        ):
            return
        resolved = scene.speed.default_index if speed_index is None else speed_index
        if not 0 <= resolved < count:
            raise ValueError(f"scene speed index {resolved} outside 0..{count - 1}")
        self.scene_speed_scene_code, self.scene_speed_index = scene.code, resolved

    async def async_set_scene_speed(self, index: int) -> None:
        """Re-upload the active scene at one documented Speed position.

        The status reply confirms scene identity but does not carry the Speed position, so the
        resulting index remains optimistic even after the scene check succeeds.
        """
        async with self._control_lock:
            context = self.scene_speed_context
            if context is None:
                raise ValueError("The active scene does not expose a documented Speed control")
            scene_name, scene = context
            assert scene.speed is not None
            if not 0 <= index < scene.speed.option_count:
                raise ValueError(f"scene speed index {index} outside 0..{scene.speed.option_count - 1}")
            if self.scene_speed_scene_code == scene.code and self.scene_speed_index == index:
                return

            async def apply() -> None:
                for packet in build_scene_multi(
                    scene.param,
                    scene.code,
                    scene.scene_type,
                    scene.speed,
                    speed_index=index,
                ):
                    await self.send_command(packet)

            await apply()
            if self.profile.state_readable and not await self.refresh_state(expected_effect=scene_name):
                await apply()
                if not await self.refresh_state(expected_effect=scene_name):
                    raise RuntimeError(f"Failed to confirm scene {scene_name!r} after changing Speed")
            self._sync_scene_speed(scene_name, speed_index=index)
            self.async_set_updated_data(self.data or {})

    def _capture_static_state(self) -> PreModeSnapshot:
        if self.color_temp_kelvin is not None:
            return PreModeSnapshot(kind="color_temp", kelvin=self.color_temp_kelvin)
        return PreModeSnapshot(kind="rgb", rgb=self.rgb_color)

    def _enter_static_mode(self) -> None:
        """Clear every non-static mode so exactly one operating mode is active."""
        self.effect = None
        self.diy_code = None
        self.music_mode = self.video_mode = "off"

    async def async_select_music_slug(self, slug: str) -> None:
        if slug == "off":
            await self.async_restore_pre_mode()
            return
        if slug not in self.profile.music_modes:
            raise ValueError(f"{self.model} does not support music mode {slug}")
        if self.active_mode == "colour":
            self._pre_mode_snapshot = self._capture_static_state()
        mode_id = MUSIC_MODE_SLUGS[slug]
        calm = self.music_calm if mode_id in MUSIC_STYLE_MODE_IDS else False
        color = self.music_color if self.profile.supports_music_color else None
        await self.send_command(build_power(True, self.model))
        self.is_on = True
        await self.send_command(
            build_music_mode_with_color(
                mode_id,
                sensitivity=self.music_sensitivity,
                color=color,
                calm=calm,
                model=self.model,
            )
        )
        if mode_id in _MUSIC_STYLE_COMPANION:
            for packet in build_music_params_a3(mode_id, _MUSIC_STYLE_COMPANION[mode_id][self.music_calm]):
                await self.send_command(packet)
        self.music_mode, self.video_mode = slug, "off"
        self.effect = None
        self.diy_code = None

    async def async_restore_pre_mode(self) -> None:
        snap = self._pre_mode_snapshot
        match snap.kind:
            case "color_temp":
                await self.send_command(build_color_temp(snap.kelvin, self.model))
            case "white":
                await self.send_command(build_white_brightness(snap.level, self.model))
            case _:
                await self.send_command(build_color_rgb(*snap.rgb, self.model))
        self._enter_static_mode()
