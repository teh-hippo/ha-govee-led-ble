import { expect, test, type Locator, type Page } from "./test";
import type { GoveeCustomEffectEditor } from "../../src/custom-effect-editor";
import type { NativeEffectContent } from "../../src/types";
import type { HomeAssistant } from "../../src/types";
import type { GoveeLedEffectStudio } from "../../src/panel";
import type { GoveePaintedSegmentEditor } from "../../src/painted-segment-editor";

test.beforeEach(async ({ page }) => {
  await page.goto("/tests/browser/fixtures/palette-editor.html");
});

test("projector advanced layers can be created, reordered and removed through shared native controls", async ({ page }) => {
  await page.evaluate(async () => {
    const modulePath = "/src/custom-effect-editor.ts";
    const { GoveeCustomEffectEditor } = await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const catalogue = contracts.responses.custom_catalogue.models.H6093;
    const content = structuredClone(catalogue.templates.find((item: { id: string }) =>
      item.id === "template:projector:advanced").content);
    content.projector_layers[0].movement_speed = 11;
    const editor = new GoveeCustomEffectEditor() as GoveeCustomEffectEditor;
    editor.catalogue = catalogue;
    editor.nativeContent = content;
    editor.addEventListener("native-content-changed", ((event: CustomEvent<{ content: NativeEffectContent }>) => {
      editor.nativeContent = event.detail.content;
      editor.dataset.content = JSON.stringify(event.detail.content);
    }) as EventListener);
    document.body.replaceChildren(editor);
  });
  const editor = page.locator("govee-custom-effect-editor");
  await editor.getByRole("button", { name: "Duplicate layer", exact: true }).click();
  await expect(editor.getByRole("heading", { name: "Projector layer 2", exact: true })).toBeVisible();
  await editor.getByRole("slider", { name: "Aurora movement", exact: true }).nth(1).press("ArrowRight");
  await editor.getByRole("button", { name: "Move earlier", exact: true }).nth(1).click();
  await expect.poll(async () => editor.evaluate(element =>
    JSON.parse(element.dataset.content!).projector_layers.map((layer: { movement_speed: number }) => layer.movement_speed)
  )).toEqual([12, 11]);
  await editor.getByRole("button", { name: "Remove layer", exact: true }).first().click();
  await expect(editor.getByRole("heading", { name: "Projector layer 2", exact: true })).toHaveCount(0);
});

async function mountFeedbackPanel(page: Page, model = "H7025", showFeedback = true): Promise<void> {
  await page.evaluate(async ({ model, showFeedback }) => {
    const modulePath = "/src/panel.ts";
    const { GoveeLedEffectStudio } = await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const device = {
      ...contracts.responses.devices.find((item: { model: string }) => item.model === model),
      hw_version: "3.01.10",
      fw_version: null,
      show_experimental_feedback: showFeedback,
      display_name: "Private device name",
      effect_categories: [],
    };
    const responses: Record<string, unknown> = {
      info: { ...contracts.responses.editor_info, integration_version: "7.24.4rc1" },
      devices: { devices: [device] },
      "library/list": { generation: 0, items: [] },
      "custom/catalogue": { catalogue: contracts.responses.custom_catalogue },
      "user_state/get": {
        user_state: { owner_id: "private-owner", recent_colours: [], selected_config_entry_id: device.config_entry_id, navigation: {} },
      },
    };
    const calls: string[] = [];
    const panel = new GoveeLedEffectStudio() as GoveeLedEffectStudio;
    const hass: HomeAssistant = {
      user: { is_admin: false },
      async callWS<T>(message: Record<string, unknown>): Promise<T> {
        const type = String(message.type).replace("ha_govee_led_ble/editor/", "");
        calls.push(type);
        panel.dataset.calls = JSON.stringify(calls);
        if (!(type in responses)) throw new Error(`Unexpected WebSocket call: ${type}`);
        return structuredClone(responses[type]) as T;
      },
      async callService() { throw new Error("Feedback must not call services"); },
      connection: { async subscribeMessage() { return () => undefined; } },
    };
    panel.hass = hass;
    document.body.replaceChildren(panel);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: window.innerWidth < 1000
        ? { writeText: () => Promise.reject(new DOMException("Denied", "NotAllowedError")) }
        : undefined,
    });
  }, { model, showFeedback });
}

