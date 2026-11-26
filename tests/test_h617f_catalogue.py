from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.ha_govee_led_ble import switch as switch_platform
from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow, require_effect_route
from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem, PaintedEffect
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.scenes import resolve_scene_identity
from tests.coordinator_test_support import frame


@pytest.mark.parametrize(
    ("pact_type", "pact_code", "hardware", "firmware"),
    [
        (None, None, None, None),
        (10, 1, "1.00.01", "1.05.99"),
        (10, 1, "1.00.02", "1.06.00"),
        (10, 1, "3.01.01", "3.02.24"),
    ],
)
def test_h617f_catalogue_admits_declared_workflows_in_identity_contexts(pact_type, pact_code, hardware, firmware):
    profile = device_profile(
        "H617F",
        pact_type,
        pact_code,
        hardware=hardware,
        firmware=firmware,
    )
    catalogue = MODEL_EFFECT_CATALOGUES["H617F"]

    assert (profile.segment_count, profile.segment_group_size) == (15, 3)
    assert profile.segment_count * profile.segment_group_size == 45
    assert profile.advanced_scene_carrier == (29884, 41599)
    assert {mode.id for mode in catalogue.music_modes} == set(profile.music_modes)
    assert [item["id"] for item in catalogue.to_dict(profile=profile)["music_modes"]] == list(profile.music_modes)
    for workflow in (
        CapabilityWorkflow.NATIVE_SCENES,
        CapabilityWorkflow.EDITED_PALETTE_SCENES,
        CapabilityWorkflow.LAYERED_SCENES,
        CapabilityWorkflow.PAINTED,
        CapabilityWorkflow.SINGLE,
        CapabilityWorkflow.MULTI,
        CapabilityWorkflow.NATIVE_MUSIC,
        CapabilityWorkflow.ADVANCED,
        CapabilityWorkflow.WORKSHOP,
    ):
        assert require_effect_route("H617F", workflow, profile=profile) == "H617A"

    for template_id in ("template:paint", "template:single:0:0"):
        template = resolve_catalogue_template("H617F", template_id, profile=profile)
        compiled = compile_application(
            LibraryItem.new(template.label, template.content),
            "H617F",
            diy_code=24,
            profile=profile,
        )
        assert compiled.packets

    assert resolve_catalogue_template("H617F", "template:music:rhythm", profile=profile)
    assert resolve_catalogue_template("H617F", "template:native-diy:504", profile=profile)


def test_h617f_catalogue_uses_exact_native_geometry_and_selector_contracts():
    catalogue = MODEL_EFFECT_CATALOGUES["H617F"]
    profile = device_profile("H617F", 10, 1, hardware="3.01.01", firmware="3.02.24")
    paint = resolve_catalogue_template("H617F", "template:paint", profile=profile).content
    meteor = resolve_catalogue_template("H617F", "template:native-diy:504", profile=profile).content
    bloom = resolve_catalogue_template("H617F", "template:native-diy:506", profile=profile).content

    assert catalogue.sku == profile.scene_catalogue_sku == "H617F"
    assert isinstance(paint, PaintedEffect) and len(paint.segments) == profile.segment_count
    assert isinstance(meteor, LayeredEffect) and all(layer.selection.quantity == 9 for layer in meteor.layers)
    assert isinstance(bloom, LayeredEffect) and [layer.selection.quantity for layer in bloom.layers[2:]] == [22, 22]
    assert {family.family for family in catalogue.effects} == {0, 1, 2, 3, 4, 8, 9, 10}
    assert resolve_scene_identity("H617F", 29884, 41599) is not None
    compiled = compile_application(
        LibraryItem.new("Advanced H617F", replace(meteor, native_diy=None)),
        "H617F",
        diy_code=402,
        profile=profile,
    )
    assert compiled.packets


