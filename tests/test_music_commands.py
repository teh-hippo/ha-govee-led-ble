"""Capture-backed music parameter tests."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, NativeModeOption
from custom_components.ha_govee_led_ble.effect_compiler import compile_music_profile
from custom_components.ha_govee_led_ble.effect_deployments import ObservationConfidence, PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import MusicBody
from custom_components.ha_govee_led_ble.music_commands import build_music_params, prepare_music_request
from custom_components.ha_govee_led_ble.music_semantics import MusicParamSpec, MusicVariant
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex

_CAPTURED_BODIES = {
    (0x30, ()): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000",
    (0x30, ((27, 0x14),)): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000",
    (0x31, ((20, 0x14), (21, 0x46))): ("0102413105ff0000ff7f00ffff0000ff000000ff14460a0000000000000000000000"),
    (0x32, ((20, 0x05),)): "0102413205ff7f00ff0000ffff000000ff00ff0005015e0000000000000000000000",
    (0x33, ((29, 0),)): (
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000000620103020600000000000000000000000000000000"
    ),
    (0x34, ()): "0102413407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000",
    (0x35, ((26, 1), (28, 3))): ("0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0101035000000000"),
    (0x37, ((26, 7), (27, 0x32))): ("0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0732000000000000"),
}


def _assemble(frames: list[bytes]) -> bytes:
    for frame in frames:
        assert len(frame) == 20 and xor_checksum(frame[:19]) == frame[19]
    return b"".join(frame[2:19] for frame in frames)


@pytest.mark.parametrize("model", ["H617A", "H617E"])
def test_music_parameter_templates_reproduce_captured_bodies(model) -> None:
    settings = [
        ({}, False),
        ({}, True),
        ({}, True),
        ({"point": 5}, False),
        ({"relative_brightness": 0}, False),
        ({}, False),
        ({"direction": "two_way"}, False),
        ({"segment_count": 7, "speed": 50}, False),
    ]
    for ((mode, _), body), (parameters, calm) in zip(_CAPTURED_BODIES.items(), settings, strict=True):
        assert _assemble(build_music_params(mode, parameters, profile=get_profile(model), calm=calm)) == H(body)


def test_music_parameter_overlay_changes_only_named_offsets() -> None:
    base = _assemble(build_music_params(0x31, {}, profile=get_profile("H617A")))
    changed = _assemble(build_music_params(0x31, {}, profile=get_profile("H617A"), calm=True))
    assert [index for index, values in enumerate(zip(base, changed, strict=True)) if values[0] != values[1]] == [20, 21]


def test_music_palette_count_guards_downstream_offsets() -> None:
    with pytest.raises(ValueError, match="palette count"):
        build_music_params(0x32, {}, palette=[(1, 2, 3)], profile=get_profile("H617A"))
    assembled = _assemble(build_music_params(0x32, {}, palette=[(1, 2, 3)] * 5, profile=get_profile("H617A")))
    assert assembled[5:20] == bytes([1, 2, 3] * 5)
    assert assembled[20] == 1


@pytest.fixture
def alternative(monkeypatch):
    # Synthetic software fixture only. Known KSY, two palette entries instead of five,
    # independent bounds/defaults and companion value; not device qualification.
    variant = MusicVariant(
        0x32,
        "TEST ONLY issue #286; no hardware qualification",
        "music_body",
        bytes.fromhex("320201020304050608007a00000000000000000000000000000000000000"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 8, 6, 12),
            MusicParamSpec("music_separation_gradient", "gradient", "gradient", "switch", False),
        ),
    )
    profile = ModelProfile(
        "Synthetic music",
        command_grammar="H617A",
        music_modes=("separation",),
        music_variants=(variant,),
        segment_count=15,
    )
    monkeypatch.setitem(MODEL_PROFILES, "TEST-MUSIC", profile)
    return profile


async def test_variant_encoding_application_and_restoration(hass, alternative):
    catalogue = replace(
        MODEL_EFFECT_CATALOGUES["H617A"], sku="TEST-MUSIC", music_modes=(NativeModeOption("separation", "Separation"),)
    )
    settings = catalogue.to_dict()["music_settings"]["separation"]
    assert settings["palette_size"] == 2
    assert settings["parameters"]["point"] == {"kind": "number", "default": 8, "min": 6, "max": 12, "options": []}
    original = build_music_params(0x32, {}, profile=get_profile("H617A"))
    item = LibraryItem.new("Synthetic", MusicProfile("TEST-MUSIC", "separation", 50))
    compiled = compile_music_profile(item, "TEST-MUSIC")
    assert compiled.parameters == {"point": 8, "gradient": False}
    packets = prepare_music_request("TEST-MUSIC", "separation", 50, None, False, compiled.parameters)
    body = MusicBody.from_bytes(_assemble(list(packets[2:])))
    body._read()
    assert body.num_palette == 2 and body.tail.point == 8 and body.tail.companion == 0x7A
    assert _assemble(list(packets[2:]))[11:14] == bytes([8, 0, 0x7A])
    with pytest.raises(ValueError, match="6 to 12"):
        build_music_params(0x32, {"point": 1}, profile=alternative)
    with pytest.raises(ValueError, match="1 to 5"):
        build_music_params(0x32, {"point": 8}, profile=get_profile("H617A"))
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    assert coordinator.music_separation_point == 8
    with patch.object(coordinator, "send_command", new_callable=AsyncMock) as send:
        await async_apply_compiled_profile(coordinator, compiled)
        assert [call.args[0] for call in send.await_args_list] == list(packets)
        state = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
        omitted = state.to_dict()
        del omitted["music_separation_point"]
        assert PriorControlState.from_dict(omitted).music_separation_point == 8
        del omitted["music_model"]
        assert PriorControlState.from_dict(omitted).music_separation_point == 1
        coordinator.music_separation_point = 12
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert [call.args[0] for call in send.await_args_list] == list(packets)
        assert coordinator.music_separation_point == 8
    assert compiled_observation(compiled) == (None, ObservationConfidence.UNKNOWN)
    assert build_music_params(0x32, {}, profile=get_profile("H617A")) == original


async def test_invalid_recovery_fails_before_any_write(hass, alternative):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    state = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=50,
        rgb_color=(1, 2, 3),
        music_mode="separation",
        music_sensitivity=50,
        music_separation_point=1,
    )
    with patch.object(coordinator, "send_command", new_callable=AsyncMock) as send:
        with pytest.raises(ValueError, match="6 to 12"):
            await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        send.assert_not_awaited()


async def test_restored_parameters_are_not_device_observations(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    compiled = compile_music_profile(LibraryItem.new("Music", MusicProfile("H617A", "separation", 50)), "H617A")
    coordinator.install_music_profile_state(
        mode="separation", sensitivity=50, colour=None, calm=False, parameters={"point": 4, "gradient": False}
    )
    assert compiled_observation(compiled) == (
        {"is_on": True, "music_mode": "separation"},
        ObservationConfidence.MODE_MATCH,
    )
    assert coordinator.music_separation_point == 4


@pytest.mark.parametrize("unknown", ["hardware", "layout"])
async def test_unknown_semantics_never_write_or_install_state(hass, alternative, monkeypatch, unknown):
    variant = replace(
        alternative.music_variants[0],
        **({"requires_physical_ic_count": True} if unknown == "hardware" else {"layout": "unknown"}),
    )
    profile = replace(alternative, music_variants=(variant,))
    monkeypatch.setitem(MODEL_PROFILES, "TEST-MUSIC", profile)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    with patch.object(coordinator, "send_command", new_callable=AsyncMock) as send:
        before = coordinator.capture_effect_control_state()
        with pytest.raises(ValueError):
            coordinator.install_music_profile_state(
                mode="separation", sensitivity=40, colour=None, calm=False, parameters={"point": 8}
            )
        assert coordinator.capture_effect_control_state() == before
        send.assert_not_awaited()
        # Native mode selection needs no unknown parameter layout or physical count.
        await coordinator.async_select_music_slug("separation", include_parameters=False)
        assert send.await_count == 2
    if unknown == "hardware":
        assert profile.segment_count == 15 and profile.physical_ic_count is None
        compiled = compile_music_profile(
            LibraryItem.new("Selector", MusicProfile("TEST-MUSIC", "separation", 50)), "TEST-MUSIC"
        )
        assert compiled.parameters == {} and compiled.progress_total == 1
        known = replace(profile, physical_ic_count=20)
        assert build_music_params(0x32, {}, profile=known)


@pytest.mark.parametrize("parameters", [{"point": True}, {"gradient": 1}, {"point": 6}, {"unknown": 1}])
def test_parameter_validation_does_not_coerce(parameters):
    with pytest.raises(ValueError):
        build_music_params(0x32, parameters, profile=get_profile("H617A"))


@pytest.mark.parametrize("sensitivity,calm", [(True, False), (50, 1), (100, False)])
def test_selector_validation_does_not_coerce(sensitivity, calm):
    with pytest.raises(ValueError):
        prepare_music_request("H617A", "rhythm", sensitivity, None, calm, {})
