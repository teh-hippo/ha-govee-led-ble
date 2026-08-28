import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_compiler import CompiledMusicProfile, CompiledVideoProfile
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    CatalogueRef,
    EffectValidationError,
    LibraryItem,
    MusicProfile,
    Origin,
    RelativeBrightness,
    SingleEffect,
    SourceKind,
    VideoProfile,
)
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_scene_defaults import NativeSceneDefault
from custom_components.ha_govee_led_ble.effect_selector import (
    effect_selector_entries,
    resolve_effect_selector,
)
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.effect_websocket import _device_payload
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_h617a_scene,
    build_h6199_video,
    build_power,
)
from custom_components.ha_govee_led_ble.light import (
    GoveeBLELight,
    _coerce_segment_brightness,
    _coerce_segment_colors,
    async_setup_entry,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    kelvin_to_rgb,
)
from custom_components.ha_govee_led_ble.light_services import async_register_light_services
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENE_LABELS, MODEL_SCENES, SCENES
from tests.storage_test_double import InMemoryVersionedDocumentStore


@pytest.fixture
def light(mock_coordinator):
    e = GoveeBLELight(mock_coordinator)
    e.async_write_ha_state = MagicMock()
    return e


@pytest.fixture
def h6199_light(mock_h6199_coordinator):
    mock_h6199_coordinator.is_on = False
    mock_h6199_coordinator.effect = None
    e = GoveeBLELight(mock_h6199_coordinator)
    e.async_write_ha_state = MagicMock()
    return e


def test_basic_and_color_props(light, mock_coordinator):
    assert light.unique_id == "aabbccddeeff" and light.is_on is False
    mock_coordinator.brightness_pct = 50
    assert light.brightness == 128
    labels = sorted(MODEL_SCENE_LABELS["H617A"].values(), key=str.casefold)
    assert light.effect_list[0] == "off"
    assert set(labels) - {"Energetic", "Rhythm", "Bloom"} <= set(light.effect_list)
    assert {"Energetic [Scene]", "Rhythm [Scene]", "Bloom [Scene]"} <= set(light.effect_list)
    mock_coordinator.effect = "rainbow"
    assert light.effect == "Rainbow"
    mock_coordinator.effect = None
    assert light.effect == "off"
    mock_coordinator.rgb_color = (128, 64, 32)
    mock_coordinator.color_temp_kelvin = 4000
    light._attr_color_mode = ColorMode.RGB
    assert light.rgb_color == (128, 64, 32) and light.color_temp_kelvin is None
    light._attr_color_mode = ColorMode.COLOR_TEMP
    assert light.rgb_color is None and light.color_temp_kelvin == 4000


def test_hidden_scene_family_does_not_project_internal_scene_state(
    light,
    mock_coordinator,
) -> None:
    mock_coordinator.effect_families = frozenset()
    mock_coordinator.effect = "rainbow"

    assert light.effect_list == ["off"]
    assert light.effect == "off"


@pytest.mark.parametrize("on", [True, False])
async def test_power(light, mock_coordinator, on):
    await (light.async_turn_on() if on else light.async_turn_off())
    mock_coordinator.send_command.assert_called_with(build_power(on))
    assert mock_coordinator.is_on is on


async def test_turn_on_variants(light, mock_coordinator):
    co = mock_coordinator

    async def _on(**kw):
        co.send_command.reset_mock()
        co.is_on = False
        await light.async_turn_on(**kw)
        return co.send_command.call_args_list

    await light.async_turn_on(brightness=128)
    c = co.send_command.call_args_list
    assert len(c) == 2 and c[1].args[0] == build_brightness(50)
    co.send_command.reset_mock()
    co.refresh_state.reset_mock()
    co.is_on = True
    await light.async_turn_on(brightness=128)
    assert co.send_command.call_count == 1
    assert co.send_command.call_args_list[0].args[0] == build_brightness(50)
    assert co.refresh_state.await_args.kwargs["expected_brightness"] == 50
    c = await _on(rgb_color=(255, 0, 128))
    assert len(c) == 2 and c[1].args[0] == build_color_rgb(255, 0, 128) and co.rgb_color == (255, 0, 128)
    c = await _on(color_temp_kelvin=4000)
    assert c[1].args[0] == build_color_temp(4000) and co.color_temp_kelvin == 4000
    assert light._attr_color_mode == ColorMode.COLOR_TEMP
    co.effect = "rainbow"
    await _on(color_temp_kelvin=5000)
    assert co.effect is None
    c = await _on(effect="rainbow")
    assert c[1].args[0] == build_h617a_scene(SCENES["rainbow"].code) and co.effect == "rainbow"
    c = await _on(effect="Candy")
    packets = [call.args[0] for call in c]
    assert packets[1][0] == 0xA3 and packets[-1] == build_h617a_scene(SCENES["candy"].code) and co.effect == "candy"
    c = await _on(effect="“candy”")
    packets = [call.args[0] for call in c]
    assert packets[1][0] == 0xA3 and packets[-1] == build_h617a_scene(SCENES["candy"].code) and co.effect == "candy"
    co.send_command.reset_mock()
    co.is_on = False
    await light.async_turn_on(effect="forest")
    packets = [call.args[0] for call in co.send_command.call_args_list]
    assert packets[0] == build_power(True)
    assert len(packets) > 2 and packets[1][0] == 0xA3 and packets[-1][0] == 0x33


async def test_mixed_colour_and_effect_request_finishes_in_effect_mode(light, mock_coordinator):
    mock_coordinator.is_on = True

    await light.async_turn_on(
        rgb_color=(12, 34, 56),
        effect="Rainbow",
    )

    assert mock_coordinator.rgb_color == (12, 34, 56)
    assert mock_coordinator.effect == "rainbow"
    assert light.effect == "Rainbow"


