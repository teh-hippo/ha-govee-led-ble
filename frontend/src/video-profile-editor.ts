import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import {
  studioBaseStyles,
  studioCardStyles,
  studioFormStyles,
} from "./studio-styles";
import {
  cloneVideoProfileContent,
  videoCaptureAreaFullScreen,
  videoCaptureAreaValue,
} from "./profile-model";
import type { RelativeBrightness, VideoProfileContent } from "./types";
import { clampInteger } from "./ui-utils";

const BRIGHTNESS_EDGE_OPTIONS = [
  { key: "left", label: "Left" },
  { key: "top", label: "Top" },
  { key: "right", label: "Right" },
  { key: "bottom", label: "Bottom" },
] as const satisfies ReadonlyArray<{
  key: keyof RelativeBrightness;
  label: string;
}>;

type RelativeBrightnessEdge = keyof RelativeBrightness;

function uniformRelativeBrightnessValue(
  relativeBrightness: RelativeBrightness,
): number | undefined {
  const values = [
    relativeBrightness.left,
    relativeBrightness.top,
    relativeBrightness.right,
    relativeBrightness.bottom,
  ];
  return values.every((value) => value === values[0]) ? values[0] : undefined;
}

function uniformBrightnessControlValue(
  relativeBrightness: RelativeBrightness,
): number {
  const uniform = uniformRelativeBrightnessValue(relativeBrightness);
  if (uniform !== undefined) {
    return uniform;
  }
  return clampInteger(
    (relativeBrightness.left +
      relativeBrightness.top +
      relativeBrightness.right +
      relativeBrightness.bottom) /
      4,
    1,
    100,
  );
}

function applyUniformRelativeBrightness(
  value: number,
): RelativeBrightness {
  const next = clampInteger(value, 1, 100);
  return {
    left: next,
    top: next,
    right: next,
    bottom: next,
  };
}

export class GoveeVideoProfileEditor extends LitElement {
  @property({ attribute: false })
  public content?: VideoProfileContent;

  @property({ type: Boolean })
  public disabled = false;

  private interaction: LivePreviewInteraction = "committed";

