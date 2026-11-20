import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from aiotools import VirtualClock
from homeassistant.config_entries import current_entry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MODEL_PROFILES,
    ModelProfile,
    device_profile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.h6199_calibration import WHITE_BALANCE_RESET
from tests.coordinator_test_support import _CONFIGURATION_URL


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    return str(tmp_path)


@pytest.fixture
async def virtual_clock():
    """Advance asyncio timers and coordinator monotonic timestamps together.

    Never patch a monotonic clock independently of absolute asyncio deadlines; filesystem/executor-backed
    operations and real-time lifecycle tests stay outside virtual time.
    """
    clock = VirtualClock()
    # Keep existing timers and coordinator receipt timestamps in the event loop's time domain.
    clock.vtime = asyncio.get_running_loop().time()
    with (
        clock.patch_loop(),
        patch("custom_components.ha_govee_led_ble.coordinator.time", SimpleNamespace(monotonic=clock.virtual_time)),
        patch(
            "custom_components.ha_govee_led_ble.coordinator_notifications.time",
            SimpleNamespace(monotonic=clock.virtual_time),
        ),
        patch(
            "custom_components.ha_govee_led_ble.coordinator_recovery.time",
            SimpleNamespace(monotonic=clock.virtual_time),
        ),
        patch(
            "custom_components.ha_govee_led_ble.coordinator_segments.time",
            SimpleNamespace(monotonic=clock.virtual_time),
        ),
    ):
        yield clock


@pytest.fixture
def effect_catalogue_targets(monkeypatch):
    """Software-only exact models sharing a codec, not application limits."""
    from custom_components.ha_govee_led_ble import effect_contracts
    from custom_components.ha_govee_led_ble.effect_catalogue import (
        MODEL_EFFECT_CATALOGUES,
        DiyEffectFamily,
        DiyEffectVariation,
    )
    from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow

    workflows = {CapabilityWorkflow.PAINTED, CapabilityWorkflow.SINGLE, CapabilityWorkflow.MULTI}
    capabilities = tuple(
        replace(capability, model=model)
        for model in ("H9901", "H9902")
        for capability in effect_contracts.RELEASE_CAPABILITY_CONTRACT
        if capability.model == "H617A" and capability.workflow in workflows
    )
    monkeypatch.setattr(
        effect_contracts, "RELEASE_CAPABILITY_CONTRACT", (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, *capabilities)
    )
    for model, narrow in (("H9901", False), ("H9902", True)):
        monkeypatch.setitem(
            MODEL_PROFILES,
            model,
            ModelProfile(
                "Synthetic",
                command_grammar="H617A",
                effect_grammar="H617A",
                segment_count=15,
            ),
        )
        family = DiyEffectFamily(
            "fade",
            "Fade",
            0,
            (DiyEffectVariation("whole", "Whole", 0),)
            if narrow
            else (
                DiyEffectVariation("whole", "Whole", 0),
                DiyEffectVariation("sections", "Sections", 1),
            ),
            True,
            rate_min=20 if narrow else 0,
            rate_max=60 if narrow else 100,
        )
        monkeypatch.setitem(
            MODEL_EFFECT_CATALOGUES,
            model,
            replace(
                MODEL_EFFECT_CATALOGUES["H617A"],
                sku=model,
                effects=(family, replace(family, id="single-only", family=1, supports_multi=not narrow)),
                painted_effects=({"id": "clockwise", "label": "Clockwise"},),
                templates=(),
                music_modes=(),
                video_modes=(),
                workshop_templates=(),
                palette_min=2 if narrow else 1,
                palette_max=2 if narrow else 8,
                multi_max=1 if narrow else 4,
                speed_min=20 if narrow else 0,
                speed_max=60 if narrow else 100,
                brightness_min=20 if narrow else 0,
                brightness_max=60 if narrow else 100,
            ),
        )
    return "H9901", "H9902"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def disable_reply_pacing():
    """Mock clients never reply; reply pacing tests opt back in explicitly."""
    with patch("custom_components.ha_govee_led_ble.coordinator.REPLY_PACING_TIMEOUT", 0):
        yield


