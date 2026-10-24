import ast
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from custom_components.ha_govee_led_ble import const, effect_catalogue
from custom_components.ha_govee_led_ble.const import (
    BLE_DISCOVERABLE_MODELS,
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_FAMILIES,
    CONF_PREFIX_EFFECT_NAMES,
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    ReadDomain,
    SupportQuality,
    always_include_custom_effects_from_options,
    default_effect_families,
    device_profile,
    effect_families_from_options,
    get_profile,
    model_from_ble_name,
    prefix_effect_names_from_options,
    protocol_model,
    resolve_model,
    supported_effect_categories,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import CompatibilityState, compatibility, compile_music_profile
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_selector import effect_selector_entries
from custom_components.ha_govee_led_ble.music_protocol import music_code_for, music_slug_for


def test_segment_count_and_supports_segments():
    assert MODEL_PROFILES["H617A"].segment_count == 15
    assert MODEL_PROFILES["H6199"].segment_count == 15
    assert MODEL_PROFILES["H617A"].segment_group_count == 5
    assert MODEL_PROFILES["H6199"].segment_group_count == 4
    assert MODEL_PROFILES["H617A"].supports_segments
    # Both models paint segments. The H6199 was gated off until captured app writes on it were
    # reproduced byte for byte, whole-strip and per-segment, including the union frame that proves
    # the field is a mask and not an index.
    assert MODEL_PROFILES["H6199"].supports_segments


def test_supports_segments_defaults_false():
    assert ModelProfile("x").segment_count == 0
    assert not ModelProfile("x").supports_segments
    assert ModelProfile("x").command_grammar is None
    assert ModelProfile("x").status_grammar is None


@pytest.mark.parametrize(
    ("model", "command_grammar", "status_grammar"),
    [
        ("H617A", "H617A", "H617A"),
        ("H617E", "H617A", "H617A"),
        ("H6076", "H617A", "H6076"),
        ("H6199", "H6199", "H6199"),
    ],
)
def test_existing_profiles_preserve_both_directional_grammars(model, command_grammar, status_grammar):
    assert get_profile(model).command_grammar == command_grammar
    assert get_profile(model).status_grammar == status_grammar


def test_h617a_and_h617e_share_wire_behaviour_but_keep_exact_product_profiles():
    h617a = MODEL_PROFILES["H617A"]
    h617e = MODEL_PROFILES["H617E"]
    assert h617e is not h617a
    assert h617e.name == "H617E LED Strip"
    assert h617e.support_quality is SupportQuality.SUPPORTED
    assert h617e.scene_catalogue_sku == "H617E"
    assert h617e.read_domains == h617a.read_domains
    assert h617e.supports_scenes
    assert h617e.supports_music_mode
    assert len(h617e.music_modes) == 11
    assert h617e.segment_count == 15
    assert h617e.supports_segments
    assert h617e.supports_advanced_effects
    assert h617e.supports_multi_layered_effects
    assert h617e.connection_idle_timeout == 3.0
    assert resolve_model("H617E") == "H617E"
    assert protocol_model("H617E") == "H617A"
    assert h617e.command_grammar == h617e.status_grammar == "H617A"
    assert h617e.effect_grammar == h617a.effect_grammar == "H617A"


def test_h617c_is_an_exact_isolated_profile_with_its_own_status_grammar_and_30_ic_geometry():
    profile = MODEL_PROFILES["H617C"]

    assert profile is not MODEL_PROFILES["H617A"]
    assert profile.support_quality is SupportQuality.SUPPORTED
    assert profile.scene_catalogue_sku == "H617C"
    assert (profile.command_grammar, profile.status_grammar, profile.effect_grammar) == ("H617A", "H617C", "H617A")
    assert (profile.segment_count, profile.segment_group_size, profile.physical_ic_count) == (15, 3, 30)
    assert profile.whole_device_mask == 0x7FFF and profile.colour_mode_query_selector == 1
    assert profile.static_readback_kelvin and profile.static_readback_zero_kelvin_is_rgb
    assert profile.static_readback_gradual and profile.boolean_controls == frozenset({"gradual"})
    assert profile.advanced_scene_carrier == (29884, 41599) and profile.advanced_diy_selector == 402
    assert (
        profile.diy_requires_upload_ack and profile.music_upload_before_selector and profile.music_requires_upload_ack
    )
    assert len(profile.music_modes) == 11 and profile.music_variants


def test_h617f_uses_exact_scene_catalogue_with_h617a_wire_grammars():
    profile = MODEL_PROFILES["H617F"]

    assert profile.support_quality is SupportQuality.SUPPORTED
    assert profile.scene_catalogue_sku == "H617F"
    assert profile.command_grammar == profile.status_grammar == profile.effect_grammar == "H617A"


def test_support_quality_has_only_supported_and_experimental_states():
    assert set(SupportQuality) == {SupportQuality.EXPERIMENTAL, SupportQuality.SUPPORTED}
    assert const.H6199_PACT1_PROFILE.support_quality is SupportQuality.SUPPORTED
    assert UNSUPPORTED_PROFILE.support_quality is SupportQuality.EXPERIMENTAL
    assert {
        model for model, profile in MODEL_PROFILES.items() if profile.support_quality is SupportQuality.SUPPORTED
    } == {"H601C", "H6076", "H60A1", "H60A6", "H6102", "H617A", "H617C", "H617E", "H617F", "H6199", "H7020"}
    assert {
        model for model, profile in MODEL_PROFILES.items() if profile.support_quality is SupportQuality.EXPERIMENTAL
    } == {"H1A42", "H6097", "H6099", "H6125", "H6179", "H61F5", "H66A0", "H7025"}


def test_h6125_is_an_exact_experimental_profile_on_the_shared_dreamcolor_route():
    profile = MODEL_PROFILES["H6125"]

    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert (profile.command_grammar, profile.status_grammar, profile.effect_grammar) == ("H617A", "H6125", "H617A")
    assert profile.scene_catalogue_sku == "H6125" and "H6125" in BLE_DISCOVERABLE_MODELS
    assert (profile.segment_count, profile.segment_group_size, profile.physical_ic_count) == (15, 3, 50)
    assert profile.a1_diy_selector == 0xFE and profile.colour_mode_query_selector == 1
    assert len(profile.music_modes) == 11 and profile.music_variants
    assert profile.supports_advanced_effects and not profile.supports_video_mode
    assert profile.brightness_wire_range is None and profile.outbound_transform is None
    assert supported_effect_categories("H6125") == ("scenes", "effects", "multi_layered", "reactive", "advanced")


@pytest.mark.parametrize("pact", [(1, 1), (2, 1), (None, None), (10, 3)])
def test_h6097_pact_admission_does_not_depend_on_version_query_success(pact):
    profile = device_profile("H6097", *pact)
    known = pact in {(1, 1), (2, 1)}
    assert profile.supports_rgb is known
    assert profile.supports_power_on_behaviour is known
    assert profile.supports_video_mode is known
    assert bool(profile.music_modes) is known
    assert profile.can_read(ReadDomain.POWER) and profile.can_read(ReadDomain.BRIGHTNESS)
    if known:
        assert profile == MODEL_PROFILES["H6097"]
        assert profile.physical_ic_count == 24 and profile.segment_count == 14
        assert not profile.video_firmware_conditions
    else:
        assert profile.command_operations == {"power", "brightness"}
        assert not profile.supports_custom_effects and not profile.supports_scenes
        assert not profile.dreamview_operations and not profile.supports_white_balance


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "wire_range"),
    [
        ((1, 2), "1.07.00", "1.00.03", (6, 254)),
        ((1, 1), "1.07.01", "1.00.04", (20, 254)),
        ((1, 2), "1.07.01", "1.00.04", (20, 254)),
        ((1, 2), "1.08.00", "1.01.00", (20, 254)),
        ((1, 2), "1.06.99", "1.00.04", (20, 254)),
        ((1, 2), "1.07.00", "1.00.02", (6, 254)),
        ((1, 2), "1.07.00", "2.00.04", None),
        ((1, 2), "1.07.00", "1.04", None),
        ((1, 2), "1.07", "1.00.04", None),
        ((1, 2), None, "1.00.04", None),
        ((1, 2), "1.07.00", None, None),
        ((1, 3), "1.07.01", "1.00.04", None),
        ((10, 2), "3.01.00", "1.00.04", None),
        ((None, None), "1.07.00", "1.00.04", None),
    ],
)
def test_h6125_pact1_register_and_invalid_identity_gates(pact, firmware, hardware, wire_range):
    profile = device_profile("H6125", *pact, firmware=firmware, hardware=hardware)

    if wire_range is None:
        assert profile is const.H6125_POWER_ONLY_PROFILE
        assert profile.command_operations == frozenset({"power"}) and profile.outbound_transform is None
        assert profile.read_domains == {ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
    else:
        assert profile.name == MODEL_PROFILES["H6125"].name
        assert profile.brightness_wire_range == wire_range
        assert profile.outbound_transform is not None
        # The cached transform keeps profile equality stable, so refreshes do not reset state.
        assert profile == device_profile("H6125", *pact, firmware=firmware, hardware=hardware)


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "music_count", "colour_temperature", "groups"),
    [
        ((1, 1), "1.00.11", "1.00.01", 4, False, 4),
        ((1, 1), "1.04.08", "1.00.04", 4, False, 4),
        ((1, 2), "1.05.99", "1.00.03", 4, False, 4),
        ((1, 2), "1.06.00", "1.00.03", 4, True, 5),
        ((1, 2), "1.07.00", "1.00.03", 11, True, 5),
        ((10, 1), "2.03.99", "2.01.01", 4, True, 5),
        ((10, 1), "2.04.00", "2.01.01", 11, True, 5),
        ((10, 2), "3.00.99", "3.01.10", 4, True, 5),
        ((10, 2), "3.01.00", "3.01.10", 11, True, 5),
        ((10, 2), "3.04.37", "3.01.10", 11, True, 5),
        ((10, 3), "3.04.37", "3.01.10", 11, True, 5),
    ],
)
def test_h6125_colour_and_music_have_independent_revision_gates(
    pact, firmware, hardware, music_count, colour_temperature, groups
):
    profile = device_profile("H6125", *pact, firmware=firmware, hardware=hardware)
    assert profile.supports_rgb
    assert profile.supports_color_temperature is colour_temperature
    assert profile.segment_group_count == groups
    assert len(profile.music_modes) == music_count
    if pact[0] == 10:
        assert profile.outbound_transform is None and profile.brightness_wire_range is None
        assert profile.a1_diy_selector is None


