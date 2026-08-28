const staticBase = new URL("./", import.meta.url);
const moduleUrl = new URL(import.meta.url);
const expectedAssetVersion = Number(
  moduleUrl.searchParams.get("asset_version") ?? "",
);
const loadedAssetVersionKey =
  "__HA_GOVEE_LED_BLE_EDITOR_LOADED_ASSET_VERSION__";
const upgradeOverlayId = "ha-govee-led-ble-editor-upgrade";
const editorElementName = "ha-govee-led-ble-editor";

function showUpgradeOverlay() {
  if (document.getElementById(upgradeOverlayId)) {
    return;
  }
  const overlay = document.createElement("div");
  overlay.id = upgradeOverlayId;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", `${upgradeOverlayId}-title`);
  const shadow = overlay.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        position: fixed;
        inset: 0;
        z-index: 2147483647;
        display: grid;
        place-items: center;
        box-sizing: border-box;
        padding: 24px;
        background: rgb(0 0 0 / 45%);
        color: var(--primary-text-color, #212121);
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
      }
      ha-card {
        box-sizing: border-box;
        width: min(100%, 520px);
        padding: 24px;
        border-radius: var(--ha-card-border-radius, 12px);
        background: var(--ha-card-background, var(--card-background-color, #fff));
        box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgb(0 0 0 / 30%));
      }
      h1 {
        margin: 0 0 12px;
        font-size: 24px;
        line-height: 1.2;
      }
      p {
        margin: 0 0 20px;
        line-height: 1.5;
      }
      button {
        min-height: 40px;
        padding: 0 16px;
        border: 0;
        border-radius: 4px;
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
        cursor: pointer;
        font: inherit;
        font-weight: 500;
      }
      button:focus-visible {
        outline: 2px solid var(--primary-text-color, #212121);
        outline-offset: 2px;
      }
    </style>
    <ha-card>
      <h1 id="${upgradeOverlayId}-title">Effect Studio was updated</h1>
      <p>Reload to use the updated Effect Studio. Your current edits remain unchanged until you reload.</p>
      <button type="button">Reload Effect Studio</button>
    </ha-card>
  `;
  shadow.querySelector("button").addEventListener("click", () => {
    window.location.reload();
  });
  (document.body ?? document.documentElement).append(overlay);
}

async function loadEditor() {
  const manifestUrl = new URL("manifest.json", staticBase);
  manifestUrl.searchParams.set(
    "asset_version",
    String(expectedAssetVersion),
  );
  const response = await fetch(manifestUrl, {
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Effect Studio manifest returned HTTP ${response.status}`);
  }
  const manifest = await response.json();
  const bootstrap = manifest?.bootstrap;
  if (
    bootstrap !== "effect-studio-bootstrap.js" ||
    manifest?.asset_version !== expectedAssetVersion
  ) {
    throw new Error("Effect Studio manifest contains an invalid asset contract");
  }
  const bootstrapUrl = new URL(bootstrap, staticBase);
  bootstrapUrl.searchParams.set(
    "asset_version",
    String(expectedAssetVersion),
  );
  await import(bootstrapUrl.href);
}

const loadedAssetVersion = globalThis[loadedAssetVersionKey];
if (
  (loadedAssetVersion !== undefined &&
    loadedAssetVersion !== expectedAssetVersion) ||
  (loadedAssetVersion === undefined && customElements.get(editorElementName))
) {
  showUpgradeOverlay();
} else if (loadedAssetVersion === undefined) {
  try {
    if (
      !Number.isSafeInteger(expectedAssetVersion) ||
      expectedAssetVersion < 1
    ) {
      throw new Error("Effect Studio loader URL has no valid asset version");
    }
    await loadEditor();
    globalThis[loadedAssetVersionKey] = expectedAssetVersion;
  } catch (error) {
    console.error("Effect Studio failed to load.", error);
    if (!customElements.get(editorElementName)) {
      customElements.define(
        editorElementName,
        class extends HTMLElement {
          connectedCallback() {
            this.render();
          }

          set panel(value) {
            this.panelConfig = value;
            this.render();
          }

          render() {
            if (!this.isConnected) {
              return;
            }
            const configurationPath =
              this.panelConfig?.config?.configuration_path ??
              "/config/integrations/integration/ha_govee_led_ble";
            this.innerHTML = `
              <style>
                :host { display: block; padding: 24px; }
                ha-card { margin: 0 auto; max-width: 640px; padding: 24px; }
                h1 { margin: 0 0 16px; font-size: 24px; }
                p { margin: 0 0 20px; line-height: 1.5; }
              </style>
              <ha-card>
                <h1>Effect Studio is unavailable</h1>
                <p>The development frontend could not be loaded. Refresh after the deployment completes.</p>
                <a href="${configurationPath}">Open integration configuration</a>
              </ha-card>
            `;
          }
        },
      );
    }
  }
}
