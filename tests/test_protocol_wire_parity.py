"""Parity gate: the shipped builders must reproduce the exact bytes the grammars parse.

The Kaitai gate proves a spec reads captured wire bytes correctly. It says nothing about
whether `protocol.py` can still PRODUCE those bytes, and that half was living inside the
roundtrip harnesses, where it ran outside pytest and outside the coverage gate.

It runs here against `tools/ble/kaitai/src/*.bin`, the same committed fixtures the `.kst`
cases read, so the encoder corpus and the decoder corpus are provably one corpus. Pinning
builders against private inline hex is what lets the two drift apart while both stay
green.

Nothing here imports a generated Kaitai parser. Those are gitignored build products
compiled by the Kaitai job, so a test depending on them would fail in the test job.
"""

import base64
import json
from pathlib import Path

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.custom_effects import ComboContent, FlatContent
from custom_components.ha_govee_led_ble.protocol import Weekday
from custom_components.ha_govee_led_ble.scenes import SCENES
from tools.ble import wifi_provision
from tools.ble.mock_ble.mock_device import GoveeDeviceSim

FIXTURES = Path(__file__).resolve().parents[1] / "tools" / "ble" / "kaitai" / "src"


def fixture(name: str) -> bytes:
    path = FIXTURES / f"{name}.bin"
    assert path.exists(), f"missing fixture {path}; the Kaitai corpus and this module have diverged"
    return path.read_bytes()


def test_fixture_directory_is_the_kaitai_corpus():
    """Guard the shared-corpus premise itself, which is the point of this module."""
    assert FIXTURES.is_dir()
    assert (FIXTURES.parent / "spec").is_dir()
    assert list(FIXTURES.glob("*.bin")), "no fixtures found, so every parity test below is vacuous"


@pytest.mark.parametrize(
    ("name", "built"),
    [
        ("command_write_power_off", lambda: proto.build_power(False)),
        ("command_write_power_on", lambda: proto.build_power(True)),
        ("command_write_brightness", lambda: proto.build_brightness(51)),
        ("command_write_color_rgb", lambda: proto.build_segment_color(proto.ALL_SEGMENTS, 255, 0, 0)),
        ("command_write_seg_color", lambda: proto.build_segment_color(range(8, 16), 0, 255, 0)),
        ("command_write_seg_brightness", lambda: proto.build_segment_brightness(range(1, 8), 17)),
        ("command_write_scene", lambda: proto.build_scene(2163)),
        ("command_write_diy", lambda: proto.build_diy_activate(0xF0, 0x00)),
        ("command_write_diy_saved", lambda: proto.build_diy_activate(0x20, 0x03)),
        ("command_write_music", lambda: proto.build_music_mode_with_color(0x03, 99, (0, 230, 210), calm=False)),
        ("command_write_timer_sleep", lambda: proto.build_timer_sleep(True, 50, 16, 16)),
        (
            "command_write_timer_wake",
            lambda: proto.build_timer_wakeup(True, 100, 17, 1, proto.parse_timer_repeat(0x00), 29),
        ),
        (
            "command_write_timer_schedule",
            lambda: proto.build_timer_schedule(0, True, True, 7, 30, proto.parse_timer_repeat(0xC0)),
        ),
        (
            "command_write_timer_schedule_off_action",
            lambda: proto.build_timer_schedule(2, True, False, 0, 0, proto.parse_timer_repeat(0x80)),
        ),
        (
            "command_write_timer_schedule_weekdays",
            lambda: proto.build_timer_schedule(2, True, True, 0, 0, proto.parse_timer_repeat(0x95)),
        ),
    ],
)
def test_builder_reproduces_the_captured_frame(name, built):
    assert built() == fixture(name)


