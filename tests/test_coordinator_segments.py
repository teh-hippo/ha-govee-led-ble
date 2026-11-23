"""Coordinator segment observation, writes and confirmation tests."""

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_segments import SegmentPaintRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_compiler import compile_application, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, StaticRgbComposition
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_power,
    build_power_query,
    build_segment_query,
    parse_status,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_temp,
    build_segment_brightness,
    build_segment_brightness_packets,
    build_segment_paint,
)
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
from tests.coordinator_test_support import _CONFIGURATION_URL, _packet
from tests.test_effect_preview import _manager, _open

M = "custom_components.ha_govee_led_ble.coordinator"


@pytest.mark.parametrize("readback", ["matching", "stale", "incomplete"])
async def test_static_rgb_observation_requires_a_fresh_complete_palette(coord, segment_client, readback):
    expected = [(255, 0, 0)] * coord.profile.segment_count
    coord.segment_colors = list(expected)
    coord.segment_state_source = "observed"

    async def query(**kwargs):
        assert kwargs["query_segments"] is True
        if readback != "stale":
            coord._field_revisions["segment_colors"] = coord._field_revisions.get("segment_colors", 0) + 1
            coord._field_received_at["segment_colors"] = time.monotonic()
        if readback == "incomplete":
            coord.segment_colors.pop()
        return True

    with patch.object(coord, "_send_state_queries", side_effect=query):
        result = await coord.async_observe_effect({"segment_colors": expected}, timeout=0.1)
    assert result is (True if readback == "matching" else None if readback == "stale" else False)


async def test_partial_static_live_uses_guarded_native_writes_without_an_effect_baseline(
    hass, monkeypatch, coord, segment_client
):
    coord.profile = replace(coord.profile, read_domains=frozenset(), setup_required_read_domains=frozenset())
    coord.segment_brightness = [22] + [75] * 14
    before = list(coord.segment_colors)
    manager, _cache = await _manager(hass, monkeypatch, coord)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_preview.async_prepare_effect_control_state",
        AsyncMock(return_value=True),
    )
    events = []
    owner = object()
    session = _open(manager, owner, events)
    with (
        patch.object(
            coord, "async_refresh_segments", side_effect=AssertionError("Write-only controls do not need readback")
        ),
        patch.object(coord, "async_admit_effect_selection", side_effect=AssertionError("Static RGB is not an effect")),
    ):
        try:
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-11-19T00:00:00Z",
                item=LibraryItem.new("Partial", StaticRgbComposition((None,) * 14 + ((0, 0, 255),))),
            )
            await manager.async_wait_idle("entry-a")
            assert events[-1].phase is PreviewPhase.WRITTEN
            assert events[-1].confidence is ObservationConfidence.WRITE_COMPLETED
            assert coord.segment_colors == before[:14] + [(0, 0, 255)]
            assert coord.segment_brightness == [22] + [75] * 14
            assert [call.args[1] for call in segment_client.write_gatt_char.await_args_list] == build_segment_paint(
                [([15], (0, 0, 255))]
            )
        finally:
            await manager.async_shutdown()


@pytest.mark.parametrize("observed", [False, True])
async def test_saved_static_rgb_uses_native_paint_without_an_effect_recovery_baseline(
    hass, coord, segment_client, observed
):
    profile = replace(
        coord.profile,
        supports_custom_effects=False,
        read_domains=coord.profile.read_domains if observed else frozenset(),
        setup_required_read_domains=frozenset(),
    )
    coord.profile = profile
    coord.is_on = True
    coord.color_mode = ParsedMode.DIY
    coord.diy_code = 0x638
    colours = ((200, 10, 0),) * 5 + ((0, 200, 0),) * 5 + ((0, 0, 200),) * 5
    item = LibraryItem.new("Tricolour", StaticRgbComposition(colours, 25))
    compiled = compile_application(item, coord.model, profile=profile)
    repository = EffectDeploymentRepository(hass)
    await repository.async_load()
    cache = EffectDeviceCache(hass)
    await cache.async_load()
    engine = EffectDeploymentEngine(repository, cache)
    published = MagicMock()
    unsubscribe = coord.async_add_listener(lambda: published(cache.get("entry-a")))
    levels = list(coord.segment_brightness)

    async def refresh():
        coord.segment_state_source = "observed"
        coord._field_revisions["segment_colors"] = coord._field_revisions.get("segment_colors", 0) + 1
        return True

    try:
        with (
            patch.object(coord, "async_refresh_segments", side_effect=refresh),
            patch.object(
                coord, "async_admit_effect_selection", side_effect=AssertionError("Static RGB is not an effect")
            ),
        ):
            result = await engine.async_apply_saved(
                coord, item, config_entry_id="entry-a", updated_at="2026-11-19T00:00:00Z", compiled=compiled
            )
    finally:
        unsubscribe()
    assert result.phase is (DeploymentPhase.CONFIRMED if observed else DeploymentPhase.APPLIED)
    assert result.verification_confidence is (
        ObservationConfidence.SETTINGS_MATCH if observed else ObservationConfidence.WRITE_COMPLETED
    )
    assert coord.segment_colors == [(50, 3, 0)] * 5 + [(0, 50, 0)] * 5 + [(0, 0, 50)] * 5
    assert coord.segment_brightness == levels
    assert coord.color_mode is ParsedMode.COLOUR
    assert coord.diy_code is None
    expected = build_segment_paint(
        [(range(1, 6), (50, 3, 0)), (range(6, 11), (0, 50, 0)), (range(11, 16), (0, 0, 50))],
        profile=profile,
    )
    assert [call.args[1] for call in segment_client.write_gatt_char.await_args_list] == expected
    state = cache.get("entry-a")
    assert state is not None
    assert published.call_args.args[0] == state
    if observed:
        assert state.active_effect is not None
        assert state.active_effect.item_id == item.id
        assert state.active_effect.confidence is ObservationConfidence.SETTINGS_MATCH
        coord.segment_colors[0] = (1, 2, 3)
        changed = engine.reconcile_current(
            coord, config_entry_id="entry-a", observed_at=result.updated_at, refreshed=True
        )
        assert changed.active_effect is None
    else:
        assert state.active_effect is None
    for changed_profile in (
        replace(profile, segment_count=profile.segment_count - 1),
        replace(profile, supports_segment_writes=False),
        replace(profile, supports_rgb=False),
    ):
        with pytest.raises(ValueError, match="static RGB segment layout"):
            validate_compiled_geometry(compiled, changed_profile)