@pytest.mark.parametrize("hardware", ["2.02.01", "3.04.10"])
def test_h6125_unmapped_hardware_does_not_inherit_the_modern_route(hardware):
    profile = device_profile("H6125", 10, 2, firmware=f"{hardware[0]}.04.37", hardware=hardware)
    assert profile is const.H6125_POWER_ONLY_PROFILE


def test_register_range_requires_the_transform_that_encodes_it():
    with pytest.raises(ValueError, match="requires the outbound transform"):
        ModelProfile("x", brightness_wire_range=(20, 254))
    with pytest.raises(ValueError, match="register range"):
        ModelProfile("x", brightness_wire_range=(0, 254), outbound_transform=lambda packet: packet)


def test_h7020_candidate_is_qualified_by_pact_not_guessed_firmware():
    profile = MODEL_PROFILES["H7020"]
    assert profile.support_quality is SupportQuality.SUPPORTED
    assert "H7020" in BLE_DISCOVERABLE_MODELS
    assert profile.command_grammar == profile.status_grammar == "H7020"
    assert profile.effect_grammar == "H617A"
    assert profile.setup_required_read_domains == {ReadDomain.POWER}
    assert profile.brightness_wire_range is None and profile.outbound_transform is None
    assert profile.supports_rgb and profile.supports_color_temperature
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2000, 9000)
    for pact in (1, 2):
        assert device_profile("H7020", pact, 1) is profile
    for pact, code in ((None, None), (1, 2), (3, 1)):
        unknown = device_profile("H7020", pact, code)
        assert unknown.command_operations == {"power", "brightness"}
        assert not unknown.supports_segments and not unknown.supports_music_mode
        assert not unknown.boolean_controls and not unknown.configured_string_counts


