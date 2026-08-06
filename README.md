# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Local BLE control of supported Govee LED strips from Home Assistant, with no cloud dependency.

## Supported Devices

All models support on/off, brightness, RGB color, color temperature, and notification-based
state readback.

- **H617A / H617E**: LED strips · 80+ mapped scenes · music mode · 15-segment painting · Effect Studio
- **H6199**: DreamView T1 · video and music modes · advanced controls

H617A and H617E intentionally share one capability profile and protocol implementation. H617E
can use the mapped H617A scene catalogue; additional scenes exposed only by the H617E vendor app
remain unmapped.

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

The integration auto-discovers nearby supported devices and controls them locally with BLE
writes plus notification-based state readback. H617A and H617E release their BLE connection
three seconds after the last Home Assistant command, allowing sequential handoff to the Govee
app; a later Home Assistant command reconnects automatically after the app disconnects. The
controller accepts only one BLE client at a time, so simultaneous Home Assistant/app ownership
is not supported or implied. H6199 retains its existing connection lifecycle.

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
