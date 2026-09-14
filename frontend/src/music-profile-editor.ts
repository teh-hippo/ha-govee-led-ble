import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import { live } from "lit/directives/live.js";

import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import "./info-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { reactiveParameterValueText } from "./effect-editor-model";
import { recentColour } from "./recent-colours";
import "./single-colour-field";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import {
  cloneMusicProfileContent,
  MUSIC_STYLE_HELP,
  musicStyleCalm,
  musicStyleValue,
} from "./profile-model";
import {
  studioBaseStyles,
  studioCardStyles,
  studioFormStyles,
} from "./studio-styles";
import type {
  JsonObject,
  ModelEffectCatalogue,
  MusicProfileContent,
  MusicParameterSpec,
  RGB,
} from "./types";
import { clampInteger, cloneRgb } from "./ui-utils";

type OwnedMusicParameterKey =
  | "point"
  | "gradient"
  | "relative_brightness"
  | "key_count"
  | "direction"
  | "segment_count"
  | "speed";

type FountainDirection = "clockwise" | "two_way" | "counterclockwise";

const FOUNTAIN_DIRECTIONS: ReadonlyArray<{
  id: FountainDirection;
  label: string;
}> = [
  { id: "clockwise", label: "Clockwise" },
  { id: "two_way", label: "Two-way" },
  { id: "counterclockwise", label: "Counterclockwise" },
];

export interface MusicModeChange {
  mode: string;
}

export class GoveeMusicProfileEditor extends LitElement {
  @property({ attribute: false })
  public content?: MusicProfileContent;

