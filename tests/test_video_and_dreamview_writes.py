"""The `0xa9` display writers and the DreamView `0x60` writers, driven end to end.

Every 0xa9 write acknowledges with a generic `33 a9 00` that echoes neither the sub-command
nor the value, so an acknowledgement says only that the frame was accepted. Each writer
therefore follows its write with a read of the same register, and each rolls its cached value
back when the write fails -- so Home Assistant never shows a setting the device does not have.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.dreamview import DreamviewMember
from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode
from custom_components.ha_govee_led_ble.video_settings import (
    AI_FILTER_SETTING,
    BLACK_BORDER_REMOVAL_SETTING,
    BLACK_SCREEN_DETECTION_SETTING,
    HDR_EFFECT_SETTING,
)

_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"


@pytest.fixture
def coord(hass):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H66A0", configuration_url=_URL)
    c._client = MagicMock(is_connected=True)
    c._async_write_packet = AsyncMock()
    c.send_command = AsyncMock()
    c.async_set_updated_data = MagicMock()
    return c


def _writes(coord) -> list[bytes]:
    return [call.args[0] for call in coord.send_command.await_args_list]


def _queries(coord) -> list[bytes]:
    return [call.args[1] for call in coord._async_write_packet.await_args_list]


# ------------------------------------------------------------------ 0xa9 display registers


async def test_black_border_removal_writes_then_reads_the_same_register(coord):
    await coord.async_set_black_border_removal(True)

    (write,) = _writes(coord)
    (query,) = _queries(coord)
    assert (write[0], write[1], write[2]) == (0x33, 0xA9, BLACK_BORDER_REMOVAL_SETTING)
    assert (query[0], query[1], query[2]) == (0xAA, 0xA9, BLACK_BORDER_REMOVAL_SETTING)
    assert coord.black_border_removal is True


async def test_a_refused_write_rolls_the_cached_value_back(coord):
    coord.video_settings[BLACK_BORDER_REMOVAL_SETTING] = [0]
    coord.send_command = AsyncMock(side_effect=RuntimeError("refused"))

    with pytest.raises(RuntimeError):
        await coord.async_set_black_border_removal(True)

    assert coord.black_border_removal is False, "a refused write left an optimistic value behind"


async def test_a_refused_first_write_leaves_no_value_at_all(coord):
    """Distinct from the rollback above: there is nothing to roll back TO.

    Caching `False` here would be worse than caching nothing -- it reads as a device that
    answered, when the register has never been read.
    """
    coord.send_command = AsyncMock(side_effect=RuntimeError("refused"))

    with pytest.raises(RuntimeError):
        await coord.async_set_black_border_removal(True)

    assert coord.black_border_removal is None


async def test_hdr_effect_round_trips_as_enabled_and_gear(coord):
    await coord.async_set_hdr_effect(True, 3)

    (write,) = _writes(coord)
    assert write[:4] == bytes([0x33, 0xA9, HDR_EFFECT_SETTING, 2])
    assert (write[4], write[5]) == (1, 3)
    assert coord.hdr_effect == (True, 3)


@pytest.mark.parametrize("gear", [0, 5])
async def test_hdr_effect_refuses_a_gear_outside_the_pickers_four_positions(coord, gear):
    with pytest.raises(Exception):  # noqa: B017 -- the grammar's own validation error
        await coord.async_set_hdr_effect(True, gear)


async def test_the_ai_filter_refuses_to_write_a_filter_it_has_not_read(coord):
    """Bytes 1..8 are a filter definition the app builds from the CLOUD.

    They cannot be reconstructed here, so zeroing them would silently clear a selection the
    user made in the app. Refusing is the only safe answer before the register has answered.
    """
    with pytest.raises(ValueError, match="has not been read"):
        await coord.async_set_ai_filter(True)


async def test_the_ai_filter_hands_back_exactly_the_filter_it_read(coord):
    selected = [0x11, 0x22, 0x33, 0x44, 0x00, 0x32, 0x00, 0x32]
    coord.video_settings[AI_FILTER_SETTING] = [0, *selected, 0xEA, 0x07, 8, 26, 8, 33]

    await coord.async_set_ai_filter(True)

    (write,) = _writes(coord)
    assert write[4] == 1
    assert list(write[5:13]) == selected, "the selected filter was not preserved"
    assert coord.ai_filter is True


async def test_blank_screen_refuses_to_invent_the_policy_it_has_not_read(coord):
    with pytest.raises(ValueError, match="has not been read"):
        await coord.async_set_video_blank_screen(True)


async def test_blank_screen_flips_only_the_enable(coord):
    """The five bytes after it are the policy the user set in the app, read back untouched."""
    coord.video_settings[BLACK_SCREEN_DETECTION_SETTING] = [1, 0x02, 0x17, 0x00, 0x28, 0x05]

    await coord.async_set_video_blank_screen(False)

    (write,) = _writes(coord)
    assert write[:4] == bytes([0x33, 0xA9, BLACK_SCREEN_DETECTION_SETTING, 6])
    assert write[4] == 0
    assert list(write[5:10]) == [0x02, 0x17, 0x00, 0x28, 0x05]
    # 0x02 = same tone, 23 s, 0x0528 = 1320 s = the 22 minutes the owner had set.
    assert coord.video_blank_screen_config == (0x02, 23, 1320)
    assert coord.video_blank_screen is False


# ------------------------------------------------------------------------- video mode entry


async def test_entering_video_mode_writes_a_whole_body(coord):
    """The app writes every field each time rather than resuming a stored one, so this does."""
    coord.video_saturation = 62
    coord.video_sound_effects = True
    coord.video_sound_effects_softness = 100

    await coord.async_enter_video_mode(game_mode=True, picture_preset="vivid")

    (write,) = _writes(coord)
    assert write[:3] == bytes([0x33, 0x05, 0x00])
    assert list(write[3:9]) == [1, 0x08, 62, 1, coord.video_reserved, 100]
    assert coord.color_mode is ParsedMode.VIDEO
    assert coord.video_mode == "game"
    assert coord.video_picture_preset == "vivid"


async def test_shared_video_control_preserves_h66a0_only_fields(coord):
    coord.video_picture_preset = "delicate"
    coord.video_reserved = 2

    await apply_active_video_mode(
        coord,
        mode="game",
        requested_values={"saturation": 62, "sound_effects": True, "sound_effects_softness": 50},
        writer=coord.send_command,
        verify=False,
    )

    _power, video = _writes(coord)
    assert list(video[3:9]) == [1, 0x0B, 62, 1, 2, 50]
    assert coord.video_picture_preset == "delicate"
    assert coord.video_reserved == 2


async def test_a_model_without_video_mode_is_refused(hass):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H1A42", configuration_url=_URL)
    with pytest.raises(ValueError, match="does not support video mode"):
        await c.async_enter_video_mode(game_mode=True)


# -------------------------------------------------------------------------------- DreamView


async def test_dreamview_switch_and_brightness_reach_the_wire(coord):
    await coord.async_set_dreamview_switch(True)
    await coord.async_set_dreamview_same_brightness(False)
    await coord.async_set_dreamview_member_brightness(1, 83)

    switch, unite, brightness = _writes(coord)
    assert switch[:5] == bytes([0x33, 0x60, 0x01, 1, 1])
    assert unite[:4] == bytes([0x33, 0x60, 0x04, 0])
    # index first, then level -- the OPPOSITE order to `33 60 05`, two sub-commands away.
    assert brightness[:5] == bytes([0x33, 0x60, 0x03, 83, 1])


async def test_setting_a_group_uploads_it_as_one_a3_sequence(coord):
    members = [DreamviewMember("AA:BB:CC:DD:EE:01", (1, 2, None)), DreamviewMember("AA:BB:CC:DD:EE:02", (3,))]

    await coord.async_set_dreamview_group(members)

    frames = _writes(coord)
    assert all(frame[0] == 0xA3 for frame in frames), "a group upload is an 0xa3 sequence"
    assert frames[-1][1] == 0xFF, "the sequence is closed by a terminator frame"
    # The member count leads the body, and the addresses go on REVERSED.
    assert frames[0][4] == 0x50, "MultiSetSubDeviceController4MovieFeastV2.getCommandType()"
    assert frames[0][5] == len(members)
    assert bytes.fromhex("01eeddccbbaa") in frames[0]


async def test_a_model_that_is_not_a_sync_centre_is_refused(hass):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H1A42", configuration_url=_URL)
    assert not MODEL_PROFILES["H1A42"].supports_dreamview
    with pytest.raises(ValueError):
        await c.async_set_dreamview_switch(True)


async def test_releasing_ble_holds_the_radio_off_and_zero_clears_it(coord):
    coord.disconnect = AsyncMock()

    await coord.async_release_ble(600)
    assert coord._ble_hold_until is not None
    coord.disconnect.assert_awaited_once()

    await coord.async_release_ble(0)
    assert coord._ble_hold_until is None


async def test_reading_the_group_answers_two_questions_and_invents_no_third(coord):
    """The sync centre never reports its members' ADDRESSES.

    The vendor app only knows them because its cloud account does. So a group created in the
    app reads back here as a member count and its settings, with the members anonymous --
    which `identify_dreamview_members` then resolves by observation, not by guessing.
    """
    digest = bytes.fromhex("aa600c01343b010101370000000000000000009e")
    members = bytes.fromhex("aa60050202000000000000000000000000000015")
    coord.send_command = AsyncMock(side_effect=lambda _p: coord._dreamview_frames.update({0x0C: digest, 0x05: members}))

    state = await coord.async_read_dreamview_state(timeout=0.1)

    # Ten slots, each its own state -- `aa 60 05` is a per-slot table, not a member count.
    # 0 = empty, 1 = connecting, 2 = connected.
    assert state.member_states[:2] == (2, 2)
    assert set(state.member_states[2:]) == {0}
    assert state.has_group is True


async def test_an_unanswered_read_leaves_every_field_none(coord):
    """A missing reply must never be mistaken for a real value."""
    state = await coord.async_read_dreamview_state(timeout=0.05)

    assert state.member_states == ()
    assert state.is_on is None


async def test_candidates_are_the_other_govee_devices_configured_here(coord, hass):
    """The vendor app lists candidates from a cloud account; the local equivalent is this."""
    sibling = MagicMock(address="11:22:33:44:55:66", model="H1A42", segment_count=5)
    entry = MagicMock(title="Govee LED Strip Light 2 (H1A42)", runtime_data=sibling)
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    (candidate,) = coord.dreamview_candidates

    assert candidate == {
        "address": "11:22:33:44:55:66",
        "model": "H1A42",
        "name": "Govee LED Strip Light 2 (H1A42)",
        # The device's OWN reported segment count, not a guess: writing an Area Config for
        # zones that may not exist is the failure this avoids.
        "zones": 5,
    }


def test_a_sync_centre_is_not_a_candidate_for_its_own_group(coord, hass):
    entry = MagicMock(title="itself", runtime_data=coord)
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    assert coord.dreamview_candidates == []


async def test_dreamview_sound_effects_reaches_the_wire(coord):
    """`33 60 0b {on, softness}` -- the frame is pinned against a capture elsewhere; this checks
    the service path that was missing. The builder shipped with the DreamView work and had no
    caller, so the group's sound effects were readable and not writable."""
    await coord.async_set_dreamview_sound_effects(True, 79)

    (frame,) = _writes(coord)
    assert frame[:5] == bytes([0x33, 0x60, 0x0B, 1, 79])


