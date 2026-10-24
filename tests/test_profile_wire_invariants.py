"""Invariants that hold a profile's declarations against the wire grammar it routes to.

Every check here exists because the suite once passed while the thing it checks was broken.
A profile can declare a capability the grammar cannot express, and nothing fails until a real
device answers: the reply parses as raw bytes, a reader reaches for a field, and the exception
lands inside the BLE notification callback where it is swallowed. These tests do on every
profile what only hardware used to do.
"""

from collections.abc import Callable
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from custom_components.ha_govee_led_ble import generated_protocol_adapter as a
from custom_components.ha_govee_led_ble import protocol_core, protocol_music_params
from custom_components.ha_govee_led_ble.const import (
    MODEL_PROFILES,
    ModelProfile,
    ReadDomain,
    device_profile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import (
    _STATUS_DOMAIN_NAMES,
    ParsedH6179Status,
    ParsedMode,
    ParsedStatusEnvelope,
    parse_color_mode,
    status_is_authorized,
)
from custom_components.ha_govee_led_ble.coordinator_status import (
    decode_status_frame as decode_single_status_frame,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    build_segment_color_temp,
)
from custom_components.ha_govee_led_ble.music_commands import (
    prepare_music_profile_writes,
    prepare_music_request,
)
from custom_components.ha_govee_led_ble.music_protocol import (
    music_code_for,
    music_mode_has_parameter_write,
)
from custom_components.ha_govee_led_ble.music_semantics import (
    music_parameters_available,
    music_variant,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import (
    MODEL_SCENES,
    SceneEntry,
    scene_key_for_code,
    scene_selector_code,
    scene_supported,
)
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def _xor(frame: bytes) -> bytes:
    return frame + bytes([xor_checksum(frame)])


def _status(domain: int, body: bytes = b"", *, profile: ModelProfile | None = None) -> bytes:
    if profile is not None and profile.bulk_status_grammar and domain == 0x05:
        record = bytes([domain, len(body)]) + body
        assert len(record) <= 12
        return _xor(b"\xac\x00\x01\x00" + bytes([len(record)]) + b"\x03\x00" + record.ljust(12, b"\x00"))
    return _xor(bytes([0xAA, domain]) + body.ljust(17, b"\x00"))


def _parse_status(frame: bytes, model: str, profile: ModelProfile):
    if a.is_bulk_status_frame(frame, profile):
        result = a.BulkStatusCollector().feed(frame)
        assert result.rejection is None and result.parsed is not None
        assert len(result.parsed.records) == 1
        return protocol_core.ProtocolParseResult(result.parsed.records[0], result.parser, None)
    return a.parse_status_result(frame, model, profile=profile)


def decode_status_frame(frame: bytes, model: str, *, profile: ModelProfile):
    if a.is_bulk_status_frame(frame, profile):
        record = _parse_status(frame, model, profile).parsed
        return ParsedStatusEnvelope(ReadDomain.COLOUR_MODE, int(record.domain), record._raw_body, record)
    return decode_single_status_frame(frame, model, profile=profile)


def _consume_status(coordinator: GoveeBLECoordinator, frame: bytes) -> None:
    if a.is_bulk_status_frame(frame, coordinator.profile):
        coordinator._bulk_collector = a.BulkStatusCollector()
        coordinator._bulk_query_incomplete = True
    coordinator._notify_callback(None, bytearray(frame))


# Runtime qualification contexts that produce distinct effective profiles through device_profile().
_QUALIFIED_CONTEXTS: tuple[tuple[str, str, int | None, int | None, str | None, str | None], ...] = (
    ("H60A1-2200k", "H60A1", None, None, None, "1.04.02"),
    ("H60A1-segmented", "H60A1", 1, 1, "1.02.20", "1.04.03"),
    ("H60A1-segmented-2200k", "H60A1", 2, 1, "1.02.20", "1.04.02"),
    ("H60A6-pact-1-1", "H60A6", 1, 1, None, None),
    ("H60A6-pact-1-2", "H60A6", 1, 2, None, None),
    ("H60A6-pact-1-3", "H60A6", 1, 3, "1.00.41", "1.04.03"),
    ("H60A6-unqualified", "H60A6", None, None, None, None),
    ("H60A6-pact-1-4", "H60A6", 1, 4, None, None),
    ("H6076-unqualified", "H6076", None, None, None, None),
    ("H6076-pact1-unidentified-fw", "H6076", 1, 1, None, None),
    ("H6076-pact1-legacy-music", "H6076", 1, 1, "1.01.00", "3.01.01"),
    ("H6076-pact2-legacy-music", "H6076", 2, 1, "1.01.00", "3.01.01"),
    ("H6076-pact2-music", "H6076", 2, 1, "1.04.05", "3.05.00"),
    ("H6097-bootstrap", "H6097", None, None, None, None),
    ("H6102-bootstrap", "H6102", None, None, None, None),
    ("H6102-pact1-basic", "H6102", 1, 1, None, None),
    ("H6102-pact1-intermediate-selector-scenes", "H6102", 1, 1, "1.03.01", "1.00.03"),
    ("H6102-pact1-intermediate-uploaded-scenes", "H6102", 1, 1, "1.04.00", "1.00.03"),
    ("H6102-pact1-intermediate-expanded-music", "H6102", 1, 1, "1.07.00", "1.00.02"),
    ("H6102-pact1-extended", "H6102", 1, 1, "1.06.00", "1.00.03"),
    ("H6102-pact1-extended-expanded-music", "H6102", 1, 1, "1.08.08", "1.00.03"),
    ("H6102-pact10-basic", "H6102", 10, 1, None, None),
    ("H6102-pact10-basic-limit", "H6102", 10, 1, "3.00.00", "3.01.01"),
    ("H6125-power-only", "H6125", None, None, None, None),
    ("H6125-legacy", "H6125", 1, 1, "1.00.11", "1.00.01"),
    ("H6125-intermediate-selector-scenes", "H6125", 1, 1, "1.03.01", "1.00.04"),
    ("H6125-intermediate-uploaded-scenes", "H6125", 1, 1, "1.04.08", "1.00.04"),
    ("H6125-current-basic-music", "H6125", 1, 2, "1.06.00", "1.00.03"),
    ("H6125-hw-1.00.03", "H6125", 1, 2, "1.07.00", "1.00.03"),
    ("H6125-hw-1.00.04", "H6125", 1, 2, "1.07.01", "1.00.04"),
    ("H6125-modern-basic-music", "H6125", 10, 1, "2.03.99", "2.01.01"),
    ("H6125-modern-full", "H6125", 10, 2, "3.04.37", "3.01.10"),
    ("H6199-pact1", "H6199", 1, 1, None, None),
    ("H6199-pact1-new-group", "H6199", 1, 1, "1.09.00", "3.02.01"),
    ("H6199-pact2-baseline-group", "H6199", 2, 1, None, None),
    ("H6199-unqualified-group", "H6199", None, None, None, None),
    ("H7020-unqualified", "H7020", None, None, None, None),
)


def _effective_profiles() -> tuple[tuple[str, str, ModelProfile], ...]:
    cases: list[tuple[str, str, ModelProfile]] = [
        (model, model, profile) for model, profile in sorted(MODEL_PROFILES.items())
    ]
    seen = {(model, profile) for _, model, profile in cases}
    for case_id, model, pact_type, pact_code, firmware, hardware in _QUALIFIED_CONTEXTS:
        profile = device_profile(model, pact_type, pact_code, firmware=firmware, hardware=hardware)
        if (model, profile) not in seen:
            seen.add((model, profile))
            cases.append((case_id, model, profile))
    return tuple(cases)


_EFFECTIVE_PROFILES = _effective_profiles()

_STATUS_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.status_grammar is not None
)

# Raw MODEL_PROFILES["H6125"] is a static template without a brightness register range; runtime
# coordinators always resolve H6125 through device_profile() to power-only or a ranged profile.
_RUNTIME_STATUS_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.status_grammar is not None and profile is not MODEL_PROFILES["H6125"]
)

