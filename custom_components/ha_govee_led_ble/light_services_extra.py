"""Services for the features this project added: video settings and DreamView.

Kept out of :mod:`light_services` so that file stays what it was -- the segment and mode
services -- and gains only the extra mixin in the light's bases.

Built on :class:`_GoveeLightOwner`, the same typed surface :class:`_GoveeLightServicesMixin`
uses, so this composes the way the existing mixin does rather than introducing a second pattern.
Each service checks the model profile first and raises a clear error rather than writing a frame
a device cannot answer.
"""

from __future__ import annotations

from typing import Any

from .const import ReadDomain
from .dreamview import DreamviewMember
from .light_services import _GoveeLightOwner


class _GoveeExtraServicesMixin(_GoveeLightOwner):
    """Video-settings and DreamView services."""

    async def async_set_video_settings(
        self,
        game_mode: bool | None = None,
        picture_preset: str | None = None,
        saturation: int | None = None,
        sound_effects: bool | None = None,
        sound_effects_softness: int | None = None,
    ) -> None:
        """The H66A0 family's video sheet, as one frame.

        Deliberately a service rather than entities. In the vendor app these live on one
        screen, but on the wire they are one body among four unrelated registers, and giving
        each its own entity would put five controls on a dashboard that only mean anything
        while the device is in video mode. Scripting reaches them; a dashboard does not have
        to carry them.

        Every field is optional and anything omitted keeps the device's current value.

        Relative brightness is NOT part of this frame -- it is its own command, and its own
        entities.
        """
        self._require_support(
            "set_video_settings",
            supported=self.coordinator.profile.supports_video_mode
            and self.coordinator.profile.video_grammar == "H66A0",
        )
        await self.coordinator.async_enter_video_mode(
            game_mode=game_mode,
            picture_preset=picture_preset,
            saturation=saturation,
            sound_effects=sound_effects,
            sound_effects_softness=sound_effects_softness,
        )

    async def async_get_dreamview_candidates(self) -> dict[str, Any]:
        """List the devices that could join this sync centre's DreamView group.

        Returns a response rather than setting state, so the flow mirrors the app: look at what
        is available, choose who is in, then write the group.
        """
        self._require_support(
            "get_dreamview_candidates",
            supported=self.coordinator.profile.supports_dreamview,
        )
        return {"candidates": self.coordinator.dreamview_candidates}

    async def async_read_dreamview_group(self) -> dict[str, Any]:
        """Report the DreamView group this device is holding, if any.

        The device reports how many slots are occupied and how each is connecting, never who is
        in them.
        `identified_members` is filled in once identify_dreamview_members has worked the mapping
        out by observation, and `members_are_anonymous` reports whether that has happened.
        """
        self._require_support(
            "read_dreamview_group",
            supported=self.coordinator.profile.supports_dreamview,
        )
        state = await self.coordinator.async_read_dreamview_state()
        learned = self.coordinator.dreamview_members
        return {
            "has_group": state.has_group,
            "member_count": state.member_count,
            "member_states": list(state.member_states),
            # The DEVICE still never reports addresses. What can be offered is a mapping learned
            # by identify_dreamview_members, which is why this is no longer a flat "anonymous".
            "members_are_anonymous": not learned,
            "identified_members": learned,
            "is_on": state.is_on,
            "brightness": state.brightness,
            "saturation": state.saturation,
            "sound_effects": state.sound_effects,
            "sound_effects_softness": state.sound_effects_softness,
            "colour_mode": state.colour_mode,
        }

    async def async_identify_dreamview_members(self, settle: float = 30.0) -> dict[str, Any]:
        """Work out which device is in each DreamView slot, and remember it.

        The device will not say, so this finds out the only way available: disconnect one slot
        at a time and see which device starts advertising. Membership, Area Config and every
        per-member setting are untouched, and each slot is reconnected immediately.

        Expect the lights to drop out and return, one at a time, for up to `settle` seconds each.
        The answer is stored on the config entry, so this is paid once.
        """
        self._require_support(
            "identify_dreamview_members",
            supported=self.coordinator.profile.supports_dreamview,
        )
        return await self.coordinator.async_identify_dreamview_members(settle=settle)

    async def async_set_dreamview_group(self, members: list[dict[str, Any]]) -> None:
        """Set who is in the DreamView group, and how the video is sampled for each of them.

        `members` is the full membership: a device listed with `enabled: false` is simply left
        out of the upload, which is what the app's toggle does. That means this service is a
        REPLACE, not a merge -- anyone omitted stops being a member.

        `zones` is REQUIRED, one entry per DreamView zone, in zone order: `1..10` for the screen
        region that zone samples, `0` for a zone assigned to no region, `null` to switch the zone
        off. It is required because a DreamView zone count cannot be derived from anything this
        integration can read -- see below.

        A ZONE COUNT IS NOT A SEGMENT COUNT. This method used to fall back to the device's own
        reported segment count when `zones` was omitted, and that was wrong: the app's `areaNum`
        is how DreamView divides a strip for video sampling, which is a different quantity from
        how many addressable LED segments the strip has. Measured 2026-08-31 against the owner's
        Area Config page: an H1A42 and an H61F5 that both report `segment_count=5` each carry
        SIX DreamView zones. The 2026-08-26 group-creation capture agrees -- both of its members
        carry six zone bytes. The old fallback would therefore have written a five-zone Area
        Config to six-zone devices.

        That failure could not be caught afterwards: the zone count is never reported over BLE,
        this upload has no read-back, and deleting the group is the only recovery. The count is
        therefore required from the caller rather than guessed.
        """
        self._require_support(
            "set_dreamview_group",
            supported=self.coordinator.profile.supports_dreamview,
        )
        resolved: list[DreamviewMember] = []
        for member in members:
            if not member.get("enabled", True):
                continue
            address = str(member["address"]).upper()
            zones = member.get("zones")
            if zones is None:
                raise ValueError(
                    f"{address} needs its zones given explicitly -- a DreamView zone count is "
                    "NOT the device's LED segment count (an H1A42 and an H61F5 both reporting 5 "
                    "segments each carry 6 DreamView zones), and a zone count cannot be read "
                    "over BLE at all. Read the count off the app's Area Config page. Guessing it "
                    "would write a wrong-length Area Config that has no read-back and cannot be "
                    "undone except by deleting the group."
                )
            resolved.append(
                DreamviewMember(
                    address=address,
                    zones=tuple(None if z is None else int(z) for z in zones),
                    is_rgbic=bool(member.get("is_rgbic", True)),
                )
            )
        if not resolved:
            raise ValueError(
                "a DreamView group needs at least one enabled member; "
                "use delete_dreamview_group to remove the group entirely"
            )
        await self.coordinator.async_set_dreamview_group(resolved)

    async def async_release_ble(self, seconds: float = 120.0) -> None:
        """Hand this device's BLE link back, and stay off it for `seconds`.

        Called on the SUB-DEVICES just before a sync centre is told to build a group. A Govee
        device accepts one central at a time, so while Home Assistant holds a strip the sync
        centre cannot finish claiming it.

        Not gated on `supports_dreamview`: the device that has to let go is the member, and
        members are ordinary strips that cannot host a group themselves.
        """
        await self.coordinator.async_release_ble(seconds)

    async def async_set_dreamview_switch(self, enabled: bool) -> None:
        """Turn the DreamView group on or off.

        Separate from creating it: a freshly uploaded group exists and holds its members but is
        not necessarily running, so an activate sequence needs this as well as the upload.
        """
        self._require_support(
            "set_dreamview_switch",
            supported=self.coordinator.profile.supports_dreamview,
        )
        await self.coordinator.async_set_dreamview_switch(enabled)

    async def async_set_dreamview_member_brightness(self, index: int, brightness: int) -> None:
        """Set one group member's brightness by slot index.

        Only has a visible effect while Same Brightness is off -- see
        `set_dreamview_same_brightness`.
        """
        self._require_support(
            "set_dreamview_member_brightness",
            supported=self.coordinator.profile.supports_dreamview,
        )
        await self.coordinator.async_set_dreamview_member_brightness(index, brightness)

    async def async_set_dreamview_same_brightness(self, enabled: bool) -> None:
        """Drive every member from one brightness, or let per-member levels apply."""
        self._require_support(
            "set_dreamview_same_brightness",
            supported=self.coordinator.profile.supports_dreamview,
        )
        await self.coordinator.async_set_dreamview_same_brightness(enabled)

    async def async_set_dreamview_sound_effects(self, enabled: bool, softness: int | None = None) -> None:
        """Sound effects for the DreamView GROUP, the counterpart to set_video_settings' pair.

        Separate service rather than a field on set_video_settings, because they are different
        frames aimed at different things: `33 60 0b` configures the group the sync centre is
        driving, `33 05 ...` configures this one device's own video mode. A dashboard control
        that should follow whichever is live has to choose between them, and it can only do that
        if they are callable separately.

        `softness` is optional; omitted, the group's current value is read back and preserved.
        """
        self._require_support(
            "set_dreamview_sound_effects",
            supported=self.coordinator.profile.supports_dreamview,
        )
        await self.coordinator.async_set_dreamview_sound_effects(enabled, softness)

    async def async_delete_dreamview_group(self) -> None:
        """Remove the DreamView group this device holds, freeing its sub-devices."""
        self._require_support(
            "delete_dreamview_group",
            supported=self.coordinator.profile.supports_dreamview,
        )
        await self.coordinator.async_delete_dreamview_group()

    async def async_set_video_blank_screen(self, enabled: bool) -> None:
        """Toggle blank-screen detection, preserving its configuration."""
        self._require_support(
            "set_video_blank_screen",
            supported=self.coordinator.profile.can_read(ReadDomain.DISPLAY_SETTING),
        )
        await self.coordinator.async_set_video_blank_screen(enabled)
