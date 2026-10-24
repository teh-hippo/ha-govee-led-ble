"""Service-only DreamView transactions and anonymous observations.

Like issue #257 this is a coordinator mixin, but local authorship is not a slot
identity map. It never probes members or claims membership was read back.

Ownership rules:
DreamView member devices are single-client BLE peripherals claimed directly by the sync centre after
`0x50` group upload. When `replace_dreamview_group` includes a member managed by Home Assistant,
atomically validate and persist its opaque `entry_id` ownership in
`ha_govee_led_ble.dreamview.claims`, enforce the coordinator claim barrier, disable the member
config entry, and confirm physical BLE disconnect before uploading `0x50`. Successful replacement
restores dropped members; successful deletion or sync-centre removal restores all owned members.
Persist a non-blocking restoration marker before re-enabling an entry, and remove it only after
native enabled state is durably saved so interrupted restoration resumes after restart. Native re-
enable schedules a delayed save, so the shared restoration helper flushes the native config-entry
store and independently checks its persisted state before clearing recovery intent. Preserve pre-
existing user-disabled entries unless the user explicitly re-enables them while claimed.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Callable, Mapping, Sequence
from enum import IntEnum
from typing import Any

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigEntryDisabler
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError
from homeassistant.util.json import SerializationError

from .const import DOMAIN, ModelProfile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .dreamview import (
    DREAMVIEW_READ_SETTINGS,
    DREAMVIEW_VIDEO_FIELDS,
    DreamviewMember,
    build_dreamview_command,
    build_dreamview_group,
    build_dreamview_query,
    parse_dreamview_status,
    require_dreamview,
)

DREAMVIEW_CLAIMS_DATA_KEY = "dreamview_claims"
DREAMVIEW_CLAIMS_LOCK_KEY = "dreamview_claims_lock"
_LOGGER = logging.getLogger(__name__)


class DreamviewClaimedError(BleakError):
    """A claimed member must not retry or misreport an encryption failure."""


def _claims_lock(hass: HomeAssistant) -> asyncio.Lock:
    lock: asyncio.Lock = hass.data.setdefault(DOMAIN, {}).setdefault(DREAMVIEW_CLAIMS_LOCK_KEY, asyncio.Lock())
    return lock


class _DreamviewStore(Store[dict[str, Any]]):
    """Require a completed atomic save, not Store's logged or deferred failure."""

    async def async_save(self, data: dict[str, Any]) -> None:
        if self.hass.is_stopping:
            raise OSError("DreamView persistence cannot be deferred during shutdown")
        save = self.hass.async_create_task(super().async_save(data))
        try:
            await asyncio.shield(save)
        except asyncio.CancelledError:
            await save
            raise

    async def _async_write_data(self, data: dict[str, Any]) -> None:
        try:
            await super()._async_write_data(data)
        except WriteError, SerializationError:
            # Store suppresses these two exceptions. Do not allow BLE after either,
            # or include serialized member identities in the propagated error.
            raise OSError("DreamView membership could not be persisted") from None


class _DreamviewClaimsStore(_DreamviewStore):
    """Opaque entry_id ownership journal for DreamView member handover."""


def _claims_store(hass: HomeAssistant) -> _DreamviewClaimsStore:
    return _DreamviewClaimsStore(hass, 1, f"{DOMAIN}.dreamview.claims", private=True, atomic_writes=True)


