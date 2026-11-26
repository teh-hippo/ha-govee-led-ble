import pytest

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow, require_effect_route
from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem, PaintedEffect


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
    assert profile.advanced_scene_carrier == (1013, 11836)
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