_SEGMENT_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_segments and profile.can_read(ReadDomain.SEGMENTS) and profile.status_grammar is not None
)

_SCALAR_WHITE_BALANCE_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_white_balance_readback and profile.video_white_balance_representation == "scalar"
)

_COMMAND_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.command_grammar is not None and profile is not MODEL_PROFILES["H6125"]
)

_VIDEO_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_video_mode
)

_MUSIC_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.music_modes and profile is not MODEL_PROFILES["H6125"]
)

_MUSIC_READBACK_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.music_modes and profile.supports_color_mode_readback and profile is not MODEL_PROFILES["H6125"]
)

_SCENE_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_scenes and profile is not MODEL_PROFILES["H6125"]
)

_DIY_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_custom_effects
    and profile.effect_readback == "diy_code_only"
    and profile is not MODEL_PROFILES["H6125"]
)

_COLOUR_MODE_READBACK_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.supports_color_mode_readback and profile is not MODEL_PROFILES["H6125"]
)

_BOOLEAN_CONTROL_PROFILES = tuple(
    pytest.param(model, profile, id=case_id)
    for case_id, model, profile in _EFFECTIVE_PROFILES
    if profile.boolean_controls and profile is not MODEL_PROFILES["H6125"]
)


def _status_root_type(profile: ModelProfile):
    assert profile.status_grammar in protocol_core._STATUS_ROOTS
    return protocol_core._STATUS_ROOTS[profile.status_grammar][1]


def _status_color_mode_enum(profile: ModelProfile):
    if profile.bulk_status_grammar:
        return protocol_core.H60aBulk.Mode
    if profile.status_grammar == "H6097":
        return protocol_core.H6099StatusReply.ModeSel
    root_type = _status_root_type(profile)
    return getattr(
        root_type,
        "ColorMode",
        getattr(root_type, "ModeSel", getattr(root_type, "ModeSelector", protocol_core.H6102StatusReply.ColorMode)),
    )


def _status_music_enum(profile: ModelProfile):
    if profile.status_grammar == "H6097":
        return protocol_core.H6097MusicWrite.MusicMode
    if profile.status_grammar == "H6076":
        return protocol_core.H6076MusicWrite.MusicMode
    if profile.status_grammar == "H6125-intermediate":
        return protocol_core.H6125StatusReply.MusicMode
    root_type = _status_root_type(profile)
    return getattr(root_type, "MusicMode", getattr(root_type, "MusicEffect", protocol_core.GoveeCommon.MusicMode))


def _segment_domain_byte(profile: ModelProfile) -> int:
    root_type = _status_root_type(profile)
    domain_enum = getattr(root_type, "AaDomain", getattr(root_type, "StatusDomain", None))
    assert domain_enum is not None
    return int(domain_enum.segments)


def _segment_pages(profile: ModelProfile) -> list[bytes]:
    """Full segment pages: segment 0 is a real black/off record, remaining meaningful
    records carry distinct R/G/B channels, and unused slots are zero-filled."""
    domain_byte = _segment_domain_byte(profile)
    rgb_only = domain_byte == 0xA2
    pages = []
    for group in range(1, profile.segment_group_count + 1):
        offset = (group - 1) * profile.segment_group_size
        meaningful = min(profile.segment_group_size, profile.segment_count - offset)
        records = b""
        for index in range(profile.segment_group_size):
            segment = offset + index
            if index >= meaningful or segment == 0:
                records += bytes(3 if rgb_only else 4)
            elif rgb_only:
                records += bytes([segment + 1, segment + 2, segment + 3])
            else:
                records += bytes([50 + segment, segment + 1, segment + 2, segment + 3])
        body = bytes([group]) + records
        pages.append(_status(domain_byte, body))
    return pages


