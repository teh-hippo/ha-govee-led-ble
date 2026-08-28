"""Effect Studio WebSocket contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.effect_application import EffectStudioApplication
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_contracts import EDITOR_API_VERSION
from custom_components.ha_govee_led_ble.effect_domain import SingleEffect, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_preview import (
    PreviewOwnershipError,
    PreviewSessionNotFoundError,
    PreviewTargetUnavailableError,
)
from custom_components.ha_govee_led_ble.effect_scenes import scene_detail_payload
from custom_components.ha_govee_led_ble.effect_storage import EffectVersionConflictError
from custom_components.ha_govee_led_ble.effect_websocket import (
    PREVIEW_SESSION_NOT_FOUND_CODE,
    PREVIEW_SESSION_UNAUTHORIZED_CODE,
    PREVIEW_TARGET_UNAVAILABLE_CODE,
    WS_APPLY,
    WS_CUSTOM_CATALOGUE,
    WS_INFO,
    WS_LIBRARY_CREATE,
    WS_LIBRARY_DELETE,
    WS_LIBRARY_GET,
    WS_LIBRARY_LIST,
    WS_LIBRARY_NAME_STATUS,
    WS_LIBRARY_OVERWRITE,
    WS_LIBRARY_SUBSCRIBE,
    WS_LIBRARY_UPDATE,
    WS_SCENE_DEFAULT_SET,
    WS_SCENE_RESET,
    WS_TEMPLATE_DEFAULT_GET,
    WS_TEMPLATE_DEFAULT_RESET,
    WS_TEMPLATE_DEFAULT_SET,
    WS_USER_STATE_GET,
    WS_USER_STATE_RECORD_COLOUR,
    WS_USER_STATE_UPDATE,
    _light_entity_id,
    _send_preview_error,
    async_register_effect_websocket,
)
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES


async def _setup_backend(hass: HomeAssistant) -> EffectBackend:
    assert await async_setup_component(hass, "websocket_api", {})
    backend = await EffectBackend.async_create(hass)
    async_register_effect_websocket(hass, backend)
    return backend


def _content(speed: int = 50) -> dict[str, Any]:
    return effect_content_to_dict(SingleEffect(0, 0, speed, ((255, 0, 0),)))


async def test_light_entity_resolution_requires_one_enabled_integration_light(
    hass: HomeAssistant,
    entity_registry,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    other = entity_registry.async_get_or_create(
        "light",
        "other",
        "other-light",
        config_entry=entry,
    )
    disabled = entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "disabled-light",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    assert _light_entity_id(hass, entry.entry_id) is None
    assert other.entity_id != disabled.entity_id

    first = entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "first-light",
        config_entry=entry,
    )
    assert _light_entity_id(hass, entry.entry_id) == first.entity_id

    entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "second-light",
        config_entry=entry,
    )
    assert _light_entity_id(hass, entry.entry_id) is None


async def test_authenticated_users_can_read_contracts(
    hass: HomeAssistant,
    hass_ws_client,
    hass_read_only_access_token: str,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)

    await client.send_json_auto_id({"type": WS_INFO})
    info = await client.receive_json()
    await client.send_json_auto_id({"type": WS_LIBRARY_LIST})
    library = await client.receive_json()
    await client.send_json_auto_id({"type": WS_CUSTOM_CATALOGUE})
    catalogue = await client.receive_json()

    assert info["result"]["api_version"] == EDITOR_API_VERSION
    assert "drafts_per_owner" not in info["result"]["limits"]
    assert library["result"] == {"generation": 0, "items": []}
    assert sorted(catalogue["result"]["catalogue"]["models"]) == ["H617A", "H6199"]


async def test_non_admin_cannot_mutate_library(
    hass: HomeAssistant,
    hass_ws_client,
    hass_read_only_access_token: str,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_CREATE,
            "name": "Test",
            "content": _content(),
        }
    )
    response = await client.receive_json()

    assert response["success"] is False
    assert response["error"]["code"] == "unauthorized"


async def test_template_default_websocket_lifecycle_has_no_ble_writes(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    await _setup_backend(hass)
    coordinator = MagicMock(model="H617A")
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    client = await hass_ws_client(hass)
    template = resolve_catalogue_template("H617A", "template:single:0:0")
    content = effect_content_to_dict(template.content)
    content["speed"] = 75

    await client.send_json_auto_id(
        {
            "type": WS_TEMPLATE_DEFAULT_GET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
        }
    )
    initial = (await client.receive_json())["result"]
    assert initial["content"] == initial["catalogue_content"]
    assert initial["has_default"] is False

    await client.send_json_auto_id(
        {
            "type": WS_TEMPLATE_DEFAULT_SET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
            "content": content,
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    stored = (await client.receive_json())["result"]
    assert stored["content"]["speed"] == 75
    assert stored["catalogue_content"]["speed"] == 50
    assert stored["has_default"] is True

    await client.send_json_auto_id(
        {
            "type": WS_TEMPLATE_DEFAULT_RESET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
        }
    )
    reset = (await client.receive_json())["result"]
    assert reset["content"] == reset["catalogue_content"]
    assert reset["has_default"] is False
    coordinator.assert_not_called()


async def test_template_default_get_is_readable_but_mutations_require_admin(
    hass: HomeAssistant,
    hass_ws_client,
    hass_read_only_access_token: str,
    monkeypatch,
) -> None:
    await _setup_backend(hass)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(model="H617A"),
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    template = resolve_catalogue_template("H617A", "template:single:0:0")

    await client.send_json_auto_id(
        {
            "type": WS_TEMPLATE_DEFAULT_GET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
        }
    )
    assert (await client.receive_json())["result"]["has_default"] is False

    for message in (
        {
            "type": WS_TEMPLATE_DEFAULT_SET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
            "content": effect_content_to_dict(template.content),
            "updated_at": "2026-08-27T00:00:00Z",
        },
        {
            "type": WS_TEMPLATE_DEFAULT_RESET,
            "config_entry_id": entry.entry_id,
            "template_id": template.id,
        },
    ):
        await client.send_json_auto_id(message)
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] == "unauthorized"


async def test_template_default_set_rejects_mismatched_identity(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    await _setup_backend(hass)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(model="H617A"),
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": WS_TEMPLATE_DEFAULT_SET,
            "config_entry_id": entry.entry_id,
            "template_id": "template:single:0:0",
            "content": effect_content_to_dict(SingleEffect(1, 0, 50, ((255, 0, 0),))),
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    response = await client.receive_json()

    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"


async def test_scene_default_websocket_persists_full_content_without_ble(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    await _setup_backend(hass)
    scene = next(
        item
        for item in SCENE_ENTRIES["H617A"]
        if item.scene_type == 2 and item.speed is not None and item.speed.option_count > 1
    )
    coordinator = SimpleNamespace(model="H617A", async_apply_native_scene=AsyncMock())
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    client = await hass_ws_client(hass)
    content = cast(dict[str, Any], scene_detail_payload("H617A", scene.scene_id, scene.effect_id)["content"])
    assert scene.speed is not None
    content["speed_index"] = (scene.speed.default_index + 1) % scene.speed.option_count

    await client.send_json_auto_id(
        {
            "type": WS_SCENE_DEFAULT_SET,
            "config_entry_id": entry.entry_id,
            "scene_id": scene.scene_id,
            "effect_id": scene.effect_id,
            "content": content,
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    stored = (await client.receive_json())["result"]
    assert stored["has_default"] is True
    assert stored["content"]["speed_index"] == content["speed_index"]
    assert stored["catalogue_content"]["speed_index"] == scene.speed.default_index

    await client.send_json_auto_id(
        {
            "type": WS_SCENE_RESET,
            "config_entry_id": entry.entry_id,
            "scene_id": scene.scene_id,
            "effect_id": scene.effect_id,
        }
    )
    reset = (await client.receive_json())["result"]
    assert reset["has_default"] is False
    assert reset["content"] == reset["catalogue_content"]
    coordinator.async_apply_native_scene.assert_not_awaited()


async def test_apply_forwards_expected_item_version(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    monkeypatch.setattr(cast(Any, backend.preview), "async_supersede_device", AsyncMock())
    deployment = MagicMock()
    deployment.to_public_dict.return_value = {"phase": "confirmed"}
    apply_saved = AsyncMock(return_value=deployment)
    monkeypatch.setattr(cast(Any, EffectStudioApplication), "async_apply_saved_effect", apply_saved)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=MagicMock(),
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": WS_APPLY,
            "config_entry_id": entry.entry_id,
            "item_id": "00000000-0000-0000-0000-000000000001",
            "expected_version": 4,
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    response = await client.receive_json()

    assert response["success"] is True
    apply_saved.assert_awaited_once_with(
        backend.engine,
        entry.runtime_data,
        item_id="00000000-0000-0000-0000-000000000001",
        config_entry_id=entry.entry_id,
        updated_at="2026-08-27T00:00:00Z",
        operation_id=None,
        expected_version=4,
    )


async def test_apply_surfaces_item_version_conflict(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    monkeypatch.setattr(cast(Any, backend.preview), "async_supersede_device", AsyncMock())
    apply_saved = AsyncMock(
        side_effect=EffectVersionConflictError(5),
    )
    monkeypatch.setattr(cast(Any, EffectStudioApplication), "async_apply_saved_effect", apply_saved)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=MagicMock(),
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": WS_APPLY,
            "config_entry_id": entry.entry_id,
            "item_id": "00000000-0000-0000-0000-000000000001",
            "expected_version": 4,
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    response = await client.receive_json()

    assert response["success"] is False
    assert response["error"]["code"] == "conflict"


async def test_admin_current_only_library_lifecycle_and_stale_token(
    hass: HomeAssistant,
    hass_ws_client,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_CREATE,
            "name": "Test",
            "content": _content(),
        }
    )
    create_result = (await client.receive_json())["result"]
    created = create_result["item"]
    assert created["version"] == 1
    assert len(created["content_hash"]) == 64
    assert created["origin"] == {"kind": "authored", "source_id": None}
    assert create_result["library"]["generation"] == 1

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_UPDATE,
            "item_id": created["id"],
            "name": "Updated",
            "content": _content(60),
            "expected_version": created["version"],
            "expected_updated_at": created["updated_at"],
        }
    )
    update_result = (await client.receive_json())["result"]
    updated = update_result["item"]
    assert updated["version"] == 2
    assert updated["updated_at"] > created["updated_at"]
    assert update_result["library"]["generation"] == 2

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_UPDATE,
            "item_id": created["id"],
            "name": "Stale",
            "content": _content(),
            "expected_version": created["version"],
            "expected_updated_at": created["updated_at"],
        }
    )
    conflict = await client.receive_json()
    assert conflict["success"] is False
    assert conflict["error"]["code"] == "conflict"

    await client.send_json_auto_id({"type": WS_LIBRARY_GET, "item_id": created["id"]})
    assert (await client.receive_json())["result"]["item"] == updated

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_DELETE,
            "item_id": updated["id"],
            "expected_version": updated["version"],
            "expected_updated_at": updated["updated_at"],
        }
    )
    deleted = await client.receive_json()
    assert deleted["success"] is True
    assert deleted["result"]["library"] == {"generation": 3, "items": []}
    await client.send_json_auto_id({"type": WS_LIBRARY_LIST})
    assert (await client.receive_json())["result"] == {"generation": 3, "items": []}


async def test_library_subscription_publishes_current_snapshot(
    hass: HomeAssistant,
    hass_ws_client,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": WS_LIBRARY_SUBSCRIBE})
    subscribed = await client.receive_json()
    assert subscribed["success"] is True
    initial = await client.receive_json()
    assert initial["id"] == subscribed["id"]
    assert initial["event"] == {"generation": 0, "items": []}

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_CREATE,
            "name": "Test",
            "content": _content(),
        }
    )
    messages = [await client.receive_json(), await client.receive_json()]
    created = next(message for message in messages if "success" in message)
    event = next(message for message in messages if "event" in message)

    assert created["success"] is True
    assert event["id"] == subscribed["id"]
    assert event["event"]["generation"] == 1
    assert event["event"]["items"][0]["version"] == 1


async def test_library_name_status_and_distinct_name_errors(
    hass: HomeAssistant,
    hass_ws_client,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_CREATE,
            "name": "Saved",
            "content": _content(),
        }
    )
    saved = (await client.receive_json())["result"]["item"]

    for name, excluding_item_id, expected in (
        ("Available", None, {"kind": "available"}),
        ("Custom", saved["id"], {"kind": "reserved"}),
        ("Saved", saved["id"], {"kind": "same_item"}),
    ):
        await client.send_json_auto_id(
            {
                "type": WS_LIBRARY_NAME_STATUS,
                "name": name,
                **({"excluding_item_id": excluding_item_id} if excluding_item_id else {}),
            }
        )
        assert (await client.receive_json())["result"]["status"] == expected

    await client.send_json_auto_id({"type": WS_LIBRARY_NAME_STATUS, "name": "Saved"})
    conflict = (await client.receive_json())["result"]["status"]
    assert conflict["kind"] == "saved"
    assert conflict["item"]["id"] == saved["id"]

    for name, code in (("Custom", "reserved_name"), ("Saved", "name_conflict")):
        await client.send_json_auto_id(
            {
                "type": WS_LIBRARY_CREATE,
                "name": name,
                "content": _content(),
            }
        )
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] == code

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_CREATE,
            "name": "Other",
            "content": _content(),
        }
    )
    other = (await client.receive_json())["result"]["item"]
    for item, name, code in (
        (saved, "Custom", "reserved_name"),
        (other, "Saved", "name_conflict"),
    ):
        await client.send_json_auto_id(
            {
                "type": WS_LIBRARY_UPDATE,
                "item_id": item["id"],
                "name": name,
                "content": _content(),
                "expected_version": item["version"],
                "expected_updated_at": item["updated_at"],
            }
        )
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] == code


async def test_library_overwrite_updates_only_target_and_returns_snapshot(
    hass: HomeAssistant,
    hass_ws_client,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass)
    items = []
    for name in ("Source", "Target"):
        await client.send_json_auto_id(
            {
                "type": WS_LIBRARY_CREATE,
                "name": name,
                "content": _content(),
            }
        )
        items.append((await client.receive_json())["result"]["item"])
    source, target = items

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_OVERWRITE,
            "target_item_id": target["id"],
            "expected_version": target["version"],
            "expected_updated_at": target["updated_at"],
            "name": target["name"],
            "content": _content(75),
        }
    )
    result = (await client.receive_json())["result"]

    assert result["item"]["id"] == target["id"]
    assert result["item"]["version"] == 2
    assert result["library"]["generation"] == 3
    assert {item["id"] for item in result["library"]["items"]} == {source["id"], target["id"]}

    await client.send_json_auto_id({"type": WS_LIBRARY_GET, "item_id": source["id"]})
    assert (await client.receive_json())["result"]["item"] == source

    await client.send_json_auto_id(
        {
            "type": WS_LIBRARY_OVERWRITE,
            "target_item_id": target["id"],
            "expected_version": target["version"],
            "expected_updated_at": target["updated_at"],
            "name": target["name"],
            "content": _content(),
        }
    )
    stale = await client.receive_json()
    assert stale["success"] is False
    assert stale["error"]["code"] == "conflict"


async def test_library_mutations_reject_invalid_layer_metadata_and_extensions(
    hass: HomeAssistant,
    hass_ws_client,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass)

    for extra in (
        {"layer_labels": [True]},
        {"layer_labels": [1, 1]},
        {"layer_labels": [1]},
        {"extensions": {"arbitrary": True}},
    ):
        await client.send_json_auto_id(
            {
                "type": WS_LIBRARY_CREATE,
                "name": "Invalid",
                "content": _content(),
                **extra,
            }
        )
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] in {"invalid_format", "invalid_info"}


async def test_user_state_contains_navigation_without_drafts(
    hass: HomeAssistant,
    hass_ws_client,
    hass_read_only_access_token: str,
) -> None:
    await _setup_backend(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)

    await client.send_json_auto_id(
        {
            "type": WS_USER_STATE_UPDATE,
            "selected_config_entry_id": "entry-a",
            "navigation": {"section": "scenes", "item_id": "effect-a"},
        }
    )
    updated = (await client.receive_json())["result"]["user_state"]
    await client.send_json_auto_id(
        {
            "type": WS_USER_STATE_RECORD_COLOUR,
            "colour": [1, 2, 3],
        }
    )
    coloured = (await client.receive_json())["result"]["user_state"]
    await client.send_json_auto_id({"type": WS_USER_STATE_GET})
    fetched = (await client.receive_json())["result"]["user_state"]

    assert updated["selected_config_entry_id"] == "entry-a"
    assert updated["navigation"] == {"section": "scenes", "item_id": "effect-a"}
    assert coloured["recent_colours"] == [[1, 2, 3]]
    assert fetched == coloured
    assert "preferences" not in fetched


def test_preview_session_and_target_errors_have_distinct_codes() -> None:
    connection = Mock()
    cases = (
        (
            PreviewSessionNotFoundError("missing"),
            PREVIEW_SESSION_NOT_FOUND_CODE,
            "The preview session was not found.",
        ),
        (
            PreviewOwnershipError("wrong owner"),
            PREVIEW_SESSION_UNAUTHORIZED_CODE,
            "The preview session belongs to another connection.",
        ),
        (
            PreviewTargetUnavailableError("unloaded"),
            PREVIEW_TARGET_UNAVAILABLE_CODE,
            "The target light is not loaded.",
        ),
    )

    for error, code, message in cases:
        connection.reset_mock()
        _send_preview_error(connection, 7, error)
        connection.send_error.assert_called_once_with(7, code, message)
