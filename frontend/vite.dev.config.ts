import { resolve } from "node:path";
import { defineConfig } from "vite";

const root = import.meta.dirname;
const allowedOrigin =
  process.env.HA_GOVEE_LED_BLE_VITE_ALLOWED_ORIGIN ??
  "http://127.0.0.1:8123";

export default defineConfig({
  root,
  server: {
    cors: {
      origin: allowedOrigin,
    },
    fs: {
      allow: [resolve(root)],
      strict: true,
    },
  },
});