def _status_frames_for_domain(domain: ReadDomain, model: str, profile: ModelProfile) -> tuple[bytes, ...]:
    if domain is ReadDomain.POWER:
        return (_status(0x01, b"\x01"),)
    if domain is ReadDomain.BRIGHTNESS:
        return (_status(0x04, b"\x32"),)
    if domain in {ReadDomain.COLOUR_MODE, ReadDomain.MODE}:
        if profile.status_grammar == "H601C":
            return (_status(0x05, bytes.fromhex("0dff00000000000000")),)
        return (_status(0x05, bytes.fromhex("0a2003"), profile=profile),)
    if domain is ReadDomain.FIRMWARE:
        return (bytes.fromhex("aa06332e30322e3234000000000000000000009b"),)
    if domain is ReadDomain.HARDWARE:
        if model == "H6199":
            return (bytes.fromhex("aa0703332e30322e30310000000000000000009e"),)
        return (bytes.fromhex("aa0703332e30312e30310000000000000000009d"),)
    if domain is ReadDomain.SUBORDINATE_20:
        return (_status(0x20, b"1.03.00\x00"),)
    if domain is ReadDomain.SUBORDINATE_21:
        return (_status(0x21, b"1.00.33\x00"),)
    if domain is ReadDomain.DISPLAY_SETTING:
        frames: list[bytes] = []
        if profile.supports_white_balance_readback:
            if profile.video_white_balance_representation == "scalar":
                frames.append(_status(0xA9, bytes([0x06, 0x01, 0x32])))
            else:
                frames.append(_status(0xA9, bytes([0x00, 0x06, 0x01, 0x10, 0x03, 0x01, 0x15, 0x05])))
        if profile.supports_blank_screen:
            frames.append(_status(0xA9, bytes([0x0A, 0x06, 0x01, 0x02, 0x0A, 0x00, 0x78, 0x00])))
        if profile.supports_black_border:
            frames.append(_status(0xA9, bytes([0x0B, 0x01, 0x01])))
        return tuple(frames)
    if domain is ReadDomain.RELATIVE_BRIGHTNESS:
        return (_status(0xAE, bytes([0x01, len(profile.video_brightness_zones), 10, 20, 30, 40, 0, 0])),)
    if domain is ReadDomain.SEGMENTS:
        return tuple(_segment_pages(profile))
    if domain is ReadDomain.CONFIGURED_STRINGS:
        return (_status(0x0F, b"\x01"),)
    if domain is ReadDomain.PHYSICAL_IC_COUNT:
        return (_status(0x40, b"\x00\x32"),)
    if domain is ReadDomain.INSTALLATION_DIRECTION:
        return (_status(0x30, b"\x02"),)
    if domain is ReadDomain.CAMERA_HEALTH:
        return (_status(0x32, b"\x01"),)
    raise AssertionError(f"no representative status frame defined for {domain}")


def test_every_registered_model_is_covered_by_effective_profiles() -> None:
    """No registered SKU in MODEL_PROFILES or qualified context may be silently omitted."""
    covered = {model for _, model, _ in _EFFECTIVE_PROFILES}
    assert covered == set(MODEL_PROFILES)
    case_ids = {case_id for case_id, _, _ in _EFFECTIVE_PROFILES}
    assert {case_id for case_id, *_ in _QUALIFIED_CONTEXTS} <= case_ids
    assert len(_SEGMENT_PROFILES) >= 10
    h6125_grammars = {
        profile.status_grammar
        for _, model, profile in _EFFECTIVE_PROFILES
        if model == "H6125" and profile.status_grammar is not None
    }
    assert h6125_grammars == {"H6125", "H6125-legacy", "H6125-intermediate", "H6125-modern"}


@pytest.mark.parametrize(("model", "profile"), _STATUS_PROFILES)
def test_every_claimed_read_domain_has_a_typed_body(model: str, profile: ModelProfile) -> None:
    """A claimed domain whose body falls through to raw bytes is the `.text`/`.value` bug:
    the reply parses, the reader reaches for a field, and AttributeError is raised inside the
    notification callback, losing the notification rather than degrading."""
    assert profile.status_grammar in protocol_core._STATUS_ROOTS, (
        f"{model} status_grammar {profile.status_grammar} is unrouted"
    )
    expected_parser = protocol_core._STATUS_ROOTS[profile.status_grammar][0]
    for domain in sorted(profile.read_domains, key=lambda d: d.value):
        frames = _status_frames_for_domain(domain, model, profile)
        assert frames, f"{model} claims {domain.value} but has no representative status frames"
        for frame in frames:
            raw = _parse_status(frame, model, profile)
            assert raw.rejection is None and raw.parsed is not None, (
                f"{model} ({profile.name}) rejected {domain.value} frame: {raw.rejection}"
            )
            parser = "h60a_bulk.payload" if a.is_bulk_status_frame(frame, profile) else expected_parser
            assert raw.parser == parser
            assert not isinstance(raw.parsed.body, (bytes, bytearray)), (
                f"{model} ({profile.name}) leaves {domain.value} as raw bytes in {expected_parser}"
            )
            decoded = decode_status_frame(frame, model, profile=profile)
            assert decoded is not None
            assert decoded.domain is domain and decoded.raw_domain == (
                int(raw.parsed.domain) if a.is_bulk_status_frame(frame, profile) else frame[1]
            )
            if profile.status_grammar == "H6179":
                assert isinstance(decoded.generated, ParsedH6179Status) and decoded.generated.values
            elif domain is ReadDomain.FIRMWARE:
                assert decoded.generated.body.text == "3.02.24"
            elif domain is ReadDomain.HARDWARE:
                assert decoded.generated.body.text == ("3.02.01" if model == "H6199" else "3.01.01")


@pytest.mark.parametrize(("model", "profile"), _SEGMENT_PROFILES)
def test_declared_segment_paging_matches_the_grammar_it_reads_through(model: str, profile: ModelProfile) -> None:
    """A profile can declare a page shape its status root does not read, and nothing fails
    until a device answers: the pages are discarded, segment state never leaves "optimistic",
    and every segment service then reports failure after the write has already applied."""
    pages = _segment_pages(profile)
    assert len(pages) == profile.segment_group_count > 0
    for group, page in enumerate(pages, start=1):
        result = a.parse_status_result(page, model, profile=profile)
        assert result.parsed is not None, (
            f"{model} ({profile.name}) page {group} is rejected by its {profile.status_grammar} root "
            f"({getattr(result.rejection, 'value', None)}): the profile declares "
            f"{profile.segment_count} segments at {profile.segment_group_size} a page"
        )
        body = result.parsed.body
        offset = (group - 1) * profile.segment_group_size
        meaningful = min(profile.segment_group_size, profile.segment_count - offset)
        assert int(body.num_segments) == len(body.segments) == meaningful, (
            f"{model} ({profile.name}) page {group}: root reads {body.num_segments} records "
            f"where the coordinator requires {meaningful}"
        )
        if _segment_domain_byte(profile) == 0xA2:
            assert len(body.segments) * 3 + len(body.unknown_tail) == 16
        else:
            assert len(body.segments) * 4 + len(body.unused) == 16


