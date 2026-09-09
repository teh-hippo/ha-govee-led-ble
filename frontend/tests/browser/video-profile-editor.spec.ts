import { expect, test } from "@playwright/test";

test("video editor shows only declared model settings", async ({ page }) => {
  await page.goto("/tests/browser/fixtures/video-profile-editor.html");

  await expect(page.getByLabel("Saturation")).toBeVisible();
  await expect(page.getByLabel("Capture area")).toBeHidden();
  await expect(page.getByLabel("Uniform brightness")).toBeHidden();
  await expect(page.getByText("Sound effects")).toHaveCount(0);
  await expect(page.getByText("Blank screen")).toHaveCount(0);
  await expect(page.getByText("White balance")).toHaveCount(0);
});
