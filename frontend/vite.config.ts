import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import {
  EDITOR_API_VERSION,
  EDITOR_ASSET_VERSION,
  EFFECT_COMPILER_VERSION,
  EFFECT_SCHEMA_VERSION,
} from "./src/contracts.ts";

const panelEntry = resolve(import.meta.dirname, "src/panel.ts");

function isStaticPanelDependency(
  id: string,
  getModuleInfo: (id: string) => { importers: readonly string[] } | null,
  visited = new Set<string>(),
): boolean {
  if (id === panelEntry) {
    return true;
  }
  if (visited.has(id)) {
    return false;
  }
  visited.add(id);
  return (
    getModuleInfo(id)?.importers.some((importer) =>
      isStaticPanelDependency(importer, getModuleInfo, visited),
    ) ?? false
  );
}

function editorManifest(): Plugin {
  return {
    name: "editor-manifest",
    generateBundle(_options, bundle) {
      const entry = Object.values(bundle).find(
        (asset) => asset.type === "chunk" && asset.isEntry,
      );
      if (
        !entry ||
        entry.type !== "chunk" ||
        entry.fileName !== "effect-studio-bootstrap.js"
      ) {
        throw new Error("Editor bootstrap entry was not generated");
      }
      const chunks = Object.values(bundle)
        .filter(
          (asset) =>
            asset.type === "chunk" &&
            !asset.isEntry &&
            asset.fileName.endsWith(".js"),
        )
        .map((asset) => asset.fileName)
        .sort();
      this.emitFile({
        type: "asset",
        fileName: "manifest.json",
        source: `${JSON.stringify({
          bootstrap: entry.fileName,
          chunks,
          asset_version: EDITOR_ASSET_VERSION,
          api_version: EDITOR_API_VERSION,
          effect_schema_version: EFFECT_SCHEMA_VERSION,
          compiler_version: EFFECT_COMPILER_VERSION,
        }, null, 2)}\n`,
      });
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [editorManifest()],
  build: {
    outDir: resolve(
      process.env.FRONTEND_OUT_DIR ??
        resolve(
          import.meta.dirname,
          "../custom_components/ha_govee_led_ble/frontend",
        ),
    ),
    emptyOutDir: false,
    target: "es2022",
    rollupOptions: {
      input: panelEntry,
      output: {
        entryFileNames: "effect-studio-bootstrap.js",
        chunkFileNames: "effect-studio-[name]-[hash].js",
        manualChunks(id, { getModuleInfo }) {
          if (
            id !== panelEntry &&
            isStaticPanelDependency(id, getModuleInfo)
          ) {
            return "core";
          }
        },
      },
    },
  },
});