for (const width of [320, 1280]) {
  test(`Canvas saves and recalls in the normal workspace at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(async () => {
      const modulePath = "/src/panel.ts";
      const { GoveeLedEffectStudio } = await import(modulePath);
      const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
      const device = contracts.responses.devices.find((item: { model: string }) => item.model === "H617A");
      const userState = {
        owner_id: "test-owner", recent_colours: [], selected_config_entry_id: device.config_entry_id,
        navigation: { section: "custom", custom_category: "single-layer", auto_save: false },
      };
      let saved: typeof contracts.responses.library_item | undefined;
      const library = () => ({
        generation: saved ? 1 : 0,
        items: saved ? [{
          ...contracts.responses.library_snapshot.items[0],
          id: saved.id, kind: saved.content.kind, name: saved.name, version: saved.version, content_hash: saved.content_hash,
        }] : [],
      });
      const panel = new GoveeLedEffectStudio();
      panel.hass = {
        user: { is_admin: true },
        async callWS<T>(message: Record<string, unknown>): Promise<T> {
          const type = String(message.type).replace("ha_govee_led_ble/editor/", "");
          if (type === "library/create") {
            saved = {
              ...contracts.responses.library_item, name: message.name, content: message.content,
              content_hash: "a".repeat(64), origin: { kind: "authored", source_id: null },
            };
            panel.dataset.saved = JSON.stringify(saved.content);
            return { item: saved, library: library() } as T;
          }
          const responses: Record<string, unknown> = {
            info: contracts.responses.editor_info, devices: { devices: [device] }, device: { device },
            "library/list": library(), "library/get": { item: saved },
            "custom/catalogue": { catalogue: contracts.responses.custom_catalogue },
            "user_state/get": { user_state: userState }, "user_state/update": { user_state: userState },
            "preview/cancel": { cancelled: true, devices: [] },
          };
          if (!(type in responses)) throw new Error(`Unexpected WebSocket call: ${type}`);
          return structuredClone(responses[type]) as T;
        },
        async callService() { throw new Error("Saving must not control a light"); },
        connection: { async subscribeMessage() { return () => undefined; } },
      } as HomeAssistant;
      document.body.replaceChildren(panel);
    });
    const panel = page.locator("ha-govee-led-ble-editor");
    const live = page.getByRole("button", { name: "Live", exact: true });
    await expect(live).toBeVisible();
    if (await live.getAttribute("aria-pressed") === "true") await live.click();
    await page.getByRole("button", { name: "Canvas", exact: true }).click();
    await page.getByRole("button", { name: "New", exact: true }).click();
    const save = page.getByRole("button", { name: "Save", exact: true });
    await expect(save).toBeEnabled();
    await expect(page.getByRole("slider", { name: "Speed", exact: true })).toHaveCount(0);
    await expect(page.getByRole("slider", { name: "RGB scale", exact: true })).toHaveCount(0);
    await expect(panel.locator("govee-painted-segment-editor button")).toHaveText(
      Array.from({ length: 15 }, (_, index) => String(index + 1)),
    );
    await expect(panel.locator("govee-painted-segment-editor .flow-wrap")).toHaveText(
      width < 600 ? ["5 ↵ 6", "10 ↵ 11"] : [],
    );
    await expect(panel.locator("header details")).toHaveCount(0);
    for (let index = 0; index < 7; index++) {
      await panel.locator("govee-painted-segment-editor button").nth(index).click();
    }
    await expect(save).toBeEnabled();
    const underlineOffset = await panel.locator(".editable-title").evaluate(row => {
      const underline = [row, ...row.children].find(element => Number.parseFloat(getComputedStyle(element).borderBottomWidth) > 0)!;
      return underline.getBoundingClientRect().right - row.getBoundingClientRect().right;
    });
    expect(Math.abs(underlineOffset)).toBeLessThan(1);
    await save.click();
    await expect(panel).toHaveAttribute("data-saved", /"kind":"static_rgb".*"rgb_scale":100/);
    const savedSegments = JSON.parse((await panel.getAttribute("data-saved"))!).segments;
    expect(savedSegments[0]).not.toEqual([0, 0, 0]);
    expect(savedSegments.slice(7)).toEqual(Array(8).fill([0, 0, 0]));
    await page.getByRole("button", { name: "New", exact: true }).click();
    await page.getByRole("button", { name: "New Canvas User-created effect", exact: true }).click();
    await expect(panel.locator("govee-painted-segment-editor button").nth(7)).toHaveAttribute("aria-label", "Segment 8, #000000");
    await page.getByRole("button", { name: "Off", exact: true }).click();
    await page.getByRole("button", { name: "Fill all", exact: true }).click();
    await expect(panel.getByRole("button", { name: /^Segment \d+, #000000$/ })).toHaveCount(15);
    await expect(save).toBeEnabled();
    await page.getByRole("button", { name: "Clear all", exact: true }).click();
    await expect(panel.getByRole("button", { name: /^Segment \d+, #000000$/ })).toHaveCount(15);
    await expect(save).toBeEnabled();
    await expect(page.getByRole("button", { name: "Save As", exact: true })).toBeEnabled();
    expect(await panel.locator(".editor-surface").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  });
}

test("Auto Save keeps keyboard editing responsive and serialises the latest draft", async ({ page }) => {
  await page.evaluate(async () => {
    const modulePath = "/src/panel.ts";
    const { GoveeLedEffectStudio } = await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const device = contracts.responses.devices.find((item: { model: string }) => item.model === "H617A");
    let saved = contracts.responses.library_item;
    let generation = 1;
    const updates: Array<{ speed: number; version: number }> = [];
    const library = () => ({
      generation,
      items: [{ ...contracts.responses.library_snapshot.items[0], name: saved.name, version: saved.version, content_hash: saved.content_hash }],
    });
    const userState = {
      owner_id: "test-owner",
      recent_colours: [],
      selected_config_entry_id: device.config_entry_id,
      navigation: { section: "custom", custom_category: "single-layer", auto_save: true },
    };
    const panel = new GoveeLedEffectStudio() as GoveeLedEffectStudio;
    panel.hass = {
      user: { is_admin: true },
      async callWS<T>(message: Record<string, unknown>): Promise<T> {
        const type = String(message.type).replace("ha_govee_led_ble/editor/", "");
        if (type === "library/update") {
          const content = message.content as { speed: number };
          updates.push({ speed: content.speed, version: Number(message.expected_version) });
          panel.dataset.updates = JSON.stringify(updates);
          await new Promise<void>(resolve => {
            document.addEventListener("release-studio-save", () => resolve(), { once: true });
          });
          if (message.expected_version !== saved.version) throw new Error("Stale saved version");
          saved = {
            ...saved,
            name: message.name,
            content: message.content,
            version: saved.version + 1,
            content_hash: String(saved.version + 1).padStart(64, "0"),
          };
          generation += 1;
          panel.dataset.savedSpeed = String(content.speed);
          return { item: saved, library: library() } as T;
        }
        const responses: Record<string, unknown> = {
          info: contracts.responses.editor_info,
          devices: { devices: [device] },
          device: { device },
          "library/list": library(),
          "library/get": { item: saved },
          "custom/catalogue": { catalogue: contracts.responses.custom_catalogue },
          "user_state/get": { user_state: userState },
          "user_state/update": { user_state: userState },
          "preview/cancel": { cancelled: true, devices: [] },
        };
        if (!(type in responses)) throw new Error(`Unexpected WebSocket call: ${type}`);
        return structuredClone(responses[type]) as T;
      },
      async callService() { throw new Error("Saving must not control a light"); },
      connection: { async subscribeMessage() { return () => undefined; } },
    } as HomeAssistant;
    document.body.replaceChildren(panel);
  });
  const panel = page.locator("ha-govee-led-ble-editor");
  const live = page.getByRole("button", { name: "Live", exact: true });
  await expect(live).toBeVisible();
  if (await live.getAttribute("aria-pressed") === "true") await live.click();
  await page.getByRole("button", { name: "Canonical painted effect User-created effect", exact: true }).click();
  const speed = page.getByRole("slider", { name: "Speed", exact: true });
  const initialSpeed = Number(await speed.inputValue());
  await speed.focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel).toHaveAttribute("data-updates", JSON.stringify([{ speed: initialSpeed + 1, version: 1 }]));
  await expect(speed).toBeEnabled();
  await expect(speed).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(speed).toHaveValue(String(initialSpeed + 2));
  await page.evaluate(() => document.dispatchEvent(new Event("release-studio-save")));
  await expect(panel).toHaveAttribute("data-updates", JSON.stringify([
    { speed: initialSpeed + 1, version: 1 },
    { speed: initialSpeed + 2, version: 2 },
  ]));
  await expect(speed).toHaveValue(String(initialSpeed + 2));
  await page.evaluate(() => document.dispatchEvent(new Event("release-studio-save")));
  await expect(page.getByRole("button", { name: "Auto Save", exact: true })).toHaveAttribute("aria-busy", "false");
  await expect(panel).toHaveAttribute("data-saved-speed", String(initialSpeed + 2));
  await expect(speed).toBeFocused();

  await page.getByRole("button", { name: "Auto Save", exact: true }).click();
  await speed.press("ArrowRight");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(speed).toBeDisabled();
  await page.evaluate(() => document.dispatchEvent(new Event("release-studio-save")));
  await expect(speed).toBeEnabled();
});

for (const viewport of [{ width: 320, height: 844 }, { width: 1280, height: 900 }]) {
  test(`compact feedback remains copyable and links to one issue at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mountFeedbackPanel(page);
    const share = page.getByRole("button", { name: "Feedback", exact: true });
    await expect(share).toBeVisible();
    const notice = page.locator(".support-notice");
    expect(await notice.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await notice.locator(":scope > span").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    const centres = await notice.locator(":scope > span, button").evaluateAll(elements =>
      elements.map(element => { const rect = element.getBoundingClientRect(); return rect.y + rect.height / 2; }));
    expect(Math.max(...centres) - Math.min(...centres)).toBeLessThan(1);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const callsBefore = await page.locator("ha-govee-led-ble-editor").getAttribute("data-calls");
    await share.click();
    const dialog = page.getByRole("dialog", { name: "Device feedback" });
    await expect(dialog).toBeVisible();
    const report = dialog.getByRole("textbox", { name: "Details", exact: true });
    await expect(report).toHaveValue(/Hardware version: 3\.01\.10/);
    await expect(report).toHaveValue(/Firmware version: not yet observed/);
    await expect(report).not.toHaveValue(/Private device name|private-owner|h7025-main/);
    await dialog.getByRole("button", { name: "Copy details", exact: true }).click();
    await expect(dialog.getByRole("status")).toContainText(viewport.width < 1000 ? "Copying failed" : "Copying is unavailable");
    expect(await report.evaluate((element: HTMLTextAreaElement) => {
      element.focus();
      element.select();
      return element.selectionEnd === element.value.length;
    })).toBe(true);
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.evaluate(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { async writeText(text: string) { document.body.dataset.copiedReport = text; } },
      });
    });
    await dialog.getByRole("button", { name: "Copy details", exact: true }).click();
    await expect(dialog.getByRole("status")).toContainText("Copied.");
    expect(await page.locator("body").getAttribute("data-copied-report")).toBe(await report.inputValue());
    const openGitHub = dialog.getByRole("button", { name: "Open GitHub (new tab)", exact: true });
    const reportBox = await report.boundingBox();
    const copyBox = await dialog.getByRole("button", { name: "Copy details", exact: true }).boundingBox();
    const openBox = await openGitHub.boundingBox();
    if (!reportBox || !copyBox || !openBox) throw new Error("Feedback actions must be visible");
    expect(copyBox.y).toBeGreaterThanOrEqual(reportBox.y + reportBox.height);
    expect(copyBox.y + copyBox.height).toBeLessThan(openBox.y);
    await page.context().route("https://github.com/teh-hippo/ha-govee-led-ble/issues/451", route =>
      route.fulfill({ contentType: "text/html", body: "<h1>Model confirmation issue</h1>" }));
    const opened = page.waitForEvent("popup");
    await openGitHub.click();
    const issuePage = await opened;
    await expect(issuePage).toHaveURL("https://github.com/teh-hippo/ha-govee-led-ble/issues/451");
    await issuePage.close();
    expect(await page.locator("ha-govee-led-ble-editor").getAttribute("data-calls")).toBe(callsBefore);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(share).toBeFocused();
  });
}

