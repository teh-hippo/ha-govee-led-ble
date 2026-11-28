"""Authenticated WebSocket API for the optional advanced-effect backend."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass
from functools import partial
from typing import Any, cast
from uuid import UUID

from bleak.exc import BleakError
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SHOW_EXPERIMENTAL_FEEDBACK,
    DOMAIN,
    MODEL_PROFILES,
    ModelProfile,
    light_unique_id,
    supported_effect_categories,
)
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import async_prepare_effect_profile
from .coordinator_modes import ModeTransitionSupersededError
from .coordinator_upload import UploadRejectedError
from .effect_backend import EffectBackend
from .effect_catalogue import (
    custom_effect_catalogue_payload,
    resolve_catalogue_template,
    validate_catalogue_template_identity,
)
from .effect_contracts import CapabilityWorkflow, EditorApiInfo, device_effect_capabilities
from .effect_deployments import DeploymentSnapshot
from .effect_diy_destination import (
    async_prepare_diy_destination_consent,
    diy_destination_authority,
    requested_diy_destination,
)
from .effect_domain import (
    BuiltinScene,
    EffectValidationError,
    MusicProfile,
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
from .effect_runtime import active_workspace_matches, async_prepare_application
from .effect_scenes import (
    async_apply_scene,
    async_reset_scene_default,
    async_set_scene_default,
    resolve_scene,
    resolve_scene_application_body,
    scene_catalogue_payload,
    scene_default_for,
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
    device_catalogue_settings,
    item_summary,
    library_snapshot_payload,
    retained_music_edit,
)
from .effect_websocket_schema import (
    DIY_CODE,
    DIY_DESTINATION_CONSENT,
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
    WS_USER_STATE_UPDATE,
)
from .govee_encryption import GoveeCryptoError
from .layered_scene import CatalogueRef
from .music_commands import music_body_style
from .music_protocol import MUSIC_MODE_CODES_BY_MODEL, music_code_for
from .schema_compat import vol
from .video_applicability import video_profile_control_states

BACKEND_DATA_KEY = "effect_backend"
PREVIEW_SESSION_NOT_FOUND_CODE = "preview_session_not_found"
PREVIEW_SESSION_UNAUTHORIZED_CODE = "preview_session_unauthorized"
PREVIEW_TARGET_UNAVAILABLE_CODE = "preview_target_unavailable"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _StudioDeviceAccess:
    light_entity_id: str | None
    can_read: bool
    can_control: bool


@websocket_command({vol.Required("type"): WS_INFO})
@async_response
async def ws_editor_info(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    integration = await async_get_integration(hass, DOMAIN)
    connection.send_result(msg["id"], EditorApiInfo(integration_version=integration.version).to_dict())


@websocket_command({vol.Required("type"): WS_DEVICES})
@async_response
async def ws_editor_devices(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    visible: list[tuple[ConfigEntry[Any], _StudioDeviceAccess]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED or not supported_effect_categories(
            entry.runtime_data.model, profile=entry.runtime_data.profile
        ):
            continue
        access = _studio_device_access(hass, connection, entry)
        if access.can_read:
            visible.append((entry, access))
    if len(visible) > MAX_EDITOR_DEVICES:
        _send_error(
            hass,
            connection,
            msg,
            "limit_reached",
            f"device response must not exceed {MAX_EDITOR_DEVICES} entries",
        )
        return
    backend = _backend(hass)
    devices = [_device_payload(hass, backend, entry, access) for entry, access in visible]
    connection.send_result(msg["id"], {"devices": devices})


@websocket_command(
    {
        vol.Required("type"): WS_DEVICE,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Optional("content"): EFFECT_CONTENT,
    }
)
@async_response
async def ws_editor_device(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    entry, access = authorized
    if "content" in msg:
        from .effect_application import EffectStudioApplication, effect_compatibility_payload

        try:
            item = EffectStudioApplication.new_authored_item(name="Draft", content=msg["content"])
            result = effect_compatibility_payload(
                item, entry.runtime_data.model, entry.runtime_data.effect_authorization_profile
            )
        except ValueError as error:
            _send_error(hass, connection, msg, "invalid_format", error)
            return
        connection.send_result(msg["id"], {"compatibility": result})
        return
    connection.send_result(
        msg["id"],
        {"device": _device_payload(hass, _backend(hass), entry, access)},
    )


def _device_payload(
    hass: HomeAssistant,
    backend: EffectBackend,
    entry: ConfigEntry[Any],
    access: _StudioDeviceAccess | None = None,
) -> dict[str, Any]:
    access = access or _StudioDeviceAccess(
        light_entity_id=_primary_light_entity_id(hass, entry.entry_id),
        can_read=True,
        can_control=True,
    )
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
        physical_ic_count=coordinator.profile.physical_ic_count,
        physical_ic_capacity=coordinator.profile.physical_ic_capacity,
        profile=coordinator.profile,
    ).to_dict()
    device["show_experimental_feedback"] = entry.options.get(CONF_SHOW_EXPERIMENTAL_FEEDBACK, True)
    device["effect_compatibilities"] = backend.application.target_compatibilities(
        coordinator.model, coordinator.effect_authorization_profile
    )
    device["compatibility_revision"] = (
        f"{getattr(coordinator, '_profile_generation', 0)}:{getattr(coordinator, '_authorization_generation', 0)}"
    )
    device["diy_destination_authority"] = diy_destination_authority(coordinator)
    device["hw_version"] = coordinator.hw_version
    device["fw_version"] = coordinator.fw_version
    device["subordinate_20_version"] = coordinator.subordinate_20_version
    device["subordinate_21_version"] = coordinator.subordinate_21_version
    device["can_read"] = access.can_read
    device["can_control"] = access.can_control
    device["active_state"] = observed.to_public_dict()
    device.update(device_catalogue_settings(coordinator.model, profile=coordinator.profile))
    device["retained_music_edit"] = retained_music_edit(coordinator)
    device["video_control_states"] = {
        key: value.value for key, value in video_profile_control_states(coordinator.profile, coordinator).items()
    }
    workspace = backend.active_workspaces.get(entry.entry_id)
    device["active_workspace"] = (
        workspace.to_dict() if workspace is not None and active_workspace_matches(coordinator, workspace) else None
    )
    device["preview_health"] = backend.preview.health(entry.entry_id).to_dict()
    return device


def _primary_light_registry_entry(
    hass: HomeAssistant,
    config_entry_id: str,
) -> er.RegistryEntry | None:
    entry = hass.config_entries.async_get_entry(config_entry_id)
    unique_id = getattr(entry, "unique_id", None)
    if entry is None or entry.domain != DOMAIN or not unique_id:
        return None
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("light", DOMAIN, light_unique_id(unique_id))
    registered = registry.async_get(entity_id) if entity_id is not None else None
    if registered is None or registered.config_entry_id != config_entry_id:
        return None
    return registered


def _primary_light_entity_id(hass: HomeAssistant, config_entry_id: str) -> str | None:
    registered = _primary_light_registry_entry(hass, config_entry_id)
    return registered.entity_id if registered is not None else None


def _light_entity_id(hass: HomeAssistant, config_entry_id: str) -> str | None:
    registered = _primary_light_registry_entry(hass, config_entry_id)
    return registered.entity_id if registered is not None and registered.disabled_by is None else None


def _studio_device_access(
    hass: HomeAssistant,
    connection: ActiveConnection,
    entry: ConfigEntry[Any],
) -> _StudioDeviceAccess:
    entity_id = _primary_light_entity_id(hass, entry.entry_id)
    if connection.user.is_admin:
        return _StudioDeviceAccess(entity_id, can_read=True, can_control=True)
    if entity_id is None:
        return _StudioDeviceAccess(None, can_read=False, can_control=False)
    can_control = connection.user.permissions.check_entity(entity_id, POLICY_CONTROL)
    can_read = connection.user.permissions.check_entity(entity_id, POLICY_READ) or can_control
    return _StudioDeviceAccess(entity_id, can_read=can_read, can_control=can_control)


def _loaded_entry_with_access(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
    permission: str,
) -> tuple[ConfigEntry[Any], _StudioDeviceAccess] | None:
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        _send_error(hass, connection, msg, "not_found", "target config entry is not loaded")
        return None
    access = _studio_device_access(hass, connection, entry)
    allowed = access.can_control if permission == POLICY_CONTROL else access.can_read
    if not allowed:
        _send_error(hass, connection, msg, "unauthorized", "target config entry is not permitted")
        return None
    return entry, access


def _ensure_entry_control(
    hass: HomeAssistant,
    connection: ActiveConnection,
    entry: ConfigEntry[Any],
) -> None:
    access = _studio_device_access(hass, connection, entry)
    if not access.can_control:
        raise Unauthorized(entity_id=access.light_entity_id, permission=POLICY_CONTROL)


def _ensure_default_admin(connection: ActiveConnection) -> None:
    if not connection.user.is_admin:
        raise Unauthorized()


async def _before_scene_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    entry: ConfigEntry[Any],
    backend: EffectBackend,
) -> None:
    _ensure_entry_control(hass, connection, entry)
    await backend.preview.async_supersede_device(entry.entry_id, reason="committed_apply")


async def _before_music_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    entry: ConfigEntry[Any],
    backend: EffectBackend,
) -> None:
    _ensure_entry_control(hass, connection, entry)
    await backend.preview.async_supersede_device(entry.entry_id, reason="home_assistant_control")


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
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    entry, access = authorized
    backend = _backend(hass)
    cancel_forward: CALLBACK_TYPE | None = None

    @callback
    def forward() -> None:
        nonlocal cancel_forward, access
        cancel_forward = None
        access = _studio_device_access(hass, connection, entry)
        if not access.can_read:
            unsubscribe_all()
            connection.subscriptions.pop(msg["id"], None)
            connection.send_error(msg["id"], "unauthorized", "target config entry is no longer permitted")
            return
        backend.engine.reconcile_current(
            entry.runtime_data,
            config_entry_id=entry.entry_id,
            observed_at=dt_util.utcnow().isoformat(),
            refreshed=False,
        )
        connection.send_event(
            msg["id"],
            {"device": _device_payload(hass, backend, entry, access)},
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
    unsubscribe_library = backend.application.subscribe_library(lambda _snapshot: schedule_forward())

    @callback
    def unsubscribe_all() -> None:
        nonlocal cancel_forward
        unsubscribe()
        unsubscribe_library()
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
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    entry, _ = authorized
    coordinator = entry.runtime_data
    if not coordinator.profile.supports_scenes:
        _send_error(hass, connection, msg, "unsupported_model", "Device profile supports no scenes")
        return
    try:
        catalogue = scene_catalogue_payload(coordinator.model, profile=coordinator.profile)
    except ValueError as exc:
        _send_error(hass, connection, msg, "not_found", exc)
        return
    scenes = catalogue["scenes"]
    if not isinstance(scenes, list):
        _send_error(hass, connection, msg, "invalid_format", "scene catalogue has no scene list")
        return
    if len(scenes) > MAX_SCENE_CATALOGUE_ENTRIES:
        _send_error(
            hass,
            connection,
            msg,
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
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    entry, _ = authorized
    if not entry.runtime_data.profile.supports_scenes:
        _send_error(hass, connection, msg, "unsupported_model", "Device profile supports no scenes")
        return
    try:
        backend = _backend(hass)
        resolved = resolve_scene(entry.runtime_data.model, msg["scene_id"], msg["effect_id"])
        detail = scene_detail_payload(
            entry.runtime_data.model,
            msg["scene_id"],
            msg["effect_id"],
            profile=entry.runtime_data.profile,
            scene_default=scene_default_for(
                backend.scene_defaults,
                entry.entry_id,
                entry.runtime_data.model,
                resolved.key,
                resolved.entry,
            ),
        )
    except ValueError as exc:
        _send_error(hass, connection, msg, "not_found", exc)
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
@async_response
async def ws_scene_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    try:
        backend = _backend(hass)
        resolved = resolve_scene(entry.runtime_data.model, msg["scene_id"], msg["effect_id"])
        if "speed_index" in msg:
            resolve_scene_application_body(resolved.entry, scene_default=None, speed_index=msg["speed_index"])
        profile = await async_prepare_effect_profile(
            entry.runtime_data,
            intent=ControlIntent.BACKGROUND,
            content=BuiltinScene(
                CatalogueRef(entry.runtime_data.model, resolved.entry.scene_id, resolved.entry.effect_id)
            ),
        )
        if not profile.supports_scenes:
            _send_error(hass, connection, msg, "unsupported_model", "Device profile supports no scenes")
            return
        resolved, speed_index = await async_apply_scene(
            hass,
            entry,
            scene_id=msg["scene_id"],
            effect_id=msg["effect_id"],
            speed_index=msg.get("speed_index"),
            user_id=connection.user.id,
            scene_defaults=backend.scene_defaults,
            before_apply=partial(
                _before_scene_apply,
                hass,
                connection,
                entry,
                backend,
            ),
            on_write=partial(backend.engine.clear_active_origin, entry.entry_id),
            profile=profile,
        )
    except (GoveeCryptoError, ModeTransitionSupersededError) as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
        return
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except ValueError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except (HomeAssistantError, RuntimeError) as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
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
                profile=entry.runtime_data.profile,
                scene_default=scene_default_for(
                    backend.scene_defaults,
                    entry.entry_id,
                    entry.runtime_data.model,
                    resolved.key,
                    resolved.entry,
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
        _send_error(hass, connection, msg, "not_found", "target config entry is not loaded")
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
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "reset_failed", exc)
        return
    connection.send_result(
        msg["id"],
        scene_detail_payload(
            entry.runtime_data.model,
            resolved.entry.scene_id,
            resolved.entry.effect_id,
            profile=entry.runtime_data.profile,
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
        _send_error(hass, connection, msg, "not_found", "target config entry is not loaded")
        return
    if not entry.runtime_data.profile.supports_scenes:
        _send_error(hass, connection, msg, "unsupported_model", "Device profile supports no scenes")
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
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "save_failed", exc)
        return
    connection.send_result(
        msg["id"],
        scene_detail_payload(
            entry.runtime_data.model,
            resolved.entry.scene_id,
            resolved.entry.effect_id,
            profile=entry.runtime_data.profile,
            scene_default=scene_default_for(
                backend.scene_defaults,
                entry.entry_id,
                entry.runtime_data.model,
                resolved.key,
                resolved.entry,
            ),
        ),
    )


def _template_default_detail(
    backend: EffectBackend,
    config_entry_id: str,
    model: str,
    template_id: str,
    *,
    profile: ModelProfile | None = None,
) -> dict[str, Any]:
    template = resolve_catalogue_template(model, template_id, profile=profile)
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
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    entry, _ = authorized
    try:
        detail = _template_default_detail(
            _backend(hass),
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
            profile=entry.runtime_data.profile,
        )
    except ValueError as exc:
        _send_error(hass, connection, msg, "not_found", exc)
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
        _send_error(hass, connection, msg, "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        content = effect_content_from_dict(msg["content"])
        template = validate_catalogue_template_identity(
            entry.runtime_data.model,
            msg["template_id"],
            content,
            profile=entry.runtime_data.profile,
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
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "save_failed", exc)
        return
    connection.send_result(
        msg["id"],
        _template_default_detail(
            backend,
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
            profile=entry.runtime_data.profile,
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
        _send_error(hass, connection, msg, "not_found", "target config entry is not loaded")
        return
    backend = _backend(hass)
    try:
        resolve_catalogue_template(entry.runtime_data.model, msg["template_id"], profile=entry.runtime_data.profile)
        await backend.template_defaults.async_delete(entry.entry_id, msg["template_id"])
    except ValueError as exc:
        _send_error(hass, connection, msg, "not_found", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "reset_failed", exc)
        return
    connection.send_result(
        msg["id"],
        _template_default_detail(
            backend,
            entry.entry_id,
            entry.runtime_data.model,
            msg["template_id"],
            profile=entry.runtime_data.profile,
        ),
    )


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_CLOSE,
        vol.Required("session_id"): UUID_TEXT,
    }
)
@async_response
async def ws_preview_close(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        outcomes = await _backend(hass).preview.async_close_session(
            msg["session_id"],
            connection,
        )
    except PreviewOwnershipError as exc:
        _send_error(hass, connection, msg, PREVIEW_SESSION_UNAUTHORIZED_CODE, exc)
        return
    except PreviewSessionNotFoundError as exc:
        _send_error(hass, connection, msg, PREVIEW_SESSION_NOT_FOUND_CODE, exc)
        return
    connection.send_result(msg["id"], {"closed": True, "devices": [outcome.to_dict() for outcome in outcomes]})


@websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/music/edit_retained",
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("mode"): IDENTIFIER,
        vol.Required("expected_body_revision"): vol.All(int, vol.Range(min=0)),
        vol.Required("parameters"): dict,
        vol.Optional("calm"): STRICT_BOOL,
    }
)
@async_response
async def ws_music_edit_retained(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    coordinator = entry.runtime_data
    backend = _backend(hass)
    workspace_attribution = None
    workspace_matched_before_attempt = False
    upload_started = False

    def invalidate_workspace() -> None:
        nonlocal upload_started, workspace_attribution, workspace_matched_before_attempt
        if upload_started:
            return
        upload_started = True
        workspace = backend.active_workspaces.get(entry.entry_id)
        content = None if workspace is None else workspace.content
        if (
            workspace is not None
            and isinstance(content, MusicProfile)
            and workspace.model == coordinator.model
            and content.mode == coordinator.music_mode
            and workspace.observable_signature == f"music:{coordinator.music_mode}"
        ):
            workspace_attribution = workspace
            workspace_matched_before_attempt = active_workspace_matches(coordinator, workspace)
            backend.active_workspaces.clear(entry.entry_id)

    try:
        if (
            type(msg["expected_body_revision"]) is not int
            or coordinator._music_body_revision != msg["expected_body_revision"]
            or coordinator.music_mode != msg["mode"]
            or msg["mode"] not in coordinator.profile.music_modes
        ):
            raise ValueError("Retained music body changed; refresh and retry")
        # The existing apply path compiles the complete body before acquiring control,
        # then guards its captured revision at each physical write.
        await coordinator.async_apply_music_params(
            music_code_for(coordinator.model, msg["mode"], profile=coordinator.profile),
            parameters=msg["parameters"],
            calm=msg.get("calm")
            if "calm" in msg or coordinator.music_body is None
            else music_body_style(coordinator.music_body, msg["mode"], profile=coordinator.profile),
            before_apply=partial(
                _before_music_apply,
                hass,
                connection,
                entry,
                backend,
            ),
            on_upload_attempt=invalidate_workspace,
        )
    except UploadRejectedError as exc:
        content = None if workspace_attribution is None else workspace_attribution.content
        if (
            workspace_matched_before_attempt
            and workspace_attribution is not None
            and isinstance(content, MusicProfile)
            and coordinator.music_mode == content.mode
            and coordinator.music_sensitivity == content.sensitivity
            and active_workspace_matches(coordinator, workspace_attribution)
            and backend.active_workspaces.get(entry.entry_id) is None
        ):
            backend.active_workspaces.set(workspace_attribution)
        _send_error(hass, connection, msg, "apply_failed", exc)
        return
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except (ValueError, HomeAssistantError, BleakError, TimeoutError) as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
        return
    connection.send_result(msg["id"], {"retained_music_edit": retained_music_edit(coordinator)})


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
        vol.Optional("diy_code"): DIY_CODE,
        vol.Optional("diy_destination_consent"): DIY_DESTINATION_CONSENT,
    }
)
@async_response
async def ws_preview_apply_snapshot(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    if msg["persist_default"] and not connection.user.is_admin:
        _send_error(hass, connection, msg, "unauthorized", "Only administrators may persist Studio defaults")
        return
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
        kwargs: dict[str, Any] = {
            "session_id": msg["session_id"],
            "owner": connection,
            "config_entry_id": msg["config_entry_id"],
            "sequence": msg["sequence"],
            "updated_at": msg["updated_at"],
            "item": item,
            "persist_default": msg["persist_default"],
            "control_guard": partial(_ensure_entry_control, hass, connection, entry),
            "default_guard": partial(_ensure_default_admin, connection),
        }
        if "diy_destination_consent" in msg:
            kwargs["diy_code"] = msg.get("diy_code")
            kwargs["destination_consent_raw"] = msg["diy_destination_consent"]
        elif "diy_code" in msg:
            kwargs["diy_code"] = msg["diy_code"]
        acceptance = await backend.preview.async_queue_snapshot(**kwargs)
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except Exception as exc:
        _send_preview_error(hass, connection, msg, exc)
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
@async_response
async def ws_preview_apply_scene(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    if msg["persist_default"] and not connection.user.is_admin:
        _send_error(hass, connection, msg, "unauthorized", "Only administrators may persist Studio defaults")
        return
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
            control_guard=partial(_ensure_entry_control, hass, connection, entry),
            default_guard=partial(_ensure_default_admin, connection),
        )
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except Exception as exc:
        _send_preview_error(hass, connection, msg, exc)
        return
    connection.send_result(msg["id"], acceptance.to_dict())


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_CANCEL,
        vol.Required("session_id"): UUID_TEXT,
        vol.Optional("config_entry_id"): IDENTIFIER,
    }
)
@async_response
async def ws_preview_cancel(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        outcomes = await _backend(hass).preview.async_cancel(
            session_id=msg["session_id"],
            owner=connection,
            config_entry_id=msg.get("config_entry_id"),
        )
    except PreviewOwnershipError as exc:
        _send_error(hass, connection, msg, PREVIEW_SESSION_UNAUTHORIZED_CODE, exc)
        return
    except PreviewSessionNotFoundError as exc:
        _send_error(hass, connection, msg, PREVIEW_SESSION_NOT_FOUND_CODE, exc)
        return
    connection.send_result(
        msg["id"],
        {"cancelled": True, "devices": [outcome.to_dict() for outcome in outcomes]},
    )


@websocket_command(
    {
        vol.Required("type"): WS_PREVIEW_SUBSCRIBE,
        vol.Required("session_id"): UUID_TEXT,
    }
)
@callback
def ws_preview_subscribe(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    unsubscribe: CALLBACK_TYPE | None = None

    @callback
    def forward(status: PreviewStatus) -> None:
        entry = hass.config_entries.async_get_entry(status.config_entry_id)
        if entry is None or not _studio_device_access(hass, connection, entry).can_read:
            if unsubscribe is not None:
                unsubscribe()
            connection.subscriptions.pop(msg["id"], None)
            connection.send_error(msg["id"], "unauthorized", "preview target is no longer permitted")
            return
        connection.send_event(msg["id"], status.to_dict())

    try:
        unsubscribe = backend.preview.subscribe(
            session_id=msg["session_id"],
            owner=connection,
            subscription_id=msg["id"],
            listener=forward,
        )
        connection.subscriptions[msg["id"]] = unsubscribe
    except Exception as exc:
        _send_preview_error(hass, connection, msg, exc)
        return
    connection.send_result(msg["id"])
    if latest := backend.preview.latest_status(msg["session_id"], connection):
        forward(latest)


@websocket_command({vol.Required("type"): WS_PREVIEW_HEALTH_SUBSCRIBE})
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
        entry = hass.config_entries.async_get_entry(status.config_entry_id)
        if entry is not None and _studio_device_access(hass, connection, entry).can_read:
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
@async_response
async def ws_preview_health_check(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_READ)
    if authorized is None:
        return
    try:
        status = await _backend(hass).preview.async_check_health(
            msg["config_entry_id"],
        )
    except Exception as exc:
        _send_preview_error(hass, connection, msg, exc)
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
        _send_error(hass, connection, msg, "not_found", exc)
        return
    if isinstance(item.content, OpaqueContent) and not connection.user.is_admin:
        _send_error(
            hass,
            connection,
            msg,
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
        _send_error(hass, connection, msg, "reserved_name", exc)
        return
    except SavedEffectNameConflictError as exc:
        _send_error(hass, connection, msg, "name_conflict", exc)
        return
    except EffectValidationError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except EffectLimitError as exc:
        _send_error(hass, connection, msg, "limit_reached", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "storage_unavailable", exc)
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
        _send_error(hass, connection, msg, "reserved_name", exc)
        return
    except SavedEffectNameConflictError as exc:
        _send_error(hass, connection, msg, "name_conflict", exc)
        return
    except EffectValidationError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except (ValueError, EffectNotFoundError) as exc:
        _send_error(hass, connection, msg, "not_found", exc)
        return
    except EffectVersionConflictError as exc:
        _send_error(
            hass,
            connection,
            msg,
            "conflict",
            f"{exc}; current_version={exc.current_version}",
        )
        return
    except EffectLimitError as exc:
        _send_error(hass, connection, msg, "limit_reached", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "storage_unavailable", exc)
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
        _send_error(hass, connection, msg, "invalid_format", exc)
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
        _send_error(hass, connection, msg, "reserved_name", exc)
        return
    except SavedEffectNameConflictError as exc:
        _send_error(hass, connection, msg, "name_conflict", exc)
        return
    except EffectValidationError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except (ValueError, EffectNotFoundError) as exc:
        _send_error(hass, connection, msg, "not_found", exc)
        return
    except EffectVersionConflictError as exc:
        _send_error(
            hass,
            connection,
            msg,
            "conflict",
            f"{exc}; current_version={exc.current_version}",
        )
        return
    except EffectLimitError as exc:
        _send_error(hass, connection, msg, "limit_reached", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "storage_unavailable", exc)
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
        _send_error(hass, connection, msg, "not_found", exc)
        return
    except EffectVersionConflictError as exc:
        _send_error(
            hass,
            connection,
            msg,
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
    selected_entry_id = msg.get("selected_config_entry_id")
    try:
        updated = _backend(hass).application.update_user_state(
            connection.user.id,
            selected_config_entry_id=selected_entry_id,
            navigation=msg["navigation"],
        )
    except EffectStorageError as exc:
        _send_error(
            hass,
            connection,
            msg,
            "limit_reached" if isinstance(exc, EffectLimitError) else "invalid_format",
            str(exc),
        )
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
        vol.Optional("diy_code"): DIY_CODE,
        vol.Optional("diy_destination_consent"): DIY_DESTINATION_CONSENT,
        vol.Optional("live"): bool,
    }
)
@async_response
async def ws_apply(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    try:
        UUID(msg["item_id"])
        operation_id = UUID(msg["operation_id"]) if "operation_id" in msg else None
    except ValueError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    try:
        async with backend.application.saved_effect_for_apply(
            msg["item_id"],
            expected_version=msg["expected_version"],
        ) as item:
            async with (
                async_control_intent(entry.runtime_data, ControlIntent.BACKGROUND)
                if "diy_destination_consent" in msg
                else nullcontext()
            ):
                destination_consent = (
                    await async_prepare_diy_destination_consent(
                        entry.runtime_data,
                        entry.entry_id,
                        msg["diy_destination_consent"],
                    )
                    if "diy_destination_consent" in msg
                    else None
                )
                diy_code = requested_diy_destination(
                    msg.get("diy_destination_consent"),
                    msg.get("diy_code"),
                )
                compiled = await async_prepare_application(
                    entry.runtime_data,
                    item,
                    diy_code=diy_code,
                    destination_consent=destination_consent,
                    intent=ControlIntent.BACKGROUND,
                )
                await backend.preview.async_supersede_device(entry.entry_id, reason="committed_apply")
                apply_kwargs: dict[str, Any] = {
                    "config_entry_id": entry.entry_id,
                    "updated_at": msg["updated_at"],
                    "operation_id": operation_id,
                    "diy_code": diy_code,
                    "compiled": compiled,
                    "write_guard": partial(_ensure_entry_control, hass, connection, entry),
                }
                if destination_consent is not None:
                    apply_kwargs["destination_consent"] = destination_consent
                if "live" in msg:
                    apply_kwargs["live"] = msg["live"]
                result = await backend.engine.async_apply_saved(
                    entry.runtime_data,
                    item,
                    **apply_kwargs,
                )
    except EffectNotFoundError as exc:
        _send_error(hass, connection, msg, "not_found", exc)
        return
    except EffectVersionConflictError as exc:
        _send_error(hass, connection, msg, "conflict", exc)
        return
    except (GoveeCryptoError, ModeTransitionSupersededError) as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
        return
    except ValueError as exc:
        _send_error(hass, connection, msg, "unsupported_model", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "storage_unavailable", exc)
        return
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except Exception as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
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
        vol.Optional("diy_code"): DIY_CODE,
        vol.Optional("diy_destination_consent"): DIY_DESTINATION_CONSENT,
    }
)
@async_response
async def ws_apply_snapshot(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    backend = _backend(hass)
    authorized = _loaded_entry_with_access(hass, connection, msg, POLICY_CONTROL)
    if authorized is None:
        return
    entry, _ = authorized
    try:
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
        operation_id = UUID(msg["operation_id"]) if "operation_id" in msg else None
        async with (
            async_control_intent(entry.runtime_data, ControlIntent.BACKGROUND)
            if "diy_destination_consent" in msg
            else nullcontext()
        ):
            destination_consent = (
                await async_prepare_diy_destination_consent(
                    entry.runtime_data,
                    entry.entry_id,
                    msg["diy_destination_consent"],
                )
                if "diy_destination_consent" in msg
                else None
            )
            diy_code = requested_diy_destination(msg.get("diy_destination_consent"), msg.get("diy_code"))
            compiled = await async_prepare_application(
                entry.runtime_data,
                item,
                diy_code=diy_code,
                destination_consent=destination_consent,
                intent=ControlIntent.BACKGROUND,
            )
            await backend.preview.async_supersede_device(entry.entry_id, reason="committed_apply")
            result = await backend.engine.async_apply_snapshot(
                entry.runtime_data,
                item,
                config_entry_id=entry.entry_id,
                updated_at=msg["updated_at"],
                operation_id=operation_id,
                diy_code=diy_code,
                compiled=compiled,
                write_guard=partial(_ensure_entry_control, hass, connection, entry),
                **({"destination_consent": destination_consent} if destination_consent is not None else {}),
            )
    except EffectValidationError as exc:
        _send_error(hass, connection, msg, "invalid_format", exc)
        return
    except (GoveeCryptoError, ModeTransitionSupersededError) as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
        return
    except ValueError as exc:
        _send_error(hass, connection, msg, "unsupported_model", exc)
        return
    except EffectStorageError as exc:
        _send_error(hass, connection, msg, "storage_unavailable", exc)
        return
    except Unauthorized as exc:
        _send_error(hass, connection, msg, "unauthorized", exc)
        return
    except Exception as exc:
        _send_error(hass, connection, msg, "apply_failed", exc)
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
    websocket_api.async_register_command(hass, ws_music_edit_retained)
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
    websocket_api.async_register_command(hass, ws_apply)
    websocket_api.async_register_command(hass, ws_apply_snapshot)


def _backend(hass: HomeAssistant) -> EffectBackend:
    return cast(EffectBackend, hass.data[DOMAIN][BACKEND_DATA_KEY])


def _log_failure(hass: HomeAssistant, msg: dict[str, Any], code: str, error: str | Exception) -> None:
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return
    entry = hass.config_entries.async_get_entry(msg["config_entry_id"]) if "config_entry_id" in msg else None
    model = (
        entry.runtime_data.model
        if entry is not None and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED
        else None
    )
    if model not in MODEL_PROFILES:
        model = None
    safe_reasons = {
        "Device profile supports no effects",
        "Device profile supports no scenes",
        "Device profile supports no effect templates",
        *(f"{model} effective profile does not support {workflow}" for workflow in CapabilityWorkflow),
        *(
            f"{model} does not support music mode {mode}"
            for modes in MUSIC_MODE_CODES_BY_MODEL.values()
            for slug in modes
            for mode in (slug, repr(slug))
        ),
    }
    # Exception messages may contain authored content, identifiers or transport credentials.
    message = str(error)
    reason = message if message in safe_reasons else code
    source = "-"
    if isinstance(error, Exception) and (traceback := error.__traceback__) is not None:
        while traceback.tb_next is not None:
            traceback = traceback.tb_next
        source = f"{traceback.tb_frame.f_code.co_name}:{traceback.tb_lineno}"
    _LOGGER.debug(
        "Effect Studio request failed: operation=%s model=%s code=%s reason=%s error_type=%s source=%s",
        msg.get("type", "unavailable"),
        model or "unavailable",
        code,
        reason,
        type(error).__name__ if isinstance(error, Exception) else "-",
        source,
    )


def _send_error(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
    code: str,
    error: str | Exception,
) -> None:
    _log_failure(hass, msg, code, error)
    connection.send_error(msg["id"], code, str(error))


def _send_preview_error(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
    error: Exception,
) -> None:
    if isinstance(error, Unauthorized):
        code = "unauthorized"
        message = "The target light is no longer permitted."
    elif isinstance(error, PreviewOwnershipError):
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
    elif (
        isinstance(error, HomeAssistantError)
        and error.translation_domain == DOMAIN
        and error.translation_key == "identity_not_ready"
    ):
        code = "preview_failed"
        message = str(error)
    else:
        code = "preview_failed"
        message = "The preview request failed."
        _LOGGER.error("Unexpected Effect Studio preview request failure: error_type=%s", type(error).__name__)
    _log_failure(hass, msg, code, error)
    connection.send_error(msg["id"], code, message)
