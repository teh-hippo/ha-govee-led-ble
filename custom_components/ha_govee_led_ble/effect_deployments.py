"""Durable Effect Studio deployment intent and audit history."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final, cast
from uuid import UUID

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .effect_domain import LibraryItem, SourceKind, effect_content_from_dict, effect_content_hash
from .effect_limits import (
    MAX_DEPLOYMENT_RECORDS,
    MAX_DEPLOYMENT_STORE_BYTES,
    MAX_IDENTIFIER_LENGTH,
    MAX_REVISION,
    MAX_STORE_JSON_NODES,
    validate_bounded_string,
    validate_json_document,
    validate_revision,
    validate_timestamp,
)
from .effect_persistence_validation import (
    EffectLimitError,
    EffectNotFoundError,
    EffectStorageError,
    EffectVersionConflictError,
)
from .effect_persistence_validation import as_persisted_mapping as _as_mapping
from .effect_persistence_validation import optional_persisted_boolean as _optional_bool
from .effect_persistence_validation import optional_persisted_integer as _optional_int
from .effect_persistence_validation import optional_persisted_rgb as _optional_rgb
from .effect_persistence_validation import optional_persisted_string as _optional_str
from .effect_persistence_validation import required_persisted_boolean as _required_bool
from .effect_persistence_validation import required_persisted_integer as _required_int
from .effect_persistence_validation import required_persisted_mapping as _required_mapping
from .effect_persistence_validation import required_persisted_rgb as _required_rgb
from .effect_persistence_validation import required_persisted_string as _required_str
from .effect_persistence_validation import validate_persisted_rgb as _validate_rgb
from .effect_schema_migration import LegacyEffectMigrationError, migrate_effect_content_v1
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore

DEPLOYMENT_STORE_VERSION: Final = 2
DEPLOYMENT_STORE_MINOR_VERSION: Final = 0
DEPLOYMENT_STORE_KEY: Final = f"{DOMAIN}.effect_deployments"
MAX_DEPLOYMENT_PROGRESS: Final = 1024
MAX_DEPLOYMENT_EVIDENCE_CODES: Final = 8

_LOGGER = logging.getLogger(__name__)


class DeploymentPhase(StrEnum):
    COMPILING = "compiling"
    PENDING = "pending"
    UPLOADING = "uploading"
    ACTIVATING = "activating"
    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    APPLIED = "applied"
    UNCERTAIN = "uncertain"
    RECOVERING = "recovering"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class ObservationConfidence(StrEnum):
    EXACT_SESSION = "exact_session"
    ACTIVATION_MATCH = "activation_match"
    SETTINGS_MATCH = "settings_match"
    MODE_MATCH = "mode_match"
    WRITE_COMPLETED = "write_completed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PriorControlState:
    mode: str
    is_on: bool
    brightness_pct: int
    rgb_color: tuple[int, int, int]
    color_temp_kelvin: int | None = None
    effect: str | None = None
    diy_code: int | None = None
    music_mode: str = "off"
    video_mode: str = "off"
    music_sensitivity: int = 100
    music_calm: bool = False
    music_color: tuple[int, int, int] | None = None
    music_separation_point: int = 1
    music_separation_gradient: bool = True
    music_hopping_brightness: int = 50
    music_piano_key_count: int = 15
    music_fountain_direction: str = "clockwise"
    music_daynight_segments: int = 1
    music_daynight_speed: int = 10
    music_daynight_gradient: bool = False
    video_full_screen: bool = True
    video_saturation: int = 100
    video_sound_effects: bool = False
    video_sound_effects_softness: int = 100
    white_balance_red: int | None = None
    white_balance_blue: int | None = None
    relative_brightness: int | None = None
    relative_brightness_left: int | None = None
    relative_brightness_top: int | None = None
    relative_brightness_right: int | None = None
    relative_brightness_bottom: int | None = None
    blank_screen: bool | None = None
    blank_screen_detection: int | None = None
    blank_screen_low_brightness_duration_seconds: int | None = None
    blank_screen_same_tone_duration_seconds: int | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.mode,
            "prior control mode",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if not isinstance(self.is_on, bool):
            raise EffectStorageError("prior power state must be a boolean")
        if (
            not isinstance(self.brightness_pct, int)
            or isinstance(self.brightness_pct, bool)
            or not 0 <= self.brightness_pct <= 100
        ):
            raise EffectStorageError("prior brightness must be from 0 to 100")
        _validate_rgb(self.rgb_color, "prior RGB colour")
        if self.color_temp_kelvin is not None and (
            not isinstance(self.color_temp_kelvin, int)
            or isinstance(self.color_temp_kelvin, bool)
            or not 1000 <= self.color_temp_kelvin <= 10000
        ):
            raise EffectStorageError("prior colour temperature must be from 1000 to 10000")
        for value, name in (
            (self.effect, "prior effect"),
            (self.music_mode, "prior music mode"),
            (self.video_mode, "prior video mode"),
        ):
            if value is not None:
                validate_bounded_string(
                    value,
                    name,
                    maximum=MAX_IDENTIFIER_LENGTH,
                    error_type=EffectStorageError,
                )
        if self.diy_code is not None and (
            not isinstance(self.diy_code, int) or isinstance(self.diy_code, bool) or not 0 <= self.diy_code <= 0xFFFF
        ):
            raise EffectStorageError("prior DIY code must be from 0 to 65535")
        if (
            not isinstance(self.music_sensitivity, int)
            or isinstance(self.music_sensitivity, bool)
            or not 0 <= self.music_sensitivity <= 100
        ):
            raise EffectStorageError("prior music sensitivity must be from 0 to 100")
        if not isinstance(self.music_calm, bool):
            raise EffectStorageError("prior music style must be a boolean")
        if self.music_color is not None:
            _validate_rgb(self.music_color, "prior music colour")
        numeric_values: tuple[tuple[int, str, int, int], ...] = (
            (self.music_separation_point, "prior separation point", 1, 5),
            (self.music_hopping_brightness, "prior hopping brightness", 0, 50),
            (self.music_piano_key_count, "prior piano key count", 8, 15),
            (self.music_daynight_segments, "prior day-and-night segment count", 1, 7),
            (self.music_daynight_speed, "prior day-and-night speed", 1, 50),
            (self.video_saturation, "prior video saturation", 0, 100),
            (self.video_sound_effects_softness, "prior video sound-effects softness", 1, 100),
        )
        for numeric_value, numeric_name, minimum, maximum in numeric_values:
            if (
                not isinstance(numeric_value, int)
                or isinstance(numeric_value, bool)
                or not minimum <= numeric_value <= maximum
            ):
                raise EffectStorageError(f"{numeric_name} must be from {minimum} to {maximum}")
        boolean_values: tuple[tuple[bool, str], ...] = (
            (self.music_separation_gradient, "prior separation gradient"),
            (self.music_daynight_gradient, "prior day-and-night gradient"),
            (self.video_full_screen, "prior video capture area"),
            (self.video_sound_effects, "prior video sound effects"),
        )
        for boolean_value, boolean_name in boolean_values:
            if not isinstance(boolean_value, bool):
                raise EffectStorageError(f"{boolean_name} must be a boolean")
        if self.music_fountain_direction not in {"clockwise", "counterclockwise", "two_way"}:
            raise EffectStorageError("prior fountain direction is invalid")
        optional_numeric_values: tuple[tuple[int | None, str, int, int], ...] = (
            (self.white_balance_red, "prior white-balance red", 0, 255),
            (self.white_balance_blue, "prior white-balance blue", 0, 255),
            (self.relative_brightness, "prior relative brightness", 1, 100),
            (self.relative_brightness_left, "prior left relative brightness", 1, 100),
            (self.relative_brightness_top, "prior top relative brightness", 1, 100),
            (self.relative_brightness_right, "prior right relative brightness", 1, 100),
            (self.relative_brightness_bottom, "prior bottom relative brightness", 1, 100),
            (self.blank_screen_detection, "prior blank-screen detection", 0, 255),
            (
                self.blank_screen_low_brightness_duration_seconds,
                "prior blank-screen low-brightness duration",
                0,
                65535,
            ),
            (
                self.blank_screen_same_tone_duration_seconds,
                "prior blank-screen same-tone duration",
                0,
                65535,
            ),
        )
        for optional_value, optional_name, minimum, maximum in optional_numeric_values:
            if optional_value is not None and (
                not isinstance(optional_value, int)
                or isinstance(optional_value, bool)
                or not minimum <= optional_value <= maximum
            ):
                raise EffectStorageError(f"{optional_name} must be from {minimum} to {maximum}")
        if self.blank_screen is not None and not isinstance(self.blank_screen, bool):
            raise EffectStorageError("prior blank-screen state must be a boolean or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "is_on": self.is_on,
            "brightness_pct": self.brightness_pct,
            "rgb_color": list(self.rgb_color),
            "color_temp_kelvin": self.color_temp_kelvin,
            "effect": self.effect,
            "diy_code": self.diy_code,
            "music_mode": self.music_mode,
            "video_mode": self.video_mode,
            "music_sensitivity": self.music_sensitivity,
            "music_calm": self.music_calm,
            "music_color": list(self.music_color) if self.music_color is not None else None,
            "music_separation_point": self.music_separation_point,
            "music_separation_gradient": self.music_separation_gradient,
            "music_hopping_brightness": self.music_hopping_brightness,
            "music_piano_key_count": self.music_piano_key_count,
            "music_fountain_direction": self.music_fountain_direction,
            "music_daynight_segments": self.music_daynight_segments,
            "music_daynight_speed": self.music_daynight_speed,
            "music_daynight_gradient": self.music_daynight_gradient,
            "video_full_screen": self.video_full_screen,
            "video_saturation": self.video_saturation,
            "video_sound_effects": self.video_sound_effects,
            "video_sound_effects_softness": self.video_sound_effects_softness,
            "white_balance_red": self.white_balance_red,
            "white_balance_blue": self.white_balance_blue,
            "relative_brightness": self.relative_brightness,
            "relative_brightness_left": self.relative_brightness_left,
            "relative_brightness_top": self.relative_brightness_top,
            "relative_brightness_right": self.relative_brightness_right,
            "relative_brightness_bottom": self.relative_brightness_bottom,
            "blank_screen": self.blank_screen,
            "blank_screen_detection": self.blank_screen_detection,
            "blank_screen_low_brightness_duration_seconds": self.blank_screen_low_brightness_duration_seconds,
            "blank_screen_same_tone_duration_seconds": self.blank_screen_same_tone_duration_seconds,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PriorControlState:
        return cls(
            mode=_required_str(raw, "mode"),
            is_on=_required_bool(raw, "is_on"),
            brightness_pct=_required_int(raw, "brightness_pct"),
            rgb_color=_required_rgb(raw, "rgb_color"),
            color_temp_kelvin=_optional_int(raw, "color_temp_kelvin"),
            effect=_optional_str(raw, "effect"),
            diy_code=_optional_int(raw, "diy_code"),
            music_mode=_optional_str(raw, "music_mode") or "off",
            video_mode=_optional_str(raw, "video_mode") or "off",
            music_sensitivity=_optional_int(raw, "music_sensitivity", default=100),
            music_calm=_optional_bool(raw, "music_calm", default=False),
            music_color=_optional_rgb(raw, "music_color"),
            music_separation_point=_optional_int(raw, "music_separation_point", default=1),
            music_separation_gradient=_optional_bool(raw, "music_separation_gradient", default=True),
            music_hopping_brightness=_optional_int(raw, "music_hopping_brightness", default=50),
            music_piano_key_count=_optional_int(raw, "music_piano_key_count", default=15),
            music_fountain_direction=_optional_str(raw, "music_fountain_direction") or "clockwise",
            music_daynight_segments=_optional_int(raw, "music_daynight_segments", default=1),
            music_daynight_speed=_optional_int(raw, "music_daynight_speed", default=10),
            music_daynight_gradient=_optional_bool(raw, "music_daynight_gradient", default=False),
            video_full_screen=_optional_bool(raw, "video_full_screen", default=True),
            video_saturation=_optional_int(raw, "video_saturation", default=100),
            video_sound_effects=_optional_bool(raw, "video_sound_effects", default=False),
            video_sound_effects_softness=_optional_int(raw, "video_sound_effects_softness", default=100),
            white_balance_red=_optional_int(raw, "white_balance_red"),
            white_balance_blue=_optional_int(raw, "white_balance_blue"),
            relative_brightness=_optional_int(raw, "relative_brightness"),
            relative_brightness_left=_optional_int(raw, "relative_brightness_left"),
            relative_brightness_top=_optional_int(raw, "relative_brightness_top"),
            relative_brightness_right=_optional_int(raw, "relative_brightness_right"),
            relative_brightness_bottom=_optional_int(raw, "relative_brightness_bottom"),
            blank_screen=_optional_bool(raw, "blank_screen"),
            blank_screen_detection=_optional_int(raw, "blank_screen_detection"),
            blank_screen_low_brightness_duration_seconds=_optional_int(
                raw,
                "blank_screen_low_brightness_duration_seconds",
            ),
            blank_screen_same_tone_duration_seconds=_optional_int(
                raw,
                "blank_screen_same_tone_duration_seconds",
            ),
        )


@dataclass(frozen=True, slots=True)
class DeploymentRecord:
    operation_id: UUID
    config_entry_id: str
    diy_code: int | None
    phase: DeploymentPhase
    compiler_version: int
    artifact_sha256: str
    updated_at: str
    content_kind: str = "custom_effect"
    target_mode: str = "custom"
    target_effect: str | None = None
    evidence_codes: tuple[str, ...] = ()
    source_kind: str = "saved_effect"
    selector_label: str = ""
    source_origin_kind: str = "authored"
    source_origin_id: str | None = None
    source_content_hash: str = ""
    item_id: UUID | None = None
    item_version: int | None = None
    error_code: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    verification_confidence: ObservationConfidence = ObservationConfidence.UNKNOWN
    prior_state: PriorControlState | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.config_entry_id,
            "deployment config entry ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if self.diy_code is not None and (
            not isinstance(self.diy_code, int) or isinstance(self.diy_code, bool) or not 0 <= self.diy_code <= 0xFFFF
        ):
            raise EffectStorageError("deployment DIY code must be from 0 to 65535")
        validate_bounded_string(
            self.content_kind,
            "deployment content kind",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if self.target_mode not in {"custom", "scene", "music", "video"}:
            raise EffectStorageError("deployment target mode must be custom, scene, music or video")
        if self.target_effect is not None:
            validate_bounded_string(
                self.target_effect,
                "deployment target effect",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if self.target_mode == "scene" and self.target_effect is None:
            raise EffectStorageError("scene deployment must include a target effect")
        if len(self.evidence_codes) > MAX_DEPLOYMENT_EVIDENCE_CODES:
            raise EffectStorageError(f"deployment must not exceed {MAX_DEPLOYMENT_EVIDENCE_CODES} evidence codes")
        for code in self.evidence_codes:
            validate_bounded_string(
                code,
                "deployment evidence code",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if self.compiler_version < 1:
            raise EffectStorageError("deployment compiler version must be positive")
        if len(self.artifact_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.artifact_sha256
        ):
            raise EffectStorageError("deployment artifact hash must be SHA-256")
        validate_timestamp(
            self.updated_at,
            "deployment timestamp",
            error_type=EffectStorageError,
        )
        if self.error_code is not None:
            validate_bounded_string(
                self.error_code,
                "deployment error code",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if (
            self.progress_current < 0
            or self.progress_total < 0
            or self.progress_current > self.progress_total
            or self.progress_total > MAX_DEPLOYMENT_PROGRESS
        ):
            raise EffectStorageError("deployment progress is invalid")
        if self.source_kind not in {"saved_effect", "snapshot", "deleted_effect"}:
            raise EffectStorageError("deployment source kind is invalid")
        validate_bounded_string(
            self.selector_label,
            "deployment selector label",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        validate_bounded_string(
            self.source_origin_kind,
            "deployment origin kind",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if self.source_origin_id is not None:
            validate_bounded_string(
                self.source_origin_id,
                "deployment origin source ID",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if len(self.source_content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_content_hash
        ):
            raise EffectStorageError("deployment source content hash must be SHA-256")
        if self.source_kind == "saved_effect":
            if self.item_id is None or self.item_version is None:
                raise EffectStorageError("deployment library source is incomplete")
            validate_revision(
                self.item_version,
                "deployment item version",
                minimum=1,
                error_type=EffectStorageError,
            )
        elif self.item_id is not None or self.item_version is not None:
            raise EffectStorageError("detached deployment source must not reference a library item")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": str(self.operation_id),
            "config_entry_id": self.config_entry_id,
            "diy_code": self.diy_code,
            "content_kind": self.content_kind,
            "phase": self.phase.value,
            "compiler_version": self.compiler_version,
            "artifact_sha256": self.artifact_sha256,
            "updated_at": self.updated_at,
            "target_mode": self.target_mode,
            "target_effect": self.target_effect,
            "evidence_codes": list(self.evidence_codes),
            "source_kind": self.source_kind,
            "selector_label": self.selector_label,
            "source_origin_kind": self.source_origin_kind,
            "source_origin_id": self.source_origin_id,
            "source_content_hash": self.source_content_hash,
            "item_id": str(self.item_id) if self.item_id is not None else None,
            "item_version": self.item_version,
            "error_code": self.error_code,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "verification_confidence": self.verification_confidence.value,
            "prior_state": self.prior_state.to_dict() if self.prior_state is not None else None,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "operation_id": str(self.operation_id),
            "config_entry_id": self.config_entry_id,
            "diy_code": self.diy_code,
            "content_kind": self.content_kind,
            "target_mode": self.target_mode,
            "target_effect": self.target_effect,
            "phase": self.phase.value,
            "updated_at": self.updated_at,
            "item_id": str(self.item_id) if self.item_id is not None else None,
            "item_version": self.item_version,
            "source_kind": self.source_kind,
            "selector_label": self.selector_label,
            "source_origin_kind": self.source_origin_kind,
            "source_origin_id": self.source_origin_id,
            "source_content_hash": self.source_content_hash,
            "error_code": self.error_code,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "verification_confidence": self.verification_confidence.value,
            "evidence_codes": list(self.evidence_codes),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DeploymentRecord:
        try:
            operation_id = UUID(_required_str(raw, "operation_id"))
            item_id_raw = raw.get("item_id")
            item_id = None if item_id_raw is None else UUID(str(item_id_raw))
        except ValueError as exc:
            raise EffectStorageError("deployment contains an invalid UUID") from exc
        try:
            phase = DeploymentPhase(_required_str(raw, "phase"))
            confidence = ObservationConfidence(
                str(raw.get("verification_confidence", ObservationConfidence.UNKNOWN.value))
            )
        except ValueError as exc:
            raise EffectStorageError("deployment phase is invalid") from exc
        prior_state_raw = raw.get("prior_state")
        return cls(
            operation_id=operation_id,
            config_entry_id=_required_str(raw, "config_entry_id"),
            diy_code=_optional_int(raw, "diy_code"),
            content_kind=_optional_str(raw, "content_kind") or "custom_effect",
            phase=phase,
            compiler_version=_required_int(raw, "compiler_version"),
            artifact_sha256=_required_str(raw, "artifact_sha256"),
            updated_at=_required_str(raw, "updated_at"),
            target_mode=_optional_str(raw, "target_mode") or "custom",
            target_effect=_optional_str(raw, "target_effect"),
            evidence_codes=_string_tuple(raw.get("evidence_codes", ()), "deployment evidence codes"),
            source_kind=_optional_str(raw, "source_kind") or "saved_effect",
            selector_label=_required_str(raw, "selector_label"),
            source_origin_kind=_required_str(raw, "source_origin_kind"),
            source_origin_id=_optional_str(raw, "source_origin_id"),
            source_content_hash=_required_str(raw, "source_content_hash"),
            item_id=item_id,
            item_version=(
                _optional_int(raw, "item_version") if "item_version" in raw else _optional_int(raw, "item_revision")
            ),
            error_code=_optional_str(raw, "error_code"),
            progress_current=_optional_int(raw, "progress_current", default=0),
            progress_total=_optional_int(raw, "progress_total", default=0),
            verification_confidence=confidence,
            prior_state=(
                None
                if prior_state_raw is None
                else PriorControlState.from_dict(_as_mapping(prior_state_raw, "prior control state"))
            ),
        )


@dataclass(frozen=True, slots=True)
class DeploymentSnapshot:
    version: int
    records: tuple[DeploymentRecord, ...]


@dataclass(frozen=True, slots=True)
class DeploymentDetachment:
    snapshot: DeploymentSnapshot
    operation_ids: tuple[UUID, ...]


class EffectDeploymentRepository:
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _deployment_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None
        self._listeners: set[Callable[[DeploymentSnapshot], None]] = set()

    async def async_load(self) -> DeploymentSnapshot:
        async with self._lock:
            stored = await self._store.async_load()
            data: dict[str, Any] = {"version": 0, "records": {}} if stored is None else stored
            snapshot, data = _load_deployments(data)
            interrupted = {}
            for record in snapshot.records:
                if record.phase is DeploymentPhase.COMPILING:
                    interrupted[str(record.operation_id)] = replace(
                        record,
                        phase=DeploymentPhase.FAILED,
                        error_code="home_assistant_restarted_before_write",
                    ).to_dict()
                elif record.phase in {
                    DeploymentPhase.UPLOADING,
                    DeploymentPhase.ACTIVATING,
                    DeploymentPhase.VERIFYING,
                    DeploymentPhase.RECOVERING,
                }:
                    interrupted[str(record.operation_id)] = replace(
                        record,
                        phase=DeploymentPhase.UNCERTAIN,
                        error_code="home_assistant_restarted",
                    ).to_dict()
            if interrupted:
                data = copy.deepcopy(data)
                data["records"].update(interrupted)
                data["version"] += 1
                snapshot = _validate_deployments(data)
                await self._store.async_save(data)
            elif stored is not None and data != stored:
                await self._store.async_save(data)
            self._data = copy.deepcopy(data)
            return snapshot

    def snapshot(self) -> DeploymentSnapshot:
        return _validate_deployments(self._require_loaded())

    def subscribe(
        self,
        listener: Callable[[DeploymentSnapshot], None],
    ) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def get(self, operation_id: UUID) -> DeploymentRecord:
        records = cast(dict[str, Any], self._require_loaded()["records"])
        raw = records.get(str(operation_id))
        if not isinstance(raw, Mapping):
            raise EffectNotFoundError(f"deployment {operation_id} does not exist")
        return DeploymentRecord.from_dict(cast(Mapping[str, Any], raw))

    def get_optional(self, operation_id: UUID) -> DeploymentRecord | None:
        try:
            return self.get(operation_id)
        except EffectNotFoundError:
            return None

    def latest_for_diy_code(
        self,
        config_entry_id: str,
        diy_code: int,
    ) -> DeploymentRecord | None:
        matching = tuple(
            record
            for record in self.snapshot().records
            if record.config_entry_id == config_entry_id
            and record.target_mode == "custom"
            and record.diy_code == diy_code
        )
        return max(matching, key=lambda record: record.updated_at, default=None)

    def latest_for_effect(
        self,
        config_entry_id: str,
        effect: str,
    ) -> DeploymentRecord | None:
        matching = tuple(
            record
            for record in self.snapshot().records
            if record.config_entry_id == config_entry_id
            and record.target_mode == "scene"
            and record.target_effect == effect
        )
        return max(matching, key=lambda record: record.updated_at, default=None)

    def latest_for_profile(
        self,
        config_entry_id: str,
        mode: str,
    ) -> DeploymentRecord | None:
        matching = tuple(
            record
            for record in self.snapshot().records
            if record.config_entry_id == config_entry_id and record.target_mode == mode
        )
        return max(matching, key=lambda record: record.updated_at, default=None)

    async def async_detach_item(self, item_id: UUID) -> DeploymentDetachment:
        async with self._lock:
            current = self._require_loaded()
            candidate = copy.deepcopy(current)
            operation_ids: list[UUID] = []
            for key, raw in candidate["records"].items():
                record = DeploymentRecord.from_dict(_as_mapping(raw, f"deployment {key}"))
                if record.item_id != item_id:
                    continue
                candidate["records"][key] = replace(
                    record,
                    source_kind="deleted_effect",
                    item_id=None,
                    item_version=None,
                ).to_dict()
                operation_ids.append(record.operation_id)
            if not operation_ids:
                return DeploymentDetachment(_validate_deployments(current), ())
            candidate["version"] += 1
            snapshot = _validate_deployments(candidate)
            await self._store.async_save(candidate)
            self._data = candidate
            for listener in tuple(self._listeners):
                try:
                    listener(snapshot)
                except Exception:
                    _LOGGER.exception("Effect deployment subscriber failed after a committed write")
            return DeploymentDetachment(snapshot, tuple(operation_ids))

    async def async_delete_device(self, config_entry_id: str) -> DeploymentSnapshot:
        async with self._lock:
            current = self._require_loaded()
            candidate = copy.deepcopy(current)
            removed = [
                key
                for key, raw in candidate["records"].items()
                if DeploymentRecord.from_dict(_as_mapping(raw, f"deployment {key}")).config_entry_id == config_entry_id
            ]
            if not removed:
                return _validate_deployments(current)
            for key in removed:
                candidate["records"].pop(key)
            candidate["version"] += 1
            snapshot = _validate_deployments(candidate)
            await self._store.async_save(candidate)
            self._data = candidate
            for listener in tuple(self._listeners):
                try:
                    listener(snapshot)
                except Exception:
                    _LOGGER.exception("Effect deployment subscriber failed after a committed write")
            return snapshot

    async def async_reattach_item(
        self,
        detachment: DeploymentDetachment,
        *,
        item_id: UUID,
        item_version: int,
    ) -> DeploymentSnapshot:
        if not detachment.operation_ids:
            return self.snapshot()
        async with self._lock:
            current = self._require_loaded()
            candidate = copy.deepcopy(current)
            for operation_id in detachment.operation_ids:
                key = str(operation_id)
                raw = candidate["records"].get(key)
                if not isinstance(raw, Mapping):
                    raise EffectStorageError(f"deployment {operation_id} disappeared during delete rollback")
                record = DeploymentRecord.from_dict(_as_mapping(raw, f"deployment {key}"))
                if record.source_kind != "deleted_effect" or record.item_id is not None:
                    raise EffectStorageError(f"deployment {operation_id} changed during delete rollback")
                candidate["records"][key] = replace(
                    record,
                    source_kind="saved_effect",
                    item_id=item_id,
                    item_version=item_version,
                ).to_dict()
            candidate["version"] += 1
            snapshot = _validate_deployments(candidate)
            await self._store.async_save(candidate)
            self._data = candidate
            for listener in tuple(self._listeners):
                try:
                    listener(snapshot)
                except Exception:
                    _LOGGER.exception("Effect deployment subscriber failed after a committed write")
            return snapshot

    async def async_put(
        self,
        record: DeploymentRecord,
        *,
        expected_version: int | None,
        durable: bool = True,
    ) -> DeploymentSnapshot:
        async with self._lock:
            current = self._require_loaded()
            version = cast(int, current["version"])
            if expected_version is not None and version != expected_version:
                raise EffectVersionConflictError(version)
            candidate = copy.deepcopy(current)
            key = str(record.operation_id)
            if key not in candidate["records"] and len(candidate["records"]) >= MAX_DEPLOYMENT_RECORDS:
                _remove_oldest_terminal_deployment(candidate["records"])
            candidate["records"][str(record.operation_id)] = record.to_dict()
            candidate["version"] += 1
            snapshot = _validate_deployments(candidate)
            if durable:
                await self._store.async_save(candidate)
                self._data = candidate
            else:
                self._data = candidate
                self._store.async_delay_save(
                    lambda: copy.deepcopy(self._require_loaded()),
                    delay=5,
                )
            for listener in tuple(self._listeners):
                try:
                    listener(snapshot)
                except Exception:
                    _LOGGER.exception("Effect deployment subscriber failed after a committed write")
            return snapshot

    async def async_reconcile_library_hashes(self, items: tuple[LibraryItem, ...]) -> None:
        hashes = {(item.id, item.version): item.content_hash for item in items}
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            changed = False
            for key, raw in candidate["records"].items():
                record = DeploymentRecord.from_dict(_as_mapping(raw, f"deployment {key}"))
                if record.source_kind != "saved_effect" or record.item_id is None or record.item_version is None:
                    continue
                content_hash = hashes.get((record.item_id, record.item_version))
                if content_hash is None or content_hash == record.source_content_hash:
                    continue
                candidate["records"][key] = replace(record, source_content_hash=content_hash).to_dict()
                changed = True
            if not changed:
                return
            candidate["version"] += 1
            _validate_deployments(candidate)
            await self._store.async_save(candidate)
            self._data = candidate

    def _require_loaded(self) -> dict[str, Any]:
        if self._data is None:
            raise EffectStorageError("deployment store has not been loaded")
        return self._data


def _deployment_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        DEPLOYMENT_STORE_VERSION,
        DEPLOYMENT_STORE_KEY,
        minor_version=DEPLOYMENT_STORE_MINOR_VERSION,
        migrate=_async_migrate_deployments,
    )


async def _async_migrate_deployments(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if old_major_version == DEPLOYMENT_STORE_VERSION and old_minor_version <= DEPLOYMENT_STORE_MINOR_VERSION:
        return old_data
    if old_major_version != 1 or old_minor_version > 3:
        raise EffectStorageError(f"cannot migrate deployment store version {old_major_version}.{old_minor_version}")
    root = _as_mapping(old_data, "legacy deployment store")
    records = _required_mapping(root, "records")
    return {
        "version": _required_non_negative_int(root, "revision"),
        "records": {
            str(key): _migrate_legacy_deployment_record(_as_mapping(value, f"legacy deployment {key}"))
            for key, value in records.items()
        },
    }


def _migrate_legacy_deployment_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    migrated = dict(raw)
    item_id = raw.get("item_id")
    snapshot = raw.get("snapshot")
    if item_id is not None:
        source_kind = "saved_effect"
        selector_label = str(item_id)
        origin_kind = SourceKind.MIGRATED.value
        origin_id = None
        content_hash = _required_str(raw, "artifact_sha256")
        item_version = _optional_int(raw, "item_revision")
    elif isinstance(snapshot, Mapping):
        try:
            content = effect_content_from_dict(migrate_effect_content_v1(_required_mapping(snapshot, "content")))
        except (LegacyEffectMigrationError, ValueError) as exc:
            raise EffectStorageError(f"legacy deployment snapshot content is invalid: {exc}") from exc
        provenance = _required_mapping(snapshot, "provenance")
        source_kind = "snapshot"
        selector_label = _required_str(snapshot, "name")
        origin_kind = str(provenance.get("source_kind", SourceKind.MIGRATED.value))
        origin_id = _optional_str(provenance, "source_id")
        content_hash = effect_content_hash(content)
        item_id = None
        item_version = None
    else:
        raise EffectStorageError("legacy deployment source is incomplete")
    migrated.update(
        {
            "source_kind": source_kind,
            "selector_label": selector_label,
            "source_origin_kind": origin_kind,
            "source_origin_id": origin_id,
            "source_content_hash": content_hash,
            "item_id": item_id,
            "item_version": item_version,
        }
    )
    migrated.pop("item_revision", None)
    migrated.pop("snapshot_id", None)
    migrated.pop("snapshot", None)
    return migrated


def _validate_deployments(data: object) -> DeploymentSnapshot:
    raw = _as_mapping(data, "deployment store")
    validate_json_document(
        raw,
        "deployment store",
        maximum_bytes=MAX_DEPLOYMENT_STORE_BYTES,
        error_type=EffectStorageError,
        maximum_nodes=MAX_STORE_JSON_NODES,
    )
    version = _required_non_negative_int(raw, "version")
    records = _required_mapping(raw, "records")
    if len(records) > MAX_DEPLOYMENT_RECORDS:
        raise EffectLimitError(f"deployment history must not exceed {MAX_DEPLOYMENT_RECORDS} records")
    parsed = tuple(
        DeploymentRecord.from_dict(_as_mapping(record, f"deployment {key}")) for key, record in records.items()
    )
    if any(str(record.operation_id) != str(key) for key, record in zip(records, parsed, strict=True)):
        raise EffectStorageError("deployment record key does not match operation ID")
    return DeploymentSnapshot(version, parsed)


def _load_deployments(data: object) -> tuple[DeploymentSnapshot, dict[str, Any]]:
    raw = _as_mapping(data, "deployment store")
    version = _required_non_negative_int(raw, "version")
    records = _required_mapping(raw, "records")
    cleaned: dict[str, Any] = {}
    invalid = 0
    for key, value in records.items():
        try:
            validate_json_document(
                value,
                f"deployment {key}",
                maximum_bytes=MAX_DEPLOYMENT_STORE_BYTES,
                error_type=EffectStorageError,
            )
            record = DeploymentRecord.from_dict(_as_mapping(value, "deployment"))
            if str(record.operation_id) != str(key):
                raise EffectStorageError("deployment record key does not match operation ID")
            record = _normalise_legacy_deployment(record)
        except EffectStorageError:
            invalid += 1
            continue
        cleaned[str(key)] = record.to_dict()
    while len(cleaned) > MAX_DEPLOYMENT_RECORDS:
        _remove_oldest_terminal_deployment(cleaned)
    candidate = {"version": version + (1 if invalid or len(cleaned) != len(records) else 0), "records": cleaned}
    snapshot = _validate_deployments(candidate)
    if invalid:
        _LOGGER.warning("Discarded %d invalid Effect Studio deployment record(s)", invalid)
    return snapshot, candidate


def _remove_oldest_terminal_deployment(records: dict[str, Any]) -> None:
    terminal = [
        DeploymentRecord.from_dict(_as_mapping(raw, "deployment"))
        for raw in records.values()
        if _required_str(_as_mapping(raw, "deployment"), "phase")
        in {
            DeploymentPhase.CONFIRMED.value,
            DeploymentPhase.APPLIED.value,
            DeploymentPhase.UNCERTAIN.value,
            DeploymentPhase.FAILED.value,
            DeploymentPhase.INTERRUPTED.value,
            DeploymentPhase.UNKNOWN.value,
        }
    ]
    if not terminal:
        raise EffectLimitError(f"deployment history cannot exceed {MAX_DEPLOYMENT_RECORDS} active records")
    oldest = min(terminal, key=lambda record: record.updated_at)
    records.pop(str(oldest.operation_id), None)


def _normalise_legacy_deployment(record: DeploymentRecord) -> DeploymentRecord:
    if record.phase is DeploymentPhase.PENDING:
        return replace(record, phase=DeploymentPhase.COMPILING)
    if record.phase in {DeploymentPhase.INTERRUPTED, DeploymentPhase.UNKNOWN}:
        return replace(record, phase=DeploymentPhase.UNCERTAIN)
    return record


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise EffectStorageError(f"{name} must be a sequence")
    if any(not isinstance(item, str) for item in value):
        raise EffectStorageError(f"{name} must contain strings")
    return tuple(value)


def _required_non_negative_int(raw: Mapping[str, Any], key: str) -> int:
    value = _required_int(raw, key)
    if not 0 <= value <= MAX_REVISION:
        raise EffectStorageError(f"{key} must not be negative")
    return value