@pytest.mark.parametrize("operation", ["whole-kelvin", "rgb", "brightness"])
async def test_native_write_only_controls_do_not_require_unavailable_segment_replies(hass, operation):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=_CONFIGURATION_URL)
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c.is_on = True
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    c._ensure_connected = AsyncMock(return_value=client)
    c._refresh_h607c_advertisements = MagicMock()
    c._renew_foreground_lease = MagicMock()
    c.async_refresh_segments = AsyncMock(return_value=False)
    c.refresh_state = AsyncMock(return_value=True)
    if operation == "whole-kelvin":
        light = GoveeBLELight(c)
        light.hass = hass
        light.entity_id = "light.native_floor_lamp"
        await light.async_turn_on(color_temp_kelvin=2200)
        expected = build_color_temp(2200, "H607C", profile=c.profile)
    elif operation == "rgb":
        groups = [([13], (1, 2, 3))]
        expected = build_segment_paint(groups, "H607C", profile=c.profile)[0]
        await c.async_paint_segments(SegmentPaintRequest(groups))
    else:
        expected = build_segment_brightness([13], 31, "H607C", profile=c.profile)
        await c.async_set_segment_brightness([13], 31)
    assert client.write_gatt_char.await_args.args[1] == expected
    c.async_refresh_segments.assert_not_awaited()
    assert c.segment_state_source == "optimistic"
    assert c._field_revisions.get("segment_colors", 0) == 0
    assert c._static_rgb_known is False


def test_segment_colors_initial_state(coord, h6199):
    assert coord.segment_colors == [(255, 255, 255)] * 15
    assert h6199.segment_colors == [(255, 255, 255)] * 15
    assert coord.segment_brightness == [100] * 15
    assert h6199.segment_brightness == [100] * 15
    assert coord.segment_state_source == h6199.segment_state_source == "initial"
    assert len(coord.segment_colors) == coord.profile.segment_count


@pytest.mark.parametrize("direct_rgb", [False, True])
def test_main_rgb_projection_does_not_replace_a_mixed_observed_palette(coord, direct_rgb):
    coord.color_mode = ParsedMode.COLOUR
    coord.rgb_color = (255, 141, 11)
    coord.rgb_color_source = "observed" if direct_rgb else "segment"
    coord.segment_state_source = "observed"
    coord.segment_colors = [(0, 255, 0), *([(217, 225, 255)] * 14)]
    coord.segment_kelvin = [0, *([9000] * 14)]
    coord.segment_brightness = [100] * 14 + [20]
    light = GoveeBLELight(coord)
    before = coord.capture_effect_control_state()
    assert light.rgb_color == (coord.rgb_color if direct_rgb else None)
    assert coord.capture_effect_control_state() == before
    coord.segment_colors = [(10, 20, 30)] * 15
    coord.rgb_color = (10, 20, 30)
    assert light.rgb_color == (10, 20, 30)


def test_segment_colors_empty_for_unsupported(hass):
    flat = replace(MODEL_PROFILES["H617A"], segment_count=0, scene_identity_fields=frozenset())
    with patch(f"{M}.get_profile", return_value=flat):
        c = GoveeBLECoordinator(
            hass,
            "AA:BB:CC:DD:EE:00",
            "H617A",
            configuration_url=_CONFIGURATION_URL,
        )
    assert c.segment_colors == [] and c.profile.segment_count == 0


@pytest.mark.parametrize("buffered", [False, True])
@pytest.mark.parametrize(
    "bad",
    [
        {"num_segments": None},
        {"num_segments": "3"},
        {"num_segments": 3.0},
        {"num_segments": True},
        {"num_segments": 0},
        {"num_segments": 2},
        {"num_segments": 4},
        {"group": 0},
        {"group": 6},
        {"group": True},
        {"group": "1"},
        {"segments": []},
        {"segments": None},
        {"segments": [SimpleNamespace(), SimpleNamespace(), SimpleNamespace()]},
    ],
)
def test_segment_page_rejected_before_buffer_mutation(coord, buffered, bad):
    parsed = parse_status(bytes.fromhex("aaa50164ff880d64ff880d64ff880d0000000010"))
    assert parsed is not None
    if buffered:
        assert coord._apply_segment_group(parsed) == ()
    colours = coord._segment_query_colors
    brightness = coord._segment_query_brightness
    before_colours = list(colours) if colours is not None else None
    before_brightness = list(brightness) if brightness is not None else None
    before_groups = set(coord._segment_groups_observed)
    body = SimpleNamespace(group=1, segments=parsed.body.segments, num_segments=3)
    vars(body).update(bad)
    # None also exercises an absent generated cardinality declaration.
    if bad.get("num_segments", 3) is None:
        del body.num_segments
    with pytest.raises(ValueError):
        coord._apply_segment_group(SimpleNamespace(body=body))
    assert coord._segment_query_colors is colours
    assert coord._segment_query_brightness is brightness
    assert coord._segment_query_colors == before_colours
    assert coord._segment_query_brightness == before_brightness
    assert coord._segment_groups_observed == before_groups
    assert coord.segment_state_source == "initial"
    assert coord.segment_colors == [(255, 255, 255)] * 15


