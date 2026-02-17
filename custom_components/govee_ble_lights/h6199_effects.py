"""Shared H6199 effect mappings and command helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .protocol import build_brightness, build_color_rgb, build_music_mode_with_color, build_video_mode

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator


VIDEO_EFFECT_GAME_MODE: dict[str, bool] = {
    "video: movie": False,
    "video: game": True,
}

VIDEO_MODE_GAME_MODE: dict[str, bool] = {
    "movie": False,
    "game": True,
}

MUSIC_MODE_IDS: dict[str, int] = {
    "energic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
}

MUSIC_EFFECT_MODE_IDS: dict[str, int] = {f"music: {name}": mode_id for name, mode_id in MUSIC_MODE_IDS.items()}


def video_game_mode_from_effect(effect: str | None) -> bool | None:
    """Return game_mode bool for a video effect string."""
    if effect is None:
        return None
    return VIDEO_EFFECT_GAME_MODE.get(effect)


def music_mode_id_from_effect(effect: str | None) -> int | None:
    """Return music mode ID for a music effect string."""
    if effect is None:
        return None
    return MUSIC_EFFECT_MODE_IDS.get(effect)


async def apply_video_mode_from_state(
    coordinator: GoveeBLECoordinator,
    *,
    game_mode: bool,
) -> None:
    """Send the video-mode packet using coordinator state values."""
    await coordinator.send_command(
        build_video_mode(
            full_screen=coordinator.video_full_screen,
            game_mode=game_mode,
            saturation=coordinator.video_saturation,
            sound_effects=coordinator.video_sound_effects,
            sound_effects_softness=coordinator.video_sound_effects_softness,
        )
    )


async def apply_active_video_mode_from_state(coordinator: GoveeBLECoordinator) -> bool:
    """Reapply active video mode using coordinator values."""
    if not coordinator.is_on:
        return False
    game_mode = video_game_mode_from_effect(coordinator.effect)
    if game_mode is None:
        return False
    await apply_video_mode_from_state(coordinator, game_mode=game_mode)
    return True


async def apply_active_video_brightness_from_state(coordinator: GoveeBLECoordinator) -> bool:
    """Reapply active video brightness using coordinator values."""
    if not coordinator.is_on:
        return False
    if video_game_mode_from_effect(coordinator.effect) is None:
        return False
    await coordinator.send_command(build_brightness(coordinator.video_brightness))
    coordinator.brightness_pct = coordinator.video_brightness
    return True


async def apply_white_brightness_from_state(coordinator: GoveeBLECoordinator) -> bool:
    """Apply white-channel brightness using coordinator values."""
    if not coordinator.is_on:
        return False
    await coordinator.send_command(build_color_rgb(255, 255, 255))
    await coordinator.send_command(build_brightness(coordinator.white_brightness))
    coordinator.brightness_pct = coordinator.white_brightness
    coordinator.rgb_color = (255, 255, 255)
    coordinator.color_temp_kelvin = None
    coordinator.effect = None
    return True


async def apply_active_music_mode_from_state(coordinator: GoveeBLECoordinator) -> bool:
    """Reapply active music mode using coordinator values."""
    if not coordinator.is_on:
        return False
    mode_id = music_mode_id_from_effect(coordinator.effect)
    if mode_id is None:
        return False
    await coordinator.send_command(
        build_music_mode_with_color(
            mode_id,
            sensitivity=coordinator.music_sensitivity,
            color=coordinator.music_color,
        )
    )
    return True
