"""Number entities for HA Govee LED BLE."""

from __future__ import annotations

from . import h6199_controls

PARALLEL_UPDATES = 0
H6199ParameterNumber = h6199_controls.H6199ParameterNumber
async_setup_entry = h6199_controls.async_setup_number_entry
