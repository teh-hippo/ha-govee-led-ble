import { expect, test } from "@playwright/test";
import type { GoveeCustomEffectEditor } from "../../src/custom-effect-editor";

test("three-source DIY edits bottom temperatures without changing the side", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/h60b0-editor.html");
  const editor = page.locator("body > govee-custom-effect-editor");
  for (const name of ["Top", "Side", "Bottom"]) await expect(editor.getByRole("heading", { name, exact: true })).toBeVisible();
  const original = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  await editor.getByRole("checkbox", { name: "Use an independent top effect" }).check();
  const bottom = editor.locator("section.card").filter({ has: page.getByRole("heading", { name: "Bottom", exact: true }) });
  await bottom.getByRole("combobox", { name: "Effect", exact: true }).selectOption("template:h60b0:3:2:3");
  await bottom.getByRole("slider", { name: "Colour temperature 1", exact: true }).evaluate(element => {
    (element as HTMLInputElement).value = "4000";
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const changed = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!);
  expect(changed.layers[1]).toEqual(original.layers[1]);
  expect(changed.layers[2]).toMatchObject({ temperatures: [4000], kind: 3 });
});

test("combined ripple edits preserve RGBIC content and ripple header fields", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/h60b0-editor.html?template=template:h60b0:combined");
  const editor = page.locator("body > govee-custom-effect-editor");
  await expect(editor.locator("govee-advanced-effect-editor")).toBeVisible();
  const original = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!.combined!);
  await editor.getByRole("slider", { name: "Ripple movement speed", exact: true }).first().evaluate(element => {
    (element as HTMLInputElement).value = "12";
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const changed = await editor.evaluate(element => (element as GoveeCustomEffectEditor).nativeContent!.combined!);
  expect(changed.effect).toEqual(original.effect);
  expect(changed.ripple_layers![0]).toEqual({ ...original.ripple_layers![0], movement_speed: 12 });
});
