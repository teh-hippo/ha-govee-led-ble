"""Protocol tests for the frames this branch reversed.

Everything here covers something added: the DreamView 0x60 family, the 0xa9 display registers,
the H66A0 video body and the widened music-id set. Frames are pinned as literals taken from a
capture or a device read-back, never rebuilt from the builder under test."""

from datetime import UTC, datetime

import pytest

from custom_components.ha_govee_led_ble import dreamview, video_settings
from custom_components.ha_govee_led_ble import generated_protocol_adapter as proto
from custom_components.ha_govee_led_ble.advertisement import parse_govee_advertisement
from custom_components.ha_govee_led_ble.const import (
    _H61F5_MUSIC_MODES,
    _H66A0_MUSIC_MODES,
    MODEL_PROFILES,
    MUSIC_MODE_IDS_ACCEPTED_BY_H61F5,
    MUSIC_MODE_IDS_REFUSED_BY_H61F5,
    MUSIC_MODE_IDS_REJECTED_BY_H66A0,
    MUSIC_MODE_SLUGS,
)
from custom_components.ha_govee_led_ble.coordinator_status import (
    ParsedMode,
    decode_status_frame,
    parse_color_mode,
)
from custom_components.ha_govee_led_ble.light_commands import build_segment_brightness, segments_to_mask

_CAPTURED_VIDEO_FRAMES = [
    # Captured from the vendor app on 2026-08-26, plus labelled read-backs on 2026-08-27.
    #
    # The last two bytes are a byte this pact never writes (reads 0x02 here) and then the
    # sound-effect softness. An earlier interpretation had them the other way round; changing softness in the
    # app left the 0x02 alone and that a control built on the last byte did nothing. See
    # command_write.ksy::video_body_h66a0 for the full account.
    #
    # Presets are given by NAME, so these frames also pin the wire order: Vivid is 0x0a and
    # Smooth 0x09, which is NOT the order the app lists them in.
    (
        dict(
            game_mode=False, picture_preset="vivid", saturation=0x19, sound_effects=False, sound_effects_softness=0x1D
        ),
        "33050000081900021d0000000000000000000038",
    ),
    (
        dict(
            game_mode=False,
            picture_preset="delicate",
            saturation=0x19,
            sound_effects=False,
            sound_effects_softness=0x1D,
        ),
        "330500000b1900021d000000000000000000003b",
    ),
    (
        dict(
            game_mode=True, picture_preset="delicate", saturation=0x19, sound_effects=False, sound_effects_softness=0x1D
        ),
        "330500010b1900021d000000000000000000003a",
    ),
    (
        dict(
            game_mode=True, picture_preset="delicate", saturation=0x33, sound_effects=True, sound_effects_softness=0x64
        ),
        "330500010b330102640000000000000000000068",
    ),
    # Labelled: Game, preset Vivid (0x08), saturation 62%, sound effects on with softness ~1%.
    # The owner reported "the initial mode is Vivid" for this exact read-back, which is one of
    # the two independent confirmations that 0x08 is Vivid and not Solid.
    (
        dict(game_mode=True, picture_preset="vivid", saturation=62, sound_effects=True, sound_effects_softness=1),
        "33050001083e0102010000000000000000000003",
    ),
    (
        dict(game_mode=True, picture_preset="delicate", saturation=62, sound_effects=True, sound_effects_softness=100),
        "330500010b3e0102640000000000000000000065",
    ),
]

