"""Effect Studio WebSocket contracts."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ha_govee_led_ble.const import CONF_SHOW_EXPERIMENTAL_FEEDBACK, DOMAIN, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import ModeTransitionSupersededError
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_contracts import EDITOR_API_VERSION
from custom_components.ha_govee_led_ble.effect_domain import SingleEffect, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_preview import (
    PreviewError,
    PreviewOwnershipError,
    PreviewSessionNotFoundError,
    PreviewTargetUnavailableError,
)
from custom_components.ha_govee_led_ble.effect_scenes import scene_detail_payload
from custom_components.ha_govee_led_ble.effect_websocket import (
    PREVIEW_SESSION_NOT_FOUND_CODE,
    PREVIEW_SESSION_UNAUTHORIZED_CODE,
    PREVIEW_TARGET_UNAVAILABLE_CODE,
    WS_APPLY,
    WS_APPLY_SNAPSHOT,
    WS_CUSTOM_CATALOGUE,
    WS_DEVICE_SUBSCRIBE,
    WS_INFO,
    WS_LIBRARY_CREATE,
    WS_LIBRARY_DELETE,
    WS_LIBRARY_GET,
    WS_LIBRARY_LIST,
    WS_LIBRARY_NAME_STATUS,
    WS_LIBRARY_OVERWRITE,
    WS_LIBRARY_SUBSCRIBE,
    WS_LIBRARY_UPDATE,
    WS_PREVIEW_APPLY_SNAPSHOT,
    WS_SCENE_APPLY,
    WS_SCENE_DEFAULT_SET,
    WS_SCENE_RESET,
    WS_TEMPLATE_DEFAULT_GET,
    WS_TEMPLATE_DEFAULT_RESET,
    WS_TEMPLATE_DEFAULT_SET,
    WS_USER_STATE_GET,
    WS_USER_STATE_UPDATE,
    _light_entity_id,
    _send_preview_error,
    async_register_effect_websocket,
)
from custom_components.ha_govee_led_ble.govee_encryption import GoveeCryptoError, GoveeTransportError
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from tests.test_effect_preview import _EffectCoordinator


async def _setup_backend(hass: HomeAssistant) -> EffectBackend:
    assert await async_setup_component(hass, "websocket_api", {})
    backend = await EffectBackend.async_create(hass)
    async_register_effect_websocket(hass, backend)
    return backend


def _content(speed: int = 50) -> dict[str, Any]:
    return effect_content_to_dict(SingleEffect(0, 0, speed, ((255, 0, 0),)))


@pytest.mark.parametrize(
    ("operation", "reason"),
    [
        ("saved", "Device profile supports no effects"),
        ("snapshot", "H6127 effective profile does not support single"),
        ("preview", "H6127 does not support music mode energetic"),
    ],
)
async def test_studio_logs_capability_rejections_without_changing_browser_errors(
    hass, hass_ws_client, monkeypatch, caplog, operation, reason
):
    from custom_components.ha_govee_led_ble import effect_websocket

    backend = await _setup_backend(hass)
    coordinator = _EffectCoordinator(model="H6127", profile=get_profile("H6127"))
    entry = SimpleNamespace(
        entry_id="private-entry", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    message: dict[str, Any] = {"config_entry_id": entry.entry_id, "updated_at": "2026-11-17T00:00:00Z"}
    if operation == "saved":
        mutation = await backend.application.async_create_library_item(name="Private name", content=_content())
        message.update({"type": WS_APPLY, "item_id": str(mutation.item.id), "expected_version": 1})
    else:
        message.update(
            {
                "type": WS_APPLY_SNAPSHOT if operation == "snapshot" else WS_PREVIEW_APPLY_SNAPSHOT,
                "name": "Private name",
                "content": _content(),
            }
        )
    if operation == "preview":
        message.update({"session_id": str(uuid4()), "sequence": 1})
        monkeypatch.setattr(backend.preview, "async_queue_snapshot", AsyncMock(side_effect=PreviewError(reason)))
    else:
        monkeypatch.setattr(effect_websocket, "async_prepare_application", AsyncMock(side_effect=ValueError(reason)))
    client = await hass_ws_client(hass)
    with caplog.at_level(logging.DEBUG, logger=effect_websocket.__name__):
        await client.send_json_auto_id(message)
        response = await client.receive_json()
    assert response["error"] == {
        "code": "invalid_format" if operation == "preview" else "unsupported_model",
        "message": reason,
    }
    records = [record for record in caplog.records if record.name == effect_websocket.__name__]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert message["type"] in records[0].message
    assert "model=H6127" in records[0].message
    assert reason in records[0].message
    assert entry.entry_id not in records[0].message
    assert "Private name" not in records[0].message


@pytest.mark.parametrize("state", [None, ConfigEntryState.NOT_LOADED])
async def test_studio_failure_logging_handles_missing_or_unloaded_targets(
    hass, hass_ws_client, monkeypatch, caplog, state
):
    logger = "custom_components.ha_govee_led_ble.effect_websocket"
    caplog.set_level(logging.DEBUG, logger=logger)
    await _setup_backend(hass)
    entry = None if state is None else SimpleNamespace(domain=DOMAIN, state=state)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": WS_APPLY_SNAPSHOT,
            "config_entry_id": "private-entry",
            "name": "Private name",
            "content": _content(),
            "updated_at": "2026-11-17T00:00:00Z",
        }
    )
    response = await client.receive_json()
    assert response["error"] == {"code": "not_found", "message": "target config entry is not loaded"}
    records = [record for record in caplog.records if record.name == logger]
    assert len(records) == 1
    assert WS_APPLY_SNAPSHOT in records[0].message
    assert "model=unavailable code=not_found" in records[0].message
    assert all(value not in records[0].message for value in ("private-entry", "Private name"))


@pytest.mark.parametrize("reason", ["missing", "stale"])
async def test_invalid_saved_apply_preserves_preview_before_identity_preparation(
    hass, hass_ws_client, monkeypatch, reason
):
    backend = await _setup_backend(hass)
    mutation = await backend.application.async_create_library_item(name="Saved guard", content=_content())
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H619A", configuration_url=None)
    entry = SimpleNamespace(entry_id="entry", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    connect = AsyncMock(return_value=MagicMock(is_connected=True))
    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    preview = coordinator.admit_preview()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": WS_APPLY,
            "config_entry_id": "entry",
            "item_id": "00000000-0000-0000-0000-000000000000" if reason == "missing" else str(mutation.item.id),
            "expected_version": mutation.item.version + 1,
            "updated_at": "2026-11-12T00:00:00Z",
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == ("not_found" if reason == "missing" else "conflict")
    assert preview.is_current
    connect.assert_not_awaited()


@pytest.mark.parametrize("case", ["speed-range", "no-speed", "unsupported-snapshot"])
async def test_invalid_studio_parameters_preserve_preview_during_preparation(hass, hass_ws_client, monkeypatch, case):
    await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H619A", configuration_url=None)
    entry = SimpleNamespace(entry_id="entry", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    connect = AsyncMock(return_value=MagicMock(is_connected=True))
    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    preview = coordinator.admit_preview()
    if case == "unsupported-snapshot":
        message = {
            "type": WS_APPLY_SNAPSHOT,
            "config_entry_id": "entry",
            "name": "Unsupported",
            "content": effect_content_to_dict(SingleEffect(250, 0, 50, ((255, 0, 0),))),
            "updated_at": "2026-11-12T00:00:00Z",
        }
    else:
        scene = next(scene for scene in SCENE_ENTRIES["H619A"] if (scene.speed is not None) == (case == "speed-range"))
        message = {
            "type": WS_SCENE_APPLY,
            "config_entry_id": "entry",
            "scene_id": scene.scene_id,
            "effect_id": scene.effect_id,
            "speed_index": 255 if case == "speed-range" else 0,
        }
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(message)
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == ("unsupported_model" if case == "unsupported-snapshot" else "invalid_format")
    assert preview.is_current
    connect.assert_not_awaited()


@pytest.mark.parametrize("sources_first", [False, True])
async def test_light_entity_resolution_uses_the_enabled_primary_identity(
    hass: HomeAssistant,
    entity_registry,
    sources_first,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)
    entity_registry.async_get_or_create("light", "other", "aabbccddeeff", config_entry=entry)
    if sources_first:
        entity_registry.async_get_or_create("light", DOMAIN, "aabbccddeeff_top", config_entry=entry)
    primary = entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "aabbccddeeff",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    assert _light_entity_id(hass, entry.entry_id) is None
    primary = entity_registry.async_update_entity(
        primary.entity_id, disabled_by=None, new_entity_id="light.renamed_master"
    )
    assert _light_entity_id(hass, entry.entry_id) == primary.entity_id
    if not sources_first:
        entity_registry.async_get_or_create("light", DOMAIN, "aabbccddeeff_top", config_entry=entry)
    assert _light_entity_id(hass, entry.entry_id) == primary.entity_id
    extra = entity_registry.async_get_or_create("light", DOMAIN, "aabbccddeeff_bottom", config_entry=entry)
    assert _light_entity_id(hass, entry.entry_id) == primary.entity_id
    entity_registry.async_update_entity(primary.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    entity_registry.async_update_entity(extra.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    assert _light_entity_id(hass, entry.entry_id) is None
    entity_registry.async_remove(primary.entity_id)
    assert _light_entity_id(hass, entry.entry_id) is None


@pytest.mark.parametrize("unique_id", [None, "AA:BB:CC:DD:EE:FF"])
async def test_light_entity_resolution_rejects_missing_identity_or_foreign_owner(
    hass, entity_registry, unique_id
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=unique_id)
    entry.add_to_hass(hass)
    foreign = MockConfigEntry(domain=DOMAIN, unique_id="11:22:33:44:55:66")
    foreign.add_to_hass(hass)
    entity_registry.async_get_or_create("light", DOMAIN, "aabbccddeeff", config_entry=foreign)
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
    assert set(catalogue["result"]["catalogue"]["models"]) == {
        "H1771",
        "H6046",
        "H605C",
        "H1A42",
        "H1AB2",
        "H600A",
        "H601C",
        "H6072",
        "H6076",
        "H607C",
        "H6097",
        "H6099",
        "H60A1",
        "H60A6",
        "H60B0",
        "H60B2",
        "H6102",
        "H6117",
        "H6125",
        "H6127",
        "H6159",
        "H6179",
        "H6181",
        "H6182",
        "H617A",
        "H617C",
        "H617E",
        "H619A",
        "H6199",
        "H61F5",
        "H66A0",
        "H7020",
        "H7025",
        "H705A",
    }


async def test_device_subscription_reports_observed_identity_without_querying(
    hass: HomeAssistant,
    hass_ws_client,
    mock_coordinator,
    monkeypatch,
) -> None:
    await _setup_backend(hass)
    entry = SimpleNamespace(
        entry_id="entry-a",
        unique_id="AA:BB:CC:DD:EE:FF",
        title="Private device name",
        options={},
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=mock_coordinator,
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WS_DEVICE_SUBSCRIBE, "config_entry_id": entry.entry_id})
    assert (await client.receive_json())["success"] is True
    device = (await client.receive_json())["event"]["device"]
    assert device["confirmation_issue"] == get_profile("H617A").confirmation_issue
    assert device["hw_version"] is None and device["fw_version"] is None
    assert device["show_experimental_feedback"] is True

    entry.options[CONF_SHOW_EXPERIMENTAL_FEEDBACK] = False
    mock_coordinator.hw_version = "1.00.01"
    mock_coordinator.fw_version = "1.02.03"
    mock_coordinator.subordinate_20_version = "2.03.04"
    mock_coordinator.async_add_listener.call_args.args[0]()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    device = (await client.receive_json())["event"]["device"]
    assert device["model"] == "H617A"
    assert device["hw_version"] == "1.00.01"
    assert device["fw_version"] == "1.02.03"
    assert device["subordinate_20_version"] == "2.03.04"
    assert device["show_experimental_feedback"] is False
    mock_coordinator.async_request_refresh.assert_not_called()
    mock_coordinator._async_write_packet.assert_not_called()


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
    coordinator = MagicMock(model="H617A", profile=get_profile("H617A"))
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
        runtime_data=_EffectCoordinator(model="H617A", profile=get_profile("H617A")),
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
        runtime_data=_EffectCoordinator(model="H617A", profile=get_profile("H617A")),
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
    coordinator = _EffectCoordinator(model="H617A", profile=get_profile("H617A"), async_apply_native_scene=AsyncMock())
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


@pytest.mark.parametrize("live", [False, True])
async def test_apply_forwards_expected_item_version(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
    live,
) -> None:
    backend = await _setup_backend(hass)
    monkeypatch.setattr(cast(Any, backend.preview), "async_supersede_device", AsyncMock())
    deployment = MagicMock()
    deployment.to_public_dict.return_value = {"phase": "confirmed"}
    apply_saved = AsyncMock(return_value=deployment)
    monkeypatch.setattr(backend.engine, "async_apply_saved", apply_saved)
    mutation = await backend.application.async_create_library_item(name="Saved", content=_content())
    item = replace(mutation.item, version=2)
    await backend.library.async_update(item, expected_version=1, expected_updated_at=mutation.item.updated_at)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=_EffectCoordinator(model="H617A", profile=get_profile("H617A")),
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
            "item_id": str(item.id),
            "expected_version": 2,
            "updated_at": "2026-08-27T00:00:00Z",
            **({"live": True} if live else {}),
        }
    )
    response = await client.receive_json()

    assert response["success"] is True
    assert apply_saved.await_args is not None
    apply_saved.assert_awaited_once_with(
        entry.runtime_data,
        item,
        config_entry_id=entry.entry_id,
        updated_at="2026-08-27T00:00:00Z",
        operation_id=None,
        diy_code=None,
        compiled=apply_saved.await_args.kwargs["compiled"],
        **({"live": True} if live else {}),
    )


@pytest.mark.parametrize("live", [False, True])
async def test_saved_apply_live_marker_enforces_source_observation_policy(hass, hass_ws_client, monkeypatch, live):
    from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
    from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene
    from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness
    from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
    from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
    from tests.test_coordinator_recovery import source_recovery_wire

    backend = await _setup_backend(hass)
    coordinator, physical = source_recovery_wire(hass, monkeypatch, "H607C")
    await coordinator.send_command(build_brightness(40, coordinator.model, profile=coordinator.profile))
    count = coordinator.profile.segment_count
    authored = [(index + 1, 20, 40) for index in range(count)]
    await coordinator.async_paint_segments([([index], rgb) for index, rgb in enumerate(authored, 1)])
    await coordinator.async_set_segment_brightness(list(range(1, count + 1)), 60)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=False))
    before = coordinator.capture_effect_control_state()
    assert before.segment_colors == tuple(authored) and not before.static_colour_observed
    scene = next(scene for scene in MODEL_SCENES["H607C"].values() if scene.scene_type == 0 and scene.speed is None)
    mutation = await backend.application.async_create_library_item(
        name="Saved scene",
        content=effect_content_to_dict(BuiltinScene(CatalogueRef("H607C", scene.scene_id, scene.effect_id))),
    )
    entry = SimpleNamespace(entry_id="entry-a", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(
        hass.config_entries, "async_get_entry", lambda entry_id: entry if entry_id == entry.entry_id else None
    )
    physical["packets"].clear()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": WS_APPLY,
            "config_entry_id": entry.entry_id,
            "item_id": str(mutation.item.id),
            "expected_version": mutation.item.version,
            "updated_at": "2026-11-16T00:00:00Z",
            "live": live,
        }
    )
    response = await client.receive_json()
    if live:
        assert not response["success"]
        assert response["error"]["code"] == "apply_failed"
        assert "live_recovery_not_observed" in response["error"]["message"]
        assert not any(packet[0] == 0x33 for packet in physical["packets"])
        assert physical["colours"] == authored
    else:
        assert response["success"]
        assert any(packet[0] == 0x33 for packet in physical["packets"])
        assert coordinator._pre_mode_snapshot is not None
        assert coordinator._pre_mode_snapshot.segment_colors == tuple(authored)


async def test_apply_surfaces_item_version_conflict(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    monkeypatch.setattr(cast(Any, backend.preview), "async_supersede_device", AsyncMock())
    mutation = await backend.application.async_create_library_item(name="Saved", content=_content())
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=_EffectCoordinator(model="H617A", profile=get_profile("H617A")),
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
            "item_id": str(mutation.item.id),
            "expected_version": 4,
            "updated_at": "2026-08-27T00:00:00Z",
        }
    )
    response = await client.receive_json()

    assert response["success"] is False
    assert response["error"]["code"] == "conflict"
    backend.preview.async_supersede_device.assert_not_awaited()


@pytest.mark.parametrize("operation", ["scene", "saved", "snapshot"])
@pytest.mark.parametrize(
    "error_type", [ValueError, GoveeCryptoError, GoveeTransportError, ModeTransitionSupersededError]
)
async def test_apply_distinguishes_session_failure_from_invalid_request(
    hass, hass_ws_client, monkeypatch, caplog, operation, error_type
):
    from custom_components.ha_govee_led_ble import effect_websocket

    backend = await _setup_backend(hass)
    monkeypatch.setattr(backend.preview, "async_supersede_device", AsyncMock())
    coordinator = _EffectCoordinator(model="H617A", profile=get_profile("H617A"))
    entry = SimpleNamespace(entry_id="entry-a", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    private_error = "AA:BB:CC:DD:EE:FF token=private-token Private effect content"
    apply = AsyncMock(side_effect=error_type(private_error))
    message: dict[str, Any] = {"config_entry_id": entry.entry_id, "updated_at": "2026-08-27T00:00:00Z"}
    if operation == "scene":
        monkeypatch.setattr(effect_websocket, "async_apply_scene", apply)
        scene = SCENE_ENTRIES["H617A"][0]
        message = {
            "type": WS_SCENE_APPLY,
            "config_entry_id": entry.entry_id,
            "scene_id": scene.scene_id,
            "effect_id": scene.effect_id,
        }
    elif operation == "saved":
        monkeypatch.setattr(backend.engine, "async_apply_saved", apply)
        mutation = await backend.application.async_create_library_item(name="Saved", content=_content())
        message.update({"type": WS_APPLY, "item_id": str(mutation.item.id), "expected_version": 1})
    else:
        monkeypatch.setattr(backend.engine, "async_apply_snapshot", apply)
        message.update({"type": WS_APPLY_SNAPSHOT, "name": "Snapshot", "content": _content()})
    client = await hass_ws_client(hass)
    try:
        with caplog.at_level(logging.DEBUG, logger=effect_websocket.__name__):
            await client.send_json_auto_id(message)
            response = await client.receive_json()
        assert response["success"] is False
        expected = (
            ("invalid_format" if operation == "scene" else "unsupported_model")
            if error_type is ValueError
            else "apply_failed"
        )
        assert response["error"]["code"] == expected
        assert response["error"]["message"] == private_error
        records = [record for record in caplog.records if record.name == effect_websocket.__name__]
        assert len(records) == 1
        assert message["type"] in records[0].message
        assert "model=H617A" in records[0].message
        assert f"code={expected}" in records[0].message
        assert error_type.__name__ in records[0].message
        assert records[0].exc_info is None
        assert all(value not in records[0].message for value in (private_error, entry.entry_id, "private-token"))
        apply.assert_awaited_once()
    finally:
        await client.close()
        await backend.preview.async_shutdown()


@pytest.mark.parametrize("error_type", [ValueError, GoveeCryptoError, GoveeTransportError])
async def test_preview_preparation_reports_session_failure_without_queueing(
    hass, hass_ws_client, monkeypatch, caplog, error_type
):
    logger = "custom_components.ha_govee_led_ble.effect_websocket"
    caplog.set_level(logging.DEBUG, logger=logger)
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H619A", configuration_url=None)
    entry = SimpleNamespace(entry_id="entry-a", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    prepare = AsyncMock(side_effect=error_type("AA:BB:CC:DD:EE:FF token=private-token"))
    monkeypatch.setattr(coordinator, "_ensure_connected", prepare)
    client = await hass_ws_client(hass)
    try:
        await client.send_json_auto_id(
            {
                "type": WS_PREVIEW_APPLY_SNAPSHOT,
                "session_id": str(uuid4()),
                "sequence": 1,
                "config_entry_id": entry.entry_id,
                "name": "Snapshot",
                "content": effect_content_to_dict(
                    resolve_catalogue_template("H619A", "template:native-diy:501").content
                ),
                "updated_at": "2026-08-27T00:00:00Z",
                "diy_code": 24,
            }
        )
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] == ("invalid_format" if error_type is ValueError else "preview_failed")
        records = [record for record in caplog.records if record.name == logger and record.levelno == logging.DEBUG]
        assert len(records) == 1
        assert WS_PREVIEW_APPLY_SNAPSHOT in records[0].message
        assert "model=H619A" in records[0].message
        for record in (record for record in caplog.records if record.name == logger):
            assert record.exc_info is None
            assert all(value not in record.message for value in ("AA:BB:CC:DD:EE:FF", "private-token", entry.entry_id))
        prepare.assert_awaited_once()
        assert not backend.preview._devices and coordinator.control_write_attempts == 0
    finally:
        await client.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("saved", [True, False])
async def test_ineligible_apply_preserves_preview(hass, hass_ws_client, monkeypatch, effect_catalogue_targets, saved):
    _broad, narrow = effect_catalogue_targets
    backend = await _setup_backend(hass)
    supersede = AsyncMock()
    monkeypatch.setattr(backend.preview, "async_supersede_device", supersede)
    apply_saved = AsyncMock()
    apply_snapshot = AsyncMock()
    monkeypatch.setattr(backend.engine, "async_apply_saved", apply_saved)
    monkeypatch.setattr(backend.engine, "async_apply_snapshot", apply_snapshot)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=_EffectCoordinator(model=narrow, profile=get_profile(narrow)),
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _entry_id: entry)
    content = effect_content_to_dict(SingleEffect(0, 1, 50, ((255, 0, 0), (0, 0, 255))))
    mutation = await backend.application.async_create_library_item(name="Imported", content=content)
    client = await hass_ws_client(hass)
    message = {
        "type": WS_APPLY if saved else WS_APPLY_SNAPSHOT,
        "config_entry_id": entry.entry_id,
        "updated_at": "2026-08-27T00:00:00Z",
    }
    message.update(
        {"item_id": str(mutation.item.id), "expected_version": 1} if saved else {"name": "Imported", "content": content}
    )
    await client.send_json_auto_id(message)
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "unsupported_model"
    supersede.assert_not_awaited()
    apply_saved.assert_not_awaited()
    apply_snapshot.assert_not_awaited()


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
    await client.send_json_auto_id({"type": WS_USER_STATE_GET})
    fetched = (await client.receive_json())["result"]["user_state"]

    assert updated["selected_config_entry_id"] == "entry-a"
    assert updated["navigation"] == {"section": "scenes", "item_id": "effect-a"}
    assert fetched == updated
    assert "preferences" not in fetched


def test_preview_session_and_target_errors_have_distinct_codes(hass) -> None:
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
        _send_preview_error(hass, connection, {"id": 7, "type": WS_PREVIEW_APPLY_SNAPSHOT}, error)
        connection.send_error.assert_called_once_with(7, code, message)
