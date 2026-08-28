import { html, nothing, type TemplateResult } from "lit";

import {
  ADVANCED_HELP_CONTENT,
  type AdvancedHelpKey,
} from "./advanced-help";
import {
  isKnownSelectionType,
  KNOWN_SELECTION_TYPES,
} from "./advanced-effect-model";
import {
  DISTRIBUTION_COLOUR_FIELDS,
  FILL_PATTERN_LABELS,
  fillPatternParameters,
} from "./advanced-effect-editor-model";
import "./info-control";
import type { SliderControlChange } from "./slider-control";
import type { EffectLayer } from "./types";
import { clampInteger } from "./ui-utils";

export {
  FILL_PATTERN_LABELS,
  FILL_PATTERN_PARAMETERS,
  fillPatternParameters,
  type FillPatternParameter,
  type FillPatternParameterKey,
} from "./advanced-effect-editor-model";

export function renderFillPatternControls(
  layer: EffectLayer,
  disabled: boolean,
  update: (update: Partial<EffectLayer["selection"]>) => void,
): TemplateResult {
  const selection = layer.selection;
  const knownType = isKnownSelectionType(selection.type);
  const parameters = fillPatternParameters(selection.type);
  return html`
    <div class="fill-pattern-controls parameter-stack">
      <div class="subsection-heading">
        <h4>Fill Pattern</h4>
        ${renderAdvancedHelp("fillPattern")}
      </div>
      <label class="field">
        ${renderFieldLabel("Type", "fillPatternType")}
        <select
          aria-label="Fill pattern type"
          .value=${knownType ? String(selection.type) : ""}
          ?disabled=${disabled}
          @change=${(event: Event) => update({ type: Number((event.target as HTMLSelectElement).value) })}
        >
          ${knownType
            ? nothing
            : html`<option value="" disabled .selected=${true}>Choose a type</option>`}
          ${KNOWN_SELECTION_TYPES.map((value) => html`
            <option value=${value} .selected=${selection.type === value}>${FILL_PATTERN_LABELS[value]}</option>
          `)}
        </select>
      </label>
      ${parameters.map(([key, label, help]) =>
        renderNumberField(
          label,
          selection[key],
          (value) => update({ [key]: value }),
          disabled,
          { help },
        ),
      )}
    </div>
  `;
}

export function renderDistribution(
  layer: EffectLayer, disabled: boolean, updateDistribution: (update: Partial<EffectLayer["distribution"]>) => void, updateLayer: (update: Partial<EffectLayer>) => void,
): TemplateResult {
  const method = layer.distribution.method;
  const knownMethod = method >= 0 && method <= 2;
  return html`
    <section class="card">
      <div class="section-heading">
        <h3 class="section-title">Distribution</h3>
        ${renderAdvancedHelp("distribution")}
      </div>
      <div class="parameter-stack">
        <label class="field">
          ${renderFieldLabel("Method", "distributionMethod")}
          <select
            .value=${knownMethod ? String(method) : ""}
            ?disabled=${disabled}
            @change=${(event: Event) => updateDistribution({ method: Number((event.target as HTMLSelectElement).value) })}
          >
            ${knownMethod
              ? nothing
              : html`<option value="" disabled .selected=${true}>Choose a method</option>`}
            <option value="0">Unified</option>
            <option value="1">By IC</option>
            <option value="2">By Segment</option>
          </select>
        </label>
        ${method === 1 || method === 2
          ? html`
              <label class="field">
                <span>Direction</span>
                <select
                  .value=${layer.distribution.backwards ? "backwards" : "forwards"}
                  ?disabled=${disabled}
                  @change=${(event: Event) => updateDistribution({
                    backwards: (event.target as HTMLSelectElement).value === "backwards",
                  })}
                >
                  <option value="forwards">Forward</option>
                  <option value="backwards">Backward</option>
                </select>
              </label>
            `
          : nothing}
        <div class="parameter-grid">
          ${DISTRIBUTION_COLOUR_FIELDS.map((field) =>
            renderRangeField(
              field.label,
              layer[field.key],
              (value) => updateLayer({ [field.key]: value }),
              disabled,
              field.help,
            ),
          )}
        </div>
      </div>
    </section>
  `;
}

export function renderRangeField(
  label: string,
  value: number,
  changed: (value: number) => void,
  disabled: boolean,
  help?: AdvancedHelpKey,
): TemplateResult {
  return html`
    <govee-slider-control
      .label=${label}
      .value=${value}
      .minimum=${0}
      .maximum=${255}
      .valueText=${String(value)}
      .hideValueText=${true}
      .disabled=${disabled}
      @value-changed=${(event: CustomEvent<SliderControlChange>) =>
        changed(event.detail.value)}
    >
      ${help ? renderAdvancedHelp(help, "help") : nothing}
    </govee-slider-control>
  `;
}

export function renderNumberField(
  label: string,
  value: number,
  changed: (value: number) => void,
  disabled: boolean,
  options: {
    minimum?: number;
    maximum?: number;
    help?: AdvancedHelpKey;
  } = {},
): TemplateResult {
  const {
    minimum = 0,
    maximum = 255,
    help,
  } = options;
  return html`
    <label class="field">
      ${renderFieldLabel(label, help)}
      <input
        type="number"
        min=${minimum}
        max=${maximum}
        .value=${String(value)}
        ?disabled=${disabled}
        @change=${(event: Event) => changed(clampInteger(Number((event.target as HTMLInputElement).value), minimum, maximum))}
      />
    </label>
  `;
}

function renderFieldLabel(
  label: string,
  help?: AdvancedHelpKey,
): TemplateResult {
  return html`
    <span class="field-label-with-help">
      <span>${label}</span>
      ${help ? renderAdvancedHelp(help) : nothing}
    </span>
  `;
}

export function renderAdvancedHelp(
  key: AdvancedHelpKey,
  slot?: string,
): TemplateResult {
  const content = ADVANCED_HELP_CONTENT[key];
  return html`
    <govee-info-control
      slot=${slot ?? nothing}
      .label=${content.label}
      .text=${content.text}
    ></govee-info-control>
  `;
}
