import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";

import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import "./info-control";
import "./palette-editor";
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
  MusicZone,
  RetainedMusicEdit,
  RGB,
} from "./types";
import { clampInteger, clonePalette, cloneRgb } from "./ui-utils";

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

  @property({ type: Boolean })
  public showSensitivity = true;

  @property({ attribute: false })
  public retainedEdit?: RetainedMusicEdit | null;

  @property({ attribute: false })
  public configEntryId?: string;

  @state() private retainedParameters: JsonObject = {};
  @state() private retainedCalm?: boolean;

  private lastFixedColour?: RGB;
  private interaction: LivePreviewInteraction = "committed";
  public clearRetainedEdits(): void {
    this.retainedParameters = {};
    this.retainedCalm = undefined;
  }

  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    const previous = changed.get("retainedEdit") as RetainedMusicEdit | null | undefined;
    if (changed.has("configEntryId") ||
        (changed.has("content") && (changed.get("content") as MusicProfileContent | undefined)?.mode !== this.content?.mode) ||
        (changed.has("retainedEdit") &&
          (previous?.mode !== this.retainedEdit?.mode || previous?.revision !== this.retainedEdit?.revision))) {
      this.clearRetainedEdits();
    }
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
    const wholeColour = this.settings?.colour && !("left_colour" in (this.settings.parameters ?? {}));

    return html`
      <section class="card">
        <div class="parameter-stack">
          ${this.renderModeSelector()}
          ${this.showSensitivity ? this.renderRangeField(
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
          ) : nothing}

          ${wholeColour ? html`<label class="field">
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

          ${wholeColour && colourMode === "fixed"
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
          ${this.settings?.palette ? html`
            <div class="field">
              <span>Music colours</span>
              <govee-palette-editor
                .palette=${this.content.palette ?? this.settings.palette.default}
                .minColours=${this.settings.palette.min}
                .maxColours=${this.settings.palette.max}
                .disabled=${this.disabled}
                .ariaLabel=${"Music colours"}
                @palette-changed=${(event: CustomEvent<{palette: RGB[]; interaction: LivePreviewInteraction}>) => {
                  this.updateContent(content => ({...content, palette: clonePalette(event.detail.palette)}), event.detail.interaction);
                }}
              ></govee-palette-editor>
              ${this.content.palette === undefined ? nothing : html`
                <button type="button" ?disabled=${this.disabled} @click=${() => this.updateContent(content => {
                  delete content.palette;
                  return content;
                })}>Use default colours</button>
              `}
            </div>
          ` : nothing}
        </div>
      </section>
      ${this.renderZones()}
      ${this.retainedEdit?.mode === this.content.mode ? html`
        <section class="card">
          <h3>Edit retained device music</h3>
          <p>Preserves the last complete body, including its palette and geometry. This is retained data, not readback.</p>
          ${this.renderModeParameters(
            { ...this.content, parameters: { ...this.retainedEdit.parameters, ...this.retainedParameters } },
            this.retainedEdit.settings,
            (key, value) => { this.retainedParameters = { ...this.retainedParameters, [key]: value }; },
          )}
          ${this.retainedEdit.settings.style ? html`
            <label class="field">Style
              <select aria-label="Retained music style" ?disabled=${this.disabled}
                @change=${(event: Event) => {
                  const value = (event.target as HTMLSelectElement).value;
                  this.retainedCalm = value === "preserve" ? undefined : value === "calm";
                }}>
                <option value="preserve" .selected=${this.retainedCalm === undefined}>Preserve</option>
                <option value="dynamic" .selected=${this.retainedCalm === false}>Dynamic</option>
                <option value="calm" .selected=${this.retainedCalm === true}>Calm</option>
              </select>
            </label>` : nothing}
          <button type="button" ?disabled=${this.disabled ||
            (!Object.keys(this.retainedParameters).length && this.retainedCalm === undefined)}
            @click=${() => this.dispatchEvent(new CustomEvent("retained-music-edit", {
              detail: { edit: this.retainedEdit, parameters: this.retainedParameters, calm: this.retainedCalm },
              bubbles: true, composed: true,
            }))}>Apply retained-body edits</button>
        </section>` : nothing}
    `;
  }

  private renderZones() {
    const content = this.content;
    const catalogue = this.catalogue;
    if (!content?.zones || !catalogue?.native_zones) return nothing;
    const childCatalogue = {
      ...catalogue,
      music_modes: catalogue.music_modes.filter(mode => mode.id !== content.mode),
    };
    return html`${content.zones.map((zone, index) => html`
      <section class="card">
        <h3>${catalogue.native_zones![index]?.label ?? zone.id}</h3>
        <govee-music-profile-editor .content=${{
          kind: "music_profile", model: content.model, mode: zone.mode, sensitivity: content.sensitivity,
          colour: null, calm: null, parameters: zone.parameters,
          ...(zone.palette === undefined ? {} : { palette: zone.palette }),
        } satisfies MusicProfileContent}
          .catalogue=${childCatalogue} .disabled=${this.disabled} .modeSelectionEnabled=${true} .showSensitivity=${false}
          @mode-changed=${(event: CustomEvent<MusicModeChange>) => {
            event.stopPropagation();
            if (!childCatalogue.music_modes.some(mode => mode.id === event.detail.mode)) return;
            this.updateZone(index, zone.mode, { id: zone.id, mode: event.detail.mode, parameters: {} });
          }}
          @content-changed=${(event: CustomEvent<{ content: MusicProfileContent; interaction: LivePreviewInteraction }>) => {
            event.stopPropagation();
            const changed = event.detail.content;
            this.updateZone(index, zone.mode, {
              ...zone, parameters: changed.parameters,
              ...(changed.palette === undefined ? {} : { palette: changed.palette }),
            }, event.detail.interaction, changed.palette === undefined);
          }}
        ></govee-music-profile-editor>
      </section>
    `)}`;
  }

  private updateZone(index: number, mode: string, zone: MusicZone,
    interaction: LivePreviewInteraction = "committed", removePalette = false): void {
    if (this.content?.zones?.[index]?.mode !== mode) return;
    this.updateContent(content => {
      const current = content.zones![index];
      if (zone.mode === mode) zone = { ...current, parameters: { ...current.parameters, ...zone.parameters },
        ...(zone.palette === undefined ? {} : { palette: zone.palette }) };
      if (removePalette) delete zone.palette;
      content.zones![index] = zone;
      return content;
    }, interaction);
  }

  private renderRangeField(
    label: string,
    value: number,
    min: number,
    max: number,
    parameter: string | undefined,
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

  private renderModeParameters(content: MusicProfileContent, settings = this.settings,
    update = (key: string, value: boolean | number | string) => this.updateParameter(key, value)) {
    return Object.entries(settings?.parameters ?? {}).map(([key, spec]) => {
      const label = parameterLabel(key);
      if ((key === "background" || key === "left_colour" || key === "right_colour") && spec.kind === "number") {
        const value = numberParameter(content.parameters, key, spec.default as number, spec.min, spec.max);
        const colour: RGB = [value >> 16, (value >> 8) & 255, value & 255];
        const change = (event: CustomEvent<{ colour: RGB }>, interaction: LivePreviewInteraction) => {
          const [red, green, blue] = event.detail.colour;
          this.interaction = interaction;
          try { update(key, (red << 16) | (green << 8) | blue); }
          finally { this.interaction = "committed"; }
        };
        return html`
          <div class="field">
            <govee-single-colour-field
              label=${key === "background" ? "Background colour" : label}
              .colour=${colour}
              .disabled=${this.disabled}
              @colour-changing=${(event: CustomEvent<{ colour: RGB }>) => change(event, "changing")}
              @colour-changed=${(event: CustomEvent<{ colour: RGB }>) => change(event, "committed")}
            ></govee-single-colour-field>
            ${key === "background" ? html`
              <button type="button" ?disabled=${this.disabled} @click=${() => update(key, 0x010101)}>
                No colour
              </button>` : nothing}
          </div>
        `;
      }
      if (spec.kind === "number") {
        return this.renderRangeField(
          label, numberParameter(content.parameters, key, spec.default as number, spec.min, spec.max),
          spec.min, spec.max, key, (value) => update(key, value),
        );
      }
      if (spec.kind === "switch") {
        return this.renderCheckboxField(
          label, booleanParameter(content.parameters, key, spec.default as boolean),
          (checked) => update(key, checked),
        );
      }
      const raw = content.parameters[key];
      const selected = typeof raw === "string" && spec.options.includes(raw) ? raw : spec.default as string;
      return html`
        <label class="field">
          <span class="parameter-label">${label}</span>
          <select
            aria-label=${label}
            .value=${live(selected)}
            ?disabled=${this.disabled}
            @change=${(event: Event) => update(key, (event.target as HTMLSelectElement).value)}
          >
            ${spec.options.map((option) => html`
              <option value=${option} .selected=${option === selected}>${parameterLabel(option)}</option>
            `)}
          </select>
        </label>
      `;
    });
  }

  private get settings() {
    return this.content ? this.catalogue?.music_settings[this.content.mode] : undefined;
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
    key: string,
    value: boolean | number | string,
  ): void {
    this.updateContent((content) => {
      const parameters = structuredClone(content.parameters);
      parameters[key] = value;
      if (key === "fixed_colour" && value === true) {
        for (const colourKey of ["left_colour", "right_colour"]) {
          const spec = this.settings?.parameters?.[colourKey];
          if (spec?.kind === "number") {
            parameters[colourKey] = numberParameter(parameters, colourKey, spec.default as number, spec.min, spec.max);
          }
        }
      }
      if (key === "left_colour" || key === "right_colour") parameters.fixed_colour = true;
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

function parameterLabel(key: string): string {
  if (key === "two_way") return "Two-way";
  return key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
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