def test_duplicate_segment_pages_require_fresh_complete_coverage(coord):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    observed_at = coord.segment_state_observed_at
    revision = coord._field_revisions["segment_colors"]
    for group in (1, 1, 2, 3, 4, 4):
        coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, [group, *([50, 1, 2, 3] * 3)])))
    assert coord._field_revisions["segment_colors"] == revision
    assert coord.segment_state_observed_at == observed_at
    assert coord.segment_colors == [(10, 20, 30)] * 15
    coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, [5, *([50, 1, 2, 3] * 3)])))
    assert coord._field_revisions["segment_colors"] == revision + 1
    assert coord.segment_colors == [(1, 2, 3)] * 15


def test_h6199_static_reply_reports_mode_only(h6199):
    h6199.segment_colors = [(1, 2, 3)] * 15
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.color_mode is ParsedMode.COLOUR
    assert h6199.rgb_color == (255, 255, 255)
    assert h6199.segment_colors == [(1, 2, 3)] * 15


def _send_uniform_segment_replies(coordinator, rgb: tuple[int, int, int]) -> None:
    group_size = 4 if coordinator.model == "H6199" else 3
    group_count = 4 if coordinator.model == "H6199" else 5
    for group in range(1, group_count + 1):
        count = min(group_size, 15 - (group - 1) * group_size)
        payload = [group, *([100, *rgb] * count)]
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 0xA5, payload)))


def test_h6199_static_segment_readback_updates_uniform_rgb(h6199):
    h6199.color_mode = ParsedMode.COLOUR
    h6199.rgb_color = (1, 2, 3)
    h6199.color_temp_kelvin = 4000

    _send_uniform_segment_replies(h6199, (10, 20, 30))

    assert h6199.rgb_color == (10, 20, 30)
    assert h6199.color_temp_kelvin is None


def test_h6199_static_segment_readback_preserves_matching_kelvin_companion(h6199):
    h6199.color_mode = ParsedMode.COLOUR
    h6199.color_temp_kelvin = 2000
    companion = table_kelvin_rgb(2000)

    _send_uniform_segment_replies(h6199, companion)

    assert h6199.color_temp_kelvin == 2000
    assert h6199.segment_colors == [companion] * 15
    assert "color_temp_kelvin" not in h6199._field_revisions


def test_partial_segment_refresh_does_not_publish_mixed_snapshot(coord):
    original_colors = [(1, 2, 3)] * 15
    original_brightness = [10] * 15
    coord.segment_colors = original_colors
    coord.segment_brightness = original_brightness
    coord.segment_state_source = "observed"
    coord.segment_state_observed_at = "2026-08-17T00:00:00+00:00"

    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0xA5, [1, *([90, 9, 8, 7] * 3)])),
    )

    assert coord.segment_colors == original_colors
    assert coord.segment_brightness == original_brightness
    assert coord.segment_state_source == "observed"
    assert coord.segment_state_observed_at == "2026-08-17T00:00:00+00:00"


@pytest.mark.parametrize(("model_fixture", "group_size", "group_count"), [("coord", 3, 5), ("h6199", 4, 4)])
def test_segment_query_replies_replace_restored_state(
    request: pytest.FixtureRequest,
    model_fixture: str,
    group_size: int,
    group_count: int,
) -> None:
    coordinator = request.getfixturevalue(model_fixture)
    coordinator.segment_colors = [(1, 2, 3)] * 15
    coordinator.segment_brightness = [1] * 15

    for group in range(1, group_count + 1):
        count = min(group_size, 15 - (group - 1) * group_size)
        payload = [group]
        for index in range(count):
            value = (group - 1) * group_size + index
            payload.extend((20 + value, value, value + 1, value + 2))
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 0xA5, payload)))

    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_state_observed_at is not None
    assert coordinator.segment_brightness == list(range(20, 35))
    assert coordinator.segment_colors == [(value, value + 1, value + 2) for value in range(15)]


@pytest.fixture
def segment_client(coord):
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coord._client = client
    with (
        patch.object(coord, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coord, "_disconnect_locked", AsyncMock()),
        patch.object(coord, "_renew_foreground_lease"),
    ):
        yield client


async def test_async_paint_segments_updates_slots_and_sends(coord, segment_client):
    groups = [([1, 2, 2], (255, 0, 0)), ([2, 3], (0, 0, 255))]
    with (
        patch.object(coord, "async_refresh_segments", new_callable=AsyncMock, return_value=True) as refresh,
        patch.object(coord, "async_set_updated_data") as pushed,
    ):
        await coord.async_paint_segments(SegmentPaintRequest((iter(segments), rgb) for segments, rgb in groups))
    assert [call.args[1] for call in segment_client.write_gatt_char.await_args_list] == build_segment_paint(groups)
    assert coord.segment_colors[:4] == [(255, 0, 0), (0, 0, 255), (0, 0, 255), (255, 255, 255)]
    assert coord.segment_state_source == "optimistic"
    refresh.assert_awaited_once_with()
    pushed.assert_called_once()


