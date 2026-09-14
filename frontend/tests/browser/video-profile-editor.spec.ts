import { expect, test } from "@playwright/test";

test("video editor shows only declared model settings", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html");

  await expect(page.getByLabel("Saturation", {exact: true})).toBeVisible();
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
