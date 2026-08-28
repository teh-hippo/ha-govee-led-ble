"""WebSocket command names and input validators for Effect Studio."""

from typing import Any

import voluptuous as vol

from .const import DOMAIN
from .effect_limits import (
    MAX_EFFECT_DOCUMENT_BYTES,
    MAX_EFFECT_NAME_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    MAX_JSON_COLLECTION_ITEMS,
    MAX_PREFERENCES_BYTES,
    MAX_REVISION,
    MAX_TIMESTAMP_LENGTH,
    validate_json_document,
    validate_timestamp,
)

WS_INFO = f"{DOMAIN}/editor/info"
WS_DEVICES = f"{DOMAIN}/editor/devices"
WS_DEVICE = f"{DOMAIN}/editor/device"
WS_DEVICE_SUBSCRIBE = f"{DOMAIN}/editor/device/subscribe"
WS_CUSTOM_CATALOGUE = f"{DOMAIN}/editor/custom/catalogue"
WS_LIBRARY_LIST = f"{DOMAIN}/editor/library/list"
WS_LIBRARY_GET = f"{DOMAIN}/editor/library/get"
WS_LIBRARY_CREATE = f"{DOMAIN}/editor/library/create"
WS_LIBRARY_UPDATE = f"{DOMAIN}/editor/library/update"
WS_LIBRARY_OVERWRITE = f"{DOMAIN}/editor/library/overwrite"
WS_LIBRARY_DELETE = f"{DOMAIN}/editor/library/delete"
WS_LIBRARY_NAME_STATUS = f"{DOMAIN}/editor/library/name_status"
WS_LIBRARY_SUBSCRIBE = f"{DOMAIN}/editor/library/subscribe"
WS_DEPLOYMENT_SUBSCRIBE = f"{DOMAIN}/editor/deployment/subscribe"
WS_USER_STATE_GET = f"{DOMAIN}/editor/user_state/get"
WS_USER_STATE_UPDATE = f"{DOMAIN}/editor/user_state/update"
WS_USER_STATE_RECORD_COLOUR = f"{DOMAIN}/editor/user_state/record_colour"
WS_APPLY = f"{DOMAIN}/editor/apply"
WS_APPLY_SNAPSHOT = f"{DOMAIN}/editor/apply_snapshot"
WS_SCENE_CATALOGUE_LIST = f"{DOMAIN}/editor/scene/catalogue/list"
WS_SCENE_CATALOGUE_GET = f"{DOMAIN}/editor/scene/catalogue/get"
WS_SCENE_APPLY = f"{DOMAIN}/editor/scene/apply"
WS_SCENE_DEFAULT_SET = f"{DOMAIN}/editor/scene/default/set"
WS_SCENE_RESET = f"{DOMAIN}/editor/scene/reset"
WS_TEMPLATE_DEFAULT_GET = f"{DOMAIN}/editor/template/default/get"
WS_TEMPLATE_DEFAULT_SET = f"{DOMAIN}/editor/template/default/set"
WS_TEMPLATE_DEFAULT_RESET = f"{DOMAIN}/editor/template/default/reset"
WS_PREVIEW_CLOSE = f"{DOMAIN}/editor/preview/session/close"
WS_PREVIEW_APPLY_SNAPSHOT = f"{DOMAIN}/editor/preview/apply_snapshot"
WS_PREVIEW_APPLY_SCENE = f"{DOMAIN}/editor/preview/apply_scene"
WS_PREVIEW_CANCEL = f"{DOMAIN}/editor/preview/cancel"
WS_PREVIEW_SUBSCRIBE = f"{DOMAIN}/editor/preview/subscribe"
WS_PREVIEW_HEALTH_SUBSCRIBE = f"{DOMAIN}/editor/preview/health/subscribe"
WS_PREVIEW_HEALTH_CHECK = f"{DOMAIN}/editor/preview/health/check"


def strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise vol.Invalid("value must be an integer")
    return value


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise vol.Invalid("value must be a boolean")
    return value


def _bounded_effect_content(value: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_json_document(
            value,
            "effect content",
            maximum_bytes=MAX_EFFECT_DOCUMENT_BYTES,
            error_type=ValueError,
        )
    except ValueError as exc:
        raise vol.Invalid(str(exc)) from exc
    return value


def _bounded_navigation(value: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_json_document(
            value,
            "navigation",
            maximum_bytes=MAX_PREFERENCES_BYTES,
            error_type=ValueError,
        )
    except ValueError as exc:
        raise vol.Invalid(str(exc)) from exc
    return value


def _timestamp(value: str) -> str:
    try:
        validate_timestamp(
            value,
            "timestamp",
            error_type=ValueError,
        )
    except ValueError as exc:
        raise vol.Invalid(str(exc)) from exc
    return value


def _unique_values(values: list[int]) -> list[int]:
    if len(values) != len(set(values)):
        raise vol.Invalid("values must be unique")
    return values


EFFECT_NAME = vol.All(str, vol.Length(max=MAX_EFFECT_NAME_LENGTH))
IDENTIFIER = vol.All(str, vol.Length(min=1, max=MAX_IDENTIFIER_LENGTH))
UUID_TEXT = vol.All(str, vol.Length(min=36, max=36))
TIMESTAMP = vol.All(str, vol.Length(min=1, max=MAX_TIMESTAMP_LENGTH), _timestamp)
POSITIVE_REVISION = vol.All(strict_int, vol.Range(min=1, max=MAX_REVISION))
LAYER_LABEL = vol.All(strict_int, vol.Range(min=1, max=0xFF))
LAYER_LABELS = vol.All(
    [LAYER_LABEL],
    vol.Length(max=MAX_JSON_COLLECTION_ITEMS),
    _unique_values,
)
SCENE_ID = vol.All(strict_int, vol.Range(min=0, max=0xFFFF))
SPEED_INDEX = vol.All(strict_int, vol.Range(min=0, max=0xFF))
EFFECT_CONTENT = vol.All(dict, _bounded_effect_content)
NAVIGATION = vol.All(dict, _bounded_navigation)
STRICT_BOOL = vol.All(_strict_bool)
