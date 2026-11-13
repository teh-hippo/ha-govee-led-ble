import { html, nothing } from "lit";

import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import "./palette-editor";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import type { ModelEffectCatalogue, NativeDiyLayer, NativeEffectContent, RGB } from "./types";
import { clonePalette } from "./ui-utils";

type ZoneChange = (
  index: number,
  update: Partial<NativeDiyLayer>,
  family: number,
  kind: number,
  interaction?: LivePreviewInteraction,
) => void;

export function renderH1771SectionEditor(
  content: NativeEffectContent,
  catalogue: ModelEffectCatalogue,
  disabled: boolean,
  change: ZoneChange,
) {
  return html`${content.layers.map((layer, index) => {
    if (layer.type === "paint") return nothing;
    const choices = (catalogue.templates ?? []).flatMap(template => {
      if (!template.id.startsWith(`template:h1771:${index}:`) || template.content.kind !== "native_effect") return [];
      const seed = template.content.layers[index];
      return seed?.type === "diy" ? [{ template, seed }] : [];
    });
    const selected = layer.type === "diy" && layer.enabled !== false
      ? choices.find(({ seed }) => seed.kind === layer.kind &&
          (seed.angle !== 0 || (seed.parameter === layer.parameter && seed.flag === layer.flag)))
      : undefined;
    const update = (value: Partial<NativeDiyLayer>, interaction?: LivePreviewInteraction) =>
      change(index, value, content.family, layer.kind, interaction);
    return html`
      <section class="card">
        <h3>Section ${index + 1}</h3>
        <label>Effect<select .value=${selected?.template.id ?? (layer.type === "diy" && layer.enabled === false ? "none" : "unknown")}
          ?disabled=${disabled} @change=${(event: Event) => {
            const id = (event.target as HTMLSelectElement).value;
            if (id === "none") {
              const seed = choices[0]?.seed;
              if (seed) update({ ...structuredClone(seed), enabled: false, opaque: "00" });
              return;
            }
            const choice = choices.find(candidate => candidate.template.id === id);
            if (choice) update(structuredClone(choice.seed));
          }}>
          <option value="none" ?selected=${layer.type === "diy" && layer.enabled === false}>None</option>
          ${!selected && !(layer.type === "diy" && layer.enabled === false)
            ? html`<option value="unknown" selected>Unrecognised effect</option>` : nothing}
          ${choices.map(({ template }) => html`<option value=${template.id} ?selected=${template.id === selected?.template.id}>${template.label}</option>`)}
        </select></label>
        ${layer.type === "opaque" ? html`<p>Unqualified parameters are retained until replaced.</p>` : nothing}
        ${layer.type === "diy" && layer.enabled !== false ? html`
          <govee-slider-control label="Speed" .value=${layer.speed} .minimum=${selected?.template.rate_min ?? 0}
            .maximum=${100} .disabled=${disabled}
            @value-changed=${(event: CustomEvent<SliderControlChange>) => update({ speed: event.detail.value }, event.detail.interaction)}
          ></govee-slider-control>
          ${layer.angle ? html`
            <govee-slider-control label="Brightness" .value=${layer.parameter} .minimum=${0} .maximum=${100}
              .disabled=${disabled}
              @value-changed=${(event: CustomEvent<SliderControlChange>) => update({ parameter: event.detail.value }, event.detail.interaction)}
            ></govee-slider-control>
            <govee-slider-control label="Colour temperature" .value=${layer.angle} .minimum=${1000} .maximum=${10000}
              .step=${100} .disabled=${disabled}
              @value-changed=${(event: CustomEvent<SliderControlChange>) => update({ angle: event.detail.value }, event.detail.interaction)}
            ></govee-slider-control>
          ` : html`
            <h4>Colours</h4>
            <govee-palette-editor .palette=${layer.palette} .minColours=${1} .maxColours=${8} .disabled=${disabled}
              @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                update({ palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
            ></govee-palette-editor>
            ${layer.secondary_palette?.length ? html`
              <h4>Background</h4>
              <govee-palette-editor .palette=${layer.secondary_palette} .minColours=${1} .maxColours=${1} .disabled=${disabled}
                @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                  update({ secondary_palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
              ></govee-palette-editor>
            ` : nothing}
          `}
        ` : nothing}
      </section>
    `;
  })}`;
}

export function renderNativeZoneEditor(
  content: NativeEffectContent,
  catalogue: ModelEffectCatalogue,
  disabled: boolean,
  change: ZoneChange,
) {
  const paired = content.layers.length > 1 && content.layers.length === catalogue.native_zones?.length;
  return html`${content.layers.map((layer, index) => {
    if (layer.type === "paint") return nothing;
    const family = catalogue.effects.find(candidate => candidate.family === layer.kind);
    const label = paired ? catalogue.native_zones![index].label : family?.label ?? "Effect";
    const update = (value: Partial<NativeDiyLayer>, interaction?: LivePreviewInteraction) =>
      change(index, value, content.family, layer.kind, interaction);
    const enabled = layer.type === "diy" && (layer.enabled ?? true);
    return html`
      <section class="card">
        <h3>${label}</h3>
        ${paired ? html`
          <label>Effect<select .value=${String(layer.kind)} ?disabled=${disabled} @change=${(event: Event) => {
            const kind = Number((event.target as HTMLSelectElement).value);
            const template = catalogue.templates?.find(candidate =>
              candidate.content.kind === "native_effect" &&
              candidate.content.family === kind && candidate.content.layers.length === 1);
            if (template?.content.kind !== "native_effect") return;
            const seed = structuredClone(template.content.layers[0]);
            if (seed.type === "diy") update({ ...seed, enabled: layer.type !== "diy" || (layer.enabled ?? true) });
          }}>
            ${!family ? html`<option value=${layer.kind}>Choose an effect</option>` : nothing}
            ${catalogue.effects.map(candidate => html`<option value=${candidate.family} ?selected=${candidate.family === layer.kind}>${candidate.label}</option>`)}
          </select></label>
        ` : nothing}
        ${layer.type === "opaque" ? html`<p>Unqualified parameters are retained. Select a known effect to replace them.</p>` : html`
          ${paired ? html`
            <govee-checkbox-control label="Include this effect" .checked=${enabled} .disabled=${disabled}
              @checked-changed=${(event: CustomEvent<CheckboxControlChange>) => update({ enabled: event.detail.checked })}
            ></govee-checkbox-control>
          ` : nothing}
          ${family ? html`
            ${family.variations.length > 1 ? html`
              <label>Variation<select .value=${String(layer.parameter)} ?disabled=${disabled} @change=${(event: Event) =>
                update({ parameter: Number((event.target as HTMLSelectElement).value) })}>
                ${!family.variations.some(value => value.variant === layer.parameter)
                  ? html`<option value=${layer.parameter}>Unknown variation ${layer.parameter}</option>` : nothing}
                ${family.variations.map(value => html`<option value=${value.variant} ?selected=${value.variant === layer.parameter}>${value.label}</option>`)}
              </select></label>
            ` : nothing}
            ${family.rate_min === family.rate_max ? html`<p>Speed: ${family.rate_min} (fixed)</p>` : html`
              <govee-slider-control label="Speed" .value=${layer.speed}
                .minimum=${family.rate_min} .maximum=${family.rate_max} .disabled=${disabled}
                @value-changed=${(event: CustomEvent<SliderControlChange>) => update({ speed: event.detail.value }, event.detail.interaction)}
              ></govee-slider-control>
            `}
            <h4>${family.palette_labels?.[0] ?? "Colours"}</h4>
            <govee-palette-editor .palette=${layer.palette}
              .minColours=${family.palette_min ?? catalogue.limits.palette_min}
              .maxColours=${family.palette_max ?? catalogue.limits.palette_max} .disabled=${disabled}
              @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                update({ palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
            ></govee-palette-editor>
            ${family.secondary_palette ? html`
              <h4>${family.palette_labels?.[1] ?? "Secondary colours"}</h4>
              <govee-palette-editor .palette=${layer.secondary_palette ?? []}
                .minColours=${family.secondary_palette.min} .maxColours=${family.secondary_palette.max} .disabled=${disabled}
                @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                  update({ secondary_palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
              ></govee-palette-editor>
            ` : nothing}
          ` : html`<p>Select a known effect before applying this definition.</p>`}
        `}
      </section>
    `;
  })}`;
}
