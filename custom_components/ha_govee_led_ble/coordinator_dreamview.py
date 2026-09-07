"""DreamView group control for the Govee BLE coordinator.

A DreamView "sync centre" holds a group of sub-devices and drives them over BLE itself. This
module is the coordinator's side of that: reading what group a device is holding, writing one,
identifying who is in which slot, and deleting it.

Split out the way :mod:`coordinator_modes` is -- a mixin over :class:`_CoordinatorBase`, so the
concrete coordinator stays a composition of behaviours rather than one long class.

The sync centre reports per-slot state and brightness but never member addresses.
Member identity is therefore learned by observation.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth

from .const import CONF_DREAMVIEW_MEMBERS, DOMAIN
from .coordinator_base import _CoordinatorBase
from .dreamview import (
    DREAMVIEW_SUB_DIGEST,
    DREAMVIEW_SUB_SUBDEVICE,
    DreamviewState,
    build_dreamview_group,
    parse_dreamview_digest,
    parse_dreamview_members,
)
from .generated_protocol_adapter import (
    build_dreamview_brightness_unite,
    build_dreamview_delete,
    build_dreamview_device_brightness,
    build_dreamview_query,
    build_dreamview_sound_effects,
    build_dreamview_sub_device_connect,
    build_dreamview_switch,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .dreamview import DreamviewMember


class _DreamviewMixin(_CoordinatorBase):
    """Reads and writes the DreamView group a sync centre is holding."""

    @property
    def dreamview_candidates(self) -> list[dict[str, Any]]:
        """Every other Govee device this Home Assistant knows, as possible group members.

        The vendor app lists candidates from the user's cloud account. We have no cloud, so the
        equivalent local question is "which other Govee devices are configured here" -- each one
        is already a config entry with an address, a model and, once read, a segment count.

        `zones` is the device's own reported segment count where it has one, so a caller can
        accept the default rather than counting segments by hand. It is None when the device has
        not been read yet, which is honest: guessing a zone count would write an Area Config for
        zones that may not exist.

        This device is excluded from its own candidate list -- the sync centre holds the group,
        it is not a member of it.
        """
        candidates: list[dict[str, Any]] = []
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            sibling = getattr(entry, "runtime_data", None)
            if sibling is None or sibling is self:
                continue
            address = getattr(sibling, "address", None)
            if not address or address == self.address:
                continue
            segments = getattr(sibling, "segment_count", 0) or 0
            candidates.append(
                {
                    "address": address,
                    "model": getattr(sibling, "model", None),
                    "name": entry.title,
                    "zones": segments or None,
                }
            )
        candidates.sort(key=lambda item: str(item["address"]))
        return candidates

    def _require_dreamview(self, action: str) -> None:
        if not self.profile.supports_dreamview:
            raise ValueError(f"{self.model} cannot host a DreamView group ({action})")

    async def async_set_dreamview_group(self, members: Sequence[DreamviewMember]) -> None:
        """Write group membership and Area Config in one upload.

        There is no read-back for this. Nothing the device reports afterwards says who is in the
        group, so this cannot be verified and a previous group cannot be restored from it. That
        is a property of the protocol, not of this method, and it is why the delete command is
        implemented alongside rather than later.
        """
        self._require_dreamview("set group")
        cap = self.profile.dreamview_max_sub_devices
        if len(members) > cap:
            raise ValueError(f"{self.model} accepts at most {cap} DreamView sub-devices, got {len(members)}")
        async with self._control_lock:
            for frame in build_dreamview_group(members):
                await self.send_command(frame)

    async def async_set_dreamview_switch(self, on: bool) -> None:
        """Turn the DreamView group on or off (`33 60 01 {on, 1}`).

        Distinct from creating the group and from video mode. A group can exist, hold its
        members' links and still be switched off, which is the state a freshly uploaded group
        was observed in on 2026-08-31 -- so an activate sequence that only uploads membership
        leaves the group present but not running.

        Read it back as `is_on` on :meth:`async_read_dreamview_state` (digest byte [0]).
        """
        self._require_dreamview("switch group")
        async with self._control_lock:
            await self.send_command(build_dreamview_switch(on))

    async def async_set_dreamview_member_brightness(self, index: int, level: int) -> None:
        """Set ONE member's brightness, 0-100 (`33 60 03 {level, index}`).

        Per-member brightness only applies while "Same Brightness" is OFF -- the app's
        `FeastBrightnessUniteController`, :meth:`async_set_dreamview_same_brightness` here. With
        it on, the device drives every member from one level and these writes have no visible
        effect, so set that first if you want members to differ.

        Reads back through `aa 60 03`, one byte per member in slot order.
        """
        self._require_dreamview("member brightness")
        async with self._control_lock:
            await self.send_command(build_dreamview_device_brightness(level, index))

    async def async_set_dreamview_same_brightness(self, enabled: bool) -> None:
        """Drive every member from one brightness, or let them differ (`33 60 04`).

        The app calls this "Same Brightness". It gates
        :meth:`async_set_dreamview_member_brightness`, and it has its OWN read (`aa 60 04`) --
        the digest byte that looked like it demonstrably is not it, see parse_dreamview_digest.
        """
        self._require_dreamview("same brightness")
        async with self._control_lock:
            await self.send_command(build_dreamview_brightness_unite(enabled))

    async def async_set_dreamview_sound_effects(self, enabled: bool, softness: int | None = None) -> None:
        """Sound effects and their softness for the GROUP (`33 60 0b {on, softness}`).

        The group's counterpart to the per-device pair inside `set_video_settings`. The frame
        builder has been here, byte-pinned against a capture (`33600b014f...` = on, softness 79),
        since the DreamView work landed -- it was simply never given a service, so the setting
        was readable through read_dreamview_group and not writable. This closes that.

        Both fields ride in ONE frame, so `softness` cannot be omitted on the wire. When the
        caller leaves it out the group's current value is read back and re-sent, which keeps
        "toggle sound effects" from silently resetting softness to zero. If the device does not
        answer that read, the call fails rather than guessing a value.
        """
        self._require_dreamview("sound effects")
        if softness is None:
            state = await self.async_read_dreamview_state()
            softness = state.sound_effects_softness
            if softness is None:
                raise ValueError("the group did not report its current sound-effect softness; pass softness explicitly")
        async with self._control_lock:
            await self.send_command(build_dreamview_sound_effects(enabled, softness))

    async def async_read_dreamview_state(self, *, timeout: float = 2.0) -> DreamviewState:
        """Ask the device what DreamView group it is holding.

        Answers two questions and refuses to invent a third: the settings digest (`aa 60 0c`)
        and the per-slot connection states (`aa 60 05`). It cannot tell you WHICH devices are in
        the group. A group created elsewhere therefore appears as a member count and settings,
        with anonymous members until they are identified locally.

        Fields stay None when the device did not answer, rather than defaulting, so a missing
        reply is never mistaken for a real value.
        """
        self._require_dreamview("read state")
        async with self._control_lock:
            for sub in (DREAMVIEW_SUB_DIGEST, DREAMVIEW_SUB_SUBDEVICE):
                self._dreamview_frames.pop(sub, None)
                await self.send_command(build_dreamview_query(sub))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if {DREAMVIEW_SUB_DIGEST, DREAMVIEW_SUB_SUBDEVICE} <= self._dreamview_frames.keys():
                    break
                await asyncio.sleep(0.05)
        digest = self._dreamview_frames.get(DREAMVIEW_SUB_DIGEST)
        members = self._dreamview_frames.get(DREAMVIEW_SUB_SUBDEVICE)
        state = parse_dreamview_digest(digest) if digest else DreamviewState()
        if members:
            state = replace(state, member_states=parse_dreamview_members(members))
        return state

    async def async_identify_dreamview_members(self, *, settle: float = 30.0, poll: float = 1.0) -> dict[str, Any]:
        """Learn which device sits in each DreamView slot, by observation.

        No BLE command returns member addresses, and Area Config is write-only.

        What CAN be observed: a sync centre holds its sub-devices' BLE links, so a member does
        not advertise. Disconnect one slot and exactly one device starts advertising -- that is
        the device in that slot. This does that per occupied slot and reconnects it immediately,
        which touches nothing else: membership, Area Config and every per-member setting are
        left alone, unlike deleting the group.

        The mapping is stored on the config entry, because it costs a minute of the lights
        dropping in and out and should be paid once.

        Honest limits, all reported rather than hidden:
          * A slot already disconnected cannot be identified -- there is nothing to change.
          * A device that does not start advertising within `settle` is reported unresolved
            rather than guessed at.
          * Names come from other Govee config entries in this Home Assistant. A member that is
            not configured here resolves to an address with no name, which is still useful.
        """
        self._require_dreamview("identify members")
        state = await self.async_read_dreamview_state()
        known = {str(c["address"]).upper(): c for c in self.dreamview_candidates}
        results: list[dict[str, Any]] = []

        for index, slot_state in enumerate(state.member_states):
            if not slot_state:
                continue
            before = {
                address: (info.time if (info := bluetooth.async_last_service_info(self.hass, address, False)) else None)
                for address in known
            }
            marker = time.monotonic()
            await self.send_command(build_dreamview_sub_device_connect(index, False))
            found: str | None = None
            deadline = time.monotonic() + settle
            try:
                while time.monotonic() < deadline and found is None:
                    await asyncio.sleep(poll)
                    for address in known:
                        info = bluetooth.async_last_service_info(self.hass, address, False)
                        # A timestamp that advanced past the disconnect is the device waking up.
                        # Comparing against the marker rather than against "is it present" is
                        # what keeps a device that was ALREADY advertising from being claimed.
                        if info is not None and info.time > marker and before.get(address) != info.time:
                            found = address
                            break
            finally:
                # Always hand the link back, including on timeout or cancellation. Leaving a
                # member disconnected because a probe was interrupted would be a silent change
                # to the owner's group.
                await self.send_command(build_dreamview_sub_device_connect(index, True))
            record: dict[str, Any] = {"index": index, "address": found}
            if found is not None:
                record["name"] = known[found].get("name")
                record["model"] = known[found].get("model")
            else:
                record["unresolved"] = (
                    "no configured Govee device started advertising within the settle window; "
                    "it may not be added to Home Assistant, or may need longer"
                )
            results.append(record)

        learned = {str(item["index"]): item["address"] for item in results if item["address"]}
        # Persisted only when there is a config entry to persist to. `config_entry` is Optional on
        # the base coordinator, and a mapping that cannot be stored is still worth returning.
        if learned and (entry := self.config_entry) is not None:
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_DREAMVIEW_MEMBERS: learned}
            )
        return {
            "members": results,
            "member_states": list(state.member_states),
            "identified": len(learned),
        }

    @property
    def dreamview_members(self) -> dict[str, str]:
        """The slot -> address mapping learned by async_identify_dreamview_members, if any."""
        entry = self.config_entry
        stored = entry.options.get(CONF_DREAMVIEW_MEMBERS) if entry is not None else None
        return {str(k): str(v) for k, v in stored.items()} if isinstance(stored, dict) else {}

    async def async_delete_dreamview_group(self) -> None:
        """Delete the group this device holds (`33 60 0d`).

        The escape hatch for the method above. Sub-devices return to being reachable on their
        own once the group holding their links is gone.
        """
        self._require_dreamview("delete group")
        async with self._control_lock:
            await self.send_command(build_dreamview_delete())