test("feedback dismissal survives reloads, stays per light and does not leak to another tab", async ({ page }) => {
  await mountFeedbackPanel(page);
  await page.getByRole("button", { name: "Hide feedback for this session" }).click();
  await expect(page.locator(".support-notice")).toHaveCount(0);
  await page.reload();
  await mountFeedbackPanel(page);
  await expect(page.locator(".support-notice")).toHaveCount(0);
  await mountFeedbackPanel(page, "H6179");
  await expect(page.getByRole("button", { name: "Feedback", exact: true })).toBeVisible();
  await mountFeedbackPanel(page, "H6097", false);
  await expect(page.locator(".support-notice")).toHaveCount(0);
  await mountFeedbackPanel(page, "H6125");
  await expect(page.locator(".support-notice")).toHaveCount(0);

  const otherTab = await page.context().newPage();
  await otherTab.goto("/tests/browser/fixtures/palette-editor.html");
  await mountFeedbackPanel(otherTab);
  await expect(otherTab.getByRole("button", { name: "Feedback", exact: true })).toBeVisible();
  await otherTab.close();
});

test("native layer moves retain authored speeds and allow building a mixed effect", async ({ page }) => {
  await page.evaluate(async () => {
    const modulePath = "/src/custom-effect-editor.ts";
    await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const templates = contracts.responses.custom_catalogue.models.H60A6.templates;
    const content: NativeEffectContent = structuredClone(templates.find(
      (template: {content: NativeEffectContent}) =>
        template.content.kind === "native_effect" && template.content.family === 797,
    ).content);
    const layer = content.layers[0];
    if (layer.type !== "diy") throw new Error("Expected native DIY layer");
    content.layers = [{ ...layer, speed: 85 }, { ...layer, speed: 58 }];
    content.speed_index = 1;
    const editor = document.createElement("govee-custom-effect-editor") as GoveeCustomEffectEditor;
    editor.nativeContent = content;
    editor.catalogue = contracts.responses.custom_catalogue.models.H60A6;
    editor.addEventListener("native-content-changed", event => {
      editor.nativeContent = (event as CustomEvent<{ content: NativeEffectContent }>).detail.content;
    });

    document.body.replaceChildren(editor);
    await editor.updateComplete;
  });
  const editor = page.locator("govee-custom-effect-editor");
  const state = () => editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  const speeds = (content: NativeEffectContent) => content.layers.map(layer => layer.type === "opaque" ? null : layer.speed);
  await editor.getByRole("button", {name: "Move later", exact: true}).click();
  expect(speeds(await state())).toEqual([58, 85]);
  expect((await state()).speed_index).toBeNull();
  await editor.evaluate(element => {
    const target = element as GoveeCustomEffectEditor;
    target.nativeContent = {...target.nativeContent!, speed_index: 1};
  });
  await editor.getByRole("button", {name: "Move earlier", exact: true}).click();
  expect(speeds(await state())).toEqual([85, 58]);
  expect((await state()).speed_index).toBeNull();
  await editor.getByRole("button", {name: "Duplicate layer", exact: true}).click();
  expect(speeds(await state())).toEqual([85, 58, 85]);
  await editor.getByRole("button", {name: "Remove layer", exact: true}).click();
  expect(speeds(await state())).toEqual([85, 58]);
});

