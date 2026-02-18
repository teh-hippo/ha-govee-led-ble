# Govee BLE Lights for Home Assistant

[![CI](https://github.com/teh-hippo/govee_ble_lights/actions/workflows/ci.yml/badge.svg)](https://github.com/teh-hippo/govee_ble_lights/actions/workflows/ci.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA](https://img.shields.io/badge/HA-2024.12%2B-blue.svg)](https://www.home-assistant.io)

Control Govee LED strips via Bluetooth Low Energy (BLE) from Home Assistant.

## Supported Devices

| Model | Name | Scenes | Video/Music Modes | State Reading |
|-------|------|:------:|:-----------------:|:-------------:|
| H617A | LED Strip | ✅ 80+ | — | — |
| H6199 | DreamView T1 | — | ✅ | ✅ |

Both models support on/off, brightness, RGB color, and color temperature (2000K–9000K).

## Installation

### HACS (recommended)

1. Open **HACS** → three-dot menu → **Custom repositories**
2. Add `https://github.com/teh-hippo/govee_ble_lights` as **Integration**
3. Install **Govee BLE Lights** and restart Home Assistant

### Manual

Copy `custom_components/govee_ble_lights/` into your HA `custom_components/` directory and restart.

## Setup

The integration auto-discovers nearby Govee BLE devices. To add manually:

**Settings → Devices & Services → Add Integration → Govee BLE Lights**

## Troubleshooting

- Ensure your HA host has a Bluetooth adapter
- Device must be in BLE range (~10 m line of sight)
- Close the Govee app first — only one BLE controller can connect at a time
- Power-cycle the device and restart HA if unresponsive
- Check **Settings → System → Logs** for BLE errors

## Development

### Preflight checks

```bash
uv run ruff check custom_components/ tests/
uv run ruff format --check custom_components/ tests/
uv run coverage run -m pytest tests/ -v --tb=short
uv run coverage report --include="custom_components/govee_ble_lights/*" --fail-under=90
```

### Releasing

Push a semver tag to trigger the release workflow:

```bash
git tag v1.4.0
git push origin v1.4.0
```

### H6199 UAT harness

For repeatable hardware validation against a live HA instance:

```bash
python scripts/h6199_harness.py \
  --base-url http://homeassistant.local:8123 \
  --token "<HA_LONG_LIVED_TOKEN>" \
  --light-entity-id light.govee_h6199 \
  --capture-region-entity-id select.govee_h6199_video_capture_region \
  --video-saturation-entity-id number.govee_h6199_video_saturation \
  --music-sensitivity-entity-id number.govee_h6199_music_sensitivity
```

## License

MIT
