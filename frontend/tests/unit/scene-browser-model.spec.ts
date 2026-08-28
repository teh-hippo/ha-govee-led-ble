import { expect, test } from "vitest";

import {
  buildScenePreviewRequest,
  cloneSceneContent,
  initialSceneBrowserState,
  nativeSceneActions,
  normaliseSceneName,
  previewMayChangeSceneDefault,
  sceneBrowserCategories,
  sceneBrowserEntries,
  sceneHasParameterSurface,
  sceneKey,
  sceneSpeedOptions,
  sameSceneDeviceIdentity,
  visibleCategoryForBuiltin,
  visibleCategoryForCustom,
} from "../../src/scene-browser-model";
import type {
  LibrarySummary,
  PaletteSceneContent,
  SceneCatalogue,
  SceneSummary,
} from "../../src/types";

const scene: SceneSummary = {
  scene_id: 1,
  effect_id: 2,
  category_id: 3,
  category: "Natural",
  name: "Glacier",
  variant: "",
  display_name: "Glacier",
  scene_type: 2,
  parameter_kind: "layers",
  speed: { option_count: 3, default_index: 2 },
};

test("scene identity and names use stable normalisation", () => {
  expect(sceneKey(scene)).toBe("builtin:1:2");
  expect(normaliseSceneName("  Glacier   Blue ")).toBe("glacier blue");
});

test("scene device identity ignores pushed state object replacement", () => {
  const device = {
    config_entry_id: "entry-a",
    model: "H617A",
  } as const;

  expect(
    sameSceneDeviceIdentity(device, {
      ...device,
    }),
  ).toBe(true);
  expect(
    sameSceneDeviceIdentity(device, {
      ...device,
      config_entry_id: "entry-b",
    }),
  ).toBe(false);
});

test("speed glyphs retain clear accessible labels", () => {
  expect(sceneSpeedOptions(3, 2)).toEqual([
    { value: 0, label: "▸", ariaLabel: "Slow" },
    { value: 1, label: "▸▸", ariaLabel: "Medium" },
    {
      value: 2,
      label: "▸▸▸",
      ariaLabel: "Fast, catalogue default",
    },
  ]);
  expect(sceneSpeedOptions(4, 0)[0].ariaLabel).toBe(
    "Slowest, catalogue default",
  );
});

test("native default actions use the shared Save, Reset, and Save As model", () => {
  expect(nativeSceneActions(true, true, false)).toEqual([
    { id: "save-as", label: "Save As", style: "secondary" },
    { id: "reset-default", label: "Reset", style: "secondary" },
    { id: "edit", label: "Edit", style: "secondary" },
    { id: "save-default", label: "Save", style: "primary" },
  ]);
  expect(nativeSceneActions(true, true, true).map((action) => action.label)).toEqual([
    "Save As",
    "Reset",
    "Edit",
  ]);
  expect(nativeSceneActions(true, true, false, false, true, true)).toEqual([
    { id: "save-as", label: "Save As", style: "secondary" },
    {
      id: "reset-default",
      label: "Reset",
      style: "secondary",
      disabled: true,
    },
    { id: "edit", label: "Edit", style: "secondary" },
  ]);
  expect(nativeSceneActions(true, true, false).some((action) => action.label.includes("Saving"))).toBe(false);
});

test("palette inspection data does not create a parameter surface", () => {
  const paletteScene: SceneSummary = {
    ...scene,
    scene_type: 1,
    parameter_kind: "palette",
    speed: null,
  };

  expect(sceneHasParameterSurface(paletteScene)).toBe(false);
  expect(sceneHasParameterSurface({ ...paletteScene, speed: scene.speed })).toBe(true);
});