@pytest.mark.parametrize(
    ("powered", "scale", "readable"),
    [(False, 0, True), (True, 0, True), (False, 1, True), (False, 0, False)],
)
async def test_paint_scale_preserves_power_intent_not_black_packet_values(
    coord, segment_client, powered, scale, readable
):
    if not readable:
        coord.profile = replace(
            coord.profile,
            read_domains=coord.profile.read_domains - {ReadDomain.POWER},
            setup_required_read_domains=coord.profile.setup_required_read_domains - {ReadDomain.POWER},
        )
    coord.is_on = powered
    physical_power = powered
    physical_palette = list(coord.segment_colors)
    before = list(physical_palette)
    colour = (0, 0, 0)
    colour_packets = build_segment_paint([([1], colour)], coord.model, profile=coord.profile)

    async def write(_uuid, packet, **_kwargs):
        nonlocal physical_power
        if packet in colour_packets:
            physical_palette[0] = colour
            physical_power = True
        elif packet == build_power(False):
            physical_power = False
        elif packet == build_power(True):
            physical_power = True

    async def refresh(_request):
        assert readable
        coord.is_on = physical_power
        coord._power_known = True
        return True

    async def segments():
        coord.segment_colors = list(physical_palette)
        coord.segment_state_source = "observed"
        if readable:
            coord.is_on = physical_power
            coord._field_revisions["is_on"] = coord._field_revisions.get("is_on", 0) + 1
        return True

    segment_client.write_gatt_char.side_effect = write
    with (
        patch.object(coord, "refresh_state", side_effect=refresh),
        patch.object(coord, "async_refresh_segments", side_effect=segments),
    ):
        light = GoveeBLELight(coord)
        if readable:
            await light.async_paint_segments([{"segments": [1], "rgb_color": [1, 0, 0]}], rgb_scale=scale)
        else:
            with pytest.raises(HomeAssistantError):
                await light.async_paint_segments([{"segments": [1], "rgb_color": [1, 0, 0]}], rgb_scale=scale)
            segment_client.write_gatt_char.assert_not_awaited()
            assert physical_palette == before
            assert physical_power is powered
            return
    assert physical_palette == [colour] + before[1:]
    assert physical_power is (powered if scale == 0 else True)
    if readable:
        assert coord.is_on is physical_power


@pytest.mark.parametrize("scale", [0, 1])
async def test_paint_accepts_native_power_change_after_confirmed_off(coord, segment_client, scale):
    physical_power = False
    colour_packets = build_segment_paint([([1], (0, 0, 0))], coord.model, profile=coord.profile)
    coord.is_on = False
    coord._arm_expected(build_power(False))
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [0])))

    async def write(_uuid, packet, **_kwargs):
        nonlocal physical_power
        if packet in colour_packets:
            physical_power = True
        elif packet == build_power(False):
            physical_power = False

    async def refresh(_request):
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [int(physical_power)])))
        return coord._power_known and coord.is_on is physical_power

    async def segments():
        await refresh(None)
        coord.segment_colors[0] = (0, 0, 0)
        coord.segment_state_source = "observed"
        return True

    segment_client.write_gatt_char.side_effect = write
    with (
        patch.object(coord, "refresh_state", side_effect=refresh),
        patch.object(coord, "async_refresh_segments", side_effect=segments),
    ):
        light = GoveeBLELight(coord)
        await light.async_paint_segments([{"segments": [1], "rgb_color": [1, 0, 0]}], rgb_scale=scale)

    assert physical_power is (scale != 0)
    assert light.is_on is physical_power


async def test_zero_scale_requires_current_power_not_cached_off(coord, segment_client):
    coord.is_on = False
    with (
        patch.object(coord, "refresh_state", AsyncMock(return_value=False)),
        pytest.raises(HomeAssistantError),
    ):
        await GoveeBLELight(coord).async_paint_segments([{"segments": [1], "rgb_color": [255, 0, 0]}], rgb_scale=0)
    segment_client.write_gatt_char.assert_not_awaited()
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize(
    ("segments_readable", "power_readback", "retired"),
    [(False, True, False), (False, False, False), (True, False, False), (False, False, True)],
)
async def test_ordinary_paint_observes_power_without_requiring_segment_readback(
    coord, segment_client, segments_readable, power_readback, retired
):
    if not segments_readable:
        coord.profile = replace(
            coord.profile,
            read_domains=coord.profile.read_domains - {ReadDomain.SEGMENTS},
            setup_required_read_domains=coord.profile.setup_required_read_domains - {ReadDomain.SEGMENTS},
        )
    coord.is_on = False

    async def refresh(_request):
        if power_readback:
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
        elif retired:
            coord._client = coord._notification_token = None
            coord._power_known = False
        return power_readback

    with (
        patch.object(coord, "refresh_state", side_effect=refresh),
        patch.object(coord, "async_refresh_segments", AsyncMock(return_value=True)) as segments,
    ):
        await GoveeBLELight(coord).async_paint_segments([{"segments": [1], "rgb_color": [20, 10, 5]}])
    segment_client.write_gatt_char.assert_awaited_once()
    assert GoveeBLELight(coord).is_on is (True if power_readback else None)
    assert coord.segment_colors[0] == (20, 10, 5)
    if not segments_readable:
        segments.assert_not_awaited()
        assert coord.segment_state_source == "optimistic"
    if retired:
        assert coord._client is None


@pytest.mark.parametrize("error", [TimeoutError("delivery failed"), asyncio.CancelledError()])
async def test_failed_zero_scale_keeps_original_error_when_power_read_fails(coord, segment_client, error):
    coord.is_on = False
    original_send = coord.send_command

    async def send(packet, **options):
        await original_send(packet, **options)
        raise error

    with (
        patch.object(coord, "refresh_state", AsyncMock(side_effect=[True, False])),
        patch.object(coord, "send_command", side_effect=send),
        pytest.raises(type(error)) as caught,
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([1], (0, 0, 0))], preserve_power=True))
    assert caught.value is error
    segment_client.write_gatt_char.assert_awaited_once()
    assert GoveeBLELight(coord).is_on is None
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("changed", ["subscription", "foreground"])
async def test_zero_scale_does_not_restore_over_newer_ownership(coord, segment_client, changed):
    coord.is_on = False
    coord._power_known = True
    replacement_token = object()

    async def write(_uuid, _wire_packet, **_options):
        if changed == "subscription":
            coord._notification_token = replacement_token
        else:
            coord._control_arbiter._foreground_generation += 1
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))

    segment_client.write_gatt_char.side_effect = write
    with (
        patch.object(coord, "refresh_state", AsyncMock(return_value=True)),
        patch.object(coord, "async_refresh_segments", AsyncMock(return_value=True)),
        pytest.raises(RuntimeError, match="ownership changed"),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([1], (0, 0, 0))], preserve_power=True))
    segment_client.write_gatt_char.assert_awaited_once()
    assert coord.is_on is True
    assert coord._power_known is True
    assert "is_on" not in coord._h607c_uncertain_state_fields
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


