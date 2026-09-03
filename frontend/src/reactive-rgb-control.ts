import { LitElement, css, html } from "lit";
import { property, state } from "lit/decorators.js";

import {
  ReactiveRgbController,
  type ReactiveRgbStatus,
} from "./reactive-rgb-controller";
import type { HomeAssistant } from "./types";

export class GoveeReactiveRgbControl extends LitElement {
  @property({ attribute: false })
  public hass?: HomeAssistant;

  @property({ attribute: "config-entry-id" })
  public configEntryId = "";

  @property({ type: Boolean, attribute: "legacy-colour-order" })
  public legacyColourOrder = false;

  @state()
  private reactiveStatus: ReactiveRgbStatus = {
    phase: "idle",
    message: "Microphone reactive colour is stopped.",
  };

  private controller?: ReactiveRgbController;
  private lastHass?: HomeAssistant;

  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    if (this.hass) {
      this.lastHass = this.hass;
    }
    if (
      this.controller?.running &&
      (changed.has("configEntryId") || changed.has("legacyColourOrder"))
    ) {
      void this.controller.stop(
        "Microphone reactive colour stopped because its settings changed.",
      );
    }
  }

  public disconnectedCallback(): void {
    this.controller?.disconnect();
    super.disconnectedCallback();
  }

  protected render() {
    const running = this.controller?.running ?? false;
    const canStart =
      Boolean(this.hass) && this.configEntryId.trim().length > 0;
    return html`
      <section aria-labelledby="reactive-rgb-heading">
        <h3 id="reactive-rgb-heading">Microphone reactive colour</h3>
        <p>
          Microphone audio stays in this browser. Only one derived RGB colour,
          containing three integer values, is sent to Home Assistant.
        </p>
        <button
          type="button"
          aria-pressed=${String(running)}
          ?disabled=${!running && !canStart}
          @click=${this.toggle}
        >
          ${running ? "Stop" : "Start"}
        </button>
        <p
          class=${this.reactiveStatus.phase === "error" ? "error" : "status"}
          role=${this.reactiveStatus.phase === "error" ? "alert" : "status"}
          aria-live=${this.reactiveStatus.phase === "error"
            ? "assertive"
            : "polite"}
        >
          ${this.reactiveStatus.message}
        </p>
      </section>
    `;
  }

  private readonly toggle = (): void => {
    const controller = this.getController();
    if (controller.running) {
      void controller.stop();
    } else {
      void controller.start();
    }
  };

  private getController(): ReactiveRgbController {
    this.controller ??= new ReactiveRgbController({
      callWS: (message) => {
        const hass = this.hass ?? this.lastHass;
        return hass
          ? hass.callWS<unknown>(message)
          : Promise.reject(new Error("Home Assistant is unavailable"));
      },
      configEntryId: () => this.configEntryId,
      legacyColourOrder: () => this.legacyColourOrder,
      statusChanged: (status) => {
        this.reactiveStatus = status;
      },
    });
    return this.controller;
  }

  static styles = css`
    :host {
      display: block;
    }

    section {
      padding: var(--studio-card-padding);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-card-radius);
      color: var(--primary-text-color);
      background: var(--studio-card);
    }

    h3 {
      margin: 0 0 var(--studio-spacing-sm);
      font-size: var(--studio-section-title-size);
      font-weight: var(--studio-section-title-weight);
      line-height: var(--studio-label-line-height);
    }

    p {
      margin: 0 0 var(--studio-spacing-lg);
      line-height: var(--studio-body-line-height);
    }

    button {
      min-width: var(--studio-editor-action-width);
      min-height: var(--studio-control-height);
      padding: var(--studio-action-padding);
      border: var(--studio-border-width) solid var(--studio-blue);
      border-radius: var(--studio-button-radius);
      color: var(--text-primary-color, #fff);
      background: var(--studio-blue);
      font: inherit;
      font-weight: var(--studio-font-weight-semibold);
      cursor: pointer;
    }

    button:focus-visible {
      outline: var(--studio-focus-width) solid var(--studio-blue);
      outline-offset: var(--studio-focus-offset);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: var(--studio-disabled-opacity);
    }

    .status,
    .error {
      margin: var(--studio-spacing-lg) 0 0;
      font-size: var(--studio-subheading-size);
      line-height: var(--studio-body-line-height);
    }

    .error {
      color: var(--studio-danger);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-reactive-rgb-control": GoveeReactiveRgbControl;
  }
}

if (!customElements.get("govee-reactive-rgb-control")) {
  customElements.define(
    "govee-reactive-rgb-control",
    GoveeReactiveRgbControl,
  );
}
