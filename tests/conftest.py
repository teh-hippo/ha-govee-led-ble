import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from aiotools import VirtualClock
from homeassistant.config_entries import current_entry
from homeassistant.helpers.device_registry import DeviceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MODEL_PROFILES,
    ModelProfile,
    default_effect_categories,
    default_effect_families,
    device_profile,
)
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, LatestRequests
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.h6199_calibration import WHITE_BALANCE_RESET
from custom_components.ha_govee_led_ble.reply_pacing import ReplyGate
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from tests.coordinator_test_support import _CONFIGURATION_URL


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


def _coord_defaults() -> dict[str, Any]:
    """Fresh attribute defaults for a mock H6199 coordinator; callers may mutate the result."""
    return dict(
        address="11:22:33:44:55:66",
        model="H6199",
        profile=MODEL_PROFILES["H6199"],
        is_on=True,
        effect="video: movie",
        fw_version=None,
        hw_version=None,
        fresh_services_required=False,
        fresh_service_discovery_forced=False,
        last_connected_at=None,
        last_disconnected_at=None,
        last_failure_type=None,
        available=True,
        connection_mode="release",
        _present=False,
        _state_read_available=False,
        brightness_pct=100,
        rgb_color=(255, 255, 255),
        color_temp_kelvin=None,
        rgb_color_source="initial",
        color_temp_kelvin_source="initial",
        _static_rgb_known=False,
        _pending_kelvin=None,
        _notification_token=None,
        _notify_started_monotonic=None,
        _reply_gate=ReplyGate(0),
        _a3_sequence=None,
        _field_revisions={},
        _field_received_at={},
        _domain_revisions={},
        _h607c_uncertain_state_fields=set(),
        _h607c_failed_color_write=False,
        _profile_generation=0,
        _authorization_generation=0,
        pact_type=None,
        pact_code=None,
        _confirmed_identity_fields=set(),
        _encryption=None,
        control_write_attempts=0,
        _static_write_attempts=0,
        source_static_intents={},
        _scene_code=None,
        _segment_groups_observed=set(),
        _segment_query_colors=None,
        _segment_query_brightness=None,
        _segment_query_incomplete=False,
        _bulk_query_incomplete=False,
        video_saturation=100,
        white_brightness=100,
        video_full_screen=True,
        video_sound_effects=False,
        video_sound_effects_softness=100,
        white_balance_red=None,
        white_balance_blue=None,
        white_balance_flag=None,
        white_balance_default_flag=None,
        white_balance_default_red=None,
        white_balance_default_blue=None,
        white_balance_scalar=None,
        subordinate_20_version=None,
        subordinate_21_version=None,
        wireless_firmware_version=None,
        wireless_hardware_version=None,
        white_balance=WHITE_BALANCE_RESET,
        relative_brightness=None,
        relative_brightness_left=None,
        relative_brightness_top=None,
        relative_brightness_right=None,
        relative_brightness_bottom=None,
        relative_brightness_strip_left=None,
        relative_brightness_strip_right=None,
        blank_screen=None,
        low_blue_light=None,
        black_border=None,
        installation_direction=None,
        camera_health="unknown",
        camera_status="unknown",
        _dreamview_last_write="unknown",
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
        music_sensitivity=100,
        music_calm=False,
        music_color=None,
        segment_colors=[(255, 255, 255)] * 15,
        segment_brightness=[100] * 15,
        segment_brightness_readable=False,
        segment_state_source="initial",
        segment_state_observed_at=None,
        configured_strings=None,
        _configured_strings_confirmed=False,
        diy_code=None,
        color_mode=None,
        _observed_color_mode=None,
        _mode_write_generation=0,
        _observed_mode_write_generation=-1,
        _observed_mode_profile_generation=-1,
        _power_write_generation=0,
        _observed_power_write_generation=-1,
        _observed_power_profile_generation=-1,
        _source_power_observation_generation={},
        music_mode="off",
        video_mode="off",
        data={},
    )


