import { LitElement, css, html } from "lit";
import { property } from "lit/decorators.js";

import { studioBaseStyles, studioFormStyles } from "./studio-styles";

export interface CheckboxControlChange {
  checked: boolean;
}

export class GoveeCheckboxControl extends LitElement {
  @property()
  public label = "";

  @property({ type: Boolean })
  public checked = false;

  @property({ type: Boolean })
  public disabled = false;

  protected render() {
    return html`
      <div class="check-control">
        <label class="check-field">
          <input
            type="checkbox"
            .checked=${this.checked}
            ?disabled=${this.disabled}
            @change=${this.checkedChanged}
          />
          <span class="parameter-label">${this.label}</span>
        </label>
        <slot name="help"></slot>
      </div>
    `;
  }

  private checkedChanged(event: Event): void {
    this.dispatchEvent(
      new CustomEvent<CheckboxControlChange>("checked-changed", {
        detail: {
          checked: (event.target as HTMLInputElement).checked,
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

      .check-control {
        display: flex;
        align-items: center;
        gap: var(--studio-compact-gap);
      }

      .check-field {
        flex: 0 1 auto;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-checkbox-control": GoveeCheckboxControl;
  }
}

if (!customElements.get("govee-checkbox-control")) {
  customElements.define("govee-checkbox-control", GoveeCheckboxControl);
}