test("native pole/base recipes retain siblings, fixed rates and independent palettes", async ({ page }) => {
  await page.evaluate(async () => {
    const modulePath = "/src/custom-effect-editor.ts";
    await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const catalogue = contracts.responses.custom_catalogue.models.H607C;
    const editor = document.createElement("govee-custom-effect-editor") as GoveeCustomEffectEditor;
    editor.nativeContent = structuredClone(catalogue.templates.find(
      (template: {id: string}) => template.id === "template:native:paired",
    ).content);
    editor.catalogue = catalogue;
    editor.addEventListener("native-content-changed", event => {
      editor.nativeContent = (event as CustomEvent<{content: NativeEffectContent}>).detail.content;
    });
    document.body.replaceChildren(editor);
    await editor.updateComplete;
  });
  const editor = page.locator("govee-custom-effect-editor");
  const before = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  await expect(editor.getByRole("checkbox", {name: "Include this effect", exact: true})).toHaveCount(2);
  await editor.getByRole("combobox").first().selectOption("113");
  await expect(editor.getByText("Speed: 50 (fixed)", {exact: true})).toBeVisible();
  const after = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  expect(after.layers[1]).toEqual(before.layers[1]);
  expect(after.layers[0]).toMatchObject({type: "diy", kind: 113, speed: 50, enabled: true});
  const palettes = editor.locator("section.card").first().locator("govee-palette-editor");
  await expect(palettes).toHaveCount(2);
  expect(await palettes.nth(0).evaluate(element => (element as HTMLElement & {minColours: number}).minColours)).toBe(1);
  expect(await palettes.nth(1).evaluate(element => (element as HTMLElement & {minColours: number}).minColours)).toBe(2);
  await editor.getByRole("checkbox", {name: "Include this effect", exact: true}).first().uncheck();
  const disabled = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  expect(disabled.layers[0]).toMatchObject({enabled: false});
  expect(disabled.layers[1]).toEqual(before.layers[1]);
  await expect(editor.getByRole("button", {name: "Add layer", exact: true})).toHaveCount(0);
  await expect(editor.getByRole("button", {name: "Move later", exact: true})).toHaveCount(0);
});