@pytest.mark.parametrize(
    ("name", "built"),
    [
        ("h6199_command_power_off", lambda: proto.build_power(False)),
        ("h6199_command_power_on", lambda: proto.build_power(True)),
        ("h6199_command_brightness_3", lambda: proto.build_brightness(3)),
        ("h6199_command_brightness_51", lambda: proto.build_brightness(51)),
        ("h6199_command_brightness_100", lambda: proto.build_brightness(100)),
        ("h6199_command_colour_red", lambda: proto.build_segment_color(proto.ALL_SEGMENTS, 255, 0, 0)),
        ("h6199_command_colour_green", lambda: proto.build_segment_color(proto.ALL_SEGMENTS, 0, 255, 0)),
        ("h6199_command_colour_blue", lambda: proto.build_segment_color(proto.ALL_SEGMENTS, 0, 0, 255)),
        ("h6199_command_colour_white", lambda: proto.build_segment_color(proto.ALL_SEGMENTS, 255, 255, 255)),
        ("h6199_command_colour_segment_1", lambda: proto.build_segment_color([1], 255, 0, 0)),
        ("h6199_command_colour_segment_3", lambda: proto.build_segment_color([3], 255, 0, 0)),
        ("h6199_command_colour_segment_1_3", lambda: proto.build_segment_color([1, 3], 255, 0, 0)),
        ("h6199_segment_brightness_one", lambda: proto.build_segment_brightness([1], 17)),
        ("h6199_segment_brightness_pair", lambda: proto.build_segment_brightness([2, 4], 37)),
        ("h6199_segment_brightness_all", lambda: proto.build_segment_brightness(proto.ALL_SEGMENTS, 73)),
        (
            "h6199_command_schedule_slot0_0730_mwf",
            lambda: proto.build_timer_schedule(0, True, True, 7, 30, proto.parse_timer_repeat(0x95)),
        ),
        (
            "h6199_command_schedule_slot1_enabled",
            lambda: proto.build_timer_schedule(1, True, False, 0, 0, proto.parse_timer_repeat(0x80)),
        ),
        (
            "h6199_command_music_rhythm",
            lambda: proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["rhythm"], 99, None),
        ),
        (
            "h6199_command_music_spectrum",
            lambda: proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["spectrum"], 99, None),
        ),
        (
            "h6199_command_music_energetic",
            lambda: proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["energetic"], 99, None),
        ),
        (
            "h6199_command_music_rolling",
            lambda: proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["rolling"], 99, None),
        ),
        ("h6199_video_part_movie", lambda: proto.build_video_mode(False, False, 100, False, 100)),
        ("h6199_video_part_game", lambda: proto.build_video_mode(False, True, 100, False, 100)),
        ("h6199_video_all_movie", lambda: proto.build_video_mode(True, False, 100, False, 100)),
        ("h6199_video_all_game", lambda: proto.build_video_mode(True, True, 100, False, 100)),
        ("h6199_video_saturation_20", lambda: proto.build_video_mode(False, False, 20, True, 12)),
        ("h6199_video_saturation_88", lambda: proto.build_video_mode(False, False, 88, True, 12)),
        ("h6199_video_softness_12", lambda: proto.build_video_mode(False, False, 100, True, 12)),
        ("h6199_video_sound_on", lambda: proto.build_video_mode(False, False, 100, True, 100)),
        ("h6199_white_balance_cool", lambda: proto.build_video_white_balance(7, 10)),
        ("h6199_white_balance_mid", lambda: proto.build_video_white_balance(13, 3)),
        ("h6199_white_balance_reset", lambda: proto.build_video_white_balance(*proto.WHITE_BALANCE_RESET)),
        ("h6199_white_balance_warm", lambda: proto.build_video_white_balance(21, 5)),
        ("h6199_blank_screen_on", lambda: proto.build_blank_screen(True)),
        ("h6199_blank_screen_off", lambda: proto.build_blank_screen(False)),
        ("h6199_relbright_36", lambda: proto.build_relative_brightness(36)),
        ("h6199_relbright_100", lambda: proto.build_relative_brightness(100)),
        ("h6199_scene_sunrise", lambda: proto.build_h6199_scene(0)[0]),
        ("h6199_scene_sunset", lambda: proto.build_h6199_scene(1)[0]),
        ("h6199_scene_candlelight", lambda: proto.build_h6199_scene(9)[0]),
    ],
)
def test_builder_reproduces_the_h6199_captured_frame(name, built):
    """The builders are shared across models, so a second model is a second chance to be wrong.

    These fixtures are H6199 bytes captured from the vendor app, and several are identical
    to their H617A counterparts. That sameness is the finding, not a reason to drop them:
    the duplicate bytes are what proves the shared encoder is right for both, and a
    fixture reused across models would instead assume it.

    What this does NOT establish is that every other shared builder is safe on the H6199.
    Only the opcodes named here have been seen on H6199 wire.

    The three segment cases are also where segments_to_mask is checked against a device
    rather than against itself. The union case is the one that matters: the app asked for
    two segments and sent 0x0005, so a builder that numbered bits from one, or that sent an
    index, reproduces the two single-segment frames and fails only here.
    """
    assert built() == fixture(name)