async def test_power_rollback(light, mock_coordinator):
    mock_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("fail")])
    with pytest.raises(HomeAssistantError) as turn_on:
        await light.async_turn_on(brightness=128)
    assert turn_on.value.translation_key == "device_command_failed"
    assert mock_coordinator.is_on is False and mock_coordinator.brightness_pct == 100
    mock_coordinator.is_on = True
    mock_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(HomeAssistantError) as turn_off:
        await light.async_turn_off()
    assert turn_off.value.translation_key == "device_command_failed"
    assert mock_coordinator.is_on is True


def test_effect_lists(h6199_light, light, mock_coordinator, mock_h6199_coordinator):
    el = light.effect_list
    assert el[0] == "off"
    assert "Energetic [Scene]" in el and "Energetic [Reactive]" in el
    assert "Piano Keys" in el
    assert el[1:] == sorted(el[1:], key=lambda label: label.split(" [", 1)[0].casefold())
    h = h6199_light.effect_list
    assert h == ["off", "Game", "Movie"]

    mock_h6199_coordinator.effect_families = frozenset({"scenes", "music", "video"})
    h = h6199_light.effect_list
    assert "Sunrise" in h and "Rhythm" in h
    assert "Movie [Scene]" in h and "Movie [Video]" in h
    assert "Bloom" not in h and "Shiny" not in h
    assert "Forest" in h and "Aurora-A" in h

    mock_h6199_coordinator.prefix_effect_names = True
    h = h6199_light.effect_list
    assert h[:3] == ["off", "Video: Game", "Video: Movie"]
    assert h.index("Scene: Afternoon") < h.index("Reactive: Energetic")


def test_selector_projection_preserves_unique_aliases_and_rejects_built_in_ambiguity():
    h617a = effect_selector_entries(
        "H617A",
        frozenset({"scenes", "effects", "multi_layered", "reactive", "advanced"}),
        (),
        prefix_effect_names=False,
    )
    assert resolve_effect_selector(h617a, "candlelight").source == "scene"
    assert resolve_effect_selector(h617a, "Music: Piano Keys").value == "piano_keys"
    assert resolve_effect_selector(h617a, "Energetic [Scene]").source == "scene"
    assert resolve_effect_selector(h617a, "Energetic [Reactive]").source == "music"
    with pytest.raises(EffectValidationError, match="ambiguous"):
        resolve_effect_selector(h617a, "Energetic")

    h6199 = effect_selector_entries(
        "H6199",
        frozenset({"video", "scenes", "effects", "reactive", "advanced"}),
        (),
        prefix_effect_names=True,
    )
    labels = [entry.display_label for entry in h6199]
    assert labels[:2] == ["Video: Game", "Video: Movie"]
    assert resolve_effect_selector(h6199, "Video: Movie").source == "video"
    assert resolve_effect_selector(h6199, "Scene: Movie").source == "scene"
    with pytest.raises(EffectValidationError, match="ambiguous"):
        resolve_effect_selector(h6199, "Movie")


def test_transient_custom_disambiguates_grandfathered_saved_name():
    saved = LibraryItem.new(
        "Custom",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    entries = effect_selector_entries(
        "H617A",
        frozenset({"effects"}),
        (saved,),
        prefix_effect_names=False,
        active_custom=True,
    )

    assert [entry.display_label for entry in entries] == ["Custom [Effect]"]
    assert resolve_effect_selector(entries, "Custom [Effect]").item == saved


def test_same_category_native_and_saved_collisions_have_unique_display_values():
    saved = LibraryItem.new(
        "Energetic",
        MusicProfile("H617A", "energetic", 50),
    )
    entries = effect_selector_entries(
        "H617A",
        frozenset({"reactive"}),
        (saved,),
        prefix_effect_names=False,
    )

    energetic = [entry for entry in entries if entry.base_label == "Energetic"]
    assert [entry.display_label for entry in energetic] == [
        "Energetic [Reactive, Built-in]",
        "Energetic [Reactive, Saved]",
    ]
    assert resolve_effect_selector(entries, "Energetic [Reactive, Built-in]").source == "music"
    assert resolve_effect_selector(entries, "Energetic [Reactive, Saved]").item == saved


def test_generated_native_label_does_not_shadow_grandfathered_saved_name():
    saved = LibraryItem.new(
        "Energetic [Scene]",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    entries = effect_selector_entries(
        "H617A",
        frozenset({"scenes", "effects", "reactive"}),
        (saved,),
        prefix_effect_names=False,
    )
    matching = [entry for entry in entries if "Energetic [Scene" in entry.display_label]

    assert len({entry.display_label for entry in matching}) == len(matching)
    assert resolve_effect_selector(entries, "Energetic [Scene, Built-in]").source == "scene"
    assert resolve_effect_selector(entries, "Energetic [Scene] [Effect, Saved]").item == saved


def test_identity_qualified_labels_continue_until_the_namespace_is_unique():
    first = LibraryItem.new(
        "Energetic [Scene]",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    second = LibraryItem.new(
        "Energetic [Scene, Built-in]",
        SingleEffect(0, 0, 50, ((0, 255, 0),)),
    )
    third = LibraryItem.new(
        "Energetic [Scene, Built-in, scene:energetic]",
        SingleEffect(0, 0, 50, ((0, 0, 255),)),
    )
    entries = effect_selector_entries(
        "H617A",
        frozenset({"scenes", "effects", "reactive"}),
        (first, second, third),
        prefix_effect_names=False,
    )
    labels = [entry.display_label for entry in entries]

    assert len(labels) == len(set(map(str.casefold, labels)))
    assert all(resolve_effect_selector(entries, label) is not None for label in labels)


def test_saved_categories_remain_visible_when_native_families_are_narrower(
    mock_h6199_coordinator,
):
    saved_scene = LibraryItem.new(
        "Saved scene",
        BuiltinScene(CatalogueRef("H6199", 168, 150)),
    )
    saved_reactive = LibraryItem.new(
        "Saved reactive",
        MusicProfile("H6199", "rhythm", 50),
    )
    entries = effect_selector_entries(
        "H6199",
        frozenset({"video", "scenes", "reactive"}),
        (saved_scene, saved_reactive),
        prefix_effect_names=False,
        native_categories=frozenset({"video"}),
    )

    assert {"Saved scene", "Saved reactive"} <= {entry.display_label for entry in entries}

    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(
                    return_value=LibrarySnapshot((saved_scene, saved_reactive)),
                )
            ),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
            active_workspaces=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_h6199_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    assert {"Saved scene", "Saved reactive"} <= set(entity.effect_list)


def test_always_custom_includes_saved_effects_with_no_enabled_categories(
    mock_coordinator,
):
    saved = LibraryItem.new(
        "Saved effect",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    mock_coordinator.effect_categories = frozenset()
    mock_coordinator.effect_families = frozenset()
    mock_coordinator.always_include_custom_effects = True
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot((saved,))),
            ),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
            active_workspaces=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    assert entity.effect_list == ["off", "Saved effect"]
    assert all(entry.source == "saved" for entry in entity._selector_entries())


def test_always_custom_keeps_active_saved_effect_in_state_and_list(
    mock_coordinator,
):
    saved = LibraryItem.new(
        "Saved effect",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    hint = SimpleNamespace(
        source_kind="saved_effect",
        item_id=saved.id,
        content_hash=saved.content_hash,
        observable_signature="custom:800",
    )
    mock_coordinator.effect_categories = frozenset()
    mock_coordinator.effect_families = frozenset()
    mock_coordinator.always_include_custom_effects = True
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 800
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot((saved,))),
            ),
            device_cache=SimpleNamespace(
                get=MagicMock(return_value=SimpleNamespace(active_effect=hint)),
            ),
            active_workspaces=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    assert entity.effect == "Saved effect"
    assert entity.effect in entity.effect_list


