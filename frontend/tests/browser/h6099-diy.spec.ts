import { expect, test } from "@playwright/test";
import type { GoveePaintedSegmentEditor } from "../../src/painted-segment-editor";
import type { GoveeCustomEffectEditor } from "../../src/custom-effect-editor";

for (const width of [390, 1280]) {
  test(`graffiti physical ICs remain accessible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/tests/browser/fixtures/palette-editor.html");
    const editor = page.getByTestId("painted-context").locator("govee-painted-segment-editor");
    await editor.evaluate((element) => {
      const painted = element as GoveePaintedSegmentEditor;
      painted.physical = true;
      painted.background = [255, 255, 255];
      painted.segments = Array.from({ length: 60 }, () => null);
    });
    await expect(editor.getByRole("button")).toHaveCount(60);
    const last = editor.getByRole("button", { name: "IC 60, background", exact: true });
    await expect(last).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await last.tap();
    await expect(page.getByTestId("painted-events")).toContainText('"index":59');
    const bounds = await editor.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
  });
}

test("DIY music omits the speed control and chase caps the palette", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/palette-editor.html");
  const editor = page.getByTestId("custom-context").locator("govee-custom-effect-editor");
  await editor.evaluate((element) => {
    const custom = element as GoveeCustomEffectEditor;
    custom.catalogue = {
      ...custom.catalogue!, sku: "H6099",
      effects: [{ ...custom.catalogue!.effects[0], family: 4, rate: "none", rate_min: 50, rate_max: 50 }],
    };
    custom.content = { kind: "h617a_single", family: 4, variant: 0, speed: 50, palette: [[255, 0, 0]] };
  });
  await expect(editor.locator("govee-slider-control")).toHaveCount(0);
  await editor.evaluate((element) => {
    const custom = element as GoveeCustomEffectEditor;
    custom.catalogue = { ...custom.catalogue!, effects: [{ ...custom.catalogue!.effects[0],
      family: 10, rate: "speed", rate_min: 1, rate_max: 100, palette_max: 3 }] };
    custom.content = { kind: "h617a_single", family: 10, variant: 0, speed: 50,
      palette: [[255, 0, 0], [0, 255, 0], [0, 0, 255]] };
  });
  await expect(editor.locator("govee-slider-control")).toHaveCount(1);
  await expect(editor.getByRole("button", { name: "Add colour" })).toHaveCount(0);
});
