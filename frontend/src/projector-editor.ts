import { html, nothing } from "lit";

import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { renderNativeLayerControls } from "./native-layer-controls";
import "./palette-editor";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import type { NativeEffectContent, ProjectorLayer, ProjectorSource, RGB } from "./types";

export function renderProjectorEditor(
  content: NativeEffectContent,
  disabled: boolean,
  change: (content: NativeEffectContent, interaction?: LivePreviewInteraction) => void,
) {
  const layers = content.projector_layers ?? [];
  const update = (index: number, patch: Partial<ProjectorLayer>, interaction?: LivePreviewInteraction) => {
    const updated = structuredClone(layers);
    updated[index] = { ...updated[index], ...patch };
    change({ ...content, projector_layers: updated, speed_index: null }, interaction);
  };
  const slider = (
    label: string,
    value: number,
    commit: (value: number, interaction: LivePreviewInteraction) => void,
    maximum = 100,
  ) => html`
    <govee-slider-control .label=${label} .value=${value} .minimum=${0} .maximum=${Math.max(maximum, value)} .disabled=${disabled}
      @value-changed=${(event: CustomEvent<SliderControlChange>) => commit(event.detail.value, event.detail.interaction)}
    ></govee-slider-control>
  `;
  const checkbox = (label: string, value: boolean, commit: (value: boolean) => void) => html`
    <govee-checkbox-control .label=${label} .checked=${value} .disabled=${disabled}
      @checked-changed=${(event: CustomEvent<CheckboxControlChange>) => commit(event.detail.checked)}
    ></govee-checkbox-control>
  `;
  const sourceEditor = (index: number, key: "coarse" | "fine", source: ProjectorSource, label: string) => {
    const sourceChange = (patch: Partial<ProjectorSource>, interaction?: LivePreviewInteraction) =>
      update(index, { [key]: { ...source, ...patch } }, interaction);
    return html`
      <section class="card">
        <h4>${label}</h4>
        ${checkbox("Enabled", source.enabled, enabled => sourceChange({ enabled }))}
        ${slider("Brightness", source.brightness, (brightness, interaction) => sourceChange({ brightness }, interaction))}
        <label>Pattern<select .value=${String(source.pattern)} ?disabled=${disabled} @change=${(event: Event) =>
          sourceChange({ pattern: Number((event.target as HTMLSelectElement).value) })}>
          ${![1, 2, 3, 4].includes(source.pattern) ? html`<option value=${source.pattern}>Unrecognised pattern</option>` : nothing}
          ${["Fade", "Breathe", "Flash", "Colour flow"].map((label, value) =>
            html`<option value=${value + 1} ?selected=${source.pattern === value + 1}>${label}</option>`)}
        </select></label>
        ${slider("Effect speed", source.speed, (speed, interaction) => sourceChange({ speed }, interaction))}
        <govee-palette-editor .palette=${source.palette} .minColours=${1} .maxColours=${8} .disabled=${disabled}
          @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
            sourceChange({ palette: structuredClone(event.detail.palette) }, event.detail.interaction)}
        ></govee-palette-editor>
      </section>
    `;
  };
  return html`${layers.map((layer, index) => {
    const starsChange = (patch: Partial<ProjectorLayer["stars"]>, interaction?: LivePreviewInteraction) =>
      update(index, { stars: { ...layer.stars, ...patch } }, interaction);
    return html`
      <section class="card">
        <h3>Projector layer ${index + 1}</h3>
        ${renderNativeLayerControls(layers, index, disabled, projector_layers =>
          change({ ...content, projector_layers, speed_index: null }))}
        ${slider("Aurora movement", layer.movement_speed, (movement_speed, interaction) => update(index, { movement_speed }, interaction))}
        <label>Direction<select .value=${String(layer.direction)} ?disabled=${disabled} @change=${(event: Event) =>
          update(index, { direction: Number((event.target as HTMLSelectElement).value) })}>
          <option value="0" ?selected=${layer.direction === 0}>Up</option>
          <option value="1" ?selected=${layer.direction === 1}>Down</option>
        </select></label>
        ${checkbox("Separate coarse and fine colours", layer.fine !== null, separate =>
          update(index, { fine: separate ? structuredClone(layer.coarse) : null }))}
        ${sourceEditor(index, "coarse", layer.coarse, layer.fine ? "Coarse aurora" : "Aurora")}
        ${layer.fine ? sourceEditor(index, "fine", layer.fine, "Fine aurora") : nothing}
        <h4>Stars</h4>
        ${checkbox("Stars enabled", layer.stars.enabled, enabled => starsChange({ enabled }))}
        ${slider("Star brightness", layer.stars.brightness, (brightness, interaction) => starsChange({ brightness }, interaction))}
        ${checkbox("Flicker", layer.stars.flicker_enabled, flicker_enabled => starsChange({ flicker_enabled }))}
        ${slider("Flicker speed", layer.stars.flicker_speed, (flicker_speed, interaction) => starsChange({ flicker_speed }, interaction))}
        ${checkbox("Movement", layer.stars.movement_enabled, movement_enabled => starsChange({ movement_enabled }))}
        ${slider("Star movement speed", layer.stars.movement_speed, (movement_speed, interaction) => starsChange({ movement_speed }, interaction))}
        ${layers.length > 1 ? slider("Duration", layer.duration, (duration, interaction) => update(index, { duration }, interaction), 65535) : nothing}
      </section>
    `;
  })}`;
}
