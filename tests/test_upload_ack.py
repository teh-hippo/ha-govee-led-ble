"""Software-only A3 ACK barrier faults; no radio or device-state proof."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import ModeTransitionSupersededError
from custom_components.ha_govee_led_ble.coordinator_upload import PendingUploadAck
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import WORKSHOP_PROTOCOL_FIXTURES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import DIY_ACK_EVIDENCE, compile_application, compile_effect
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    EffectPair,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    PaletteDiyEffect,
    RetainedSceneEffect,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_diy_activation,
    build_music_mode,
    build_power,
    build_scene_activation,
    parse_command_ack_result,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_workshop_effect
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.protocol_effect_bodies import A3Sequence
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import fragment_a3, fragment_a3_envelope, reassemble_a3
from tests.coordinator_test_support import approve_diy_destination_operation, frame
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_effect_preview import _manager, _open

MUSIC_OK = frame("a3413000")
MUSIC_NO = frame("a3413001")
DIY_OK = frame("a30200")
DIY_NO = frame("a30201")


@pytest.fixture
async def connected(hass, monkeypatch, request):
    model = getattr(request, "param", "H617A")
    model, pact = model if isinstance(model, tuple) else (model, 1 if model in {"H6139", "H6159"} else 2)
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    if c.model in {"H6097", "H6046", "H6053"}:
        c.pact_type, c.pact_code = pact, 1
        c._resolve_device_profile()
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    await c._start_notify()
    if c.model in {"H617A", "H617C", "H617E", "H617F"}:
        c._note_identity(fw_version="3.02.24", hw_version="3.01.01")
        c._observe_identity_field("fw_version", c.fw_version)
        c._observe_identity_field("hw_version", c.hw_version)
    if c.model == "H6053":
        c._observe_pact(pact, 1)
        c._observe_identity_field("fw_version", "1.08.05")
        c._observe_identity_field("hw_version", "1.00.00")
    if c.model == "H6199":
        c._observe_pact(2, 1)
        c._observe_identity_field("fw_version", "1.10.04")
        c._observe_identity_field("hw_version", "3.02.01")
    if c.model == "H6102":
        c._observe_pact(1, 1)
        c._observe_identity_field("fw_version", "1.01.20")
        c._observe_identity_field("hw_version", "1.00.02")
    if c.model in {"H6139", "H6159"}:
        c._observe_pact(pact, 1)
        c._observe_identity_field("fw_version", "1.07.02")
        c._observe_identity_field("hw_version", "1.00.01")
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.02)
    if c.model not in {"H600A", "H6097", "H7025", "H6046"}:
        monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 1)
    monkeypatch.setattr(coordinator_module, "RETRY_BACKOFF_SECONDS", 0)

    async def disconnect(*, planned_release=False):
        client.is_connected = False
        await client.disconnect()
        c._clear_client_state(c._client, preserve_static_baseline=planned_release)

    monkeypatch.setattr(c, "_disconnect_locked", AsyncMock(side_effect=disconnect))

    async def reconnect():
        if c._client is not client or not client.is_connected:
            firmware, hardware = c.fw_version, c.hw_version
            pact_type, pact_code = c.pact_type, c.pact_code
            client.is_connected = True
            c._client = client
            await c._start_notify()
            if pact_type is not None and pact_code is not None:
                c._observe_pact(pact_type, pact_code)
            if firmware is not None:
                c._observe_identity_field("fw_version", firmware)
            if hardware is not None:
                c._observe_identity_field("hw_version", hardware)
        return client

    c._ensure_connected.side_effect = reconnect
    yield c, client
    if c._cancel_disconnect:
        c._cancel_disconnect()


@pytest.fixture
def selection_ready(connected, monkeypatch):
    """Keep ACK/identity faults independent of static recovery acquisition."""
    c, _ = connected
    if c.model == "H6199":
        c.diy_code = 73
    baseline = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=23,
        rgb_color=(17, 34, 51),
        static_rgb_known=True,
        left_bar_enabled=True if "left_bar_enabled" in c.profile.boolean_controls else None,
        right_bar_enabled=True if "right_bar_enabled" in c.profile.boolean_controls else None,
        segment_colors=((17, 34, 51),) * c.profile.segment_count if c.profile.supports_segments else None,
        segment_brightness=(23,) * c.profile.segment_count if c.profile.supports_segments else None,
    )
    monkeypatch.setattr(c, "async_prepare_static_baseline", AsyncMock(return_value=baseline))
    return connected


def receive(client, data):
    client.start_notify.call_args.args[1](None, bytearray(data))


@pytest.mark.parametrize("connected", ["H6102"], indirect=True)
@pytest.mark.parametrize("route", ["diy", "music"])
@pytest.mark.parametrize("response", ["accepted", "rejected", "missing", "wrong_subtype", "stale"])
async def test_h6102_legacy_upload_verdict_blocks_activation(connected, route, response):
    c, client = connected
    c._renew_foreground_lease = MagicMock()
    assert c.profile.diy_requires_upload_ack and c.profile.music_requires_upload_ack
    if route == "diy":
        compiled = compile_application(
            LibraryItem.new("H6102 upload", SingleEffect(0, 0, 50, ((1, 2, 3),))),
            c.model,
            diy_code=0xFE,
            profile=c.profile,
        )
        packets = compiled.packets
        index = len(compiled.upload_packets) - 1
        accepted = frame("a10200")
        rejected = frame("a10201")
        wrong_subtype = frame("a10300")
    else:
        c._observe_identity_field("fw_version", "1.07.00")
        packets = tuple(prepare_music_request(c.model, "separation", 50, None, False, {}, profile=c.profile))
        index = len(packets) - 2
        accepted = frame("a3413000")
        rejected = frame("a3413001")
        wrong_subtype = frame("a30200")
    subtype = upload_ack_subtype(packets, index, c.model, profile=c.profile)
    assert subtype == (2 if route == "diy" else 0x41)
    old_callback = client.start_notify.call_args.args[1]

    async def write(_uuid, packet, **_kwargs):
        if packet != packets[index]:
            return
        assert packets[-1] not in [call.args[1] for call in client.write_gatt_char.await_args_list]
        if response == "accepted":
            receive(client, accepted)
        elif response == "rejected":
            receive(client, rejected)
        elif response == "wrong_subtype":
            receive(client, wrong_subtype)
        elif response == "stale":
            await c._start_notify()
            old_callback(None, bytearray(accepted))

    client.write_gatt_char.side_effect = write
    options = {
        "require_upload_ack": True,
        "upload_ack_index": index,
        "retry_allowed": lambda: False,
    }
    if response == "accepted":
        await c.async_write_effect_sequence(packets, intent=ControlIntent.APPLY, **options)
        expected = [
            c.profile.outbound_transform(packet) if c.profile.outbound_transform else packet for packet in packets
        ]
    else:
        with pytest.raises((BleakError, RuntimeError, TimeoutError, ValueError)):
            await c.async_write_effect_sequence(packets, intent=ControlIntent.APPLY, **options)
        expected = list(packets[: index + 1])
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == expected
    assert c._upload_ack is None


@pytest.mark.parametrize(
    "connected,pact",
    [("H61E5", (1, 1)), ("H61F5", (3, 1)), ("H617C", (10, 1)), ("H617E", (10, 1)), ("H617F", (10, 1))],
    indirect=["connected"],
)
async def test_exact_rgbic_scene_transfer_observes_upload_before_activation(selection_ready, pact):
    c, client = selection_ready
    if c.model in {"H61E5", "H61F5"}:
        c._observe_pact(*pact)
        c._observe_identity_field("fw_version", "1.06.00")
        c._observe_identity_field("hw_version", "1.00.03")
        c._physical_ic_count_confirmed = True
    c.is_on = True
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.scene_type == 2 and scene.command_version == 1)
    compiled = compile_effect(
        LibraryItem.new("Scene", BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))),
        c.model,
        profile=c.effect_authorization_profile,
    )
    assert compiled.rgbic_scene_v0 is False
    assert compiled.physical_ic_count == c.profile.physical_ic_count

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, DIY_OK)

    client.write_gatt_char.side_effect = write
    await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(compiled.packets)
    assert c._upload_ack is None


@pytest.mark.parametrize(
    "connected,kind,change",
    [
        (("H6139", 1), "single", "qualified"),
        (("H6139", 1), "multi", "qualified"),
        (("H6139", 10), "programme", "qualified"),
        (("H6139", 10), "programme", "unsupported"),
        (("H6139", 10), "programme", "unconfirmed"),
        (("H6139", 1), "single", "pact"),
    ],
    indirect=["connected"],
)
@pytest.mark.parametrize("phase", ["chunk", "verdict"])
async def test_upload_revalidates_its_own_identity_dependencies(selection_ready, monkeypatch, kind, change, phase):
    c, client = selection_ready
    c.fw_version = c.hw_version = None
    c._confirmed_identity_fields.difference_update({"fw_version", "hw_version"})
    c._resolve_device_profile()
    if kind == "programme":
        c._observe_identity_field("fw_version", "2.04.00")
        content = next(
            content
            for scene in SCENE_ENTRIES[c.model]
            if (content := decode_catalogue_palette_scene(c.model, scene)) is not None
        )
        delayed = frame("aa0703" + b"2.01.01".hex())
    else:
        content = (
            SingleEffect(0, 0, 0, ((12, 34, 56),))
            if kind == "single"
            else MultiEffect((EffectPair(0, 0), EffectPair(2, 0)), 0, ((12, 34, 56),))
        )
        delayed = frame("aa06" + b"1.07.02".hex())
    c.is_on = True
    c.brightness_pct = 23
    item = LibraryItem.new("Independent upload", content)
    compiled = compile_effect(item, c.model, profile=c.effect_authorization_profile)
    last = len(compiled.upload_packets) - 1
    subtype = upload_ack_subtype(compiled.upload_packets, last, c.model, profile=c.effect_authorization_profile)
    accepted = frame(f"{compiled.upload_packets[-1][0]:02x}{subtype:02x}00")
    store = InMemoryVersionedDocumentStore()
    repository = EffectDeploymentRepository(store)
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=True))
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)
    uploaded = asyncio.Event()
    generation, authority = c._profile_generation, c._authorization_generation

    def identity_reply():
        if change == "unsupported":
            receive(client, frame("aa06" + b"1.00.01".hex()))
        elif change == "unconfirmed":
            c._observe_identity_field("fw_version", None)
        elif change == "pact":
            c._observe_pact(10, 1)
        else:
            receive(client, delayed)
            assert (c._profile_generation, c._authorization_generation) == (generation, authority)
            assert c.brightness_pct == 23

    async def write(_uuid, packet, **_kwargs):
        if phase == "chunk" and packet == compiled.upload_packets[0]:
            identity_reply()
        if packet == compiled.upload_packets[-1]:
            uploaded.set()
            if phase == "chunk":
                receive(client, accepted)

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-11-22T00:00:00Z")
    )
    try:
        if phase == "verdict":
            await asyncio.wait_for(uploaded.wait(), 1)
            assert c._upload_ack is not None and not c._upload_ack.future.done()
            identity_reply()
            assert c._upload_ack.future.done() == (change != "qualified")
            receive(client, accepted)
        if change == "qualified":
            result = await asyncio.wait_for(task, 2)
            assert result.phase is DeploymentPhase.CONFIRMED
            assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(compiled.packets)
            reloaded = EffectDeploymentRepository(store)
            await reloaded.async_load()
            assert reloaded.snapshot().records == (result,)
        else:
            with pytest.raises((ValueError, HomeAssistantError)):
                await asyncio.wait_for(task, 2)
            assert compiled.activation_packet not in [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert c._upload_ack is None
        assert c._ensure_connected.await_count == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("scene_type", [0, 1])
@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_identity_independent_native_scene_survives_scene_policy_change(selection_ready, scene_type):
    c, client = selection_ready
    c.is_on = False
    c.brightness_pct = 23
    c._music_body = b"resident music"
    c._music_calm = None
    generation, authorization = c._profile_generation, c._authorization_generation
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.scene_type == scene_type)
    content = BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))
    compiled = compile_effect(
        LibraryItem.new("Independent scene", content), c.model, profile=c.effect_authorization_profile
    )
    power = build_power(True, c.model)

    async def write(_uuid, packet, **_kwargs):
        if packet == power:
            c._observe_identity_field("hw_version", "1.00.01")
            c._observe_identity_field("fw_version", "1.00.01")
            assert c.brightness_pct == 23 and c._music_body == b"resident music" and c._music_calm is None
        elif compiled.upload_packets and packet == compiled.upload_packets[-1]:
            receive(client, frame(f"a3{scene_type:02x}00"))

    client.write_gatt_char.side_effect = write
    await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [power, *compiled.packets]
    assert c.profile.rgbic_scene_v0 is True
    assert (c._profile_generation, c._authorization_generation) == (generation, authorization)


@pytest.mark.parametrize("hardware", ["1.00.01", "3.01.01"])
@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_versioned_scene_waits_for_current_hardware_identity(selection_ready, monkeypatch, hardware):
    c, client = selection_ready
    c.is_on = True
    c._confirmed_identity_fields.discard("hw_version")
    monkeypatch.setattr(coordinator_module, "IDENTITY_QUERY_TIMEOUT", 0)
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.command_version == 1)

    with pytest.raises(HomeAssistantError) as error:
        await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
    assert error.value.translation_key == "identity_not_ready"
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [frame("aa0703")]
    assert c.control_write_attempts == 0

    client.write_gatt_char.reset_mock()
    c._observe_identity_field("hw_version", hardware)
    if hardware == "1.00.01":
        with pytest.raises(ValueError, match="Scene is not supported"):
            await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
        client.write_gatt_char.assert_not_awaited()
        return

    item = LibraryItem.new("Scene", BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id)))
    compiled = compile_effect(item, c.model, profile=c.effect_authorization_profile)

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, DIY_OK)

    client.write_gatt_char.side_effect = write
    await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == list(compiled.packets)


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_versioned_light_effect_checks_identity_before_writes(selection_ready, monkeypatch, saved):
    c, client = selection_ready
    c.is_on = False
    c._confirmed_identity_fields.discard("hw_version")
    monkeypatch.setattr(coordinator_module, "IDENTITY_QUERY_TIMEOUT", 0)
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.command_version == 1)
    if saved:
        backend = MagicMock(spec=EffectBackend)
        name = "Saved"
        item = LibraryItem.new(name, BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id)))
        backend.application.library_snapshot.return_value = LibrarySnapshot((item,))
        backend.active_workspaces.get.return_value = None
        light = GoveeBLELight(c, config_entry_id="entry-a", effect_backend=backend)
        assert name in light.effect_list
    else:
        c.profile = device_profile(c.model, None, None, firmware=c.fw_version)
        light = GoveeBLELight(c)
        name = scene.display_name
        assert name not in light.effect_list
    supersede = AsyncMock()
    monkeypatch.setattr(light, "_async_supersede_preview", supersede)
    generation = c._control_arbiter.foreground_generation

    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(effect=name, brightness=128)
    assert error.value.translation_key == "identity_not_ready"
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [frame("aa0703")]
    supersede.assert_not_awaited()
    assert c._control_arbiter.foreground_generation == generation


@pytest.mark.parametrize("change", ["policy", "authority"])
@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_scene_ack_revalidates_dependent_policy_and_authority(selection_ready, change):
    c, client = selection_ready
    c.is_on = True
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.command_version == 1)
    content = BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))
    compiled = compile_effect(
        LibraryItem.new("Dependent scene", content), c.model, profile=c.effect_authorization_profile
    )

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            if change == "policy":
                c._observe_identity_field("hw_version", "1.00.01")
            else:
                c._observe_identity_field("hw_version", None)
            receive(client, DIY_OK)

    client.write_gatt_char.side_effect = write
    with pytest.raises(ValueError):
        await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == list(compiled.upload_packets)
    assert c._upload_ack is None
    assert c._ensure_connected.await_count == 1


@pytest.mark.parametrize("connected", ["H600A", "H601C"], indirect=True)
@pytest.mark.parametrize("kind", ["scene", "diy"])
@pytest.mark.parametrize("response", ["accepted", "rejected", "missing"])
async def test_bulb_scene_and_diy_ack_barrier(selection_ready, kind, response):
    c, client = selection_ready
    c.is_on = True
    if kind == "scene":
        scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.scene_type == 1)
        content = BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))
    else:
        content = SingleEffect(0, 0, 50, ((1, 2, 3),))
    compiled = compile_effect(LibraryItem.new("Bulb effect", content), c.model, diy_code=24)
    final_upload = len(compiled.upload_packets) - 1
    subtype = upload_ack_subtype(compiled.upload_packets, final_upload, c.model)
    assert subtype == (4 if kind == "diy" else 1)

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1] and response != "missing":
            assert compiled.activation_packet not in [call.args[1] for call in client.write_gatt_char.call_args_list]
            receive(client, frame(f"a3{subtype:02x}{'00' if response == 'accepted' else '01'}"))

    async def apply():
        if kind == "scene":
            await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
        else:
            await c.async_write_effect_sequence(
                compiled.packets,
                intent=ControlIntent.APPLY,
                require_upload_ack=c.profile.diy_requires_upload_ack,
                upload_ack_index=final_upload,
            )

    client.write_gatt_char.side_effect = write
    if response == "accepted":
        await apply()
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            await apply()
    sent = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert sent == list(compiled.packets if response == "accepted" else compiled.upload_packets)
    assert c._upload_ack is None
    assert c._ensure_connected.await_count == 1


@pytest.mark.parametrize("connected", ["H601C"], indirect=True)
@pytest.mark.parametrize("response", ["accepted", "rejected", "missing"])
async def test_h601c_production_upload_waits_for_positive_ack_before_selector(selection_ready, response):
    c, client = selection_ready
    c.is_on = True
    compiled = compile_effect(
        LibraryItem.new("H601C upload", SingleEffect(0, 0, 50, ((1, 2, 3),))),
        c.model,
        diy_code=24,
        profile=c.profile,
    )
    final_upload = len(compiled.upload_packets) - 1
    assert upload_ack_subtype(compiled.upload_packets, final_upload, c.model, profile=c.profile) == 0x04
    assert compiled.activation_packet == frame("33050a1800")
    uploaded = asyncio.Event()
    verdict_delivered = False

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            uploaded.set()
        if packet == compiled.activation_packet:
            assert response == "accepted"
            assert verdict_delivered

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        c.async_write_effect_sequence(
            compiled.packets,
            intent=ControlIntent.APPLY,
            require_upload_ack=c.profile.diy_requires_upload_ack,
            upload_ack_index=final_upload,
        )
    )
    await asyncio.wait_for(uploaded.wait(), 1)
    assert c._upload_ack is not None
    assert compiled.activation_packet not in [call.args[1] for call in client.write_gatt_char.await_args_list]
    if response != "missing":
        verdict_delivered = True
        receive(client, frame(f"a304{'00' if response == 'accepted' else '01'}"))
    if response == "accepted":
        await asyncio.wait_for(task, 1)
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            await asyncio.wait_for(task, 1)
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(compiled.packets if response == "accepted" else compiled.upload_packets)
    assert c._upload_ack is None
    assert c._ensure_connected.await_count == 1


@pytest.mark.parametrize("connected", ["H6139", "H6159", "H6181"], indirect=True)
@pytest.mark.parametrize("kind,pact", [("diy", (None, None)), ("diy", (10, 2)), ("scene", (10, 2))])
@pytest.mark.parametrize("response", ["accepted", "rejected", "missing"])
async def test_h6181_revision_uploads_require_matching_success_before_activation(connected, kind, pact, response):
    c, client = connected
    c.profile = replace(
        device_profile(c.model, *pact, firmware="1.07.02", hardware="1.00.02"),
        profile_identity_fields=frozenset(),
        effect_identity_fields=frozenset(),
    )
    if kind == "scene":
        scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.scene_type == 1)
        content = BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))
    else:
        content = SingleEffect(0, 0, 50, ((1, 2, 3),))
    compiled = compile_effect(
        LibraryItem.new("Palette", content),
        c.model,
        diy_code=None if c.model in {"H6139", "H6159"} else 42,
        profile=c.profile,
    )
    last_upload = len(compiled.upload_packets) - 1
    subtype = upload_ack_subtype(compiled.upload_packets, last_upload, c.model, profile=c.profile)
    protocol = compiled.upload_packets[-1][0]

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1] and response != "missing":
            receive(client, frame(f"{protocol:02x}{subtype:02x}{'00' if response == 'accepted' else '01'}"))

    client.write_gatt_char.side_effect = write
    if response == "accepted":
        await c.async_write_effect_sequence(
            compiled.packets, intent=ControlIntent.APPLY, require_upload_ack=True, upload_ack_index=last_upload
        )
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            await c.async_write_effect_sequence(
                compiled.packets, intent=ControlIntent.APPLY, require_upload_ack=True, upload_ack_index=last_upload
            )
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(compiled.packets if response == "accepted" else compiled.upload_packets)
    assert c._upload_ack is None


@pytest.mark.parametrize(
    "connected,carrier",
    [(("H6053", 1), "diy"), ("H6053", "diy"), ("H6053", "rgb"), ("H6053", "rgbic_v1"), ("H6053", "rgbic_v2")],
    indirect=["connected"],
)
@pytest.mark.parametrize("response", ["accepted", "rejected", "wrong_protocol"])
async def test_retained_and_revision_uploads_wait_for_their_exact_ack(selection_ready, carrier, response):
    c, client = selection_ready
    if carrier == "diy":
        content = SingleEffect(0, 0, 50, ((1, 2, 3),))
    else:
        raw = bytes.fromhex(
            {
                "rgb": "9301ffff800100ff0000",
                "rgbic_v1": "011a000100010001ffff0080010100800101ff000000008000008000",
                "rgbic_v2": "0a011e000100010001ffff0080010100800101ff00000000800000800000010000",
            }[carrier]
        )
        effect, padding = decode_workshop_effect(c.model, raw, carrier=carrier)
        content = RetainedSceneEffect(c.model, "retained", effect, raw, padding, carrier)
    compiled = compile_application(
        LibraryItem.new("Upload", content),
        c.model,
        diy_code=37 if carrier == "diy" else None,
        profile=c.profile,
    )
    last_upload = len(compiled.upload_packets) - 1
    subtype = upload_ack_subtype(compiled.upload_packets, last_upload, c.model, profile=c.profile)
    assert upload_ack_mode(compiled.upload_packets, last_upload, c.model, profile=c.profile) is None
    protocol = compiled.upload_packets[-1][0]

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            assert compiled.activation_packet not in [call.args[1] for call in client.write_gatt_char.call_args_list]
            ack_protocol = (0xA3 if protocol == 0xA1 else 0xA1) if response == "wrong_protocol" else protocol
            receive(client, frame(f"{ack_protocol:02x}{subtype:02x}{'01' if response == 'rejected' else '00'}"))

    client.write_gatt_char.side_effect = write

    async def apply():
        await c.async_write_effect_sequence(
            compiled.packets, intent=ControlIntent.APPLY, require_upload_ack=True, upload_ack_index=last_upload
        )

    if response == "accepted":
        await apply()
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            await apply()
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(compiled.packets if response == "accepted" else compiled.upload_packets)
    assert c._upload_ack is None


@pytest.mark.parametrize("connected", [("H6053", 1), "H6053"], indirect=True)
async def test_newer_scene_during_final_activation_invalidates_upload_completion(
    selection_ready, monkeypatch, virtual_clock
):
    c, client = selection_ready
    c.is_on = True
    receive(client, frame("aa050a2500"))
    item = LibraryItem.new("Superseded", SingleEffect(0, 0, 50, ((1, 2, 3),)))
    compiled = compile_application(
        item,
        c.model,
        diy_code=37,
        profile=c.profile,
    )
    index = len(compiled.upload_packets) - 1
    subtype = upload_ack_subtype(compiled.upload_packets, index, c.model, profile=c.profile)
    protocol = compiled.upload_packets[-1][0]

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, frame(f"{protocol:02x}{subtype:02x}00"))
        elif packet == compiled.activation_packet:
            for field in ("color_mode", "effect", "scene_code", "unknown_scene_code"):
                if field in c._expected_state:
                    virtual_clock.vtime = max(virtual_clock.vtime, c._expected_state[field][1])
            receive(client, frame("aa05041800"))
            assert c.scene_code == 24
            assert c.diy_code is None

    client.write_gatt_char.side_effect = write
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    with pytest.raises(ModeTransitionSupersededError):
        await engine.async_apply_snapshot(
            c,
            item,
            config_entry_id="entry-a",
            updated_at="2026-09-16T00:00:00Z",
            diy_code=37,
            destination_consent=approve_diy_destination_operation(c, "entry-a", 37),
        )
    assert c.scene_code == 24
    assert c.diy_code is None


@pytest.mark.parametrize("connected", ["H6097", "H600A"], indirect=True)
@pytest.mark.parametrize("fault", ["missing", "rejected", "write_timeout", "disconnect"])
async def test_diy_upload_requires_result_without_uncertain_replay(connected, fault):
    c, client = connected
    compiled = compile_application(
        LibraryItem.new("Basic", SingleEffect(0, 0, 50, ((1, 2, 3),))),
        c.model,
        diy_code=24 if c.model == "H600A" else None,
    )
    final_upload = len(compiled.upload_packets) - 1

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[0] and fault == "write_timeout":
            raise TimeoutError("upload write timed out")
        if packet == compiled.upload_packets[0] and fault == "disconnect":
            c._clear_client_state(client)
            raise BleakError("disconnected during upload")
        if packet == compiled.upload_packets[-1] and fault == "rejected":
            receive(client, frame("a30401"))

    client.write_gatt_char.side_effect = write
    with pytest.raises((RuntimeError, TimeoutError, BleakError)):
        await c.async_write_effect_sequence(
            compiled.packets, intent=ControlIntent.APPLY, require_upload_ack=True, upload_ack_index=final_upload
        )
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(
        compiled.upload_packets[:1] if fault in {"write_timeout", "disconnect"} else compiled.upload_packets
    )
    assert c._ensure_connected.await_count == 1


@pytest.mark.parametrize("connected", ["H6097", "H600A", "H617A", "H617C", "H617E", "H617F"], indirect=True)
@pytest.mark.parametrize("observations", [(None,), (False, False), (False, True)])
async def test_scene_verification_does_not_repeat_accepted_upload(selection_ready, monkeypatch, observations):
    c, client = selection_ready
    c.is_on = True
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.scene_type == (1 if c.model == "H600A" else 2))
    compiled = compile_effect(
        LibraryItem.new("Scene", BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))), c.model
    )
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(side_effect=observations))

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1]:
            subtype = upload_ack_subtype(compiled.upload_packets, len(compiled.upload_packets) - 1, c.model)
            receive(client, frame(f"a3{subtype:02x}00"))

    client.write_gatt_char.side_effect = write
    if observations[-1] is False:
        with pytest.raises(RuntimeError, match="Failed to confirm scene"):
            await c.async_apply_native_scene(scene.display_name, scene_entry=scene)
    else:
        await c.async_apply_native_scene(scene.display_name, scene_entry=scene)
    expected = [*compiled.packets, *([compiled.activation_packet] if observations[0] is False else [])]
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == expected
    assert c._ensure_connected.await_count == len(observations)


@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_missing_upload_ack_cannot_spend_transport_retries(connected, monkeypatch):
    c, client = connected
    packets, index = sequence()
    token, generation = c._notification_token, c._profile_generation
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 2)
    with pytest.raises(TimeoutError, match="did not acknowledge"):
        await write_sequence(c, packets, index)
    assert c._ensure_connected.await_count == 1
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == packets[: index + 1]
    assert c._upload_ack is None
    c._disconnect_locked.assert_awaited_once_with(planned_release=True)
    assert c._client is None
    assert c._notification_token is None
    assert token is not None
    assert c._profile_generation == generation


@pytest.mark.parametrize("preview", [False, True])
async def test_late_ack_from_retired_channel_cannot_authorise_next_upload(connected, monkeypatch, preview):
    c, client = connected
    packets, index = sequence()
    old_callback = client.start_notify.call_args.args[1]
    old_token = c._notification_token
    options = {"writer": lambda *args, **kwargs: preview_writer(c, *args, **kwargs)} if preview else {}
    with pytest.raises(TimeoutError):
        await write_sequence(c, packets, index, **options)
    await c._ensure_connected()
    assert c._notification_token is not old_token
    uploaded = asyncio.Event()
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)

    async def write(_uuid, packet, **_kwargs):
        if packet == packets[index]:
            old_callback(None, bytearray(MUSIC_OK))
            uploaded.set()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(write_sequence(c, packets, index, **options))
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        assert c._upload_ack is not None and not c._upload_ack.future.done()
        assert not task.done()
        receive(client, MUSIC_OK)
        await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [*packets[: index + 1], *packets]


@pytest.mark.parametrize("connected", ["H617C", "H617E", "H617F"], indirect=True)
@pytest.mark.parametrize("preview", [False, True])
async def test_retired_write_failure_preserves_replacement_resources(connected, monkeypatch, preview):
    c, client = connected
    packets, index = sequence()
    replacement = MagicMock(
        is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock()
    )
    future = asyncio.get_running_loop().create_future()
    pending = owned = None
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 3)

    async def write(_uuid, _packet, **_kwargs):
        nonlocal pending, owned
        c._client = replacement
        await c._start_notify()
        pending = PendingUploadAck(
            replacement,
            c._notification_token,
            c._profile_generation,
            0x41,
            None,
            0xA3,
            future,
            lambda: None,
        )
        c._upload_ack = pending
        owned = (asyncio.current_task(), A3Sequence(packets))
        c._a3_sequence = owned
        raise BleakError("attribute not found on retired client")

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kwargs: preview_writer(c, *args, **kwargs)} if preview else {}
    try:
        with pytest.raises(ModeTransitionSupersededError):
            await write_sequence(c, packets, index, **options)
        assert c._client is replacement and c._upload_ack is pending and c._a3_sequence is owned
        assert not future.done() and not c.fresh_services_required
        replacement.write_gatt_char.assert_not_awaited()
        replacement.disconnect.assert_not_awaited()
        c._disconnect_locked.assert_not_awaited()
        assert client.write_gatt_char.await_count == 1
    finally:
        future.cancel()
        c._upload_ack = c._a3_sequence = None


@pytest.mark.parametrize("activated", [False, True])
async def test_upload_outcome_records_actual_selector_attempt(connected, activated):
    c, _ = connected
    packets, index = sequence()
    if activated:
        packets = [packets[-1], *packets[:-1]]
        index = len(packets) - 1
    with pytest.raises(coordinator_module.UploadAckTimeoutError) as caught:
        await write_sequence(c, packets, index)
    assert caught.value.before_activation is not activated


@pytest.mark.parametrize("outcome", ["missing", "cancelled"])
async def test_music_upload_without_verdict_does_not_restore_a_selector(selection_ready, monkeypatch, outcome):
    c, client = selection_ready
    c.is_on = True
    item = LibraryItem.new("Music", MusicProfile(c.model, "bloom", 42))
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    uploaded = asyncio.Event()

    async def write(_uuid, _packet, **_kwargs):
        if c._upload_ack is not None:
            uploaded.set()

    client.write_gatt_char.side_effect = write
    if outcome == "cancelled":
        monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)
    task = asyncio.create_task(
        engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-11-22T00:00:00Z")
    )
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        if outcome == "cancelled":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else TimeoutError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    c.async_restore_effect_control_state.assert_not_awaited()
    assert c._mode_write_generation == 0
    (record,) = repository.snapshot().records
    assert record.phase is DeploymentPhase.UNCERTAIN
    assert record.error_code == ("operation_cancelled" if outcome == "cancelled" else "upload_unconfirmed")


@pytest.mark.parametrize("connected", ["H617A", "H617C", "H617E", "H617F"], indirect=True)
async def test_native_scene_revalidates_command_version_after_subscription_replacement(selection_ready):
    c, first = selection_ready
    c.is_on = True
    c._note_identity(fw_version="1.06.00", hw_version="1.00.02")
    scene = next(scene for scene in SCENE_ENTRIES[c.model] if scene.command_version == 1)
    compiled = compile_effect(
        LibraryItem.new("Scene", BuiltinScene(CatalogueRef(c.model, scene.scene_id, scene.effect_id))),
        c.model,
        profile=c.effect_authorization_profile,
    )
    generation = c._profile_generation
    second = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())

    async def reconnect():
        c._clear_client_state(first)
        c._client = second
        await c._start_notify()
        assert c._profile_generation == generation
        assert c.effect_authorization_profile.scene_command_versions == {0}
        assert c.effect_authorization_profile.rgbic_scene_v0
        return second

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(second, frame("a30200"))

    c._ensure_connected.side_effect = reconnect
    second.write_gatt_char.side_effect = write
    with pytest.raises(ValueError, match="Scene is not supported"):
        await c.async_apply_native_scene(scene.display_name, scene_entry=scene, verify=False)
    second.write_gatt_char.assert_not_awaited()
    assert c.control_write_attempts == 0


@pytest.mark.parametrize("connected", ["H600A"], indirect=True)
async def test_h600a_connection_failure_before_upload_can_retry(connected):
    c, client = connected
    compiled = compile_application(LibraryItem.new("Basic", SingleEffect(0, 0, 50, ((1, 2, 3),))), c.model, diy_code=24)
    reconnect = c._ensure_connected.side_effect

    async def connect():
        if c._ensure_connected.await_count == 1:
            raise BleakError("connection failed before upload")
        return await reconnect()

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, frame("a30400"))

    c._ensure_connected.side_effect = connect
    client.write_gatt_char.side_effect = write
    await c.async_write_effect_sequence(
        compiled.packets,
        intent=ControlIntent.APPLY,
        require_upload_ack=True,
        upload_ack_index=len(compiled.upload_packets) - 1,
    )
    assert c._ensure_connected.await_count == 2
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(compiled.packets)


@pytest.mark.parametrize(
    "connected", ["H6022", "H6139", "H6159", "H6097", "H7025", "H6046", ("H6053", 1), "H6053"], indirect=True
)
@pytest.mark.parametrize("accepted", [False, True])
async def test_h7025_music_waits_for_positive_upload_result(selection_ready, accepted):
    c, client = selection_ready
    c.music_sensitivity = 42
    mode, code = (
        ("energetic", "39")
        if c.model == "H6022"
        else ("bloom", "30")
        if c.model in {"H6139", "H6159"}
        else ("torch", "50")
        if c.model in {"H6046", "H6053"}
        else ("hopping", "48")
    )
    expected = prepare_music_request(c.model, mode, 42, None, c.model == "H6022", {}, profile=c.profile)
    selector = c.profile.outbound_transform(expected[-1]) if c.profile.outbound_transform else expected[-1]

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2]:
            receive(client, frame("a341" + code + ("00" if accepted else "01")))

    client.write_gatt_char.side_effect = write
    if accepted:
        await c.async_select_music_slug(mode)
        assert c.music_body is not None
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await c.async_select_music_slug(mode)
        assert c.music_body is None
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert (selector in sent) is accepted


@pytest.mark.parametrize("connected", ["H61E5"], indirect=True)
@pytest.mark.parametrize("verdict", ["accepted", "rejected", "missing"])
async def test_h61e5_extended_music_activates_only_after_positive_upload_verdict(selection_ready, verdict):
    c, client = selection_ready
    c._observe_pact(1, 1)
    c._physical_ic_count_confirmed = True
    c.music_sensitivity = 42
    expected = tuple(
        bytes.fromhex(packet)
        for packet in (
            "3301010000000000000000000000000000000033",
            "a3000103413307ff0000ff7f00ffff0000ff0054",
            "a3010000ff00ffff8b00ff010101196201030554",
            "a3ff0f0000000000000000000000000000000053",
            "330513332a00000000000000000000000000003c",
        )
    )

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2] and verdict != "missing":
            receive(client, frame("a3413300" if verdict == "accepted" else "a3413301"))

    client.write_gatt_char.side_effect = write
    if verdict == "accepted":
        await c.async_select_music_slug("hopping")
        assert c.music_body is not None
    elif verdict == "rejected":
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await c.async_select_music_slug("hopping")
        assert c.music_body is None
    else:
        with pytest.raises(TimeoutError, match="Device did not acknowledge effect upload"):
            await c.async_select_music_slug("hopping")
        assert c.music_body is None
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(expected if verdict == "accepted" else expected[:-1])
    assert c._upload_ack is None


@pytest.mark.parametrize("connected", ["H61F5"], indirect=True)
@pytest.mark.parametrize("response", ["accepted", "rejected", "missing"])
async def test_h61f5_extended_music_waits_for_positive_upload_result(selection_ready, response):
    c, client = selection_ready
    c._observe_pact(3, 1)
    c._physical_ic_count_confirmed = True
    c.music_sensitivity = 42
    recovery = c._pre_mode_snapshot
    expected = (
        bytes.fromhex("3301010000000000000000000000000000000033"),
        bytes.fromhex("a3000103413307ff0000ff7f00ffff0000ff0054"),
        bytes.fromhex("a3010000ff00ffff8b00ff010101196201030657"),
        bytes.fromhex("a3ff140000000000000000000000000000000048"),
        bytes.fromhex("330513332a00000000000000000000000000003c"),
    )
    assert prepare_music_request("H61F5", "hopping", 42, None, False, {}, profile=c.profile) == expected
    selector = expected[-1]

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2] and response != "missing":
            assert selector not in [call.args[1] for call in client.write_gatt_char.call_args_list]
            receive(client, frame("a34133" + ("00" if response == "accepted" else "01")))

    client.write_gatt_char.side_effect = write
    if response == "accepted":
        await c.async_select_music_slug("hopping")
        assert c.music_mode == "hopping"
        assert c.music_body is not None
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            await c.async_select_music_slug("hopping")
        assert c.music_mode == "off"
        assert c.music_body is None
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(
        expected if response == "accepted" else expected[:-1]
    )
    if response == "accepted":
        assert c._pre_mode_snapshot is not None
        assert c._pre_mode_snapshot.segment_colors == ((17, 34, 51),) * 10
        assert c._pre_mode_snapshot.segment_brightness == (23,) * 10
    else:
        assert c._pre_mode_snapshot == recovery
    assert c._upload_ack is None
    assert c._ensure_connected.await_count == 1


@pytest.mark.parametrize("connected", ["H617E"], indirect=True)
@pytest.mark.parametrize("verdict", ["accepted", "rejected", "missing", "late"])
async def test_h617e_extended_music_requires_positive_verdict_before_selector(selection_ready, verdict, monkeypatch):
    c, client = selection_ready
    expected = prepare_music_request(c.model, "hopping", c.music_sensitivity, None, False, {}, profile=c.profile)
    final_upload, selector = expected[-2:]
    assert final_upload[0] == 0xA3 and selector[0] == 0x33
    uploaded = asyncio.Event()

    async def write(_uuid, packet, **_kwargs):
        if packet == final_upload:
            uploaded.set()

    client.write_gatt_char.side_effect = write
    if verdict == "missing":
        monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.05)
    task = asyncio.create_task(c.async_select_music_slug("hopping"))
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert sent == list(expected[:-1])
        assert selector not in sent
        assert not task.done()

        if verdict in {"accepted", "rejected"}:
            receive(client, frame(f"a34133{'00' if verdict == 'accepted' else '01'}"))
            if verdict == "accepted":
                await task
            else:
                with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
                    await task
        else:
            with pytest.raises(TimeoutError, match="did not acknowledge"):
                await asyncio.wait_for(task, 1)
            if verdict == "late":
                receive(client, frame("a3413300"))
                await asyncio.sleep(0)

        sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert sent == list(expected if verdict == "accepted" else expected[:-1])
        assert c._upload_ack is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "connected,mode,pact",
    [
        ("H6099", "hopping", None),
        ("H66A0", "hopping", None),
        ("H1A42", "splash", None),
        ("H61E5", "hopping", (1, 1)),
        ("H61F5", "hopping", (3, 1)),
        ("H617E", "hopping", None),
    ],
    indirect=["connected"],
)
@pytest.mark.parametrize("accepted", [False, True])
async def test_fleet_extended_music_activates_only_after_positive_upload_verdict(selection_ready, mode, pact, accepted):
    c, client = selection_ready
    if pact is not None:
        c._observe_pact(*pact)
        c._physical_ic_count_confirmed = True
        c.profile = device_profile(c.model, *pact)
    elif c.model == "H6099":
        c.profile = replace(c.profile, physical_ic_count=50)
        c._physical_ic_count_confirmed = True
    c.music_sensitivity = 42
    expected = prepare_music_request(c.model, mode, 42, None, False, {}, profile=c.profile)
    final_upload, selector = expected[-2:]
    assert final_upload[0] == 0xA3 and selector[0] == 0x33

    async def write(_uuid, packet, **_kwargs):
        if packet == final_upload:
            receive(client, frame(f"a341{selector[3]:02x}{'00' if accepted else '01'}"))

    client.write_gatt_char.side_effect = write
    if accepted:
        await c.async_select_music_slug(mode)
        assert c.music_body is not None
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await c.async_select_music_slug(mode)
        assert c.music_body is None
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(expected if accepted else expected[:-1])
    assert c._upload_ack is None


@pytest.mark.parametrize("connected", ["H61E5", "H61F5", "H617E", "H617F"], indirect=True)
@pytest.mark.parametrize("accepted", [False, True])
async def test_fleet_authored_uploads_activate_only_after_positive_verdict(selection_ready, accepted):
    c, client = selection_ready
    if c.model == "H61E5":
        c._observe_pact(1, 1)
        c._physical_ic_count_confirmed = True
    elif c.model == "H61F5":
        c._observe_pact(3, 1)
        c._physical_ic_count_confirmed = True
    c.is_on = True
    if c.model == "H617F":
        upload_packets = tuple(fragment_a3(4, bytes.fromhex("0401006401010203")))
        activation_packet = build_diy_activation(24, c.model, profile=c.profile)
    else:
        compiled = compile_effect(
            LibraryItem.new("Fleet upload", SingleEffect(0, 0, 50, ((1, 2, 3),))),
            c.model,
            diy_code=24,
            profile=c.profile,
        )
        upload_packets = compiled.upload_packets
        activation_packet = compiled.activation_packet
    assert activation_packet is not None
    packets = (*upload_packets, activation_packet)
    last_upload = len(upload_packets) - 1
    subtype = upload_ack_subtype(upload_packets, last_upload, c.model, profile=c.profile)

    async def write(_uuid, packet, **_kwargs):
        if packet == upload_packets[-1]:
            receive(client, frame(f"a3{subtype:02x}{'00' if accepted else '01'}"))

    client.write_gatt_char.side_effect = write
    awaitable = c.async_write_effect_sequence(
        packets,
        intent=ControlIntent.APPLY,
        require_upload_ack=c.profile.diy_requires_upload_ack,
        upload_ack_index=last_upload,
    )
    if accepted:
        await awaitable
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await awaitable
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == list(packets if accepted else upload_packets)
    assert c._upload_ack is None


@pytest.mark.parametrize("connected", ["H6139", "H6159"], indirect=True)
@pytest.mark.parametrize("pact,firmware,hardware,mode", [(1, "1.07.02", "1.00.01", 14), (10, "2.04.00", "2.01.01", 19)])
async def test_invalid_native_sensitivity_does_not_poison_observation_or_mode_selection(
    selection_ready, pact, firmware, hardware, mode
):
    c, client = selection_ready
    later_pact = 2 if c.model == "H6159" and pact == 10 else pact
    c._pact_identity.connection_pacts.clear()
    c._observe_pact(later_pact, 1)
    c._observe_identity_field("fw_version", firmware)
    c._observe_identity_field("hw_version", hardware)
    receive(client, frame(bytes([0xAA, 5, mode, 48, 42]).hex()))
    revision = c._field_revisions["music_sensitivity"]
    receive(client, frame(bytes([0xAA, 5, mode, 48, 100]).hex()))
    assert c.music_sensitivity == 42
    assert c._field_revisions["music_sensitivity"] == revision
    assert c.music_mode == "bloom"
    expected = prepare_music_request(c.model, "dynamic", 42, None, False, {}, profile=c.profile)[-1]
    selector = c.profile.outbound_transform(expected) if c.profile.outbound_transform else expected
    await c.async_select_music_slug("dynamic")
    assert selector in [call.args[1] for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("connected", ["H6097", "H7025", "H6046", ("H6053", 1), "H6053"], indirect=True)
@pytest.mark.parametrize("fault", ["missing_ack", "write_timeout", "disconnect"])
async def test_h7025_uncertain_upload_is_not_automatically_replayed(selection_ready, fault):
    c, client = selection_ready
    mode = "torch" if c.model in {"H6046", "H6053"} else "hopping"
    expected = prepare_music_request(c.model, mode, 99, None, False, {}, profile=c.profile)

    async def reconnect():
        if c._client is not client:
            c._client = client
            await c._start_notify()
        return client

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[1]:
            if fault == "write_timeout":
                raise TimeoutError("upload write timed out")
            if fault == "disconnect":
                c._clear_client_state(client)
                raise BleakError("disconnected during upload")

    c._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = write
    with pytest.raises((TimeoutError, BleakError)):
        await c.async_select_music_slug(mode)
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == (list(expected[:-1]) if fault == "missing_ack" else list(expected[:2]))
    assert c._ensure_connected.await_count == 1
    assert c.music_body is None and c._upload_ack is None


@pytest.mark.parametrize("connected", ["H6097", "H7025"], indirect=True)
async def test_h7025_connection_failure_before_upload_can_retry(connected):
    c, client = connected
    expected = prepare_music_request(c.model, "hopping", 99, None, False, {})

    async def reconnect():
        if c._ensure_connected.await_count == 1:
            raise BleakError("connection failed before upload")
        client.is_connected = True
        c._client = client
        await c._start_notify()
        return client

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2]:
            receive(client, frame("a3414800"))

    c._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = write
    await c.async_write_effect_sequence(
        expected,
        intent=ControlIntent.USER,
        require_upload_ack=True,
        upload_ack_index=len(expected) - 2,
    )
    assert c._ensure_connected.await_count == 2
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(expected)


@pytest.mark.parametrize(
    ("connected", "mode", "code", "body", "parameters", "edited"),
    [
        ("H7025", "flow", 0x59, "5902010203040506000205", {"direction": "counterclockwise"}, "5902010203040506010205"),
        (
            "H7025",
            "hopping",
            0x48,
            "480201020304050601020319aabb",
            {"relative_brightness": 17},
            "480201020304050601020311aabb",
        ),
        (
            "H617A",
            "hopping",
            0x33,
            "3302010203040506aabbcc196104050708",
            {"relative_brightness": 17},
            "3302010203040506aabbcc116104050708",
        ),
    ],
    indirect=["connected"],
)
@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("preview", [False, True])
async def test_retained_edit_uploads_acknowledges_then_activates(
    selection_ready, mode, code, body, parameters, edited, accepted, preview
):
    c, client = selection_ready
    c.music_mode, c.music_sensitivity = mode, 42
    c._music_body = (mode, bytes.fromhex(body))
    upload = fragment_a3(0x41, bytes.fromhex(edited))
    selector = build_music_mode(code, 42, None, False, c.model)
    events = []
    uploaded = asyncio.Event()

    async def write(_uuid, packet, **_kwargs):
        events.append(packet)
        if packet == upload[-1]:
            uploaded.set()

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kwargs: preview_writer(c, *args, **kwargs)} if preview else {}
    task = asyncio.create_task(c.async_apply_music_params(code, parameters=parameters, **options))
    await asyncio.wait_for(uploaded.wait(), 1)
    assert events == upload
    assert not task.done()
    assert c._upload_ack is not None and not c._upload_ack.future.done()
    events.append("positive ACK" if accepted else "negative ACK")
    receive(client, frame(f"a341{code:02x}" + ("00" if accepted else "01")))
    if accepted:
        await task
        assert events == [*upload, "positive ACK", selector]
        assert c.music_body == bytes.fromhex(edited)
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await task
        assert events == [*upload, "negative ACK"]
        assert c.music_body is None


def sequence(subtype=0x41):
    upload = fragment_a3(subtype, bytes(range(40)))
    return [*upload, build_scene_activation("H617A", 507)], len(upload) - 1


async def write_sequence(c, packets, index, **kwargs):
    await c.async_write_effect_sequence(
        packets,
        intent=ControlIntent.PREVIEW if "writer" in kwargs else ControlIntent.USER,
        require_upload_ack=True,
        upload_ack_index=index,
        **kwargs,
    )


async def preview_writer(c, packet, *, write_guard=None, state_values=None, expected_values=None, on_write=None):
    assert not c._lock.locked(), "caller must not deadlock the connection-bound writer"
    await c.async_preview_write(
        packet, before_write=write_guard, state_values=state_values, expected_values=expected_values, on_write=on_write
    )


@pytest.mark.parametrize(
    "prefix,subtype,expected",
    [
        ("a3413000", 0x41, True),
        ("a3410001", 0x41, False),
        ("a30200ff", 2, True),
        ("a3020100", 2, False),
        ("330100", 0x41, None),
        ("a30200", 0x41, None),
    ],
)
def test_generated_ack_offsets_and_subtype(prefix, subtype, expected):
    result = parse_command_ack_result(frame(prefix), "H617A")
    assert result.parsed is not None
    assert result.parser == "h617a_command_ack"
    assert type(result.parsed).__module__.endswith(".h617a_command_ack")
    assert upload_ack_success(result.parsed, subtype) is expected


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("a3415000", True), ("a3415001", False), ("a3414d00", None), ("a3415100", None), ("a3425000", None)],
)
def test_h6076_ack_must_repeat_the_uploaded_mode(prefix, expected):
    # The lamp answers a Torch (0x50) companion with `a3 41 50 00`.
    profile = device_profile("H6076", 1, 1, firmware="1.04.05")
    *upload, selector = prepare_music_request("H6076", "torch", 99, None, False, {}, profile=profile)[1:]
    assert selector[:3] == b"\x33\x05\x0f"
    index = len(upload) - 1
    assert upload_ack_subtype(upload, index, "H6076", profile=profile) == 0x41
    assert upload_ack_mode(upload, index, "H6076", profile=profile) == 0x50
    result = parse_command_ack_result(frame(prefix), "H6076", profile=profile)
    assert result.parser == ("h6076_music_ack" if prefix.startswith("a341") else "h617a_command_ack")
    assert upload_ack_success(result.parsed, 0x41, 0x50) is expected
    assert upload_ack_success(result.parsed, 0x41) is None
    assert parse_command_ack_result(frame("330100"), "H6076", profile=profile).parser == "h617a_command_ack"
    for subtype in (0x02, 0x03, 0x04):
        effect_upload = fragment_a3(subtype, b"\x01\x02\x03")
        effect_index = len(effect_upload) - 1
        assert upload_ack_subtype(effect_upload, effect_index, "H6076", profile=profile) == subtype
        assert upload_ack_mode(effect_upload, effect_index, "H6076", profile=profile) is None
        ack = parse_command_ack_result(frame(f"a3{subtype:02x}00"), "H6076", profile=profile)
        assert ack.parser == "h617a_command_ack"
        assert upload_ack_success(ack.parsed, subtype) is True


def test_ack_uses_command_grammar_independently_of_video(monkeypatch):
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", command_grammar="H617A"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed.is_success
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", video_grammar="H6199"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed is None


@pytest.mark.parametrize("response", [None, "a10201", "a30200", "330200", "a10200"])
@pytest.mark.parametrize(
    "model,firmware,hardware",
    [
        ("H6125", "1.07.01", "1.00.04"),
        ("H6127", "1.01.20", "1.00.01"),
    ],
)
async def test_a1_upload_requires_its_own_positive_ack_before_activation(
    connected, response, model, firmware, hardware
):
    c, client = connected
    c.model = model
    c.pact_type, c.pact_code = 1, 2
    c.fw_version, c.hw_version = firmware, hardware
    c.profile = device_profile(model, 1, 2, firmware=c.fw_version, hardware=c.hw_version)
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    item = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    compiled = compile_application(item, c.model, profile=c.profile)
    packets = [build_power(True, c.model, profile=c.profile), *compiled.upload_packets]
    index = len(packets) - 1

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index] and response is not None:
            receive(client, frame(response))

    client.write_gatt_char.side_effect = write

    async def apply():
        await c.async_write_effect_sequence(
            packets,
            intent=ControlIntent.USER,
            require_upload_ack=DIY_ACK_EVIDENCE in compiled.evidence_codes,
            upload_ack_index=index,
            final_packet=compiled.activation_packet,
        )

    if response == "a10200":
        await apply()
        expected = [*packets, compiled.activation_packet]
    else:
        with pytest.raises((TimeoutError, RuntimeError)):
            await apply()
        expected = packets
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == expected
    assert c._field_revisions == {}


async def test_ordinary_ack_is_diagnostic_not_power_readback(connected):
    c, client = connected
    c.is_on = True
    receive(client, frame("330100"))
    assert c.is_on
    assert c._field_revisions == {}
    assert c.packet_log[-1]["reason"] == "command_ack_parsed"


@pytest.mark.parametrize("response", [None, MUSIC_NO, DIY_OK, frame("330100"), MUSIC_OK[:-1] + b"\xff"])
@pytest.mark.parametrize("preview", [False, True])
async def test_no_negative_unrelated_or_corrupt_ack_never_activates(connected, response, preview):
    c, client = connected
    packets, index = sequence()

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index] and response is not None:
            receive(client, response)

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kw: preview_writer(c, *args, **kw)} if preview else {}
    with pytest.raises((TimeoutError, RuntimeError)):
        await write_sequence(c, packets, index, **options)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == packets[: index + 1]
    assert c._upload_ack is None
    if preview:
        c._ensure_connected.assert_not_awaited()
        if response == MUSIC_NO:
            c._disconnect_locked.assert_not_awaited()
        else:
            c._disconnect_locked.assert_awaited_once_with(planned_release=True)


@pytest.mark.parametrize("preview", [False, True])
async def test_final_write_callback_race_and_state_boundaries(connected, preview):
    c, client = connected
    packets, index = sequence()
    states = [{"music_sensitivity": n + 10} for n in range(len(packets))]
    guards, progress = [], []

    def guard(n):
        assert c._upload_ack is None
        guards.append(n)

    async def write(_uuid, packet, **kwargs):
        n = packets.index(packet)
        assert c.music_sensitivity == n + 10
        assert guards == list(range(n + 1))
        if n == index:
            receive(client, MUSIC_OK)  # Before write_gatt_char returns.
            c.music_sensitivity = 99  # Fresh notification must survive the await.
        if n == index + 1:
            assert c._upload_ack is None

    async def progressed(n):
        if n == index + 1:
            assert c.music_sensitivity == 99
        progress.append(n)

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kw: preview_writer(c, *args, **kw)} if preview else {}
    await asyncio.wait_for(
        write_sequence(
            c, packets, index, packet_state_values=states, packet_write_guard=guard, progress=progressed, **options
        ),
        1,
    )
    assert progress == list(range(1, len(packets) + 1))
    assert c._upload_ack is None


@pytest.mark.parametrize("fault", ["early", "stale_subscription", "profile", "disconnect", "cancel", "transform"])
async def test_stale_early_disconnected_and_cancelled_uploads(connected, fault):
    c, client = connected
    packets, index = sequence()
    old_callback = client.start_notify.call_args.args[1]
    if fault == "stale_subscription":
        await c._start_notify()
    if fault == "transform":

        def transform(packet):
            if packet == packets[index]:
                receive(client, MUSIC_OK)  # Transform occurs before physical arming.
            return packet

        c.profile = replace(c.profile, outbound_transform=transform)

    async def write(_uuid, packet, **kwargs):
        if fault == "early" and packet == packets[0]:
            receive(client, MUSIC_OK)
        if packet == packets[index]:
            if fault == "stale_subscription":
                old_callback(None, bytearray(MUSIC_OK))
            elif fault == "profile":
                c._advance_profile_generation()
                receive(client, MUSIC_OK)
            elif fault == "disconnect":
                c._clear_client_state(client)
                old_callback(None, bytearray(MUSIC_OK))
            elif fault == "cancel":
                asyncio.current_task().cancel()
                await asyncio.sleep(0)

    client.write_gatt_char.side_effect = write
    with pytest.raises((TimeoutError, ValueError, BleakError, asyncio.CancelledError)):
        await write_sequence(c, packets, index)
    assert client.write_gatt_char.call_count == index + 1
    assert c._upload_ack is None


@pytest.mark.parametrize("ack_on_retry", [False, True])
@pytest.mark.parametrize("connected", ["H617F", "H617C"], indirect=True)
async def test_failed_final_attempt_discards_ack_and_retries_entire_upload(connected, monkeypatch, ack_on_retry):
    c, first = connected
    packets, index = sequence()
    second = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    connections = 0
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 2)

    async def connect():
        nonlocal connections
        connections += 1
        c._client = first if connections == 1 else second
        await c._start_notify()
        return c._client

    c._ensure_connected.side_effect = connect

    async def failed_write(_uuid, packet, **kwargs):
        if packet == packets[index]:
            receive(first, MUSIC_OK)
            raise BleakError("final physical attempt failed after callback")

    async def retry_write(_uuid, packet, **kwargs):
        receive(first, MUSIC_OK)  # Old-client callbacks must not unlock attempt two.
        if packet == packets[index] and ack_on_retry:
            receive(second, MUSIC_OK)

    first.write_gatt_char.side_effect = failed_write
    second.write_gatt_char.side_effect = retry_write
    if ack_on_retry:
        await write_sequence(c, packets, index)
    else:
        with pytest.raises(TimeoutError):
            await write_sequence(c, packets, index)
    assert [call.args[1] for call in first.write_gatt_char.call_args_list] == packets[: index + 1]
    assert [call.args[1] for call in second.write_gatt_char.call_args_list] == (
        packets if ack_on_retry else packets[: index + 1]
    )
    assert c._upload_ack is None


@pytest.mark.parametrize("index", [None, -1, 0, 3, True])
async def test_invalid_upload_boundary_fails_before_connection_or_writes(connected, index):
    c, client = connected
    packets, _ = sequence()
    with pytest.raises(ValueError):
        await write_sequence(c, packets, index)
    c._ensure_connected.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("kind", ["diy", "music"])
@pytest.mark.parametrize("positive", [False, True])
@pytest.mark.parametrize("power", [False, True])
async def test_real_preview_path_upload_ack_then_own_selector(connected, hass, monkeypatch, kind, positive, power):
    c, client = connected
    c.is_on = power
    monkeypatch.setattr(
        c,
        "async_prepare_static_baseline",
        AsyncMock(
            return_value=PriorControlState(
                mode="colour",
                is_on=power,
                brightness_pct=23,
                rgb_color=(17, 34, 51),
                static_rgb_known=True,
                segment_colors=((17, 34, 51),) * c.profile.segment_count,
                segment_brightness=(23,) * c.profile.segment_count,
            )
        ),
    )
    c.async_preview_preflight = AsyncMock()
    c.async_observe_effect = AsyncMock(return_value=True)
    if kind == "diy":
        content = resolve_catalogue_template("H617A", "template:native-diy:507").content
        final = compile_effect(LibraryItem.new("Stack", content), "H617A").upload_packets[-1]
        response = DIY_OK if positive else DIY_NO
    else:
        content = MusicProfile("H617A", "bloom", 42)
        from custom_components.ha_govee_led_ble.music_commands import prepare_music_profile_writes

        writes = prepare_music_profile_writes("H617A", "bloom", 42, None, False, {}, profile=c.profile)
        assert writes.last_upload is not None
        final = writes[writes.last_upload][0]
        response = MUSIC_OK if positive else MUSIC_NO
    written = []

    async def write(_uuid, packet, **kwargs):
        written.append(packet)
        if packet == final:
            receive(client, response)

    client.write_gatt_char.side_effect = write
    manager, _ = await _manager(hass, monkeypatch, c)
    events = []
    owner = object()
    session = _open(manager, owner, events)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-16T00:00:00Z",
            item=LibraryItem.new("Preview", content),
        )
        await asyncio.wait_for(manager.async_wait_idle("entry-a"), 2)
        assert final in written
        if positive:
            assert events[-1].phase in {PreviewPhase.CONFIRMED, PreviewPhase.UNCONFIRMED}
            assert written.index(final) < len(written) - 1
            if kind == "diy":
                assert written[-1] == build_scene_activation("H617A", 507)
        else:
            assert events[-1].phase == PreviewPhase.FAILED
            assert written[-1] == final
        assert c._upload_ack is None
        c._ensure_connected.assert_not_awaited()
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("positive", [False, True])
async def test_saved_native_diy_apply_uses_ack_gate(selection_ready, monkeypatch, positive):
    c, client = selection_ready
    c.is_on = True
    item = LibraryItem.new("Stack", resolve_catalogue_template("H617A", "template:native-diy:507").content)
    compiled = compile_effect(item, "H617A")
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=True))
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=True))

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, DIY_OK if positive else DIY_NO)

    client.write_gatt_char.side_effect = write
    if positive:
        await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
    else:
        with pytest.raises(RuntimeError, match="rejected A3"):
            await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
    sent = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert sent == list(compiled.packets if positive else compiled.upload_packets)
    assert c._upload_ack is None


@pytest.mark.parametrize("connected", ["H6199"], indirect=True)
@pytest.mark.parametrize("path", ["saved", "snapshot", "preview"])
@pytest.mark.parametrize("power", [False, True])
@pytest.mark.parametrize("verdict", ["accepted", "rejected", "missing", "disconnect", "subscription"])
async def test_palette_public_paths_wait_for_upload_verdict(
    selection_ready, hass, monkeypatch, path, power, verdict, virtual_clock
):
    c, client = selection_ready
    c.is_on = power
    item = LibraryItem.new("Fade", PaletteDiyEffect(c.model, 0, 0, 20, ((30, 0, 0), (0, 30, 0))))
    compiled = compile_effect(item, c.model, diy_code=73, profile=c.profile)
    destination_consent = approve_diy_destination_operation(c, "entry-a", 73)
    uploaded = asyncio.Event()
    monkeypatch.setattr(c, "async_preview_preflight", AsyncMock())
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=True))
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=None))
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 3)

    async def reconnect():
        if c._client is not client:
            c._client = client
            await c._start_notify()
            c._observe_pact(2, 1)
            c._observe_identity_field("fw_version", "1.10.04")
            c._observe_identity_field("hw_version", "3.02.01")
        return client

    c._ensure_connected.side_effect = reconnect

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[-1]:
            uploaded.set()

    client.write_gatt_char.side_effect = write
    manager = None
    if path == "preview":
        manager, _ = await _manager(hass, monkeypatch, c)
        events = []
        owner = object()
        session = _open(manager, owner, events)
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-16T00:00:00Z",
            item=item,
            diy_code=73,
            destination_consent=destination_consent,
        )
        task = asyncio.create_task(manager.async_wait_idle("entry-a"))
    else:
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        engine = EffectDeploymentEngine(repository)
        monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
        monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
        monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=False))
        apply = engine.async_apply_saved if path == "saved" else engine.async_apply_snapshot
        task = asyncio.create_task(
            apply(
                c,
                item,
                config_entry_id="entry-a",
                updated_at="2026-09-16T00:00:00Z",
                diy_code=73,
                destination_consent=destination_consent,
            )
        )
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        expected = [*([] if power else [build_power(True, c.model)]), *compiled.upload_packets]
        assert [call.args[1] for call in client.write_gatt_char.call_args_list] == expected
        assert c._upload_ack is not None and not c._upload_ack.future.done()
        assert not task.done()
        for unrelated in (frame("330500"), DIY_OK, frame("a30400")[:-1] + b"\xff"):
            receive(client, unrelated)
            assert not c._upload_ack.future.done()
        if verdict == "disconnect":
            c._clear_client_state(client)
        elif verdict == "subscription":
            await c._start_notify()
        elif verdict != "missing":
            receive(client, frame("a30400" if verdict == "accepted" else "a30401"))
        if verdict == "accepted" or path == "preview":
            result = await asyncio.wait_for(task, 2)
            if path == "preview":
                assert events[-1].phase is (PreviewPhase.WRITTEN if verdict == "accepted" else PreviewPhase.FAILED)
            else:
                assert result.phase is DeploymentPhase.UNCERTAIN
                assert result.error_code == "device_state_unconfirmed"
                assert result.verification_confidence.value == "unknown"
                c.async_restore_effect_control_state.assert_not_awaited()
        else:
            error = (
                ModeTransitionSupersededError
                if verdict == "subscription"
                else BleakError
                if verdict == "disconnect"
                else TimeoutError
                if verdict == "missing"
                else RuntimeError
            )
            with pytest.raises(error):
                await asyncio.wait_for(task, 2)
        if verdict == "accepted":
            expected.append(compiled.activation_packet)
        else:
            c.async_observe_effect.assert_not_awaited()
            if verdict == "missing" and path != "preview":
                c.async_restore_effect_control_state.assert_not_awaited()
                if not power:
                    expected.append(build_power(False, c.model))
        assert [call.args[1] for call in client.write_gatt_char.call_args_list] == expected
        assert c._upload_ack is None
        assert c._field_revisions == {}
        if verdict == "missing":
            c._disconnect_locked.assert_awaited_once_with(planned_release=True)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if manager is not None:
            await manager.async_shutdown()


@pytest.mark.parametrize("fault", [None, "kind", "palette_length", "chunk_count", "incomplete"])
def test_palette_ack_boundary_requires_complete_generated_diy(fault):
    item = LibraryItem.new("Fade", PaletteDiyEffect("H6199", 0, 0, 20, ((30, 0, 0), (0, 30, 0))))
    compiled = compile_effect(item, "H6199", diy_code=73)
    envelope = bytearray(reassemble_a3(compiled.upload_packets))
    if fault == "kind":
        envelope[2] = 1
    elif fault == "palette_length":
        envelope[6] = 5
    elif fault == "chunk_count":
        envelope[1] = 3
        envelope.extend(bytes(17))
    packets = fragment_a3_envelope(bytes(envelope))
    index = 0 if fault == "incomplete" else len(packets) - 1
    if fault is None:
        assert upload_ack_subtype(packets, index, "H6199") == compiled.upload_subtype
    else:
        with pytest.raises(ValueError):
            upload_ack_subtype(packets, index, "H6199")


@pytest.mark.parametrize("connected", ["H617F"], indirect=True)
@pytest.mark.parametrize("fault", ["disconnect", "subscription"])
async def test_completed_upload_with_lost_verdict_does_not_replay(connected, monkeypatch, fault):
    c, client = connected
    packets, index = sequence()
    uploaded = asyncio.Event()
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 3)

    async def write(_uuid, packet, **_kwargs):
        if packet == packets[index]:
            uploaded.set()

    async def reconnect():
        c._client = client
        await c._start_notify()
        return client

    c._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(write_sequence(c, packets, index))
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        assert c._upload_ack is not None and not c._upload_ack.future.done()
        if fault == "disconnect":
            c._clear_client_state(client)
        else:
            await c._start_notify()
        with pytest.raises(ModeTransitionSupersededError if fault == "subscription" else BleakError):
            await asyncio.wait_for(task, 2)
        assert c._ensure_connected.await_count == 1
        assert [call.args[1] for call in client.write_gatt_char.call_args_list] == packets[: index + 1]
        assert c._upload_ack is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("path", ["saved", "preview"])
@pytest.mark.parametrize("ack", ["accepted", "rejected", "missing"])
async def test_workshop_public_paths_require_upload_ack(selection_ready, hass, monkeypatch, path, ack):
    c, client = selection_ready
    c.model = "H6125"
    c.profile = device_profile("H6125", 10, 2, firmware="3.04.37", hardware="3.01.10")
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    c.is_on = True
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H6125"))
    compiled = compile_effect(item, c.model, profile=c.profile)
    monkeypatch.setattr(c, "async_preview_preflight", AsyncMock())
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=True))

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1] and ack != "missing":
            receive(client, DIY_OK if ack == "accepted" else DIY_NO)

    client.write_gatt_char.side_effect = write
    if path == "saved":
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        engine = EffectDeploymentEngine(repository)
        monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=(False, None)))
        monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
        monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=False))
        if ack == "accepted":
            result = await engine.async_apply_saved(
                c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z"
            )
            assert result.phase is DeploymentPhase.CONFIRMED
        else:
            with pytest.raises(TimeoutError if ack == "missing" else RuntimeError):
                await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
            assert repository.snapshot().records[-1].phase is DeploymentPhase.UNCERTAIN
    else:
        manager, _ = await _manager(hass, monkeypatch, c)
        events = []
        owner = object()
        session = _open(manager, owner, events)
        try:
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-09-16T00:00:00Z",
                item=item,
            )
            await asyncio.wait_for(manager.async_wait_idle("entry-a"), 2)
            assert events[-1].phase in (
                {PreviewPhase.CONFIRMED, PreviewPhase.UNCONFIRMED} if ack == "accepted" else {PreviewPhase.FAILED}
            )
        finally:
            await manager.async_shutdown()
    sent = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert sent == list(compiled.packets if ack == "accepted" else compiled.upload_packets)
    if ack != "accepted":
        c.async_observe_effect.assert_not_awaited()
    assert c._upload_ack is None


@pytest.mark.parametrize(
    "fault", ["cancel_wait", "disconnect_wait", "profile_wait", "subscription_wait", "write_error", "guard_error"]
)
async def test_preview_failure_cleans_pending_without_reconnect(connected, monkeypatch, fault):
    c, client = connected
    packets, index = sequence()
    final_written = asyncio.Event()
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index]:
            final_written.set()
            if fault == "write_error":
                receive(client, MUSIC_OK)
                raise BleakError("final write failed")

    def guard(n):
        if n == index and fault == "guard_error":
            receive(client, MUSIC_OK)
            raise ValueError("guard rejected final attempt")

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        write_sequence(
            c,
            packets,
            index,
            packet_write_guard=guard,
            writer=lambda *args, **kw: preview_writer(c, *args, **kw),
        )
    )
    if fault.endswith("_wait"):
        await asyncio.wait_for(final_written.wait(), 1)
        pending = c._upload_ack.future
        if fault == "cancel_wait":
            task.cancel()
        elif fault == "disconnect_wait":
            c._clear_client_state(client)
        elif fault == "profile_wait":
            c._advance_profile_generation()
        else:
            await c._start_notify()
        if fault != "cancel_wait":
            assert pending.done()
        error = (
            asyncio.CancelledError
            if fault == "cancel_wait"
            else ModeTransitionSupersededError
            if fault == "subscription_wait"
            else ValueError
            if fault == "profile_wait"
            else BleakError
        )
        with pytest.raises(error):
            await asyncio.wait_for(task, 1)
        if fault == "cancel_wait":
            assert pending.cancelled()
        else:
            assert isinstance(pending.exception(), BleakError if fault == "subscription_wait" else error)
    else:
        with pytest.raises(BleakError if fault == "write_error" else ValueError):
            await task
    assert client.write_gatt_char.call_count == index + (fault != "guard_error")
    assert c._upload_ack is None
    c._ensure_connected.assert_not_awaited()
    if fault == "cancel_wait":
        c._disconnect_locked.assert_awaited_once_with(planned_release=True)
    else:
        c._disconnect_locked.assert_not_awaited()
