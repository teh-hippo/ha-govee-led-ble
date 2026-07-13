# Example dashboards

Stock Home Assistant Lovelace dashboards for the Govee LED strip, covering every
non-segment feature of this integration. No custom cards are used here. Segment
painting has its own control surface, the integration's bundled
`custom:govee-led-ble-card` (served automatically at
`/ha_govee_led_ble/govee-led-ble-card.js`), and is out of scope for these
examples.

## Use

1. Go to Settings > Dashboards > Add dashboard > New dashboard from scratch.
2. Open the dashboard, choose Edit, then the three-dot menu > Raw configuration
   editor.
3. Paste [`govee-dashboard.yaml`](./govee-dashboard.yaml) and save.
4. Replace every `govee_strip` entity id with your own. Your device's entities
   are listed under Settings > Devices & Services > your Govee device. The
   example ids follow your light's device name, so a device named `Govee H6199`
   gives `light.govee_h6199`, `number.govee_h6199_music_sensitivity`, and so on.

For the colour favourites row, open the light's more-info colour picker and save
a few colours first; the `light-color-favorites` tile feature then shows them as
swatches.

## Views and model fit

| View | H617A | H6199 | Covers |
| --- | --- | --- | --- |
| Comfort | yes | yes | on/off, brightness, RGB colour, colour temperature, colour favourites, active-mode readout, effect preview |
| Scenes | yes | no | built-in scene effects; H6199 scene transport exists but its model catalogue is not yet surfaced |
| Music | yes | yes | all mapped H617A modes; the four validated classic modes on H6199 |
| Video | no | yes | movie/game, colour mapping, sound/softness and static white; white-balance UI mapping remains gated |
| Timers | yes | no | H617A sleep and wake-up timers (disabled by default) |
| Advanced | yes | limited | custom-effect services; H6199 authoring remains gated until its write paths are attributable |

A card that references an entity your model does not expose simply shows as
unavailable, so delete the views or rows that do not apply to your device.

## Entities and services referenced

Entities (example ids, substitute your own):

- `light.govee_strip`
- `sensor.govee_strip_active_mode`
- `image.govee_strip_effect_preview`
- `switch.govee_strip_reduce_preview_motion`
- `select.govee_strip_music_mode`
- `select.govee_strip_music_style`
- `number.govee_strip_music_sensitivity`
- `select.govee_strip_video_color_mapping`
- `switch.govee_strip_power_off_memory`
- `switch.govee_strip_sleep_timer`, `number.govee_strip_sleep_timer_duration`
- `switch.govee_strip_wake_up_timer`, `time.govee_strip_wake_up_time`

Services:

- `light.turn_on` with `brightness`, `rgb_color`, `color_temp_kelvin`, or `effect`
- `ha_govee_led_ble.set_music_mode`
- `ha_govee_led_ble.set_video_mode`
- `ha_govee_led_ble.set_white_brightness`
- `ha_govee_led_ble.save_effect`, `rename_effect`, `update_effect`, `delete_effect`, `export_effect`

## Behaviour notes

- Music mode is chosen with `select.govee_strip_music_mode`; set it to Off to
  leave music mode. Music style (Dynamic or Calm) is H617A only and affects the
  Rhythm mode. The per-mode tuning entities (sensitivity and the rest) are
  disabled by default; enable the ones you want in their entity settings.
- The `set_music_mode` service is an advanced shortcut that applies a mode with a
  one-shot sensitivity and accent colour in a single call.
- The effect preview is a server-rendered image of the selected look; it never
  talks to the device. Turn on `switch.govee_strip_reduce_preview_motion` to
  render it as a still instead of an animation.
- Saved custom effects appear in the light's effect list under their given
  names; save, rename, update, or remove them with the `save_effect`,
  `rename_effect`, `update_effect`, and `delete_effect` services (or the bundled
  segment card's Save button). `export_effect` returns a portable snapshot of a
  saved effect by its stable id.
- Colour mapping reapplies the active video mode as you change it, so switching
  it moves the strip into video mode. Saturation is supported through
  `set_video_mode`; the same service exposes the validated sound and softness
  controls.
- H617A timer entities are disabled by default. H6199 white-balance, segment, timer and power-off
  memory controls remain hidden until their model-specific mappings are validated. Static white
  (`set_white_brightness`) is separate from DreamView white balance.
