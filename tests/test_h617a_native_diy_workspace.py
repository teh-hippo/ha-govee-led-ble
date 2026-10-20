"""Native DIY identity survives shared upload-canonicalized workspace content."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, get_profile
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_a3_effect_frames
from custom_components.ha_govee_led_ble.effect_runtime import (
    _active_workspace_content,
    active_workspace_matches,
    observable_signature_for_compiled,
)
from tests.storage_test_double import InMemoryVersionedDocumentStore


@pytest.mark.parametrize("code", range(501, 508))
async def test_workspace_persist_reload_recompile_retains_native_carrier_and_ack(
    code: int,
) -> None:
    template = resolve_catalogue_template("H617A", f"template:native-diy:{code}")
    source = template.content
    assert isinstance(source, LayeredEffect)
    # Distinguish the actual compiled upload from the source so returning source
    # instead of canonicalizing the upload cannot satisfy this regression.
    edited = replace(source, layers=(replace(source.layers[0], colour_speed=123), *source.layers[1:]))
    item = LibraryItem.new(template.label, edited)
    compiled = compile_effect(item, "H617A")
    decoded = decode_a3_effect_frames(compiled.upload_packets, "H617A")
    assert isinstance(decoded, LayeredEffect)
    assert decoded.native_diy is None
    assert _active_workspace_content(source, None) is source
    canonical = _active_workspace_content(source, compiled)
    assert isinstance(canonical, LayeredEffect)
    assert canonical.native_diy == code
    assert canonical.layers == decoded.layers
    signature = observable_signature_for_compiled(compiled)
    assert signature == f"scene-code:{code}"
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label=template.label,
        content=canonical,
        origin=item.origin,
        observable_signature=signature,
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
    restored = reloaded.get("entry-a")
    assert restored is not None
    coordinator: Any = SimpleNamespace(
        model="H617A",
        is_on=True,
        scene_code=code,
        diy_code=None,
        effect=None,
    )
    assert active_workspace_matches(coordinator, restored)
    rebuilt = compile_effect(LibraryItem.new(restored.selector_label, restored.content), "H617A")
    assert rebuilt.packets == compiled.packets
    assert rebuilt.artifact_sha256 == compiled.artifact_sha256
    assert rebuilt.diy_code == code
    assert rebuilt.selector_kind == "scene"
    assert "native_diy_positive_ack_required" in rebuilt.evidence_codes
    for wrong_code in (401, 24, 507 if code == 501 else 501):
        coordinator.scene_code = wrong_code
        assert not active_workspace_matches(coordinator, restored)
        # Even an independently matching signature must not override identity.
        assert not active_workspace_matches(
            coordinator,
            replace(restored, observable_signature=f"scene-code:{wrong_code}"),
        )
    coordinator.scene_code = code
    coordinator.is_on = False
    assert not active_workspace_matches(coordinator, restored)
    coordinator.is_on = True
    coordinator.model = "H617E"
    assert not active_workspace_matches(coordinator, restored)


def test_h7020_workspace_matches_approved_slot_not_body_template(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = replace(
        get_profile("H7020"),
        command_operations=None,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
    )
    monkeypatch.setitem(MODEL_PROFILES, "H7020", profile)
    source = resolve_catalogue_template("H7020", "template:native-diy:17").content
    assert isinstance(source, LayeredEffect)
    compiled = compile_effect(LibraryItem.new("Spin", source), "H7020", diy_code=321, profile=profile)
    canonical = _active_workspace_content(source, compiled)
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H7020",
        selector_label="Spin",
        content=canonical,
        origin=LibraryItem.new("Spin", source).origin,
        observable_signature="custom:321",
        updated_at="2026-10-21T00:00:00Z",
        generation=1,
    )
    coordinator: Any = SimpleNamespace(
        model="H7020",
        is_on=True,
        scene_code=None,
        diy_code=321,
        effect=None,
    )

    assert active_workspace_matches(coordinator, workspace)
    coordinator.diy_code = 17
    assert not active_workspace_matches(coordinator, workspace)
