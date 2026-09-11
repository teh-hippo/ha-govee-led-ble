import ast
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from custom_components.ha_govee_led_ble import const, effect_catalogue
from custom_components.ha_govee_led_ble.const import (
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
    effect_families_from_options,
    get_profile,
    prefix_effect_names_from_options,
    protocol_model,
    resolve_model,
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


def test_h6076_profile_is_basic_and_fail_closed():
    profile = MODEL_PROFILES["H6076"]
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


def test_setup_required_domains_must_be_readable():
    with pytest.raises(ValueError, match="setup-required"):
        ModelProfile("x", setup_required_read_domains=frozenset({ReadDomain.POWER}))


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
    assert (MODEL_PROFILES["H6199"].music_sensitivity_min, MODEL_PROFILES["H6199"].music_sensitivity_max) == (1, 100)
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
