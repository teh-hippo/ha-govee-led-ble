import { resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  outputDir: resolve(import.meta.dirname, "../.build/playwright"),
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "mobile-webkit",
      use: {
        ...devices["iPhone 15"],
        browserName: "webkit",
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173/tests/browser/fixtures/palette-editor.html",
    reuseExistingServer: !process.env.CI,
  },
});
