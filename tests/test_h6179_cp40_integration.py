"""Serialized CP-40 backend integration checks."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_domain import (
    H6179SingleDiyEffect,
    LibraryItem,
    SingleEffect,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_websocket import async_register_effect_websocket
from custom_components.ha_govee_led_ble.effect_websocket_schema import (
    WS_APPLY,
    WS_APPLY_SNAPSHOT,
    WS_PREVIEW_APPLY_SNAPSHOT,
)

DIY_CODE = 0x1234


async def test_h6179_diy_approval_reaches_saved_snapshot_and_preview_websockets(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    item = LibraryItem.new(
        "Disposable",
        H6179SingleDiyEffect("H6179", 0, 0, 50, ((255, 0, 0),)),
    )
    deployment = SimpleNamespace(to_public_dict=lambda: {"phase": "confirmed"})
    acceptance = SimpleNamespace(to_dict=lambda: {"accepted": True})
    application = SimpleNamespace(
        async_apply_saved_effect=AsyncMock(return_value=deployment),
        new_authored_item=MagicMock(return_value=item),
    )
    engine = SimpleNamespace(async_apply_snapshot=AsyncMock(return_value=deployment))
    preview = SimpleNamespace(
        async_supersede_device=AsyncMock(),
        ensure_session=MagicMock(),
        async_queue_snapshot=AsyncMock(return_value=acceptance),
    )
    backend = cast(
        EffectBackend,
        cast(
            Any,
            SimpleNamespace(
                application=application,
                engine=engine,
                preview=preview,
            ),
        ),
    )
    coordinator = SimpleNamespace(model="H6179")
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
    async_register_effect_websocket(hass, backend)
    client = await hass_ws_client(hass)
    content = effect_content_to_dict(item.content)
    updated_at = "2026-09-03T00:00:00Z"

    await client.send_json_auto_id(
        {
            "type": WS_APPLY,
            "config_entry_id": entry.entry_id,
            "item_id": str(item.id),
            "expected_version": item.version,
            "updated_at": updated_at,
            "diy_code": DIY_CODE,
        }
    )
    assert (await client.receive_json())["result"]["deployment"]["phase"] == "confirmed"

    await client.send_json_auto_id(
        {
            "type": WS_APPLY_SNAPSHOT,
            "config_entry_id": entry.entry_id,
            "name": item.name,
            "content": content,
            "updated_at": updated_at,
            "diy_code": DIY_CODE,
        }
    )
    assert (await client.receive_json())["result"]["deployment"]["phase"] == "confirmed"

    await client.send_json_auto_id(
        {
            "type": WS_PREVIEW_APPLY_SNAPSHOT,
            "session_id": "11111111-1111-1111-1111-111111111111",
            "sequence": 1,
            "config_entry_id": entry.entry_id,
            "updated_at": updated_at,
            "name": item.name,
            "content": content,
            "diy_code": DIY_CODE,
        }
    )
    assert (await client.receive_json())["result"] == {"accepted": True}

    assert application.async_apply_saved_effect.await_args.kwargs["diy_code"] == DIY_CODE
    assert engine.async_apply_snapshot.await_args.kwargs["diy_code"] == DIY_CODE
    assert preview.async_queue_snapshot.await_args.kwargs["diy_code"] == DIY_CODE

    application.async_apply_saved_effect.reset_mock()
    engine.async_apply_snapshot.reset_mock()
    preview.async_queue_snapshot.reset_mock()
    coordinator.model = "H617A"
    legacy_item = LibraryItem.new("Legacy", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    application.new_authored_item.return_value = legacy_item
    legacy_content = effect_content_to_dict(legacy_item.content)

    for payload in (
        {
            "type": WS_APPLY,
            "config_entry_id": entry.entry_id,
            "item_id": str(item.id),
            "expected_version": item.version,
            "updated_at": updated_at,
        },
        {
            "type": WS_APPLY_SNAPSHOT,
            "config_entry_id": entry.entry_id,
            "name": legacy_item.name,
            "content": legacy_content,
            "updated_at": updated_at,
        },
        {
            "type": WS_PREVIEW_APPLY_SNAPSHOT,
            "session_id": "11111111-1111-1111-1111-111111111111",
            "sequence": 2,
            "config_entry_id": entry.entry_id,
            "updated_at": updated_at,
            "name": legacy_item.name,
            "content": legacy_content,
        },
    ):
        await client.send_json_auto_id(payload)
        assert (await client.receive_json())["success"] is True

    assert "diy_code" not in application.async_apply_saved_effect.await_args.kwargs
    assert "diy_code" not in engine.async_apply_snapshot.await_args.kwargs
    assert "diy_code" not in preview.async_queue_snapshot.await_args.kwargs