  protected render() {
    if (!this.content) {
      return html`
        <section class="card empty-state" role="status">
          <h3 class="section-title">Video profile unavailable</h3>
          <p class="muted">
            Load an H6199 video profile to edit video-sync settings.
          </p>
        </section>
      `;
    }

    const brightness = this.content.relative_brightness;
    const mixedBrightness =
      uniformRelativeBrightnessValue(brightness) === undefined;
    const uniformBrightness = uniformBrightnessControlValue(brightness);

    return html`
      <div class="editor-grid">
        <section class="card">
          <div class="parameter-stack">
            <label class="field">
              <span>Capture area</span>
              <select
                aria-label="Capture area"
                ?disabled=${this.disabled}
                @change=${(event: Event) =>
                  this.updateContent((content) => {
                    content.full_screen =
                      videoCaptureAreaFullScreen(
                        (event.target as HTMLSelectElement).value,
                      );
                  })}
              >
                <option
                  value="full"
                  .selected=${videoCaptureAreaValue(
                    this.content.full_screen,
                  ) === "full"}
                >
                  Full screen
                </option>
                <option
                  value="part"
                  .selected=${videoCaptureAreaValue(
                    this.content.full_screen,
                  ) === "part"}
                >
                  Part screen
                </option>
              </select>
            </label>
            ${this.renderCheckboxField(
              "Sound effects",
              this.content.sound_effects,
              (checked) =>
                this.updateContent((content) => {
                  content.sound_effects = checked;
                }),
            )}
            ${this.content.sound_effects
              ? this.renderRangeField(
                  "Softness",
                  this.content.sound_effects_softness,
                  1,
                  100,
                  (value) =>
                    this.updateContent((content) => {
                      content.sound_effects_softness = clampInteger(
                        value,
                        1,
                        100,
                      );
                    }),
                )
              : nothing}
            ${this.renderCheckboxField(
              "Blank screen",
              this.content.blank_screen,
              (checked) =>
                this.updateContent((content) => {
                  content.blank_screen = checked;
                }),
            )}
          </div>
        </section>

        <section class="card">
          <h3 class="section-title">Image</h3>
          <div class="parameter-stack">
            ${this.renderRangeField(
              "Saturation",
              this.content.saturation,
              0,
              100,
              (value) =>
                this.updateContent((content) => {
                  content.saturation = clampInteger(value, 0, 100);
                }),
            )}
            ${this.renderWhiteBalanceField(this.content.white_balance_position)}
          </div>
        </section>

        <section class="card brightness-card">
          <div class="card-heading">
            <h3 class="section-title">Relative brightness</h3>
            ${mixedBrightness
              ? html`<span class="status-chip">Mixed edges</span>`
              : nothing}
          </div>
          <div class="parameter-stack">
            ${this.renderRangeField(
              "Uniform brightness",
              uniformBrightness,
              1,
              100,
              (value) =>
                this.updateContent((content) => {
                  content.relative_brightness =
                    applyUniformRelativeBrightness(value);
                }),
              mixedBrightness ? "relative-brightness-note" : undefined,
            )}
            ${mixedBrightness
              ? html`
                  <p class="section-note muted" id="relative-brightness-note">
                    Edges differ.  Adjust Uniform brightness to align all four
                    sides, or adjust them around the screen.
                  </p>
                `
              : nothing}
            <div
              class="screen-brightness"
              role="group"
              aria-label="Screen edge brightness"
            >
              ${this.renderScreenEdgeControl("top", "Top", brightness.top)}
              ${this.renderScreenEdgeControl("left", "Left", brightness.left)}
              <div class="virtual-screen" aria-hidden="true">
                ${BRIGHTNESS_EDGE_OPTIONS.map(
                  ({ key }) => html`
                    <span
                      class="screen-edge screen-edge-${key}"
                      style=${`--edge-level: ${brightness[key] / 100}`}
                    ></span>
                  `,
                )}
                <div class="screen-image">
                  <span>Screen</span>
                </div>
                <div class="screen-stand"></div>
              </div>
              ${this.renderScreenEdgeControl(
                "right",
                "Right",
                brightness.right,
              )}
              ${this.renderScreenEdgeControl(
                "bottom",
                "Bottom",
                brightness.bottom,
              )}
            </div>
          </div>
        </section>
      </div>
    `;
  }

  private renderCheckboxField(
    label: string,
    checked: boolean,
    changed: (checked: boolean) => void,
  ) {
    return html`
      <govee-checkbox-control
        .label=${label}
        .checked=${checked}
        .disabled=${this.disabled}
        @checked-changed=${(event: CustomEvent<CheckboxControlChange>) =>
          changed(event.detail.checked)}
      ></govee-checkbox-control>
    `;
  }

  private renderRangeField(
    label: string,
    value: number,
    minimum: number,
    maximum: number,
    changed: (value: number) => void,
    describedBy?: string,
  ) {
    return html`
      <govee-slider-control
        .label=${label}
        .value=${value}
        .minimum=${minimum}
        .maximum=${maximum}
        .describedBy=${describedBy}
        .disabled=${this.disabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) =>
          this.runInteraction(
            event.detail.interaction,
            () => changed(event.detail.value),
          )}
      ></govee-slider-control>
    `;
  }

  private renderWhiteBalanceField(value: number) {
    return html`
      <label class="range-field white-balance-field">
        <span class="parameter-label">White balance</span>
        <div class="slider-with-endpoints">
          <input
            type="range"
            min="1"
            max="20"
            .value=${String(clampInteger(value, 1, 20))}
            aria-label="White balance"
            ?disabled=${this.disabled}
            @input=${(event: Event) =>
              this.updateContent(
                (content) => {
                  content.white_balance_position = clampInteger(
                    Number((event.target as HTMLInputElement).value),
                    1,
                    20,
                  );
                },
                "changing",
              )}
          />
          <div class="endpoint-labels" aria-hidden="true">
            <span>Cool</span>
            <span>Warm</span>
          </div>
        </div>
      </label>
    `;
  }