def test_video_source_polarity_is_pinned_by_the_pair_that_differs_only_there():
    """Game is 1 and Movie is 0, which is the reverse of the order the app lists them in.

    A single frame cannot show this: swap the two and the builder still produces bytes that
    parse. The proof is the differential (`_aggregates.yaml`: h6199_video_part_movie vs
    h6199_video_part_game differ at byte 4 and nowhere else), so it is asserted as a
    differential here too rather than as two independent equalities.
    """
    movie, game = fixture("h6199_video_part_movie"), fixture("h6199_video_part_game")
    moved = [i for i in range(len(movie) - 1) if movie[i] != game[i]]
    assert moved == [4], "the capture pair no longer isolates the picture profile to one byte"
    assert game[4] == 1
    assert proto.build_video_mode(False, True, 100, False, 100)[4] == game[4]
    assert proto.build_video_mode(False, False, 100, False, 100)[4] == movie[4]


def test_h6199_scene_activation_is_not_the_h617a_one():
    """The models disagree at byte 5, so applying a scene with the shared builder is wrong bytes.

    `scene_body::kind` [CONFIRMED_LIVE] carries 1 on the H6199 for a scene the light already
    holds. The H617A activation has no such byte and leaves the position at the scene type,
    which is 0 for a catalogue scene. Both frames are otherwise identical, so the mistake
    survives every test that only checks the scene number.
    """
    for name, code in (("sunrise", 0), ("sunset", 1), ("candlelight", 9)):
        captured = fixture(f"h6199_scene_{name}")
        h617a = proto.build_scene_multi("", code, 0)[-1]
        moved = [i for i in range(len(captured) - 1) if captured[i] != h617a[i]]
        assert moved == [5], name
        assert captured[5] == 1 and h617a[5] == 0, name


def test_the_shared_catalogue_only_agrees_with_h6199_wire_for_the_scenes_we_offer():
    """The catalogue is an H617A numbering, so it may only be read for codes a capture confirms.

    Sunrise, Sunset and Candlelight are 0, 1 and 9 in both, which is why taking their codes
    from the shared catalogue is safe. Forest shows the agreement is coincidence and not a
    rule: 2163 in the catalogue against 212 on this model's wire. Any scene beyond the three
    would therefore be sending the wrong number even if we could upload its body, which is a
    second and independent reason the offered list is closed.
    """
    for name in ("sunrise", "sunset", "candlelight"):
        frame = fixture(f"h6199_scene_{name}")
        assert int.from_bytes(frame[3:5], "little") == SCENES[name].code, name
        assert frame[5] == 1, name
    forest = fixture("h6199_scene_forest")
    assert int.from_bytes(forest[3:5], "little") == 212 != SCENES["forest"].code
    for name in ("forest", "dracarys", "fire_blood", "green_reign"):
        assert fixture(f"h6199_scene_{name}")[5] == 2, name


def test_relative_brightness_compatibility_builder_writes_every_edge():
    frame = proto.build_relative_brightness(36)
    assert frame == fixture("h6199_relbright_36")
    assert set(frame[4:8]) == {36}


def test_every_white_balance_slider_position_is_a_captured_frame():
    assert len(proto.WHITE_BALANCE_POSITIONS) == 20
    for position, pair in enumerate(proto.WHITE_BALANCE_POSITIONS, 1):
        assert proto.build_video_white_balance(*pair) == fixture(f"h6199_white_balance_position_{position:02d}")


@pytest.mark.parametrize(
    ("name", "kelvin", "captured_preview"),
    [
        ("h6199_colour_temp_warm", 2000, (255, 141, 11)),
        ("h6199_colour_temp_mid", 5500, (255, 238, 222)),
        ("h6199_colour_temp_cool", 9000, (217, 225, 255)),
    ],
)
def test_h6199_colour_temperature_shape_matches_while_the_companion_curve_differs(name, kelvin, captured_preview):
    captured = fixture(name)
    built = proto.build_color_temp(kelvin)
    assert built[:9] == captured[:9]
    assert built[12:19] == captured[12:19]
    assert tuple(captured[9:12]) == captured_preview
    assert tuple(built[9:12]) == proto.kelvin_to_rgb(kelvin)


def test_timer_repeat_survives_a_round_trip_through_the_weekday_set():
    """0x95 is the reading that killed "bit 0x80 means fire once": it also names three days."""
    days = proto.parse_timer_repeat(0x95)
    assert days == frozenset({Weekday.MON, Weekday.WED, Weekday.FRI})
    assert proto.build_timer_schedule(2, True, True, 0, 0, days) == fixture("command_write_timer_schedule_weekdays")