def test_always_custom_keeps_native_effects_category_gated() -> None:
    saved = LibraryItem.new(
        "Saved effect",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )

    entries = effect_selector_entries(
        "H617A",
        frozenset(),
        (saved,),
        prefix_effect_names=False,
        always_include_custom_effects=True,
    )

    assert [(entry.source, entry.display_label) for entry in entries] == [("saved", "Saved effect")]


def test_prefixes_depend_on_represented_categories() -> None:
    one_category = effect_selector_entries(
        "H617A",
        frozenset({"scenes", "effects"}),
        (),
        prefix_effect_names=True,
    )
    saved_effect = LibraryItem.new(
        "Saved effect",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    two_categories = effect_selector_entries(
        "H617A",
        frozenset({"scenes"}),
        (saved_effect,),
        prefix_effect_names=True,
        always_include_custom_effects=True,
    )

    assert "Birthday" in {entry.display_label for entry in one_category}
    assert "Scene: Birthday" in {entry.display_label for entry in two_categories}
    assert "Effect: Saved effect" in {entry.display_label for entry in two_categories}


async def test_saved_effects_are_compatible_reactive_and_lock_safe(
    mock_coordinator,
):
    saved = LibraryItem.new(
        "My Effect",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    incompatible = LibraryItem.new(
        "Movie profile",
        VideoProfile(
            "H6199",
            "movie",
            True,
            100,
            False,
            100,
            10,
            RelativeBrightness(100, 100, 100, 100),
            False,
        ),
    )
    listener = None

    def subscribe(callback):
        nonlocal listener
        listener = callback
        return MagicMock()

    @asynccontextmanager
    async def saved_effect_for_apply(*_args, **_kwargs):
        assert not mock_coordinator._control_lock.locked()
        yield saved

    async def apply_saved_effect(*_args, **_kwargs):
        assert mock_coordinator._control_lock.locked()

    application = SimpleNamespace(
        library_snapshot=MagicMock(
            return_value=LibrarySnapshot((saved, incompatible)),
        ),
        subscribe_library=MagicMock(side_effect=subscribe),
        saved_effect_for_apply=saved_effect_for_apply,
    )
    apply_saved = AsyncMock(side_effect=apply_saved_effect)
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=application,
            engine=SimpleNamespace(async_apply_saved=apply_saved),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entity.async_write_ha_state = MagicMock()

    assert "My Effect" in entity.effect_list
    assert "Movie profile" not in entity.effect_list

    await entity.async_turn_on(effect="my effect")

    apply_saved.assert_awaited_once_with(
        mock_coordinator,
        saved,
        config_entry_id="entry-a",
        updated_at=apply_saved.await_args.kwargs["updated_at"],
    )
    mock_coordinator.send_command.assert_awaited_once_with(build_power(True))
    assert mock_coordinator.is_on is True

    assert listener is None
    late_saved = LibraryItem.new(
        "Late Effect",
        SingleEffect(0, 0, 50, ((0, 255, 0),)),
    )
    application.library_snapshot.return_value = LibrarySnapshot((saved, incompatible, late_saved))
    entity._async_restore_static_color = AsyncMock()
    entity._async_restore_segments = AsyncMock()
    entity.async_on_remove = MagicMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await entity.async_added_to_hass()
    assert listener is not None
    assert "Late Effect" in entity.effect_list

    listener(LibrarySnapshot(()))

    assert "My Effect" not in entity.effect_list
    entity.async_write_ha_state.assert_called()


def test_active_saved_effect_uses_current_name_only_for_matching_content(
    mock_coordinator,
):
    saved = LibraryItem.new(
        "Original name",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    renamed = replace(
        saved,
        version=2,
        name="Renamed effect",
        updated_at="2026-08-17T00:00:01+00:00",
    )
    hint = SimpleNamespace(
        source_kind="saved_effect",
        item_id=saved.id,
        content_hash=saved.content_hash,
        observable_signature="custom:800",
    )
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(
                    return_value=LibrarySnapshot((renamed,)),
                )
            ),
            device_cache=SimpleNamespace(
                get=MagicMock(
                    return_value=SimpleNamespace(active_effect=hint),
                )
            ),
            active_workspaces=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entity.async_write_ha_state = MagicMock()
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 800

    assert entity.effect == "Renamed effect"

    mock_coordinator.diy_code = None
    mock_coordinator.effect = "forest"
    assert entity.effect == "Forest"

    mock_coordinator.effect = None
    assert entity.effect == "off"

    mock_coordinator.unknown_scene_code = 800
    assert entity.effect == "Renamed effect"

    mock_coordinator.unknown_scene_code = None
    mock_coordinator.diy_code = 800

    backend.active_workspaces.get.return_value = SimpleNamespace(
        model="H617A",
        observable_signature="custom:800",
    )
    assert entity.effect == "Custom"
    backend.active_workspaces.get.return_value = None

    changed = replace(
        renamed,
        version=3,
        content=SingleEffect(0, 0, 60, ((255, 0, 0),)),
        updated_at="2026-08-17T00:00:02+00:00",
        content_hash="",
    )
    entity._library_updated(LibrarySnapshot((changed,)))

    assert entity.effect == "off"


async def test_workspace_identity_agrees_between_device_payload_and_light_effect(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    deployments = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await deployments.async_load()
    await cache.async_load()
    await active_workspaces.async_load()
    sena = LibraryItem.new(
        "Sena",
        SingleEffect(9, 9, 50, ((255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255))),
    )
    await deployments.async_put(
        DeploymentRecord(
            operation_id=uuid4(),
            config_entry_id="entry-a",
            diy_code=24,
            phase=DeploymentPhase.CONFIRMED,
            compiler_version=1,
            artifact_sha256=sha256(b"sena").hexdigest(),
            updated_at="2026-08-26T00:00:00Z",
            target_mode="custom",
            source_kind="saved_effect",
            selector_label=sena.name,
            source_origin_kind=sena.origin.kind.value,
            source_content_hash=sena.content_hash,
            item_id=sena.id,
            item_version=sena.version,
            verification_confidence=ObservationConfidence.ACTIVATION_MATCH,
        ),
        expected_version=None,
    )
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label="Flow",
        content=SingleEffect(9, 9, 60, ((255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255))),
        origin=Origin(SourceKind.CATALOGUE_TEMPLATE, "h617a:flow:clockwise"),
        observable_signature="custom:24",
        updated_at="2026-08-26T00:01:00Z",
        generation=1,
    )
    active_workspaces.set(workspace)
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = None
    mock_coordinator.effect = None
    mock_coordinator.unknown_scene_code = 24
    mock_coordinator.effect_categories = frozenset({"custom", "scenes"})
    engine = EffectDeploymentEngine(deployments, cache, active_workspaces)
    observed = engine.reconcile_current(
        mock_coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:02:00Z",
        refreshed=True,
    )
    preview_health = MagicMock()
    preview_health.to_dict.return_value = {}
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(library_snapshot=MagicMock(return_value=LibrarySnapshot((sena,)))),
            device_cache=cache,
            active_workspaces=active_workspaces,
            engine=engine,
            preview=SimpleNamespace(health=MagicMock(return_value=preview_health)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entry = SimpleNamespace(
        entry_id="entry-a",
        runtime_data=mock_coordinator,
        title="Govee H617A",
    )

    payload = _device_payload(hass, backend, entry)

    assert observed.active_effect is None
    assert payload["active_state"]["active_effect"] is None
    assert payload["active_workspace"]["selector_label"] == "Flow"
    assert entity.effect == "Custom"
    assert entity.effect_list[:2] == ["off", "Custom"]

    mock_coordinator.unknown_scene_code = None
    mock_coordinator.diy_code = 25
    engine.reconcile_current(
        mock_coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:03:00Z",
        refreshed=True,
    )
    suspended_payload = _device_payload(hass, backend, entry)

    assert suspended_payload["active_workspace"] is None
    assert active_workspaces.get("entry-a") == workspace


def test_active_custom_remains_in_effect_list_when_categories_are_disabled(
    mock_coordinator,
):
    mock_coordinator.effect_categories = frozenset()
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
            active_workspaces=SimpleNamespace(
                get=MagicMock(
                    return_value=SimpleNamespace(
                        model="H617A",
                        observable_signature="custom:24",
                    )
                )
            ),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    assert entity.effect == "Custom"
    assert entity.effect_list == ["off", "Custom"]


def test_active_custom_uses_the_advertised_namespace_for_saved_resolution(
    mock_coordinator,
):
    saved = LibraryItem.new(
        "Custom",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    )
    mock_coordinator.effect_categories = frozenset({"effects"})
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(
                    return_value=LibrarySnapshot((saved,)),
                ),
            ),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
            active_workspaces=SimpleNamespace(
                get=MagicMock(
                    return_value=SimpleNamespace(
                        model="H617A",
                        observable_signature="custom:24",
                    )
                )
            ),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    assert "Custom [Effect]" in entity.effect_list
    assert entity._saved_effect("Custom [Effect]") == saved


async def test_direct_colour_control_clears_active_workspace(mock_coordinator):
    workspace = SimpleNamespace(
        model="H617A",
        observable_signature="custom:24",
    )
    current_workspace = workspace
    active_workspaces = MagicMock()
    active_workspaces.get.side_effect = lambda _entry_id: current_workspace

    def clear_workspace(_entry_id):
        nonlocal current_workspace
        current_workspace = None
        return True

    active_workspaces.clear.side_effect = clear_workspace
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            active_workspaces=active_workspaces,
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    light = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    light.async_write_ha_state = MagicMock()

    assert light.effect == "Custom"

    await light.async_turn_on(rgb_color=(12, 34, 56))

    active_workspaces.clear.assert_called_once_with("entry-a")
    assert light.effect == "off"
    assert light.rgb_color == (12, 34, 56)


async def test_failed_foreground_control_preserves_active_workspace(mock_coordinator):
    workspace = SimpleNamespace(
        model="H617A",
        observable_signature="custom:24",
    )
    active_workspaces = MagicMock()
    active_workspaces.get.return_value = workspace
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            active_workspaces=active_workspaces,
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    mock_coordinator.send_command = AsyncMock(side_effect=BleakError("failed"))
    light = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(rgb_color=(12, 34, 56))

    active_workspaces.clear.assert_not_called()
    assert light.effect == "Custom"


async def test_custom_effect_selection_with_brightness_preserves_workspace(
    mock_coordinator,
):
    workspace = SimpleNamespace(
        model="H617A",
        observable_signature="custom:24",
    )
    active_workspaces = MagicMock()
    active_workspaces.get.return_value = workspace
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            active_workspaces=active_workspaces,
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    light = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    light.async_write_ha_state = MagicMock()

    await light.async_turn_on(brightness=128, effect="Custom")

    active_workspaces.clear.assert_not_called()
    assert light.effect == "Custom"


async def test_brightness_only_control_preserves_active_workspace(
    mock_coordinator,
):
    workspace = SimpleNamespace(
        model="H617A",
        observable_signature="custom:24",
    )
    active_workspaces = MagicMock()
    active_workspaces.get.return_value = workspace
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            active_workspaces=active_workspaces,
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    mock_coordinator.is_on = True
    mock_coordinator.diy_code = 24
    light = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    light.async_write_ha_state = MagicMock()

    await light.async_turn_on(brightness=128)

    active_workspaces.clear.assert_not_called()
    assert light.effect == "Custom"


async def test_turn_on_scene_applies_and_clears_sticky(light, mock_coordinator):
    co = mock_coordinator
    co.is_on = True
    co.music_mode, co.video_mode = "rhythm", "off"
    co.diy_code = 0xF0
    await light.async_turn_on(effect="rainbow")
    sent = [call.args[0] for call in co.send_command.call_args_list]
    scene = SCENES["rainbow"]
    assert sent == build_native_scene_packets("H617A", scene)
    assert co.effect == "rainbow"
    assert co.diy_code is None
    assert co.music_mode == "off" and co.video_mode == "off"


async def test_turn_on_effect_off_returns_to_static_colour(light, mock_coordinator):
    mock_coordinator.is_on = True
    mock_coordinator.effect = "rainbow"
    mock_coordinator.rgb_color = (12, 34, 56)
    mock_coordinator.segment_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)] * 5
    mock_coordinator.unknown_scene_code = 800

    await light.async_turn_on(effect="off")

    mock_coordinator.send_command.assert_awaited_once_with(build_color_rgb(12, 34, 56))
    assert mock_coordinator.effect is None
    assert mock_coordinator.unknown_scene_code is None
    assert mock_coordinator.segment_colors == [(12, 34, 56)] * 15
    assert mock_coordinator.segment_state_source == "optimistic"
    assert light.effect == "off"


