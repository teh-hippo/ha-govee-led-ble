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
from custom_components.ha_govee_led_ble.effect_selector import MUSIC_EFFECTS, effect_selector_entries


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
    ("model", "grammar"), [("H617A", "H617A"), ("H617E", "H617A"), ("H6076", "H617A"), ("H6199", "H6199")]
)
def test_existing_profiles_preserve_both_directional_grammars(model, grammar):
    assert get_profile(model).command_grammar == grammar
    assert get_profile(model).status_grammar == grammar


def test_h617a_and_h617e_share_wire_behaviour_but_keep_exact_product_profiles():
    h617a = MODEL_PROFILES["H617A"]
    h617e = MODEL_PROFILES["H617E"]
    assert h617e is not h617a
    assert h617e.name == "H617E LED Strip"
    assert h617e.support_quality is SupportQuality.COMPATIBLE
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


@pytest.mark.parametrize("model", ["H617C", "H617F"])
def test_h617c_and_h617f_use_exact_scene_catalogues_with_h617a_wire_grammars(model):
    profile = MODEL_PROFILES[model]

    assert profile.scene_catalogue_sku == model
    assert profile.command_grammar == profile.status_grammar == profile.effect_grammar == "H617A"


def test_h6125_is_an_exact_experimental_profile_on_the_shared_dreamcolor_route():
    profile = MODEL_PROFILES["H6125"]

    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert (profile.command_grammar, profile.status_grammar, profile.effect_grammar) == ("H617A", "H6125", "H617A")
    assert profile.scene_catalogue_sku == "H6125" and "H6125" in BLE_DISCOVERABLE_MODELS
    assert (profile.segment_count, profile.segment_group_size, profile.physical_ic_count) == (15, 3, 50)
    assert profile.a1_diy_selector == 0xFE and profile.colour_mode_query_selector == 1
    assert len(profile.music_modes) == 11 and profile.music_variants
    assert not profile.supports_advanced_effects and not profile.supports_video_mode
    assert profile.brightness_wire_range is None and profile.outbound_transform is None
    assert supported_effect_categories("H6125") == ("scenes", "effects", "multi_layered", "reactive")


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "wire_range"),
    [
        ((1, 2), "1.07.00", "1.00.03", (6, 254)),
        ((1, 1), "1.07.01", "1.00.04", (20, 254)),
        ((1, 2), "1.07.01", "1.00.04", (20, 254)),
        ((1, 2), "1.08.00", "1.01.00", (20, 254)),
        ((1, 2), "1.06.99", "1.00.04", None),
        ((1, 2), "1.07.00", "1.00.02", None),
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
def test_h6125_pact_revision_gate_admits_one_controller_generation(pact, firmware, hardware, wire_range):
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


def test_register_range_requires_the_transform_that_encodes_it():
    with pytest.raises(ValueError, match="requires the outbound transform"):
        ModelProfile("x", brightness_wire_range=(20, 254))
    with pytest.raises(ValueError, match="register range"):
        ModelProfile("x", brightness_wire_range=(0, 254), outbound_transform=lambda packet: packet)


def test_h6076_profile_is_basic_and_fail_closed_until_identity_qualifies_music():
    profile = device_profile("H6076", None, None)
    assert profile is const._H6076_PROFILE
    assert profile.support_quality is SupportQuality.PARTIAL
    assert profile.state_readable
    assert profile.read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
    }
    assert profile.setup_required_read_domains == {ReadDomain.POWER, ReadDomain.BRIGHTNESS}
    assert profile.supports_rgb and profile.supports_color_temperature
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2700, 6500)
    assert not profile.supports_color_mode_readback
    assert not profile.supports_custom_effects
    assert not profile.supports_scenes
    assert not profile.supports_music_mode
    assert not profile.supports_segments
    assert profile.whole_device_mask == 0x007F
    assert profile.command_grammar == profile.status_grammar == "H617A"
    assert protocol_model("H6076") == "H6076"
    assert profile.effect_grammar is None


def test_h6076_registry_profile_is_the_music_ceiling_of_the_basic_profile():
    ceiling = MODEL_PROFILES["H6076"]

    assert ceiling.music_grammar == "H6076"
    assert ceiling.music_upload_before_selector and ceiling.music_requires_upload_ack
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
            music_grammar=None,
            music_modes=(),
            music_variants=(),
            supports_music_color=False,
            music_upload_before_selector=False,
            music_requires_upload_ack=False,
        )
        == const._H6076_PROFILE
    )
    assert supported_effect_categories("H6076") == ("reactive",)


@pytest.mark.parametrize(
    ("pact", "firmware", "qualified"),
    [
        ((1, 1), "1.02.00", True),
        ((2, 1), "1.04.05", True),
        ((1, 1), "1.04.08", True),
        ((1, 1), "1.01.99", False),
        ((1, 1), "1.2.0", False),
        ((1, 1), None, False),
        ((1, 2), "1.04.05", False),
        ((3, 1), "1.04.05", False),
        ((None, None), "1.04.05", False),
    ],
)
def test_h6076_music_needs_a_known_pact_and_software_1_02_or_newer(pact, firmware, qualified):
    profile = device_profile("H6076", *pact, firmware=firmware, hardware="3.05.00")

    assert (profile is MODEL_PROFILES["H6076"]) is qualified
    assert (profile is const._H6076_PROFILE) is not qualified


def test_h6102_static_candidate_is_exact_and_manual_only():
    profile = MODEL_PROFILES["H6102"]

    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert profile.command_grammar == "H617A"
    assert profile.status_grammar == "H6102"
    assert profile.scene_catalogue_sku == "H6102"
    assert profile.requires_notifications
    assert profile.supports_rgb
    assert "H6102" not in BLE_DISCOVERABLE_MODELS
    assert model_from_ble_name("Govee_H6102_ABCD") is None


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
    monkeypatch.setitem(MUSIC_EFFECTS, "Music: Future Mode", "future_mode")

    for model in ("H617A", "H617E", "H6199"):
        profile = namespace.MODEL_PROFILES[model]
        assert profile.music_modes == MODEL_PROFILES[model].music_modes
        assert "future_mode" not in profile.music_modes
        monkeypatch.setitem(MODEL_PROFILES, model, profile)
        assert "future_mode" not in {mode.id for mode in effect_catalogue._native_music_modes(model)}
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
