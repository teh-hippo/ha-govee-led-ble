import { resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  outputDir: resolve(import.meta.dirname, "../.build/playwright"),
  reporter: "line",
  use: {
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
    command: "npm run dev -- --host 127.0.0.1 --port 0",
    env: { FORCE_COLOR: "0" },
    wait: {
      stdout: /Local:.*http:\/\/127\.0\.0\.1:(?<govee_server_port>[1-9]\d*)\//,
    },
  },
});