_CAPTURED_DREAMVIEW = [
    ("switch on", proto.build_dreamview_switch(True), "3360010101000000000000000000000000000052"),
    ("switch off", proto.build_dreamview_switch(False), "3360010001000000000000000000000000000053"),
    ("saturation 37", proto.build_dreamview_saturation(0x25), "336009250000000000000000000000000000007f"),
    (
        "sound on, softness 79",
        proto.build_dreamview_sound_effects(True, 0x4F),
        "33600b014f000000000000000000000000000016",
    ),
    (
        "brightness 83 on member 1",
        proto.build_dreamview_device_brightness(0x53, 1),
        "3360035301000000000000000000000000000002",
    ),
    ("same-brightness off", proto.build_dreamview_brightness_unite(False), "3360040000000000000000000000000000000057"),
    # The per-member Disconnect button. All four forms the app sent, in capture order.
    (
        "disconnect member 1",
        proto.build_dreamview_sub_device_connect(1, False),
        "3360050100000000000000000000000000000057",
    ),
    (
        "disconnect member 0",
        proto.build_dreamview_sub_device_connect(0, False),
        "3360050000000000000000000000000000000056",
    ),
    ("connect member 1", proto.build_dreamview_sub_device_connect(1, True), "3360050101000000000000000000000000000056"),
    ("connect member 0", proto.build_dreamview_sub_device_connect(0, True), "3360050001000000000000000000000000000057"),
]

_A = "AA:BB:CC:DD:EE:FF"

_B = "11:22:33:44:55:66"


def test_aa40_query_and_black_border_write_are_well_formed():
    """The two new frames, checked against their documented forms.

    `aa 40` is the IC/segment-count read. `33 a9 0b 01 <0|1>` is the one 0xa9 write this
    integration builds -- sub-command, value count, value -- and it is the form COMMANDS.md
    records for the whole 0xa9 write surface.
    """
    query = proto.build_ic_segment_count_query()

    assert query[:2] == b"\xaa\x40"
    assert query[2:19] == bytes(17)
    assert query[19] == proto.xor_checksum(query[:19])

    on = proto.build_black_border_removal(True)
    off = proto.build_black_border_removal(False)

    assert on[:5] == b"\x33\xa9\x0b\x01\x01"
    assert off[:5] == b"\x33\xa9\x0b\x01\x00"
    for frame in (on, off):
        assert len(frame) == 20
        assert frame[19] == proto.xor_checksum(frame[:19])
    # The two differ at the value byte and at the checksum, and nowhere else.
    assert [i for i in range(20) if on[i] != off[i]] == [4, 19]


def test_segments_to_mask_bounds_on_the_device_not_the_wire_field():
    """Segment 15 is a valid mask bit and an invalid segment on a 14-segment device.

    Those are different questions and used to have one answer. The mask field is 15 bits wide
    on every model; how many of them address anything is a property of the device.
    """
    assert segments_to_mask([1, 2, 3]) == 0b111
    assert segments_to_mask([15]) == 1 << 14
    profile = MODEL_PROFILES["H66A0"]
    assert segments_to_mask([14], profile) == 1 << 13

    with pytest.raises(ValueError, match="out of range 1..14"):
        segments_to_mask([15], profile)
    with pytest.raises(ValueError, match="out of range 1..14"):
        build_segment_brightness([15], 50, "H66A0", profile=profile)


def test_govee_advertisement_carries_pact_keys():
    """The real H66A0 advertisement, parsed. Company id is little-endian, pactType is not.

    Observed 2026-08-23: company id 0x8843, payload `ec 00 02 01 01`, which puts Govee's
    literal `88 ec` magic across the company id's high byte and the payload's first byte.
    """
    parsed = parse_govee_advertisement({0x8843: b"\xec\x00\x02\x01\x01"})

    assert parsed is not None
    assert (parsed.pact_type, parsed.pact_code) == (2, 1)
    assert parsed.broadcast_version == 3
    assert parsed.supports_encryption is True
    # Anything that is not a Govee element is not guessed at.
    assert parse_govee_advertisement({0x004C: b"\x02\x15\x00"}) is None
    assert parse_govee_advertisement({}) is None
    # A flags byte without bit 6 reports no encryption, and the keys still parse.
    plain = parse_govee_advertisement({0x8803: b"\xec\x00\x02\x01\x01"})
    assert plain is not None and plain.supports_encryption is False


