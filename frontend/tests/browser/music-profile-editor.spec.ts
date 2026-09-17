import { expect, test } from "@playwright/test";
import type { GoveeMusicProfileEditor } from "../../src/music-profile-editor";

for (const width of [390, 1280]) {
  test(`optional music palette edits, bounds and reset at ${width}px`, async ({ page }) => {
    await page.setViewportSize({width, height: 900});
    await page.goto("/tests/browser/fixtures/music-profile-editor.html?palette");
    const editor = page.locator("govee-music-profile-editor");
    const palette = page.locator("govee-palette-editor");
    await expect(palette).toBeVisible();
    expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content!.palette)).toBeUndefined();
    await palette.getByRole("button", {name: "Add colour", exact: true}).click();
    expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content!.palette?.length)).toBe(3);
    await page.getByText("Music colours", {exact: true}).click();
    for (let i = 3; i < 8; i++) {
      await palette.getByRole("button", {name: "Add colour", exact: true}).click();
      await page.getByText("Music colours", {exact: true}).click();
    }
    await expect(palette.getByRole("button", {name: "Add colour", exact: true})).toBeHidden();
    await page.getByRole("button", {name: "Use default colours"}).click();
    expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content!.palette)).toBeUndefined();
    await expect(palette.getByRole("button", {name: "Add colour", exact: true})).toBeVisible();
    await editor.evaluate(el => { (el as GoveeMusicProfileEditor).disabled = true; });
    await expect(palette.getByRole("button", {name: "Add colour", exact: true})).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("unqualified music palette is not editable", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?unknown");
  await expect(page.locator("govee-palette-editor")).toBeHidden();
});

test("music controls use variant defaults and bounds", async ({ page }) => {
  await page.setViewportSize({width: 1280, height: 900});
  await page.goto("/tests/browser/fixtures/music-profile-editor.html");
  const point = page.getByRole("slider", { name: "Point", exact: true });
  await expect(point).toHaveAttribute("min", "6");
  await expect(point).toHaveAttribute("max", "12");
  await expect(point).toHaveValue("8");
  await expect(page.getByRole("checkbox", { name: "Gradient" })).not.toBeChecked();
  await expect(page.getByLabel("Colour mode")).toBeHidden();
  await expect(page.getByLabel("Style", {exact: true})).toBeHidden();
});

test("unknown dependent parameters do not hide the selector", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?unknown");
  await expect(page.getByRole("slider", { name: "Point", exact: true })).toBeHidden();
  await expect(page.getByLabel("Reactive effect")).toBeVisible();
});

test("new declared Fountain speed renders and survives editing", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?fountain");
  await expect(page.getByLabel("Direction", {exact: true})).toBeVisible();
  const speed = page.getByRole("slider", {name: "Speed", exact: true});
  await expect(speed).toHaveAttribute("min", "16");
  await expect(speed).toHaveAttribute("max", "80");
  await expect(speed).toHaveValue("80");
  await speed.evaluate((element) => {
    (element as HTMLInputElement).value = "16";
    element.dispatchEvent(new Event("input", {bubbles: true}));
    element.dispatchEvent(new Event("change", {bubbles: true}));
  });
  await page.getByLabel("Direction", {exact: true}).selectOption("two_way");
  await expect(speed).toHaveValue("16");
  expect(await page.locator("govee-music-profile-editor").evaluate((element) =>
    (element as HTMLElement & {content: {parameters: unknown}}).content.parameters,
  )).toEqual({speed: 16, direction: "two_way"});
});

test("H617A fixed colour contract follows the exact legacy editor roster", async ({ page }) => {
  for (const mode of ["spectrum", "rolling", "energetic"]) {
    await page.goto(`/tests/browser/fixtures/music-profile-editor.html?mode=${mode}`);
    const control = page.getByLabel("Colour mode", {exact: true});
    if (mode === "energetic") {
      await expect(control).toBeHidden();
    } else {
      await control.selectOption("fixed");
      await expect(page.getByRole("group", {name: "Fixed colour", exact: true})).toBeVisible();
    }
  }
});