def test_h6076_profile_is_basic_and_fail_closed_until_identity_qualifies_music():
    profile = device_profile("H6076", None, None)
    assert profile == const._H6076_PROFILE
    assert profile.support_quality is SupportQuality.SUPPORTED
    assert profile.state_readable
    assert profile.read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.COLOUR_MODE,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
        ReadDomain.SEGMENTS,
    }
    assert profile.setup_required_read_domains == {ReadDomain.POWER, ReadDomain.BRIGHTNESS}
    assert profile.supports_rgb and profile.supports_color_temperature
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2700, 6500)
    assert profile.readback_min_color_temp_kelvin == 2200
    assert profile.supports_color_mode_readback
    assert (
        profile.supports_custom_effects and profile.supports_advanced_effects and profile.supports_multi_layered_effects
    )
    assert profile.supports_scenes
    assert profile.supports_music_mode
    assert profile.music_modes == ("energetic", "rhythm", "bounce", "hopping", "beat", "spray")
    assert profile.readback_music_modes == const._H6076_ALL_MUSIC_MODES
    assert profile.supports_segments and profile.supports_segment_brightness
    assert not profile.supports_segment_color_temperature
    assert (profile.segment_count, profile.segment_group_size, profile.physical_ic_count) == (7, 4, 14)
    assert profile.whole_device_mask == 0x007F
    assert (profile.command_grammar, profile.status_grammar, profile.effect_grammar) == ("H617A", "H6076", "H617A")
    assert protocol_model("H6076") == "H6076"
    assert profile.boolean_controls == frozenset({"gradual"})


