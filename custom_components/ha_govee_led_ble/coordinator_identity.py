"""Product-neutral identity context used while constructing a coordinator."""

from dataclasses import dataclass
from typing import Literal

type DeviceIdentitySource = Literal["ble", "configured"]


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