def _make_coord(hass, **overrides) -> MagicMock:
    """Use production initial state while retaining spies for isolated entity tests."""
    model = overrides.get("model", "H6199")
    real = GoveeBLECoordinator(
        hass,
        overrides.get("address", "11:22:33:44:55:66"),
        model,
        configuration_url=_CONFIGURATION_URL,
    )
    d = vars(real) | dict(
        is_on=True,
        effect="video: movie",
        available=True,
        _power_known=True,
        white_balance=WHITE_BALANCE_RESET,
        music_calm=real.music_calm,
        data={},
    )
    # MagicMock consumes name as its diagnostic label rather than an ordinary attribute.
    d.pop("name", None)
    d.update(overrides)
    d["identity_gated_controls"] = False
    d["scene_name_set"] = real.scene_name_set
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c._async_read_setting_fields = AsyncMock(return_value=False)
    c._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c.async_mode_transition = GoveeBLECoordinator.async_mode_transition.__get__(c)
    c._discard_static_baseline = GoveeBLECoordinator._discard_static_baseline.__get__(c)

    async def send_command(packet, *, write_guard=None, state_values=None, on_write=None) -> None:
        await GoveeBLECoordinator._async_write_packet(
            c,
            c._client,
            packet,
            arm_expected=True,
            before_write=write_guard,
            state_values=state_values,
            on_write=on_write,
        )

    c.send_command = AsyncMock(side_effect=send_command)
    for name in (
        "control_state_checkpoint",
        "control_write_request",
        "control_state_uncertain",
        "static_color_unknown",
        "unconfirmed_state_fields",
        "source_field_fresh",
        "source_power_state",
        "install_static_color",
        "_apply_static_write_intent",
        "mark_segment_state_optimistic",
        "mark_segment_state_restored",
        "_enter_static_mode",
    ):
        setattr(c, name, MagicMock(side_effect=getattr(GoveeBLECoordinator, name).__get__(c)))
    for name in ("async_turn_on_source", "async_set_source_enabled", "_async_apply_native_scene_locked"):
        setattr(c, name, AsyncMock(side_effect=getattr(GoveeBLECoordinator, name).__get__(c)))
    c.async_paint_segments = AsyncMock()
    c.async_set_segment_brightness = AsyncMock()
    c.async_refresh_segments = AsyncMock(return_value=True)

    c.refresh_state, c.async_set_updated_data = AsyncMock(return_value=True), MagicMock()
    c.unknown_scene_code = None

    async def write_effect_sequence(packets, **kwargs) -> None:
        for packet in packets:
            if (guard := kwargs.get("write_guard")) is not None:
                guard()
            for field, value in (kwargs.get("state_values") or {}).items():
                setattr(c, field, value)
            await c.send_command(packet)

    c.async_write_effect_sequence = AsyncMock(side_effect=write_effect_sequence)

    type(c).native_presentation_profile = PropertyMock(side_effect=lambda: c.profile)
    type(c).effect_authorization_profile = PropertyMock(side_effect=lambda: c.profile)
    type(c).device_info = PropertyMock(return_value=real.device_info)
    return c


@pytest.fixture
def mock_h6199_coordinator(hass):
    return _make_coord(
        hass,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
    )


@pytest.fixture
def mock_coordinator(hass):
    return _make_coord(
        hass, address="AA:BB:CC:DD:EE:FF", model="H617A", profile=MODEL_PROFILES["H617A"], is_on=False, effect=None
    )


@pytest.fixture
def mock_h6076_coordinator(hass):
    return _make_coord(
        hass,
        address="22:33:44:55:66:77",
        model="H6076",
        profile=device_profile("H6076", None, None),
        is_on=False,
        effect=None,
        segment_colors=[(255, 255, 255)] * 7,
        segment_brightness=[100] * 7,
    )


@pytest.fixture
def coord(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        return GoveeBLECoordinator(
            hass,
            "AA:BB:CC:DD:EE:FF",
            "H617A",
            configuration_url=_CONFIGURATION_URL,
        )


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url=_CONFIGURATION_URL,
    )
