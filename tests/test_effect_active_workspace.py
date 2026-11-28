"""Selector domains survive workspace reload without guessing from slot numbers."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import (
    LegacyEffectSelectorDomain,
    ModelProfile,
    device_profile,
    get_profile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_catalogue import WORKSHOP_PROTOCOL_FIXTURES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    OpaqueContent,
    Origin,
    PaletteDiyEffect,
    SingleEffect,
    SourceKind,
)
from custom_components.ha_govee_led_ble.effect_identity import (
    legacy_deployment_effect_signature,
    legacy_effect_selector_domain,
)
from custom_components.ha_govee_led_ble.effect_runtime import (
    active_workspace_matches,
    observable_signature_for_compiled,
)
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore


@pytest.mark.parametrize(
    ("model", "content", "signature", "expected"),
    [
        ("H617A", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"), "custom:24", "scene-code:24"),
        ("H617E", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617E"), "custom:24", "scene-code:24"),
        ("H6199", WORKSHOP_PROTOCOL_FIXTURES[0].content("H6199"), "custom:24", "scene-code:24"),
        ("H6199", PaletteDiyEffect("H6199", 8, 9, 60, ((255, 0, 0),)), "custom:24", "custom:24"),
        (
            "H6199",
            PaletteDiyEffect("H6199", 8, 9, 60, ((255, 0, 0),)),
            "custom:401",
            "scene-code:401",
        ),
        ("H617A", SingleEffect(0, 0, 50, ((255, 0, 0),)), "custom:24", "custom:24"),
        ("H617E", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"), "custom:24", "custom:24"),
        ("H617A", OpaqueContent("shared_scene", {"model": "H6199"}), "custom:24", "custom:24"),
    ],
)
async def test_legacy_workspace_selector_migration_is_content_scoped(model, content, signature, expected) -> None:
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model=model,
        selector_label="Custom",
        content=content,
        origin=Origin(SourceKind.AUTHORED),
        observable_signature=signature,
        updated_at="2026-08-26T00:00:00Z",
        generation=1,
    )
    store = InMemoryVersionedDocumentStore({"devices": {"entry-a": workspace.to_dict()}})
    repository = ActiveEffectWorkspaceRepository(store)
    assert (await repository.async_load())[0].observable_signature == expected
    await repository.async_flush()
    reloaded = ActiveEffectWorkspaceRepository(store)
    assert (await reloaded.async_load())[0].observable_signature == expected


def test_legacy_selector_policy_is_route_semantic() -> None:
    profile = ModelProfile(
        "Synthetic profile",
        legacy_effect_selector_domains=(
            ("diy-route", LegacyEffectSelectorDomain.DIY),
            ("scene-route", LegacyEffectSelectorDomain.SCENE),
        ),
    )

    assert legacy_effect_selector_domain(profile, "diy-route") is LegacyEffectSelectorDomain.DIY
    assert legacy_effect_selector_domain(profile, "unknown-route") is None
    assert legacy_deployment_effect_signature(profile, "diy-route", 321) == "custom:321"
    assert legacy_deployment_effect_signature(profile, "scene-route", 321) == "scene-code:321"
    assert legacy_deployment_effect_signature(profile, "scene-route", None) is None
    assert legacy_deployment_effect_signature(profile, "unknown-route", 321) is None


@pytest.mark.parametrize("model", ["H6159", "H617A"])
async def test_authored_palette_workspace_retains_template_identity_under_its_effective_selector(hass, model):
    profile = (
        device_profile(model, 1, 1, firmware="1.07.02", hardware="1.00.02") if model == "H6159" else get_profile(model)
    )
    scene = next(scene for scene in SCENE_ENTRIES[model] if scene.scene_type == 1)
    content = decode_catalogue_palette_scene(model, scene)
    assert content is not None
    item = LibraryItem.new("Palette programme", content)
    compiled = compile_effect(item, model, profile=profile)
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model=model,
        selector_label=item.name,
        content=content,
        origin=item.origin,
        observable_signature=observable_signature_for_compiled(compiled),
        updated_at=item.updated_at,
        generation=1,
    )
    store = InMemoryVersionedDocumentStore()
    repository = ActiveEffectWorkspaceRepository(store)
    await repository.async_load()
    assert repository.set(workspace)
    await repository.async_flush()
    reloaded = ActiveEffectWorkspaceRepository(store)
    assert await reloaded.async_load() == (workspace,)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    coordinator.profile = replace(profile, profile_identity_fields=frozenset())
    if model == "H6159":
        coordinator.pact_type, coordinator.pact_code = 1, 1
        coordinator._confirmed_identity_fields.add("pact")
    coordinator.is_on = True
    assert (
        compile_effect(LibraryItem.new(item.name, workspace.content), model, profile=profile).packets
        == compiled.packets
    )
    assert compiled.diy_code is not None
    for selector, matches in ((compiled.diy_code, True), (65000, False)):
        payload = bytes([0xAA, 5, 4, selector & 255, selector >> 8]).ljust(19, b"\0")
        coordinator._notify_callback(None, bytearray(payload + bytes([xor_checksum(payload)])))
        assert active_workspace_matches(coordinator, reloaded.get("entry-a")) is matches
    assert not active_workspace_matches(coordinator, replace(workspace, observable_signature="scene-code:65000"))
