"""Authenticated WebSocket API for the optional advanced-effect backend."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .effect_backend import EffectBackend
from .effect_catalogue import (
    custom_effect_catalogue_payload,
    resolve_catalogue_template,
    validate_catalogue_template_identity,
)
from .effect_contracts import EditorApiInfo, device_effect_capabilities
from .effect_deployments import DeploymentSnapshot
from .effect_domain import (
    EffectValidationError,
    OpaqueContent,
    Origin,
    SourceKind,
    effect_content_from_dict,
    effect_content_hash,
    effect_content_to_dict,
)
from .effect_limits import (
    MAX_EDITOR_DEVICES,
    MAX_SCENE_CATALOGUE_ENTRIES,
)
from .effect_preview import (
    PreviewError,
    PreviewHealthStatus,
    PreviewOwnershipError,
    PreviewSequenceError,
    PreviewSessionNotFoundError,
    PreviewShutdownError,
    PreviewStatus,
    PreviewTargetUnavailableError,
)
from .effect_scenes import (
    async_apply_scene,
    async_reset_scene_default,
    async_set_scene_default,
    scene_catalogue_payload,
    scene_detail_payload,
)
from .effect_selector import ReservedEffectNameError, SavedEffectNameConflictError
from .effect_storage import (
    EffectLimitError,
    EffectNotFoundError,
    EffectStorageError,
    EffectVersionConflictError,
    LibrarySnapshot,
)
from .effect_template_defaults import CatalogueTemplateDefault
from .effect_websocket_payloads import (
    deployment_snapshot_payload,
    item_summary,
    library_snapshot_payload,
)
from .effect_websocket_schema import (
    EFFECT_CONTENT,
    EFFECT_NAME,
    IDENTIFIER,
    LAYER_LABELS,
    NAVIGATION,
    POSITIVE_REVISION,
    SCENE_ID,
    SPEED_INDEX,
    STRICT_BOOL,
    TIMESTAMP,
    UUID_TEXT,
    WS_APPLY,
    WS_APPLY_SNAPSHOT,
    WS_CUSTOM_CATALOGUE,
    WS_DEPLOYMENT_SUBSCRIBE,
    WS_DEVICE,
    WS_DEVICE_SUBSCRIBE,
    WS_DEVICES,
    WS_INFO,
    WS_LIBRARY_CREATE,
    WS_LIBRARY_DELETE,
    WS_LIBRARY_GET,
    WS_LIBRARY_LIST,
    WS_LIBRARY_NAME_STATUS,
    WS_LIBRARY_OVERWRITE,
    WS_LIBRARY_SUBSCRIBE,
    WS_LIBRARY_UPDATE,
    WS_PREVIEW_APPLY_SCENE,
    WS_PREVIEW_APPLY_SNAPSHOT,
    WS_PREVIEW_CANCEL,
    WS_PREVIEW_CLOSE,
    WS_PREVIEW_HEALTH_CHECK,
    WS_PREVIEW_HEALTH_SUBSCRIBE,
    WS_PREVIEW_SUBSCRIBE,
    WS_SCENE_APPLY,
    WS_SCENE_CATALOGUE_GET,
    WS_SCENE_CATALOGUE_LIST,
    WS_SCENE_DEFAULT_SET,
    WS_SCENE_RESET,
    WS_TEMPLATE_DEFAULT_GET,
    WS_TEMPLATE_DEFAULT_RESET,
    WS_TEMPLATE_DEFAULT_SET,
    WS_USER_STATE_GET,
    WS_USER_STATE_RECORD_COLOUR,
    WS_USER_STATE_UPDATE,
    strict_int,
)

BACKEND_DATA_KEY = "effect_backend"
PREVIEW_SESSION_NOT_FOUND_CODE = "preview_session_not_found"
PREVIEW_SESSION_UNAUTHORIZED_CODE = "preview_session_unauthorized"
PREVIEW_TARGET_UNAVAILABLE_CODE = "preview_target_unavailable"
_LOGGER = logging.getLogger(__name__)


@websocket_command({vol.Required("type"): WS_INFO})
@callback
def ws_editor_info(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    connection.send_result(msg["id"], EditorApiInfo().to_dict())


@websocket_command({vol.Required("type"): WS_DEVICES})
@async_response
async def ws_editor_devices(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entries = [entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.state is ConfigEntryState.LOADED]
    if len(entries) > MAX_EDITOR_DEVICES:
        connection.send_error(
            msg["id"],
            "limit_reached",
            f"device response must not exceed {MAX_EDITOR_DEVICES} entries",
        )
        return
    backend = _backend(hass)
    devices = [_device_payload(hass, backend, entry) for entry in entries]
    connection.send_result(msg["id"], {"devices": devices})


@websocket_command(
    {
        vol.Required("type"): WS_DEVICE,
        vol.Required("config_entry_id"): IDENTIFIER,
    }
)
@async_response
async def ws_editor_device(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    connection.send_result(
        msg["id"],
        {"device": _device_payload(hass, _backend(hass), entry)},
    )


def _device_payload(
    hass: HomeAssistant,
    backend: EffectBackend,
    entry: ConfigEntry[Any],
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    observed = backend.device_cache.get(entry.entry_id)
    if observed is None:
        observed = backend.engine.reconcile_current(
            coordinator,
            config_entry_id=entry.entry_id,
            observed_at=dt_util.utcnow().isoformat(),
            refreshed=False,
        )
    device = device_effect_capabilities(
        entry.entry_id,
        coordinator.model,
        entry.title,
        coordinator.profile.segment_count,
        light_entity_id=_light_entity_id(hass, entry.entry_id),
        effect_categories=tuple(coordinator.effect_categories),
    ).to_dict()
    device["active_state"] = observed.to_public_dict()
    workspace = backend.active_workspaces.get(entry.entry_id)
    device["active_workspace"] = (
        workspace.to_dict()
        if workspace is not None
        and workspace.model == coordinator.model
        and workspace.observable_signature == _observed_signature(observed)
        else None
    )
    device["preview_health"] = backend.preview.health(entry.entry_id).to_dict()
    return device


def _observed_signature(observed: Any) -> str | None:
    if observed.mode == "custom" and observed.diy_code is not None:
        return f"custom:{observed.diy_code}"
    if observed.mode == "scene" and observed.effect is not None:
        return f"scene:{observed.effect}"
    if observed.mode in {"music", "video"} and observed.native_mode is not None:
        return f"{observed.mode}:{observed.native_mode}"
    return None


def _light_entity_id(hass: HomeAssistant, config_entry_id: str) -> str | None:
    entries = [
        entry
        for entry in er.async_entries_for_config_entry(er.async_get(hass), config_entry_id)
        if entry.domain == "light" and entry.platform == DOMAIN and entry.disabled_by is None
    ]
    return entries[0].entity_id if len(entries) == 1 else None


@websocket_command(
    {
        vol.Required("type"): WS_DEVICE_SUBSCRIBE,
        vol.Required("config_entry_id"): IDENTIFIER,
    }
)
@callback
def ws_device_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    cancel_forward: CALLBACK_TYPE | None = None

    @callback
    def forward() -> None:
        nonlocal cancel_forward
        cancel_forward = None
        backend.engine.reconcile_current(
            entry.runtime_data,
            config_entry_id=entry.entry_id,
            observed_at=dt_util.utcnow().isoformat(),
            refreshed=False,
        )
        connection.send_event(
            msg["id"],
            {"device": _device_payload(hass, backend, entry)},
        )

    @callback
    def delayed_forward(_now: Any) -> None:
        forward()

    @callback
    def schedule_forward() -> None:
        nonlocal cancel_forward
        if cancel_forward is None:
            cancel_forward = async_call_later(
                hass,
                0.1,
                delayed_forward,
            )

    unsubscribe = entry.runtime_data.async_add_listener(schedule_forward)

    @callback
    def unsubscribe_all() -> None:
        nonlocal cancel_forward
        unsubscribe()
        if cancel_forward is not None:
            cancel_forward()
            cancel_forward = None

    connection.subscriptions[msg["id"]] = unsubscribe_all
    connection.send_result(msg["id"])
    forward()


@websocket_command({vol.Required("type"): WS_CUSTOM_CATALOGUE})
@callback
def ws_custom_catalogue(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    connection.send_result(msg["id"], {"catalogue": custom_effect_catalogue_payload()})


@websocket_command(
    {
        vol.Required("type"): WS_SCENE_CATALOGUE_LIST,
        vol.Required("config_entry_id"): IDENTIFIER,
    }
)
@callback
def ws_scene_catalogue_list(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    coordinator = entry.runtime_data
    try:
        catalogue = scene_catalogue_payload(coordinator.model)
    except ValueError as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    scenes = catalogue["scenes"]
    if not isinstance(scenes, list):
        connection.send_error(msg["id"], "invalid_format", "scene catalogue has no scene list")
        return
    if len(scenes) > MAX_SCENE_CATALOGUE_ENTRIES:
        connection.send_error(
            msg["id"],
            "limit_reached",
            f"scene catalogue must not exceed {MAX_SCENE_CATALOGUE_ENTRIES} entries",
        )
        return
    connection.send_result(msg["id"], {"catalogue": catalogue})


@websocket_command(
    {
        vol.Required("type"): WS_SCENE_CATALOGUE_GET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("scene_id"): SCENE_ID,
        vol.Required("effect_id"): SCENE_ID,
    }
)
@callback
def ws_scene_catalogue_get(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    try:
        backend = _backend(hass)
        detail = scene_detail_payload(
            entry.runtime_data.model,
            msg["scene_id"],
            msg["effect_id"],
            scene_default=backend.scene_defaults.get(
                entry.entry_id,
                msg["scene_id"],
                msg["effect_id"],
            ),
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    connection.send_result(msg["id"], detail)


@websocket_command(
    {
        vol.Required("type"): WS_SCENE_APPLY,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("scene_id"): SCENE_ID,
        vol.Required("effect_id"): SCENE_ID,
        vol.Optional("speed_index"): SPEED_INDEX,
    }
)
@require_admin
@async_response
async def ws_scene_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    try:
        backend = _backend(hass)
        await backend.preview.async_supersede_device(
            entry.entry_id,
            reason="committed_apply",
        )
        resolved, speed_index = await async_apply_scene(
            hass,
            entry,
            scene_id=msg["scene_id"],
            effect_id=msg["effect_id"],
            speed_index=msg.get("speed_index"),
            user_id=connection.user.id,
            scene_defaults=backend.scene_defaults,
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except (HomeAssistantError, RuntimeError) as exc:
        connection.send_error(msg["id"], "apply_failed", str(exc))
        return
    backend.engine.reconcile_current(
        entry.runtime_data,
        config_entry_id=entry.entry_id,
        observed_at=dt_util.utcnow().isoformat(),
        refreshed=True,
    )
    connection.send_result(
        msg["id"],
        {
            "scene": scene_detail_payload(
                entry.runtime_data.model,
                resolved.entry.scene_id,
                resolved.entry.effect_id,
                scene_default=backend.scene_defaults.get(
                    entry.entry_id,
                    resolved.entry.scene_id,
                    resolved.entry.effect_id,
                ),
            )["scene"],
            "speed_index": speed_index,
            "readback": "scene_identity_only",
        },
    )


@websocket_command(
    {
        vol.Required("type"): WS_SCENE_RESET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("scene_id"): SCENE_ID,
        vol.Required("effect_id"): SCENE_ID,
    }
)
@require_admin
@async_response
async def ws_scene_reset(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        resolved = await async_reset_scene_default(
            entry,
            scene_id=msg["scene_id"],
            effect_id=msg["effect_id"],
            scene_defaults=backend.scene_defaults,
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "reset_failed", str(exc))
        return
    connection.send_result(
        msg["id"],
        scene_detail_payload(
            entry.runtime_data.model,
            resolved.entry.scene_id,
            resolved.entry.effect_id,
        ),
    )


@websocket_command(
    {
        vol.Required("type"): WS_SCENE_DEFAULT_SET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("scene_id"): SCENE_ID,
        vol.Required("effect_id"): SCENE_ID,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Required("updated_at"): TIMESTAMP,
    }
)
@require_admin
@async_response
async def ws_scene_default_set(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        resolved = await async_set_scene_default(
            entry,
            scene_id=msg["scene_id"],
            effect_id=msg["effect_id"],
            content=msg["content"],
            updated_at=msg["updated_at"],
            scene_defaults=backend.scene_defaults,
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "save_failed", str(exc))
        return
    connection.send_result(
        msg["id"],
        scene_detail_payload(
            entry.runtime_data.model,
            resolved.entry.scene_id,
            resolved.entry.effect_id,
            scene_default=backend.scene_defaults.get(
                entry.entry_id,
                resolved.entry.scene_id,
                resolved.entry.effect_id,
            ),
        ),
    )


def _template_default_detail(
    backend: EffectBackend,
    config_entry_id: str,
    model: str,
    template_id: str,
) -> dict[str, Any]:
    template = resolve_catalogue_template(model, template_id)
    stored = backend.template_defaults.get(config_entry_id, template_id)
    if stored is not None and stored.model != model:
        stored = None
    return {
        "template_id": template_id,
        "content": effect_content_to_dict(stored.content if stored is not None else template.content),
        "catalogue_content": effect_content_to_dict(template.content),
        "has_default": stored is not None,
    }


@websocket_command(
    {
        vol.Required("type"): WS_TEMPLATE_DEFAULT_GET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("template_id"): IDENTIFIER,
    }
)
@callback
def ws_template_default_get(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    try:
        detail = _template_default_detail(
            _backend(hass),
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    connection.send_result(msg["id"], detail)


@websocket_command(
    {
        vol.Required("type"): WS_TEMPLATE_DEFAULT_SET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("template_id"): IDENTIFIER,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Required("updated_at"): TIMESTAMP,
    }
)
@require_admin
@async_response
async def ws_template_default_set(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        content = effect_content_from_dict(msg["content"])
        template = validate_catalogue_template_identity(
            entry.runtime_data.model,
            msg["template_id"],
            content,
        )
        if effect_content_hash(content) == effect_content_hash(template.content):
            await backend.template_defaults.async_delete(entry.entry_id, msg["template_id"])
        else:
            await backend.template_defaults.async_set(
                CatalogueTemplateDefault(
                    config_entry_id=entry.entry_id,
                    model=entry.runtime_data.model,
                    template_id=msg["template_id"],
                    updated_at=msg["updated_at"],
                    content=content,
                )
            )
    except (EffectValidationError, ValueError) as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "save_failed", str(exc))
        return
    connection.send_result(
        msg["id"],
        _template_default_detail(
            backend,
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
        ),
    )


@websocket_command(
    {
        vol.Required("type"): WS_TEMPLATE_DEFAULT_RESET,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("template_id"): IDENTIFIER,
    }
)
@require_admin
@async_response
async def ws_template_default_reset(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        resolve_catalogue_template(entry.runtime_data.model, msg["template_id"])
        await backend.template_defaults.async_delete(entry.entry_id, msg["template_id"])
    except ValueError as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "reset_failed", str(exc))
        return
    connection.send_result(
        msg["id"],
        _template_default_detail(
            backend,
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
        ),
    )


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_CLOSE,
        vol.Required("session_id"): UUID_TEXT,
    }
)
@require_admin
@async_response
async def ws_preview_close(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        await _backend(hass).preview.async_close_session(
            msg["session_id"],
            connection,
        )
    except PreviewOwnershipError as exc:
        connection.send_error(msg["id"], PREVIEW_SESSION_UNAUTHORIZED_CODE, str(exc))
        return
    except PreviewSessionNotFoundError as exc:
        connection.send_error(msg["id"], PREVIEW_SESSION_NOT_FOUND_CODE, str(exc))
        return
    connection.send_result(msg["id"], {"closed": True})


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_APPLY_SNAPSHOT,
        vol.Required("session_id"): UUID_TEXT,
        vol.Required("sequence"): POSITIVE_REVISION,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("updated_at"): TIMESTAMP,
        vol.Required("name"): EFFECT_NAME,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Optional("origin_kind"): vol.In([SourceKind.CATALOGUE_TEMPLATE.value]),
        vol.Optional("origin_id"): IDENTIFIER,
        vol.Optional("persist_default", default=False): STRICT_BOOL,
    }
)
@require_admin
@async_response
async def ws_preview_apply_snapshot(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    try:
        backend.preview.ensure_session(msg["session_id"], connection)
        if "origin_id" in msg and "origin_kind" not in msg:
            raise EffectValidationError("origin ID requires an origin kind")
        item = backend.application.new_authored_item(
            name=msg["name"],
            content=msg["content"],
            origin=(
                Origin(
                    SourceKind(msg["origin_kind"]),
                    msg.get("origin_id"),
                )
                if "origin_kind" in msg
                else None
            ),
        )
        acceptance = await backend.preview.async_queue_snapshot(
            session_id=msg["session_id"],
            owner=connection,
            config_entry_id=msg["config_entry_id"],
            sequence=msg["sequence"],
            updated_at=msg["updated_at"],
            item=item,
            persist_default=msg["persist_default"],
        )
    except Exception as exc:
        _send_preview_error(connection, msg["id"], exc)
        return
    connection.send_result(msg["id"], acceptance.to_dict())


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_APPLY_SCENE,
        vol.Required("session_id"): UUID_TEXT,
        vol.Required("sequence"): POSITIVE_REVISION,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("updated_at"): TIMESTAMP,
        vol.Required("scene_id"): SCENE_ID,
        vol.Required("effect_id"): SCENE_ID,
        vol.Optional("speed_index"): SPEED_INDEX,
        vol.Optional("persist_default", default=False): STRICT_BOOL,
    }
)
@require_admin
@async_response
async def ws_preview_apply_scene(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    try:
        backend.preview.ensure_session(msg["session_id"], connection)
        acceptance = await backend.preview.async_queue_scene(
            session_id=msg["session_id"],
            owner=connection,
            config_entry_id=msg["config_entry_id"],
            sequence=msg["sequence"],
            updated_at=msg["updated_at"],
            scene_id=msg["scene_id"],
            effect_id=msg["effect_id"],
            speed_index=msg.get("speed_index"),
            persist_default=msg["persist_default"],
        )
    except Exception as exc:
        _send_preview_error(connection, msg["id"], exc)
        return
    connection.send_result(msg["id"], acceptance.to_dict())


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_CANCEL,
        vol.Required("session_id"): UUID_TEXT,
        vol.Optional("config_entry_id"): IDENTIFIER,
    }
)
@require_admin
@async_response
async def ws_preview_cancel(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        await _backend(hass).preview.async_cancel(
            session_id=msg["session_id"],
            owner=connection,
            config_entry_id=msg.get("config_entry_id"),
        )
    except PreviewOwnershipError as exc:
        connection.send_error(msg["id"], PREVIEW_SESSION_UNAUTHORIZED_CODE, str(exc))
        return
    except PreviewSessionNotFoundError as exc:
        connection.send_error(msg["id"], PREVIEW_SESSION_NOT_FOUND_CODE, str(exc))
        return
    connection.send_result(msg["id"], {"cancelled": True})


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_SUBSCRIBE,
        vol.Required("session_id"): UUID_TEXT,
    }
)
@require_admin
@callback
def ws_preview_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)

    @callback
    def forward(status: PreviewStatus) -> None:
        connection.send_event(msg["id"], status.to_dict())

    try:
        connection.subscriptions[msg["id"]] = backend.preview.subscribe(
            session_id=msg["session_id"],
            owner=connection,
            subscription_id=msg["id"],
            listener=forward,
        )
    except Exception as exc:
        _send_preview_error(connection, msg["id"], exc)
        return
    connection.send_result(msg["id"])
    if latest := backend.preview.latest_status(msg["session_id"], connection):
        forward(latest)


@websocket_command({vol.Required("type"): WS_PREVIEW_HEALTH_SUBSCRIBE})
@require_admin
@callback
def ws_preview_health_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    preview = _backend(hass).preview
    subscription_token = object()

    @callback
    def forward(status: PreviewHealthStatus) -> None:
        connection.send_event(msg["id"], status.to_dict())

    connection.subscriptions[msg["id"]] = preview.subscribe_health(
        subscription_id=subscription_token,
        listener=forward,
    )
    connection.send_result(msg["id"])
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            forward(preview.health(entry.entry_id))


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_HEALTH_CHECK,
        vol.Required("config_entry_id"): IDENTIFIER,
    }
)
@require_admin
@async_response
async def ws_preview_health_check(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        status = await _backend(hass).preview.async_check_health(
            msg["config_entry_id"],
        )
    except Exception as exc:
        _send_preview_error(connection, msg["id"], exc)
        return
    connection.send_result(msg["id"], {"health": status.to_dict()})


@websocket_command({vol.Required("type"): WS_LIBRARY_LIST})
@callback
def ws_library_list(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    snapshot = backend.application.library_snapshot()
    connection.send_result(msg["id"], library_snapshot_payload(snapshot))


@websocket_command({vol.Required("type"): WS_LIBRARY_SUBSCRIBE})
@callback
def ws_library_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    application = _backend(hass).application

    @callback
    def forward(snapshot: LibrarySnapshot) -> None:
        connection.send_event(msg["id"], library_snapshot_payload(snapshot))

    connection.subscriptions[msg["id"]] = application.subscribe_library(forward)
    connection.send_result(msg["id"])
    forward(application.library_snapshot())


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_GET,
        vol.Required("item_id"): UUID_TEXT,
    }
)
@callback
def ws_library_get(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    try:
        item = backend.application.get_saved_effect(msg["item_id"])
    except (ValueError, EffectNotFoundError) as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    if isinstance(item.content, OpaqueContent) and not connection.user.is_admin:
        connection.send_error(
            msg["id"],
            "unauthorized",
            "opaque effect content is available only to administrators",
        )
        return
    connection.send_result(msg["id"], {"item": item.to_dict()})


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_CREATE,
        vol.Required("name"): EFFECT_NAME,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Optional("layer_labels"): LAYER_LABELS,
    }
)
@require_admin
@async_response
async def ws_library_create(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        mutation = await _backend(hass).application.async_create_library_item(
            name=msg["name"],
            content=msg["content"],
            layer_labels=msg.get("layer_labels"),
        )
    except ReservedEffectNameError as exc:
        connection.send_error(msg["id"], "reserved_name", str(exc))
        return
    except SavedEffectNameConflictError as exc:
        connection.send_error(msg["id"], "name_conflict", str(exc))
        return
    except EffectValidationError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except EffectLimitError as exc:
        connection.send_error(msg["id"], "limit_reached", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "storage_unavailable", str(exc))
        return
    connection.send_result(
        msg["id"],
        {
            "item": mutation.item.to_dict(),
            "library": library_snapshot_payload(mutation.snapshot),
        },
    )


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_UPDATE,
        vol.Required("item_id"): UUID_TEXT,
        vol.Required("name"): EFFECT_NAME,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Required("expected_version"): POSITIVE_REVISION,
        vol.Required("expected_updated_at"): TIMESTAMP,
        vol.Optional("layer_labels"): LAYER_LABELS,
    }
)
@require_admin
@async_response
async def ws_library_update(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        mutation = await _backend(hass).application.async_update_library_item(
            item_id=msg["item_id"],
            name=msg["name"],
            content=msg["content"],
            expected_version=msg["expected_version"],
            expected_updated_at=msg["expected_updated_at"],
            layer_labels=msg.get("layer_labels"),
        )
    except ReservedEffectNameError as exc:
        connection.send_error(msg["id"], "reserved_name", str(exc))
        return
    except SavedEffectNameConflictError as exc:
        connection.send_error(msg["id"], "name_conflict", str(exc))
        return
    except EffectValidationError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except (ValueError, EffectNotFoundError) as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    except EffectVersionConflictError as exc:
        connection.send_error(
            msg["id"],
            "conflict",
            f"{exc}; current_version={exc.current_version}",
        )
        return
    except EffectLimitError as exc:
        connection.send_error(msg["id"], "limit_reached", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "storage_unavailable", str(exc))
        return
    connection.send_result(
        msg["id"],
        {
            "item": mutation.item.to_dict(),
            "library": library_snapshot_payload(mutation.snapshot),
        },
    )


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_NAME_STATUS,
        vol.Required("name"): EFFECT_NAME,
        vol.Optional("excluding_item_id"): UUID_TEXT,
    }
)
@callback
def ws_library_name_status(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        status = _backend(hass).application.saved_effect_name_status(
            msg["name"],
            excluding_item_id=msg.get("excluding_item_id"),
        )
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    payload: dict[str, Any] = {"kind": status.kind}
    if status.item is not None:
        payload["item"] = item_summary(status.item)
    connection.send_result(msg["id"], {"status": payload})


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_OVERWRITE,
        vol.Required("target_item_id"): UUID_TEXT,
        vol.Required("name"): EFFECT_NAME,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Required("expected_version"): POSITIVE_REVISION,
        vol.Required("expected_updated_at"): TIMESTAMP,
        vol.Optional("layer_labels"): LAYER_LABELS,
    }
)
@require_admin
@async_response
async def ws_library_overwrite(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        mutation = await _backend(hass).application.async_overwrite_library_item(
            target_item_id=msg["target_item_id"],
            name=msg["name"],
            content=msg["content"],
            expected_version=msg["expected_version"],
            expected_updated_at=msg["expected_updated_at"],
            layer_labels=msg.get("layer_labels"),
        )
    except ReservedEffectNameError as exc:
        connection.send_error(msg["id"], "reserved_name", str(exc))
        return
    except SavedEffectNameConflictError as exc:
        connection.send_error(msg["id"], "name_conflict", str(exc))
        return
    except EffectValidationError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except (ValueError, EffectNotFoundError) as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    except EffectVersionConflictError as exc:
        connection.send_error(
            msg["id"],
            "conflict",
            f"{exc}; current_version={exc.current_version}",
        )
        return
    except EffectLimitError as exc:
        connection.send_error(msg["id"], "limit_reached", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "storage_unavailable", str(exc))
        return
    connection.send_result(
        msg["id"],
        {
            "item": mutation.item.to_dict(),
            "library": library_snapshot_payload(mutation.snapshot),
        },
    )


@websocket_command(
    {
        vol.Required("type"): WS_LIBRARY_DELETE,
        vol.Required("item_id"): UUID_TEXT,
        vol.Required("expected_version"): POSITIVE_REVISION,
        vol.Required("expected_updated_at"): TIMESTAMP,
    }
)
@require_admin
@async_response
async def ws_library_delete(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        snapshot = await _backend(hass).application.async_delete_library_item(
            item_id=msg["item_id"],
            expected_version=msg["expected_version"],
            expected_updated_at=msg["expected_updated_at"],
        )
    except (ValueError, EffectNotFoundError) as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    except EffectVersionConflictError as exc:
        connection.send_error(
            msg["id"],
            "conflict",
            f"{exc}; current_version={exc.current_version}",
        )
        return
    connection.send_result(msg["id"], {"library": library_snapshot_payload(snapshot)})


@websocket_command({vol.Required("type"): WS_DEPLOYMENT_SUBSCRIBE})
@require_admin
@callback
def ws_deployment_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    repository = _backend(hass).deployments

    @callback
    def forward(snapshot: DeploymentSnapshot) -> None:
        connection.send_event(msg["id"], deployment_snapshot_payload(snapshot))

    connection.subscriptions[msg["id"]] = repository.subscribe(forward)
    connection.send_result(msg["id"])
    forward(repository.snapshot())


@websocket_command({vol.Required("type"): WS_USER_STATE_GET})
@callback
def ws_user_state_get(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    state = _backend(hass).application.get_user_state(connection.user.id)
    connection.send_result(msg["id"], {"user_state": state.to_dict()})


@websocket_command(
    {
        vol.Required("type"): WS_USER_STATE_UPDATE,
        vol.Optional("selected_config_entry_id"): IDENTIFIER,
        vol.Required("navigation"): NAVIGATION,
    }
)
@callback
def ws_user_state_update(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        updated = _backend(hass).application.update_user_state(
            connection.user.id,
            selected_config_entry_id=msg.get("selected_config_entry_id"),
            navigation=msg["navigation"],
        )
    except EffectStorageError as exc:
        connection.send_error(
            msg["id"],
            "limit_reached" if isinstance(exc, EffectLimitError) else "invalid_format",
            str(exc),
        )
        return
    connection.send_result(msg["id"], {"user_state": updated.to_dict()})


@websocket_command(
    {
        vol.Required("type"): WS_USER_STATE_RECORD_COLOUR,
        vol.Required("colour"): [vol.All(strict_int, vol.Range(min=0, max=255))],
    }
)
@callback
def ws_user_state_record_colour(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        updated = _backend(hass).application.record_user_colour(
            connection.user.id,
            msg["colour"],
        )
    except EffectLimitError as exc:
        connection.send_error(msg["id"], "limit_reached", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    connection.send_result(msg["id"], {"user_state": updated.to_dict()})


@websocket_command(
    {
        vol.Required("type"): WS_APPLY,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("item_id"): UUID_TEXT,
        vol.Required("expected_version"): POSITIVE_REVISION,
        vol.Required("updated_at"): TIMESTAMP,
        vol.Optional("operation_id"): UUID_TEXT,
    }
)
@require_admin
@async_response
async def ws_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    try:
        UUID(msg["item_id"])
        operation_id = UUID(msg["operation_id"]) if "operation_id" in msg else None
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    try:
        await backend.preview.async_supersede_device(
            entry.entry_id,
            reason="committed_apply",
        )
        result = await backend.application.async_apply_saved_effect(
            backend.engine,
            entry.runtime_data,
            item_id=msg["item_id"],
            config_entry_id=entry.entry_id,
            updated_at=msg["updated_at"],
            operation_id=operation_id,
            expected_version=msg["expected_version"],
        )
    except EffectNotFoundError as exc:
        connection.send_error(msg["id"], "not_found", str(exc))
        return
    except EffectVersionConflictError as exc:
        connection.send_error(msg["id"], "conflict", str(exc))
        return
    except ValueError as exc:
        connection.send_error(msg["id"], "unsupported_model", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "storage_unavailable", str(exc))
        return
    except Exception as exc:
        connection.send_error(msg["id"], "apply_failed", str(exc))
        return
    connection.send_result(msg["id"], {"deployment": result.to_public_dict()})


@websocket_command(
    {
        vol.Required("type"): WS_APPLY_SNAPSHOT,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("name"): EFFECT_NAME,
        vol.Required("content"): EFFECT_CONTENT,
        vol.Required("updated_at"): TIMESTAMP,
        vol.Optional("origin_kind"): vol.In([SourceKind.CATALOGUE_TEMPLATE.value]),
        vol.Optional("origin_id"): IDENTIFIER,
        vol.Optional("operation_id"): UUID_TEXT,
    }
)
@require_admin
@async_response
async def ws_apply_snapshot(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "target config entry is not loaded")
        return
    try:
        if "origin_id" in msg and "origin_kind" not in msg:
            raise EffectValidationError("origin ID requires an origin kind")
        await backend.preview.async_supersede_device(
            entry.entry_id,
            reason="committed_apply",
        )
        item = backend.application.new_authored_item(
            name=msg["name"],
            content=msg["content"],
            origin=(
                Origin(
                    SourceKind(msg["origin_kind"]),
                    msg.get("origin_id"),
                )
                if "origin_kind" in msg
                else None
            ),
        )
        result = await backend.engine.async_apply_snapshot(
            entry.runtime_data,
            item,
            config_entry_id=entry.entry_id,
            updated_at=msg["updated_at"],
            operation_id=(UUID(msg["operation_id"]) if "operation_id" in msg else None),
        )
    except EffectValidationError as exc:
        connection.send_error(msg["id"], "invalid_format", str(exc))
        return
    except ValueError as exc:
        connection.send_error(msg["id"], "unsupported_model", str(exc))
        return
    except EffectStorageError as exc:
        connection.send_error(msg["id"], "storage_unavailable", str(exc))
        return
    except Exception as exc:
        connection.send_error(msg["id"], "apply_failed", str(exc))
        return
    connection.send_result(msg["id"], {"deployment": result.to_public_dict()})


def async_register_effect_websocket(
    hass: HomeAssistant,
    backend: EffectBackend,
) -> None:
    hass.data.setdefault(DOMAIN, {})[BACKEND_DATA_KEY] = backend
    websocket_api.async_register_command(hass, ws_editor_info)
    websocket_api.async_register_command(hass, ws_editor_devices)
    websocket_api.async_register_command(hass, ws_editor_device)
    websocket_api.async_register_command(hass, ws_device_subscribe)
    websocket_api.async_register_command(hass, ws_custom_catalogue)
    websocket_api.async_register_command(hass, ws_scene_catalogue_list)
    websocket_api.async_register_command(hass, ws_scene_catalogue_get)
    websocket_api.async_register_command(hass, ws_scene_apply)
    websocket_api.async_register_command(hass, ws_scene_default_set)
    websocket_api.async_register_command(hass, ws_scene_reset)
    websocket_api.async_register_command(hass, ws_template_default_get)
    websocket_api.async_register_command(hass, ws_template_default_set)
    websocket_api.async_register_command(hass, ws_template_default_reset)
    websocket_api.async_register_command(hass, ws_preview_close)
    websocket_api.async_register_command(hass, ws_preview_apply_snapshot)
    websocket_api.async_register_command(hass, ws_preview_apply_scene)
    websocket_api.async_register_command(hass, ws_preview_cancel)
    websocket_api.async_register_command(hass, ws_preview_subscribe)
    websocket_api.async_register_command(hass, ws_preview_health_subscribe)
    websocket_api.async_register_command(hass, ws_preview_health_check)
    websocket_api.async_register_command(hass, ws_library_list)
    websocket_api.async_register_command(hass, ws_library_get)
    websocket_api.async_register_command(hass, ws_library_create)
    websocket_api.async_register_command(hass, ws_library_update)
    websocket_api.async_register_command(hass, ws_library_overwrite)
    websocket_api.async_register_command(hass, ws_library_delete)
    websocket_api.async_register_command(hass, ws_library_name_status)
    websocket_api.async_register_command(hass, ws_library_subscribe)
    websocket_api.async_register_command(hass, ws_deployment_subscribe)
    websocket_api.async_register_command(hass, ws_user_state_get)
    websocket_api.async_register_command(hass, ws_user_state_update)
    websocket_api.async_register_command(hass, ws_user_state_record_colour)
    websocket_api.async_register_command(hass, ws_apply)
    websocket_api.async_register_command(hass, ws_apply_snapshot)


def _backend(hass: HomeAssistant) -> EffectBackend:
    return cast(EffectBackend, hass.data[DOMAIN][BACKEND_DATA_KEY])


def _send_preview_error(
    connection: ActiveConnection,
    message_id: int,
    error: Exception,
) -> None:
    if isinstance(error, PreviewOwnershipError):
        code = PREVIEW_SESSION_UNAUTHORIZED_CODE
        message = "The preview session belongs to another connection."
    elif isinstance(error, PreviewSessionNotFoundError):
        code = PREVIEW_SESSION_NOT_FOUND_CODE
        message = "The preview session was not found."
    elif isinstance(error, PreviewTargetUnavailableError):
        code = PREVIEW_TARGET_UNAVAILABLE_CODE
        message = "The target light is not loaded."
    elif isinstance(error, PreviewSequenceError):
        code = "invalid_sequence"
        message = "The preview sequence is invalid."
    elif isinstance(error, PreviewShutdownError):
        code = "shutdown"
        message = "Home Assistant is stopping."
    elif isinstance(error, EffectValidationError):
        code = "invalid_format"
        message = "The preview effect is invalid."
    elif isinstance(error, PreviewError):
        code = "invalid_format"
        message = str(error)
    else:
        code = "preview_failed"
        message = "The preview request failed."
        _LOGGER.exception("Unexpected Effect Studio preview request failure", exc_info=error)
    connection.send_error(message_id, code, message)
