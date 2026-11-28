"""Configured-string geometry for H7020 native catalogue scenes."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble import coordinator_base as coordinator_base_module
from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_base import async_prepare_effect_profile
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import (
    compile_effect,
    validate_compiled_geometry,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, LibraryItem
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    async_prepare_application,
)
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_configured_strings_query
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef, SelectionType
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_layered_scene
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3
from tests.coordinator_test_support import _packet
from tests.storage_test_double import InMemoryVersionedDocumentStore


def _scene(name: str):
    return next(entry for entry in SCENE_ENTRIES["H7020"] if entry.display_name == name)


def _scene_content(name: str) -> BuiltinScene:
    entry = _scene(name)
    return BuiltinScene(CatalogueRef("H7020", entry.scene_id, entry.effect_id))


def _decoded_upload(packets: list[bytes]):
    envelope = reassemble_a3(packets[:-1])
    assert envelope[2] == 2
    return decode_layered_scene(CatalogueRef("H7020", 0, 0), envelope[3:])


def _assert_geometry(layer, count: int) -> None:
    if layer.selection.type in {SelectionType.SEGMENT, SelectionType.CONTINUOUS}:
        assert layer.selection.quantity <= count
        assert layer.selection.quantity != 50
    elif layer.selection.type == SelectionType.RANDOM:
        assert layer.selection.param_1 <= count
        assert layer.selection.param_2 <= count
    elif layer.selection.type == SelectionType.CUSTOM:
        assert layer.selection.param_1 <= count
        assert layer.selection.param_2 <= count
    assert layer.selected_movement.distance <= count - 2
    assert layer.overall_movement.distance <= count - 2


@pytest.fixture
async def h7020(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7020", configuration_url=None)
    coordinator.pact_type = coordinator.pact_code = 1
    coordinator._resolve_device_profile()
    client = MagicMock(
        is_connected=True,
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    await coordinator._start_notify()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 1)
    yield coordinator, client, client.start_notify.call_args.args[1]
    await coordinator.disconnect()


@pytest.mark.parametrize(
    ("name", "count", "expected"),
    [
        ("Party", 15, ((1, 0, 15, 0, 8), (1, 0, 15, 0, 1), (1, 0, 15, 0, 0), (2, 15, 1, 0, 0))),
        ("Party", 30, ((1, 0, 30, 0, 8), (1, 0, 30, 0, 1), (1, 0, 30, 0, 0), (2, 25, 1, 0, 0))),
        ("Moonlight", 15, ((2, 14, 6, 0, 0), (1, 0, 15, 0, 0))),
        ("Moonlight", 30, ((2, 14, 6, 0, 0), (1, 0, 30, 0, 0))),
        ("Candy", 15, ((1, 0, 15, 0, 8), (1, 0, 15, 0, 1), (1, 0, 15, 0, 0), (2, 15, 1, 0, 0))),
        ("Candy", 30, ((1, 0, 30, 0, 8), (1, 0, 30, 0, 1), (1, 0, 30, 0, 0), (2, 25, 1, 0, 0))),
    ],
)
def test_h7020_catalogue_bodies_use_exact_configured_geometry(name, count, expected):
    profile = replace(get_profile("H7020"), physical_ic_count=count, segment_count=count)
    scene = _scene(name)

    prepared = _decoded_upload(build_native_scene_packets("H7020", scene, profile=profile))

    actual = tuple(
        (
            layer.selection.type,
            layer.selection.param_1,
            layer.selection.param_2,
            layer.selected_movement.distance,
            layer.overall_movement.distance,
        )
        for layer in prepared.effect.layers
    )
    assert actual == expected


async def test_saved_resident_scene_does_not_read_configured_layout(hass, h7020, monkeypatch):
    coordinator, _client, _receive = h7020
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._pact_identity.marker_pact = (1, 1)
    item = LibraryItem.new("Saved Ripple", _scene_content("Ripple"))
    backend = MagicMock(spec=EffectBackend)
    backend.application.library_snapshot.return_value = LibrarySnapshot((item,))
    backend.active_workspaces.get.return_value = None
    light = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)
    light._library_snapshot = LibrarySnapshot((item,))
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    apply = AsyncMock()
    monkeypatch.setattr(light, "_async_apply_saved_item", apply)
    read_layout = AsyncMock(side_effect=AssertionError("resident scene unexpectedly required configured layout"))
    monkeypatch.setattr(coordinator, "_read_configured_strings", read_layout)

    await light._async_handle_turn_on(effect=item.name)

    apply.assert_awaited_once()
    read_layout.assert_not_awaited()


@pytest.mark.parametrize("count", [15, 30])
def test_h7020_speed_packets_are_prepared_after_speed_application(count):
    scene = _scene("Party")
    assert scene.speed is not None
    speed_index = 0
    profile = replace(get_profile("H7020"), physical_ic_count=count, segment_count=count)

    default = build_native_scene_packets("H7020", scene, speed_index=scene.speed.default_index, profile=profile)
    speed = build_native_scene_packets("H7020", scene, speed_index=speed_index, profile=profile)
    prepared = _decoded_upload(speed)

    assert speed != default
    for layer in prepared.effect.layers:
        _assert_geometry(layer, count)


async def test_h7020_scene_preparation_fails_closed_when_count_query_fails(h7020, monkeypatch):
    coordinator, client, _receive = h7020
    monkeypatch.setattr(coordinator_base_module, "STATE_QUERY_TIMEOUT", 0.01)

    with pytest.raises(ValueError, match="configured bulb layout"):
        await async_prepare_effect_profile(coordinator, intent=ControlIntent.APPLY, content=_scene_content("Party"))

    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.await_args.args[1] == build_configured_strings_query(coordinator.profile)


async def test_h7020_reconnect_invalidates_cached_configured_count(h7020):
    coordinator, client, _receive = h7020
    coordinator._apply_configured_strings(2)
    coordinator._configured_strings_confirmed = True
    compiled = compile_effect(
        LibraryItem.new("Party", _scene_content("Party")),
        "H7020",
        profile=coordinator.effect_authorization_profile,
    )

    coordinator._clear_client_state(client)
    coordinator._client = client
    client.is_connected = True

    assert coordinator.configured_strings == 2
    assert not coordinator._configured_strings_confirmed
    with pytest.raises(ValueError, match="Physical IC count changed"):
        validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)


async def test_h7020_rejects_layout_change_during_scene_transfer(h7020, monkeypatch):
    coordinator, client, receive = h7020
    coordinator.is_on = True
    scene = _scene("Party")
    scene_packets = 0
    baseline = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=23,
        rgb_color=(17, 34, 51),
        static_rgb_known=True,
        segment_colors=((17, 34, 51),) * 30,
        segment_brightness=(23,) * 30,
        segment_kelvin=(0,) * 30,
    )
    monkeypatch.setattr(coordinator, "async_prepare_static_baseline", AsyncMock(return_value=baseline))

    async def write(_uuid, packet, **_kwargs):
        nonlocal scene_packets
        if packet == build_configured_strings_query(coordinator.profile):
            receive(None, bytearray(_packet(0xAA, 0x0F, [1])))
        elif packet[0] == 0xA3:
            scene_packets += 1
            if scene_packets == 1:
                receive(None, bytearray(_packet(0xAA, 0x0F, [2])))

    client.write_gatt_char.side_effect = write

    with pytest.raises(ValueError, match="geometry changed|profile changed"):
        await coordinator.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)

    assert scene_packets == 1
    assert coordinator.profile.physical_ic_count == 30
    activation = build_native_scene_packets("H7020", scene, profile=replace(coordinator.profile, physical_ic_count=15))[
        -1
    ]
    assert activation not in [call.args[1] for call in client.write_gatt_char.await_args_list]


async def test_h7020_prepared_light_scene_revalidates_before_leading_brightness(h7020):
    coordinator, client, receive = h7020
    coordinator.is_on = True

    async def write(_uuid, packet, **_kwargs):
        if packet == build_configured_strings_query(coordinator.profile):
            receive(None, bytearray(_packet(0xAA, 0x0F, [1])))

    client.write_gatt_char.side_effect = write
    light = GoveeBLELight(coordinator)
    guards = []
    prepared = await light._prepare_effect("Party", effect_guards=guards)
    prepared_generation = coordinator._profile_generation
    client.write_gatt_char.reset_mock()

    coordinator._notification_token = object()
    coordinator._configured_strings_confirmed = False
    assert coordinator._profile_generation == prepared_generation

    with pytest.raises(ValueError, match="geometry authority changed"):
        await light._async_turn_on(
            prepared_effect=prepared,
            effect_write_guard=guards[0],
            brightness=128,
        )

    client.write_gatt_char.assert_not_awaited()
    assert coordinator.brightness_pct != 50


async def test_h7020_studio_rejects_old_subscription_at_same_geometry(h7020):
    coordinator, client, receive = h7020

    async def write(_uuid, packet, **_kwargs):
        if packet == build_configured_strings_query(coordinator.profile):
            receive(None, bytearray(_packet(0xAA, 0x0F, [1])))

    client.write_gatt_char.side_effect = write
    item = LibraryItem.new("Party", _scene_content("Party"))
    compiled = await async_prepare_application(coordinator, item)
    assert compiled.physical_ic_count == 15
    assert compiled.scene_geometry_authority is not None
    original_token = coordinator._notification_token
    coordinator._notification_token = object()
    assert coordinator._notification_token is not original_token
    assert coordinator.configured_strings == 1
    assert coordinator._configured_strings_confirmed

    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    with pytest.raises(ValueError, match="authority changed since compilation"):
        await engine.async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-11-27T00:00:00Z",
            compiled=compiled,
        )

    assert coordinator.control_write_attempts == 0


@pytest.mark.parametrize("current_count", [15, 30])
def test_h7020_prepared_scene_rejects_stale_geometry(current_count):
    prepared = replace(get_profile("H7020"), physical_ic_count=15, segment_count=15)
    compiled = compile_effect(
        LibraryItem.new("Party", _scene_content("Party")),
        "H7020",
        profile=prepared,
    )
    current = replace(get_profile("H7020"), physical_ic_count=current_count, segment_count=current_count)

    if current_count == 15:
        validate_compiled_geometry(compiled, current)
        with pytest.raises(ValueError, match="RGBIC scene format changed"):
            validate_compiled_geometry(replace(compiled, rgbic_scene_v0=None), current)
    else:
        with pytest.raises(ValueError, match="Physical IC count changed"):
            validate_compiled_geometry(compiled, current)


def test_h7020_native_diy_packets_ignore_scene_geometry():
    source = resolve_catalogue_template("H7020", "template:native-diy:17").content
    item = LibraryItem.new("Spin", source)
    plain = replace(
        get_profile("H7020"),
        physical_ic_count=None,
        configured_string_scene_geometry=False,
    )
    installed = replace(
        get_profile("H7020"),
        physical_ic_count=15,
        segment_count=15,
        configured_string_scene_geometry=True,
    )

    assert (
        compile_effect(item, "H7020", diy_code=321, profile=installed).packets
        == compile_effect(item, "H7020", diy_code=321, profile=plain).packets
    )
