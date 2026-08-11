class GoveeLedBleEditor extends HTMLElement {
  connectedCallback() {
    this._render();
  }

  set panel(value) {
    this._panel = value;
    this._render();
  }

  _render() {
    if (!this.isConnected || !this._panel) {
      return;
    }

    const configurationPath =
      this._panel.config?.configuration_path ??
      "/config/integrations/integration/ha_govee_led_ble";

    this.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 24px;
        }

        ha-card {
          margin: 0 auto;
          max-width: 640px;
          padding: 24px;
        }

        h1 {
          font-size: 24px;
          margin: 0 0 16px;
        }

        p {
          line-height: 1.5;
          margin: 0 0 24px;
        }

        a {
          color: var(--primary-color);
          font-weight: 500;
        }
      </style>
      <ha-card>
        <h1>Govee LED BLE configuration</h1>
        <p>
          Advanced effect editing is not available in this version. You can
          continue managing the integration through Home Assistant.
        </p>
        <a>Open integration configuration</a>
      </ha-card>
    `;
    this.querySelector("a").href = configurationPath;
  }
}

if (!customElements.get("ha-govee-led-ble-editor")) {
  customElements.define("ha-govee-led-ble-editor", GoveeLedBleEditor);
}