async def test_async_paint_segments_preserves_state_without_write_attempt(coord, segment_client):
    before = list(coord.segment_colors)
    coord._arm_expected(build_power(False))
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [0])))

    async def send(_packet, *, write_guard, on_write=None):
        write_guard()
        raise BleakError("boom")

    with (
        patch.object(coord, "send_command", side_effect=send),
        pytest.raises(BleakError),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([1, 2], (255, 0, 0))]))
    segment_client.write_gatt_char.assert_not_awaited()
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
    assert GoveeBLELight(coord).is_on is False
    assert coord.segment_colors == before
    assert coord.segment_state_source == "initial"


async def test_async_set_segment_brightness_verifies_complete_state(coord, segment_client):
    def write(_uuid, _packet, **_kwargs):
        assert coord.segment_brightness[:5] == [100, 60, 100, 60, 100]
        assert coord.segment_state_source == "optimistic"

    segment_client.write_gatt_char.side_effect = write
    with (
        patch.object(coord, "async_refresh_segments", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        await coord.async_set_segment_brightness(iter([2, 4, 4]), 60)

    segment_client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, build_segment_brightness([2, 4], 60), response=False
    )
    assert coord.segment_brightness[:5] == [100, 60, 100, 60, 100]
    assert coord.segment_state_source == "optimistic"
    refresh.assert_awaited_once_with()


async def test_async_paint_segments_rejects_unsupported(coord):
    coord.profile = replace(coord.profile, supports_segment_writes=False)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([1], (1, 2, 3))]))
    sc.assert_not_awaited()


@pytest.mark.parametrize("bad", [[0], [16], [], [1, True], [1, 1.0], [1.5]])
async def test_async_paint_segments_rejects_invalid_segments(coord, bad):
    before = list(coord.segment_colors)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([(bad, (1, 2, 3))]))
    sc.assert_not_awaited()
    assert coord.segment_colors == before


@pytest.mark.parametrize("count", [5, 14])
async def test_segment_writes_use_effective_profile(coord, segment_client, count):
    coord.profile = replace(coord.profile, segment_count=count)
    coord.segment_colors = coord.segment_colors[:count]
    coord.segment_brightness = coord.segment_brightness[:count]
    with (
        patch.object(coord, "async_refresh_segments", new_callable=AsyncMock),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([count], (1, 2, 3))]))
        await coord.async_set_segment_brightness([count], 50)
        assert segment_client.write_gatt_char.await_count == 2
        segment_client.write_gatt_char.reset_mock()
        with patch.object(coord, "mark_segment_state_optimistic") as optimistic:
            with pytest.raises(ValueError):
                await coord.async_paint_segments(SegmentPaintRequest([([1], (4, 5, 6)), ([count + 1], (1, 2, 3))]))
            with pytest.raises(ValueError):
                await coord.async_set_segment_brightness([count + 1], 50)
        optimistic.assert_not_called()
        segment_client.write_gatt_char.assert_not_awaited()
    assert coord.segment_colors == [(255, 255, 255)] * (count - 1) + [(1, 2, 3)]
    assert coord.segment_brightness == [100] * (count - 1) + [50]


async def test_paint_serialization_failure_precedes_optimistic_state(coord):
    before = list(coord.segment_colors)
    with (
        patch(
            "custom_components.ha_govee_led_ble.protocol_commands._serialize_xor",
            side_effect=[b"first packet", ValueError("serialization failed")],
        ) as serialize,
        patch.object(coord, "mark_segment_state_optimistic") as optimistic,
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        pytest.raises(ValueError, match="serialization failed"),
    ):
        await coord.async_paint_segments(SegmentPaintRequest([([1], (1, 2, 3)), ([2], (4, 5, 6))]))
    assert serialize.call_count == 2
    optimistic.assert_not_called()
    send.assert_not_awaited()
    assert coord.segment_colors == before
    assert coord.segment_state_source == "initial"


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("recovery", ["complete", "partial", "error"])
async def test_segment_write_failure_reconciles_without_masking_error(coord, segment_client, operation, recovery):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    revision = coord._field_revisions["segment_colors"]
    coord.rgb_color_source = coord.color_temp_kelvin_source = "observed"
    # A pre-write page must not complete the post-write observation.
    coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, [5, *([100, 10, 20, 30] * 3)])))
    error = BleakError("original write failure")
    segment_client.write_gatt_char.side_effect = [None, error, error, error] if operation == "paint" else error

    async def refresh():
        assert coord._control_arbiter.current_task_intent is ControlIntent.USER
        assert not coord._lock.locked()
        assert coord.segment_state_source == "optimistic"
        assert coord.segment_state_observed_at is None
        assert not coord._segment_groups_observed
        assert coord._field_revisions["segment_colors"] == revision
        if operation == "paint":
            assert coord.segment_colors[:3] == [(255, 0, 0), (0, 0, 255), (10, 20, 30)]
            assert coord.rgb_color_source == coord.color_temp_kelvin_source == "retained"
        if recovery == "error":
            raise RuntimeError("recovery failed")
        for group in range(1, 6 if recovery == "complete" else 5):
            coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, [group, *([40, 9, 8, 7] * 3)])))
        return recovery == "complete"

    with patch.object(coord, "async_refresh_segments", AsyncMock(side_effect=refresh)) as refresh_mock:
        with pytest.raises(BleakError) as raised:
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0)), ([2], (0, 0, 255))]))
            else:
                await coord.async_set_segment_brightness([1], 60)
    assert raised.value is error
    refresh_mock.assert_awaited_once_with()
    assert segment_client.write_gatt_char.await_count == (4 if operation == "paint" else 3)
    assert not coord._control_arbiter.locked()
    if recovery == "complete":
        assert coord.segment_colors == [(9, 8, 7)] * 15
        assert coord.segment_brightness == [40] * 15
        assert coord.segment_state_source == "observed"
        assert coord.segment_state_observed_at is not None
        assert coord._field_revisions["segment_colors"] == revision + 1
    else:
        assert coord.segment_state_source == "optimistic"
        assert coord.segment_state_observed_at is None
        assert coord._field_revisions["segment_colors"] == revision