def test_hdr_effect_layout_matches_the_devices_own_reply():
    """The 0x11 decode, checked against the frame an H66A0 actually sent.

    Captured writes and replies use `{17, 2, enabled, level}`, establishing both fields.
    """
    frame = bytes.fromhex("aaa9110201020000000000000000000000000013")
    decoded = decode_status_frame(frame, "H66A0")

    assert decoded is not None
    body = decoded.generated.body
    assert int(body.setting.value) == video_settings.HDR_EFFECT_SETTING
    assert int(body.len) == 2

    values = list(decoded.payload[2 : 2 + int(body.len)])
    assert values == [1, 2]
    assert video_settings.parse_hdr_effect(values) == video_settings.HdrEffect(enabled=True, level=2)
    # The app's own default for an unset bean, which is the only hint at the level's range.
    # Gears, not percent. Pinned as a pair so the old 0-100 reading cannot come back quietly:
    # the vendor's control has four positions and writes the index directly.
    assert (video_settings.HDR_EFFECT_GEAR_MIN, video_settings.HDR_EFFECT_GEAR_MAX) == (1, 4)
    assert (
        video_settings.HDR_EFFECT_GEAR_MIN
        <= video_settings.HDR_EFFECT_GEAR_DEFAULT
        <= video_settings.HDR_EFFECT_GEAR_MAX
    )


@pytest.mark.parametrize(
    ("slug", "sensitivity", "colour", "captured"),
    [
        ("energetic", 0x63, (255, 0, 0), "33051305630001ff0000000000000000000000bd"),
        ("rhythm", 0x63, None, "3305130363000000000000000000000000000045"),
        ("piano_keys", 0x63, (255, 0, 0), "33051334630001ff00000000000000000000008c"),
        # Same mode, a second sensitivity: 59 as well as 99, so the field is pinned by two.
        ("piano_keys", 0x3B, (255, 0, 0), "330513343b0001ff0000000000000000000000d4"),
    ],
)
def test_h66a0_music_frames_match_the_app(slug, sensitivity, colour, captured):
    frame = proto.build_music_mode(MUSIC_MODE_SLUGS[slug], sensitivity, colour, False, model="H66A0")
    assert frame.hex() == captured


def test_h66a0_claims_every_music_mode_it_was_proven_to_accept():
    """Seventeen, each written to the device and confirmed by read-back on 2026-08-27.

    The set was found by sweeping the known identifier range rather than reasoning about which
    block they live in -- an earlier pass assumed 0x30-0x3b was the whole space, and Splash and
    Spring turned out to be 0x84 and 0x85.
    """
    # Listed, not derived from MUSIC_MODE_SLUGS. That derivation was a latent bug: the table is
    # shared across models, so adding the H1A42's 0x92/0xa3 widened this model to claim two ids
    # its OWN sweep refused. A per-model claim must never be read out of a registry.
    assert MODEL_PROFILES["H66A0"].music_modes == _H66A0_MUSIC_MODES
    assert sorted(MUSIC_MODE_SLUGS[slug] for slug in _H66A0_MUSIC_MODES) == [
        0x03, 0x04, 0x05, 0x06,
        0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37,
        0x53, 0x55, 0x65, 0x78, 0x84, 0x85,
    ]  # fmt: skip
    assert len(MODEL_PROFILES["H66A0"].music_modes) == 17
    assert "rolling" in MODEL_PROFILES["H66A0"].music_modes
    assert MODEL_PROFILES["H66A0"].supports_music_mode is True


def test_h66a0_claims_relative_brightness_after_the_round_trip():
    # `33 ae 01 04 3c 3c 3c 3c` read back as 60 and `… 32 32 32 32` restored the 50 it
    # started at, on hardware, 2026-08-24. The query needs its 0x01 selector: the bare form
    # answers `00 00`, which is where the old "zero zones" reading came from.
    assert MODEL_PROFILES["H66A0"].supports_relative_brightness is True
    assert proto.build_relative_brightness_query("H66A0").hex().startswith("aaae01")


def test_hdr_effect_builder_matches_the_frames_the_device_accepted():
    # gear 1 -> read back `02 01 01`; gear 3 -> `02 01 03`; gear 2 -> `02 01 02` (restored).
    assert proto.build_hdr_effect(True, 1) == bytes.fromhex("33a9110201010000000000000000000000000089")
    assert proto.build_hdr_effect(True, 3) == bytes.fromhex("33a911020103000000000000000000000000008b")
    assert proto.build_hdr_effect(True, 2) == bytes.fromhex("33a911020102000000000000000000000000008a")


