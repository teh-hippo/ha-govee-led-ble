"""Optional music palettes survive documents and writes without claiming readback."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import CompatibilityState, compatibility, compile_music_profile
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    ObservationConfidence,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    MusicProfile,
    effect_content_from_dict,
    effect_content_hash,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_persistence_validation import EffectStorageError
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase, PreviewWriteDisposition
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters import H6099MusicParameters
from custom_components.ha_govee_led_ble.generated_protocol_adapter import MusicBody, build_brightness
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.transport import reassemble_a3
from tests.test_effect_preview import _manager, _open
from tests.test_h6099_music import frame
from tests.test_music_commands import _music_transport

PALETTE = ((12, 34, 56), (78, 90, 123))


def test_absent_palette_document_and_compiled_hashes_unchanged():
    content = MusicProfile("H6099", "bloom", 42)
    raw = effect_content_to_dict(content)
    assert raw == {
        "kind": "music_profile",
        "model": "H6099",
        "mode": "bloom",
        "sensitivity": 42,
        "colour": None,
        "calm": None,
        "parameters": {},
    }
    assert effect_content_hash(content) == "2f4ed723d6c2d4ea08d067d52da6dd4a046b80b65dfff51217e1ca277460dd3a"
    compiled = compile_music_profile(LibraryItem.new("Bloom", content), "H6099")
    assert compiled.artifact_sha256 == "86b7bbd8ebc78eb4d59b5bb2b8840d0eeba9a46626e0eb311dc6f031f4a7f0a0"
    assert effect_content_from_dict(raw) == content
    authored = replace(content, palette=PALETTE)
    assert effect_content_to_dict(authored)["palette"] == [list(rgb) for rgb in PALETTE]
    assert effect_content_from_dict(effect_content_to_dict(authored)) == authored
    assert effect_content_hash(authored) != effect_content_hash(content)
    assert (
        compile_music_profile(LibraryItem.new("Bloom", authored), "H6099").artifact_sha256 != compiled.artifact_sha256
    )


@pytest.mark.parametrize("palette", [None, [], [[True, 2, 3]], [[-1, 2, 3]], [[256, 2, 3]], [[1, 2]], [[1, 2, 3]] * 9])
def test_present_invalid_palette_fails_document_validation(palette):
    raw = effect_content_to_dict(MusicProfile("H6099", "bloom", 42))
    with pytest.raises(ValueError):
        effect_content_from_dict({**raw, "palette": palette})


@pytest.mark.parametrize(
    "model,mode,ic,available",
    [
        ("H6099", "bloom", None, True),
        ("H6099", "piano_keys", None, False),
        ("H6099", "piano_keys", 60, True),
        ("H6099", "rhythm", None, False),
        ("H617A", "bloom", None, True),
    ],
)
def test_variant_availability_matches_catalogue_and_compiler(model, mode, ic, available):
    profile = replace(get_profile(model), physical_ic_count=ic)
    item = LibraryItem.new("Palette", MusicProfile(model, mode, 42, palette=PALETTE))
    settings = MODEL_EFFECT_CATALOGUES[model].to_dict(profile=profile)["music_settings"][mode]
    assert ("palette" in settings) is available
    assert (compatibility(item, model, profile=profile).state is CompatibilityState.COMPATIBLE) is available
    if available:
        compiled = compile_music_profile(item, model, profile=profile)
        parsed = (
            MusicBody.from_bytes(reassemble_a3(compiled.packets[1:-1]))
            if model == "H617A"
            else H6099MusicParameters.from_bytes(reassemble_a3(compiled.packets[1:-1])[3:])
        )
        parsed._read()
        assert [(rgb.red, rgb.green, rgb.blue) for rgb in parsed.palette] == list(PALETTE)
        expectations, confidence = compiled_observation(compiled, profile=profile)
        assert "music_palette" not in expectations and confidence is ObservationConfidence.MODE_MATCH
    else:
        with pytest.raises(ValueError):
            compile_music_profile(item, model, profile=profile)


@pytest.mark.parametrize("route", ["native", "studio", "preview"])
async def test_apply_recovery_and_retained_palette_are_not_readback(hass, route):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    compiled = compile_music_profile(
        LibraryItem.new("Palette", MusicProfile("H6099", "bloom", 42, palette=PALETTE)), "H6099"
    )
    coordinator.music_sensitivity = 42

    async def preview_writer(packet, *, state_values=None, write_guard=None):
        await coordinator._async_write_packet(
            coordinator._client, packet, arm_expected=True, state_values=state_values, before_write=write_guard
        )

    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        if route == "native":
            await coordinator.async_select_music_slug("bloom", palette=PALETTE)
        else:
            await async_apply_compiled_profile(
                coordinator, compiled, writer=preview_writer if route == "preview" else None
            )
        assert [call.args[1] for call in physical.await_args_list] == list(compiled.packets)
        assert coordinator.music_palette == PALETTE
        state = coordinator.capture_effect_control_state()
        assert state.music_palette == PALETTE
        restored = PriorControlState.from_dict(state.to_dict())
        assert restored == state
        assert "music_palette" not in coordinator._field_revisions
        await coordinator.async_select_music_slug("bloom")
        assert coordinator.music_palette != PALETTE
        physical.reset_mock()
        coordinator.refresh_state.return_value = True
        assert not await coordinator.async_restore_effect_control_state(restored, overwritten_diy_code=None)
        assert [call.args[1] for call in physical.await_args_list] == [
            build_brightness(restored.brightness_pct, coordinator.model),
            *compiled.packets,
        ]
        assert coordinator.music_palette == PALETTE
        assert "music_palette" not in coordinator._expected_state


@pytest.mark.parametrize("palette", [None, (), ((True, 2, 3),), ((256, 2, 3),)])
async def test_unknown_or_invalid_recovery_never_sends_default_palette(hass, palette):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    before = coordinator.capture_effect_control_state()
    with _music_transport(coordinator) as physical:
        coordinator.refresh_state.return_value = True
        if palette is None:
            state = replace(before, mode="music", is_on=True, music_mode="bloom")
            assert state.music_palette is None and "music_palette" not in state.to_dict()
            assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        else:
            with pytest.raises(EffectStorageError, match="prior music palette"):
                replace(before, mode="music", is_on=True, music_mode="bloom", music_palette=palette)
        physical.assert_not_awaited()
        coordinator.refresh_state.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before


@pytest.mark.parametrize("index", [0, 1, 2, 3])
async def test_guards_and_fresh_notifications_do_not_install_unattempted_palette(hass, index):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    coordinator.music_mode = "bloom"
    old = ((1, 2, 3),)
    coordinator._music_palette = ("bloom", old)
    compiled = compile_music_profile(
        LibraryItem.new("Palette", MusicProfile("H6099", "bloom", 42, palette=PALETTE)), "H6099"
    )

    def reject(packet):
        if packet == compiled.packets[index]:
            raise ValueError("rejected before physical attempt")
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=reject)
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        with pytest.raises(ValueError, match="before physical"):
            await async_apply_compiled_profile(coordinator, compiled)
        assert physical.await_count == index
    assert coordinator.music_palette == (old if index <= 1 else None)
    coordinator._expected_state.clear()
    coordinator._notify_callback(None, bytearray(frame("aa05130611")))
    assert coordinator.music_palette is None
    coordinator._notify_callback(None, bytearray(frame("aa05133011")))
    assert coordinator.music_palette is None
    assert "music_palette" not in coordinator._field_revisions


async def test_fresh_notification_during_final_await_is_not_overwritten(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    compiled = compile_music_profile(
        LibraryItem.new("Palette", MusicProfile("H6099", "bloom", 42, palette=PALETTE)), "H6099"
    )

    async def transmit(uuid, packet, *, response):
        if packet == compiled.packets[-1]:
            coordinator._expected_state.clear()
            coordinator._notify_callback(None, bytearray(frame("aa05130611")))

    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        physical.side_effect = transmit
        await async_apply_compiled_profile(coordinator, compiled)
    assert coordinator.music_mode == "rolling" and coordinator.music_palette is None


def test_palette_cannot_be_silently_discarded():
    with pytest.raises(ValueError, match="requires a parameter upload"):
        prepare_music_request("H6099", "bloom", 42, None, False, {}, palette=PALETTE, include_parameters=False)


@pytest.mark.parametrize("stale", [False, True])
async def test_public_preview_preserves_palette_and_geometry_guards(hass, monkeypatch, stale):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    coordinator.profile = replace(coordinator.profile, physical_ic_count=60)
    item = LibraryItem.new("Palette", MusicProfile("H6099", "piano_keys", 42, palette=PALETTE))
    compiled = compile_music_profile(item, "H6099", profile=coordinator.profile)
    events = []
    manager, _ = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session = _open(manager, owner, events)

    async def preflight(**kwargs):
        if stale:
            coordinator.profile = replace(coordinator.profile, physical_ic_count=None)

    try:
        with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
            monkeypatch.setattr(coordinator, "async_preview_preflight", AsyncMock(side_effect=preflight))
            monkeypatch.setattr(coordinator, "async_observe_effect", AsyncMock(return_value=True))
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-09-15T00:00:00Z",
                item=item,
            )
            await manager.async_wait_idle("entry-a")
            if stale:
                assert events[-1].phase is PreviewPhase.FAILED
                assert events[-1].write_disposition is PreviewWriteDisposition.NOT_STARTED
                physical.assert_not_awaited()
                assert coordinator.music_palette is None
            else:
                assert events[-1].phase is PreviewPhase.CONFIRMED
                assert events[-1].confidence is ObservationConfidence.MODE_MATCH
                assert [call.args[1] for call in physical.await_args_list] == list(compiled.packets)
                assert coordinator.music_palette == PALETTE
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("saved", [False, True])
async def test_public_apply_persists_palette_and_never_claims_settings_match(hass, saved):
    backend = await EffectBackend.async_create(hass)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    item = LibraryItem.new("Palette", MusicProfile("H6099", "bloom", 42, palette=PALETTE))
    compiled = compile_music_profile(item, "H6099")
    if saved:
        await backend.library.async_create(item)
        assert backend.library.snapshot().items[0].content.palette == PALETTE
    with (
        _music_transport(coordinator) as physical,
        patch.object(coordinator, "_encryption", None),
        patch.object(coordinator, "async_observe_effect", AsyncMock(return_value=True)),
    ):

        async def refresh(**kwargs):
            coordinator._notify_callback(None, bytearray(frame("aa0101")))
            coordinator._notify_callback(None, bytearray(frame("aa0464")))
            coordinator._notify_callback(None, bytearray(frame("aa0513062a")))
            return True

        coordinator.refresh_state.side_effect = refresh
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
        assert result.verification_confidence is ObservationConfidence.MODE_MATCH
        assert [call.args[1] for call in physical.await_args_list][-len(compiled.packets) :] == list(compiled.packets)
        assert coordinator.music_palette == PALETTE


async def test_compiled_palette_mutation_is_rejected_before_writes(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    compiled = compile_music_profile(
        LibraryItem.new("Palette", MusicProfile("H6099", "bloom", 42, palette=PALETTE)), "H6099"
    )
    before = coordinator.capture_effect_control_state()
    with _music_transport(coordinator) as physical:
        with pytest.raises(ValueError, match="request changed"):
            await async_apply_compiled_profile(coordinator, replace(compiled, palette=((1, 2, 3),)))
        physical.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before
