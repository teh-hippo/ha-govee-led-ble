import { expect, test } from "@playwright/test";

test("video editor shows only declared model settings", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html");

  await expect(page.getByLabel("Saturation", {exact: true})).toBeVisible();
  await expect(page.getByLabel("Saturation", {exact: true})).toHaveAttribute("min", "0");
  await expect(page.getByLabel("Capture area")).toBeHidden();
  await expect(page.getByLabel("Uniform brightness")).toBeHidden();
  await expect(page.getByText("Sound effects")).toHaveCount(0);
  await expect(page.getByText("Blank screen")).toHaveCount(0);
  await expect(page.getByText("White balance")).toHaveCount(0);
});

test("scalar calibration and six ordered brightness zones stay editable", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html?alternate");
  const balance = page.getByLabel("White balance", {exact: true});
  await expect(balance).toHaveAttribute("min", "0");
  await expect(balance).toHaveAttribute("max", "2");
  await balance.fill("2");
  await expect(balance).toHaveValue("2");
  await expect(page.getByLabel("Strip left", {exact: true})).toBeVisible();
  await expect(page.getByLabel("Strip right", {exact: true})).toBeVisible();
  await page.getByLabel("Strip right", {exact: true}).fill("75");
  await expect(page.getByLabel("Strip right", {exact: true})).toHaveValue("75");
  await page.getByLabel("Uniform brightness", {exact: true}).fill("80");
  await expect(page.getByLabel("Strip left", {exact: true})).toHaveValue("80");
  await expect(page.getByLabel("Strip right", {exact: true})).toHaveValue("80");
});

test("firmware evidence gaps are explicit without stripping profile values", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html?alternate&gated");
  await expect(page.getByText(/firmware identity unavailable/)).toBeVisible();
  await expect(page.getByLabel("White balance", {exact: true})).toHaveValue("1");
  await expect(page.getByLabel("Strip right", {exact: true})).toHaveValue("60");
  await page.getByLabel("Include white balance", {exact: true}).uncheck();
  await expect(page.getByLabel("White balance", {exact: true})).toHaveCount(0);
  await expect(page.getByLabel("Strip right", {exact: true})).toHaveValue("60");
});

test("H6099 border is optional and blank-screen policy editing is explicit", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html?h6099");
  await expect(page.getByLabel("Include black border", {exact: true})).not.toBeChecked();
  await expect(page.getByLabel("Saturation", {exact: true})).toBeEnabled();
  await expect(page.getByLabel("Saturation", {exact: true})).toHaveAttribute("min", "1");
  await expect(page.getByLabel("Saturation", {exact: true})).toHaveAttribute("max", "100");
  await page.getByLabel("Include black border", {exact: true}).check();
  await page.getByLabel("Black-border removal", {exact: true}).check();
  await page.getByLabel("Include black border", {exact: true}).uncheck();
  await expect(page.getByLabel("Black-border removal", {exact: true})).toHaveCount(0);
  await expect(page.getByLabel("Blank-screen detection", {exact: true})).toHaveCount(0);
  await page.getByLabel("Edit blank-screen policy", {exact: true}).check();
  await page.getByLabel("Blank-screen detection", {exact: true}).selectOption("1");
  await page.getByLabel("Low-brightness seconds", {exact: true}).fill("300");
  await page.getByLabel("Low-brightness seconds", {exact: true}).blur();
  await page.getByLabel("Same-tone seconds", {exact: true}).fill("600");
  await page.getByLabel("Same-tone seconds", {exact: true}).blur();
  await page.getByLabel("Blank screen", {exact: true}).check();
  await page.getByLabel("Blank screen", {exact: true}).uncheck();
  await expect(page.getByLabel("Blank-screen detection", {exact: true})).toHaveValue("1");
  await expect(page.getByLabel("Low-brightness seconds", {exact: true})).toHaveValue("300");
  await expect(page.getByLabel("Same-tone seconds", {exact: true})).toHaveValue("600");
  await page.getByLabel("Edit blank-screen policy", {exact: true}).uncheck();
  await expect(page.getByLabel("Blank-screen detection", {exact: true})).toHaveCount(0);
});
