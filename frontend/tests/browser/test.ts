import { test as base } from "@playwright/test";

export { expect } from "@playwright/test";
export type { Locator, Page } from "@playwright/test";

export const test = base.extend({
  baseURL: async ({}, use) => {
    const port = process.env.GOVEE_SERVER_PORT;
    if (!port) throw new Error("The gate-owned Vite server did not report its port");
    await use(`http://127.0.0.1:${port}`);
  },
});
