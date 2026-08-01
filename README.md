# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Local BLE control of supported Govee LED strips from Home Assistant, with no cloud dependency.

## Supported Devices

All models support on/off, brightness, RGB color, color temperature, and notification-based
state readback. H617A and H617E intentionally share one capability profile and protocol
implementation.

| Feature | H617A | H617E | H6199 |
| --- | --- | --- | --- |
| Built-in scenes | 80+ mapped | H617A catalogue mapped; additional device scenes remain unmapped | Not surfaced |
| Music modes | 11 mapped modes | Same 11 modes | 4 validated modes |
| 15-segment painting | Yes | Yes | Not validated |
| Effect Studio | Static, Gradient, Sketch, Flat, Combo | Same complete surface | Not validated |
| Saved custom effects | Save, apply, rename, update, delete | Same complete surface | Not validated |
| Effect JSON import/export | Yes | Yes | No validated authoring surface |
| Sleep and wake-up timers | Yes | Yes | Not validated |
| DreamView video controls | No | No | Yes |

The bundled `custom:govee-led-ble-card` provides segment painting and the Govee Effect Studio.
Effect Studio drafts can be saved as named effects, selected from the light's effect list, and
exported or imported as portable JSON.

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