@pytest.mark.parametrize(("model", "profile"), _SEGMENT_PROFILES)
def test_segment_pages_reach_observed_state(hass, model: str, profile: ModelProfile) -> None:
    """The same pages, end to end through the notification path across every segment-capable
    effective profile, including runtime-qualified ceiling and strip profiles."""
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
    coordinator.profile = profile
    if profile.configured_string_counts:
        coordinator._configured_strings_confirmed = True
        coordinator._segment_query_generation = coordinator._profile_generation
    coordinator.segment_colors = [(255, 255, 255)] * profile.segment_count
    coordinator.segment_brightness = [100] * profile.segment_count
    for page in _segment_pages(profile):
        coordinator._notify_callback(None, bytearray(page))
    assert coordinator.segment_state_source == "observed", (
        f"{model} ({profile.name}) declares {profile.segment_count} segments at {profile.segment_group_size} a page, "
        f"which its {profile.status_grammar} root does not read back"
    )
    expected_colors = [(0, 0, 0)] + [(index + 1, index + 2, index + 3) for index in range(1, profile.segment_count)]
    expected_brightness = [0] + [50 + index for index in range(1, profile.segment_count)]
    assert coordinator.segment_colors == expected_colors
    if _segment_domain_byte(profile) == 0xA2:
        assert not coordinator.segment_brightness_readable
        assert coordinator.segment_brightness == [100] * profile.segment_count
    else:
        assert coordinator.segment_brightness_readable
        assert coordinator.segment_brightness == expected_brightness


def _query_builders(model: str, profile: ModelProfile) -> dict[ReadDomain, tuple[Callable[[], bytes], ...]]:
    """Every way this profile can ask for a domain, so 'claimed but never asked' or a broken
    sibling display/segment query shows up immediately."""
    display_queries: list[Callable[[], bytes]] = []
    if profile.supports_white_balance_readback:
        display_queries.append(lambda: a.build_white_balance_query(model, profile=profile))
    if profile.supports_blank_screen:
        display_queries.append(lambda: a.build_blank_screen_query(model, profile=profile))
    if profile.supports_black_border:
        display_queries.append(lambda: a.build_black_border_query(model, profile=profile))
    return {
        ReadDomain.POWER: (lambda: a.build_power_query(model, profile=profile),),
        ReadDomain.BRIGHTNESS: (lambda: a.build_brightness_query(model, profile=profile),),
        ReadDomain.COLOUR_MODE: (lambda: a.build_colour_mode_query(model, profile=profile),),
        ReadDomain.MODE: (lambda: a.build_colour_mode_query(model, profile=profile),),
        ReadDomain.FIRMWARE: (lambda: a.build_firmware_query(model, profile=profile),),
        ReadDomain.HARDWARE: (lambda: a.build_hardware_query(model, profile=profile),),
        ReadDomain.SUBORDINATE_20: (lambda: a.build_subordinate_query(0x20, model, profile=profile),),
        ReadDomain.SUBORDINATE_21: (lambda: a.build_subordinate_query(0x21, model, profile=profile),),
        ReadDomain.SEGMENTS: tuple(
            (lambda group=group: a.build_segment_query(group, model, profile=profile))
            for group in range(1, profile.segment_group_count + 1)
        ),
        ReadDomain.CONFIGURED_STRINGS: (lambda: a.build_configured_strings_query(profile),),
        ReadDomain.PHYSICAL_IC_COUNT: (lambda: a.build_physical_ic_count_query(model, profile=profile),),
        ReadDomain.DISPLAY_SETTING: tuple(display_queries),
        ReadDomain.RELATIVE_BRIGHTNESS: (lambda: a.build_relative_brightness_query(model, profile=profile),),
        ReadDomain.INSTALLATION_DIRECTION: (lambda: a.build_installation_direction_query(model, profile=profile),),
        ReadDomain.CAMERA_HEALTH: (lambda: a.build_camera_health_query(model, profile=profile),),
    }


@pytest.mark.parametrize(("model", "profile"), _STATUS_PROFILES)
def test_every_claimed_read_domain_can_actually_be_asked_for(model: str, profile: ModelProfile) -> None:
    """Every claimed read domain (and every claimed display subsetting or segment group) must
    emit a profile-authorised 20-byte frame that parses through the command grammar's query root."""
    builders = _query_builders(model, profile)
    for domain in sorted(profile.read_domains, key=lambda d: d.value):
        candidates = builders.get(domain)
        assert candidates, f"{model} ({profile.name}) claims {domain.value} but has no query builders"
        for build in candidates:
            query = build()
            assert len(query) == 20 and xor_checksum(query) == 0
            a.require_profile_packet(query, profile)
            if a.is_bulk_status_frame(query, profile):
                bulk_query = protocol_core.H60aBulk.Query.from_bytes(query)
                bulk_query._read()
                assert domain in {ReadDomain.COLOUR_MODE, ReadDomain.MODE}
                assert {item.name for item in bulk_query.domains} == a.bulk_status_domains(profile)
                continue
            parsed = protocol_core._parse_xor_frame(query, profile.command_grammar, protocol_core._STATUS_QUERY_ROOTS)
            assert parsed.rejection is None and parsed.parsed is not None, (
                f"{model} ({profile.name}) {domain.value} query rejected by {profile.command_grammar} query root"
            )
            domain_name = getattr(parsed.parsed.domain, "name", "")
            assert _STATUS_DOMAIN_NAMES.get(domain_name) is domain or (
                domain is ReadDomain.MODE and _STATUS_DOMAIN_NAMES.get(domain_name) is ReadDomain.COLOUR_MODE
            )
            if profile.outbound_transform is not None:
                wire = profile.outbound_transform(query)
                assert len(wire) == 20 and xor_checksum(wire) == 0
                if domain is ReadDomain.SEGMENTS and _segment_domain_byte(profile) == 0xA2:
                    legacy_query = protocol_core.H6125LegacySegmentQuery.from_bytes(wire)
                    legacy_query._read()
                    assert legacy_query.domain.name == "segments"


