import { html, nothing } from "lit";
import type { LivePreviewInteraction } from "./live-preview-controller";
import type { SliderControlChange } from "./slider-control";
import type { RGB, RippleLayer } from "./types";
import "./palette-editor";
import "./slider-control";

export function renderRippleEditor(
  layers: RippleLayer[],
  disabled: boolean,
  change: (layers: RippleLayer[], interaction?: LivePreviewInteraction) => void,
) {
  return html`${layers.map((layer, index) => {
    const update = (patch: Partial<RippleLayer>, interaction?: LivePreviewInteraction) =>
      change(layers.map((current, position) => position === index ? { ...structuredClone(current), ...patch } : structuredClone(current)), interaction);
    return html`
      <section class="card">
        <h3>Ripple layer ${index + 1}</h3>
        <p>Effect ${layer.effect}.  Header and unqualified parameters are retained.</p>
        ${layer.palette.length ? html`<govee-palette-editor .palette=${layer.palette} .minColours=${1}
          .maxColours=${Math.max(8, layer.palette.length)} .disabled=${disabled}
          @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
            update({ palette: structuredClone(event.detail.palette) }, event.detail.interaction)}
        ></govee-palette-editor>` : nothing}
        ${(["movement_speed", "colour_speed"] as const).map(field => html`
          <govee-slider-control .label=${field === "movement_speed" ? "Ripple movement speed" : "Ripple colour speed"}
            .value=${layer[field]} .minimum=${0} .maximum=${255} .disabled=${disabled}
            @value-changed=${(event: CustomEvent<SliderControlChange>) => update({ [field]: event.detail.value }, event.detail.interaction)}
          ></govee-slider-control>
        `)}
      </section>
    `;
  })}`;
}
