"""Device-scoped AA40 geometry through public Effect Studio paths."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import DOMAIN, EFFECT_FAMILY_MUSIC, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, ObservationConfidence
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase, PreviewWriteDisposition
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.effect_selector import compatible_saved_effects
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefault
from custom_components.ha_govee_led_ble.effect_websocket import (
    WS_APPLY,
    WS_APPLY_SNAPSHOT,
    WS_DEVICE,
    WS_TEMPLATE_DEFAULT_GET,
)
from custom_components.ha_govee_led_ble.effect_websocket_payloads import item_summary
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness, music_default_palette
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.music_commands import music_body_parameters, prepare_music_profile_writes
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from tests.test_effect_preview import _manager, _open
from tests.test_effect_websocket import _setup_backend
from tests.test_h6099_music import frame
from tests.test_music_commands import _music_transport as _transport


@contextmanager
def _music_transport(coordinator):
    async def refresh(**kwargs):
        # Fresh preflight replies, without turning optimistic writes into observations.
        if not kwargs.get("refresh_all"):
            return True
        for prefix in (f"aa01{int(coordinator.is_on):02x}", "aa0464", "aa0515000000"):
            coordinator._notify_callback(None, bytearray(frame(prefix)))
        return True

    async def segments(**kwargs):
        for group in range(1, 5):
            coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + "64ffffff" * 4)))
        return True

    with (
        _transport(coordinator) as physical,
        patch.object(coordinator, "refresh_state", AsyncMock(side_effect=refresh)),
        patch.object(coordinator, "async_refresh_segments", AsyncMock(side_effect=segments)),
    ):
        yield physical


def _item(kind):
    profile = replace(get_profile("H6099"), physical_ic_count=60)
    content = (
        resolve_catalogue_template("H6099", "template:paint", profile=profile).content
        if kind == "paint"
        else MusicProfile("H6099", "piano_keys", 42, parameters={"key_count": 18})
    )
    return LibraryItem.new("Device geometry", content)


def _device(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    coordinator.profile = replace(coordinator.profile, physical_ic_count=60)
    return coordinator


@pytest.mark.parametrize("kind", ["paint", "music"])
def test_compilation_and_saved_eligibility_are_device_scoped(kind):
    registry = get_profile("H6099")
    profile = replace(registry, physical_ic_count=60)
    item = _item(kind)
    compiled = compile_application(item, "H6099", profile=profile)
    assert compiled.physical_ic_count == 60
    assert compiled.progress_total > 1
    assert compatible_saved_effects((item,), "H6099", profile=profile) == (item,)
    assert compatible_saved_effects((item,), "H6099") == ()
    assert get_profile("H6099") is registry and registry.physical_ic_count is None
    assert item_summary(item)["model"] == "H6099"
    if kind == "music":
        with pytest.raises(TypeError):
            compiled.parameters["key_count"] = 20
        assert compiled_observation(compiled, profile=profile) == (
            {"is_on": True, "music_mode": "piano_keys", "music_sensitivity": 42},
            ObservationConfidence.MODE_MATCH,
        )


@pytest.mark.parametrize("kind", ["paint", "music"])
@pytest.mark.parametrize("saved", [False, True])
async def test_public_saved_and_snapshot_apply_use_effective_profile(hass, kind, saved):
    backend = await EffectBackend.async_create(hass)
    coordinator = _device(hass)
    item = _item(kind)
    compiled = compile_application(item, coordinator.model, profile=coordinator.profile)
    if saved:
        await backend.library.async_create(item)
    with (
        _music_transport(coordinator) as physical,
        patch.object(coordinator, "_encryption", None),
        patch.object(coordinator, "async_observe_effect", AsyncMock(return_value=True)),
    ):
        if saved:
            result = await backend.application.async_apply_saved_effect(
                backend.engine,
                coordinator,
                item_id=str(item.id),
                config_entry_id="entry-a",
                updated_at="2026-09-15T00:00:00Z",
                expected_version=1,
            )
        else:
            result = await backend.engine.async_apply_snapshot(
                coordinator,
                item,
                config_entry_id="entry-a",
                updated_at="2026-09-15T00:00:00Z",
            )
        assert result.phase is DeploymentPhase.CONFIRMED
        assert [call.args[1] for call in physical.await_args_list][-len(compiled.packets) :] == list(compiled.packets)
    assert coordinator._field_revisions == {
        "is_on": 1,
        "brightness_pct": 1,
        "color_mode": 1,
        "color_temp_kelvin": 1,
        "effect": 1,
        "segment_colors": 1,
        "segment_brightness": 1,
    }
    assert coordinator._domain_revisions == {
        ReadDomain.POWER: 1,
        ReadDomain.BRIGHTNESS: 1,
        ReadDomain.COLOUR_MODE: 1,
        ReadDomain.SEGMENTS: 4,
    }
    if kind == "music":
        assert coordinator.capture_effect_control_state().music_parameters == {"key_count": 18, "gradient": False}


@pytest.mark.parametrize("kind", ["paint", "music"])
@pytest.mark.parametrize("count", [None, 14])
@pytest.mark.parametrize("stage", ["refresh", "connect"])
async def test_committed_apply_fails_closed_when_geometry_changes(hass, kind, count, stage):
    backend = await EffectBackend.async_create(hass)
    coordinator = _device(hass)
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        refresh = coordinator.refresh_state.side_effect

        async def change(**kwargs):
            coordinator.profile = replace(coordinator.profile, physical_ic_count=count)
            return coordinator._client if stage == "connect" else await refresh(**kwargs)

        (coordinator.refresh_state if stage == "refresh" else coordinator._ensure_connected).side_effect = change
        with pytest.raises(ValueError, match="Physical IC count changed"):
            await backend.engine.async_apply_snapshot(
                coordinator,
                _item(kind),
                config_entry_id="entry-a",
                updated_at="2026-09-15T00:00:00Z",
            )
        physical.assert_not_awaited()
    assert backend.deployments.snapshot().records[-1].phase is DeploymentPhase.FAILED


@pytest.mark.parametrize("kind", ["paint", "music"])
@pytest.mark.parametrize("stage", ["unchanged", "preflight", "write"])
async def test_preview_rechecks_geometry_after_preflight_and_at_write(hass, monkeypatch, kind, stage):
    coordinator = _device(hass)
    events = []
    manager, _ = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session = _open(manager, owner, events)
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):

        async def preflight(**kwargs):
            if stage == "preflight":
                coordinator.profile = replace(coordinator.profile, physical_ic_count=None)

        async def connect():
            if stage == "write":
                coordinator.profile = replace(coordinator.profile, physical_ic_count=14)
            return coordinator._client

        monkeypatch.setattr(coordinator, "async_preview_preflight", AsyncMock(side_effect=preflight))
        monkeypatch.setattr(coordinator, "async_observe_effect", AsyncMock(return_value=True))
        coordinator._ensure_connected.side_effect = connect
        if stage == "write" and kind == "music":
            original_write = coordinator.async_preview_write

            async def changed_write(*args, **kwargs):
                coordinator.profile = replace(coordinator.profile, physical_ic_count=14)
                await original_write(*args, **kwargs)

            monkeypatch.setattr(coordinator, "async_preview_write", changed_write)
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-15T00:00:00Z",
            item=_item(kind),
        )
        await manager.async_wait_idle("entry-a")
        if stage == "unchanged":
            assert events[-1].phase is PreviewPhase.CONFIRMED
            assert physical.await_count > 2
        else:
            assert events[-1].phase is PreviewPhase.FAILED
            physical.assert_not_awaited()
            if stage == "preflight":
                assert events[-1].write_disposition is PreviewWriteDisposition.NOT_STARTED
    await manager.async_shutdown()


async def test_music_geometry_change_between_packets_stops_upload_without_observations(hass):
    coordinator = _device(hass)
    compiled = compile_application(_item("music"), coordinator.model, profile=coordinator.profile)
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):

        async def transmit(*args, **kwargs):
            coordinator.profile = replace(coordinator.profile, physical_ic_count=None)

        physical.side_effect = transmit
        with pytest.raises(ValueError, match="Physical IC count changed"):
            await async_apply_compiled_profile(coordinator, compiled)
        assert physical.await_count == 1
    assert coordinator.music_mode == "off"
    assert coordinator._field_revisions == {} and coordinator._domain_revisions == {}


async def test_selector_only_request_is_not_silently_expanded_after_aa40(hass):
    coordinator = _device(hass)
    compiled = compile_application(LibraryItem.new("Piano", MusicProfile("H6099", "piano_keys", 42)), "H6099")
    assert len(compiled.packets) == 2
    with _music_transport(coordinator) as physical:
        with pytest.raises(ValueError, match="Physical IC count changed"):
            await async_apply_compiled_profile(coordinator, compiled)
        physical.assert_not_awaited()


async def test_new_music_snapshot_is_captured_at_selector_not_companion(hass):
    coordinator = _device(hass)
    coordinator._pre_mode_snapshot = None
    compiled = compile_application(
        LibraryItem.new("Bloom", MusicProfile("H6099", "bloom", 42, calm=True)),
        "H6099",
        profile=coordinator.profile,
    )
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):

        async def transmit(_uuid, packet, **kwargs):
            if packet[0] == 0xA3:
                assert coordinator._pre_mode_snapshot is None
            if packet == compiled.packets[-2]:
                coordinator.rgb_color = (10, 20, 30)

        physical.side_effect = transmit
        await async_apply_compiled_profile(coordinator, compiled)
    assert coordinator._pre_mode_snapshot.rgb == (10, 20, 30)
    assert coordinator._field_revisions == {} and coordinator._domain_revisions == {}


@pytest.mark.parametrize("saved", [False, True])
async def test_websocket_apply_and_device_payload_use_aa40(hass, hass_ws_client, monkeypatch, saved):
    backend = await _setup_backend(hass)
    coordinator = _device(hass)
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        title="Device",
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WS_DEVICE, "config_entry_id": entry.entry_id})
    response = await client.receive_json()
    device = response["result"]["device"]
    assert device["physical_ic_count"] == 60 and device["segment_count"] == 14
    settings = device["music_settings"]
    assert settings["piano_keys"]["parameters"]["key_count"] == {
        "kind": "number",
        "default": 18,
        "min": 9,
        "max": 36,
        "options": [],
    }
    assert settings["rhythm"]["colour"] is True and settings["bloom"]["colour"] is False
    assert MODEL_EFFECT_CATALOGUES["H6099"].to_dict()["music_settings"]["piano_keys"]["parameters"] == {}
    await client.send_json_auto_id(
        {"type": WS_TEMPLATE_DEFAULT_GET, "config_entry_id": entry.entry_id, "template_id": "template:paint"}
    )
    response = await client.receive_json()
    assert len(response["result"]["content"]["segments"]) == 60
    item = _item("music")
    await backend.library.async_create(item)
    message = {"config_entry_id": entry.entry_id, "updated_at": "2026-09-15T00:00:00Z"}
    message.update(
        {"type": WS_APPLY, "item_id": str(item.id), "expected_version": 1}
        if saved
        else {"type": WS_APPLY_SNAPSHOT, "name": item.name, "content": effect_content_to_dict(item.content)}
    )
    with (
        _music_transport(coordinator) as physical,
        patch.object(coordinator, "_encryption", None),
        patch.object(coordinator, "async_observe_effect", AsyncMock(return_value=True)),
    ):
        await client.send_json_auto_id(message)
        response = await client.receive_json()
        assert response["success"] is True, response
        assert response["result"]["deployment"]["phase"] == "confirmed"
        assert physical.await_count == 4


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("reconnect", [False, True])
async def test_light_selector_and_template_default_guard_geometry(hass, saved, reconnect):
    backend = await EffectBackend.async_create(hass)
    coordinator = _device(hass)
    coordinator.effect_families = frozenset({EFFECT_FAMILY_MUSIC})
    item = _item("music")
    if saved:
        await backend.library.async_create(item)
    else:
        await backend.template_defaults.async_set(
            CatalogueTemplateDefault(
                config_entry_id="entry-a",
                model="H6099",
                template_id="template:music:piano_keys",
                updated_at="2026-09-15T00:00:00Z",
                content=item.content,
            )
        )
    light = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)
    light.hass = hass
    light.async_write_ha_state = lambda: None
    name = item.name if saved else "Music: Piano Keys"
    if saved:
        assert item.name in light.effect_list
    with (
        _music_transport(coordinator) as physical,
        patch.object(coordinator, "_encryption", None),
        patch.object(coordinator, "async_observe_effect", AsyncMock(return_value=True)),
    ):
        coordinator.refresh_state.return_value = True
        if reconnect:

            async def connect():
                coordinator.profile = replace(coordinator.profile, physical_ic_count=None)
                return coordinator._client

            coordinator._ensure_connected.side_effect = connect
            with pytest.raises(HomeAssistantError):
                await light.async_turn_on(effect=name)
            physical.assert_not_awaited()
        else:
            await light.async_turn_on(effect=name)
            assert coordinator.music_piano_key_count == 18
            assert physical.await_count >= 4


@pytest.mark.parametrize("parameters_only", [False, True])
async def test_native_music_rechecks_count_at_connection(hass, parameters_only):
    coordinator = _device(hass)
    coordinator.music_mode = "piano_keys"
    coordinator._music_palette = ("piano_keys", music_default_palette(music_variant(coordinator.profile, 0x34)))
    compiled = compile_application(_item("music"), coordinator.model, profile=coordinator.profile)
    coordinator._music_body = prepare_music_profile_writes(
        "H6099", "piano_keys", 42, None, False, compiled.parameters, profile=coordinator.profile
    )[-2][1]["_music_body"]
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):

        async def connect():
            coordinator.profile = replace(coordinator.profile, physical_ic_count=None)
            return coordinator._client

        coordinator._ensure_connected.side_effect = connect
        with pytest.raises(ValueError, match="Physical IC count changed"):
            if parameters_only:
                await coordinator.async_apply_music_params(0x34, parameters={"key_count": 20})
            else:
                await coordinator.async_select_music_slug("piano_keys")
        physical.assert_not_awaited()


async def test_recovery_uses_device_scoped_music_parameters(hass):
    coordinator = _device(hass)
    compiled = compile_application(_item("music"), coordinator.model, profile=coordinator.profile)
    body = prepare_music_profile_writes(
        "H6099", "piano_keys", 42, None, False, compiled.parameters, profile=coordinator.profile
    )[-2][1]["_music_body"][1]
    state = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="piano_keys",
        music_sensitivity=42,
        music_parameters={"key_count": 18, "gradient": False},
        music_palette=music_default_palette(music_variant(coordinator.profile, 0x34)),
        music_body=body,
    )
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        coordinator.refresh_state.return_value = True
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert [call.args[1] for call in physical.await_args_list] == [
            build_brightness(state.brightness_pct, "H6099"),
            *compiled.packets,
        ]
    assert coordinator.music_body == body
    assert music_body_parameters(body, "piano_keys", profile=coordinator.profile) == {
        "key_count": 18,
        "gradient": False,
    }
    assert coordinator._field_revisions == {} and coordinator._domain_revisions == {}
