# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

**Govee LED BLE** is a fully local Home Assistant integration for complete control of supported Govee BLE lights—without the cloud.  It connects directly over Bluetooth or through ESPHome Bluetooth proxies, with **Effect Studio** for creating custom effects.

## Device support

| Model | Status |
| --- | --- |
| **H1A42** | ✅ Supported |
| **H600A** | ✅ Supported |
| **H601C** | ✅ Supported |
| **H6046** | ✅ Supported |
| **H6072** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/486) |
| **H607C** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/511) |
| **H6076** | ✅ Supported |
| **H6097** | ✅ Supported |
| **H6099** | ✅ Supported |
| **H60A1** | ✅ Supported |
| **H60A6** | ✅ Supported |
| **H6102** | ✅ Supported |
| **H6125** | ✅ Supported |
| **H6179** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/448) |
| **H617A** | ✅ Supported |
| **H617C** | ✅ Supported |
| **H617E** | ✅ Supported |
| **H617F** | ✅ Supported |
| **H6199** | ✅ Supported |
| **H61F5** | ✅ Supported |
| **H66A0** | ✅ Supported |
| **H7020** | ✅ Supported |
| **H7025** | [🚧 Experimental](https://github.com/teh-hippo/ha-govee-led-ble/issues/451) |

To request support for another model or contribute protocol schemas, see [CONTRIBUTING.md](CONTRIBUTING.md).

On qualified H6199 revisions, Camera status shows the last report received from the camera and starts unknown until a report arrives.
Missing replies or brief Bluetooth reconnects do not change that report; this diagnostic is not a real-time connection monitor.

## Effect Studio

Effect Studio is a Home Assistant sidebar panel that gives you full control of supported devices' effect capabilities.  Explore built-in scenes, create custom effects with colours and layers, tune music and camera/video settings, and preview changes live before saving.  The panel shows the controls available for your device.

![Effect Studio custom effect editor](docs/images/effect-studio-effects.png)

![Effect Studio scene browser](docs/images/effect-studio-scenes.png)

## DreamView

On compatible revisions, H6097, H6099, H6199 and H66A0 expose DreamView group actions separately from the backlight's standalone video effects.
H6097 and H6099 support up to seven members; H66A0 supports up to ten.  Set both DreamView choices explicitly:

H607C has candidate Music DreamView membership, switch, brightness and connection controls for up to ten members.
Its group-effect recipes are not yet qualified; ordinary onboard music and paired pole/base editing are separate and available.
H607C does not expose the camera/video settings below.

```yaml
action: ha_govee_led_ble.set_dreamview_video_settings
target:
  entity_id: light.tv_backlight
data:
  apply_area: part
  content_mode: movie
```

`apply_area` accepts `all` or `part`; `content_mode` accepts `game` or `movie`.  Neither field has a default, and this action does not change group membership.

**DreamView Game/Movie is not the light's `Video: Game` / `Video: Movie` effect.**  Selecting a standalone video effect can switch off a running DreamView group.  You do not need to select that effect before enabling DreamView.

H6199 uses its own legacy group protocol and a candidate limit of five members.  Same brightness additionally requires main hardware 3.02.01 or newer and firmware 1.09.00 or newer, confirmed on the current connection.  Other group controls remain available if version queries time out, provided the advertised Pact is supported.

H6199 group replacement and deletion require a matching device acceptance reply before Home Assistant releases member ownership.  An attempted upload is not retried automatically.  A failed or unanswered change retains private recovery intent and member claims; do not assume that the old hardware group is unchanged.  `read_dreamview_group` separates locally authored metadata from anonymous device observations, and reports identity-gated reads in `unavailable_reads`.  Acceptance does not confirm membership or visible synchronisation.  These new H6199 group paths still need owner qualification.

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture, repository non-goals, and validation rules.

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
