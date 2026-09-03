"""H6179 Home Assistant snapshot and restore-state integration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from homeassistant.components import light as light_component
from homeassistant.components.light import ColorMode
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import RestoredExtraData
from homeassistant.setup import async_setup_component

from custom_components.ha_govee_led_ble.const import (
    EFFECT_CATEGORY_REACTIVE,
    EFFECT_CATEGORY_SCENES,
    EFFECT_FAMILY_MUSIC,
    EFFECT_FAMILY_SCENES,
    MODEL_PROFILES,
    ModelProfile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_runtime import observable_signature_for_coordinator
from custom_components.ha_govee_led_ble.effect_storage import EffectLibraryRepository
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_music_mode,
    build_power,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore

ENTITY_ID = "light.h6179_snapshot"
ENTRY_ID = "h6179-snapshot-entry"


@dataclass(slots=True)
class H6179LightHarness:
    coordinator: GoveeBLECoordinator
    entity: GoveeBLELight
    sent: list[bytes]


def _status(domain: int, body: bytes) -> bytes:
    packet = bytearray((0xAA, domain))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def _enabled_profile() -> ModelProfile:
    return replace(
        MODEL_PROFILES["H6179"],
        supports_power=True,
        supports_brightness=True,
        supports_rgb=True,
        supports_color_temperature=True,
        supports_color_mode_readback=True,
        supports_scenes=True,
        music_modes=("mode_0", "mode_1"),
        music_sensitivity_min=0,
        music_sensitivity_max=99,
        supports_music_color=True,
    )


async def _setup_light(
    hass: HomeAssistant,
    profile: ModelProfile,
    *,
    effect_backend: EffectBackend | None = None,
    last_state: State | None = None,
    last_extra_data: RestoredExtraData | None = None,
) -> H6179LightHarness:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
        effect_families=frozenset({EFFECT_FAMILY_SCENES, EFFECT_FAMILY_MUSIC}),
        effect_categories=frozenset({EFFECT_CATEGORY_SCENES, EFFECT_CATEGORY_REACTIVE}),
    )
    coordinator.profile = profile
    coordinator._present = True
    sent: list[bytes] = []

    async def send(packet: bytes) -> None:
        sent.append(packet)
        coordinator._arm_expected(packet)
        if packet[:2] == b"\x33\x01":
            coordinator._notify_callback(None, bytearray(_status(0x01, packet[2:3])))
        elif packet[:2] == b"\x33\x04":
            coordinator._notify_callback(None, bytearray(_status(0x04, packet[2:3])))
        elif packet[:2] == b"\x33\x05":
            coordinator._notify_callback(None, bytearray(_status(0x05, packet[2:19])))

    coordinator.send_command = AsyncMock(side_effect=send)  # type: ignore[method-assign]

    async def write_sequence(packets: list[bytes] | tuple[bytes, ...], **_kwargs: Any) -> None:
        for packet in packets:
            await send(packet)

    coordinator.async_write_effect_sequence = AsyncMock(side_effect=write_sequence)  # type: ignore[method-assign]
    entity = GoveeBLELight(
        coordinator,
        config_entry_id=ENTRY_ID,
        effect_backend=effect_backend,
    )
    entity.entity_id = ENTITY_ID
    if last_state is not None:
        entity.async_get_last_state = AsyncMock(return_value=last_state)  # type: ignore[method-assign]
        entity.async_get_last_extra_data = AsyncMock(return_value=last_extra_data)  # type: ignore[method-assign]
    await hass.data[light_component.DATA_COMPONENT].async_add_entities([entity])
    await hass.async_block_till_done()
    return H6179LightHarness(coordinator, entity, sent)


async def _turn_on(hass: HomeAssistant, **data: Any) -> None:
    await hass.services.async_call(
        light_component.DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _capture_scene(hass: HomeAssistant, scene_id: str) -> State:
    await hass.services.async_call(
        "scene",
        "create",
        {
            "scene_id": scene_id,
            "snapshot_entities": [ENTITY_ID],
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    scene = hass.data["homeassistant_scene"].entities[f"scene.{scene_id}"]
    return scene.scene_config.states[ENTITY_ID]


async def _replay_scene(hass: HomeAssistant, scene_id: str) -> None:
    await hass.services.async_call(
        "scene",
        "turn_on",
        {ATTR_ENTITY_ID: f"scene.{scene_id}"},
        blocking=True,
    )
    await hass.async_block_till_done()


@pytest.fixture
async def h6179_hass(hass: HomeAssistant) -> AsyncIterator[tuple[HomeAssistant, ModelProfile]]:
    profile = _enabled_profile()
    with patch.dict(MODEL_PROFILES, {"H6179": profile}):
        assert await async_setup_component(hass, light_component.DOMAIN, {})
        assert await async_setup_component(hass, "scene", {})
        await hass.async_block_till_done()
        yield hass, profile


@pytest.mark.parametrize(
    ("scene_id", "target", "mutation", "expected"),
    [
        ("h6179_power", {}, None, {"state": STATE_ON}),
        ("h6179_brightness", {"brightness": 64}, {"brightness": 191}, {"state": STATE_ON, "brightness": 64}),
        (
            "h6179_rgb",
            {"rgb_color": (12, 34, 56)},
            {"color_temp_kelvin": 5000},
            {
                "state": STATE_ON,
                "color_mode": ColorMode.RGB,
                "rgb_color": (12, 34, 56),
            },
        ),
        (
            "h6179_temperature",
            {"color_temp_kelvin": 4200},
            {"rgb_color": (200, 10, 20)},
            {
                "state": STATE_ON,
                "color_mode": ColorMode.COLOR_TEMP,
                "color_temp_kelvin": 4200,
            },
        ),
        (
            "h6179_native_scene",
            {"effect": "Energetic"},
            {"rgb_color": (200, 10, 20)},
            {"state": STATE_ON, "effect": "Energetic"},
        ),
    ],
)
async def test_native_scene_capture_replays_standard_light_state(
    h6179_hass: tuple[HomeAssistant, ModelProfile],
    scene_id: str,
    target: dict[str, Any],
    mutation: dict[str, Any] | None,
    expected: dict[str, Any],
) -> None:
    hass, profile = h6179_hass
    harness = await _setup_light(hass, profile)

    await _turn_on(hass, **target)
    captured = await _capture_scene(hass, scene_id)
    if mutation is None:
        await hass.services.async_call(
            light_component.DOMAIN,
            "turn_off",
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )
    else:
        await _turn_on(hass, **mutation)

    await _replay_scene(hass, scene_id)

    current = hass.states.get(ENTITY_ID)
    assert current is not None
    expected_state = expected["state"]
    assert captured.state == expected_state
    assert current.state == captured.state
    assert all(current.attributes[key] == value for key, value in expected.items() if key != "state")
    assert harness.coordinator.active_mode == ("scene" if scene_id == "h6179_native_scene" else "colour")


@pytest.mark.parametrize(
    ("scene_id", "presentation", "color_mode", "state_attribute", "expected"),
    [
        ("h6179_off_rgb", {"rgb_color": (12, 34, 56)}, ColorMode.RGB, "rgb_color", (12, 34, 56)),
        (
            "h6179_off_temperature",
            {"color_temp_kelvin": 4200},
            ColorMode.COLOR_TEMP,
            "color_temp_kelvin",
            4200,
        ),
    ],
)
async def test_off_state_restart_restores_presentation_and_native_replay(
    h6179_hass: tuple[HomeAssistant, ModelProfile],
    scene_id: str,
    presentation: dict[str, Any],
    color_mode: ColorMode,
    state_attribute: str,
    expected: Any,
) -> None:
    hass, profile = h6179_hass
    first = await _setup_light(hass, profile)
    await _turn_on(hass, brightness=64, **presentation)
    await hass.services.async_call(
        light_component.DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    await hass.async_block_till_done()
    captured = await _capture_scene(hass, scene_id)
    extra_data = first.entity.extra_restore_state_data
    assert extra_data is not None

    await hass.data[light_component.DATA_COMPONENT].async_remove_entity(ENTITY_ID)
    restarted = await _setup_light(
        hass,
        profile,
        last_state=captured,
        last_extra_data=RestoredExtraData(extra_data.as_dict()),
    )
    restarted.coordinator.brightness_pct = 25
    restarted.coordinator.async_set_updated_data(restarted.coordinator.data or {})
    await hass.async_block_till_done()

    restored = hass.states.get(ENTITY_ID)
    assert restored is not None
    assert restored.state == STATE_OFF
    assert restored.attributes["brightness"] is None
    assert restarted.entity.color_mode == color_mode
    assert getattr(restarted.entity, state_attribute) == expected
    assert restarted.sent == []

    await _turn_on(hass)
    on_state = hass.states.get(ENTITY_ID)
    assert on_state is not None
    assert on_state.attributes["brightness"] == 64
    assert on_state.attributes[state_attribute] == expected
    before_replay = len(restarted.sent)
    await _replay_scene(hass, scene_id)

    assert restarted.sent[before_replay:] == [build_power(False, "H6179")]
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert getattr(restarted.coordinator, state_attribute) == expected


async def test_external_app_handoff_can_be_captured_replayed_and_replaced(
    h6179_hass: tuple[HomeAssistant, ModelProfile],
) -> None:
    hass, profile = h6179_hass
    harness = await _setup_light(hass, profile)
    client = MagicMock()
    harness.coordinator._client = client
    harness.coordinator._clear_client_state(client)

    harness.coordinator._notify_callback(None, bytearray(_status(0x01, b"\x01")))
    harness.coordinator._notify_callback(None, bytearray(_status(0x04, b"\x88")))
    harness.coordinator._notify_callback(None, bytearray(_status(0x05, b"\x04\x0a\x00")))
    await hass.async_block_till_done()

    assert harness.coordinator.effect == "breathe"
    external = hass.states.get(ENTITY_ID)
    assert external is not None
    assert external.state == STATE_ON
    assert external.attributes["effect"] == "Breathe"
    await _capture_scene(hass, "h6179_external")

    await _turn_on(hass, rgb_color=(12, 34, 56))
    assert harness.coordinator.active_mode == "colour"
    static_state = hass.states.get(ENTITY_ID)
    assert static_state is not None
    assert static_state.attributes["effect"] == "off"

    await _replay_scene(hass, "h6179_external")
    assert harness.coordinator.active_mode == "scene"
    replayed = hass.states.get(ENTITY_ID)
    assert replayed is not None
    assert replayed.attributes["effect"] == "Breathe"

    harness.coordinator._expected_state.clear()
    harness.coordinator._notify_callback(
        None,
        bytearray(_status(0x05, build_color_rgb(7, 8, 9, "H6179")[2:19])),
    )
    await hass.async_block_till_done()
    assert harness.coordinator.rgb_color == (7, 8, 9)
    rgb_state = hass.states.get(ENTITY_ID)
    assert rgb_state is not None
    assert rgb_state.attributes["color_mode"] == ColorMode.RGB
    assert rgb_state.attributes["rgb_color"] == (7, 8, 9)

    harness.coordinator._notify_callback(
        None,
        bytearray(_status(0x05, build_color_temp(4200, "H6179")[2:19])),
    )
    await hass.async_block_till_done()
    assert harness.coordinator.color_temp_kelvin == 4200
    temperature_state = hass.states.get(ENTITY_ID)
    assert temperature_state is not None
    assert temperature_state.attributes["color_mode"] == ColorMode.COLOR_TEMP
    assert temperature_state.attributes["color_temp_kelvin"] == 4200

    harness.coordinator._notify_callback(
        None,
        bytearray(_status(0x05, b"\x0e\x01\x32\x01\x01\x02\x03")),
    )
    await hass.async_block_till_done()
    assert harness.coordinator.active_mode == "music"

    await _turn_on(hass, color_temp_kelvin=4200)
    assert harness.coordinator.active_mode == "colour"
    assert harness.coordinator.music_mode == "off"
    assert harness.coordinator.effect is None


async def test_saved_music_profile_replay_reuses_existing_library_item(
    h6179_hass: tuple[HomeAssistant, ModelProfile],
) -> None:
    hass, profile = h6179_hass
    store = InMemoryVersionedDocumentStore()
    library = EffectLibraryRepository(store)
    await library.async_load()
    item = LibraryItem.new(
        "Saved H6179 music",
        MusicProfile("H6179", "mode_1", 50, (1, 2, 3)),
    )
    await library.async_create(item)
    active_hint: SimpleNamespace | None = None

    @asynccontextmanager
    async def saved_effect_for_apply(
        item_id: str,
        *,
        expected_version: int | None = None,
    ) -> AsyncIterator[LibraryItem]:
        current = library.get(UUID(item_id))
        assert expected_version in (None, current.version)
        yield current

    coordinator_ref: GoveeBLECoordinator | None = None

    async def apply_saved(
        coordinator: GoveeBLECoordinator,
        selected: LibraryItem,
        **_kwargs: Any,
    ) -> MagicMock:
        nonlocal active_hint, coordinator_ref
        coordinator_ref = coordinator
        content = cast(MusicProfile, selected.content)
        coordinator.install_music_profile_state(
            mode=content.mode,
            sensitivity=content.sensitivity,
            colour=content.colour,
            calm=bool(content.calm),
            parameters=content.parameters,
        )
        await coordinator.async_select_music_slug(content.mode)
        active_hint = SimpleNamespace(
            source_kind="saved_effect",
            item_id=selected.id,
            content_hash=selected.content_hash,
            observable_signature=observable_signature_for_coordinator(coordinator),
        )
        coordinator.async_set_updated_data(coordinator.data or {})
        return MagicMock()

    application = SimpleNamespace(
        library_snapshot=library.snapshot,
        subscribe_library=library.subscribe,
        saved_effect_for_apply=saved_effect_for_apply,
    )
    engine = SimpleNamespace(async_apply_saved=AsyncMock(side_effect=apply_saved))
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=application,
            engine=engine,
            device_cache=SimpleNamespace(
                get=lambda _entry_id: None if active_hint is None else SimpleNamespace(active_effect=active_hint)
            ),
            active_workspaces=SimpleNamespace(get=lambda _entry_id: None, clear=MagicMock()),
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
        ),
    )
    harness = await _setup_light(hass, profile, effect_backend=backend)

    assert "Saved H6179 music" in harness.entity.effect_list
    await _turn_on(hass, effect="Saved H6179 music")
    music_state = hass.states.get(ENTITY_ID)
    assert music_state is not None
    assert music_state.attributes["effect"] == "Saved H6179 music"
    await _capture_scene(hass, "h6179_saved_music")

    await _turn_on(hass, rgb_color=(12, 34, 56))
    assert harness.coordinator.active_mode == "colour"
    await _replay_scene(hass, "h6179_saved_music")

    assert coordinator_ref is harness.coordinator
    assert harness.coordinator.active_mode == "music"
    assert harness.coordinator.music_mode == "mode_1"
    assert harness.coordinator.music_sensitivity == 50
    assert harness.coordinator.music_color == (1, 2, 3)
    assert engine.async_apply_saved.await_count == 2
    assert all(
        (
            call.args[1].id,
            call.args[1].version,
            call.args[1].content_hash,
        )
        == (item.id, item.version, item.content_hash)
        for call in engine.async_apply_saved.await_args_list
    )
    assert library.snapshot().items == (item,)
    assert library.snapshot().generation == 1
    assert store.save_count == 1
    assert build_music_mode(1, 50, (1, 2, 3), False, "H6179") in harness.sent


async def test_effect_control_restore_uses_the_h6179_music_codebook(
    h6179_hass: tuple[HomeAssistant, ModelProfile],
) -> None:
    hass, profile = h6179_hass
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )
    coordinator.profile = replace(profile, state_readable=True)
    coordinator.refresh_state = AsyncMock(return_value=True)  # type: ignore[method-assign]
    coordinator.send_command = AsyncMock()  # type: ignore[method-assign]
    prior = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=50,
        rgb_color=(12, 34, 56),
        music_mode="mode_1",
        music_sensitivity=50,
        music_color=(1, 2, 3),
    )

    restored = await coordinator.async_restore_effect_control_state(
        prior,
        overwritten_diy_code=None,
    )

    assert restored is True
    assert [call.args[0] for call in coordinator.send_command.await_args_list] == [
        build_power(True, "H6179"),
        build_music_mode(1, 50, (1, 2, 3), False, "H6179"),
    ]
    coordinator.refresh_state.assert_awaited_once_with(
        expected_on=True,
        expected_music_mode="mode_1",
        expected_music_sensitivity=50,
        expected_music_color=(1, 2, 3),
        expected_music_auto_color=False,
    )