async def test_turn_on_effect_off_restores_colour_temperature(light, mock_coordinator):
    mock_coordinator.is_on = True
    mock_coordinator.effect = "rainbow"
    mock_coordinator.color_temp_kelvin = 4000

    await light.async_turn_on(effect="off")

    mock_coordinator.send_command.assert_awaited_once_with(build_color_temp(4000))
    assert mock_coordinator.segment_colors == [kelvin_to_rgb(4000)] * 15
    assert light.color_mode is ColorMode.COLOR_TEMP


async def test_turn_on_scene_uses_the_device_stored_default(mock_coordinator):
    scene = MODEL_SCENES["H617A"]["forest"]
    scene_default = NativeSceneDefault(
        config_entry_id="entry-a",
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        updated_at="2026-08-17T00:00:00Z",
        canonical_body=b"\x00",
    )
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            scene_defaults=SimpleNamespace(
                get=MagicMock(return_value=scene_default),
            ),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entity.async_write_ha_state = MagicMock()
    mock_coordinator.is_on = True

    await entity.async_turn_on(effect="forest")

    assert [call.args[0] for call in mock_coordinator.send_command.await_args_list] == build_native_scene_packets(
        "H617A",
        scene,
        canonical_body=scene_default.canonical_body,
    )


async def test_h6199_scene_disables_linked_music(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.is_on = True
    co.effect_families = frozenset({"scenes"})
    await h6199_light.async_turn_on(effect="sunrise")
    sent = [call.args[0] for call in co.send_command.call_args_list]
    scene = MODEL_SCENES["H6199"]["sunrise"]
    assert sent == build_native_scene_packets("H6199", scene)
    assert sent[0][5:7] == b"\x00\x00"
    assert co.effect == "sunrise"


async def test_h6199_uploads_an_opted_in_scene(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.is_on = True
    co.effect_families = frozenset({"scenes"})
    await h6199_light.async_turn_on(effect="forest")
    scene = MODEL_SCENES["H6199"]["forest"]
    assert [call.args[0] for call in co.send_command.await_args_list] == build_native_scene_packets("H6199", scene)


async def test_turn_on_unknown_effect_raises(light, mock_coordinator):
    mock_coordinator.is_on = True
    with pytest.raises(ServiceValidationError):
        await light.async_turn_on(effect="does not exist")


@pytest.mark.parametrize(
    "effect,slug", [("Music: Rhythm", "rhythm"), ("Music: Piano Keys", "piano_keys"), ("music: rhythm", "rhythm")]
)
async def test_turn_on_music_effect_is_first_class(light, mock_coordinator, effect, slug):
    co = mock_coordinator
    co.is_on = True
    await light.async_turn_on(effect=effect)
    co.async_select_music_slug.assert_awaited_once_with(slug)


async def test_turn_on_music_effect_uses_the_device_template_default(mock_coordinator):
    content = MusicProfile("H617A", "rhythm", 42, None, False, {})
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            template_defaults=SimpleNamespace(
                get=MagicMock(return_value=SimpleNamespace(model="H617A", content=content)),
            ),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entity.async_write_ha_state = MagicMock()
    mock_coordinator.is_on = True

    with patch(
        "custom_components.ha_govee_led_ble.light.async_apply_compiled_profile",
        new_callable=AsyncMock,
    ) as apply_profile:
        await entity.async_turn_on(effect="Music: Rhythm")

    compiled = apply_profile.await_args.args[1]
    assert isinstance(compiled, CompiledMusicProfile)
    assert compiled.mode == "rhythm"
    assert compiled.sensitivity == 42
    backend.template_defaults.get.assert_called_once_with("entry-a", "template:music:rhythm")
    mock_coordinator.async_select_music_slug.assert_not_awaited()


@pytest.mark.parametrize("effect,mode", [("Video: Movie", "movie"), ("Video: Game", "game"), ("video: game", "game")])
async def test_turn_on_video_effect_is_first_class(h6199_light, mock_h6199_coordinator, effect, mode):
    co = mock_h6199_coordinator
    co.is_on = True
    co.video_full_screen = False
    co.video_saturation = 63
    co.video_sound_effects = True
    co.video_sound_effects_softness = 27
    co.refresh_state = AsyncMock(side_effect=[False, True])
    await h6199_light.async_turn_on(effect=effect)
    packet = build_h6199_video(False, mode == "game", 63, True, 27)
    assert [call.args[0] for call in co.send_command.call_args_list] == [
        build_power(True),
        packet,
        build_power(True),
        packet,
    ]
    for call in co.refresh_state.await_args_list:
        assert call.kwargs["expected_video_mode"] == mode
        assert call.kwargs["expected_video_full_screen"] is False
        assert call.kwargs["expected_video_saturation"] == 63
        assert call.kwargs["expected_video_sound_effects"] is True
        assert call.kwargs["expected_video_sound_effects_softness"] == 27
    assert co.video_mode == mode and co.effect is None


async def test_turn_on_video_effect_uses_the_device_template_default(mock_h6199_coordinator):
    content = VideoProfile(
        "H6199",
        "movie",
        False,
        63,
        True,
        27,
        10,
        RelativeBrightness(80, 70, 60, 50),
        True,
    )
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            template_defaults=SimpleNamespace(
                get=MagicMock(return_value=SimpleNamespace(model="H6199", content=content)),
            ),
        ),
    )
    entity = GoveeBLELight(
        mock_h6199_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )
    entity.async_write_ha_state = MagicMock()
    mock_h6199_coordinator.is_on = True

    with patch(
        "custom_components.ha_govee_led_ble.light.async_apply_compiled_profile",
        new_callable=AsyncMock,
    ) as apply_profile:
        await entity.async_turn_on(effect="Video: Movie")

    compiled = apply_profile.await_args.args[1]
    assert isinstance(compiled, CompiledVideoProfile)
    assert compiled.saturation == 63
    assert compiled.relative_brightness == (80, 70, 60, 50)
    backend.template_defaults.get.assert_called_once_with("entry-a", "template:video:movie")