test("H1771 DIY sections can be edited without changing their sibling", async ({ page }) => {
  await page.evaluate(async () => {
    const modulePath = "/src/custom-effect-editor.ts";
    await import(modulePath);
    const contracts = await fetch("/tests/fixtures/backend-contracts.json").then(response => response.json());
    const catalogue = contracts.responses.custom_catalogue.models.H1771;
    const editor = document.createElement("govee-custom-effect-editor") as GoveeCustomEffectEditor;
    editor.nativeContent = structuredClone(catalogue.templates.find(
      (template: {id: string}) => template.id === "template:h1771:0:0",
    ).content);
    editor.catalogue = catalogue;
    editor.addEventListener("native-content-changed", event => {
      editor.nativeContent = (event as CustomEvent<{content: NativeEffectContent}>).detail.content;
    });
    document.body.replaceChildren(editor);
    await editor.updateComplete;
  });
  const editor = page.locator("govee-custom-effect-editor");
  const before = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  await expect(editor.getByRole("combobox").first()).toHaveValue("template:h1771:0:0");
  await editor.getByRole("combobox").nth(1).selectOption("template:h1771:1:1");
  const after = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  expect(after.layers[0]).toEqual(before.layers[0]);
  expect(after.layers[1]).toMatchObject({ type: "diy", kind: 1, parameter: 1, enabled: true });
  await expect(editor.getByText("Colour temperature", { exact: true })).toBeVisible();
  await expect(editor.locator("govee-palette-editor")).toHaveCount(1);
});

