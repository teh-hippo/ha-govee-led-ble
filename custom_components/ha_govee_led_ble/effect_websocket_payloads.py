"""Public payload builders for Effect Studio WebSocket responses."""

from typing import Any

from .const import protocol_model
from .effect_deployments import DeploymentSnapshot
from .effect_domain import (
    BuiltinScene,
    LayeredScene,
    LibraryItem,
    PaletteScene,
    effect_content_to_dict,
)
from .effect_storage import LibrarySnapshot


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
    if model in {"H617A", "H617E", "H6199"}:
        summary["model"] = model
    elif kind in {"h617a_painted", "h617a_single", "h617a_multi"}:
        hinted_model = item.target_hint.model if item.target_hint is not None else None
        summary["model"] = hinted_model if protocol_model(hinted_model or "") == "H617A" else "H617A"
    elif kind in {"scene_builtin", "scene_palette", "scene_layered"}:
        template = content.get("template")
        if isinstance(template, dict) and template.get("sku") in {"H617A", "H617E", "H6199"}:
            summary["model"] = template["sku"]
    elif item.target_hint is not None and item.target_hint.model in {"H617A", "H617E", "H6199"}:
        summary["model"] = item.target_hint.model
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
