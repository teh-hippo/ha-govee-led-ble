import { html, nothing } from "lit";
import type { CheckboxControlChange } from "./checkbox-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { renderRippleEditor } from "./ripple-editor";
import type { SliderControlChange } from "./slider-control";
import type { AdvancedContent, ModelEffectCatalogue, NativeDiyLayer, NativeEffectContent, RGB } from "./types";
import "./advanced-effect-editor";
import "./checkbox-control";
import "./palette-editor";
import "./slider-control";

export function renderH60B0Editor(
  content: NativeEffectContent,
  catalogue: ModelEffectCatalogue,
  disabled: boolean,
  change: (content: NativeEffectContent, interaction?: LivePreviewInteraction) => void,
) {
  if (content.combined) {
    const combined = content.combined;
    return html`
      <govee-advanced-effect-editor .content=${{ kind: "advanced", layers: combined.effect.layers } satisfies AdvancedContent}
        .segmentCount=${8} .disabled=${disabled}
        @content-changed=${(event: CustomEvent<{ content: AdvancedContent; interaction?: LivePreviewInteraction }>) => {
          event.stopPropagation();
          change({ ...content, combined: { ...combined, effect: { layers: structuredClone(event.detail.content.layers) }, speed_index: null } }, event.detail.interaction);
        }}
      ></govee-advanced-effect-editor>
      ${renderRippleEditor(combined.ripple_layers ?? [], disabled, (ripple_layers, interaction) =>
        change({ ...content, combined: { ...combined, ripple_layers, speed_index: null } }, interaction))}
    `;
  }
  const modern = content.revision === 3;
  const single = !modern && content.family !== 13;
  return html`${content.layers.map((layer, index) => {
    if (layer.type === "paint") return nothing;
    const top = modern && index === 0;
    const bottom = modern && index === 2;
    const ripple = !single && index === 0;
    const prefix = `template:h60b0:${content.revision}:${single ? "single" : index}:`;
    const choices = (catalogue.templates ?? []).flatMap(template => {
      if (!template.id.startsWith(prefix) || template.content.kind !== "native_effect") return [];
      const seed = template.content.layers[index];
      return seed?.type === "diy" ? [{ template, seed }] : [];
    });
    const selected = choices.find(choice => choice.seed.kind === layer.kind);
    const update = (patch: Partial<NativeDiyLayer>, interaction?: LivePreviewInteraction) => {
      if (layer.type !== "diy") return;
      const layers = structuredClone(content.layers);
      layers[index] = { ...layer, ...patch };
      change({ ...content, layers, speed_index: null }, interaction);
    };
    const slider = (label: string, value: number, min: number, max: number, commit: (value: number, interaction: LivePreviewInteraction) => void, step = 1) =>
      html`<govee-slider-control .label=${label} .value=${value} .minimum=${min} .maximum=${max} .step=${step} .disabled=${disabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) => commit(event.detail.value, event.detail.interaction)}
      ></govee-slider-control>`;
    const palette = (secondary = false) => layer.type !== "diy" ? nothing : html`
      <h4>${secondary ? "Background" : "Colours"}</h4>
      <govee-palette-editor .palette=${secondary ? layer.secondary_palette ?? [] : layer.palette}
        .minColours=${secondary || modern || [5, 8].includes(layer.kind) || ripple && [2, 11, 12].includes(layer.kind) ? 1 : 2}
        .maxColours=${secondary ? 1 : 8} .disabled=${disabled}
        @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
          update({ [secondary ? "secondary_palette" : "palette"]: structuredClone(event.detail.palette) }, event.detail.interaction)}
      ></govee-palette-editor>`;
    const active = layer.type === "diy" && (modern ? layer.kind !== 1 : layer.enabled !== false);
    return html`
      <section class="card">
        <h3>${single ? "Effect" : modern ? ["Top", "Side", "Bottom"][index] : ["Ripple", "Side"][index]}</h3>
        ${top && layer.type === "diy" ? html`
          <govee-checkbox-control label="Use an independent top effect" .checked=${layer.enabled !== false} .disabled=${disabled}
            @checked-changed=${(event: CustomEvent<CheckboxControlChange>) => update({ enabled: event.detail.checked })}
          ></govee-checkbox-control>
          <p>When unchecked, the top follows the side effect.  Native DIY can activate at most two sources together.</p>
        ` : nothing}
        <label>Effect<select .value=${active ? selected?.template.id ?? "unknown" : "off"} ?disabled=${disabled || top && layer.type === "diy" && layer.enabled === false}
          @change=${(event: Event) => {
            const id = (event.target as HTMLSelectElement).value;
            if (id === "off") {
              const seed: NativeDiyLayer = {
                type: "diy", kind: modern ? 1 : 0, speed: 0, palette: [], parameters: "", parameter: top ? 50 : 0,
                flag: 0, points: [], direction: top ? 1 : 0, angle: 0, opaque: "", enabled: modern,
                secondary_palette: [], temperatures: [],
              };
              const layers = structuredClone(content.layers);
              layers[index] = seed;
              change({ ...content, layers, speed_index: null });
              return;
            }
            const choice = choices.find(candidate => candidate.template.id === id);
            if (!choice || choice.template.content.kind !== "native_effect") return;
            const layers = structuredClone(content.layers);
            layers[index] = structuredClone(choice.seed);
            change({ ...content, family: single ? choice.template.content.family : content.family, layers, speed_index: null });
          }}>
          ${!single ? html`<option value="off">Off</option>` : nothing}
          ${active && !selected ? html`<option value="unknown">Unrecognised effect</option>` : nothing}
          ${choices.map(choice => html`<option value=${choice.template.id} ?selected=${active && selected?.template.id === choice.template.id}>${choice.template.label}</option>`)}
        </select></label>
        ${layer.type !== "diy" ? html`<p>Unqualified parameters are retained until a known effect is selected.</p>` : html`
          ${top ? slider("Ripple movement speed", layer.parameter, 0, 100, (parameter, interaction) => update({ parameter }, interaction)) : nothing}
          ${ripple ? slider("Direction", layer.direction, 1, 3, (direction, interaction) => update({ direction }, interaction)) : nothing}
          ${active && !(top && layer.enabled === false) ? html`
            ${top && layer.kind === 7 ? html`
              ${slider("Colour temperature", layer.angle, 2700, 6500, (angle, interaction) => update({ angle }, interaction), 100)}
              ${slider("Brightness", layer.flag, 0, 100, (flag, interaction) => update({ flag }, interaction))}
            ` : html`
              ${slider("Speed", layer.speed, 1, 100, (speed, interaction) => update({ speed }, interaction))}
              ${bottom ? html`
                ${(layer.temperatures ?? []).map((kelvin, position) => html`
                  ${slider(`Colour temperature ${position + 1}`, kelvin, 2700, 6500, (value, interaction) =>
                    update({ temperatures: layer.temperatures!.map((current, i) => i === position ? value : current) }, interaction), 100)}
                  <button type="button" ?disabled=${disabled || layer.temperatures!.length <= 1} @click=${() =>
                    update({ temperatures: layer.temperatures!.filter((_, i) => i !== position), palette: layer.palette.filter((_, i) => i !== position) })}>Remove temperature</button>
                `)}
                <button type="button" ?disabled=${disabled || (layer.temperatures?.length ?? 0) >= 8}
                  @click=${() => update({ temperatures: [...(layer.temperatures ?? []), 4000], palette: [...layer.palette, [255, 255, 255]] })}>Add temperature</button>
              ` : palette()}
              ${layer.secondary_palette?.length ? palette(true) : nothing}
              ${modern && layer.points.length ? layer.points.map((value, position) =>
                slider(position === 0 ? "Minimum brightness" : "Maximum brightness", value, 0, 100, (next, interaction) =>
                  update({ points: layer.points.map((current, i) => i === position ? next : current) }, interaction))) : nothing}
              ${!modern && ripple ? slider("Ripple movement speed", layer.flag, 0, 100, (flag, interaction) => update({ flag }, interaction)) : nothing}
              ${modern && index === 1 && [7, 10].includes(layer.kind) ? slider("Direction", layer.direction, 1, 2, (direction, interaction) => update({ direction }, interaction)) : nothing}
              ${modern && index === 1 && [9, 13].includes(layer.kind) ? html`
                <govee-checkbox-control label="Use varied colours" .checked=${layer.flag === 1} .disabled=${disabled}
                  @checked-changed=${(event: CustomEvent<CheckboxControlChange>) => update({ flag: event.detail.checked ? 1 : 0 })}
                ></govee-checkbox-control>
              ` : nothing}
              ${single && layer.kind === 9 ? slider("Variation", layer.parameter, 1, 2, (parameter, interaction) => update({ parameter }, interaction)) : nothing}
            `}
          ` : nothing}
        `}
      </section>
    `;
  })}`;
}