async def test_effect_reflects_active_video_mode(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.effect = None
    mock_h6199_coordinator.video_mode = "movie"
    assert h6199_light.effect == "Movie"
    mock_h6199_coordinator.video_mode = "game"
    assert h6199_light.effect == "Game"
    mock_h6199_coordinator.video_mode = "off"
    mock_h6199_coordinator.effect = "rainbow"
    assert h6199_light.effect == "off"


def test_registers_segment_services_during_integration_setup():
    hass = MagicMock()
    hass.data = {}
    async_register_light_services(hass)
    registered = {call.args[1] for call in hass.services.async_register.call_args_list}
    assert registered == {
        "paint_segments",
        "set_segment_brightness",
        "set_segment_color",
    }


async def test_setup_entry_adds_light(mock_coordinator):
    entry = MagicMock(runtime_data=mock_coordinator)
    added: list = []
    await async_setup_entry(MagicMock(), entry, lambda entities: added.extend(entities))
    assert len(added) == 1 and isinstance(added[0], GoveeBLELight)


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("async_paint_segments", {"groups": []}),
        ("async_paint_segments", {"groups": [{"segments": [], "rgb_color": (1, 2, 3)}]}),
        ("async_set_segment_color", {"segments": [], "color": (1, 2, 3)}),
        ("async_set_segment_brightness", {"segments": [], "brightness": 50}),
    ],
)
async def test_segment_services_reject_empty_selections(light, mock_coordinator, method, kwargs):
    with pytest.raises(ServiceValidationError) as exc:
        await getattr(light, method)(**kwargs)
    assert exc.value.translation_key == "invalid_segments"
    mock_coordinator.send_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "kwargs", "expected"),
    [
        (
            "async_paint_segments",
            {
                "groups": [
                    {"segments": [1, 2, 3], "rgb_color": (255, 0, 0)},
                    {"segments": [4, 5], "rgb_color": (0, 255, 0)},
                ]
            },
            [([1, 2, 3], (255, 0, 0)), ([4, 5], (0, 255, 0))],
        ),
        (
            "async_set_segment_color",
            {"segments": [2, 4], "color": (10, 20, 30)},
            [([2, 4], (10, 20, 30))],
        ),
    ],
)
async def test_segment_colour_services_normalise_groups(
    light,
    mock_coordinator,
    method,
    kwargs,
    expected,
):
    await getattr(light, method)(**kwargs)

    mock_coordinator.async_paint_segments.assert_awaited_once_with(expected)