@pytest.mark.parametrize("operation", ["paint", "brightness"])
async def test_segment_false_confirmation_surfaces_without_resending(coord, segment_client, operation):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    with patch.object(coord, "async_refresh_segments", AsyncMock(return_value=False)) as refresh:
        with pytest.raises(RuntimeError, match="confirm segment"):
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0))]))
            else:
                await coord.async_set_segment_brightness([1], 60)
    assert segment_client.write_gatt_char.await_count == 1
    refresh.assert_awaited_once_with()
    assert coord.segment_state_source == "optimistic"
    assert coord.segment_state_observed_at is None


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("failure", ["validation", "transform", "connection"])
async def test_segment_no_write_preserves_observation_and_buffers(coord, segment_client, operation, failure):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    coord.rgb_color_source = coord.color_temp_kelvin_source = "observed"
    coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, [1, *([40, 9, 8, 7] * 3)])))
    observed_at = coord.segment_state_observed_at
    revisions = dict(coord._field_revisions)
    colors, brightness = coord._segment_query_colors, coord._segment_query_brightness
    admission = coord.admit_preview()
    if failure == "transform":
        coord.profile = replace(coord.profile, outbound_transform=MagicMock(side_effect=ValueError("transform")))
    elif failure == "connection":
        coord._ensure_connected.side_effect = TimeoutError("connection")
    with patch.object(coord, "async_refresh_segments", AsyncMock()) as refresh:
        with pytest.raises((ValueError, TimeoutError)):
            selected = [16] if failure == "validation" else [1]
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0)), (selected, (0, 0, 255))]))
            else:
                await coord.async_set_segment_brightness(selected, 60)
    segment_client.write_gatt_char.assert_not_awaited()
    refresh.assert_not_awaited()
    assert coord.segment_colors == [(10, 20, 30)] * 15
    assert coord.segment_brightness == [100] * 15
    assert coord.segment_state_source == coord.rgb_color_source == coord.color_temp_kelvin_source == "observed"
    assert coord.segment_state_observed_at == observed_at
    assert coord._field_revisions == revisions
    assert coord._segment_groups_observed == {1}
    assert coord._segment_query_colors is colors
    assert coord._segment_query_brightness is brightness
    if failure == "validation":
        assert admission.is_current


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_segment_new_observations_survive_write_completion(coord, segment_client, operation, outcome):
    def write(_uuid, _packet, **_kwargs):
        _send_uniform_segment_replies(coord, (9, 8, 7))
        coord.rgb_color_source = coord.color_temp_kelvin_source = "observed"
        coord._mark_received(ReadDomain.COLOUR_MODE, "rgb_color", "color_temp_kelvin", "color_mode")
        coord.color_mode = ParsedMode.VIDEO
        coord.video_mode = "game"
        if outcome == "failure":
            raise TimeoutError("ambiguous write")
        if outcome == "cancelled":
            raise asyncio.CancelledError

    segment_client.write_gatt_char.side_effect = write
    with patch.object(coord, "async_refresh_segments", AsyncMock(return_value=True)) as refresh:

        async def apply():
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0))]))
            else:
                await coord.async_set_segment_brightness([1], 60)

        if outcome == "success":
            with pytest.raises(RuntimeError, match="confirm segment"):
                await apply()
        else:
            with pytest.raises(TimeoutError if outcome == "failure" else asyncio.CancelledError):
                await apply()
    assert refresh.await_count == (0 if outcome == "cancelled" else 1)
    assert coord.segment_colors == [(9, 8, 7)] * 15
    assert coord.segment_brightness == [100] * 15
    assert coord.segment_state_source == coord.rgb_color_source == coord.color_temp_kelvin_source == "observed"
    assert coord.segment_state_observed_at is not None
    assert coord.color_mode is ParsedMode.VIDEO
    assert coord.video_mode == "game"
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("operation", ["paint", "brightness"])
async def test_cancelled_segment_write_leaves_uncertainty_without_recovery_task(coord, segment_client, operation):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    segment_client.write_gatt_char.side_effect = asyncio.CancelledError
    with patch.object(coord, "async_refresh_segments", AsyncMock()) as refresh:
        with pytest.raises(asyncio.CancelledError):
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0))]))
            else:
                await coord.async_set_segment_brightness([1], 60)
    refresh.assert_not_awaited()
    assert coord.segment_state_source == "optimistic"
    assert coord.segment_state_observed_at is None
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("model_fixture", ["coord", "h6199"])
@pytest.mark.parametrize("operation", ["paint", "brightness"])
async def test_segment_failure_reconciles_real_complete_query_pages(request, model_fixture, operation):
    coord = request.getfixturevalue(model_fixture)
    _send_uniform_segment_replies(coord, (10, 20, 30))
    revision = coord._field_revisions["segment_colors"]
    group_size = coord.profile.segment_group_size
    replies = {
        build_segment_query(group, coord.model): _packet(
            0xAA, 0xA5, [group, *([40, 9, 8, 7] * min(group_size, 15 - (group - 1) * group_size))]
        )
        for group in range(1, coord._segment_group_count + 1)
    }
    packets = (
        build_segment_paint([([1], (255, 0, 0)), ([2], (0, 0, 255))], coord.model)
        if operation == "paint"
        else [build_segment_brightness([1], 60, coord.model)]
    )
    error = TimeoutError("ambiguous write")

    def write(_uuid, packet, **_kwargs):
        if packet == packets[-1]:
            raise error
        if packet in replies:
            coord._notify_callback(None, bytearray(replies[packet]))
            if packet != list(replies)[-1]:
                assert coord.segment_state_source == "optimistic"
                assert coord.segment_state_observed_at is None
                assert coord._field_revisions["segment_colors"] == revision

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coord._client = client
    with (
        patch.object(coord, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coord, "_renew_foreground_lease"),
        pytest.raises(TimeoutError) as raised,
    ):
        if operation == "paint":
            await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0)), ([2], (0, 0, 255))]))
        else:
            await coord.async_set_segment_brightness([1], 60)
    assert raised.value is error
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == packets + [build_power_query(coord.model, profile=coord.profile)] + list(replies)
    assert coord.segment_colors == [(9, 8, 7)] * 15
    assert coord.segment_brightness == [40] * 15
    assert coord.segment_state_source == "observed"
    assert coord.segment_state_observed_at is not None
    assert coord._field_revisions["segment_colors"] == revision + 1