def test_colour_temperature_matches_the_capture_except_companion_rgb():
    """Pin the unresolved companion-RGB divergence instead of claiming byte parity."""
    captured = fixture("command_write_color_temp")
    built = proto.build_color_temp(3600)
    assert built[:7] == captured[:7]
    assert built[12:14] == captured[12:14]
    assert tuple(captured[9:12]) == (255, 203, 141)
    assert proto.kelvin_to_rgb(3600) != tuple(captured[9:12])


def test_workshop_activation_has_no_builder():
    """scene_type 0x02 is decode-only, so there is deliberately nothing to reproduce it.

    build_scene emits scene_type 0x00. If it ever starts emitting the Workshop form this
    test fails, which is the point: the gap is a decision, not an oversight.
    """
    captured = fixture("command_write_scene_workshop")
    assert captured[5] == 0x02
    assert proto.build_scene(401)[5] == 0x00


def test_per_segment_brightness_has_no_builder():
    """static_sub 0x03 is decode-only. Same reasoning as the Workshop case above."""
    captured = fixture("command_write_seg_brightness_all")
    assert captured[3] == 0x03
    assert len(captured[4:19]) == 15
    assert proto.build_segment_brightness(range(1, 16), 100)[3] == 0x02


def payload_of(name: str) -> bytes:
    """The decoder-side payload, split by the shipped splitter rather than by hand."""
    split = proto.split_status_frame(fixture(name))
    assert split is not None, f"{name} was not recognised as a status frame at all"
    return split[1]


@pytest.mark.parametrize(
    ("name", "domain"),
    [
        ("status_reply_power", 0x01),
        ("status_reply_brightness", 0x04),
        ("status_reply_unit_count", 0x40),
        ("status_reply_fw", 0x06),
        ("status_reply_hw", 0x07),
        ("status_reply_cm_music", 0x05),
    ],
)
def test_status_frames_split_on_the_domain_the_grammar_reads(name, domain):
    assert proto.split_status_frame(fixture(name))[0] == domain


def test_version_strings_decode_the_same_as_the_grammar():
    assert proto.parse_fw_version(payload_of("status_reply_fw")) == "3.02.24"
    assert proto.parse_hw_version(payload_of("status_reply_hw")) == "3.01.01"


def test_hardware_version_rejects_a_payload_without_its_prefix():
    """The 0x03 prefix is what separates the two version replies, so dropping it must fail."""
    assert proto.parse_hw_version(payload_of("status_reply_fw")) is None


def test_schedule_table_decodes_all_four_slots():
    slots = proto.parse_timer_schedule_table(payload_of("status_reply_timer"))
    assert len(slots) == 4
    assert (slots[0].enabled, slots[0].on_action) == (True, True)
    assert (slots[0].hour, slots[0].minute) == (7, 30)
    assert slots[0].repeat_days == proto.parse_timer_repeat(0xC0)


def test_the_device_stores_the_repeat_byte_rather_than_the_app_remembering_it():
    """Slot 2 read back 0x95 moments after it was written, against 0x80 in the earlier table.

    This is the whole point of holding both tables: one table alone cannot tell a stored
    value from an app-side default echoed back.
    """
    before = proto.parse_timer_schedule_table(payload_of("status_reply_timer"))
    after = proto.parse_timer_schedule_table(payload_of("status_reply_timer_stored_repeat"))
    assert before[2].repeat_days == frozenset()
    assert after[2].repeat_days == frozenset({Weekday.MON, Weekday.WED, Weekday.FRI})


def test_colour_mode_replies_decode_the_same_as_the_grammar():
    music = proto.parse_color_mode_response(payload_of("status_reply_cm_music"))
    assert music.music_sensitivity == 99
    assert music.music_color == (255, 0, 0)
    diy = proto.parse_color_mode_response(payload_of("status_reply_cm_diy_saved"))
    assert diy.diy_slot == 0x84


