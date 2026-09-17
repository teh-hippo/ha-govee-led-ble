"""Runtime qualification at selector, advertisement and recovery boundaries."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from custom_components.ha_govee_led_ble import select, sensor
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, PaletteDiyEffect, VideoProfile
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefault
from custom_components.ha_govee_led_ble.effect_websocket import _device_payload
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_power
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_h6099 import frame


@pytest.fixture
def coordinator(hass):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c.fw_version, c.hw_version = "1.10.04", "3.02.01"
    c.subordinate_20_version, c.subordinate_21_version = "1.03.00", "1.00.33"
    c.pact_type, c.pact_code = 2, 1
    return c


@pytest.mark.parametrize("source", ["saved", "snapshot"])
@pytest.mark.parametrize("kind", ["music", "custom"])
async def test_non_video_failure_restores_power_without_white_balance(coordinator, monkeypatch, source, kind):
    c = coordinator
    c.white_balance_flag, c.white_balance_red, c.white_balance_blue = 0, 21, 5
    # The hidden resident mode is unknown: power-off recovery cannot prove appearance.
    c._notify_callback(None, bytearray(frame("aa0504ffff")))
    before = c.capture_effect_control_state()
    assert before.video_restore_controls is None
    wb = AsyncMock(side_effect=RuntimeError("optional white balance silent"))
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.apply_white_balance", wb)

    async def refresh(**kwargs):
        for prefix in ("aa0100", "aa0464", "aa0504ffff"):
            c._notify_callback(None, bytearray(frame(prefix)))
        return True

    monkeypatch.setattr(c, "refresh_state", refresh)

    async def refresh_segments():
        for page in range(1, 5):
            c._notify_callback(None, bytearray(frame(f"aaa5{page:02x}" + "64ffffff" * 4)))
        return True

    monkeypatch.setattr(c, "async_refresh_segments", refresh_segments)

    async def transmit(_uuid, packet, **kwargs):
        if packet[0] != 0xAA and packet not in (build_power(True, c.model), build_power(False, c.model)):
            raise RuntimeError("effect write failed")

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", Mock())
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    content = (
        MusicProfile("H6199", "rhythm", 50, None, False)
        if kind == "music"
        else PaletteDiyEffect("H6199", 1, 0, 50, ((255, 0, 0),))
    )
    with pytest.raises(RuntimeError, match="effect write failed"):
        await getattr(engine, f"async_apply_{source}")(
            c, LibraryItem.new("Failure", content), config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z"
        )
    record = repository.snapshot().records[0]
    assert record.phase is DeploymentPhase.UNCERTAIN
    assert record.prior_state is not None
    assert record.prior_state == replace(
        before,
        video_restore_controls=(),
        segment_colors=((255, 255, 255),) * 15,
        segment_brightness=(100,) * 15,
    )
    assert record.prior_state.from_dict(record.prior_state.to_dict()).video_restore_controls == ()
    assert not c.is_on
    assert client.write_gatt_char.await_args_list[-1].args[1] == build_power(False, c.model)
    wb.assert_not_awaited()
    assert before.video_restore_controls is None


@pytest.mark.parametrize("model,control", [("H6199", "white_balance"), ("H6099", "black_border")])
async def test_selector_filters_saved_video_and_defaults_without_mutation(hass, coordinator, model, control):
    c = (
        coordinator
        if model == "H6199"
        else GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    )
    c.subordinate_21_version = "1.00.33"
    content = VideoProfile(
        model,
        "movie",
        True,
        50,
        None,
        None,
        17 if control == "white_balance" else None,
        None,
        None,
        black_border=True if control == "black_border" else None,
    )
    blocked = LibraryItem.new("Revision setting", content)
    omitted = LibraryItem.new("Mode only", replace(content, white_balance_position=None, black_border=None))
    backend = await EffectBackend.async_create(hass)
    default = CatalogueTemplateDefault(
        config_entry_id="entry-a",
        model=model,
        template_id="template:video:movie",
        content=content,
        updated_at="2026-09-16T00:00:00Z",
    )
    await backend.template_defaults.async_set(default)
    light = GoveeBLELight(c, config_entry_id="entry-a", effect_backend=backend)
    light._library_snapshot = LibrarySnapshot((blocked, omitted))
    original = blocked.to_dict(), default.to_dict()
    for version, supported in (("1.00.33", True), (None, False), ("1.00.01", False), ("1.00.33", True)):
        c.subordinate_21_version = version
        entries = light._selector_entries()
        assert any(entry.item == blocked for entry in entries) is supported
        assert any(entry.item == omitted for entry in entries)
        assert any(entry.source == "video" and entry.value == "movie" for entry in entries) is supported
        assert any(entry.source == "video" and entry.value == "game" for entry in entries)
        retained = backend.template_defaults.get("entry-a", default.template_id)
        assert retained is not None
        assert (blocked.to_dict(), retained.to_dict()) == original
    c.subordinate_21_version = None
    await backend.template_defaults.async_delete("entry-a", default.template_id)
    assert any(entry.source == "video" and entry.value == "movie" for entry in light._selector_entries())


async def test_pact_change_publishes_late_entities_and_effective_states(hass, coordinator):
    c = coordinator
    c._present = True
    c.pact_type = c.pact_code = None
    entry = SimpleNamespace(runtime_data=c, entry_id="entry-a", title="Test", async_on_unload=Mock())
    selects, sensors = [], []
    await select.async_setup_entry(hass, entry, selects.extend)
    await sensor.async_setup_entry(hass, entry, sensors.extend)
    backend = MagicMock()
    backend.active_workspaces.get.return_value = None
    published = []
    unsubscribe = c.async_add_listener(lambda: published.append(_device_payload(hass, backend, entry)))
    try:
        for pact, count in ((2, 1), (2, 1), (3, 2)):
            c._async_on_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, pact, 1, 0))}), None)
            assert len(published) == count
            assert len(selects) == 3 and len(sensors) == 1
            assert selects[0].available is (pact == 2)
        c.hw_version, c.fw_version = "2.01.00", "1.00.01"
        c._async_on_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00020100")}), None)
        assert published[-1]["video_control_states"]["sound_effects"] == "unsupported"
        c._async_on_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00030100")}), None)
        assert published[-1]["video_control_states"]["sound_effects"] == "supported"
        count = len(published)
        c._async_on_advertisement(SimpleNamespace(manufacturer_data={}), None)
        assert len(published) == count
        c._present = False
        c._async_on_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00020100")}), None)
        assert len(published) == count + 1
    finally:
        unsubscribe()
        for call in entry.async_on_unload.call_args_list:
            call.args[0]()
