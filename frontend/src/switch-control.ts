import { LitElement, css, html } from "lit";
import { property } from "lit/decorators.js";

import { studioBaseStyles } from "./studio-styles";

export interface SwitchControlChange {
  checked: boolean;
}

export class GoveeSwitchControl extends LitElement {
  @property()
  public label = "";

  @property({ type: Boolean })
  public checked = false;

  @property({ type: Boolean })
  public disabled = false;

  protected render() {
    return html`
      <button
        class=${this.checked ? "on" : ""}
        type="button"
        role="switch"
        aria-checked=${this.checked}
        aria-label=${this.label}
        ?disabled=${this.disabled}
        @click=${this.toggle}
      >
        <span aria-hidden="true"></span>
      </button>
    `;
  }

  private toggle(): void {
    this.dispatchEvent(
      new CustomEvent<SwitchControlChange>("checked-changed", {
        detail: { checked: !this.checked },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    studioBaseStyles,
    css`
      :host {
        display: inline-block;
        flex: 0 0 auto;
      }

      button {
        --studio-switch-track-width: var(--studio-compact-switch-track-width);
        --studio-switch-thumb-travel: calc(
          var(--studio-switch-track-width) - var(--studio-switch-thumb-inset) -
            var(--studio-switch-thumb-inset) -
            var(--studio-switch-thumb-size)
        );
        position: relative;
        width: var(--studio-switch-track-width);
        min-height: var(--studio-switch-track-height);
        height: var(--studio-switch-track-height);
        padding: 0;
        border: 0;
        border-radius: var(--studio-pill-radius);
        background: var(--studio-switch-track-off);
        cursor: pointer;
        transition: background var(--studio-switch-transition-duration)
          var(--studio-switch-transition-easing);
      }

      button span {
        position: absolute;
        top: var(--studio-switch-thumb-inset);
        left: var(--studio-switch-thumb-inset);
        width: var(--studio-switch-thumb-size);
        height: var(--studio-switch-thumb-size);
        border-radius: var(--studio-round-radius);
        background: var(--studio-switch-thumb-off);
        box-shadow: 0 var(--studio-border-width)
          var(--studio-strong-border-width) rgb(0 0 0 / 20%);
        transition:
          transform var(--studio-switch-transition-duration)
            var(--studio-switch-transition-easing),
          background var(--studio-switch-transition-duration)
            var(--studio-switch-transition-easing);
      }

      button.on {
        background: var(--studio-switch-track-on);
      }

      button.on span {
        background: var(--studio-switch-thumb-on);
        transform: translateX(var(--studio-switch-thumb-travel));
      }

      button:focus-visible {
        outline: var(--studio-focus-width) solid var(--studio-blue);
        outline-offset: var(--studio-focus-offset);
      }

      @media (prefers-reduced-motion: reduce) {
        button,
        button span {
          transition: none;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-switch-control": GoveeSwitchControl;
  }
}

if (!customElements.get("govee-switch-control")) {
  customElements.define("govee-switch-control", GoveeSwitchControl);
}
