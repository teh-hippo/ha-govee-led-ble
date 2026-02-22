"""Constants for HA Govee LED BLE."""

from dataclasses import dataclass, field

DOMAIN = "ha_govee_led_ble"
CONF_MODEL = "model"


@dataclass(frozen=True)
class ModelProfile:
    name: str
    state_readable: bool = False
    scene_source: str = "none"
    effects: list[str] = field(default_factory=list)
    ble_name_prefixes: list[str] = field(default_factory=list)
    supports_video_mode: bool = False
    supports_music_mode: bool = False
    supports_white_brightness: bool = False
    supports_advanced_controls: bool = False


MUSIC_EFFECTS: tuple[str, ...] = ("music: energic", "music: rhythm", "music: spectrum", "music: rolling")
VIDEO_EFFECTS: tuple[str, ...] = ("video: movie", "video: game")


MODEL_PROFILES: dict[str, ModelProfile] = {
    "H617A": ModelProfile(
        "H617A LED Strip",
        state_readable=True,
        scene_source="api",
        effects=[*MUSIC_EFFECTS],
        ble_name_prefixes=["ihoment_H617A", "Govee_H617A", "GBK_H617A", "GVH_H617A"],
        supports_music_mode=True,
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        state_readable=True,
        effects=[*VIDEO_EFFECTS, *MUSIC_EFFECTS],
        ble_name_prefixes=["Govee_H6199", "ihoment_H6199", "GBK_H6199", "GVH_H6199"],
        supports_video_mode=True,
        supports_music_mode=True,
        supports_white_brightness=True,
        supports_advanced_controls=True,
    ),
}


def get_profile(model: str) -> ModelProfile:
    return MODEL_PROFILES.get(model, MODEL_PROFILES["H617A"])
