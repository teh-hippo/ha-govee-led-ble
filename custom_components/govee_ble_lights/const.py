"""Constants for Govee BLE Lights."""

from __future__ import annotations

from dataclasses import dataclass, field

DOMAIN = "govee_ble_lights"
CONF_MODEL = "model"


@dataclass(frozen=True)
class ModelProfile:
    name: str
    state_readable: bool = False
    scene_source: str = "none"
    effects: list[str] = field(default_factory=list)
    ble_name_prefixes: list[str] = field(default_factory=list)


MODEL_PROFILES: dict[str, ModelProfile] = {
    "H617A": ModelProfile(
        "H617A LED Strip",
        scene_source="api",
        ble_name_prefixes=["ihoment_H617A", "Govee_H617A", "GBK_H617A", "GVH_H617A"],
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        state_readable=True,
        effects=["video: movie", "video: game", "music: energic", "music: rhythm", "music: spectrum", "music: rolling"],
        ble_name_prefixes=["Govee_H6199", "ihoment_H6199", "GBK_H6199", "GVH_H6199"],
    ),
}


def get_profile(model: str) -> ModelProfile:
    return MODEL_PROFILES.get(model, MODEL_PROFILES["H617A"])
