import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import { studioBaseStyles, studioFormStyles } from "./studio-styles";

export type SegmentedControlValue = boolean | number | string;

export interface SegmentedControlOption<
  T extends SegmentedControlValue = SegmentedControlValue,
> {
  value: T;
  label: string;
  ariaLabel?: string;
}

export interface SegmentedControlChange<
  T extends SegmentedControlValue = SegmentedControlValue,
> {
  value: T;
}

export class GoveeSegmentedControl extends LitElement {
  @property()
  public label = "";

  @property({ attribute: false })
  public options: readonly SegmentedControlOption[] = [];

  @property({ attribute: false })
  public value: SegmentedControlValue = "";

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Boolean })
  public hideLabel = false;

  protected render() {
    return html`
      <div class="parameter-group">
        ${this.hideLabel
          ? nothing
          : html`<span class="parameter-label">${this.label}</span>`}
        <div class="parameter-options" role="group" aria-label=${this.label}>
          ${this.options.map((option) => {
            const selected = option.value === this.value;
            return html`
              <button
                class=${selected ? "selected" : ""}
                type="button"
                aria-pressed=${selected}
                aria-label=${option.ariaLabel ?? nothing}
                title=${option.ariaLabel ?? nothing}
                ?disabled=${this.disabled}
                @click=${() => this.select(option.value)}
              >
                ${option.label}
              </button>
            `;
          })}
        </div>
      </div>
    `;
  }

  private select(value: SegmentedControlValue): void {
    if (this.disabled || value === this.value) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<SegmentedControlChange>("value-changed", {
        detail: { value },
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-segmented-control": GoveeSegmentedControl;
  }
}

if (!customElements.get("govee-segmented-control")) {
  customElements.define("govee-segmented-control", GoveeSegmentedControl);
}
