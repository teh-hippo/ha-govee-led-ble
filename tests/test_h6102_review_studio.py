"""Issue 115 review: real Studio admission and retained-body editing endpoints."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.ha_govee_led_ble.const import DOMAIN, device_profile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template, validate_native_diy
from custom_components.ha_govee_led_ble.effect_compiler import compile_music_profile
from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_websocket_payloads import retained_music_edit
from custom_components.ha_govee_led_ble.layered_scene import AppliedArea, Selection
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import fragment_a3
from tests.test_effect_websocket import _setup_backend
from tests.test_music_commands import _music_transport

BODY = bytes.fromhex("3302010203040506aabbcc196104050708")


def _coordinator(hass, *, resolved=True):
    coordinator = GoveeBLECoordinator(
        hass, "AA:BB:CC:DD:EE:FF", "H6102", configuration_url=None, h6102_pact="10/1" if resolved else None
    )
    coordinator.fw_version, coordinator.hw_version = "3.02.02", "3.02.01"
    coordinator._resolve_device_profile()
    return coordinator


def _entry(hass, monkeypatch, coordinator):
    entry = SimpleNamespace(entry_id="h6102", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    return entry


async def test_native_preview_rejects_unresolved_profile_before_accept(hass, hass_ws_client, monkeypatch):
    backend = await _setup_backend(hass)
    coordinator = _coordinator(hass, resolved=False)
    _entry(hass, monkeypatch, coordinator)
    accept = AsyncMock()
    monkeypatch.setattr(backend.preview, "_async_accept", accept)
    scene = SCENE_ENTRIES["H6102"][0]
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/editor/preview/apply_scene",
            "session_id": str(uuid4()),
            "sequence": 1,
            "config_entry_id": "h6102",
            "updated_at": "2026-09-17T00:00:00Z",
            "scene_id": scene.scene_id,
            "effect_id": scene.effect_id,
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert "native scenes are not supported" in response["error"]["message"]
    accept.assert_not_awaited()


@pytest.mark.parametrize(
    "sizes,valid",
    [
        ((1, 1, 1), False),
        ((1, 2, 1), False),
        ((1, 2, 2), True),
        ((1, 3, 2), True),
        ((1, 4, 4), True),
        ((1, 5, 4), False),
        ((2, 2, 2), False),
        ((1, 1, 3), False),
    ],
)
def test_colorful_exact_aggregate_and_layer_structure(sizes, valid):
    content = resolve_catalogue_template("H6102", "template:native-diy:501").content
    assert isinstance(content, LayeredEffect)
    edited = replace(
        content,
        layers=tuple(
            replace(layer, palette=((1, 2, 3),) * count) for layer, count in zip(content.layers, sizes, strict=True)
        ),
    )
    if valid:
        validate_native_diy(edited, "H6102", get_profile("H6102"))
    else:
        with pytest.raises(ValueError, match="palette group"):
            validate_native_diy(edited, "H6102", get_profile("H6102"))


@pytest.mark.parametrize("selector", range(501, 508))
def test_native_templates_satisfy_qualified_bounds_without_geometry(selector):
    content = resolve_catalogue_template("H6102", f"template:native-diy:{selector}").content
    assert isinstance(content, LayeredEffect)
    assert not validate_native_diy(content, "H6102", get_profile("H6102"))
    donor = resolve_catalogue_template("H617A", f"template:native-diy:{selector}").content
    assert isinstance(donor, LayeredEffect)
    assert not validate_native_diy(donor, "H617A", get_profile("H617A"))


@pytest.mark.parametrize("selector,index,count", [(502, 0, 8), (504, 0, 8), (505, 1, 2), (506, 0, 8)])
def test_other_apk_palette_groups_reject_out_of_bounds(selector, index, count):
    content = resolve_catalogue_template("H6102", f"template:native-diy:{selector}").content
    assert isinstance(content, LayeredEffect)
    layers = list(content.layers)
    layers[index] = replace(layers[index], palette=((1, 2, 3),) * count)
    with pytest.raises(ValueError, match="palette group"):
        validate_native_diy(replace(content, layers=tuple(layers)), "H6102", get_profile("H6102"))


@pytest.mark.parametrize(
    "sizes,valid",
    [
        ((1, 1), True),
        ((2, 1), True),
        ((4, 4), True),
        ((8, 8), False),
        ((1, 7), False),
        ((5, 4), False),
        ((1, 2), False),
    ],
)
def test_bloom_two_way_moving_palette_bounds(sizes, valid):
    content = resolve_catalogue_template("H6102", "template:native-diy:506").content
    assert isinstance(content, LayeredEffect)
    edited = replace(
        content,
        layers=(
            *content.layers[:2],
            *(
                replace(layer, palette=((1, 2, 3),) * size)
                for layer, size in zip(content.layers[2:], sizes, strict=True)
            ),
        ),
    )
    if valid:
        assert not validate_native_diy(edited, "H6102", get_profile("H6102"))
    else:
        with pytest.raises(ValueError, match="palette group"):
            validate_native_diy(edited, "H6102", get_profile("H6102"))


@pytest.mark.parametrize("direction", [0, 2])
@pytest.mark.parametrize("size,valid", [(1, False), (2, True), (8, True), (9, False)])
def test_bloom_one_way_active_palette_excludes_black_inactive_layer(direction, size, valid):
    content = resolve_catalogue_template("H6102", "template:native-diy:506").content
    assert isinstance(content, LayeredEffect)
    moving = tuple(
        replace(
            layer,
            area=AppliedArea(0, 0),
            selection=Selection(1, 0, 60 if index == 0 else 1),
            selected_movement=replace(layer.selected_movement, direction=direction),
            palette=((1, 2, 3),) * size if index == 0 else ((0, 0, 0),),
        )
        for index, layer in enumerate(content.layers[2:])
    )
    edited = replace(content, layers=(*content.layers[:2], *moving))
    profile = replace(get_profile("H6102"), physical_ic_count=60)
    if valid:
        assert validate_native_diy(edited, "H6102", profile)
        with pytest.raises(ValueError, match="known physical IC"):
            validate_native_diy(edited, "H6102", get_profile("H6102"))
        invalid = replace(edited, layers=(*edited.layers[:3], replace(moving[1], palette=((1, 0, 0),))))
        with pytest.raises(ValueError, match="inactive layer"):
            validate_native_diy(invalid, "H6102", profile)
    else:
        with pytest.raises(ValueError, match="palette group"):
            validate_native_diy(edited, "H6102", profile)


@pytest.mark.parametrize("change", ["area", "direction", "quantity", "enabled"])
def test_bloom_rejects_inconsistent_direction_topology(change):
    content = resolve_catalogue_template("H6102", "template:native-diy:506").content
    assert isinstance(content, LayeredEffect)
    layer = content.layers[3]
    if change == "area":
        layer = replace(layer, area=AppliedArea(0, 0))
    elif change == "direction":
        layer = replace(layer, selected_movement=replace(layer.selected_movement, direction=0))
    elif change == "quantity":
        layer = replace(layer, selection=Selection(1, 0, 60))
    else:
        layer = replace(layer, selected_movement=replace(layer.selected_movement, enabled=False))
    with pytest.raises(ValueError, match="direction topology"):
        validate_native_diy(
            replace(content, layers=(*content.layers[:3], layer)),
            "H6102",
            replace(get_profile("H6102"), physical_ic_count=60),
        )


@pytest.mark.parametrize("failure", [None, "stale", "unknown", "geometry", "during_write"])
async def test_retained_music_actual_endpoint_preserves_companions(hass, hass_ws_client, monkeypatch, failure):
    await _setup_backend(hass)
    coordinator = _coordinator(hass)
    _entry(hass, monkeypatch, coordinator)
    coordinator.music_mode = "hopping"
    coordinator._music_body = ("hopping", BODY)
    edit = retained_music_edit(coordinator)
    assert edit is not None and "relative_brightness" in edit["settings"]["parameters"]
    assert coordinator.profile.physical_ic_count is None
    parameters = {"relative_brightness": 17}
    if failure == "geometry":
        parameters = {"direction": "two_way"}
    if failure == "unknown":
        coordinator._music_body = None
    client = await hass_ws_client(hass)
    with _music_transport(coordinator) as physical:
        if failure == "during_write":

            async def change_body(*args, **kwargs):
                coordinator._music_body = None

            physical.side_effect = change_body
        await client.send_json_auto_id(
            {
                "type": f"{DOMAIN}/editor/music/edit_retained",
                "config_entry_id": "h6102",
                "mode": "hopping",
                "expected_body_revision": edit["revision"] - (failure == "stale"),
                "parameters": parameters,
            }
        )
        response = await client.receive_json()
        if failure is None:
            assert response["success"], response
            changed = bytes.fromhex("3302010203040506aabbcc116104050708")
            assert [call.args[1] for call in physical.await_args_list] == fragment_a3(0x41, changed)
            assert coordinator.music_body == changed
            assert response["result"]["retained_music_edit"]["parameters"]["relative_brightness"] == 17
        else:
            assert not response["success"], response
            assert physical.await_count == (1 if failure == "during_write" else 0)


def test_fresh_geometry_authoring_stays_gated():
    profile = device_profile("H6102", 10, 1, hardware="3.02.01", firmware="3.02.02")
    with pytest.raises(ValueError, match="unavailable"):
        compile_music_profile(
            LibraryItem.new("Fresh", MusicProfile("H6102", "hopping", 50, parameters={"relative_brightness": 17})),
            "H6102",
            profile=profile,
        )


async def test_retained_piano_endpoint_allows_gradient_but_rejects_key_count(hass, hass_ws_client, monkeypatch):
    await _setup_backend(hass)
    coordinator = _coordinator(hass)
    _entry(hass, monkeypatch, coordinator)
    coordinator.music_mode = "piano_keys"
    body = bytes.fromhex("3402010203040506000f0a0407")
    coordinator._music_body = ("piano_keys", body)
    client = await hass_ws_client(hass)
    with _music_transport(coordinator) as physical:
        for parameters, success in (({"key_count": 12}, False), ({"gradient": True}, True)):
            await client.send_json_auto_id(
                {
                    "type": f"{DOMAIN}/editor/music/edit_retained",
                    "config_entry_id": "h6102",
                    "mode": "piano_keys",
                    "expected_body_revision": coordinator._music_body_revision,
                    "parameters": parameters,
                }
            )
            response = await client.receive_json()
            assert response["success"] is success, response
            if not success:
                physical.assert_not_awaited()
        assert coordinator.music_body == bytes.fromhex("3402010203040506010f0a0407")