def _make_coord(**ov) -> MagicMock:
    d = _coord_defaults()
    d |= ov
    model = d["model"]
    assert isinstance(model, str)
    d.setdefault("effect_families", default_effect_families(model))
    d.setdefault("effect_categories", frozenset(default_effect_categories(model)))
    d.setdefault("prefix_effect_names", False)
    d.setdefault("always_include_custom_effects", False)
    d.setdefault("identity_gated_controls", False)
    effect_families = d["effect_families"]
    assert isinstance(effect_families, frozenset)
    d.setdefault(
        "scene_name_set",
        frozenset(MODEL_SCENES[model]) if "scenes" in effect_families else frozenset(),
    )
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c._expected_state = {}
    c._lock = asyncio.Lock()
    c._async_read_setting_fields = AsyncMock(return_value=False)
    c._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

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
    c.control_state_checkpoint = MagicMock(side_effect=lambda: GoveeBLECoordinator.control_state_checkpoint(c))
    c.control_write_request = MagicMock(
        side_effect=lambda **kwargs: GoveeBLECoordinator.control_write_request(c, **kwargs)
    )
    c.control_state_uncertain = MagicMock(
        side_effect=lambda *fields: GoveeBLECoordinator.control_state_uncertain(c, *fields)
    )
    c.static_color_unknown = MagicMock(side_effect=lambda: GoveeBLECoordinator.static_color_unknown(c))
    c.unconfirmed_state_fields = MagicMock(side_effect=lambda: GoveeBLECoordinator.unconfirmed_state_fields(c))
    c.source_field_fresh = MagicMock(side_effect=lambda field: GoveeBLECoordinator.source_field_fresh(c, field))
    c.source_power_state = MagicMock(side_effect=lambda key: GoveeBLECoordinator.source_power_state(c, key))

    async def turn_on_source(key, request):
        await GoveeBLECoordinator.async_turn_on_source(c, key, request)

    async def set_source_enabled(key, enabled):
        await GoveeBLECoordinator.async_set_source_enabled(c, key, enabled)

    c.async_turn_on_source = AsyncMock(side_effect=turn_on_source)
    c.async_set_source_enabled = AsyncMock(side_effect=set_source_enabled)
    c.install_static_color = MagicMock(
        side_effect=lambda **kwargs: GoveeBLECoordinator.install_static_color(c, **kwargs)
    )
    c._apply_static_write_intent = MagicMock(
        side_effect=lambda static, requested, **kwargs: GoveeBLECoordinator._apply_static_write_intent(
            c, static, requested, **kwargs
        )
    )
    c.async_paint_segments = AsyncMock()
    c.async_set_segment_brightness = AsyncMock()
    c.async_refresh_segments = AsyncMock(return_value=True)

    def mark_segment_state_optimistic(*, colours=None, brightness=None) -> None:
        if colours is not None:
            c.segment_colors = colours
        if brightness is not None:
            c.segment_brightness = brightness
        c.segment_state_source = "optimistic"
        c.segment_state_observed_at = None

    def mark_segment_state_restored(colours, brightness) -> None:
        c.segment_colors = colours
        c.segment_brightness = brightness
        c.segment_state_source = "restored"
        c.segment_state_observed_at = None

    c.mark_segment_state_optimistic = MagicMock(side_effect=mark_segment_state_optimistic)
    c.mark_segment_state_restored = MagicMock(side_effect=mark_segment_state_restored)
    c._control_arbiter = BLEControlArbiter()
    c.latest_requests = LatestRequests()
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

    async def _apply_native_scene_locked(*args, **kwargs) -> None:
        await GoveeBLECoordinator._async_apply_native_scene_locked(c, *args, **kwargs)

    c._async_apply_native_scene_locked = AsyncMock(side_effect=_apply_native_scene_locked)

    def _enter_static_mode() -> None:
        c.color_mode = ParsedMode.COLOUR
        c._scene_code = None
        c.unknown_scene_code = None
        c.effect = None
        c.diy_code = None
        c.music_mode = c.video_mode = "off"

    c._enter_static_mode = MagicMock(side_effect=_enter_static_mode)
    type(c).native_presentation_profile = PropertyMock(side_effect=lambda: c.profile)
    type(c).effect_authorization_profile = PropertyMock(side_effect=lambda: c.profile)
    type(c).device_info = PropertyMock(
        return_value=DeviceInfo(
            identifiers={(DOMAIN, d["address"])},
            name=f"Govee {d['model']}",
            manufacturer="Govee",
            model=d["model"],
            configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
        )
    )
    return c


@pytest.fixture
def mock_h6199_coordinator():
    return _make_coord()


@pytest.fixture
def mock_coordinator():
    return _make_coord(
        address="AA:BB:CC:DD:EE:FF", model="H617A", profile=MODEL_PROFILES["H617A"], is_on=False, effect=None
    )


@pytest.fixture
def mock_h6076_coordinator():
    return _make_coord(
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
