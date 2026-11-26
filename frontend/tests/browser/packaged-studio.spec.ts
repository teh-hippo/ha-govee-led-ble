import { readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { parseAst } from "rolldown/parseAst";
import { Visitor } from "rolldown/utils";
import type { GoveeLedEffectStudio } from "../../src/panel";
import type { HomeAssistant } from "../../src/types";
import { expect, test } from "./test";

const assets = resolve(import.meta.dirname, "../../../custom_components/ha_govee_led_ble/frontend");
const manifest = JSON.parse(await readFile(resolve(assets, "manifest.json"), "utf8")) as {
  bootstrap: string;
  chunks: string[];
  asset_version: number;
};

test("packaged bootstrap and lazy chunks avoid class static blocks unsupported by Safari 15", async () => {
  for (const filename of [manifest.bootstrap, ...manifest.chunks]) {
    const source = await readFile(resolve(assets, filename), "utf8");
    const blocks: number[] = [];
    new Visitor({ StaticBlock(node) { blocks.push(node.start); } }).visit(parseAst(source));
    expect(blocks, filename).toEqual([]);
  }
});

for (const legacyCss of [false, true]) {
  test(`packaged Studio loads and edits Canvas with ${legacyCss ? "fallback" : "modern"} CSS`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width: 375, height: 667 });
    await page.route("**/packaged-studio/**", async route => {
      const filename = basename(new URL(route.request().url()).pathname);
      if (filename === "index.html") {
        await route.fulfill({
          contentType: "text/html",
          body: `<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
              body { margin: 0; --primary-text-color: #212121; --primary-background-color: #fff; }
            </style>`,
        });
        return;
      }
      let body = await readFile(resolve(assets, filename), "utf8");
      if (legacyCss) {
        body = body.replaceAll("color-mix(", "unsupported-color-mix(")
          .replaceAll("container-type:", "unsupported-container-type:");
      }
      await route.fulfill({
        contentType: filename.endsWith(".json") ? "application/json" : "text/javascript",
        body,
      });
    });
    await page.goto("/packaged-studio/index.html");
    const contracts = JSON.parse(await readFile(resolve(import.meta.dirname, "../fixtures/backend-contracts.json"), "utf8"));
    await page.evaluate(async ({ assetVersion, contracts }) => {
      localStorage.setItem("ha_govee_led_ble/effect_studio/live_apply", "false");
      const modulePath = `/packaged-studio/editor-loader.js?asset_version=${assetVersion}`;
      await import(modulePath);
      const device = contracts.responses.devices.find((item: { model: string }) => item.model === "H617A");
      const userState = {
        owner_id: "test-owner", recent_colours: [], selected_config_entry_id: device.config_entry_id,
        navigation: { section: "custom", custom_category: "single-layer", auto_save: false },
      };
      const responses: Record<string, unknown> = {
        info: contracts.responses.editor_info,
        devices: { devices: [device] },
        device: { device },
        "library/list": { generation: 0, items: [] },
        "custom/catalogue": { catalogue: contracts.responses.custom_catalogue },
        "user_state/get": { user_state: userState },
        "user_state/update": { user_state: userState },
        "preview/cancel": { cancelled: true, devices: [] },
      };
      const panel = document.createElement("ha-govee-led-ble-editor") as GoveeLedEffectStudio;
      panel.hass = {
        user: { is_admin: true },
        async callWS<T>(message: Record<string, unknown>): Promise<T> {
          const type = String(message.type).replace("ha_govee_led_ble/editor/", "");
          if (!(type in responses)) throw new Error(`Unexpected WebSocket call: ${type}`);
          return structuredClone(responses[type]) as T;
        },
        async callService() { throw new Error("Smoke testing must not control a light"); },
        connection: { async subscribeMessage() { return () => undefined; } },
      } as HomeAssistant;
      document.body.append(panel);
    }, { assetVersion: manifest.asset_version, contracts });
    const panel = page.locator("ha-govee-led-ble-editor");
    await expect(panel.getByRole("heading", { name: "Effect Studio", exact: true })).toBeAttached();
    expect(await panel.evaluate(element => {
      const style = getComputedStyle(element);
      return ["--studio-blue-soft", "--studio-switch-track-off", "--studio-switch-track-on", "--studio-switch-thumb-off"]
        .every(token => CSS.supports("color", style.getPropertyValue(token).trim()));
    })).toBe(true);
    await panel.getByRole("button", { name: "Canvas", exact: true }).tap();
    await panel.getByRole("button", { name: "New", exact: true }).tap();
    await expect(panel.locator("govee-painted-segment-editor button")).toHaveCount(15);
    await panel.locator("govee-painted-segment-editor button").first().tap();
    await expect(panel.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
    await panel.getByRole("button", { name: "Off", exact: true }).tap();
    await panel.getByRole("button", { name: "Fill all", exact: true }).tap();
    await expect(panel.getByRole("button", { name: /^Segment \d+, #000000$/ })).toHaveCount(15);
    await expect(panel.locator("govee-painted-segment-editor button").first()).toHaveCSS("border-top-style", "solid");
    expect(await panel.locator(".editor-surface").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}