def test_h6199_music_reply_tracks_fixed_red_and_blue():
    red = proto.parse_color_mode_response(payload_of("h6199_status_colour_mode_music_red"))
    blue = proto.parse_color_mode_response(payload_of("h6199_status_colour_mode_music_blue"))
    assert red.music_mode == blue.music_mode == "rhythm"
    assert red.music_color == (255, 0, 0)
    assert blue.music_color == (0, 0, 255)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("h6199_status_colour_mode_video", ("movie", True, 100, False, 100)),
        ("h6199_status_colour_mode_video_game", ("game", True, 100, False, 100)),
        ("h6199_status_colour_mode_video_custom", ("game", False, 20, True, 12)),
    ],
)
def test_h6199_video_reply_tracks_the_captured_settings(name, expected):
    parsed = proto.parse_color_mode_response(payload_of(name), video_supported=True)
    assert (
        parsed.video_mode,
        parsed.video_full_screen,
        parsed.video_saturation,
        parsed.video_sound_effects,
        parsed.video_sound_effects_softness,
    ) == expected


def test_the_style_byte_is_only_read_as_calm_for_rhythm():
    """A deliberate asymmetry between the grammar and the decoder, pinned so it stays one.

    govee_common::music_selector names byte 3 `style` for every mode, because structurally
    that is what it is. Only Rhythm interprets it as Dynamic/Calm; the other modes
    repurpose it, so the decoder leaves music_calm unset rather than reporting a value it
    cannot justify. This fixture is Rolling, so a bare False here would be a claim the
    capture does not support.
    """
    rolling = proto.parse_color_mode_response(payload_of("status_reply_cm_music"))
    assert rolling.music_mode == "rolling"
    assert rolling.music_calm is None


def test_the_colour_mode_query_decodes_as_a_video_reply():
    """The direction trap, stated as a test rather than left as a warning in a doc.

    A parser handed the aa 05 query with no direction reports video mode. The query's
    payload begins 0x00, and 0x00 is the video selector, so the two are indistinguishable
    without knowing which way the frame travelled. This has been hit live twice, on 0xa3
    and on 0x01, which is why decode_govee refuses to label a frame without a direction.

    Knowing the model narrows it but does not close it: a model with video still cannot
    tell its own query from a reply, which is why the direction, not the profile, is the fix.
    """
    split = proto.split_status_frame(proto.COLOR_MODE_QUERY)
    assert split is not None
    domain, payload = split
    assert domain == 0x05
    assert payload[0] == 0x00
    assert proto.parse_color_mode_response(payload, video_supported=True).mode is proto.ParsedMode.VIDEO
    assert proto.parse_color_mode_response(payload).mode is proto.ParsedMode.UNKNOWN


@pytest.mark.parametrize(
    ("name", "setup"),
    [
        ("status_reply_cm_static", lambda sim: sim.handle_write(proto.build_color_rgb(10, 20, 30))),
        ("status_reply_multi_effect", lambda sim: None),
    ],
)
def test_the_simulator_answers_with_the_bytes_the_device_sent(name, setup):
    """Hold the sim to the corpus, because everything else in the suite trusts it.

    The sim answered a static query with a fabricated ``15 01 <rgb>`` echo for a long time.
    Every test agreed with it, so the decoder reading a colour the H617A never sends stayed
    invisible until the capture was read. Asserting the decoded fields is not enough to catch
    that: once the decoder stops reading those bytes, a fabricated payload decodes identically
    to an honest one. Only the bytes themselves close it.
    """
    frame = fixture(name)
    sim = GoveeDeviceSim("H617A")
    setup(sim)
    (reply,) = sim.handle_write(proto.build_packet(proto.STATUS_HEADER, frame[1], []))
    assert bytes(reply) == frame


@pytest.mark.parametrize(
    ("name", "built"),
    [
        ("music_frame_rhythm_c1_ff0000", lambda: proto.build_music_mode_with_color(0x03, 99, (255, 0, 0))),
        ("music_frame_rhythm_c0_dynamic", lambda: proto.build_music_mode_with_color(0x03, 99, None, calm=False)),
        ("music_frame_rhythm_c0_calm", lambda: proto.build_music_mode_with_color(0x03, 99, None, calm=True)),
        ("music_frame_rhythm_sens0", lambda: proto.build_music_mode_with_color(0x03, 0, (0, 230, 210))),
        ("music_frame_rhythm_sens47", lambda: proto.build_music_mode_with_color(0x03, 47, (0, 230, 210))),
        ("music_frame_rhythm_sens99", lambda: proto.build_music_mode_with_color(0x03, 99, (0, 230, 210))),
        ("music_frame_rolling_c1_sens50", lambda: proto.build_music_mode_with_color(0x06, 50, (255, 0, 0))),
        ("music_frame_separation_c0_sens50", lambda: proto.build_music_mode_with_color(0x32, 50, None)),
        ("music_frame_bloom_c0_calm", lambda: proto.build_music_mode_with_color(0x30, 99, None, calm=True)),
    ],
)
def test_music_builder_reproduces_the_captured_frame(name, built):
    assert built() == fixture(name)


