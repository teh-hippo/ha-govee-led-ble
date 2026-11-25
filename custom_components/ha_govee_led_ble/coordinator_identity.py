"""Product-neutral identity context used while constructing a coordinator."""

from dataclasses import dataclass, field
from typing import Literal

type DeviceIdentitySource = Literal["ble", "configured"]
type PactIdentity = tuple[int, int]


@dataclass(frozen=True, slots=True)
class InitialDeviceIdentity:
    firmware: str | None = None
    firmware_source: DeviceIdentitySource | None = None
    hardware: str | None = None
    hardware_source: DeviceIdentitySource | None = None
    pact_type: int | None = None
    pact_code: int | None = None

    @property
    def bootstrap_firmware(self) -> str | None:
        return self.firmware

    @property
    def bootstrap_hardware(self) -> str | None:
        return self.hardware

    @property
    def bootstrap_pact_type(self) -> int | None:
        return self.pact_type

    @property
    def bootstrap_pact_code(self) -> int | None:
        return self.pact_code

    def __post_init__(self) -> None:
        if self.firmware_source is not None and self.firmware is None:
            raise ValueError("Firmware source requires firmware")
        if self.hardware_source is not None and self.hardware is None:
            raise ValueError("Hardware source requires hardware")
        if (self.pact_type is None) != (self.pact_code is None):
            raise ValueError("Pact type and code must be supplied together")
        if self.pact_type is not None and (
            type(self.pact_type) is not int
            or type(self.pact_code) is not int
            or self.pact_type < 0
            or self.pact_code < 0
        ):
            raise ValueError("Pact identity must be non-negative integers")


@dataclass(slots=True)
class PactIdentityState:
    advertised_pacts: set[PactIdentity] = field(default_factory=set)
    advertisement_observations: dict[str, tuple[float, frozenset[PactIdentity]]] = field(default_factory=dict)
    marker_pact: PactIdentity | None = None
    last_marker_pact: PactIdentity | None = None
    connection_pacts: set[PactIdentity] = field(default_factory=set)
    subscription_advertised_pact: PactIdentity | None = None
    query_result: str | None = None
    marker_seen: bool = False
    conflict: bool = False
    invalid_version_seen: bool = False
