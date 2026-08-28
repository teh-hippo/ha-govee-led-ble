import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import "./colour-picker";
import { studioBaseStyles, studioFormStyles } from "./studio-styles";
import type { RGB } from "./types";

export class GoveeSingleColourField extends LitElement {
  @property()
  public label = "Colour";

  @property({ type: Boolean })
  public visibleLabel = true;

  @property({ attribute: false })
  public colour: RGB = [255, 255, 255];

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Boolean })
  public selectionActive = true;

  @property({ type: Boolean })
  public rememberOnCommit = true;

  protected render() {
    return html`
      <div class="parameter-group" role="group" aria-label=${this.label}>
        ${this.visibleLabel
          ? html`<span class="parameter-label">${this.label}</span>`
          : nothing}
        <govee-colour-picker
          .colour=${this.colour}
          .disabled=${this.disabled}
          .selectionActive=${this.selectionActive}
          .rememberOnCommit=${this.rememberOnCommit}
        ></govee-colour-picker>
      </div>
    `;
  }

  static styles = [
    studioBaseStyles,
    studioFormStyles,
    css`
      :host {
        display: block;
      }

      .parameter-group {
        width: min(460px, 100%);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-single-colour-field": GoveeSingleColourField;
  }
}

if (!customElements.get("govee-single-colour-field")) {
  customElements.define(
    "govee-single-colour-field",
    GoveeSingleColourField,
  );
}