test("painted segment taps finish with a committed interaction", async ({
  page,
}) => {
  const context = page.getByTestId("painted-context");

  await context.getByRole("button", { name: "Segment 1, off" }).tap();

  await expect(context.getByTestId("painted-events")).toHaveText(
    JSON.stringify([
      { index: 0, interaction: "changing" },
      { index: 0, interaction: "committed" },
    ]),
  );
});

test("painted segment flow follows rendered columns through resize and geometry changes", async ({ page }) => {
  const editor = page.getByTestId("painted-context").locator("govee-painted-segment-editor");
  await page.setViewportSize({ width: 390, height: 900 });
  await editor.evaluate(element => {
    const painted = element as GoveePaintedSegmentEditor;
    painted.physical = true;
    painted.segments = Array.from({ length: 22 }, () => null);
  });
  await expect(editor.getByRole("button")).toHaveText(Array.from({ length: 22 }, (_, index) => String(index + 1)));
  await expect(editor.getByRole("button", { name: "IC 22, background", exact: true })).toBeVisible();
  await expect(editor.locator(".flow-wrap")).toHaveText(["5 ↵ 6", "10 ↵ 11", "15 ↵ 16", "20 ↵ 21"]);
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(editor.locator(".flow-wrap")).toHaveText(["15 ↵ 16"]);
  await editor.locator(".segments").evaluate(element => {
    (element as HTMLElement).style.gridTemplateColumns = "repeat(7, minmax(0, 1fr))";
  });
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(editor.locator(".flow-wrap")).toHaveText(["7 ↵ 8", "14 ↵ 15", "21 ↵ 22"]);
  await editor.evaluate(element => {
    (element as GoveePaintedSegmentEditor).segments = Array.from({ length: 4 }, () => null);
  });
  await expect(editor.getByRole("button")).toHaveText(["1", "2", "3", "4"]);
  await expect(editor.locator(".flow-wrap")).toHaveCount(0);
});