async def async_load_dreamview_claims(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if isinstance(existing := domain_data.get(DREAMVIEW_CLAIMS_DATA_KEY), dict):
        return existing
    async with _claims_lock(hass):
        if isinstance(existing := domain_data.get(DREAMVIEW_CLAIMS_DATA_KEY), dict):
            return existing
        loaded = await _claims_store(hass).async_load()
        raw_claims = (loaded or {}).get("claims", {})
        claims: dict[str, dict[str, Any]] = {
            str(entry_id): dict(claim)
            for entry_id, claim in raw_claims.items()
            if isinstance(entry_id, str) and isinstance(claim, Mapping)
        }
        domain_data[DREAMVIEW_CLAIMS_DATA_KEY] = claims
        return claims


async def _async_save_dreamview_claims(hass: HomeAssistant, claims: Mapping[str, Mapping[str, Any]]) -> None:
    """Save a snapshot while the caller holds the claims transaction lock."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    snapshot = {str(entry_id): dict(claim) for entry_id, claim in claims.items()}

    async def persist() -> None:
        await _claims_store(hass).async_save({"claims": copy.deepcopy(snapshot)})
        domain_data[DREAMVIEW_CLAIMS_DATA_KEY] = snapshot

    save = hass.async_create_task(persist())
    try:
        await asyncio.shield(save)
    except asyncio.CancelledError:
        await save
        raise


async def _async_persist_dreamview_restoration(hass: HomeAssistant, entry_ids: set[str]) -> None:
    if not entry_ids:
        return
    if hass.is_stopping:
        raise OSError("DreamView restoration cannot be persisted during shutdown")
    # Native enable only schedules a save; preserve any subsequent deliberate disable too.
    native_store = hass.config_entries._store
    expected = {
        entry_id: str(entry.disabled_by) if entry.disabled_by is not None else None
        for entry_id in entry_ids
        if (entry := hass.config_entries.async_get_entry(entry_id)) is not None
    }
    save = hass.async_create_task(native_store.async_save(hass.config_entries._data_to_save()))
    await asyncio.shield(save)
    reader = Store[dict[str, Any]](
        hass, native_store.version, native_store.key, minor_version=native_store.minor_version
    )
    stored = await reader.async_load()
    saved = {entry["entry_id"]: entry.get("disabled_by") for entry in (stored or {}).get("entries", ())}
    for entry_id, disabled_by in expected.items():
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            continue
        current = str(entry.disabled_by) if entry.disabled_by is not None else None
        if entry_id not in saved or saved[entry_id] not in (disabled_by, current):
            raise OSError("DreamView member restoration could not be persisted")


def is_dreamview_claimed(hass: HomeAssistant, entry_id: str | None, coordinator: Any = None) -> bool:
    if getattr(coordinator, "_dreamview_claimed", False):
        return True
    if entry_id is None:
        return False
    claims = hass.data.get(DOMAIN, {}).get(DREAMVIEW_CLAIMS_DATA_KEY)
    if not isinstance(claims, Mapping) or entry_id not in claims:
        return False
    claim = claims[entry_id]
    if isinstance(claim, Mapping) and claim.get("releasing"):
        return False
    centre_entry_id = claim.get("centre_entry_id") if isinstance(claim, Mapping) else None
    if isinstance(centre_entry_id, str) and hass.config_entries.async_get_entry(centre_entry_id) is None:
        return False
    return True


def resolve_dreamview_member_entries(
    hass: HomeAssistant,
    centre_entry_id: str | None,
    members: Sequence[DreamviewMember],
    claims: Mapping[str, Mapping[str, Any]],
) -> tuple[ConfigEntry[Any], ...]:
    entries = hass.config_entries.async_entries(DOMAIN)
    resolved: list[ConfigEntry[Any]] = []
    seen: set[str] = set()
    for member in members:
        if member.address is not None:
            matches = [
                entry
                for entry in entries
                if isinstance(entry.unique_id, str) and entry.unique_id.strip().upper() == member.address
            ]
        else:
            advertised_matches = []
            title_matches = []
            for entry in entries:
                advertised_name = None
                if isinstance(entry.unique_id, str) and entry.unique_id:
                    info = bluetooth.async_last_service_info(hass, entry.unique_id, connectable=True)
                    if info is not None:
                        advertised_name = info.name
                if advertised_name == member.name:
                    advertised_matches.append(entry)
                if entry.title == member.name:
                    title_matches.append(entry)
            matches = advertised_matches or title_matches
            if len(matches) > 1:
                raise ValueError("Ambiguous DreamView member name")
        if not matches:
            continue
        member_entry = matches[0]
        if centre_entry_id is not None and member_entry.entry_id == centre_entry_id:
            raise ValueError("DreamView sync centre cannot be a member of its own group")
        if member_entry.entry_id in seen:
            raise ValueError("Duplicate DreamView member config entry")
        if (existing := claims.get(member_entry.entry_id)) is not None:
            if existing.get("releasing"):
                raise ValueError("DreamView member restoration is pending; retry after restoration")
            owner_id = existing.get("centre_entry_id")
            if owner_id != centre_entry_id and (
                not isinstance(owner_id, str) or hass.config_entries.async_get_entry(owner_id) is not None
            ):
                raise ValueError("DreamView member is already claimed by another sync centre")
        seen.add(member_entry.entry_id)
        resolved.append(member_entry)
    return tuple(resolved)


async def async_release_dreamview_claims_for_centre(
    hass: HomeAssistant,
    centre_entry_id: str,
    *,
    only_entry_ids: set[str] | None = None,
) -> None:
    await async_load_dreamview_claims(hass)
    async with _claims_lock(hass):
        claims = await async_load_dreamview_claims(hass)
        released = {
            entry_id: {**claim, "releasing": True}
            for entry_id, claim in claims.items()
            if claim.get("centre_entry_id") == centre_entry_id
            and (only_entry_ids is None or entry_id in only_entry_ids)
        }
        if not released:
            return
        # Keep recovery intent until native re-enable completes, without blocking setup.
        await _async_save_dreamview_claims(hass, {**claims, **released})
    for entry_id in released:
        if (entry := hass.config_entries.async_get_entry(entry_id)) is not None and (
            coord := getattr(entry, "runtime_data", None)
        ) is not None:
            coord._dreamview_claimed = False
    restored: set[str] = set()
    for entry_id, claim in released.items():
        if (
            claim.get("disabled_by_dreamview")
            and (entry := hass.config_entries.async_get_entry(entry_id)) is not None
            and entry.disabled_by == ConfigEntryDisabler.USER
        ):
            await hass.config_entries.async_set_disabled_by(entry_id, None)
            if entry.disabled_by is not None:
                raise RuntimeError("DreamView member config entry could not be restored")
        if (entry := hass.config_entries.async_get_entry(entry_id)) is not None and entry.disabled_by is None:
            if claim.get("disabled_by_dreamview"):
                restored.add(entry_id)
            from .effect_setup import get_effect_backend

            if (backend := get_effect_backend(hass)) is not None:
                await backend.preview.async_load_device(entry_id)
    await _async_persist_dreamview_restoration(hass, restored)
    async with _claims_lock(hass):
        claims = await async_load_dreamview_claims(hass)
        await _async_save_dreamview_claims(
            hass, {eid: dict(item) for eid, item in claims.items() if item != released.get(eid)}
        )


async def async_recover_dreamview_claims(hass: HomeAssistant) -> None:
    """Resume interrupted restoration and release ownership of removed centres."""
    claims = await async_load_dreamview_claims(hass)
    centres = {
        claim["centre_entry_id"]
        for claim in claims.values()
        if isinstance(claim.get("centre_entry_id"), str)
        and (claim.get("releasing") or hass.config_entries.async_get_entry(claim["centre_entry_id"]) is None)
    }
    for centre_id in centres:
        claims = await async_load_dreamview_claims(hass)
        orphaned = hass.config_entries.async_get_entry(centre_id) is None
        await async_release_dreamview_claims_for_centre(
            hass,
            centre_id,
            only_entry_ids={
                eid
                for eid, claim in claims.items()
                if claim.get("centre_entry_id") == centre_id and (orphaned or claim.get("releasing"))
            },
        )


async def async_guard_dreamview_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Block setup before coordinator construction, preserving explicit enable intent."""
    claims = await async_load_dreamview_claims(hass)
    claim = claims.get(entry.entry_id)
    if claim is None or claim.get("releasing"):
        return False
    centre_id = claim.get("centre_entry_id")
    if isinstance(centre_id, str) and hass.config_entries.async_get_entry(centre_id) is None:
        await async_release_dreamview_claims_for_centre(hass, centre_id, only_entry_ids={entry.entry_id})
        return False
    async with _claims_lock(hass):
        claims = await async_load_dreamview_claims(hass)
        if (claim := claims.get(entry.entry_id)) is None or claim.get("releasing"):
            return False
        if entry.disabled_by is None:
            await _async_save_dreamview_claims(
                hass,
                {**claims, entry.entry_id: {**claim, "disabled_by_dreamview": True, "prior_disabled_by": None}},
            )

    async def disable_claimed_entry() -> None:
        # Native reload acquires entry.setup_lock; setup acquires the claims lock.
        if is_dreamview_claimed(hass, entry.entry_id) and entry.disabled_by is None:
            await hass.config_entries.async_set_disabled_by(entry.entry_id, ConfigEntryDisabler.USER)

    hass.async_create_task(disable_claimed_entry())
    return True


async def async_cleanup_dreamview_claims_on_entry_removed(hass: HomeAssistant, entry_id: str) -> None:
    await _DreamviewStore(hass, 1, f"{DOMAIN}.dreamview.{entry_id}", private=True, atomic_writes=True).async_remove()
    await async_release_dreamview_claims_for_centre(hass, entry_id)
    async with _claims_lock(hass):
        claims = await async_load_dreamview_claims(hass)
        if entry_id in claims:
            remaining = {eid: dict(claim) for eid, claim in claims.items() if eid != entry_id}
            await _async_save_dreamview_claims(hass, remaining)


class _DreamviewMixin(_CoordinatorBase):
    """Uses the existing complete-sequence writer, physical guards and arbiter."""

    def _init_dreamview(self) -> None:
        self._dreamview_claimed = False
        self._dreamview_observed: dict[str, dict[str, Any]] = {}
        self._dreamview_authored: dict[str, Any] | None = None
        self._dreamview_loaded = False
        self._dreamview_last_write = "unknown"
        self._dreamview_private_write = False
        self._dreamview_store = (
            _DreamviewStore(
                self.hass, 1, f"{DOMAIN}.dreamview.{self.config_entry.entry_id}", private=True, atomic_writes=True
            )
            if self.config_entry is not None
            else None
        )

    def _require_not_dreamview_claimed(self) -> None:
        entry_id = self.config_entry.entry_id if self.config_entry is not None else None
        if is_dreamview_claimed(self.hass, entry_id, self):
            raise DreamviewClaimedError("Device is claimed by a DreamView sync centre")

    async def async_validate_dreamview_members(
        self, members: Sequence[DreamviewMember]
    ) -> tuple[ConfigEntry[Any], ...]:
        claims = await async_load_dreamview_claims(self.hass)
        centre_entry_id = self.config_entry.entry_id if self.config_entry is not None else None
        return resolve_dreamview_member_entries(self.hass, centre_entry_id, members, claims)

    def _handle_dreamview_notification(self, frame: bytes) -> bool:
        """Call after decryption, before generic status routing; ACKs are ignored."""
        if self.profile.dreamview_grammar != "H6099":
            return False
        observed = parse_dreamview_status(frame)
        if observed is None:
            return False
        setting, values = observed
        if setting not in self.profile.dreamview_reads:
            return False
        self._dreamview_observed[setting] = values
        return True

    async def _async_load_dreamview(self) -> None:
        if not self._dreamview_loaded:
            if self._dreamview_store is None:
                raise ValueError("DreamView requires a config entry for private membership persistence")
            self._dreamview_authored = await self._dreamview_store.async_load()
            self._dreamview_loaded = True

    async def async_replace_dreamview_group(self, members: Sequence[DreamviewMember]) -> None:
        """Explicit replacement, not merge. Persist intent, never confirmed membership."""
        members = tuple(members)
        packets = build_dreamview_group(members, self.profile)

        def validate(packet: bytes, profile: ModelProfile) -> None:
            require_dreamview(profile, "replace_group", member_count=len(members))
            if packet not in packets:
                raise ValueError("Packet is not part of the validated DreamView group")

        authored = {"operation": "replace", "members": [member.as_dict() for member in members]}
        async with async_control_intent(self, ControlIntent.USER):
            self._require_not_dreamview_claimed()
            await self._async_load_dreamview()
            assert self._dreamview_store is not None
            await async_load_dreamview_claims(self.hass)
            centre_entry_id = self.config_entry.entry_id if self.config_entry is not None else None
            prior_authored = copy.deepcopy(self._dreamview_authored)
            self._dreamview_last_write = "not_attempted"
            self._dreamview_private_write = True
            prior_claims: dict[str, dict[str, Any]] = {}
            new_entry_ids: set[str] = set()
            try:
                async with _claims_lock(self.hass):
                    claims = await async_load_dreamview_claims(self.hass)
                    resolved_entries = resolve_dreamview_member_entries(self.hass, centre_entry_id, members, claims)
                    prior_claims = {
                        eid: copy.deepcopy(claim)
                        for eid, claim in claims.items()
                        if centre_entry_id is not None and claim.get("centre_entry_id") == centre_entry_id
                    }
                    new_entry_ids = {entry.entry_id for entry in resolved_entries}
                    await self._dreamview_store.async_save(authored)
                    self._dreamview_authored = authored
                    updated_claims = dict(claims)
                    for member_entry in resolved_entries:
                        if member_entry.entry_id not in prior_claims or member_entry.disabled_by is None:
                            updated_claims[member_entry.entry_id] = {
                                "centre_entry_id": centre_entry_id,
                                "disabled_by_dreamview": member_entry.disabled_by is None,
                                "prior_disabled_by": (
                                    str(member_entry.disabled_by) if member_entry.disabled_by is not None else None
                                ),
                            }
                    if updated_claims != claims:
                        await _async_save_dreamview_claims(self.hass, updated_claims)
                if centre_entry_id is not None and (resolved_entries or prior_claims):
                    from .effect_setup import get_effect_backend

                    effect_backend = get_effect_backend(self.hass)
                    for member_entry in resolved_entries:
                        member_coord = getattr(member_entry, "runtime_data", None)
                        client = getattr(member_coord, "_client", None)
                        if member_coord is not None:
                            member_coord._dreamview_claimed = True
                            member_coord.invalidate_previews()
                            if effect_backend is not None:
                                await effect_backend.preview.async_unload_device(member_entry.entry_id)
                        if member_entry.disabled_by is None:
                            await self.hass.config_entries.async_set_disabled_by(
                                member_entry.entry_id, ConfigEntryDisabler.USER
                            )
                        if member_entry.disabled_by is None:
                            raise RuntimeError("DreamView member config entry could not be disabled")
                        if member_coord is not None:
                            await member_coord.disconnect()
                            if any(
                                link is not None and link.is_connected
                                for link in (client, getattr(member_coord, "_client", None))
                            ):
                                raise BleakError("DreamView member BLE connection could not be released")
                await self._async_write_dreamview(packets, validate)
            except BaseException:
                if self._dreamview_last_write == "not_attempted" and centre_entry_id is not None:
                    try:
                        newly_claimed = new_entry_ids - prior_claims.keys()
                        if newly_claimed:
                            await async_release_dreamview_claims_for_centre(
                                self.hass, centre_entry_id, only_entry_ids=newly_claimed
                            )
                        if self._dreamview_authored != prior_authored:
                            if prior_authored is None:
                                await self._dreamview_store.async_remove()
                            else:
                                await self._dreamview_store.async_save(prior_authored)
                            self._dreamview_authored = prior_authored
                    except Exception:
                        _LOGGER.exception("DreamView rollback incomplete; persisted recovery intent retained")
                raise
            finally:
                self._dreamview_private_write = False
            if self._dreamview_last_write == "sent_unconfirmed" and centre_entry_id is not None:
                dropped = prior_claims.keys() - new_entry_ids
                if dropped:
                    await async_release_dreamview_claims_for_centre(self.hass, centre_entry_id, only_entry_ids=dropped)

    async def async_set_dreamview(self, setting: str, values: Mapping[str, Any]) -> None:
        values = dict(values)
        packet = build_dreamview_command(setting, values, self.profile)
        if setting == "delete_group":
            raise ValueError("Use explicit delete_dreamview_group")
        async with async_control_intent(self, ControlIntent.USER):
            await self._async_write_dreamview(
                (packet,), lambda packet, profile: self._validate_dreamview_command(packet, setting, values, profile)
            )

    async def async_delete_dreamview_group(self) -> None:
        """Keep the last authored members for recovery, mark only deletion intent."""
        packet = build_dreamview_command("delete_group", {}, self.profile)
        async with async_control_intent(self, ControlIntent.USER):
            await self._async_load_dreamview()
            assert self._dreamview_store is not None
            authored = {**(self._dreamview_authored or {}), "operation": "delete"}
            await self._dreamview_store.async_save(authored)
            self._dreamview_authored = authored
            await self._async_write_dreamview(
                (packet,), lambda packet, profile: self._validate_dreamview_command(packet, "delete_group", {}, profile)
            )
            if self._dreamview_last_write == "sent_unconfirmed" and self.config_entry is not None:
                await async_release_dreamview_claims_for_centre(self.hass, self.config_entry.entry_id)

    @staticmethod
    def _validate_dreamview_command(
        packet: bytes, setting: str, values: Mapping[str, Any], profile: ModelProfile
    ) -> None:
        if packet != build_dreamview_command(setting, values, profile):
            raise ValueError("Packet does not match the validated DreamView command")

    async def _async_write_dreamview(
        self, packets: Sequence[bytes], validator: Callable[[bytes, ModelProfile], None]
    ) -> None:
        self._dreamview_last_write = "not_attempted"

        def guard() -> None:
            validator(packets[0], self.profile)
            self._dreamview_last_write = "attempted_unconfirmed"

        await self.async_write_effect_sequence(
            packets, intent=ControlIntent.USER, write_guard=guard, packet_validator=validator
        )
        self._dreamview_last_write = "sent_unconfirmed"

    async def async_read_dreamview_state(self, *, timeout: float = 2.0) -> dict[str, Any]:
        """Query only known individual reads; absent replies remain unknown.

        The protocol has no request IDs. Responses received after dispatch are
        observations, not proof they were caused by that request or any write.
        """
        if not 0 <= timeout <= 10:
            raise ValueError("DreamView read timeout must be 0..10 seconds")
        settings = tuple(setting for setting in DREAMVIEW_READ_SETTINGS if setting in self.profile.dreamview_reads)
        if not settings:
            raise ValueError("No DreamView reads are supported by this profile")
        queries = {build_dreamview_query(setting, self.profile): setting for setting in settings}

        def validate(packet: bytes, profile: ModelProfile) -> None:
            if packet not in queries or packet != build_dreamview_query(queries[packet], profile):
                raise ValueError("Packet does not match a validated DreamView query")

        async with async_control_intent(self, ControlIntent.USER):
            await self._async_load_dreamview()
            self._dreamview_observed.clear()
            await self.async_write_effect_sequence(tuple(queries), intent=ControlIntent.USER, packet_validator=validate)
            deadline = asyncio.get_running_loop().time() + timeout
            while not set(settings) <= self._dreamview_observed.keys():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.05, remaining))
            observed = copy.deepcopy(self._dreamview_observed)
            if video := observed.get("video_settings"):
                observed["sample"] = {
                    "sample_first": int(video["apply_area"]),
                    "sample_second": int(video["content_mode"]),
                    "unknown": list(video["unknown"]),
                }
                for field in DREAMVIEW_VIDEO_FIELDS:
                    value = video[field]
                    video[field] = value.name if isinstance(value, IntEnum) else value
            missing = set(settings) - self._dreamview_observed.keys()
            unsupported = set(DREAMVIEW_READ_SETTINGS) - set(settings)
            for names in (missing, unsupported):
                if "video_settings" in names:
                    names.add("sample")
            return {
                "authored": copy.deepcopy(self._dreamview_authored),
                "authored_source": "local_request",
                "membership_confirmed": False,
                "membership_readback": "unavailable",
                "last_write": self._dreamview_last_write,
                "observed": observed,
                "missing_reads": sorted(missing),
                "unsupported_reads": sorted(unsupported),
                "slot_identities": "unknown",
            }