@pytest.mark.parametrize(("model", "profile"), _RUNTIME_STATUS_PROFILES)
def test_every_claimed_read_domain_is_consumed(hass, model: str, profile: ModelProfile) -> None:
    """Every claimed read domain must reach a handler in `coordinator._notify_callback` and
    advance both domain and field observation revisions."""
    for domain in sorted(profile.read_domains, key=lambda d: d.value):
        coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
        coordinator._client = MagicMock(is_connected=True)
        coordinator.profile = replace(profile, profile_identity_fields=frozenset())
        if profile.configured_string_counts:
            coordinator._configured_strings_confirmed = True
            coordinator._segment_query_generation = coordinator._profile_generation
        coordinator.segment_colors = [(255, 255, 255)] * profile.segment_count
        coordinator.segment_brightness = [100] * profile.segment_count
        for frame in _status_frames_for_domain(domain, model, profile):
            _consume_status(coordinator, frame)
        assert coordinator._domain_revisions.get(domain, 0) > 0, (
            f"{model} ({profile.name}) did not record receipt for {domain.value}"
        )
        assert coordinator._field_revisions or (
            domain is ReadDomain.PHYSICAL_IC_COUNT and coordinator.profile.physical_ic_count == 50
        ), f"{model} ({profile.name}) parsed {domain.value} but observed no state fields"


@pytest.mark.parametrize(("model", "profile"), _SCALAR_WHITE_BALANCE_PROFILES)
def test_scalar_white_balance_readback_has_a_typed_payload(model: str, profile: ModelProfile) -> None:
    """Declaring the scalar representation arms a reader that takes `.value` off the display
    setting payload. Where the root leaves that payload raw the reader raises AttributeError
    inside the BLE notification callback."""
    decoded = decode_status_frame(_status(0xA9, bytes([0x06, 0x01, 0x32])), model, profile=profile)
    assert decoded is not None, f"{model} cannot parse its own `aa a9 06` reply"
    payload = decoded.generated.body.payload
    assert not isinstance(payload, (bytes, bytearray)), (
        f"{model} claims scalar white-balance readback, but its {profile.status_grammar} root "
        f"leaves the setting-6 payload as raw bytes"
    )
    assert int(payload.value) == 0x32


@pytest.mark.parametrize(("model", "profile"), _COMMAND_PROFILES)
def test_every_declared_basic_command_can_be_built_and_parsed(model: str, profile: ModelProfile) -> None:
    """Every profile with a command grammar (including write-only H601C and restricted Pact 1
    profiles) must build valid, profile-authorised basic commands that round-trip through its
    command parser and outbound transform."""
    commands: list[tuple[bytes, str, object]] = [(a.build_power(True, model, profile=profile), "is_on", True)]
    if profile.command_operations is None or "brightness" in profile.command_operations:
        commands.append((a.build_brightness(50, model, profile=profile), "brightness_pct", 50))
    if profile.supports_rgb:
        commands.append((build_color_rgb(10, 20, 30, model, profile=profile), "rgb_color", (10, 20, 30)))
    if profile.supports_color_temperature:
        kelvin = profile.min_color_temp_kelvin
        commands.append((build_color_temp(kelvin, model, profile=profile), "color_temp_kelvin", kelvin))
    if profile.supports_segments:
        commands.append((build_segment_color([profile.segment_count], 10, 20, 30, model, profile=profile), "", None))
        if profile.supports_segment_brightness:
            commands.append((build_segment_brightness([profile.segment_count], 50, model, profile=profile), "", None))
        if profile.supports_segment_color_temperature:
            commands.append(
                (
                    build_segment_color_temp(
                        [profile.segment_count], profile.min_color_temp_kelvin, model, profile=profile
                    ),
                    "",
                    None,
                )
            )
    for packet, expected_field, expected_value in commands:
        assert len(packet) == 20 and xor_checksum(packet) == 0
        a.require_profile_packet(packet, profile)
        parsed = a.parse_command_result(packet, model, profile=profile)
        assert parsed.rejection is None and parsed.parsed is not None
        if expected_field:
            expectations = expectations_from_packet(
                packet, model, static_echoes_color=profile.static_readback_echoes_color, profile=profile
            )
            assert expectations[expected_field] == expected_value
        if profile.outbound_transform is not None:
            wire = profile.outbound_transform(packet)
            assert len(wire) == 20 and xor_checksum(wire) == 0


@pytest.mark.parametrize(("model", "profile"), _VIDEO_PROFILES)
def test_every_declared_video_mode_can_be_built(hass, model: str, profile: ModelProfile) -> None:
    """Every declared video mode must build a profile-authorised command that parses through
    the selected grammar, produces the matching video_mode expectation, and (where colour-mode
    readback is supported) decodes back from its status root."""
    assert profile.video_modes, f"{model} claims video mode without naming any"
    values = (
        {"picture_preset": next(iter(protocol_core.H66a0VideoCommand.PicturePreset.__members__)), "opaque": 0}
        if profile.video_grammar == "H66A0-video"
        else {}
    )
    saturation = max(50, profile.video_saturation_min)
    for mode in profile.video_modes:
        frame = a.build_video_mode(mode, True, saturation, False, 50, model, values=values, profile=profile)
        assert len(frame) == 20 and xor_checksum(frame) == 0
        a.require_profile_packet(frame, profile)
        if profile.video_grammar == "H66A0-video":
            assert a.parse_video_command(frame, model, profile=profile) is not None
        else:
            parsed = a.parse_command_result(frame, model, profile=profile)
            assert parsed.rejection is None and parsed.parsed is not None
        assert expectations_from_packet(frame, model, profile=profile)["video_mode"] == mode
        if profile.supports_color_mode_readback:
            color_mode_enum = _status_color_mode_enum(profile)
            video_byte = int(color_mode_enum.video)
            if profile.video_grammar == "H66A0-video":
                source_code = int(protocol_core.H66a0VideoCommand.VideoSource[mode])
                preset_code = int(protocol_core.H66a0VideoCommand.PicturePreset[values["picture_preset"]])
                body = bytes([video_byte, source_code, preset_code, saturation, 1, int(values["opaque"]), 50])
            else:
                assert profile.command_grammar is not None
                video_root = protocol_core._COMMAND_ROOTS[profile.command_grammar][1]
                source_code = int(video_root.VideoSource[mode])
                region_code = int(video_root.VideoRegion.all)
                body = (
                    bytes([video_byte, source_code, region_code, saturation, 1, 2, 50])
                    if profile.video_grammar == "H6099"
                    else bytes([video_byte, region_code, source_code, saturation, 1, 50])
                )
            reply = _status(0x05, body)
            decoded = decode_status_frame(reply, model, profile=profile)
            assert decoded is not None
            parsed_reply = parse_color_mode(decoded.generated, model, profile=profile)
            assert parsed_reply.mode is ParsedMode.VIDEO and parsed_reply.video_mode == mode
            coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
            coordinator.profile = replace(profile, profile_identity_fields=frozenset())
            coordinator._notify_callback(None, bytearray(reply))
            assert coordinator.color_mode is ParsedMode.VIDEO and coordinator.video_mode == mode