def test_h6076_registry_profile_is_the_music_ceiling_of_the_basic_profile():
    ceiling = MODEL_PROFILES["H6076"]

    assert ceiling.music_grammar == "H6076"
    assert (
        ceiling.music_upload_before_selector
        and ceiling.music_requires_upload_ack
        and ceiling.music_params_require_activation
    )
    assert [slug for slug in ceiling.music_modes] == [
        "energetic",
        "rhythm",
        "bounce",
        "hopping",
        "beat",
        "spray",
        "skittles",
        "torch",
        "candy_crush",
        "fusion",
        "shiny",
        "separation",
    ]
    assert (
        replace(
            ceiling,
            min_color_temp_kelvin=2700,
            readback_min_color_temp_kelvin=2200,
            music_modes=("energetic", "rhythm", "bounce", "hopping", "beat", "spray"),
            readback_music_modes=const._H6076_ALL_MUSIC_MODES,
            music_variants=const.H6076_LEGACY_MUSIC_VARIANTS,
            music_upload_before_selector=False,
            music_requires_upload_ack=False,
            music_params_require_activation=False,
        )
        == const._H6076_PROFILE
    )
    assert supported_effect_categories("H6076") == ("scenes", "effects", "multi_layered", "reactive", "advanced")


@pytest.mark.parametrize(
    ("pact", "firmware", "qualified", "min_kelvin", "readback_min_kelvin"),
    [
        ((1, 1), "1.02.00", True, 2200, None),
        ((2, 1), "1.04.05", True, 2700, None),
        ((1, 1), "1.04.08", True, 2200, None),
        ((1, 1), "1.01.99", False, 2200, None),
        ((2, 1), "1.01.99", False, 2700, None),
        ((1, 1), "1.2.0", False, 2200, None),
        ((1, 1), None, False, 2200, None),
        ((1, 2), "1.04.05", False, 2700, 2200),
        ((3, 1), "1.04.05", False, 2700, 2200),
        ((None, None), "1.04.05", False, 2700, 2200),
    ],
)
def test_h6076_music_needs_a_known_pact_and_software_1_02_or_newer(
    pact, firmware, qualified, min_kelvin, readback_min_kelvin
):
    profile = device_profile("H6076", *pact, firmware=firmware, hardware="3.05.00")

    assert (len(profile.music_modes) == 12) is qualified
    assert (len(profile.music_modes) == 6) is not qualified
    assert profile.min_color_temp_kelvin == min_kelvin
    assert profile.readback_min_color_temp_kelvin == readback_min_kelvin


