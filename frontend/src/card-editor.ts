import { LitElement, html, css } from "../vendor/lit.js";
import type { GoveeLedBleCardConfig, HassLike } from "./types";

class GoveeLedBleCardEditor extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  declare hass?: HassLike;
  declare private _config?: GoveeLedBleCardConfig;

  setConfig(config: GoveeLedBleCardConfig): void {
    this._config = { ...config };
  }

  render(): unknown {
    return html`
      <div class="editor">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config?.entity ?? ""}
          .includeDomains=${["light"]}
          .label=${"Light entity"}
          allow-custom-entity
          @value-changed=${this._entityChanged}
        ></ha-entity-picker>
        <p class="help">
          Choose a segment-capable Govee light (one exposing a
          <code>segment_colors</code> attribute).
        </p>
      </div>
    `;
  }

  private _entityChanged(ev: Event): void {
    const value = (ev as CustomEvent<{ value?: string }>).detail?.value ?? "";
    const next: GoveeLedBleCardConfig = { ...this._config, entity: value };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = css`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `;
}

customElements.define("govee-led-ble-card-editor", GoveeLedBleCardEditor);