test("settled scene preview statuses trigger an authoritative default refresh", () => {
  const status = {
    session_id: "session-a",
    sequence: 1,
    config_entry_id: "entry-a",
    phase: "written" as const,
    content_kind: "scene_layered",
    confidence: "write_completed" as const,
    error_code: null,
    error_message: null,
    write_disposition: "completed" as const,
    persist_default: true,
    scene_id: 1,
    effect_id: 2,
    default_action: "set" as const,
  };

  expect(previewMayChangeSceneDefault(status, "entry-a")).toBe(false);
  expect(
    previewMayChangeSceneDefault(
      {
        ...status,
        phase: "failed",
        error_code: "transport_failed",
        write_disposition: "may_have_started",
      },
      "entry-a",
    ),
  ).toBe(true);
  expect(previewMayChangeSceneDefault(status, "entry-b")).toBe(false);
});

test("scene content clones do not share editable colour arrays", () => {
  const content: PaletteSceneContent = {
    kind: "scene_palette",
    template: {
      sku: "H617A",
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
    layout: 0,
    brightness_flag: true,
    steps: [{ value: 1, colour: [1, 2, 3], inline_colour: null }],
    palette: [[4, 5, 6]],
    speed_index: null,
  };
  const clone = cloneSceneContent(content);
  if (clone.kind !== "scene_palette") {
    throw new Error("palette scene clone changed kind");
  }

  clone.steps[0].colour[0] = 255;
  clone.palette[0][0] = 255;

  expect(content.steps[0].colour).toEqual([1, 2, 3]);
  expect(content.palette[0]).toEqual([4, 5, 6]);
});

test("scene categories and entries are derived without DOM state", () => {
  const catalogue: SceneCatalogue = {
    schema_version: 1,
    sku: "H617A",
    enabled: true,
    categories: [{ id: 3, name: "Natural" }],
    scenes: [scene],
  };
  const custom: LibrarySummary = {
    id: "custom-a",
    version: 1,
    updated_at: "2026-08-18T00:00:00Z",
    name: "Aurora custom",
    kind: "scene_palette",
    content_hash: "a".repeat(64),
    origin: { kind: "authored", source_id: null },
    template: {
      sku: "H617A",
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
  };
  const state = { ...initialSceneBrowserState(), catalogue };

  expect(sceneBrowserCategories(catalogue, [custom]).map((category) => category.label)).toEqual([
    "All",
    "My Effects",
    "Natural",
  ]);
  expect(sceneBrowserEntries(state, [custom]).map((entry) => entry.label)).toEqual([
    "Aurora custom",
    "Glacier",
  ]);
});

test("restored selections move only to categories that contain them", () => {
  expect(visibleCategoryForBuiltin("all", scene)).toBe("all");
  expect(visibleCategoryForBuiltin(scene.category_id, scene)).toBe(scene.category_id);
  expect(visibleCategoryForBuiltin(9, scene)).toBe(scene.category_id);
  expect(visibleCategoryForCustom("all")).toBe("all");
  expect(visibleCategoryForCustom("custom")).toBe("custom");
  expect(visibleCategoryForCustom(scene.category_id)).toBe("custom");
});

test("preview requests use the current selection identity and editable speed", () => {
  const content: PaletteSceneContent = {
    kind: "scene_palette",
    template: {
      sku: "H617A",
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
    layout: 0,
    brightness_flag: false,
    steps: [],
    palette: [],
    speed_index: null,
  };
  const state = {
    ...initialSceneBrowserState(),
    catalogue: {
      schema_version: 1,
      sku: "H617A",
      enabled: true,
      categories: [],
      scenes: [scene],
    },
    selectedScene: scene,
    content,
    name: "Editable",
    speedIndex: 1,
    editingCopy: true,
  };

  expect(buildScenePreviewRequest(state, sceneKey(scene), true, true)).toEqual({
    kind: "snapshot",
    name: "Editable",
    content: { ...content, speed_index: 1 },
  });
  expect(buildScenePreviewRequest(state, "builtin:other", true, true)).toBeUndefined();
  expect(
    buildScenePreviewRequest(
      {
        ...state,
        catalogue: { ...state.catalogue, enabled: false },
        editingCopy: false,
      },
      sceneKey(scene),
      true,
      true,
    ),
  ).toEqual({
    kind: "snapshot",
    name: "Editable",
    content: { ...content, speed_index: 1 },
  });
});
