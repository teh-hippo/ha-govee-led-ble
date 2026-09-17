"""Foreground qualification waits for the real background reconnect's identity replies."""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent, async_control_intent
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, VideoProfile, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, async_apply_compiled_profile
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefault
from custom_components.ha_govee_led_ble.effect_websocket import ws_apply, ws_apply_snapshot
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_colour_mode_query,
    build_firmware_query,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import (
    apply_active_video_mode,
    apply_blank_screen,
    apply_relative_brightness,
    apply_white_balance,
    async_require_video_controls,
)
from custom_components.ha_govee_led_ble.select import GoveeBLEControlSelect
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_effect_preview import _manager, _open
from tests.test_h6199_capabilities import QUALIFIED
from tests.test_h6199_capabilities import lifecycle as reconnect_lifecycle  # noqa: F401
from tests.test_h6199_native_controls import frame


@pytest.mark.parametrize("identity", ["qualified", "missing", "mismatched"])
@pytest.mark.parametrize(
    "route",
    [
        "select",
        "register",
        "mode",
        "white",
        "relative",
        "blank",
        "compiled",
        "apply",
        "preview",
        "light_saved",
        "light_default",
        "service_name",
        "service_id",
        "ws_saved",
        "ws_snapshot",
    ],
)
async def test_background_reconnect_admission(reconnect_lifecycle, hass, monkeypatch, route, identity):  # noqa: F811
    c, replies, clients, packets = reconnect_lifecycle
    vars(c).update(QUALIFIED)
    replies[build_colour_mode_query("H6199")] = frame("aa05000100640164")
    if identity == "missing":
        del replies[build_firmware_query("H6199")]
    elif identity == "mismatched":
        replies[build_firmware_query("H6199")] = frame("aa06" + b"1.00.01".hex())
    connecting, release = asyncio.Event(), asyncio.Event()
    connect = coordinator_module.async_establish_ble_connection

    async def paused_connect(*args, **kwargs):
        connecting.set()
        await release.wait()
        return await connect(*args, **kwargs)

    monkeypatch.setattr(coordinator_module, "async_establish_ble_connection", paused_connect)
    item = LibraryItem.new("Video", VideoProfile("H6199", "movie", True, 100, True, 100, None, None, None))
    manager, _ = await _manager(hass, monkeypatch, c, connect_timeout=1)
    owner, statuses = object(), []
    session = _open(manager, owner, statuses)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    writer = AsyncMock()
    if route.startswith(("light_", "service_", "ws_")):
        backend = await EffectBackend.async_create(hass)
        await backend.library.async_create(item)
        light = GoveeBLELight(c, config_entry_id="entry-a", effect_backend=backend)
        light.async_write_ha_state = Mock()
        if route == "light_default":
            await backend.template_defaults.async_set(
                CatalogueTemplateDefault(
                    config_entry_id="entry-a",
                    model=c.model,
                    template_id="template:video:movie",
                    content=item.content,
                    updated_at="2026-09-16T00:00:00Z",
                )
            )
        monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_websocket._backend", lambda _: backend)

    async def request():
        if route in ("light_saved", "light_default"):
            await light.async_turn_on(effect=item.name if route == "light_saved" else "Video: Movie")
        elif route == "service_name":
            await light.async_apply_custom_effect(effect=item.name)
        elif route == "service_id":
            await light.async_apply_custom_effect(effect_id=str(item.id))
        elif route.startswith("ws_"):
            connection = Mock()
            message = {"id": 1, "config_entry_id": "entry-a", "updated_at": "2026-09-16T00:00:00Z"}
            if route == "ws_saved":
                message.update(item_id=str(item.id), expected_version=item.version)
                handler = ws_apply
            else:
                message.update(name=item.name, content=effect_content_to_dict(item.content))
                handler = ws_apply_snapshot
            await inspect.unwrap(handler)(hass, connection, message)
            if connection.send_error.called:
                raise ValueError(connection.send_error.call_args.args)
            connection.send_result.assert_called_once()
        elif route == "select":
            entity = GoveeBLEControlSelect(SimpleNamespace(runtime_data=c, entry_id="entry-a"), "camera_position")
            entity.hass = hass
            monkeypatch.setattr("custom_components.ha_govee_led_ble.select.get_effect_backend", lambda _: None)
            await entity.async_select_option("bottom")
        elif route == "register":
            await c.async_set_h6199_control("camera_position", 1)
        elif route == "mode":
            await apply_active_video_mode(
                c, mode="movie", requested_values={"sound_effects": True}, writer=writer, verify=False
            )
        elif route == "white":
            await apply_white_balance(c, (21, 5), writer=writer, verify=False)
        elif route == "relative":
            await apply_relative_brightness(c, (80, 80, 80, 80), writer=writer, verify=False)
        elif route == "blank":
            await apply_blank_screen(c, False, policy=(2, 10, 120), writer=writer, verify=False)
        elif route == "compiled":
            await async_apply_compiled_profile(c, compile_video_profile(item, c.model), writer=writer, verify=False)
        elif route == "apply":
            await EffectDeploymentEngine(repository).async_apply_snapshot(
                c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z"
            )
        else:
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-09-16T00:00:00Z",
                item=item,
            )
            await manager.async_wait_idle("entry-a")
            assert statuses[-1].phase is not PreviewPhase.FAILED

    background = asyncio.create_task(c._async_update_data())
    foreground = None
    try:
        await asyncio.wait_for(connecting.wait(), 1)
        assert c._connection_initializing and c.fw_version is None
        foreground = asyncio.create_task(request())
        await asyncio.sleep(0.01)
        assert not foreground.done()
        assert not packets and not writer.await_count
        release.set()
        await background
        if identity == "qualified":
            await asyncio.wait_for(foreground, 3)
            assert writer.await_count or any(packet[0] == 0x33 for packet in packets)
        else:
            with pytest.raises((ValueError, HomeAssistantError)):
                await asyncio.wait_for(foreground, 3)
            assert not any(packet[0] == 0x33 for packet in packets)
            writer.assert_not_awaited()
    finally:
        release.set()
        for task in (background, foreground):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (background, foreground) if task is not None), return_exceptions=True)
        await manager.async_shutdown()
        if route.startswith(("light_", "service_", "ws_")):
            await backend.preview.async_shutdown()


async def test_qualification_wait_cancels_without_writes_or_stale_fallback(reconnect_lifecycle):  # noqa: F811
    c, _, _, packets = reconnect_lifecycle
    vars(c).update(QUALIFIED)
    async with async_control_intent(c, ControlIntent.BACKGROUND):
        c.fw_version = None
        task = asyncio.create_task(apply_white_balance(c, (21, 5)))
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert c._control_arbiter.current_task_intent is ControlIntent.BACKGROUND
    assert not packets and not c._control_arbiter.locked()
    with pytest.raises(ValueError, match="evidence_gap"):
        await async_require_video_controls(c, ("white_balance",))


async def test_structurally_invalid_register_fails_without_waiting(reconnect_lifecycle):  # noqa: F811
    c, _, _, packets = reconnect_lifecycle
    async with async_control_intent(c, ControlIntent.BACKGROUND):
        task = asyncio.create_task(c.async_set_h6199_control("gradient", 2))
        with pytest.raises(ValueError, match="integer 0 or 1"):
            await asyncio.wait_for(task, 0.1)
        task = asyncio.create_task(apply_white_balance(c, (21, 5), flag=255))
        with pytest.raises(ValueError, match="known auto/manual flag"):
            await asyncio.wait_for(task, 0.1)
    assert not packets