def test_h6199_sensitivity_reaches_the_captured_ceiling():
    assert proto.build_music_mode_with_color(0x03, 255, None)[4] == 100
    assert fixture("h6199_music_sensitivity_100")[4] == 100


def test_h6199_brightness_query_and_reply_use_direct_percent():
    assert proto.BRIGHTNESS_QUERY == fixture("h6199_query_brightness")
    assert payload_of("h6199_status_brightness_3")[0] == 3
    assert payload_of("h6199_status_brightness_24")[0] == 24


def a3_body(frames: list[bytes]) -> bytes:
    """Reassemble the single A3 transaction a builder emits, using the shared implementation.

    reassemble_a3 requires exactly one transaction and says so; handing it a builder's whole
    output concatenates the upload with whatever follows. Segmenting first is not a detail,
    it is the contract, and getting it wrong is the defect that corrupted 21 of 31 A3
    captures before it was found.
    """
    from tools.ble.decode_govee import reassemble_a3, segment_a3

    uploads = segment_a3([f for f in frames if len(f) == 20 and f[0] == 0xA3])
    assert len(uploads) == 1, f"expected one A3 transaction from the builder, got {len(uploads)}"
    return reassemble_a3(uploads[0])


@pytest.mark.parametrize(
    ("name", "mode", "overrides"),
    [
        ("music_body_bloom_dynamic", 0x30, {}),
        ("music_body_bloom", 0x30, {27: 0x14}),
        ("music_body_shiny_dynamic", 0x31, {}),
        ("music_body_shiny_calm", 0x31, {20: 0x14, 21: 0x46}),
        ("music_body_separation_p5_grad1", 0x32, {20: 5}),
        ("music_body_hopping_rb50", 0x33, {}),
        ("music_body_fountain", 0x35, {26: 1, 28: 3}),
    ],
)
def test_music_parameter_builder_reproduces_shared_corpus(name, mode, overrides):
    assert a3_body(proto.build_music_params_a3(mode, overrides)) == fixture(name)


def slice_palette(body: bytes, offset: int, plen: int) -> tuple[tuple[int, int, int], ...]:
    return tuple((body[i], body[i + 1], body[i + 2]) for i in range(offset, offset + plen, 3))


@pytest.mark.parametrize(
    "name",
    [
        "diy_type04_flat_plen_0x03_1_colour_fam_0x01",
        "diy_type04_flat_plen_0x09_3_colours_fam_0x08",
        "diy_type04_flat_plen_0x0c_4_colours_fam_0x00",
        "diy_type04_flat_plen_0x15_7_colours_fam_0x03",
    ],
)
def test_flat_diy_encoder_reproduces_the_captured_body(name):
    """Feed the captured fields straight back through the builder, as the harness did.

    Transcribing a palette by hand only tests the transcription, so the arguments are
    sliced out of the fixture using the layout the grammar declares.
    """
    captured = fixture(name)
    plen = captured[6]
    content = FlatContent(
        family=captured[3],
        variant=captured[4],
        speed=captured[5],
        palette=slice_palette(captured, 7, plen),
    )
    assert a3_body(proto.build_flat_diy(content)) == captured


@pytest.mark.parametrize(
    "name",
    [
        "diy_type04_combo_seqlen_0x02_1_effect",
        "diy_type04_combo_seqlen_0x04_2_effects",
        "diy_type04_combo_seqlen_0x06_3_effects",
        "diy_type04_combo_seqlen_0x08_4_effects",
        "diy_type04_combo_seqlen_0x04_pairs_0_0_3_3",
    ],
)
def test_combo_encoder_reproduces_the_captured_body(name):
    captured = fixture(name)
    plen = captured[6]
    seq_offset = 7 + plen
    seqlen = captured[seq_offset]
    pairs = captured[seq_offset + 1 : seq_offset + 1 + seqlen]
    content = ComboContent(
        variant=captured[4],
        speed=captured[5],
        palette=slice_palette(captured, 7, plen),
        effects=tuple((pairs[i], pairs[i + 1]) for i in range(0, seqlen, 2)),
    )
    assert a3_body(proto.build_combo(content)) == captured