@pytest.mark.parametrize("error", [TypeError("bad segment"), ValueError("bad colour")])
async def test_paint_segments_reports_invalid_input(light, mock_coordinator, error):
    mock_coordinator.async_paint_segments.side_effect = error

    with pytest.raises(ServiceValidationError) as exc:
        await light.async_paint_segments([{"segments": [1], "rgb_color": (1, 2, 3)}])

    assert exc.value.translation_key == "invalid_segments"


async def test_segment_service_wraps_transport_failure(light, mock_coordinator):
    mock_coordinator.async_paint_segments.side_effect = BleakError("transport failed")

    with pytest.raises(HomeAssistantError) as exc:
        await light.async_paint_segments([{"segments": [1], "rgb_color": (1, 2, 3)}])
    assert exc.value.translation_key == "device_command_failed"


async def test_set_segment_brightness_sends_packet(light, mock_coordinator):
    light.async_write_ha_state = MagicMock()
    await light.async_set_segment_brightness(segments=[2, 4], brightness=60)
    mock_coordinator.async_set_segment_brightness.assert_awaited_once_with([2, 4], 60)
    light.async_write_ha_state.assert_called_once_with()


async def test_segment_services_reject_unsupported(mock_coordinator):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=0)
    e = GoveeBLELight(mock_coordinator)
    e.async_write_ha_state = MagicMock()
    actions = (
        lambda: e.async_paint_segments([{"segments": [1], "rgb_color": (1, 2, 3)}]),
        lambda: e.async_set_segment_color(segments=[1], color=(1, 2, 3)),
        lambda: e.async_set_segment_brightness(segments=[1], brightness=50),
    )
    for action in actions:
        with pytest.raises(ServiceValidationError) as exc:
            await action()
        assert exc.value.translation_key == "unsupported_model"
        assert exc.value.translation_placeholders is not None
        assert exc.value.translation_placeholders["model"] == "H617A"
    mock_coordinator.async_paint_segments.assert_not_awaited()
    mock_coordinator.send_command.assert_not_called()