def _needs_ic_context(profile: ModelProfile) -> bool:
    return profile.physical_ic_count is None and any(
        variant.requires_physical_ic_count or any(spec.requires_physical_ic_count for spec in variant.parameters)
        for variant in profile.music_variants
    )


@pytest.mark.parametrize(("model", "profile"), _MUSIC_PROFILES)
def test_every_advertised_music_mode_has_a_way_to_be_applied(model: str, profile: ModelProfile) -> None:
    """Every advertised music mode must produce valid power, selector, and (when available)
    companion upload packets that round-trip through their selected Kaitai codecs."""
    contexts = (profile, replace(profile, physical_ic_count=60)) if _needs_ic_context(profile) else (profile,)
    for active_profile in contexts:
        for slug in active_profile.music_modes:
            mode_code = music_code_for(model, slug, profile=active_profile)
            variant = music_variant(active_profile, mode_code)
            available = variant is not None and music_parameters_available(active_profile, variant)
            include = bool(variant and (variant.template or variant.supports_style) and available)
            packets = prepare_music_request(
                model, slug, 50, None, False, {}, include_parameters=include, profile=active_profile
            )
            writes = prepare_music_profile_writes(
                model, slug, 50, None, False, {}, include_parameters=include, profile=active_profile
            )
            assert packets and tuple(packet for packet, _ in writes) == packets
            for packet in packets:
                assert len(packet) == 20 and xor_checksum(packet) == 0
                a.require_profile_packet(packet, active_profile)
            selector_index = len(packets) - 1 if active_profile.music_upload_before_selector else 1
            selector = packets[selector_index]
            assert writes[selector_index][1]["music_mode"] == slug
            parsed_cmd = a.parse_command_result(selector, model, profile=active_profile)
            assert parsed_cmd.rejection is None and parsed_cmd.parsed is not None
            assert expectations_from_packet(selector, model, profile=active_profile)["music_mode"] == slug
            if active_profile.music_grammar == "H6076":
                assert parsed_cmd.parsed.selector.mode_id.name == slug
            elif active_profile.music_grammar == "H7025":
                assert parsed_cmd.parsed.selector.mode_id.name == slug
            if active_profile.outbound_transform is not None:
                wire = active_profile.outbound_transform(selector)
                assert len(wire) == 20 and xor_checksum(wire) == 0
                if model == "H6125":
                    parsed_wire = protocol_core.H6125WireWrite.from_bytes(wire)
                    parsed_wire._read()
                    assert parsed_wire.body.sub_body.mode_id.name == slug
            if variant is not None and variant.template and available:
                assert len(packets) > 2, f"{model} music mode {slug} carries a template but sends no upload"
                upload = packets[1:-1] if active_profile.music_upload_before_selector else packets[2:]
                assert all(frame[0] == 0xA3 for frame in upload)
                envelope = reassemble_a3(list(upload))
                assert envelope[2] == 0x41
                companion_index = len(packets) - 2 if active_profile.music_upload_before_selector else len(packets) - 1
                mode_name, body = writes[companion_index][1]["_music_body"]
                assert mode_name == slug
                parsed_body = protocol_music_params.parse_music_parameters(variant, body)
                assert int(parsed_body.mode) == variant.mode_code
                assert envelope[3:] == body.ljust(len(envelope) - 3, b"\x00")


def test_the_parameter_write_table_agrees_with_the_profiles_it_gates() -> None:
    """`music_mode_has_parameter_write` decides whether a mode's `a3 00` upload is sent at all,
    and `variant.template` is what holds the payload. Both the advertised mode roster and the
    declared variant list must agree with the parameter-write gate."""
    for _, model, profile in _EFFECTIVE_PROFILES:
        if not profile.music_modes:
            continue
        for slug in profile.music_modes:
            code = music_code_for(model, slug, profile=profile)
            variant = music_variant(profile, code)
            gated = music_mode_has_parameter_write(model, code, profile=profile)
            has_template = bool(variant and variant.template)
            assert gated == has_template, (
                f"{model} ({profile.name}) mode {slug} (0x{code:02x}): parameter-write gate says {gated} "
                f"but variant template is {has_template}"
            )
        for variant in profile.music_variants:
            gated = music_mode_has_parameter_write(model, variant.mode_code, profile=profile)
            assert gated == bool(variant.template), (
                f"{model} ({profile.name}) mode 0x{variant.mode_code:02x}: parameter-write gate says {gated} "
                f"but the variant {'carries' if variant.template else 'has'} "
                f"{'a' if variant.template else 'no'} template"
            )