def body_after_type(captured: bytes) -> bytes:
    """Strip the 01 <linecount> 03 A3 header, leaving what build_a3_multi is handed."""
    assert captured[0] == 0x01 and captured[2] == 0x03
    return captured[3:].rstrip(b"\x00")


@pytest.mark.parametrize(
    "name",
    ["diy_type03_anchor_vibrant_15g", "diy_type03_eff09_gc15", "diy_type03_eff19_gc07"],
)
def test_type03_plain_framing_reproduces_the_captured_body(name):
    """The plain multi-frame form, which is what the app actually sends."""
    captured = fixture(name)
    frames = proto.build_a3_multi(0x03, body_after_type(captured))
    assert a3_body(frames) == captured


def test_build_sketch_reproduces_a_single_chunk_body():
    """The common case works: a body fitting one 17-byte chunk plus the terminator frame."""
    captured = fixture("diy_type03_anchor_sketch_seg3")
    after = body_after_type(captured)
    assert len(after) + 3 <= 17
    assert a3_body(proto.build_a3_multi(0x03, after, terminator=True)) == captured


def test_the_terminator_form_cannot_reproduce_a_multi_chunk_body():
    """The two A3 forms, pinned apart on the one body that can tell them apart.

    A body fitting a single chunk gets a terminator either way, so `terminator` is
    unfalsifiable there. The merged-group sketch body is exactly one byte over that
    boundary, which makes it the smallest fixture that can separate the forms: the plain
    form gives the last DATA chunk the 0xff index, while the terminator form appends a
    further all-zero frame and overshoots by 17 bytes.

    This test used to assert the divergence as a live defect, because build_sketch
    hardcoded terminator=True and could not reproduce this capture. That was corrected on
    2026-07-31 (see the comment on build_sketch), and the assertions were inverted to pin
    the fixed behaviour -- but the name and this docstring were left describing the old
    defect until 2026-08-01. Anything that reads like a standing bug here is stale; the
    builder is right, and what is pinned is that the WRONG form stays wrong.
    """
    captured = fixture("diy_type03_anchor_sketch_merged")
    after = body_after_type(captured)
    assert len(after) + 3 == 18, "this fixture is meant to sit just over the one-chunk boundary"
    assert a3_body(proto.build_a3_multi(0x03, after, terminator=False)) == captured
    diverged = a3_body(proto.build_a3_multi(0x03, after, terminator=True))
    assert len(diverged) == len(captured) + 17
    assert diverged != captured


CATALOGUE = Path(__file__).resolve().parents[1] / "tools" / "ble" / "catalogues" / "effect-library-H617A.json"


def test_the_h617a_catalogue_holds_exactly_two_type_one_scenes():
    """A claim about the frozen catalogue, not about wire structure, so it lives here.

    If a refresh adds a third, the scene_type1 fixtures no longer cover the population and
    the corpus must be extended rather than quietly left behind.
    """
    scenes = [s for s in json.loads(CATALOGUE.read_text())["scenes"] if s.get("scene_type") == 1]
    assert {s["code"] for s in scenes} == {1170, 1173}


@pytest.mark.parametrize(("code", "name"), [(1173, "halloween"), (1170, "sweet")])
def test_type_one_scene_bodies_are_the_catalogue_param_framed(code, name):
    """The round trip here is internal: catalogue param in, A3 body out, param back.

    A captured Halloween application confirmed the catalogue param IS the A3 payload, which
    is what makes this more than a self-consistency check.
    """
    param = base64.b64decode(next(s["param"] for s in json.loads(CATALOGUE.read_text())["scenes"] if s["code"] == code))
    captured = fixture(f"scene_type1_h617a_{name}")
    assert a3_body(proto.build_a3_multi(1, param)) == captured
    assert captured[3 : 3 + len(param)] == param
    assert captured[0] == 0x01 and captured[2] == 0x01