def test_hdr_effect_shares_the_black_border_envelope():
    """Same 0xa9 setting/len/values shape, differing only in the value count."""
    hdr = proto.build_hdr_effect(True, 2)
    border = proto.build_black_border_removal(True)
    assert hdr[:2] == border[:2] == bytes.fromhex("33a9")
    assert border[2:4] == bytes([0x0B, 1])  # one value
    assert hdr[2:4] == bytes([0x11, 2])  # two values
    assert len(hdr) == len(border) == 20


def test_hdr_effect_disabled_keeps_the_gear():
    """Enable and gear are one register and one write, so disabling must still carry a gear."""
    disabled = proto.build_hdr_effect(False, 2)
    assert disabled[2:6] == bytes([0x11, 2, 0, 2])
    assert len(disabled) == 20


@pytest.mark.parametrize("gear", [-1, 0, 5, 50, 255])
def test_hdr_effect_refuses_a_gear_outside_the_pickers_four_positions(gear):
    """Gears are 1..4, numbered as the app numbers them -- 0 is not one of them.

    This pinned 0..3 until 2026-08-27, inferred from the widget's `spiltPoint_nums="4"`. A
    device whose app read "4 of 4" then answered `02 01 04`, so the builder would have refused
    a setting the vendor uses. Hardware over widget-reading.
    """
    with pytest.raises(ValueError):
        proto.build_hdr_effect(True, gear)


def test_hdr_gear_four_is_the_value_a_labelled_device_reported():
    """`aa a9 11` answered `02 01 04` with the app showing 4 of 4."""
    assert proto.build_hdr_effect(True, 4) == bytes.fromhex("33a911020104000000000000000000000000008c")
    assert video_settings.parse_hdr_effect([1, 4]).level == 4


def test_hdr_effect_parses_what_the_device_answered():
    """`aa a9 11` answered `02 01 02` on hardware: two values, enabled, gear 2."""
    decoded = video_settings.parse_hdr_effect([1, 2])
    assert decoded is not None
    assert decoded.enabled is True
    assert decoded.level == 2


@pytest.mark.parametrize("kwargs,expected", _CAPTURED_VIDEO_FRAMES)
def test_video_mode_builder_reproduces_every_captured_frame(kwargs, expected):
    assert proto.build_video_mode_h66a0(**kwargs) == bytes.fromhex(expected)


def test_video_picture_preset_map_is_the_measured_one():
    """Solid and Vivid are transposed against the app's list; the other two are not.

    Measured on 2026-08-27 by setting each preset IN THE APP and reading the device back, so this
    is wire value -> app label with no inference in between:

        Vivid -> 0x08   Solid -> 0x09   Smooth -> 0x0a   Delicate -> 0x0b

    Two earlier fixes assumed the swapped pair was Vivid/SMOOTH and both failed. Pinned as a whole
    map rather than a claim about which pair moved, so a future edit has to disagree with data.
    """
    assert proto.PICTURE_PRESETS == ("vivid", "solid", "smooth", "delicate")
    assert proto.PICTURE_PRESET_DISPLAY_ORDER == ("solid", "vivid", "smooth", "delicate")
    assert sorted(proto.PICTURE_PRESETS) == sorted(proto.PICTURE_PRESET_DISPLAY_ORDER)
    encoded = {n: proto.build_video_mode_h66a0(picture_preset=n)[4] for n in proto.PICTURE_PRESETS}
    assert encoded == {"vivid": 0x08, "solid": 0x09, "smooth": 0x0A, "delicate": 0x0B}


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(saturation=101),
        dict(saturation=-1),
        dict(sound_effects_softness=101),
        dict(picture_preset="lurid"),
    ],
)
def test_video_mode_refuses_values_the_app_cannot_produce(kwargs):
    with pytest.raises(ValueError):
        proto.build_video_mode_h66a0(**kwargs)


