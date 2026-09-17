"""Exact H6102 candidate, independent revision gates and runtime admission."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import (
    MODEL_EFFECT_CATALOGUES,
    resolve_catalogue_template,
    validate_effect_eligibility,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    compile_application,
    resolve_diy_code,
    validate_compiled_geometry,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    EffectPair,
    LayeredEffect,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    PaintedEffect,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_scene_activation, parse_music_parameters
from custom_components.ha_govee_led_ble.h6102_capabilities import resolve_h6102_capabilities
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.music_commands import edit_music_body, prepare_music_request
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_h6199_native_controls import frame
from tests.test_h6199_pact1 import advertise


@pytest.mark.parametrize("firmware", [None, "1.03.00", "1.03.01", "3.02.02", "9.99.99"])
def test_firmware_never_selects_pact(firmware):
    profile = device_profile("H6102", None, None, firmware=firmware)
    assert profile.command_operations == frozenset({"power", "brightness"})
    assert profile.requires_notifications and profile.can_read(ReadDomain.FIRMWARE)
    assert not profile.supports_rgb and not profile.supports_scenes


@pytest.mark.parametrize("pact_code", [1, 2])
def test_modern_candidate_exact_catalogue_and_no_donor_policy(pact_code):
    profile = device_profile("H6102", 10, pact_code)
    assert profile.supports_rgb and profile.supports_scenes and profile.supports_custom_effects
    assert profile.supports_color_temperature and profile.supports_segments
    assert profile.command_grammar == profile.effect_grammar == "H617A"
    assert profile.status_grammar == "H6102"
    assert (profile.segment_count, profile.segment_group_count) == (15, 5)
    assert profile.physical_ic_count is None and profile.music_requires_upload_ack
    assert len(profile.music_modes) == 4
    assert len(SCENE_ENTRIES["H6102"]) == 240
    catalogue = MODEL_EFFECT_CATALOGUES["H6102"]
    assert sum("native-diy" in template.id for template in catalogue.templates) == 7
    assert {family.family: tuple(v.variant for v in family.variations) for family in catalogue.effects} == {
        0: (0, 1, 2),
        1: (0, 2),
        2: (0, 1, 2),
        3: (3, 4, 5),
        8: (9, 10),
        9: (9, 10),
        10: (0,),
        4: (8, 6, 7),
    }
    chase = SingleEffect(family=10, variant=0, speed=1, palette=((1, 2, 3),) * 3)
    validate_effect_eligibility(chase, "H6102", profile=profile)
    with pytest.raises(ValueError, match="palette"):
        validate_effect_eligibility(replace(chase, palette=((1, 2, 3),) * 4), "H6102", profile=profile)


@pytest.mark.parametrize(
    ("hardware", "firmware", "modes"),
    [
        (None, "3.02.02", 4),
        ("3.02.01", None, 4),
        ("2.01.01", "2.03.99", 4),
        ("2.01.01", "2.04.00", 11),
        ("3.02.01", "3.00.99", 4),
        ("3.02.01", "3.01.00", 11),
        ("1.00.03", "3.02.02", 4),
        ("3.04.01", "3.02.02", 4),
    ],
)
def test_music_condition_is_independent_of_rgb_and_diy(hardware, firmware, modes):
    profile = device_profile("H6102", 10, 1, firmware=firmware, hardware=hardware)
    assert len(profile.music_modes) == modes
    assert profile.supports_rgb and profile.supports_custom_effects and profile.supports_scenes


def test_exact_h6102_catalogue_compiles_without_foreign_scene_identity():
    profile = device_profile("H6102", 10, 1, firmware="3.02.02", hardware="3.02.01")
    for scene in SCENE_ENTRIES["H6102"]:
        item = LibraryItem.new(scene.name, BuiltinScene(CatalogueRef("H6102", scene.scene_id, scene.effect_id)))
        assert compile_application(item, "H6102", profile=profile).packets
    for template in MODEL_EFFECT_CATALOGUES["H6102"].templates:
        if isinstance(template.content, PaintedEffect):
            with pytest.raises(ValueError, match="physical IC"):
                resolve_catalogue_template("H6102", template.id, profile=profile)
            continue
        item = LibraryItem.new(template.label, template.content)
        assert compile_application(
            item,
            "H6102",
            diy_code=resolve_diy_code(item, model="H6102"),
            profile=profile,
        ).packets


def test_physical_painted_and_advanced_selector_use_exact_contracts():
    profile = replace(MODEL_PROFILES["H6102"], physical_ic_count=60)
    template = resolve_catalogue_template("H6102", "template:paint", profile=profile)
    assert isinstance(template.content, PaintedEffect)
    painted = replace(template.content, segments=(None,) * 59 + ((1, 2, 3),))
    compiled = compile_application(LibraryItem.new("Paint", painted), "H6102", diy_code=800, profile=profile)
    assert compiled.physical_ic_count == 60
    assert "native_diy_positive_ack_required" in compiled.evidence_codes
    with pytest.raises(ValueError):
        compile_application(LibraryItem.new("Paint", painted), "H6102", diy_code=800)
    native = resolve_catalogue_template("H6102", "template:native-diy:504").content
    assert isinstance(native, LayeredEffect)
    assert all(layer.selection.quantity == 12 for layer in native.layers)
    bloom = resolve_catalogue_template("H6102", "template:native-diy:506").content
    assert isinstance(bloom, LayeredEffect)
    assert [layer.selection.quantity for layer in bloom.layers[2:]] == [30, 30]
    advanced = compile_application(LibraryItem.new("Studio", replace(native, native_diy=None)), "H6102")
    assert advanced.activation_packet == build_scene_activation("H6102", 402)
    assert advanced.expected_effect is None and advanced.selector_kind == "scene"


def test_single_and_mixed_have_independent_rate_ranges():
    single = SingleEffect(0, 0, 0, ((1, 2, 3),))
    with pytest.raises(ValueError, match="speed"):
        validate_effect_eligibility(single, "H6102")
    validate_effect_eligibility(MultiEffect((EffectPair(0, 0),), 0, single.palette), "H6102")
    validate_effect_eligibility(SingleEffect(4, 8, 100, single.palette), "H6102")


def test_native_music_geometry_and_upload_order():
    unknown = MODEL_PROFILES["H6102"]
    known = replace(unknown, physical_ic_count=60)
    for mode in unknown.music_modes[:4]:
        assert len(prepare_music_request("H6102", mode, 50, None, False, {}, profile=unknown)) == 2
    for mode in ("bloom", "shiny"):
        packets = prepare_music_request("H6102", mode, 50, None, False, {}, profile=unknown)
        assert packets[1][0] == 0xA3 and packets[-1][0] == 0x33
    for mode in ("separation", "hopping", "piano_keys", "fountain", "day_and_night"):
        assert len(prepare_music_request("H6102", mode, 50, None, False, {}, profile=unknown)) == 2
        assert len(prepare_music_request("H6102", mode, 50, None, False, {}, profile=known)) > 2
    piano = music_variant(known, 0x34)
    assert piano.parameters[0].default == 15
    daynight = music_variant(known, 0x37)
    assert daynight.parameters[1].max_value == 100
    assert parse_music_parameters(daynight, daynight.template).tail.speed == 20
    hopping = music_variant(unknown, 0x33)
    edited = edit_music_body(hopping.template, "hopping", {"relative_brightness": 17}, profile=unknown)
    assert parse_music_parameters(hopping, edited).tail.rel_brightness == 17
    separation = music_variant(unknown, 0x32)
    with pytest.raises(ValueError, match="unavailable"):
        edit_music_body(separation.template, "separation", {"gradient": True}, profile=unknown)


async def test_two_devices_and_profile_downgrade_reject_inflight(hass, monkeypatch):
    modern = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    legacy = GoveeBLECoordinator(hass, "11:22:33:44:55:77", "H6102", configuration_url="studio", h6102_pact="1/1")
    assert modern.configuration_url == "studio" and legacy.configuration_url is None
    assert GoveeBLELight(legacy).supported_color_modes == {ColorMode.BRIGHTNESS}
    item = LibraryItem.new(name="H6102 test", content=SingleEffect(family=0, variant=1, speed=50, palette=((1, 2, 3),)))
    compiled = compile_application(item, modern.model, diy_code=24, profile=modern.profile)
    assert compiled_observation(compiled, profile=modern.profile)[0] == {"is_on": True, "diy_code": compiled.diy_code}
    with pytest.raises(ValueError):
        compile_application(item, legacy.model, diy_code=24, profile=legacy.profile)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    modern._client = client

    async def connect():
        advertise(modern, 1)
        return client

    monkeypatch.setattr(modern, "_ensure_connected", connect)
    with pytest.raises(ValueError):
        await modern.async_write_effect_sequence(compiled.packets, intent=ControlIntent.APPLY)
    assert modern.control_write_attempts == 0
    client.write_gatt_char.assert_not_awaited()
    with pytest.raises(ValueError):
        validate_compiled_geometry(compiled, modern.profile)


def test_new_music_compile_revoked_without_revoking_scenes():
    profile = device_profile("H6102", 10, 1, firmware="3.02.02", hardware="3.02.01")
    item = LibraryItem.new(name="Music", content=MusicProfile(model="H6102", mode="bloom", sensitivity=50))
    compiled = compile_application(item, "H6102", profile=profile)
    old = device_profile("H6102", 10, 1, firmware="3.00.99", hardware="3.02.01")
    with pytest.raises(ValueError, match="music mode"):
        validate_compiled_geometry(compiled, old)
    assert old.supports_scenes


async def test_physical_music_selector_rechecks_effective_roster(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    profile = device_profile("H6102", 10, 1, firmware="3.02.02", hardware="3.02.01")
    item = LibraryItem.new("Music", MusicProfile(model="H6102", mode="bloom", sensitivity=50))
    compiled = compile_application(item, "H6102", profile=profile)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    with pytest.raises(ValueError, match="music mode"):
        await coordinator._async_write_packet(client, compiled.packets[-1], arm_expected=True)
    assert coordinator.control_write_attempts == 0 and not coordinator._expected_state
    client.write_gatt_char.assert_not_awaited()


async def test_reconnect_invalidates_revision_grants_before_connect_yields(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    coordinator.fw_version, coordinator.hw_version = "3.02.02", "3.02.01"
    coordinator._resolve_device_profile()
    assert "bloom" in coordinator.profile.music_modes
    generation = coordinator._profile_generation

    async def connect(*args, **kwargs):
        assert coordinator.fw_version is coordinator.hw_version is None
        assert len(coordinator.profile.music_modes) == 4
        assert coordinator.profile.supports_scenes
        assert coordinator._profile_generation > generation
        raise BleakError("offline")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    with pytest.raises(BleakError, match="offline"):
        await coordinator._ensure_connected()


def test_observed_pact_overrides_owner_context(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    advertise(coordinator, 1)
    assert not coordinator.profile.supports_rgb
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={}))
    assert not coordinator.profile.supports_rgb
    assert MODEL_PROFILES["H6102"].supports_rgb
    assert resolve_h6102_capabilities("3.02.02", "configured").capability_resolution_reason == "pact_unknown"


def test_identity_change_invalidates_generation_even_with_same_roster(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    coordinator.fw_version, coordinator.hw_version = "3.02.02", "3.02.01"
    coordinator._resolve_device_profile()
    profile, generation = coordinator.profile, coordinator._profile_generation
    coordinator.fw_version = "3.02.03"
    coordinator._resolve_device_profile()
    assert coordinator.profile == profile
    assert coordinator._profile_generation == generation + 1


@pytest.mark.parametrize("confirm", [True, False])
async def test_saved_apply_requires_fresh_exact_h6102_readback(hass, monkeypatch, confirm):
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6102",
        configuration_url="studio",
        h6102_pact="10/1",
    )
    selected = False

    async def transmit(_uuid, packet, **kwargs):
        nonlocal selected
        if packet[:3] == bytes.fromhex("33050a"):
            selected = True
        if packet[0] == 0xA3 and packet[1] == 0xFF:
            coordinator._notify_callback(None, bytearray(frame("a30400")))
        if packet[:2] == bytes.fromhex("aa01"):
            coordinator._notify_callback(None, bytearray(frame("aa0101")))
        elif packet[:2] == bytes.fromhex("aa04"):
            coordinator._notify_callback(None, bytearray(frame("aa0432")))
        elif packet[:2] == bytes.fromhex("aa05"):
            # DIY code 24 is read back, not inferred from a write or ACK.
            prefix = "aa050a1800" if selected and confirm else "aa051500"
            coordinator._notify_callback(None, bytearray(frame(prefix)))
        elif packet[:2] == bytes.fromhex("aaa5"):
            page = packet[2]
            coordinator._notify_callback(None, bytearray(frame("aaa5" + bytes([page, *([100, 1, 2, 3] * 3)]).hex())))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    # Exercise the real setup refresh and the same engine used by saved Apply.
    await coordinator._async_update_data()
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    result = await EffectDeploymentEngine(repository).async_apply_saved(
        coordinator,
        LibraryItem.new("Saved H6102", SingleEffect(0, 1, 50, ((1, 2, 3),))),
        config_entry_id="h6102",
        updated_at="2026-09-17T00:00:00Z",
    )
    assert (result.phase is DeploymentPhase.CONFIRMED) is confirm
    if confirm:
        assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
        assert coordinator.diy_code == 24
    assert coordinator._field_revisions["color_mode"] >= 2
    assert coordinator._domain_revisions[ReadDomain.SEGMENTS] >= 5


@pytest.mark.parametrize("control,domain", [("gradual", "a3"), ("limit", "0e")])
@pytest.mark.parametrize("confirm", [True, False])
async def test_boolean_setting_requires_fresh_matching_readback(hass, monkeypatch, control, domain, confirm):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    coordinator.fw_version, coordinator.hw_version = "3.02.02", "3.02.01"
    coordinator._resolve_device_profile()
    coordinator.boolean_control_state[control] = True  # Stale cached success cannot confirm.

    async def transmit(_uuid, packet, **kwargs):
        if packet[:2] == bytes.fromhex("aa" + domain):
            coordinator._notify_callback(None, bytearray(frame("aa" + domain + ("01" if confirm else "00"))))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    if confirm:
        await coordinator.async_set_boolean_control(control, True)
    else:
        with pytest.raises(ValueError, match="confirm"):
            await coordinator.async_set_boolean_control(control, True)
    assert coordinator.boolean_control_state[control] is confirm
    assert coordinator._field_revisions[f"boolean_{control}"] == 1


def test_limit_and_pact1_static_conditions_are_independent():
    old = device_profile("H6102", 10, 1, hardware="1.00.01")
    new = device_profile("H6102", 10, 1, hardware="1.00.02")
    assert old.boolean_controls == {"gradual"} and new.boolean_controls == {"gradual", "limit"}
    static = device_profile("H6102", 1, 1, hardware="1.00.03", firmware="1.06.00")
    assert static.supports_rgb and not static.supports_custom_effects
    from custom_components.ha_govee_led_ble.generated_protocol_adapter import require_profile_packet
    from custom_components.ha_govee_led_ble.light_commands import build_color_rgb

    require_profile_packet(build_color_rgb(1, 2, 3, "H6102", profile=static), static)
    with pytest.raises(ValueError):
        require_profile_packet(build_scene_activation("H6102", 402), static)
