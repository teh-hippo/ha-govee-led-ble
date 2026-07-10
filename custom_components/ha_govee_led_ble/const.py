"""Constants for HA Govee LED BLE."""

from dataclasses import dataclass

DOMAIN = "ha_govee_led_ble"
CONF_MODEL = "model"


@dataclass(frozen=True)
class ModelProfile:
    name: str
    state_readable: bool = False
    scene_source: str = "none"
    supports_video_mode: bool = False
    supports_music_mode: bool = False
    supports_music_style: bool = False
    supports_music_params: bool = False
    supports_white_brightness: bool = False
    supports_diy: bool = False
    supports_timers: bool = False
    supports_poweroff_memory: bool = False
    segment_count: int = 0

    @property
    def supports_segments(self) -> bool:
        return self.segment_count > 0


MUSIC_MODES: dict[str, int] = {
    "energetic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
    "separation": 0x32,
    "hopping": 0x33,
    "piano keys": 0x34,
    "fountain": 0x35,
    "day and night": 0x37,
    "bloom": 0x30,
    "shiny": 0x31,
}

# Single source of truth for the ``select.music_mode`` options: HA slugs (underscored, no
# "off") mapped to their live-confirmed mode codes. Distinct from ``MUSIC_MODES`` above, whose
# spaced display names remain the parse/service vocabulary.
MUSIC_MODE_SLUGS: dict[str, int] = {
    "energetic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
    "separation": 0x32,
    "hopping": 0x33,
    "piano_keys": 0x34,
    "fountain": 0x35,
    "day_and_night": 0x37,
    "bloom": 0x30,
    "shiny": 0x31,
}


MODEL_PROFILES: dict[str, ModelProfile] = {
    "H617A": ModelProfile(
        "H617A LED Strip",
        state_readable=True,
        scene_source="api",
        supports_music_mode=True,
        supports_music_style=True,
        supports_music_params=True,
        supports_diy=True,
        supports_timers=True,
        segment_count=15,
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        state_readable=True,
        supports_video_mode=True,
        supports_music_mode=True,
        supports_white_brightness=True,
        supports_diy=True,
        supports_timers=True,
        supports_poweroff_memory=True,
        segment_count=15,
    ),
}


def get_profile(model: str) -> ModelProfile:
    return MODEL_PROFILES.get(model, MODEL_PROFILES["H617A"])
