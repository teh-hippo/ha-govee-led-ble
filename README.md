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

## Beta versions

Preview builds are published from the `segments` branch as [GitHub pre-releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository/about-releases), tagged `vX.Y.Z-beta.N`. Stable installs never see them.

To opt in, open the integration in HACS, choose **Redownload** from the three-dot menu, and enable **Show beta versions**. Turn it off and redownload to return to the stable channel.

## Configuration

The integration auto-discovers nearby supported devices.

To add manually in Home Assistant:

**Settings → Devices & Services → Add Integration → Govee LED BLE**

## Dashboards

Example stock Lovelace dashboards live in [`docs/dashboards/`](docs/dashboards/). Segment painting uses the bundled `custom:govee-led-ble-card`, not these.

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