@pytest.mark.parametrize(("model", "profile"), _MUSIC_READBACK_PROFILES)
def test_every_advertised_music_mode_resolves_from_status_reply(hass, model: str, profile: ModelProfile) -> None:
    """Every music mode advertised by a colour-mode-readable profile must resolve back from
    its status root's Kaitai enum through `decode_status_frame`, `parse_color_mode`, and
    `coordinator._notify_callback`, while unadvertised or unknown codes fail closed."""
    color_mode_enum = _status_color_mode_enum(profile)
    status_music_enum = _status_music_enum(profile)
    music_byte = int(color_mode_enum.music)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
    coordinator.profile = replace(profile, profile_identity_fields=frozenset())
    readable_modes = profile.readback_music_modes or profile.music_modes

    for slug in readable_modes:
        assert slug in status_music_enum.__members__, (
            f"{model} ({profile.name}) advertises {slug!r} but {profile.status_grammar} Kaitai enum lacks it"
        )
        status_code = int(status_music_enum[slug])
        reply = _status(0x05, bytes([music_byte, status_code, 50]))
        decoded = decode_status_frame(reply, model, profile=profile)
        assert decoded is not None
        parsed = parse_color_mode(decoded.generated, model, profile=profile)
        assert parsed.mode is ParsedMode.MUSIC
        assert parsed.music_mode == slug
        assert parsed.music_sensitivity == 50
        coordinator._notify_callback(None, bytearray(reply))
        assert coordinator.color_mode is ParsedMode.MUSIC
        assert coordinator.music_mode == slug
        assert coordinator.music_sensitivity == 50

    prior_mode = coordinator.music_mode
    rejected_codes = [int(member) for member in status_music_enum if member.name not in readable_modes] + [0x7F]
    for bad_code in rejected_codes:
        bad_reply = _status(0x05, bytes([music_byte, bad_code, 50]))
        coordinator._notify_callback(None, bytearray(bad_reply))
        assert coordinator.packet_log[-1]["reason"] == "semantic_rejected"
        assert coordinator.music_mode == prior_mode


@pytest.mark.parametrize(("model", "profile"), _SCENE_PROFILES)
def test_every_supported_scene_round_trips_between_command_and_status(hass, model: str, profile: ModelProfile) -> None:
    """Supported scenes must resolve uniquely by selector code, build valid commands with
    matching expectations, and (where colour-mode readback is supported) decode back to the
    same scene key while unsupported scene codes fail closed or remain unknown."""
    assert profile.scene_catalogue_sku is not None and profile.scene_catalogue_sku in MODEL_SCENES
    root_type = _status_root_type(profile) if profile.status_grammar is not None else None
    if root_type is not None and hasattr(root_type, "SceneMode") and profile.scene_codes is not None:
        assert profile.scene_codes == {int(scene) for scene in root_type.SceneMode}

    catalogue = MODEL_SCENES[profile.scene_catalogue_sku]
    supported = [(key, scene) for key, scene in catalogue.items() if scene_supported(scene, profile)]
    unsupported = [(key, scene) for key, scene in catalogue.items() if not scene_supported(scene, profile)]
    assert supported, f"{model} ({profile.name}) claims scenes but supports none"

    for key, scene in supported:
        selector = scene_selector_code(model, scene, profile=profile)
        assert scene_key_for_code(model, selector, profile=profile) == key

    sampled: list[tuple[str, SceneEntry]] = [supported[0], supported[-1]]
    for candidate in supported:
        if candidate[1].selector_only and candidate not in sampled:
            sampled.append(candidate)
            break
    for candidate in supported:
        if not candidate[1].selector_only and candidate not in sampled:
            sampled.append(candidate)
            break

    for key, scene in sampled:
        selector = scene_selector_code(model, scene, profile=profile)
        packets = build_native_scene_packets(model, scene, profile=profile)
        assert packets
        for packet in packets:
            assert 4 <= len(packet) <= 20 if packet[:1] == b"\xa4" else len(packet) == 20
            assert xor_checksum(packet) == 0
            a.require_profile_packet(packet, profile)
        activation = packets[-1]
        assert expectations_from_packet(activation, model, profile=profile) == {
            "color_mode": (ParsedMode.SCENE, None),
            "scene_code": selector,
            "effect": key,
            "unknown_scene_code": None,
        }
        if profile.supports_color_mode_readback:
            color_mode_enum = _status_color_mode_enum(profile)
            scene_bytes = (
                bytes([selector]) if profile.status_grammar == "H6125-legacy" else selector.to_bytes(2, "little")
            )
            reply = _status(0x05, bytes([int(color_mode_enum.scene)]) + scene_bytes, profile=profile)
            decoded = decode_status_frame(reply, model, profile=profile)
            assert decoded is not None
            parsed = parse_color_mode(decoded.generated, model, profile=profile)
            assert parsed.mode is ParsedMode.SCENE and parsed.effect == key and parsed.scene_code == selector
            coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
            coordinator.profile = replace(profile, profile_identity_fields=frozenset())
            _consume_status(coordinator, reply)
            assert coordinator.color_mode is ParsedMode.SCENE
            assert coordinator.effect == key
            assert coordinator._scene_code == selector

    if unsupported:
        _, rejected_scene = unsupported[0]
        with pytest.raises(ValueError, match="not supported"):
            build_native_scene_packets(model, rejected_scene, profile=profile)

    if profile.supports_color_mode_readback:
        color_mode_enum = _status_color_mode_enum(profile)
        unknown_code = 0xFE if profile.status_grammar == "H6125-legacy" else 0x7FFE
        unknown_bytes = (
            bytes([unknown_code]) if profile.status_grammar == "H6125-legacy" else unknown_code.to_bytes(2, "little")
        )
        unknown_reply = _status(0x05, bytes([int(color_mode_enum.scene)]) + unknown_bytes, profile=profile)
        coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
        coordinator.profile = replace(profile, profile_identity_fields=frozenset())
        _consume_status(coordinator, unknown_reply)
        assert coordinator.color_mode is ParsedMode.SCENE
        assert coordinator.effect is None
        assert coordinator._scene_code == unknown_code


