# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Local BLE control of supported Govee LED strips from Home Assistant — no cloud dependency.

## Supported Devices

All models support on/off, brightness, RGB color, color temperature, and state readback.

- **H617A** — LED Strip · 80+ scenes · music mode
- **H6199** — DreamView T1 · video & music modes · advanced controls

## Installation

### HACS (recommended)

1. Open **HACS** → three-dot menu → **Custom repositories**
2. Add `https://github.com/teh-hippo/ha-govee-led-ble` as **Integration**
3. Install **Govee LED BLE** and restart Home Assistant

### Manual

Copy `custom_components/ha_govee_led_ble/` into your HA `custom_components/` directory and restart.

## Configuration

The integration auto-discovers nearby supported devices.

To add manually in Home Assistant:

**Settings → Devices & Services → Add Integration → Govee LED BLE**

## Development

```bash
bash scripts/check.sh
```

Requires [uv](https://docs.astral.sh/uv/). Uses [Conventional Commits](https://www.conventionalcommits.org/).

## License

MIT

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/teh-hippo/ha-govee-led-ble
[release-url]: https://github.com/teh-hippo/ha-govee-led-ble/releases
[validate-badge]: https://img.shields.io/github/actions/workflow/status/teh-hippo/ha-govee-led-ble/validate.yml?branch=master&label=validate
[validate-url]: https://github.com/teh-hippo/ha-govee-led-ble/actions/workflows/validate.yml
[ha-badge]: https://img.shields.io/badge/HA-2026.3%2B-blue.svg
[ha-url]: https://www.home-assistant.io