test("painted segment drags across a row wrap commit once and release for the next gesture", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const context = page.getByTestId("painted-context");
  const lastInRow = context.locator('[data-segment="4"] .segment-number');
  const firstInNextRow = context.getByRole("button", { name: "Segment 6, off" });

  await mouseDrag(page, lastInRow, firstInNextRow);

  const firstEvents = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(firstEvents[0]).toEqual({ index: 4, interaction: "changing" });
  expect(firstEvents.at(-1)).toEqual({
    index: 5,
    interaction: "committed",
  });
  expect(
    firstEvents.filter((event) => event.interaction === "committed"),
  ).toHaveLength(1);

  await context.getByRole("button", { name: /^Segment 1,/ }).tap();
  const nextEvents = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(nextEvents.at(-1)).toEqual({
    index: 0,
    interaction: "committed",
  });
});

test("cancelled painted strokes commit applied changes and release capture", async ({
  page,
}) => {
  const context = page.getByTestId("painted-context");
  const first = context.locator('[data-segment="0"]');
  await first.scrollIntoViewIfNeeded();
  const box = await first.boundingBox();
  expect(box).not.toBeNull();
  await page.evaluate(() => {
    const state = window as Window & { paintPointerId?: number };
    state.paintPointerId = undefined;
    window.addEventListener(
      "pointerdown",
      (event) => {
        state.paintPointerId = event.pointerId;
      },
      { capture: true, once: true },
    );
  });

  await page.mouse.move(
    box!.x + box!.width / 2,
    box!.y + box!.height / 2,
  );
  await page.mouse.down();
  const pointerId = await page.evaluate(
    () => (window as Window & { paintPointerId?: number }).paintPointerId,
  );
  expect(pointerId).toBeDefined();
  await first.dispatchEvent("pointercancel", {
    bubbles: true,
    buttons: 0,
    composed: true,
    isPrimary: true,
    pointerId,
    pointerType: "mouse",
  });
  await page.mouse.up();

  await expect(context.getByTestId("painted-events")).toHaveText(
    JSON.stringify([
      { index: 0, interaction: "changing" },
      { index: 0, interaction: "committed" },
    ]),
  );
  await context.getByRole("button", { name: "Segment 2, off" }).tap();
  const events = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(events.at(-1)).toEqual({
    index: 1,
    interaction: "committed",
  });
});

test("cancelled multi-effect touch drags do not poison the next reorder", async ({
  page,
}) => {
  const context = page.getByTestId("multi-context");
  const first = context.getByRole("button", {
    name: /Reorder Layer 1/,
  });
  const second = context.getByRole("button", {
    name: /Reorder Layer 2/,
  });

  await touchDrag(first, second, true);
  await expect(context.getByTestId("multi-order")).toHaveText("[2,3,4]");

  await touchDrag(first, second, false);
  await expect(context.getByTestId("multi-order")).toHaveText("[3,2,4]");
});

test("multi-effect row menus dismiss outside and restore focus on Escape", async ({
  page,
}) => {
  const context = page.getByTestId("multi-context");
  const firstMenu = context.getByLabel("Layer actions for Layer 1");

  await firstMenu.tap();
  await expect(context.getByRole("button", { name: "Remove" })).toBeVisible();
  await page.getByTestId("outside").tap();
  await expect(context.getByRole("button", { name: "Remove" })).toHaveCount(0);

  await firstMenu.tap();
  await firstMenu.press("Escape");
  await expect(context.getByRole("button", { name: "Remove" })).toHaveCount(0);
  await expect(firstMenu).toBeFocused();
});

