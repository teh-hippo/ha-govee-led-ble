# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

**Govee LED BLE** provides fully local Home Assistant control of supported Govee BLE lights.
Connect over Bluetooth or ESPHome Bluetooth proxies, and create custom effects with **Effect Studio**.

## Device support

| Model | Status |
| --- | --- |
| **H1A42** | ✅ Supported |
| **H1771** | ✅ Supported |
| **H600A** | ✅ Supported |
| **H601C** | ✅ Supported |
| **H6022** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/622) |
| **H6046** | ✅ Supported |
| **H6053** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/662) |
| **H605C** | ✅ Supported |
| **H6072** | ✅ Supported |
| **H607C** | ✅ Supported |
| **H6076** | ✅ Supported |
| **H6093** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/623) |
| **H6097** | ✅ Supported |
| **H6099** | ✅ Supported |
| **H60A1** | ✅ Supported |
| **H60A6** | ✅ Supported |
| **H60B0** | ✅ Supported |
| **H60B2** | ✅ Supported |
| **H6102** | ✅ Supported |
| **H6117** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/537) |
| **H612A** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/687) |
| **H6125** | ✅ Supported |
| **H6127** | ✅ Supported |
| **H6138** | ✅ Supported |
| **H6139** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/705) |
| **H6159** | ✅ Supported |
| **H6179** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/448) |
| **H617A** | ✅ Supported |
| **H617C** | ✅ Supported |
| **H617E** | ✅ Supported |
| **H617F** | ✅ Supported |
| **H618A** | ✅ Supported |
| **H6181** | ✅ Supported |
| **H6182** | ✅ Supported |
| **H619A** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/567) |
| **H6199** | ✅ Supported |
| **H61E5** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/731) |
| **H61F5** | ✅ Supported |
| **H1AB2** | ✅ Supported |
| **H66A0** | ✅ Supported |
| **H8604** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/688) |
| **H7020** | ✅ Supported |
| **H7025** | ✅ Supported |
| **H705A** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/596) |

To request another model or suggest a device-specific fix, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Effect Studio

Effect Studio is a Home Assistant sidebar panel showing your device's available effect controls.
Explore built-in scenes, create effects with colours and layers, tune music and camera/video settings, and preview changes live before saving.
Studio follows Home Assistant permissions for each light.
Read permission allows viewing; control permission also allows Apply and Live preview.
Shared library and default changes remain administrator-only.

Starting a new effect requires a recoverable static appearance.
Effect off restores that appearance, including area and segment colours, even after switching effects.
Some devices can recover retained static colours and levels while an effect is active, including after a restart.
If recovery is unavailable, establish a complete static appearance through the integration first.
Completed static writes can establish that appearance on write-only devices, but Live preview may require independent readback.
Disabling Live or closing the editor restores the appearance owned by the preview; explicit Apply or newer lighting controls take precedence.
Restoring a previously off light may briefly illuminate it before turning it off again.

On H6093, **Initialise projector lighting** replaces the current appearance to establish a recovery baseline.
It turns the projector on at full brightness, sets both aurora patterns blue and sets the stars to 50% with flicker and movement off.
Aurora movement controls physical motion separately from pattern speed.
Local sound playback pauses or resumes the selected sound; Local sound mode controls device-wide sound enablement.

Choose **Canvas** to paint native logical segments and save complete colour compositions for recall.
New canvases and **Clear all** set every segment Off (black), so you can paint only the segments you want lit and save the complete layout.
Compositions store only RGB colours and their input scale.
Apply them through ordinary static controls.

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

Install [mise](https://mise.jdx.dev/getting-started.html) and run `make bootstrap`.
See [contributor guidance](CONTRIBUTING.md#development) for build, test and acceptance steps.

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