def test_h617f_scene_revision_separates_command_admission_from_v0_conversion():
    expected = {
        (None, None): ({0}, True),
        ("1.05.99", "1.00.03"): ({0}, True),
        ("1.06.00", "1.00.01"): ({0}, True),
        ("1.06.00", "1.00.02"): ({0}, True),
        ("1.06.00", "1.00.03"): ({0, 1}, False),
        ("3.02.24", "3.01.01"): ({0, 1}, False),
    }

    for (firmware, hardware), (scene_versions, rgbic_scene_v0) in expected.items():
        profile = device_profile("H617F", 10, 1, hardware=hardware, firmware=firmware)

        assert profile.scene_command_versions == scene_versions
        assert profile.rgbic_scene_v0 is rgbic_scene_v0
        assert (profile.physical_ic_count, profile.segment_count, profile.segment_group_size) == (45, 15, 3)


@pytest.mark.parametrize("model,v0", [("H617A", True), ("H617C", False), ("H617E", False)])
def test_h617f_scene_revision_preserves_sibling_gt70_contracts(model, v0):
    profile = device_profile(model, 10, 1, hardware="1.00.02", firmware="1.06.00")

    assert profile.scene_command_versions == {0, 1}
    assert profile.rgbic_scene_v0 is v0


@pytest.mark.parametrize("enabled", [False, True])
def test_h617f_gradual_uses_exact_shared_register_and_query(enabled):
    profile = device_profile("H617F", 10, 1, hardware="1.00.02", firmware="1.06.00")
    write = build_boolean_control("gradual", enabled, "H617F", profile=profile)

    assert profile.static_readback_gradual
    assert profile.boolean_controls == {"gradual"}
    assert write == frame(f"33a3{int(enabled):02x}")
    assert build_boolean_control_query("gradual", "H617F", profile=profile) == frame("aaa3")
    require_profile_packet(write, profile)

    narrowed = replace(profile, boolean_controls=frozenset())
    with pytest.raises(ValueError, match="boolean control gradual"):
        build_boolean_control("gradual", enabled, "H617F", profile=narrowed)


def test_h617f_gradual_readback_updates_register_and_static_state_independently(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617F", configuration_url=None)
    coordinator.profile = device_profile("H617F", 10, 1, hardware="1.00.02", firmware="1.06.00")

    coordinator._notify_callback(None, bytearray(frame("aa0515011194")))
    assert coordinator.static_gradual is True

    coordinator._notify_callback(None, bytearray(frame("aaa300")))
    assert coordinator.boolean_control_state["gradual"] is False
    assert coordinator.static_gradual is True
    assert coordinator._field_revisions["boolean_gradual"] > 0
    assert coordinator._field_revisions["static_gradual"] > 0
    assert coordinator._setting_queries(coordinator.profile) == [(frame("aaa3"), ("boolean_gradual",))]


async def test_h617f_gradual_write_verifies_exact_register_reply(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617F", configuration_url=None)
    coordinator.profile = device_profile("H617F", 10, 1, hardware="1.00.02", firmware="1.06.00")
    query = frame("aaa3")

    async def transmit(_uuid, packet, **_kwargs):
        if packet == query:
            coordinator._notify_callback(None, bytearray(frame("aaa301")))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)

    await coordinator.async_set_boolean_control("gradual", True)

    assert [item.args[1] for item in client.write_gatt_char.await_args_list] == [frame("33a301"), query]
    assert coordinator.boolean_control_state["gradual"] is True
    assert coordinator.static_gradual is None


async def test_h617f_exposes_and_routes_public_gradual_switch(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617F", configuration_url=None)
    entry = MagicMock(runtime_data=coordinator)
    add_entities = MagicMock()
    await switch_platform.async_setup_entry(hass, entry, add_entities)
    gradual = next(entity for entity in add_entities.call_args.args[0] if entity.translation_key == "gradual")
    setter = AsyncMock()
    monkeypatch.setattr(coordinator, "async_set_boolean_control", setter)

    await gradual.async_turn_on()
    await gradual.async_turn_off()

    assert setter.await_args_list == [call("gradual", True), call("gradual", False)]
