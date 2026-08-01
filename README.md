# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Local BLE control and effect authoring for supported Govee lights from Home Assistant, with no cloud dependency.

## Supported Devices

All models support on/off, brightness, RGB colour, colour temperature, and state readback.

- **H617A**: LED Strip · 83 scenes · 11 music modes
- **H617E**: LED Strip · H617A-compatible scenes, effects and music modes
- **H6199**: DreamView T1 · 240 scenes · video and music modes · advanced controls

## Effect Studio

Govee Effect Studio is added to the Home Assistant sidebar when the integration loads.  It provides local, model-aware effect editing without a Govee cloud account.

| Model | Studio surfaces |
| --- | --- |
| H617A | Scenes, painted segments, single-layer effects, multi-layered effects, reactive music effects and advanced layered effects |
| H617E | H617A-compatible scenes, effects and reactive music effects |
| H6199 | Scenes, palette effects, reactive music effects, Movie and Game video profiles, and advanced layered effects |

H6199 video profiles keep saturation, capture area, sound effects, softness, white balance, relative brightness and blank-screen behaviour together as one reusable effect.

Administrators can edit effects and manage the shared saved-effect library.  Other authenticated users can browse scenes and compatible saved effects in read-only mode.

### Using the editor

1. Open **Govee Effect Studio** from the Home Assistant sidebar and choose a light.
2. Select a category, then choose a built-in template or saved effect.
3. Leave **Live** enabled to preview changes on the light, or disable it and use **Apply** when the draft is ready.
4. Use **Save** for a built-in default, **Save As** for a named library effect, and **Reset** to restore the catalogue version.

**Auto Save** persists committed changes to the selected built-in default or saved effect.  Editable built-ins can retain a per-light default, including native scenes, music profiles and H6199 video profiles.  The current unsaved draft is retained per device.

Saved effect names appear in the standard Home Assistant light effect selector, so dashboards, scenes, scripts and automations use the same control path as Effect Studio.  The `ha_govee_led_ble.apply_custom_effect` entity action accepts either the current saved name or its stable effect ID and supports entity, device, area and label targets.

Home Assistant light commands, scenes and automations take priority over Live previews.  Effect uploads and activation use one serialised operation, with verification and recovery on state-readable devices.

Effect definitions are model-specific.  A strip cannot return the body uploaded by the Govee app, and the app provides no supported export format, so Effect Studio cannot import an arbitrary app-authored DIY effect directly.  The protocol boundary is documented in [#89](https://github.com/teh-hippo/ha-govee-led-ble/issues/89).

## Upgrade notes

- Version 7 adds Effect Studio while retaining the standard Home Assistant light effect selector introduced in version 6.
- The standalone H617A scene-speed entity remains removed.  Edit scene speed in Effect Studio or select the native scene through the light effect selector.
- Renaming a saved effect immediately changes its selector name.  Name-based automations must use the new name; the stable effect ID does not change.
- Effect Studio stores the current saved definition rather than revision history.  Deleting a saved effect is permanent.
- Timers, the active-mode sensor and the old mode services remain removed.  Segment painting remains available through the `paint_segments`, `set_segment_color` and `set_segment_brightness` entity actions.

## Installation

### HACS (recommended)

1. Open **HACS** → three-dot menu → **Custom repositories**
2. Add `https://github.com/teh-hippo/ha-govee-led-ble` as **Integration**
3. Enable **Show beta versions** for the repository when installing a prerelease.
4. Install **Govee LED BLE** and restart Home Assistant.

### Manual

Download `ha_govee_led_ble.zip` from the GitHub release, extract it into `config/custom_components/ha_govee_led_ble/`, and restart Home Assistant.  A source checkout does not contain generated runtime modules; developers building from source must run `make package` and install the resulting ZIP.

### Updating

Restart Home Assistant after updating this integration through HACS or replacing the manual installation.  Home Assistant can reload a config entry's runtime state, but integration updates contain Python modules that are loaded when Home Assistant starts.

## Configuration

The integration auto-discovers nearby supported devices.

To add manually in Home Assistant:

**Settings → Devices & Services → Add Integration → Govee LED BLE**

Use the integration's **Configure** action to choose which Effect Studio categories and light effect names are exposed for each device.

## Scope, non-goals, and expert tools

The supported product scope is local BLE control of H617A, H617E and H6199 through Home Assistant.  The persistent H617A [`0xa3` register](https://github.com/teh-hippo/ha-govee-led-ble/issues/131) stores the app's gradual-colour-change switch, but the app explicitly classifies H617A as unsupported.  Paired physical comparisons found no visible effect, so the integration preserves the raw boolean and exposes no user-facing behaviour for it.

Wi-Fi provisioning is not a maintained integration or contributor workflow.  The decoded H6199 [`a1 11` frame](tools/ble/kaitai/h6199_wifi_provision.ksy), [reassembled body](tools/ble/kaitai/h6199_wifi_body.ksy) and [`ee 11` result](tools/ble/kaitai/h6199_wifi_result.ksy) remain as tested protocol findings.

The following are intentional non-goals for this integration:

- on-device timers;
- manufacturer-style animated scene previews;
- phone-microphone music-stream injection;
- firmware or OTA updates.

The retained music-stream schema is decode-only evidence support.  It does not provide injection or playback control.

Native H6199 camera calibration is unavailable from the current local interfaces.  The completed [camera-calibration investigation](https://github.com/teh-hippo/ha-govee-led-ble/issues/136) found that the required geometry exchange remains behind the manufacturer's trusted network service.

Cross-SKU evidence, additional device models, Home Assistant quality-scale work, and restart-free integration updates are separate future programmes.  They do not define H617A/H6199 completion.

The final [UX completion evidence matrix](docs/completion-evidence.md) records issue dispositions, cleanup metrics, retained tests and tooling, public-contract parity, and release qualification.

## Development

```bash
make build
npm --prefix frontend exec -- playwright install webkit
make check
make package
```

`make check` is the canonical local gate.  The build requires the Node.js version in `.node-version`, locked Python dependencies through [uv](https://docs.astral.sh/uv/), and Kaitai Struct Compiler 0.11.  [mise](https://mise.jdx.dev/) can install the pinned tools, but Make calls the standard tools directly.  `make package` writes the deterministic HACS archive and SHA-256 to `dist/`; byte identity is guaranteed for the pinned CI toolchain.

Physical and isolated Home Assistant qualification belongs to the published [`ha-test-harness`](https://github.com/teh-hippo/ha-test-harness).  This repository does not contain privileged lab, household identity or provisioning implementations.

The public [`ios-ble-capture` methodology](https://github.com/teh-hippo/ios-ble-capture/blob/main/docs/methodology.md) documents the iPhone capture, peer attribution and target-owned Kaitai workflow used when adding or revisiting a model.  This repository owns its schemas and protocol findings and has no build or runtime dependency on that tooling.

The production frontend has two generated outputs: `effect-studio-bootstrap.js` and `manifest.json`.  Home Assistant serves them without cache headers, while `editor-loader.js` validates the manifest and retains the stable fallback module.

The project uses [Conventional Commits](https://www.conventionalcommits.org/).

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