def test_h6102_static_candidate_is_exact_and_discoverable():
    profile = MODEL_PROFILES["H6102"]

    assert profile.support_quality is SupportQuality.SUPPORTED
    assert profile.command_grammar == "H617A"
    assert profile.status_grammar == "H6102"
    assert profile.scene_catalogue_sku == "H6102"
    assert profile.requires_notifications
    assert profile.supports_rgb
    assert BLE_DISCOVERABLE_MODELS == frozenset(MODEL_PROFILES)
    assert model_from_ble_name("Govee_H6102_ABCD") == "H6102"


def test_h6179_profile_uses_exact_experimental_capabilities():
    profile = MODEL_PROFILES["H6179"]

    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert profile.read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.MODE,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
    }
    assert profile.setup_required_read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.MODE,
    }
    assert profile.supports_rgb and profile.supports_color_temperature
    assert profile.supports_scenes and profile.scene_catalogue_sku == "H6179"
    assert profile.supports_custom_effects and profile.supports_multi_layered_effects
    assert profile.music_modes == ("mode_0", "mode_1")
    assert profile.selector_only_scene_bits == 8
    assert profile.command_grammar == profile.status_grammar == profile.effect_grammar == "H6179"
    assert protocol_model("H6179") == "H6179"


def test_setup_required_domains_must_be_readable():
    with pytest.raises(ValueError, match="setup-required"):
        ModelProfile("x", setup_required_read_domains=frozenset({ReadDomain.POWER}))
    with pytest.raises(ValueError, match="selector-only scene width"):
        ModelProfile("x", selector_only_scene_bits=17)


@pytest.mark.parametrize("domain", list(ReadDomain))
def test_read_domains_require_status_grammar(domain):
    with pytest.raises(ValueError, match="read domains require a status grammar"):
        ModelProfile("x", command_grammar="H6199", status_grammar=None, read_domains=frozenset({domain}))


@pytest.mark.parametrize(
    "domain",
    [
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.COLOUR_MODE,
        ReadDomain.MODE,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
        ReadDomain.SEGMENTS,
    ],
)
def test_basic_read_domains_require_command_grammar(domain):
    with pytest.raises(ValueError, match="basic read domains require a command grammar"):
        ModelProfile("x", command_grammar=None, status_grammar="H6199", read_domains=frozenset({domain}))


@pytest.mark.parametrize(
    "domain",
    [
        ReadDomain.SUBORDINATE_20,
        ReadDomain.SUBORDINATE_21,
        ReadDomain.DISPLAY_SETTING,
        ReadDomain.RELATIVE_BRIGHTNESS,
        ReadDomain.OTHER,
    ],
)
def test_non_basic_read_domains_do_not_require_command_grammar(domain):
    profile = ModelProfile("x", command_grammar=None, status_grammar="H6199", read_domains=frozenset({domain}))
    assert profile.can_read(domain)


def test_unknown_models_fail_closed():
    assert get_profile("nope") is UNSUPPORTED_PROFILE
    assert not UNSUPPORTED_PROFILE.supports_segments
    assert not UNSUPPORTED_PROFILE.supports_music_mode
    assert resolve_model("H617A-extra") is None
    assert resolve_model("H9999") is None
    assert get_profile("H9999").command_grammar is None
    assert get_profile("H9999").status_grammar is None
    assert UNSUPPORTED_PROFILE.effect_grammar is None


def test_effect_family_defaults_and_options():
    assert default_effect_families("H617A") == {"scenes", "music"}
    assert default_effect_families("H6199") == {"video"}
    assert effect_families_from_options("H6199", {}) == {"video"}
    assert effect_families_from_options(
        "H6199",
        {CONF_EFFECT_FAMILIES: ["scenes", "music", "unsupported"]},
    ) == {"scenes", "music"}
    assert prefix_effect_names_from_options({}) is False
    assert prefix_effect_names_from_options({CONF_PREFIX_EFFECT_NAMES: True}) is True
    assert prefix_effect_names_from_options({CONF_PREFIX_EFFECT_NAMES: 1}) is False
    assert always_include_custom_effects_from_options({}) is False
    assert always_include_custom_effects_from_options({CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True}) is True
    assert always_include_custom_effects_from_options({CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: 1}) is False


