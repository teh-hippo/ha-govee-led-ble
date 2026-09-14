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
