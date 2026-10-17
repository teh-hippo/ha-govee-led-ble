# H7020 support

## Request and known context

The H7020 is an outdoor string light with fifteen RGBIC bulbs that also carry a warm-white channel.  It advertises as `Govee_H7020_*` with Govee manufacturer data `ec 00 01 01 01`, which the shared parser reads as Pact 1/1, broadcast version 2, without encryption.  Installation and promotion follow [CONTRIBUTING.md](../CONTRIBUTING.md).

## Research findings

| Surface | Evidence | Disposition |
| --- | --- | --- |
| Identity | `Govee_H7020_*` advertisement name; Pact 1/1, plaintext | Four standard name prefixes; auto-discovered |
| Power | Shared `33 01` frame | H617A command grammar |
| Brightness | Owner-confirmed on the device: the register is a percentage.  A 0–255 encoding left full brightness visibly dim.  An H7020 owner in [homebridge-govee #570](https://github.com/homebridge-plugins/homebridge-govee/issues/570) fixed brightness the same way, by disabling 0–254 scaling | Percent `33 04`; no `brightness_wire_range` |
| Static colour | Shared `33 05 15 01` static write with the fifteen-bit whole-device mask `0x7fff` | Whole-string RGB only |
| Colour temperature | Warm-white channel driven by the Kelvin field of the same static write; the app reports 2300 K to 6700 K in homebridge-govee #570 | 2300–6700 K |
| Readback | `aa 01` and `aa 04` replies on the H617A status root; power is required at setup | Power, brightness, firmware and hardware |

## Candidate support scope

Power, percent brightness, whole-string RGB and 2300–6700 K colour temperature, with power and brightness readback.

Colour-mode readback, per-bulb segments, segment brightness, scenes, music and Effect Studio remain unavailable until each is confirmed on the device.  The fifteen bulbs suggest fifteen segments, but no segment page or per-bulb write has been observed.

## Model-specific changes and owner checks

- `H7020` profile in `const.py`, marked Partial, with H617A command and status grammars.
- Manifest name matchers and BLE discovery.
- Owner checks on a Pact 1/1 device through an ESPHome Bluetooth proxy: power, brightness at full range, RGB and colour temperature work.  Firmware and hardware versions were not recorded.
