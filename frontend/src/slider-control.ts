import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import { studioBaseStyles, studioFormStyles } from "./studio-styles";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { clamp } from "./ui-utils";

export interface SliderControlChange {
  value: number;
  interaction: LivePreviewInteraction;
}

export class GoveeSliderControl extends LitElement {
  @property()
  public label = "";

  @property({ type: Number })
  public value = 0;

  @property({ type: Number })
  public minimum = 0;

  @property({ type: Number })
  public maximum = 100;

  @property({ type: Number })
  public step = 1;

  @property({ type: Boolean })
  public disabled = false;

  @property({ attribute: false })
  public describedBy?: string;

  @property({ attribute: false })
  public valueText?: string;

  @property({ type: Boolean })
  public hideValueText = false;

  protected render() {
    const value = clamp(this.value, this.minimum, this.maximum);
    return html`
      <label class="slider-field">
        <span class="slider-label">
          <span class="slider-label-context">
            <span class="parameter-label">${this.label}</span>
            <slot name="help"></slot>
          </span>
          ${this.valueText === undefined || this.hideValueText
              ? nothing
              : html`<span class="slider-value">${this.valueText}</span>`}
        </span>
        <input
          type="range"
          min=${this.minimum}
          max=${this.maximum}
          step=${this.step}
          .value=${String(value)}
          aria-label=${this.label}
          aria-describedby=${this.describedBy ?? nothing}
          aria-valuetext=${this.valueText ?? nothing}
          ?disabled=${this.disabled}
          @input=${(event: Event) =>
            this.valueChanged(event, "changing")}
          @change=${(event: Event) =>
            this.valueChanged(event, "committed")}
        />
      </label>
    `;
  }

  private valueChanged(
    event: Event,
    interaction: LivePreviewInteraction,
  ): void {
    this.dispatchEvent(
      new CustomEvent<SliderControlChange>("value-changed", {
        detail: {
          value: Number((event.target as HTMLInputElement).value),
          interaction,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    studioBaseStyles,
    studioFormStyles,
    css`
      :host {
        display: block;
      }

      .slider-field {
        display: grid;
        gap: var(--studio-control-gap);
      }

      .slider-label {
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-height: var(--studio-info-control-size);
        gap: var(--studio-compact-gap);
      }

      .slider-label-context {
        display: inline-flex;
        align-items: center;
        gap: var(--studio-compact-gap);
      }

      .slider-value {
        color: var(--studio-muted);
        font-variant-numeric: tabular-nums;
      }

      input {
        width: 100%;
        min-width: 0;
        min-height: var(--studio-control-height);
        margin: 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-slider-control": GoveeSliderControl;
  }
}

if (!customElements.get("govee-slider-control")) {
  customElements.define("govee-slider-control", GoveeSliderControl);
}
