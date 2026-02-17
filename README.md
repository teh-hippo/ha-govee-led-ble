# Govee BLE Lights for Home Assistant

[![CI](https://github.com/teh-hippo/govee_ble_lights/actions/workflows/ci.yml/badge.svg)](https://github.com/teh-hippo/govee_ble_lights/actions/workflows/ci.yml)

A Home Assistant custom integration for controlling Govee LED strips via Bluetooth Low Energy (BLE).

## Supported Devices

| Model | Name | Features |
|-------|------|----------|
| H617A | LED Strip | Scenes, RGB, Color Temp |
| H6199 | DreamView T1 | Video Sync, Music Modes, RGB, Color Temp, State Reading |

## Features

- **On/Off** control
- **Brightness** adjustment (0-100%)
- **RGB Color** — full color control via segmented BLE mode
- **Color Temperature** — 2000K–9000K (converted to RGB)
- **Scenes** — 80+ cloud scenes for H617A (sunrise, sunset, rainbow, etc.)
- **Video Sync** — camera-based TV ambient lighting (H6199: movie & game modes)
- **Music Modes** — sound-reactive lighting (H6199: energic, rhythm, spectrum, rolling)
- **State Reading** — real-time device state via BLE notify (H6199)
- **BLE Auto-Discovery** — automatically detects Govee devices nearby

## Installation (HACS)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/teh-hippo/govee_ble_lights` as an **Integration**
4. Search for "Govee BLE Lights" and install
5. Restart Home Assistant

## Configuration

Once installed, the integration will automatically discover nearby Govee BLE devices. You can also add devices manually:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Govee BLE Lights"
3. Enter the BLE address and select the device model

## BLE Troubleshooting

- Ensure your Home Assistant host has a Bluetooth adapter
- The device must be within BLE range (~10m line of sight)
- Only one controller can be connected to a BLE device at a time — close the Govee app before using HA
- If the device is unresponsive, power cycle it and restart HA
- Check **Settings → System → Logs** for BLE connection errors

## H6199 UAT Harness

For repeatable hardware checks, run:

```bash
python scripts/h6199_harness.py \
  --base-url http://homeassistant.local:8123 \
  --token "<HA_LONG_LIVED_TOKEN>" \
  --light-entity-id light.govee_h6199 \
  --capture-region-entity-id select.govee_h6199_video_capture_region \
  --video-saturation-entity-id number.govee_h6199_video_saturation \
  --music-sensitivity-entity-id number.govee_h6199_music_sensitivity
```

It executes a fixed scenario (video movie -> video game/part -> music spectrum -> off), polls HA state until convergence, and writes a JSON report in `artifacts/`.

## Developer Preflight (before push/release)

Run the same local checks used by CI:

```bash
uv run ruff check custom_components/ tests/
uv run ruff format --check custom_components/ tests/
uv run coverage run -m pytest tests/ -v --tb=short
uv run coverage report --include="custom_components/govee_ble_lights/*" --fail-under=90
```

## License

MIT