async def test_omitting_softness_preserves_it_rather_than_sending_zero(coord, monkeypatch):
    """Both fields share one frame, so a plain on/off toggle must not reset softness.

    Without the read-back this would send `33 60 0b 01 00` and silently flatten a user's
    softness to zero the first time they toggled sound effects from a dashboard.
    """
    from custom_components.ha_govee_led_ble.dreamview import DreamviewState

    async def _state(*_args, **_kwargs):
        return DreamviewState(sound_effects=True, sound_effects_softness=42)

    monkeypatch.setattr(type(coord), "async_read_dreamview_state", _state)

    await coord.async_set_dreamview_sound_effects(False)

    (frame,) = _writes(coord)
    assert frame[:5] == bytes([0x33, 0x60, 0x0B, 0, 42]), "softness must be carried over, not zeroed"


async def test_softness_is_required_when_the_group_will_not_report_it(coord, monkeypatch):
    """A device that does not answer must produce an error, not a guessed value."""
    from custom_components.ha_govee_led_ble.dreamview import DreamviewState

    async def _state(*_args, **_kwargs):
        return DreamviewState()

    monkeypatch.setattr(type(coord), "async_read_dreamview_state", _state)

    with pytest.raises(ValueError, match="softness"):
        await coord.async_set_dreamview_sound_effects(True)

    assert not _writes(coord), "nothing should be written when the value is unknown"


async def test_a_video_write_is_refused_on_a_model_without_the_capability(hass) -> None:
    """A strip has no video registers, so the write must be refused rather than sent.

    The device would accept the frame and ignore it, which looks like the control working.
    """
    strip = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H1A42", configuration_url=_URL)
    assert not strip.profile.supports_black_border
    assert not strip.profile.supports_blank_screen
    with pytest.raises(ValueError, match="black-border removal"):
        await strip.async_set_black_border_removal(True)
    with pytest.raises(ValueError, match="blank-screen detection"):
        await strip.async_set_video_blank_screen(True)
