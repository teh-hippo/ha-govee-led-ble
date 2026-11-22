import { html, nothing } from "lit";

import type { LivePreviewInteraction } from "./live-preview-controller";
import "./palette-editor";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import type { NativeDiyLayer, NativeEffectContent, RGB } from "./types";
import { clonePalette } from "./ui-utils";

type Change = (content: NativeEffectContent, interaction?: LivePreviewInteraction) => void;
const LABELS: Record<number, string> = {
  12: "Retrace",
  13: "Spray",
  14: "Streamer",
  15: "Glimmer",
  16: "Star Flash",
  17: "Pile-up",
};

function choices(label: string, value: number, minimum: number, maximum: number, disabled: boolean, change: (value: number) => void) {
  return html`<label>${label}<select .value=${String(value)} ?disabled=${disabled}
    @change=${(event: Event) => change(Number((event.target as HTMLSelectElement).value))}>
    ${Array.from({ length: maximum - minimum + 1 }, (_, index) => index + minimum).map(candidate =>
      html`<option value=${candidate} ?selected=${candidate === value}>${candidate}</option>`)}
  </select></label>`;
}

export function renderH7025Editor(content: NativeEffectContent, disabled: boolean, change: Change) {
  const layer = content.layers[0];
  if (layer?.type !== "diy") return html`<p>H7025 native parameters cannot be edited from this definition.</p>`;
  const update = (patch: Partial<NativeDiyLayer>, interaction?: LivePreviewInteraction) => {
    change({ ...content, layers: [{ ...layer, ...patch }], speed_index: null }, interaction);
  };
  const paletteMin = content.preset_id === 20 || content.preset_id === 24 ? 2 : 1;
  return html`
    <section class="card">
      <h3>${LABELS[layer.kind]}</h3>
      <govee-slider-control label="Speed" .value=${layer.speed} .minimum=${0} .maximum=${100} .disabled=${disabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) =>
          update({ speed: event.detail.value }, event.detail.interaction)}
      ></govee-slider-control>
      ${layer.kind === 12 ? choices("Quantity", layer.parameter, 1, 10, disabled,
        parameter => update({ parameter })) : nothing}
      ${layer.kind === 13 ? html`
        ${choices("Injection count", layer.points[0] ?? 3, 1, 5, disabled,
          injections => update({ points: [injections, layer.points[1] ?? 3] }))}
        ${choices("Interval", layer.points[1] ?? 3, 2, 5, disabled,
          interval => update({ points: [layer.points[0] ?? 3, interval] }))}
      ` : nothing}
      ${layer.kind === 14 || layer.kind === 17
        ? choices("Direction", layer.parameter, 1, 2, disabled, parameter => update({ parameter }))
        : nothing}
      ${layer.kind === 15
        ? choices("Density", layer.parameter, 0, 2, disabled, parameter => update({ parameter }))
        : nothing}
      <h4>${layer.kind === 16 ? "Adorn colours" : "Colours"}</h4>
      <govee-palette-editor .palette=${layer.palette} .minColours=${paletteMin} .maxColours=${8} .disabled=${disabled}
        @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
          update({ palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
      ></govee-palette-editor>
      ${layer.kind === 16 ? html`
        <h4>Background colour</h4>
        <govee-palette-editor .palette=${layer.secondary_palette ?? []} .minColours=${1} .maxColours=${1}
          .disabled=${disabled}
          @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
            update({ secondary_palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
        ></govee-palette-editor>
      ` : nothing}
    </section>
  `;
}