def test_video_state_is_read_back_from_aa_05():
    """`aa 05` carries the same six fields while the device is in video mode.

    That read is what makes entering video mode possible without inventing settings, so the
    round trip is pinned: the body a live H66A0 reported on 2026-08-25 must parse, and must
    rebuild into the frame that would restore it.
    """
    reply = bytes.fromhex("aa050000083200026400000000000000000000f3")
    decoded = decode_status_frame(reply, "H66A0")
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H66A0")
    assert parsed.mode is ParsedMode.VIDEO
    assert parsed.video_mode == "movie"
    assert parsed.video_picture_preset == "vivid"  # preset byte 0x08
    assert parsed.video_saturation == 50
    assert parsed.video_sound_effects is False
    # 02 then 64: the untouched reserved byte, then softness.
    assert parsed.video_reserved == 2
    assert parsed.video_sound_effects_softness == 100


def test_blank_screen_builder_reproduces_the_captured_pair():
    """The vendor app's own off/on pair, with the other five bytes untouched.

    Those five hold a configuration the user set in the app and none is identified, so the
    builder takes them rather than inventing them.
    """
    opaque = [0x01, 0x14, 0x00, 0x38, 0x04]
    assert proto.build_black_screen_detection(False, opaque) == bytes.fromhex(
        "33a90a06000114003804000000000000000000bf"
    )
    assert proto.build_black_screen_detection(True, opaque) == bytes.fromhex("33a90a06010114003804000000000000000000be")


@pytest.mark.parametrize("opaque", [[], [1, 2, 3], [0] * 6])
def test_blank_screen_refuses_a_wrong_length_configuration(opaque):
    with pytest.raises(ValueError):
        proto.build_black_screen_detection(True, opaque)


@pytest.mark.parametrize("label,frame,expected", _CAPTURED_DREAMVIEW)
def test_dreamview_builders_reproduce_captured_frames(label, frame, expected):
    assert frame == bytes.fromhex(expected), label


def test_dreamview_query_matches_the_apps_own_reads():
    """`aa 60 <sub>` -- the app read subs 03, 04, 05 and 0c during setup."""
    assert proto.build_dreamview_query(0x03) == bytes.fromhex("aa600300000000000000000000000000000000c9")
    assert proto.build_dreamview_query(0x0C) == bytes.fromhex("aa600c00000000000000000000000000000000c6")


@pytest.mark.parametrize(
    "call",
    [
        lambda: proto.build_dreamview_saturation(101),
        lambda: proto.build_dreamview_sound_effects(True, 101),
        lambda: proto.build_dreamview_device_brightness(101, 0),
        lambda: proto.build_dreamview_device_brightness(50, 9),
    ],
)
def test_dreamview_refuses_out_of_range(call):
    with pytest.raises(ValueError):
        call()


def test_dreamview_delete_exists_but_reset_and_clear_do_not():
    """Delete is deliberately present; the other two destructive sub-commands are not.

    Creating a group is not read-backable -- nothing the device reports says who is in it -- so
    without a delete the integration could reach a state it cannot leave except through the
    vendor app. That makes delete a safety requirement rather than a convenience, which is why
    this reverses an earlier decision to exclude all three.

    Reset (0x06) and clear-sub-devices (0x07) stay out: neither undoes anything this integration
    can do, and both discard state we cannot reconstruct.
    """
    assert proto.build_dreamview_delete() == bytes.fromhex("33600d000000000000000000000000000000005e")
    for name in dir(proto):
        lowered = name.lower()
        if "dreamview" in lowered:
            assert "reset" not in lowered and "clear" not in lowered, name


def test_group_entry_puts_the_address_on_the_wire_reversed():
    """Captured group traffic writes the display-order address last byte first.

    Proven on real data: a captured entry reversed matches an address recovered independently
    from another capture's handshake, while the unreversed form matches nothing.
    """
    entry = dreamview.DreamviewMember(address=_A, zones=(0,)).to_bytes()
    assert entry[3:9] == bytes.fromhex("FFEEDDCCBBAA")


