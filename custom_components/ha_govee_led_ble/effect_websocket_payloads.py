"""Public payload builders for Effect Studio WebSocket responses."""

from typing import Any

from .const import MUSIC_MODE_SLUGS, ModelProfile, resolve_model
from .effect_catalogue import MODEL_EFFECT_CATALOGUES
from .effect_deployments import DeploymentSnapshot
from .effect_domain import (
    BuiltinScene,
    LayeredScene,
    LibraryItem,
    PaintedEffect,
    PaletteScene,
    effect_content_to_dict,
)
from .effect_storage import LibrarySnapshot
from .music_commands import music_body_parameters, music_body_style
from .music_semantics import retained_music_profile


def device_music_settings(model: str, *, profile: ModelProfile) -> dict[str, Any]:
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    return {} if catalogue is None else {"music_settings": catalogue.to_dict(profile=profile)["music_settings"]}


def retained_music_edit(coordinator: Any) -> dict[str, Any] | None:
    """Expose retained edit context separately from fresh-authoring capabilities/readback."""
    body = coordinator.music_body
    mode = coordinator.music_mode
    if not isinstance(body, bytes) or mode not in coordinator.profile.music_modes:
        return None
    try:
        profile = retained_music_profile(coordinator.profile, MUSIC_MODE_SLUGS[mode])
        settings = device_music_settings(coordinator.model, profile=profile)["music_settings"][mode]
        parameters = music_body_parameters(body, mode, profile=profile)
        return {
            "mode": mode,
            "revision": coordinator._music_body_revision,
            "parameters": {key: value for key, value in parameters.items() if key in settings["parameters"]},
            "calm": music_body_style(body, mode, profile=profile),
            "settings": settings,
        }
    except ValueError:
        return None


def item_summary(item: LibraryItem) -> dict[str, Any]:
    content = effect_content_to_dict(item.content)
    kind = content["kind"]
    summary = {
        "id": str(item.id),
        "version": item.version,
        "updated_at": item.updated_at,
        "name": item.name,
        "kind": kind,
        "content_hash": item.content_hash,
        "origin": {
            "kind": item.origin.kind.value,
            "source_id": item.origin.source_id,
        },
    }
    model = (
        content.get("model")
        if kind
        in {
            "palette_diy",
            "music_profile",
            "video_profile",
            "workshop",
        }
        else None
    )
    if isinstance(model, str) and resolve_model(model) is not None:
        summary["model"] = model
    elif kind in {"scene_builtin", "scene_palette", "scene_layered"}:
        template = content.get("template")
        sku = template.get("sku") if isinstance(template, dict) else None
        if isinstance(sku, str) and resolve_model(sku) is not None:
            summary["model"] = sku
    elif isinstance(item.content, PaintedEffect) and item.content.addressing == "physical_ic":
        summary["model"] = "H6099"
    elif item.target_hint is not None and resolve_model(item.target_hint.model) is not None:
        summary["model"] = item.target_hint.model
    elif item.target_hint is None and kind in {"h617a_painted", "h617a_single", "h617a_multi"}:
        summary["model"] = "H617A"
    if isinstance(item.content, BuiltinScene | PaletteScene | LayeredScene):
        summary["template"] = content["template"]
    return summary


def library_snapshot_payload(snapshot: LibrarySnapshot) -> dict[str, Any]:
    return {
        "generation": snapshot.generation,
        "items": [item_summary(item) for item in snapshot.items],
    }


def deployment_snapshot_payload(snapshot: DeploymentSnapshot) -> dict[str, Any]:
    return {
        "version": snapshot.version,
        "deployments": [record.to_public_dict() for record in snapshot.records],
    }