def test_segment_colors_attribute_present(light, mock_coordinator):
    mock_coordinator.segment_colors = [(10, 20, 30)] * 15
    assert light.extra_state_attributes == {
        "segment_colors": [[10, 20, 30]] * 15,
        "segment_brightness": [100] * 15,
        "segment_state_source": "initial",
    }


def test_h6199_segment_surface_is_exposed(h6199_light):
    assert h6199_light.extra_state_attributes == {
        "segment_colors": [[255, 255, 255]] * 15,
        "segment_brightness": [100] * 15,
        "segment_state_source": "initial",
    }


async def test_whole_strip_write_fills_segment_colors(light, mock_coordinator):
    mock_coordinator.segment_colors = [(1, 2, 3)] * 15
    await light.async_turn_on(rgb_color=(10, 20, 30))
    assert mock_coordinator.segment_colors == [(10, 20, 30)] * 15
    await light.async_turn_on(color_temp_kelvin=4000)
    assert mock_coordinator.segment_colors == [kelvin_to_rgb(4000)] * 15


def test_segment_colors_attribute_absent_for_zero_count(mock_coordinator):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=0)
    mock_coordinator.segment_colors = []
    attrs = GoveeBLELight(mock_coordinator).extra_state_attributes
    assert "segment_colors" not in attrs
    assert attrs == {}


@pytest.mark.parametrize(
    (
        "segment_count",
        "initial_colors",
        "initial_source",
        "stored_colors",
        "stored_brightness",
        "expected_colors",
        "expected_brightness",
        "reads_last_state",
        "updates_coordinator",
    ),
    [
        pytest.param(
            15,
            [(255, 255, 255)] * 15,
            "initial",
            [[1, 2, 3]] * 15,
            [40] * 15,
            [(1, 2, 3)] * 15,
            [40] * 15,
            True,
            True,
            id="restores-last-state",
        ),
        pytest.param(
            15,
            [(255, 255, 255)] * 15,
            "observed",
            [[1, 2, 3]] * 15,
            [40] * 15,
            [(255, 255, 255)] * 15,
            [100] * 15,
            False,
            False,
            id="observed-white-device-state",
        ),
        pytest.param(
            15,
            [(255, 255, 255)] * 15,
            "initial",
            [[1, 2, 3]] * 15,
            None,
            [(255, 255, 255)] * 15,
            [100] * 15,
            True,
            False,
            id="missing-brightness",
        ),
        pytest.param(
            15,
            [(255, 255, 255)] * 15,
            "initial",
            [[1, 2]] * 15,
            [40] * 15,
            [(255, 255, 255)] * 15,
            [100] * 15,
            True,
            False,
            id="malformed-last-state",
        ),
        pytest.param(0, [], "initial", [[1, 2, 3]], [40], [], [], False, False, id="unsupported-model"),
    ],
)
async def test_segment_restore(
    light,
    mock_coordinator,
    segment_count,
    initial_colors,
    initial_source,
    stored_colors,
    stored_brightness,
    expected_colors,
    expected_brightness,
    reads_last_state,
    updates_coordinator,
):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=segment_count)
    mock_coordinator.segment_colors = initial_colors
    mock_coordinator.segment_brightness = [100] * segment_count
    mock_coordinator.segment_state_source = initial_source
    last_state = MagicMock(
        attributes={
            "segment_colors": stored_colors,
            "segment_brightness": stored_brightness,
        }
    )
    light.async_get_last_state = AsyncMock(return_value=last_state)

    await light._async_restore_segments()

    assert mock_coordinator.segment_colors == expected_colors
    assert mock_coordinator.segment_brightness == expected_brightness
    assert mock_coordinator.segment_state_source == ("restored" if updates_coordinator else initial_source)
    if reads_last_state:
        light.async_get_last_state.assert_awaited_once()
    else:
        light.async_get_last_state.assert_not_awaited()
    if updates_coordinator:
        mock_coordinator.async_set_updated_data.assert_called_once_with(mock_coordinator.data)
    else:
        mock_coordinator.async_set_updated_data.assert_not_called()