@pytest.mark.parametrize(("model", "profile"), _DIY_PROFILES)
def test_diy_commands_and_status_readback(hass, model: str, profile: ModelProfile) -> None:
    """Profiles with DIY-code activation/readback must build valid DIY activation commands
    and decode DIY status replies back to the same code."""
    diy_code = profile.a1_diy_selector or profile.advanced_diy_selector or 0x0320
    packet = a.build_diy_activation(diy_code, model, profile=profile)
    assert len(packet) == 20 and xor_checksum(packet) == 0
    a.require_profile_packet(packet, profile)
    parsed_cmd = a.parse_command_result(packet, model, profile=profile)
    assert parsed_cmd.rejection is None and parsed_cmd.parsed is not None
    assert expectations_from_packet(packet, model, profile=profile)["color_mode"] == (ParsedMode.DIY, diy_code)
    if profile.supports_color_mode_readback:
        color_mode_enum = _status_color_mode_enum(profile)
        reply = _status(0x05, bytes([int(color_mode_enum.diy)]) + diy_code.to_bytes(2, "little"), profile=profile)
        decoded = decode_status_frame(reply, model, profile=profile)
        assert decoded is not None
        parsed = parse_color_mode(decoded.generated, model, profile=profile)
        assert parsed.mode is ParsedMode.DIY and parsed.diy_code == diy_code
        coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
        coordinator.profile = replace(profile, profile_identity_fields=frozenset())
        _consume_status(coordinator, reply)
        assert coordinator.color_mode is ParsedMode.DIY and coordinator.diy_code == diy_code


@pytest.mark.parametrize(("model", "profile"), _COLOUR_MODE_READBACK_PROFILES)
def test_static_colour_and_kelvin_status_readback(hass, model: str, profile: ModelProfile) -> None:
    """Profiles with colour-mode readback must decode static colour replies and enforce
    their declared Kelvin bounds on static temperature readback."""
    color_mode_enum = _status_color_mode_enum(profile)
    static_byte = int(getattr(color_mode_enum, "static", getattr(color_mode_enum, "static_colour", None)))
    if profile.status_grammar in {"H601C", "H6179"}:
        rgb_body = bytes([static_byte, 10, 20, 30, 0, 0])
    else:
        rgb_body = bytes([static_byte, 0, 0, 0])
    rgb_reply = _status(0x05, rgb_body, profile=profile)
    decoded_rgb = decode_status_frame(rgb_reply, model, profile=profile)
    assert decoded_rgb is not None
    parsed_rgb = parse_color_mode(decoded_rgb.generated, model, profile=profile)
    assert parsed_rgb.mode is ParsedMode.COLOUR
    if profile.static_readback_echoes_color:
        assert parsed_rgb.rgb_color == (10, 20, 30)

    if profile.static_readback_kelvin:
        coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
        coordinator.profile = replace(profile, profile_identity_fields=frozenset())
        min_kelvin = profile.readback_min_color_temp_kelvin or profile.min_color_temp_kelvin
        for kelvin in (min_kelvin, profile.max_color_temp_kelvin):
            kelvin_bytes = kelvin.to_bytes(2, "big")
            body = (
                bytes([static_byte, 255, 255, 255]) + kelvin_bytes
                if profile.status_grammar in {"H601C", "H6179"}
                else bytes([static_byte, 1]) + kelvin_bytes
            )
            reply = _status(0x05, body)
            decoded = decode_status_frame(reply, model, profile=profile)
            assert decoded is not None
            parsed = parse_color_mode(decoded.generated, model, profile=profile)
            assert parsed.mode is ParsedMode.COLOUR and parsed.color_temp_kelvin == kelvin
            coordinator._notify_callback(None, bytearray(reply))
            assert coordinator.color_mode is ParsedMode.COLOUR and coordinator.color_temp_kelvin == kelvin

        for out_of_range in (min_kelvin - 1, profile.max_color_temp_kelvin + 1):
            bad_bytes = out_of_range.to_bytes(2, "big")
            bad_body = (
                bytes([static_byte, 255, 255, 255]) + bad_bytes
                if profile.status_grammar in {"H601C", "H6179"}
                else bytes([static_byte, 1]) + bad_bytes
            )
            bad_reply = _status(0x05, bad_body)
            coordinator._notify_callback(None, bytearray(bad_reply))
            assert coordinator.packet_log[-1]["reason"] == "semantic_rejected"


@pytest.mark.parametrize(("model", "profile"), _BOOLEAN_CONTROL_PROFILES)
def test_declared_boolean_controls_round_trip(hass, model: str, profile: ModelProfile) -> None:
    """Every declared boolean control must build valid write and query frames and decode
    authorised status register replies while rejecting invalid flag values."""
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="http://x")
    coordinator.profile = replace(profile, profile_identity_fields=frozenset())
    for control in sorted(profile.boolean_controls):
        query = a.build_boolean_control_query(control, model, profile=profile)
        assert len(query) == 20 and xor_checksum(query) == 0
        a.require_profile_packet(query, profile)
        domain_byte = query[1]
        for enabled in (False, True):
            cmd = a.build_boolean_control(control, enabled, model, profile=profile)
            assert len(cmd) == 20 and xor_checksum(cmd) == 0
            a.require_profile_packet(cmd, profile)
            if profile.setting_grammar == "H60A6":
                reply = _xor(b"\xee\x30\x01\x00" + bytes([int(enabled), int(enabled)]) + bytes(13))
                result = a.parse_zone_notification(reply, profile)
                assert result.parsed is not None and result.rejection is None
                assert getattr(result.parsed, control) is enabled
                _consume_status(coordinator, reply)
                assert coordinator.boolean_control_state[control] is enabled
                assert coordinator._field_revisions[f"boolean_{control}"] > 0
                continue
            reply = _status(domain_byte, bytes([int(enabled)]))
            decoded = decode_status_frame(reply, model, profile=profile)
            assert decoded is not None and status_is_authorized(decoded, profile)
            assert a.parse_boolean_control(decoded.generated, model, profile=profile) == {control: enabled}
            coordinator._notify_callback(None, bytearray(reply))
            assert coordinator.boolean_control_state[control] is enabled
            assert coordinator._field_revisions[f"boolean_{control}"] > 0

        bad_reply = (
            _xor(b"\xee\x30\x02" + bytes(16)) if profile.setting_grammar == "H60A6" else _status(domain_byte, b"\x02")
        )
        coordinator._notify_callback(None, bytearray(bad_reply))
        assert coordinator.packet_log[-1]["reason"] in {"schema_rejected", "semantic_rejected"}
        assert coordinator.boolean_control_state[control] is True