  @property({ attribute: false })
  public catalogue?: ModelEffectCatalogue;

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Boolean })
  public modeSelectionEnabled = false;

  private lastFixedColour?: RGB;
  private interaction: LivePreviewInteraction = "committed";
  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("content") && this.content?.colour != null) {
      this.lastFixedColour = cloneRgb(this.content.colour);
    }
  }

  protected render() {
    if (!this.content) {
      return nothing;
    }

    const sensitivityMinimum = this.catalogue?.limits.music_sensitivity_min ?? 0;
    const sensitivityMaximum = this.catalogue?.limits.music_sensitivity_max ?? 100;
    const sensitivity = clampInteger(
      this.content.sensitivity,
      sensitivityMinimum,
      sensitivityMaximum,
    );
    const colourMode = this.content.colour === null ? "automatic" : "fixed";
    const fixedColour = this.content.colour ?? this.lastFixedColour ?? recentColour(0);

    return html`
      <section class="card">
        <div class="parameter-stack">
          ${this.renderModeSelector()}
          ${this.renderRangeField(
            "Sensitivity",
            sensitivity,
            sensitivityMinimum,
            sensitivityMaximum,
            undefined,
            (value) =>
              this.updateContent((content) => {
                content.sensitivity = value;
                return content;
              }),
          )}

          ${this.settings?.colour ? html`<label class="field">
            <span>Colour mode</span>
            <select
              aria-label="Colour mode"
              ?disabled=${this.disabled}
              @change=${(event: Event) =>
                this.colourModeChanged(
                  (event.target as HTMLSelectElement).value === "fixed",
                )}
            >
              <option
                value="automatic"
                .selected=${colourMode === "automatic"}
              >
                Automatic
              </option>
              <option value="fixed" .selected=${colourMode === "fixed"}>
                Fixed
              </option>
            </select>
          </label>` : nothing}

          ${this.settings?.colour && colourMode === "fixed"
            ? html`
                <govee-single-colour-field
                  label="Fixed colour"
                  .visibleLabel=${false}
                  .colour=${fixedColour}
                  .disabled=${this.disabled}
                  .selectionActive=${true}
                  .rememberOnCommit=${true}
                  @colour-changing=${(event: CustomEvent<{ colour: RGB }>) =>
                    this.fixedColourChanged(event.detail.colour, "changing")}
                  @colour-changed=${(event: CustomEvent<{ colour: RGB }>) =>
                    this.fixedColourChanged(event.detail.colour, "committed")}
                ></govee-single-colour-field>
              `
            : nothing}

          ${this.settings?.style
            ? html`
                <label class="field">
                  <span class="field-label-with-help">
                    <span>Style</span>
                    <govee-info-control
                      .label=${MUSIC_STYLE_HELP.label}
                      .text=${MUSIC_STYLE_HELP.text}
                    ></govee-info-control>
                  </span>
                  <select
                    aria-label="Style"
                    ?disabled=${this.disabled}
                    @change=${(event: Event) =>
                      this.styleChanged(
                        musicStyleCalm(
                          (event.target as HTMLSelectElement).value,
                        ),
                      )}
                  >
                    <option
                      value="dynamic"
                      .selected=${musicStyleValue(this.content.calm ?? this.settings.calm_default) ===
                      "dynamic"}
                    >
                      Dynamic
                    </option>
                    <option
                      value="calm"
                      .selected=${musicStyleValue(this.content.calm ?? this.settings.calm_default) ===
                      "calm"}
                    >
                      Calm
                    </option>
                  </select>
                </label>
              `
            : nothing}

          ${this.renderModeParameters(this.content)}
        </div>
      </section>
    `;
  }

  private renderRangeField(
    label: string,
    value: number,
    min: number,
    max: number,
    parameter: OwnedMusicParameterKey | undefined,
    commit: (value: number) => void,
  ) {
    return html`
      <govee-slider-control
        .label=${label}
        .value=${value}
        .minimum=${min}
        .maximum=${max}
        .valueText=${parameter
          ? reactiveParameterValueText(parameter, value)
          : undefined}
        .disabled=${this.disabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) => {
          this.interaction = event.detail.interaction;
          try {
            commit(event.detail.value);
          } finally {
            this.interaction = "committed";
          }
        }}
      ></govee-slider-control>
    `;
  }

  private renderModeSelector() {
    if (!this.modeSelectionEnabled || !this.content || !this.catalogue) {
      return nothing;
    }
    const knownMode = this.catalogue.music_modes.some(
      (mode) => mode.id === this.content!.mode,
    );
    return html`
      <label class="field">
        <span>Reactive effect</span>
        <select
          aria-label="Reactive effect"
          .value=${live(this.content.mode)}
          ?disabled=${this.disabled}
          @change=${(event: Event) =>
            this.dispatchEvent(
              new CustomEvent<MusicModeChange>("mode-changed", {
                detail: {
                  mode: (event.target as HTMLSelectElement).value,
                },
                bubbles: true,
                composed: true,
              }),
            )}
        >
          ${knownMode
            ? nothing
            : html`<option value=${this.content.mode}>${this.content.mode}</option>`}
          ${this.catalogue.music_modes.map(
            (mode) => html`<option value=${mode.id}>${mode.label}</option>`,
          )}
        </select>
      </label>
    `;
  }

  private renderModeParameters(content: MusicProfileContent) {
    switch (content.mode) {
      case "separation":
        return this.renderSeparationParameters(content.parameters);
      case "hopping":
        return this.renderHoppingParameters(content.parameters);
      case "piano_keys":
        return this.renderPianoKeysParameters(content.parameters);
      case "fountain":
        return this.renderFountainParameters(content.parameters);
      case "day_and_night":
        return this.renderDayAndNightParameters(content.parameters);
      default:
        return nothing;
    }
  }

  private get settings() {
    return this.content ? this.catalogue?.music_settings[this.content.mode] : undefined;
  }

  private renderNumberParameter(label: string, key: OwnedMusicParameterKey, parameters: JsonObject) {
    const spec = this.settings?.parameters[key];
    if (!spec || spec.kind !== "number") return nothing;
    return this.renderRangeField(label, numberParameter(parameters, key, spec.default as number, spec.min, spec.max),
      spec.min, spec.max, key, (value) => this.updateParameter(key, value));
  }

  private renderGradient(parameters: JsonObject) {
    const spec = this.settings?.parameters.gradient;
    if (!spec || spec.kind !== "switch") return nothing;
    return this.renderCheckboxField("Gradient", booleanParameter(parameters, "gradient", spec.default as boolean),
      (checked) => this.updateParameter("gradient", checked));
  }

  private renderSeparationParameters(parameters: JsonObject) {
    return html`
      ${this.renderNumberParameter("Point", "point", parameters)}
      ${this.renderGradient(parameters)}
    `;
  }

  private renderHoppingParameters(parameters: JsonObject) {
    return this.renderNumberParameter("Relative brightness", "relative_brightness", parameters);
  }

  private renderPianoKeysParameters(parameters: JsonObject) {
    return this.renderNumberParameter("Key count", "key_count", parameters);
  }

  private renderFountainParameters(parameters: JsonObject) {
    const spec = this.settings?.parameters.direction;
    if (!spec || spec.kind !== "select") return nothing;
    const direction = directionParameter(parameters, "direction", spec);

    return html`
      <label class="field">
        <span class="parameter-label">Direction</span>
        <select
          aria-label="Direction"
          .value=${live(direction)}
          ?disabled=${this.disabled}
          @change=${(event: Event) =>
            this.updateParameter(
              "direction",
              (event.target as HTMLSelectElement).value as FountainDirection,
            )}
        >
          ${FOUNTAIN_DIRECTIONS.filter((option) => spec.options.includes(option.id)).map(
            (option) => html`
              <option
                value=${option.id}
                .selected=${option.id === direction}
              >
                ${option.label}
              </option>
            `,
          )}
        </select>
      </label>
    `;
  }

  private renderDayAndNightParameters(parameters: JsonObject) {
    return html`
      ${this.renderNumberParameter("Segment count", "segment_count", parameters)}
      ${this.renderNumberParameter("Speed", "speed", parameters)}
      ${this.renderGradient(parameters)}
    `;
  }

  private renderCheckboxField(
    label: string,
    checked: boolean,
    commit: (checked: boolean) => void,
  ) {
    return html`
      <govee-checkbox-control
        .label=${label}
        .checked=${checked}
        .disabled=${this.disabled}
        @checked-changed=${(event: CustomEvent<CheckboxControlChange>) =>
          commit(event.detail.checked)}
      ></govee-checkbox-control>
    `;
  }

  private colourModeChanged(fixed: boolean): void {
    this.updateContent((content) => {
      if (!fixed) {
        this.lastFixedColour = content.colour === null ? this.lastFixedColour : cloneRgb(content.colour);
        content.colour = null;
        return content;
      }

      const colour = content.colour ?? this.lastFixedColour ?? recentColour(0);
      this.lastFixedColour = cloneRgb(colour);
      content.colour = cloneRgb(colour);
      return content;
    });
  }

  private fixedColourChanged(
    colour: RGB,
    interaction: LivePreviewInteraction,
  ): void {
    this.lastFixedColour = cloneRgb(colour);
    this.updateContent((content) => {
      content.colour = cloneRgb(colour);
      return content;
    }, interaction);
  }

  private styleChanged(calm: boolean): void {
    this.updateContent((content) => {
      if (!this.settings?.style) {
        return content;
      }
      content.calm = calm;
      return content;
    });
  }

  private updateParameter(
    key: OwnedMusicParameterKey,
    value: boolean | number | FountainDirection,
  ): void {
    this.updateContent((content) => {
      const parameters = structuredClone(content.parameters);
      parameters[key] = value;
      content.parameters = parameters;
      return content;
    });
  }

  private updateContent(
    transform: (content: MusicProfileContent) => MusicProfileContent,
    interaction: LivePreviewInteraction = this.interaction,
  ): void {
    if (!this.content) {
      return;
    }

    const installed = cloneMusicProfileContent(transform(cloneMusicProfileContent(this.content)));
    this.content = installed;
    this.dispatchEvent(
      new CustomEvent<{
        content: MusicProfileContent;
        interaction: LivePreviewInteraction;
      }>("content-changed", {
        detail: {
          content: cloneMusicProfileContent(installed),
          interaction,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    studioBaseStyles,
    studioCardStyles,
    studioFormStyles,
    css`
      :host {
        display: block;
      }

      .field-label-with-help {
        display: inline-flex;
        align-items: center;
        gap: var(--studio-compact-gap);
        justify-self: start;
      }

    `,
  ];
}

function numberParameter(
  parameters: JsonObject,
  key: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const value = parameters[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  return clampInteger(value, minimum, maximum);
}

function booleanParameter(
  parameters: JsonObject,
  key: string,
  fallback: boolean,
): boolean {
  return typeof parameters[key] === "boolean" ? (parameters[key] as boolean) : fallback;
}

function directionParameter(
  parameters: JsonObject,
  key: string,
  spec: MusicParameterSpec,
): FountainDirection {
  const value = parameters[key];
  return typeof value === "string" && spec.options.includes(value)
    ? (value as FountainDirection)
    : spec.default as FountainDirection;
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-music-profile-editor": GoveeMusicProfileEditor;
  }
}

if (!customElements.get("govee-music-profile-editor")) {
  customElements.define(
    "govee-music-profile-editor",
    GoveeMusicProfileEditor,
  );
}
