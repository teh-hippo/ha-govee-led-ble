"""Select entities for HA Govee LED BLE."""

from . import h6199_controls

PARALLEL_UPDATES = 0
H6199VideoCaptureSelect = h6199_controls.H6199VideoCaptureSelect
async_setup_entry = h6199_controls.async_setup_select_entry
