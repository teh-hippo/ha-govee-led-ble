# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Most Govee integrations rely on rate-limited cloud APIs, require developer keys, or only expose basic on/off and single-colour control over Bluetooth.  **Govee LED BLE** runs 100% locally over Bluetooth (including ESPHome proxies) with full state readback, per-segment RGB and colour temperature, onboard microphone music modes, camera and video settings, and **Effect Studio** for authoring and saving custom effects in Home Assistant.

Each device protocol is captured in [Kaitai Struct](https://kaitai.io/) (`.ksy`) schemas as the single source of truth, powering a shared compatibility layer across all supported models.

## Device support

| Model | Status |
| --- | --- |
| **H601C** | ✅ Supported |
| **H6076** | ✅ Supported |
| **H6099** | 🚧 Experimental |
| **H60A1** | ✅ Supported |
| **H60A6** | ✅ Supported |
| **H6102** | ✅ Supported |
| **H6125** | 🚧 Experimental |
| **H6179** | 🚧 Experimental |
| **H617A** | ✅ Supported |
| **H617C** | ✅ Supported |
| **H617E** | ✅ Supported |
| **H617F** | ✅ Supported |
| **H6199** | ✅ Supported |
| **H7020** | ✅ Supported |
| **H7025** | 🚧 Experimental |

To request support for another model or contribute protocol schemas, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Effect Studio

Effect Studio adds a dedicated panel to the Home Assistant sidebar for lights that support scenes, custom DIY effects, reactive music modes, or camera video profiles.  Administrators can browse exact-SKU scene catalogues, customise palettes and layers, tune onboard microphone or camera settings, and preview changes live on the light before saving.

Saved effects are stored in Home Assistant and exposed directly through the standard `light` entity effect selector for use in dashboards, scripts, and automations.  Non-admin users can browse scenes and saved effects in read-only mode.

H60A1 and H60A6 include their exact-model scene catalogues and DIY effects.  H60A6 also supports native layered effects and 133-point paint, with independent **Panel enabled** and **Ring enabled** switches and a **Power-on behaviour** select.  These additional entities are hidden by default; enabling a zone does not switch on master power.  Newly added ceiling-light effect and setting paths still need owner confirmation on hardware.

The `ha_govee_led_ble.paint_segments` action accepts `rgb_scale` from 0 to 100, applied once to the unscaled RGB groups supplied in that request.  Zero paints black rather than switching power off.  This is static RGB composition, not native ring brightness; retained RGB cannot safely recover native-white intent after a disconnect, so no separate ring-scale number is exposed.

![Effect Studio custom effect editor](docs/images/effect-studio-effects.png)

![Effect Studio scene browser](docs/images/effect-studio-scenes.png)

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=teh-hippo&repository=ha-govee-led-ble&category=integration)

1. Open **HACS** in Home Assistant and search for **Govee LED BLE**.
2. Download **Govee LED BLE** and restart Home Assistant.
3. Supported lights are discovered automatically over Bluetooth, or can be added via **Settings → Devices & Services → Add Integration → Govee LED BLE**.

### Manual

Download `ha_govee_led_ble.zip` from the [latest GitHub release][release-url], extract it into `config/custom_components/ha_govee_led_ble/`, and restart Home Assistant.

## Development

```bash
make build
make check
make package
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture, Kaitai protocol schemas, repository non-goals, and validation rules.

## License

MIT

[hacs-badge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/teh-hippo/ha-govee-led-ble
[release-url]: https://github.com/teh-hippo/ha-govee-led-ble/releases
[validate-badge]: https://img.shields.io/github/actions/workflow/status/teh-hippo/ha-govee-led-ble/validate.yml?branch=master&label=validate
[validate-url]: https://github.com/teh-hippo/ha-govee-led-ble/actions/workflows/validate.yml
[ha-badge]: https://img.shields.io/badge/HA-2026.9%2B-blue.svg
[ha-url]: https://www.home-assistant.io
