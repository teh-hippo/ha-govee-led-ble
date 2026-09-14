import { expect, test } from "@playwright/test";

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