async def test_paint_later_transform_failure_keeps_latest_observations(coord, segment_client):
    packets = build_segment_paint([([1], (255, 0, 0)), ([2], (0, 0, 255))])
    error = ValueError("second transform rejected")
    coord.profile = replace(coord.profile, outbound_transform=MagicMock(side_effect=[packets[0], error]))
    segment_client.write_gatt_char.side_effect = lambda *_args, **_kwargs: _send_uniform_segment_replies(
        coord, (9, 8, 7)
    )
    with patch.object(coord, "async_refresh_segments", AsyncMock(return_value=False)) as refresh:
        with pytest.raises(ValueError) as raised:
            await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0)), ([2], (0, 0, 255))]))
    assert raised.value is error
    assert segment_client.write_gatt_char.await_count == 1
    refresh.assert_awaited_once_with()
    assert coord.segment_colors == [(9, 8, 7)] * 15
    assert coord.segment_state_source == "observed"
    assert coord.segment_state_observed_at is not None


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("failure", ["later", "recovery", "zero", "cancelled"])
async def test_multipart_segment_recovery_tracks_physical_attempts(hass, operation, failure):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile("H60B0", 1, 2)
    coord.pact_type, coord.pact_code = 1, 2
    coord._confirmed_identity_fields.add("pact")
    coord.is_on = True
    coord._client = client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coord._ensure_connected = AsyncMock(return_value=client)
    coord._refresh_h607c_advertisements = MagicMock()
    coord._renew_foreground_lease = MagicMock()
    groups = [([1, 9], (1, 2, 3))]
    packets = (
        build_segment_paint(groups, "H60B0", profile=coord.profile)
        if operation == "paint"
        else build_segment_brightness_packets([1, 9], 40, "H60B0", profile=coord.profile)
    )
    assert len(packets) == 2
    original_send = coord.send_command
    error = asyncio.CancelledError() if failure == "cancelled" else ValueError("pre-write rejection")

    async def send(packet, *, write_guard, on_write=None):
        assert coord._control_arbiter.current_task_intent is ControlIntent.USER
        if failure == "zero":
            write_guard()
            raise error
        if packet == packets[1]:
            raise error
        await original_send(packet, write_guard=write_guard, on_write=on_write)

    refresh = AsyncMock(side_effect=RuntimeError("refresh failed")) if failure == "recovery" else AsyncMock()
    source_refresh = (
        AsyncMock(side_effect=RuntimeError("source refresh failed")) if failure == "recovery" else AsyncMock()
    )
    with (
        patch.object(coord, "send_command", side_effect=send),
        patch.object(coord, "async_refresh_segments", refresh),
        patch.object(coord, "refresh_state", source_refresh),
    ):
        with pytest.raises(type(error)) as raised:
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest(groups))
            else:
                await coord.async_set_segment_brightness([1, 9], 40)
    assert raised.value is error
    assert client.write_gatt_char.await_count == coord._static_write_attempts == (0 if failure == "zero" else 1)
    if failure in {"later", "recovery"}:
        refresh.assert_awaited_once_with()
    else:
        refresh.assert_not_awaited()
    if operation == "paint" and failure in {"later", "recovery"}:
        source_refresh.assert_awaited_once_with(RefreshRequest(refresh_all=True, query_segments=True))
    else:
        source_refresh.assert_not_awaited()
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("operation", ["paint", "brightness"])
async def test_segment_recovery_cancellation_releases_operation(coord, segment_client, operation):
    started = asyncio.Event()
    segment_client.write_gatt_char.side_effect = TimeoutError("ambiguous write")

    async def refresh():
        started.set()
        await asyncio.Event().wait()

    with patch.object(coord, "async_refresh_segments", AsyncMock(side_effect=refresh)):
        task = asyncio.create_task(
            coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0))]))
            if operation == "paint"
            else coord.async_set_segment_brightness([1], 60)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert coord.segment_state_source == "optimistic"
    assert coord.segment_state_observed_at is None
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("model_fixture", ["coord", "h6199"])
@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("source", ["observed", "initial", "restored", "optimistic"])
@pytest.mark.parametrize("result", ["unchanged", "partial", "match", "unselected", "companion"])
async def test_segment_confirmation_compares_complete_pages(request, model_fixture, operation, source, result):
    coord = request.getfixturevalue(model_fixture)
    _send_uniform_segment_replies(coord, (10, 20, 30))
    coord.segment_state_source = source
    if source != "observed":
        coord.segment_state_observed_at = None
    revision = coord._field_revisions["segment_colors"]
    colors = list(coord.segment_colors)
    brightness = list(coord.segment_brightness)
    groups = [([1, 2], (255, 0, 0)), ([2], (0, 0, 255))]
    if result != "unchanged":
        if operation == "paint":
            colors[:2] = [(255, 0, 0), (255, 0, 0) if result == "partial" else (0, 0, 255)]
        else:
            brightness[:2] = [60, 100 if result == "partial" else 60]
    if result == "unselected":
        if operation == "paint":
            colors[-1] = (9, 8, 7)
        else:
            brightness[-1] = 40
    if result == "companion":
        if operation == "paint":
            brightness[0] = 40
        else:
            colors[0] = (9, 8, 7)
    size = coord.profile.segment_group_size
    replies = {}
    for group in range(1, coord._segment_group_count + 1):
        payload = [group]
        for index in range((group - 1) * size, min(group * size, len(colors))):
            payload.extend((brightness[index], *colors[index]))
        replies[build_segment_query(group, coord.model)] = _packet(0xAA, 0xA5, payload)

    def write(_uuid, packet, **_kwargs):
        if packet in replies:
            coord._notify_callback(None, bytearray(replies[packet]))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coord._client = client
    with (
        patch.object(coord, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coord, "_renew_foreground_lease"),
    ):

        async def apply():
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest(groups))
            else:
                await coord.async_set_segment_brightness([1, 2], 60)

        if result in {"unchanged", "partial"}:
            with pytest.raises(RuntimeError, match="confirm segment"):
                await apply()
        else:
            await apply()
    assert coord.segment_colors == colors
    assert coord.segment_brightness == brightness
    assert coord.segment_state_source == "observed"
    assert coord.segment_state_observed_at is not None
    assert coord._field_revisions["segment_colors"] == revision + 1
    assert client.write_gatt_char.await_count == len(replies) + (2 if operation == "paint" else 1) + 1
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("error", [TimeoutError("verification failed"), asyncio.CancelledError()])
async def test_segment_verification_error_preserves_state(coord, segment_client, operation, observed, error):
    _send_uniform_segment_replies(coord, (10, 20, 30))
    revision = coord._field_revisions["segment_colors"]

    async def refresh():
        assert coord._control_arbiter.current_task_intent is ControlIntent.USER
        assert not coord._lock.locked()
        if observed:
            _send_uniform_segment_replies(coord, (9, 8, 7))
        raise error

    with patch.object(coord, "async_refresh_segments", AsyncMock(side_effect=refresh)) as verify:
        with pytest.raises(type(error)) as raised:
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0))]))
            else:
                await coord.async_set_segment_brightness([1], 60)
    assert raised.value is error
    verify.assert_awaited_once_with()
    assert segment_client.write_gatt_char.await_count == 1
    assert coord.segment_state_source == ("observed" if observed else "optimistic")
    assert (coord.segment_state_observed_at is not None) == observed
    assert coord._field_revisions["segment_colors"] == revision + observed
    if observed:
        assert coord.segment_colors == [(9, 8, 7)] * 15
        assert coord.segment_brightness == [100] * 15
    assert not coord._control_arbiter.locked()
    assert not coord._lock.locked()