def test_coerce_segment_colors_variants():
    assert _coerce_segment_colors([[1, 2, 3], [4, 5, 6]], 2) == [(1, 2, 3), (4, 5, 6)]
    assert _coerce_segment_colors([[300, -5, 10]], 1) == [(255, 0, 10)]
    assert _coerce_segment_colors([(7, 8, 9)], 1) == [(7, 8, 9)]
    assert _coerce_segment_colors("nope", 1) is None
    assert _coerce_segment_colors([[1, 2, 3]], 2) is None
    assert _coerce_segment_colors([[1, 2]], 1) is None
    assert _coerce_segment_colors([["a", "b", "c"]], 1) is None
    assert _coerce_segment_brightness([0, 50, 100], 3) == [0, 50, 100]
    assert _coerce_segment_brightness([-1, 101], 2) == [0, 100]
    assert _coerce_segment_brightness([True], 1) is None


async def test_async_added_to_hass_triggers_restore(light):
    light._async_restore_static_color = AsyncMock()
    light._async_restore_segments = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ) as super_added:
        await light.async_added_to_hass()
    super_added.assert_awaited_once()
    light._async_restore_static_color.assert_awaited_once()
    light._async_restore_segments.assert_awaited_once()


async def test_restore_static_rgb_as_last_known_presentation(light, mock_coordinator):
    mock_coordinator.color_mode = ParsedMode.COLOUR
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.RGB,
                "rgb_color": [12, 34, 56],
                "segment_colors": [[12, 34, 56]] * 15,
                "segment_brightness": [100] * 15,
            }
        )
    )

    await light._async_restore_static_color()
    await light._async_restore_segments()

    assert mock_coordinator.rgb_color == (12, 34, 56)
    assert mock_coordinator.segment_colors == [(12, 34, 56)] * 15
    assert light._attr_color_mode is ColorMode.RGB
    mock_coordinator.send_command.assert_not_awaited()


async def test_restore_static_colour_temperature_as_last_known_presentation(light, mock_coordinator):
    mock_coordinator.color_mode = ParsedMode.COLOUR
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.COLOR_TEMP,
                "color_temp_kelvin": 4200,
            }
        )
    )

    await light._async_restore_static_color()

    assert mock_coordinator.color_temp_kelvin == 4200
    assert light._attr_color_mode is ColorMode.COLOR_TEMP
    mock_coordinator.send_command.assert_not_awaited()


async def test_restore_static_state_never_replaces_observed_segments(light, mock_coordinator):
    mock_coordinator.color_mode = ParsedMode.COLOUR
    mock_coordinator.segment_state_source = "observed"
    mock_coordinator.segment_colors = [(255, 255, 255)] * 15
    mock_coordinator.rgb_color = (255, 255, 255)
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.RGB,
                "rgb_color": [12, 34, 56],
                "segment_colors": [[12, 34, 56]] * 15,
                "segment_brightness": [50] * 15,
            }
        )
    )

    await light._async_restore_static_color()
    await light._async_restore_segments()

    assert mock_coordinator.rgb_color == (255, 255, 255)
    assert mock_coordinator.segment_colors == [(255, 255, 255)] * 15
    assert mock_coordinator.segment_brightness == [100] * 15
    assert mock_coordinator.segment_state_source == "observed"
    mock_coordinator.mark_segment_state_restored.assert_not_called()


async def test_restore_kelvin_only_when_observed_companion_matches(light, mock_coordinator):
    mock_coordinator.color_mode = ParsedMode.COLOUR
    mock_coordinator.segment_state_source = "observed"
    mock_coordinator.segment_colors = [kelvin_to_rgb(4200)] * 15
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.COLOR_TEMP,
                "color_temp_kelvin": 4200,
            }
        )
    )

    await light._async_restore_static_color()

    assert mock_coordinator.color_temp_kelvin == 4200
    assert mock_coordinator.segment_state_source == "observed"


async def test_restore_static_colour_never_overwrites_a_live_effect(light, mock_coordinator):
    mock_coordinator.color_mode = ParsedMode.SCENE
    mock_coordinator.effect = "rainbow"
    light.async_get_last_state = AsyncMock()

    await light._async_restore_static_color()

    light.async_get_last_state.assert_not_called()
    assert mock_coordinator.effect == "rainbow"


async def test_control_lock_keeps_failed_rollback_before_newer_colour(light, mock_coordinator):
    mock_coordinator.is_on = True
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    sent: list[bytes] = []
    red = build_color_rgb(255, 0, 0)
    blue = build_color_rgb(0, 0, 255)

    async def send(packet: bytes) -> None:
        sent.append(packet)
        if packet == red:
            first_started.set()
            await release_first.wait()
            raise BleakError("failed red write")

    mock_coordinator.send_command = AsyncMock(side_effect=send)
    first = asyncio.create_task(light.async_turn_on(rgb_color=(255, 0, 0)))
    await first_started.wait()
    second = asyncio.create_task(light.async_turn_on(rgb_color=(0, 0, 255)))
    await asyncio.sleep(0)
    assert sent == [red]

    release_first.set()
    with pytest.raises(HomeAssistantError) as exc:
        await first
    assert exc.value.translation_key == "device_command_failed"
    await second

    assert sent == [red, blue]
    assert mock_coordinator.rgb_color == (0, 0, 255)
