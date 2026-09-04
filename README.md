# Govee LED BLE for Home Assistant

[![HACS][hacs-badge]][hacs-url]
[![GitHub Release][release-badge]][release-url]
[![Validate][validate-badge]][validate-url]
[![Home Assistant][ha-badge]][ha-url]

Local BLE control and effect authoring for supported Govee lights from Home Assistant, with no cloud dependency.

## Device support

| Model | Status | Controls and limitations |
| --- | --- | --- |
| **H617A** | Supported | Power, brightness, RGB, colour temperature, 15 segments, 83 scenes, 11 music modes and Effect Studio |
| **H6199** | Supported | Power, brightness, RGB, colour temperature, 15 segments, 240 scenes, video and music modes, advanced controls and Effect Studio |
| **H617E** | Compatible | H617A-compatible controls, effects and music modes with its exact 240-scene catalogue and retained legacy scene-name compatibility; exact-model protocol documentation remains incomplete |
| **H6076** | Partial | Power, brightness, RGB and 2700–6500 K colour temperature; colour-mode readback, segments, scenes, music and Effect Studio remain unavailable |
| **H6099** | Experimental | Power, brightness, RGB, colour temperature, 14 segments, 240 scenes, 11 music modes, video controls, advanced effects and Effect Studio; awaiting owner qualification |

**Experimental** is a model-specific prerelease awaiting owner confirmation.  **Partial** has confirmed controls plus known disabled gaps.  **Compatible** has no known issue in its exposed feature set but incomplete documentation.  **Supported** is fully documented, with every known feature implemented or explicitly excluded and evidence-backed Kaitai coverage for every enabled wire path.  See [CONTRIBUTING.md](CONTRIBUTING.md) for the request, speculative-schema, prerelease and promotion process.

## Effect Studio

Effect Studio appears in the Home Assistant sidebar when a configured light supports it.  Available scenes, effects, music, video, and editing controls follow the selected device's capabilities.

Administrators can preview, edit, apply, and save supported effects.  Other authenticated users can browse scenes and compatible saved effects in read-only mode.  Saved names are also available through the standard Home Assistant light effect selector.

Home Assistant commands take priority over live previews.  Effect uploads and activation are serialised with verification and recovery where the device supports readback.  Arbitrary app-authored DIY effects cannot be imported because the app provides no supported export format.

## Upgrade notes

- An H6076 previously configured as H617A must be explicitly changed to H6076 through the integration's **Reconfigure** action.  The config entry and entity identity are preserved.
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

The integration auto-discovers exact listed models.  Experimental models are available only in their model-specific prerelease.

To add manually in Home Assistant:

**Settings → Devices & Services → Add Integration → Govee LED BLE**

Use the integration's **Configure** action to choose which Effect Studio categories and light effect names are exposed for each device.

Use **Reconfigure** to correct the selected model while preserving the existing config entry and entity identity.

## Scope, non-goals, and expert tools

The maintained product scope and per-model limitations are defined by the [device support table](#device-support).  H617A stores a gradual-colour-change boolean, but the app classifies the model as unsupported and physical comparisons found no visible effect, so the integration exposes no user-facing behaviour for it.

Wi-Fi provisioning is not a maintained integration or contributor workflow.  The decoded H6199 [`a1 11` frame](tools/ble/kaitai/h6199_wifi_provision.ksy), [reassembled body](tools/ble/kaitai/h6199_wifi_body.ksy) and [`ee 11` result](tools/ble/kaitai/h6199_wifi_result.ksy) remain as tested protocol findings.

The following are intentional non-goals for this integration:

- Wi-Fi provisioning, cloud control, and account or network setup;
- user-facing on-device timers and schedules;
- host microphone capture or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates;
- manufacturer-style animated scene previews;
- camera calibration that depends on Govee Wi-Fi or cloud services.

The repository may retain Kaitai schemas and protocol findings for non-goals without exposing runtime controls.  Onboard device-microphone modes, ordinary BLE commands, and bounded multipart effect uploads remain supported.

Additional models follow the request and qualification process in [CONTRIBUTING.md](CONTRIBUTING.md).  Cross-SKU evidence, Home Assistant quality-scale work, and restart-free integration updates remain separate programmes.

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

Exact-model contributions without captures begin under [`tools/ble/kaitai/speculative/`](tools/ble/kaitai/speculative/README.md).  Speculative schemas compile through the normal Kaitai build, but do not qualify a model as Supported.

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