def test_group_entry_layout_is_the_apps_own():
    """isRgbic, marker, cmdVer, address, zone count, then one byte per zone."""
    entry = dreamview.DreamviewMember(address=_A, zones=(1, 2, 3)).to_bytes()
    assert entry[0] == 1, "isRgbic"
    assert entry[1] == 0, "marker: 0 when a BLE address is present"
    assert entry[2] == dreamview.DREAMVIEW_DEFAULT_CMD_VER
    assert entry[9] == 3, "zone count"
    assert entry[10:] == bytes([1, 2, 3])
    assert len(entry) == 13


def test_a_disabled_zone_is_written_as_ff_not_omitted():
    """The zone count and entry length must not change when a zone is switched off."""
    on = dreamview.DreamviewMember(address=_A, zones=(1, 2, 3)).to_bytes()
    off = dreamview.DreamviewMember(address=_A, zones=(1, None, 3)).to_bytes()
    assert len(off) == len(on)
    assert off[9] == 3, "zone count still counts the disabled zone"
    assert off[10:] == bytes([1, 0xFF, 3])


def test_group_upload_is_one_a3_sequence_with_the_member_count_first():
    frames = dreamview.build_dreamview_group(
        [
            dreamview.DreamviewMember(address=_A, zones=(1, 1, 2, 3, 4, 4)),
            dreamview.DreamviewMember(address=_B, zones=(9, 9, 8, 7, 6, 6)),
        ]
    )
    assert all(frame[0] == 0xA3 and len(frame) == 20 for frame in frames)
    assert [frame[1] for frame in frames] == [0x00, 0x01, 0xFF]
    # version, packet count, type, then makeSubDeviceBytes' leading member count.
    assert frames[0][2:6] == bytes([0x01, 0x03, dreamview.DREAMVIEW_GROUP_TYPE, 0x02])


def test_group_rejects_what_the_app_would_never_send():
    with pytest.raises(ValueError):
        dreamview.build_dreamview_group([])
    with pytest.raises(ValueError, match="twice"):
        dreamview.build_dreamview_group(
            [
                dreamview.DreamviewMember(address=_A, zones=(0,)),
                dreamview.DreamviewMember(address=_A.lower(), zones=(0,)),
            ]
        )
    with pytest.raises(ValueError, match="at most 10"):
        dreamview.build_dreamview_group(
            [dreamview.DreamviewMember(address=f"AA:BB:CC:DD:EE:{n:02X}", zones=(0,)) for n in range(11)]
        )


@pytest.mark.parametrize("bad", ["not-a-mac", "AA:BB:CC:DD:EE", "AABBCCDDEEFF", ""])
def test_group_member_rejects_a_malformed_address(bad):
    with pytest.raises(ValueError, match="address"):
        dreamview.DreamviewMember(address=bad, zones=(0,))


def test_group_member_rejects_a_region_the_app_would_never_write():
    """The wire only ever carries 0..10.

    The app's Area Config page offers twenty cells, but getIndex4Portocol folds 1..10 and 11..20
    onto the same ten regions before the byte is sent, so a raw 11 or 0xFE is not a value the
    vendor app can produce. 0 is a real value meaning "assigned to no region".
    """
    for bad in (11, 20, 0xFE):
        with pytest.raises(ValueError, match="zone region"):
            dreamview.DreamviewMember(address=_A, zones=(bad,))
    for good in (0, 1, 10):
        assert dreamview.DreamviewMember(address=_A, zones=(good,)).to_bytes()[-1] == good
    with pytest.raises(ValueError, match="zones"):
        dreamview.DreamviewMember(address=_A, zones=())


def test_dreamview_digest_matches_the_captured_pair():
    """Both digests from the 2026-08-26 capture, and what the owner was doing between them."""
    before = dreamview.parse_dreamview_digest(bytes.fromhex("aa600c01643200000135000000000000000000a5"))
    after = dreamview.parse_dreamview_digest(bytes.fromhex("aa600c01343b01010137000000000000000000fe"))
    assert (before.brightness, after.brightness) == (100, 52)
    assert (before.saturation, after.saturation) == (50, 59)
    assert (before.sound_effects, after.sound_effects) == (False, True)
    assert (before.colour_mode, after.colour_mode) == (0, 1)
    # 0x37 is exactly the last softness written before the second digest.
    assert (before.sound_effects_softness, after.sound_effects_softness) == (53, 0x37)