def test_model_specific_music_capabilities():
    assert MODEL_PROFILES["H617A"].music_modes == (
        "energetic",
        "rhythm",
        "spectrum",
        "rolling",
        "separation",
        "hopping",
        "piano_keys",
        "fountain",
        "day_and_night",
        "bloom",
        "shiny",
    )
    assert MODEL_PROFILES["H6199"].music_modes == ("energetic", "rhythm", "spectrum", "rolling")
    assert MODEL_PROFILES["H617E"].music_modes == MODEL_PROFILES["H617A"].music_modes
    assert MODEL_PROFILES["H6199"].effect_grammar == "H6199"
    assert MODEL_PROFILES["H6199"].video_grammar == "H6199"
    assert MODEL_PROFILES["H6199"].video_modes == ("movie", "game")
    assert MODEL_PROFILES["H6199"].supports_video_capture_region
    assert MODEL_PROFILES["H6199"].supports_video_saturation
    assert MODEL_PROFILES["H617A"].supports_music_color
    assert MODEL_PROFILES["H6199"].supports_music_color
    assert (MODEL_PROFILES["H617A"].music_sensitivity_min, MODEL_PROFILES["H617A"].music_sensitivity_max) == (0, 99)
    assert (MODEL_PROFILES["H6199"].music_sensitivity_min, MODEL_PROFILES["H6199"].music_sensitivity_max) == (0, 100)
    assert not MODEL_PROFILES["H6199"].supports_white_brightness
    assert not MODEL_PROFILES["H6199"].static_readback_echoes_color
    assert MODEL_PROFILES["H6199"].supports_video_sound_effects


async def test_new_encoding_metadata_does_not_enable_music_before_profile_construction(monkeypatch):
    # Inject after the registry assignment, before profiles are built, in an isolated module.
    tree = ast.parse(Path(const.__file__).read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "MUSIC_MODE_SLUGS"
    )
    tree.body.insert(tree.body.index(assignment) + 1, ast.parse('MUSIC_MODE_SLUGS["future_mode"] = 5').body[0])
    namespace = ModuleType("_music_profile_regression")
    namespace.__package__ = const.__package__
    monkeypatch.setitem(sys.modules, namespace.__name__, namespace)
    exec(compile(ast.fix_missing_locations(tree), const.__file__, "exec"), namespace.__dict__)  # noqa: S102
    monkeypatch.setitem(const.MUSIC_MODE_SLUGS, "future_mode", 5)

    for model in ("H617A", "H617C", "H617E", "H6199"):
        profile = namespace.MODEL_PROFILES[model]
        assert profile.music_modes == MODEL_PROFILES[model].music_modes
        assert "future_mode" not in profile.music_modes
        monkeypatch.setitem(MODEL_PROFILES, model, profile)
        assert "future_mode" not in {mode.id for mode in effect_catalogue._native_music_modes(model)}
        with pytest.raises(ValueError, match="does not support music mode"):
            music_code_for(model, "future_mode", profile=profile)
        assert music_slug_for(model, 5, profile=profile) == "energetic"
        entries = effect_selector_entries(
            model, frozenset({const.EFFECT_CATEGORY_REACTIVE}), (), prefix_effect_names=False
        )
        assert {entry.value for entry in entries} == set(profile.music_modes)
        item = LibraryItem.new("Unenabled", MusicProfile(model, "future_mode", 50))
        assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
        with pytest.raises(ValueError, match="does not support music mode"):
            compile_music_profile(item, model)
        coordinator = GoveeBLECoordinator.__new__(GoveeBLECoordinator)
        coordinator.model = model
        coordinator.profile = profile
        coordinator.send_command = AsyncMock()
        with pytest.raises(ValueError, match="music mode"):
            await coordinator.async_select_music_slug("future_mode")
        coordinator.send_command.assert_not_awaited()