  private renderScreenEdgeControl(
    edge: RelativeBrightnessEdge,
    label: string,
    value: number,
  ) {
    return html`
      <label class="screen-edge-control edge-control-${edge}">
        <span class="parameter-label">${label}</span>
        <input
          type="range"
          min="1"
          max="100"
          .value=${String(value)}
          aria-label=${label}
          ?disabled=${this.disabled}
          @input=${(event: Event) =>
            this.updateRelativeBrightnessEdge(
              edge,
              Number((event.target as HTMLInputElement).value),
            )}
        />
      </label>
    `;
  }

  private updateRelativeBrightnessEdge(
    edge: RelativeBrightnessEdge,
    value: number,
  ): void {
    this.updateContent(
      (content) => {
        content.relative_brightness[edge] = clampInteger(value, 1, 100);
      },
      "changing",
    );
  }

  private updateContent(
    changed: (content: VideoProfileContent) => void,
    interaction: LivePreviewInteraction = this.interaction,
  ): void {
    if (!this.content) {
      return;
    }
    const next = cloneVideoProfileContent(this.content);
    changed(next);
    this.emitContent(next, interaction);
  }

  private emitContent(
    content: VideoProfileContent,
    interaction: LivePreviewInteraction = "committed",
  ): void {
    this.dispatchEvent(
      new CustomEvent<{
        content: VideoProfileContent;
        interaction: LivePreviewInteraction;
      }>("content-changed", {
        detail: {
          content: cloneVideoProfileContent(content),
          interaction,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private runInteraction(
    interaction: LivePreviewInteraction,
    changed: () => void,
  ): void {
    this.interaction = interaction;
    try {
      changed();
    } finally {
      this.interaction = "committed";
    }
  }

  static styles = [
    studioBaseStyles,
    studioCardStyles,
    studioFormStyles,
    css`
      :host {
        --video-edge-control-width: 72px;
        --video-screen-min-width: 260px;
        --video-screen-max-width: 560px;
        --video-screen-row-min-height: 220px;
        --video-screen-padding: var(--studio-spacing-md);
        --video-screen-radius: 14px;
        --video-screen-image-radius: 7px;
        --video-screen-shadow-offset: 18px;
        --video-screen-shadow-blur: 34px;
        --video-stand-offset: 18px;
        --video-stand-width: 28%;
        --video-stand-height: 14px;
        --video-stand-stroke: 4px;
        --video-edge-inset: var(--studio-spacing-2xl);
        --video-edge-thickness: 5px;
        --video-edge-border-inset: 3px;
        --video-horizontal-label-width: 48px;
        --video-horizontal-slider-min-width: 120px;
        --video-range-label-min-width: 118px;
        --video-vertical-slider-min-height: 130px;
        --video-mobile-edge-control-width: 52px;
        --video-mobile-screen-size: 160px;
        --video-mobile-horizontal-label-width: 42px;
        --video-mobile-vertical-slider-min-height: 90px;
        --video-screen-label-letter-spacing: 0.08em;
        --video-edge-near-glow-blur: 8px;
        --video-edge-near-glow-spread: 2px;
        --video-edge-far-glow-blur: 20px;
        --video-edge-far-glow-spread: 5px;
        --video-status-chip-inline-padding: 9px;
        display: block;
        color: var(--primary-text-color);
      }

      p {
        margin-top: 0;
      }

      .editor-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--studio-section-gap);
      }

      .brightness-card {
        grid-column: 1 / -1;
      }

      .muted,
      .endpoint-labels {
        color: var(--studio-muted);
        font-size: var(--studio-parameter-label-size);
        line-height: var(--studio-muted-line-height);
      }

      .section-note {
        margin: calc(0px - var(--studio-tight-gap)) 0 0;
      }

      .screen-brightness {
        display: grid;
        grid-template:
          ". top ." auto
          "left screen right" minmax(var(--video-screen-row-min-height), 1fr)
          ". bottom ." auto
          / var(--video-edge-control-width)
          minmax(var(--video-screen-min-width), var(--video-screen-max-width))
          var(--video-edge-control-width);
        align-items: center;
        justify-content: center;
        gap: var(--studio-spacing-lg);
        padding: var(--studio-spacing-lg) 0 var(--studio-spacing-4xl);
      }

      .virtual-screen {
        position: relative;
        grid-area: screen;
        width: 100%;
        aspect-ratio: 16 / 10;
        padding: var(--video-screen-padding);
        border: var(--studio-border-width) solid
          color-mix(in srgb, var(--studio-muted) 55%, transparent);
        border-radius: var(--video-screen-radius);
        background: #181b22;
        box-shadow:
          0 var(--video-screen-shadow-offset) var(--video-screen-shadow-blur)
            rgb(15 23 42 / 18%),
          inset 0 0 0 var(--studio-border-width) rgb(255 255 255 / 6%);
      }

      .screen-image {
        display: grid;
        width: 100%;
        height: 100%;
        place-items: center;
        overflow: hidden;
        border-radius: var(--video-screen-image-radius);
        color: rgb(255 255 255 / 62%);
        background:
          radial-gradient(circle at 72% 24%, rgb(64 186 255 / 42%), transparent 31%),
          radial-gradient(circle at 25% 72%, rgb(126 87 255 / 38%), transparent 36%),
          linear-gradient(145deg, #24334b, #101724 62%, #1e1633);
        font-size: var(--studio-parameter-label-size);
        font-weight: var(--studio-font-weight-emphasis);
        letter-spacing: var(--video-screen-label-letter-spacing);
        text-transform: uppercase;
      }

      .screen-stand {
        position: absolute;
        bottom: calc(0px - var(--video-stand-offset));
        left: 50%;
        width: var(--video-stand-width);
        height: var(--video-stand-height);
        border-bottom: var(--video-stand-stroke) solid #353b47;
        transform: translateX(-50%);
      }

      .screen-stand::before {
        position: absolute;
        top: 0;
        left: 50%;
        width: var(--video-stand-stroke);
        height: var(--studio-spacing-lg);
        background: #353b47;
        content: "";
        transform: translateX(-50%);
      }

      .screen-edge {
        position: absolute;
        z-index: var(--studio-z-raised);
        border-radius: var(--studio-pill-radius);
        background: rgb(67 168 255);
        box-shadow:
          0 0 var(--video-edge-near-glow-blur)
            var(--video-edge-near-glow-spread) rgb(67 168 255 / 72%),
          0 0 var(--video-edge-far-glow-blur)
            var(--video-edge-far-glow-spread) rgb(67 168 255 / 34%);
        opacity: calc(0.12 + var(--edge-level) * 0.88);
        pointer-events: none;
      }

      .screen-edge-top,
      .screen-edge-bottom {
        right: var(--video-edge-inset);
        left: var(--video-edge-inset);
        height: var(--video-edge-thickness);
      }

      .screen-edge-top {
        top: var(--video-edge-border-inset);
      }

      .screen-edge-bottom {
        bottom: var(--video-edge-border-inset);
      }

      .screen-edge-left,
      .screen-edge-right {
        top: var(--video-edge-inset);
        bottom: var(--video-edge-inset);
        width: var(--video-edge-thickness);
      }

      .screen-edge-left {
        left: var(--video-edge-border-inset);
      }

      .screen-edge-right {
        right: var(--video-edge-border-inset);
      }

      .screen-edge-control {
        display: grid;
        align-items: center;
        gap: var(--studio-compact-gap);
        min-width: 0;
      }

      .screen-edge-control input {
        min-width: 0;
      }

      .edge-control-top,
      .edge-control-bottom {
        grid-template-columns:
          var(--video-horizontal-label-width)
          minmax(var(--video-horizontal-slider-min-width), 1fr);
      }

      .edge-control-top input,
      .edge-control-bottom input {
        min-height: var(--studio-control-height);
      }

      .edge-control-top {
        grid-area: top;
      }

      .edge-control-bottom {
        grid-area: bottom;
      }

      .edge-control-left,
      .edge-control-right {
        grid-template-rows:
          auto
          minmax(var(--video-vertical-slider-min-height), 1fr);
        justify-items: center;
        height: 100%;
      }

      .edge-control-left {
        grid-area: left;
      }

      .edge-control-right {
        grid-area: right;
      }

      .edge-control-left input,
      .edge-control-right input {
        width: var(--studio-control-height);
        height: 100%;
        writing-mode: vertical-lr;
        direction: rtl;
      }

      .card-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--studio-spacing-lg);
        margin-bottom: var(--studio-section-title-gap);
      }

      .card-heading h3 {
        margin-bottom: 0;
      }

      .range-field {
        grid-template-columns:
          minmax(var(--video-range-label-min-width), auto)
          minmax(0, 1fr);
        align-items: center;
        gap: var(--studio-control-gap);
        margin-top: 0;
      }

      .range-field input[type="range"] {
        width: 100%;
        min-width: 0;
      }

      .white-balance-field {
        align-items: start;
      }

      .slider-with-endpoints {
        display: grid;
        gap: var(--studio-tight-gap);
        min-width: 0;
      }

      .endpoint-labels {
        display: flex;
        justify-content: space-between;
        font-size: var(--studio-caption-size);
        font-weight: var(--studio-font-weight-semibold);
      }

      .status-chip {
        padding: var(--studio-micro-gap)
          var(--video-status-chip-inline-padding);
        border-radius: var(--studio-pill-radius);
        color: var(--studio-blue);
        background: var(--studio-blue-soft);
        font-size: var(--studio-caption-size);
        font-weight: var(--studio-font-weight-emphasis);
        white-space: nowrap;
      }

      .empty-state h3,
      .empty-state p {
        margin-bottom: 0;
      }

      .empty-state h3 {
        margin-bottom: var(--studio-compact-gap);
      }

      /* Uses one card column when HA's docked sidebar reduces the editor workspace. */
      @media (max-width: 1320px) {
        .editor-grid {
          grid-template-columns: 1fr;
        }

        .brightness-card {
          grid-column: auto;
        }
      }

      /* Compresses the screen-edge visualisation to the minimum usable phone geometry. */
      @media (max-width: 560px) {
        .range-field {
          grid-template-columns: 1fr;
        }

        .screen-brightness {
          grid-template:
            ". top ." auto
            "left screen right" minmax(var(--video-mobile-screen-size), 1fr)
            ". bottom ." auto
            / var(--video-mobile-edge-control-width)
            minmax(var(--video-mobile-screen-size), 1fr)
            var(--video-mobile-edge-control-width);
          gap: var(--studio-compact-gap);
        }

        .edge-control-top,
        .edge-control-bottom {
          grid-template-columns:
            minmax(0, 1fr)
            var(--video-mobile-horizontal-label-width);
        }

        .edge-control-top .parameter-label,
        .edge-control-bottom .parameter-label {
          grid-column: 1 / -1;
        }

        .edge-control-left,
        .edge-control-right {
          grid-template-rows:
            auto
            minmax(var(--video-mobile-vertical-slider-min-height), 1fr)
            auto;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-video-profile-editor": GoveeVideoProfileEditor;
  }
}

if (!customElements.get("govee-video-profile-editor")) {
  customElements.define(
    "govee-video-profile-editor",
    GoveeVideoProfileEditor,
  );
}