test("Hopping background uses RGB picker and exact no-colour sentinel without dropping siblings", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?mode=hopping");
  const editor = page.locator("govee-music-profile-editor");
  await editor.evaluate(el => {
    const editor = el as GoveeMusicProfileEditor;
    editor.content = {...editor.content!, palette: [[12, 34, 56]], parameters: {background: 0, relative_brightness: 17}};
  });
  await expect(page.getByRole("slider", {name: "Background", exact: true})).toBeHidden();
  await expect(page.getByRole("group", {name: "Background colour", exact: true})).toBeVisible();
  await page.getByRole("button", {name: "No colour", exact: true}).click();
  expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content)).toMatchObject({
    palette: [[12, 34, 56]], parameters: {background: 0x010101, relative_brightness: 17},
  });
  await page.locator("govee-single-colour-field").evaluate(el => el.dispatchEvent(new CustomEvent("colour-changed", {
    detail: {colour: [32, 96, 160]}, bubbles: true, composed: true,
  })));
  expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content)).toMatchObject({
    palette: [[12, 34, 56]], parameters: {background: 0x2060a0, relative_brightness: 17},
  });
});

test("Piano gradient remains editable with unknown IC count", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?mode=piano_keys");
  await expect(page.getByRole("slider", {name: "Key count", exact: true})).toBeHidden();
  await page.getByRole("checkbox", {name: "Gradient", exact: true}).check();
  expect(await page.locator("govee-music-profile-editor").evaluate(el => (el as GoveeMusicProfileEditor).content!.parameters.gradient)).toBe(true);
  await expect(page.locator("govee-palette-editor")).toBeVisible();
});

test("retained-body edit emits only explicit intent and leaves fresh content intact", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/music-profile-editor.html?unknown");
  const editor = page.locator("govee-music-profile-editor");
  await editor.evaluate(el => {
    const editor = el as GoveeMusicProfileEditor;
    editor.configEntryId = "device-a";
    editor.retainedEdit = {
      mode: editor.content!.mode, revision: 7, parameters: { gradient: false }, calm: null,
      settings: { available: false, style: false, calm_default: false, colour: false,
        evidence: "APK", palette_size: 2, parameters: {
          gradient: { kind: "switch", default: false, min: 0, max: 1, options: [] },
        } },
    };
    el.addEventListener("retained-music-edit", event => {
      el.setAttribute("data-edit", JSON.stringify((event as CustomEvent).detail));
    });
  });
  const before = await editor.evaluate(el => (el as GoveeMusicProfileEditor).content);
  const retained = editor.locator("section").filter({hasText: "Edit retained device music"});
  await expect(retained.getByRole("button", {name: "Apply retained-body edits"})).toBeDisabled();
  await retained.getByRole("checkbox", {name: "Gradient"}).check();
  await editor.evaluate(async el => {
    const editor = el as GoveeMusicProfileEditor;
    editor.retainedEdit = structuredClone(editor.retainedEdit);
    editor.content = structuredClone(editor.content);
    await editor.updateComplete;
  });
  await expect(retained.getByRole("checkbox", {name: "Gradient"})).toBeChecked();
  await expect(retained.getByRole("button", {name: "Apply retained-body edits"})).toBeEnabled();
  await retained.getByRole("button", {name: "Apply retained-body edits"}).click();
  expect(JSON.parse((await editor.getAttribute("data-edit"))!)).toMatchObject({
    edit: {revision: 7}, parameters: {gradient: true},
  });
  expect(await editor.evaluate(el => (el as GoveeMusicProfileEditor).content)).toEqual(before);
  // Successful API completion clears intent even if the returned revision is unchanged.
  await editor.evaluate(el => (el as GoveeMusicProfileEditor).clearRetainedEdits());
  await expect(retained.getByRole("button", {name: "Apply retained-body edits"})).toBeDisabled();

  for (const change of ["revision", "mode", "device", "content-mode"]) {
    await retained.getByRole("checkbox", {name: "Gradient"}).check();
    await editor.evaluate(async (el, change) => {
      const editor = el as GoveeMusicProfileEditor;
      if (change === "revision") editor.retainedEdit = {...editor.retainedEdit!, revision: 8};
      if (change === "mode") {
        editor.retainedEdit = {...editor.retainedEdit!, mode: "piano_keys"};
        editor.content = {...editor.content!, mode: "piano_keys"};
      }
      if (change === "device") editor.configEntryId = "device-b";
      if (change === "content-mode") {
        const previous = editor.content!;
        editor.content = {...previous, mode: "hopping"};
        await editor.updateComplete;
        editor.content = previous;
      }
      await editor.updateComplete;
    }, change);
    await expect(retained.getByRole("checkbox", {name: "Gradient"})).not.toBeChecked();
    await expect(retained.getByRole("button", {name: "Apply retained-body edits"})).toBeDisabled();
  }
});