def test_dreamview_member_states_are_per_slot_not_a_count():
    """The app assigns bytes[i] to sub-device i, so position matters."""
    states = dreamview.parse_dreamview_members(bytes.fromhex("aa600501020000000000000000000000000000cc"))
    assert states == (1, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    assert dreamview.DreamviewState(member_states=states).member_count == 2
    assert dreamview.DreamviewState(member_states=states).has_group is True
    assert dreamview.DreamviewState().has_group is False


def test_sub_device_connect_puts_the_index_first_and_the_flag_second():
    """Index first. The two bytes are both small ints, so a swap would look plausible forever.

    `SubDeviceConnectController.q()` emits `{g, f}` and the call site builds it as
    `(z ? 1 : 0, i)`, making `f` the flag and `g` the index -- so the wire is {index, flag}. The
    capture agrees independently: writing {slot, 0} drove that slot's `aa 60 05` byte to 0, and
    {slot, 1} drove it 1 then 2. Two sources, because a transposition here disconnects the
    wrong device.
    """
    assert proto.build_dreamview_sub_device_connect(1, False)[3:5] == bytes([1, 0])
    assert proto.build_dreamview_sub_device_connect(0, True)[3:5] == bytes([0, 1])
    with pytest.raises(ValueError, match="member index"):
        proto.build_dreamview_sub_device_connect(6, True)


def test_disconnecting_a_member_does_not_mean_the_group_is_gone():
    """`has_group` reads connection state, and a disconnected member still belongs.

    Pinned because `33 60 05` makes this reachable on purpose rather than by accident: taking a
    sub-device back for direct BLE control leaves the group intact, and a caller that treated
    all-zero as "no group" could delete or recreate one that is still configured.
    """
    all_disconnected = dreamview.parse_dreamview_members(bytes.fromhex("aa600500000000000000000000000000000000cf"))
    assert all_disconnected == (0,) * 10
    assert dreamview.DreamviewState(member_states=all_disconnected).has_group is False
    assert "not whether a group exists" in (dreamview.DreamviewState.has_group.__doc__ or "").lower()


def test_a_dreamview_reply_is_not_read_as_the_wrong_sub_command():
    """Every DreamView reply shares `aa 60`, so the sub byte has to be checked."""
    members = bytes.fromhex("aa600501020000000000000000000000000000cc")
    with pytest.raises(ValueError, match="sub 0x0c"):
        dreamview.parse_dreamview_digest(members)
    with pytest.raises(ValueError, match="not a DreamView reply"):
        dreamview.parse_dreamview_digest(bytes.fromhex("aa050000083200026400000000000000000000f3"))


def test_ai_filter_reproduces_the_captured_pair():
    """The vendor app's own on/off writes, which differ only in the enable byte.

    The tail is a wall-clock stamp -- 2026-08-26 08:33, when the capture was taken -- so the
    builder takes a time rather than replaying a constant.
    """
    stamp = datetime(2026, 8, 26, 8, 33)
    assert proto.build_ai_filter(True, now=stamp) == bytes.fromhex("33a9100f010000000000000000ea07081a082152")
    assert proto.build_ai_filter(False, now=stamp) == bytes.fromhex("33a9100f000000000000000000ea07081a082153")


def test_ai_filter_sends_the_current_time_not_the_captured_one():
    """A replayed timestamp would tell the device it is permanently 2026-08-26."""
    frame = proto.build_ai_filter(True)
    now = datetime.now()
    assert int.from_bytes(frame[13:15], "little") == now.year
    assert frame[15] == now.month


def test_ai_filter_preserves_the_selected_filter():
    """The eight bytes between the enable and the timestamp are the chosen filter.

    Their meanings are unavailable from the device. Zeroing them would clear a selection we
    cannot reconstruct, so a writer must hand back what it read.
    """
    params = bytes([50, 50, 50, 50, 0, 10, 0, 20])
    frame = proto.build_ai_filter(True, params, now=datetime(2026, 8, 26, 8, 33, tzinfo=UTC))
    assert frame[5:13] == params
    assert frame[4] == 1

    with pytest.raises(ValueError, match="8 bytes"):
        proto.build_ai_filter(True, bytes(4))


def test_shipped_music_ids_are_the_ones_the_device_ran():
    """The set found by SWEEPING the device, not by reasoning about which block ids live in.

    An earlier pass assumed 0x30-0x3b was the whole space; the registry actually runs 0x16-0xab,
    and Splash and Spring turned out to be 0x84 and 0x85. Every id here was written with
    `33 05 13 <id>` and read back as itself on 2026-08-27.
    """
    shipped = {MUSIC_MODE_SLUGS[slug] for slug in MODEL_PROFILES["H66A0"].music_modes}
    withheld = set(MUSIC_MODE_IDS_REJECTED_BY_H66A0.values())
    assert shipped.isdisjoint(withheld), "nothing is both shipped and withheld"
    # This model's shipped ids, not the table's: MUSIC_MODE_SLUGS also carries ids swept onto
    # OTHER hardware, and reading them as this device's was the bug the H1A42 work exposed.
    assert sorted(shipped) == [
        0x03,
        0x04,
        0x05,
        0x06,
        0x30,
        0x31,
        0x32,
        0x33,
        0x34,
        0x35,
        0x37,
        0x53,
        0x55,
        0x65,
        0x78,
        0x84,
        0x85,
    ]
    # Accepted and reported back with the LEDs dark, so acceptance alone never qualified an id.
    assert 0x54 in withheld and 0x54 not in shipped


def test_h61f5_music_modes_are_the_fifteen_the_strip_accepted():
    """The H61F5's music list is a sweep result, not the classic set minus a few.

    Every id in MUSIC_MODE_SLUGS was written as `33 05 13 <id> 3c` over encryption v1 on
    2026-09-02 and `aa 05` was read back after each. Fifteen echoed themselves; four acked and
    held the previous mode, and each of those four was re-probed behind a DIFFERENT anchor id so
    a single sticky failure could not masquerade as four. The owner watched the strip during the
    run and reported the modes playing, which is what separates accepted from accepted-and-inert.
    """
    profile = MODEL_PROFILES["H61F5"]
    # Listed, not derived. It coincides with _CLASSIC_MUSIC_MODES + the H1A42's four extras, and
    # deriving it that way would let a future id added for another model widen this claim.
    assert profile.music_modes == _H61F5_MUSIC_MODES
    assert profile.supports_music_mode is True
    assert len(profile.music_modes) == 15
    assert sorted(MUSIC_MODE_SLUGS[slug] for slug in _H61F5_MUSIC_MODES) == sorted(MUSIC_MODE_IDS_ACCEPTED_BY_H61F5)


def test_h61f5_does_not_claim_the_ids_its_own_sweep_refused():
    """0x53/0x55/0x65/0x78 are refusals measured on this strip, not gaps in the sweep.

    Four of them the H66A0 accepts, so this is exactly the case where reading a per-model claim
    out of the shared registry would have shipped ids the hardware rejects.
    """
    shipped = {MUSIC_MODE_SLUGS[slug] for slug in MODEL_PROFILES["H61F5"].music_modes}
    assert shipped.isdisjoint(MUSIC_MODE_IDS_REFUSED_BY_H61F5)
    assert set(MUSIC_MODE_IDS_REFUSED_BY_H61F5) == {0x53, 0x55, 0x65, 0x78}
    # Three of the four are shipped for the H66A0, which is the whole reason these are listed
    # per model rather than read out of MUSIC_MODE_SLUGS.
    assert {0x53, 0x55, 0x78} <= {MUSIC_MODE_SLUGS[s] for s in _H66A0_MUSIC_MODES}
    # Every refused id is a real registry entry, so these are refusals and not typos.
    assert set(MUSIC_MODE_IDS_REFUSED_BY_H61F5) <= set(MUSIC_MODE_SLUGS.values())