@pytest.mark.parametrize(
    ("ssid", "password", "fixture_names"),
    [
        (
            wifi_provision.KNOWN_ACCEPTED_SSID,
            wifi_provision.KNOWN_ACCEPTED_PASSWORD,
            (
                "h6199_wifi_frame_header",
                "h6199_wifi_frame_data1",
                "h6199_wifi_frame_data2",
                "h6199_wifi_frame_data3",
                "h6199_wifi_frame_data4",
                "h6199_wifi_frame_terminator",
            ),
        ),
        (
            wifi_provision.SHAPE3_SSID,
            wifi_provision.SHAPE3_PASSWORD,
            (
                "h6199_wifi_shape3_header",
                "h6199_wifi_shape3_data1",
                "h6199_wifi_shape3_data2",
                "h6199_wifi_shape3_data3",
                "h6199_wifi_frame_terminator",
            ),
        ),
        (
            wifi_provision.SHAPE5_SSID,
            wifi_provision.SHAPE5_PASSWORD,
            (
                "h6199_wifi_shape5_header",
                "h6199_wifi_shape5_data1",
                "h6199_wifi_shape5_data2",
                "h6199_wifi_shape5_data3",
                "h6199_wifi_shape5_data4",
                "h6199_wifi_shape5_data5",
                "h6199_wifi_frame_terminator",
            ),
        ),
    ],
)
def test_wifi_encoder_reproduces_every_captured_shape(ssid, password, fixture_names):
    """The provisioning encoder is checked against captured bytes, not against itself.

    This is the one encoder in the tree whose output is written to a device's persistent
    configuration. The captured corpus spans three, four and five data frames, so a boundary
    bug can no longer hide behind the original four-frame case.

    The credentials are invented. A real network's must never be committed, and the tool
    reads them from stdin for the same reason.
    """
    assert wifi_provision.verify_against_known_accepted()

    frames = wifi_provision.build(ssid, password)
    for name, frame in zip(fixture_names, frames, strict=True):
        assert frame == fixture(name), name


def test_wifi_body_is_forty_nine_bytes_and_fragments_into_four():
    """The two trailing bytes are the whole reason the sequence has four data frames.

    They were on the wire before they were understood and were briefly read as padding,
    which made the frame count look unpredictable. A 47-byte body has never been
    acknowledged by this firmware and a 49-byte one has, so the encoder always sends them.
    """
    body = wifi_provision.build_body(wifi_provision.KNOWN_ACCEPTED_SSID, wifi_provision.KNOWN_ACCEPTED_PASSWORD)
    assert body == fixture("h6199_wifi_body_fakenet")
    assert len(body) == 49
    assert len(wifi_provision.build_sequence(body)) == 6  # header + 4 data + terminator


@pytest.mark.parametrize(
    ("ssid", "password", "fixture_name", "body_len", "data_frames"),
    [
        (wifi_provision.SHAPE3_SSID, wifi_provision.SHAPE3_PASSWORD, "h6199_wifi_shape3_body", 48, 3),
        (wifi_provision.SHAPE5_SSID, wifi_provision.SHAPE5_PASSWORD, "h6199_wifi_shape5_body", 65, 5),
    ],
)
def test_wifi_body_crosses_both_neighbouring_frame_boundaries(ssid, password, fixture_name, body_len, data_frames):
    body = wifi_provision.build_body(ssid, password)
    assert body == fixture(fixture_name)
    assert len(body) == body_len
    assert len(wifi_provision.build_sequence(body)) == data_frames + 2
    assert wifi_provision.reference_for(ssid, password) is not None


def test_wifi_builder_refuses_unobserved_field_lengths():
    assert wifi_provision.reference_for("UNSEEN12", "12345678") is None


def test_wifi_endpoint_override_is_limited_to_a_captured_api_width():
    endpoint = "https://govee.ai.xaz.lol"
    assert len(endpoint) == len(wifi_provision.DEFAULT_API)
    assert wifi_provision.reference_for(
        wifi_provision.KNOWN_ACCEPTED_SSID,
        wifi_provision.KNOWN_ACCEPTED_PASSWORD,
        endpoint,
    )
    assert not wifi_provision.reference_for(
        wifi_provision.KNOWN_ACCEPTED_SSID,
        wifi_provision.KNOWN_ACCEPTED_PASSWORD,
        f"{endpoint}/longer",
    )
    assert wifi_provision.build(
        wifi_provision.KNOWN_ACCEPTED_SSID,
        wifi_provision.KNOWN_ACCEPTED_PASSWORD,
        endpoint,
    ) != wifi_provision.build(
        wifi_provision.KNOWN_ACCEPTED_SSID,
        wifi_provision.KNOWN_ACCEPTED_PASSWORD,
    )


def test_an_open_network_sends_a_zero_length_passphrase():
    """password_len is why the body cannot be read as fixed-width fields."""
    body = wifi_provision.build_body("OPENNET", "")
    assert body[8] == 0
    assert body[:8] == b"\x07OPENNET"