@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize(
    ("during_write", "shape"),
    [(False, "same"), (True, "same"), (False, "short"), (False, "long")],
)
async def test_segment_preservation_baseline_is_first_write_boundary(
    coord, segment_client, operation, during_write, shape
):
    _send_uniform_segment_replies(coord, (10, 20, 30))

    async def connect():
        if not during_write:
            _send_uniform_segment_replies(coord, (9, 8, 7))
        return segment_client

    def write(*_args, **_kwargs):
        if during_write:
            _send_uniform_segment_replies(coord, (9, 8, 7))

    async def refresh():
        colors = [(9, 8, 7)] * 15
        if operation == "paint":
            colors[:2] = [(255, 0, 0), (0, 0, 255)]
        for group in range(1, 6):
            payload = [group]
            for index in range((group - 1) * 3, group * 3):
                payload.extend((60 if operation == "brightness" and index == 0 else 100, *colors[index]))
            coord._notify_callback(None, bytearray(_packet(0xAA, 0xA5, payload)))
        values = coord.segment_colors if operation == "paint" else coord.segment_brightness
        if shape == "short":
            values.pop()
        elif shape == "long":
            values.append(values[-1])
        return True

    coord._ensure_connected.side_effect = connect
    segment_client.write_gatt_char.side_effect = write
    with patch.object(coord, "async_refresh_segments", AsyncMock(side_effect=refresh)) as verify:

        async def apply():
            if operation == "paint":
                await coord.async_paint_segments(SegmentPaintRequest([([1], (255, 0, 0)), ([2], (0, 0, 255))]))
            else:
                await coord.async_set_segment_brightness([1], 60)

        # Only the connect-time observation is a pre-write baseline. The historical
        # observation and replies after the first write cannot establish one.
        if shape == "same":
            await apply()
        else:
            with pytest.raises(RuntimeError, match="confirm segment"):
                await apply()
    verify.assert_awaited_once_with()
    assert coord.segment_state_source == "observed"
    assert coord.segment_colors[-1] == (9, 8, 7)
