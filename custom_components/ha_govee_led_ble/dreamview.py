"""DreamView group model: members, Area Config and the readers for the `0x60` register.

The vendor calls this "Feast" internally. A sync centre HOLDS a group of sub-devices and drives
them; membership and per-member Area Config are written as one `0xa3` upload and are never read
back, so a group deleted from here cannot be rebuilt from here.

Wire STRUCTURE lives in tools/ble/kaitai/command_write.ksy::dreamview_cmd and its builders in
generated_protocol_adapter. What is here is the group model that upload serialises, and the two
readers for registers whose replies are a digest rather than a modelled body.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .transport import fragment_a3

# The `aa` status header, for the two 0x60 replies read here as raw bodies.
STATUS_HEADER = 0xAA

DREAMVIEW_PACKET_TYPE = 0x60
DREAMVIEW_SUB_SWITCH = 0x01
DREAMVIEW_SUB_DEVICE_BRIGHTNESS = 0x03
DREAMVIEW_SUB_BRIGHTNESS_UNITE = 0x04
DREAMVIEW_SUB_SUBDEVICE = 0x05
DREAMVIEW_SUB_SATURATION = 0x09
DREAMVIEW_SUB_GET_COLOR = 0x0A
DREAMVIEW_SUB_SOUND = 0x0B
DREAMVIEW_SUB_DIGEST = 0x0C

DREAMVIEW_GROUP_TYPE = 0x50  # MultiSetSubDeviceController4MovieFeastV2.getCommandType()

# `cmdVer` is a CLOUD field, and we have no cloud. Both sub-devices in the only capture of this
# command reported 11, so that is what this defaults to -- an observed value, not a derived one.
# It is exposed as a parameter so a device that disagrees can be corrected without a code change.
DREAMVIEW_DEFAULT_CMD_VER = 0x0B

# A zone whose switchConfig is off is written as 0xFF rather than omitted, so the zone count and
# the entry length stay fixed however many zones are disabled.
DREAMVIEW_ZONE_DISABLED = 0xFF

# Which screen region a zone samples. The app's Area Config page has TWENTY cells around the
# screen (the shrink/expand panel pair) and stores the picked cell as `Z + 1`, i.e. 1..20 -- but
# Constant.getIndex4Portocol folds 1..10 and 11..20 onto the SAME ten protocol regions before the
# byte reaches the wire, and returns 0 for anything else. So the wire only ever carries 0..10.
#
# 0 is UNASSIGNED, not "region zero": the app writes areaConfigs[i] = 0 together with
# switchConfigs[i] = 0 when a zone is cleared, and defaults a new device's areaConfigs to zeros.
DREAMVIEW_REGION_UNASSIGNED = 0
DREAMVIEW_REGION_MAX = 10


@dataclass(frozen=True)
class DreamviewMember:
    """One sub-device in a DreamView group, with its per-zone Area Config.

    `address` is the ordinary display form (`AA:BB:CC:DD:EE:FF`) and is written in reverse
    byte order, as verified against captured group and handshake traffic.

    `zones` is one entry per zone, in zone order:

      * ``1..10`` -- the screen region that zone samples (the app's areaConfigs).
      * ``0``     -- assigned to no region. This is the app's own default for a new device.
      * ``None``  -- the zone is switched OFF (the app's switchConfigs), written as 0xFF.

    The app's Area Config page shows twenty cells, but folds them onto these ten before writing,
    so 1..10 is the whole range the wire ever carries.
    """

    address: str
    zones: tuple[int | None, ...]
    is_rgbic: bool = True
    cmd_ver: int = DREAMVIEW_DEFAULT_CMD_VER

    def __post_init__(self) -> None:
        if not _MAC_RE.fullmatch(self.address):
            raise ValueError(f"address must be AA:BB:CC:DD:EE:FF, got {self.address!r}")
        if not 1 <= len(self.zones) <= 255:
            raise ValueError(f"a member needs 1..255 zones, got {len(self.zones)}")
        for zone in self.zones:
            if zone is None:
                continue
            if not DREAMVIEW_REGION_UNASSIGNED <= zone <= DREAMVIEW_REGION_MAX:
                raise ValueError(
                    f"zone region must be 0..{DREAMVIEW_REGION_MAX} (0 = unassigned) or None to "
                    f"disable the zone, got {zone}"
                )
        if not 0 <= self.cmd_ver <= 0xFF:
            raise ValueError(f"cmd_ver must be a byte, got {self.cmd_ver}")

    def to_bytes(self) -> bytes:
        """Encode one Area4Device.j() entry."""
        mac = bytes(int(part, 16) for part in self.address.split(":"))
        return bytes(
            [
                1 if self.is_rgbic else 0,
                0,  # the app's marker bit: 0 when a BLE address is present, 1 when it sends a name
                self.cmd_ver,
                *reversed(mac),
                len(self.zones),
                *(DREAMVIEW_ZONE_DISABLED if z is None else z for z in self.zones),
            ]
        )


@dataclass(frozen=True)
class DreamviewState:
    """What a sync centre will tell us about its own DreamView group.

    Assembled from two reads, because no single one answers everything:

      * `aa 60 0c` -- a digest of the group's SETTINGS in one frame.
      * `aa 60 05` -- one byte per sub-device SLOT, its connection state.

    Same-brightness is deliberately absent: it has its own read, `aa 60 04`, and the digest byte
    that looked like it demonstrably is not (see parse_dreamview_digest).

    `member_states` is the honest limit of this. The device reports a state per slot but never
    the addresses behind them: the vendor app knows who is in the group because its CLOUD
    account told it, and indexes these bytes against that list. So we can say how many
    sub-devices a group holds and whether each is connected, and we cannot say which devices
    they are. A group created in the app is therefore VISIBLE to us but not enumerable.
    """

    is_on: bool | None = None
    brightness: int | None = None
    saturation: int | None = None
    sound_effects: bool | None = None
    # The 0x0a "get colour mode" selector -- the app's All/Part choice. Reported as the raw byte
    # because only the values 0 and 1 have been observed and neither has been tied to a label.
    colour_mode: int | None = None
    sound_effects_softness: int | None = None
    member_states: tuple[int, ...] = ()

    @property
    def member_count(self) -> int:
        """How many sub-device slots report a non-zero state."""
        return sum(1 for state in self.member_states if state)

    @property
    def has_group(self) -> bool:
        """Whether any sub-device is currently connected -- NOT whether a group exists.

        The distinction became real once `33 60 05` was identified: a member can be
        DISCONNECTED from the sync centre (state 0) while remaining a member, with its Area
        Config and brightness intact. A group whose members are all disconnected therefore
        reports False here even though deleting it would still destroy something.

        So treat True as proof a group exists and False as "no member is connected right now".
        `aa 60 03` is the second signal -- its length tracked membership across a delete in the
        2026-08-27 live run -- and is the read to reach for before concluding a group is absent.
        """
        return self.member_count > 0


def parse_dreamview_digest(frame: bytes) -> DreamviewState:
    """Parse `aa 60 0c`, which returns the group's settings in one frame.

    Field order is correlated against the individual reads and writes in the same capture, not
    assumed. Two digests were taken, before and after the owner changed things:

        01 64 32 00 00 01 35        01 34 3b 01 01 01 37

      * [1] 0x64 -> 0x34 tracks `aa 60 03`, which answered 0x64 then `34 51 44`.
      * [2] 0x32 -> 0x3b tracks the saturation writes (`33 60 09`).
      * [3] 0x00 -> 0x01 tracks sound effects being switched on (`33 60 0b 01 ..`).
      * [4] 0x00 -> 0x01 appears only after the two `33 60 0a` colour-mode writes.
      * [6] 0x35 -> 0x37 matches the LAST softness written before the second digest,
            `33 60 0b 01 37`.

    Byte [5] is 0x01 in both snapshots and is NOT the same-brightness toggle: `aa 60 04` read
    0x01 at the first digest, and same-brightness was switched OFF (`33 60 04 00`) before the
    second, yet [5] stayed 0x01. It is left unnamed rather than guessed; read `aa 60 04` for the
    real same-brightness state.
    """
    body = _dreamview_reply_body(frame, DREAMVIEW_SUB_DIGEST, minimum=7)
    return DreamviewState(
        is_on=bool(body[0]),
        brightness=body[1],
        saturation=body[2],
        sound_effects=bool(body[3]),
        colour_mode=body[4],
        sound_effects_softness=body[6],
    )


def parse_dreamview_members(frame: bytes) -> tuple[int, ...]:
    """Parse `aa 60 05` into one connection state per sub-device slot.

    Ten slots, matching the app's own maximum. Trailing zero slots are kept rather than trimmed,
    so the index of a state is the index of its sub-device.
    """
    body = _dreamview_reply_body(frame, DREAMVIEW_SUB_SUBDEVICE, minimum=10)
    return tuple(body[:10])


def _dreamview_reply_body(frame: bytes, sub: int, *, minimum: int) -> bytes:
    """Validate a `aa 60 <sub>` reply and return its payload.

    Checks the sub-command byte as well as the header, because every DreamView reply shares the
    same first two bytes and reading one as another would silently produce plausible nonsense.
    """
    if len(frame) != 20:
        raise ValueError(f"a Govee frame is 20 bytes, got {len(frame)}")
    if frame[0] != STATUS_HEADER or frame[1] != DREAMVIEW_PACKET_TYPE:
        raise ValueError(f"not a DreamView reply: {frame[:2].hex()}")
    if frame[2] != sub:
        raise ValueError(f"expected DreamView sub 0x{sub:02x}, got 0x{frame[2]:02x}")
    body = frame[3:19]
    if len(body) < minimum:
        raise ValueError(f"DreamView sub 0x{sub:02x} needs {minimum} payload bytes")
    return body


def build_dreamview_group(members: Sequence[DreamviewMember]) -> list[bytes]:
    """Build the `0xa3` upload that sets a DreamView group's membership and Area Config.

    THIS IS NOT READ-BACKABLE. No query returns group membership, so this write cannot be
    verified against the device afterwards and a previous group cannot be recovered from it.

    An empty `members` is rejected rather than treated as "remove everyone": the app's own
    makeSubDeviceBytes returns null for an empty list, so an empty upload is not a form the
    firmware has been shown to accept. Use build_dreamview_delete for removal.
    """
    if not members:
        raise ValueError("a DreamView group needs at least one member; use build_dreamview_delete to remove one")
    if len(members) > 10:
        # The app's Constant.maxSubDeviceNum caps this per model at 5, 7 or 10 by cloud lookup.
        # 10 is the largest of those, so it is the only bound we can enforce without the cloud.
        raise ValueError(f"at most 10 sub-devices, got {len(members)}")
    seen: set[str] = set()
    for member in members:
        key = member.address.upper()
        if key in seen:
            raise ValueError(f"{member.address} appears twice in the group")
        seen.add(key)
    body = bytes([len(members)]) + b"".join(member.to_bytes() for member in members)
    return fragment_a3(DREAMVIEW_GROUP_TYPE, body)


_MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
