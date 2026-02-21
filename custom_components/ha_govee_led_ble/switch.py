"""Switch entities for HA Govee LED BLE."""

from __future__ import annotations

from . import h6199_controls

PARALLEL_UPDATES = 0
H6199ParameterSwitch = h6199_controls.H6199ParameterSwitch
async_setup_entry = h6199_controls.async_setup_switch_entry