test("applied-area pointer drags emit live updates and one commit", async ({
  page,
}) => {
  const context = page.getByTestId("area-context");
  const right = context.getByRole("slider", {
    name: "Applied area right edge",
  });
  await right.scrollIntoViewIfNeeded();
  const box = await right.boundingBox();
  expect(box).not.toBeNull();

  await page.mouse.move(
    box!.x + box!.width / 2,
    box!.y + box!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width / 2 + 36,
    box!.y + box!.height / 2,
    { steps: 3 },
  );
  await page.mouse.up();

  const interactions = await jsonOutput<string[]>(
    context.getByTestId("area-events"),
  );
  expect(interactions).toContain("changing");
  expect(interactions.at(-1)).toBe("committed");
  expect(
    interactions.filter((interaction) => interaction === "committed"),
  ).toHaveLength(1);
});

test("native colour input separates live input from committed change", async ({
  page,
}) => {
  const context = page.getByTestId("colour-context");
  const input = context.getByRole("textbox", { name: "Custom colour" });

  await input.fill("#123456");
  await expect(context.getByTestId("colour-events")).toHaveText(
    JSON.stringify([
      {
        colour: [18, 52, 86],
        type: "colour-changing",
      },
      {
        colour: [18, 52, 86],
        type: "colour-changed",
      },
    ]),
  );
  await input.blur();
  await expect(context.getByTestId("colour-events")).toHaveText(
    JSON.stringify([
      {
        colour: [18, 52, 86],
        type: "colour-changing",
      },
      {
        colour: [18, 52, 86],
        type: "colour-changed",
      },
    ]),
  );
});

test("information popovers stay within the mobile viewport and dismiss", async ({
  page,
}) => {
  const context = page.getByTestId("info-context");
  const trigger = context.getByRole("button", {
    name: "WebKit information",
  });
  const note = context.getByRole("note", {
    name: "WebKit information",
  });

  await trigger.scrollIntoViewIfNeeded();
  await trigger.tap();
  await expect(note).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await assertWithinViewport(page, note);

  await page.setViewportSize({ width: 320, height: 480 });
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(note).not.toBeVisible();

  await page.setViewportSize({ width: 393, height: 659 });
  await trigger.scrollIntoViewIfNeeded();
  await trigger.tap();
  await expect(note).toBeVisible();
  await page.getByTestId("outside").tap();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(note).not.toBeVisible();
});

async function mouseDrag(
  page: Page,
  source: Locator,
  target: Locator,
): Promise<void> {
  await source.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await page.mouse.move(
    sourceBox!.x + sourceBox!.width / 2,
    sourceBox!.y + sourceBox!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    targetBox!.x + targetBox!.width / 2,
    targetBox!.y + targetBox!.height / 2,
    { steps: 4 },
  );
  await page.mouse.up();
}

async function touchDrag(
  source: Locator,
  target: Locator,
  cancelled: boolean,
): Promise<void> {
  await source.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await source.evaluate(
    (
      element,
      { cancelled, sourceBox, targetBox },
    ) => {
      const start = {
        bubbles: true,
        composed: true,
        isPrimary: true,
        pointerId: 17,
        pointerType: "touch",
        clientX: sourceBox.x + sourceBox.width / 2,
        clientY: sourceBox.y + sourceBox.height / 2,
      };
      const end = {
        ...start,
        clientX: targetBox.x + targetBox.width / 2,
        clientY: targetBox.y + targetBox.height / 2,
      };
      element.dispatchEvent(
        new PointerEvent("pointerdown", {
          ...start,
          buttons: 1,
        }),
      );
      element.dispatchEvent(
        new PointerEvent("pointermove", {
          ...end,
          buttons: 1,
        }),
      );
      element.dispatchEvent(
        new PointerEvent(cancelled ? "pointercancel" : "pointerup", {
          ...end,
          buttons: 0,
        }),
      );
    },
    {
      cancelled,
      sourceBox: sourceBox!,
      targetBox: targetBox!,
    },
  );
  await settle(source.page());
}

async function jsonOutput<T>(output: Locator): Promise<T> {
  return JSON.parse((await output.textContent()) ?? "null") as T;
}

async function assertWithinViewport(
  page: Page,
  element: Locator,
): Promise<void> {
  await expect
    .poll(async () => {
      const box = await element.boundingBox();
      const viewport = page.viewportSize();
      return (
        box !== null &&
        viewport !== null &&
        box.x >= 0 &&
        box.y >= 0 &&
        box.x + box.width <= viewport.width &&
        box.y + box.height <= viewport.height
      );
    })
    .toBe(true);
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}
