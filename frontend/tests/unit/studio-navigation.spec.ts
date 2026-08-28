import { expect, test } from "vitest";

import {
  activeStudioContext,
  deviceIdFromEditorPath,
  editorDevicePath,
  initialDeviceId,
  rememberedStudioSection,
  studioNavigationItems,
} from "../../src/studio-navigation";
import type {
  DeviceCapabilities,
  LibrarySummary,
  ModelEffectCatalogue,
} from "../../src/types";

const device = (
  id: string,
  painted: "supported" | "unsupported",
): DeviceCapabilities => ({
  config_entry_id: id,
  light_entity_id: `light.${id}`,
  model: "H617A",
  display_name: id,
  segment_count: 15,
  custom_effects: {
    painted,
    single: "supported",
    multi: "supported",
    palette_diy: "unsupported",
    advanced: "supported",
    workshop: "supported",
  },
  profiles: {
    music: "supported",
    video: "unsupported",
  },
  readback: "state",
  preview_health: {
    config_entry_id: id,
    revision: 0,
    phase: "healthy",
    incident_id: null,
    error_code: null,
    error_message: null,
    write_disposition: "not_started",
    checked_at: "2026-08-24T00:00:00Z",
  },
  effect_categories: [
    "scenes",
    "effects",
    "multi_layered",
    "reactive",
    "advanced",
  ],
  active_state: null,
});

const catalogue: ModelEffectCatalogue = {
  sku: "H617A",
  painted_effects: [],
  effects: [],
  music_modes: [{ id: "separation", label: "Separation" }],
  video_modes: [{ id: "movie", label: "Movie" }],
  workshop_templates: [],
  workflows: [],
  supports: {
    multi: "unsupported",
    advanced: "unsupported",
    workshop: "unsupported",
  },
  limits: {
    palette_min: 1,
    palette_max: 8,
    multi_max: 5,
    music_sensitivity_min: 0,
    music_sensitivity_max: 100,
  },
  apply: {
    painted: "supported",
    single: "supported",
    multi: "supported",
    palette_diy: "unsupported",
    workshop: "unsupported",
  },
};

test("remembered navigation restores only an available top-level section", () => {
  expect(
    rememberedStudioSection(
      { section: "video" },
      { scenes: true, custom: true, video: true },
    ),
  ).toBe("video");
  expect(
    rememberedStudioSection(
      { section: "video" },
      { scenes: true, custom: true, video: false },
    ),
  ).toBe("custom");
  expect(
    rememberedStudioSection(
      { section: "future" },
      { scenes: true, custom: false, video: false },
    ),
  ).toBe("scenes");
});

test("primary navigation flattens custom categories", () => {
  const categories = [
    { category: "single-layer" as const, label: "Effects" },
    { category: "multi-layer" as const, label: "Multi-Layered" },
  ];
  expect(studioNavigationItems(true, true, categories)).toEqual([
    { section: "video", label: "Video" },
    { section: "scenes", label: "Scenes" },
    { section: "custom", category: "single-layer", label: "Effects" },
    {
      section: "custom",
      category: "multi-layer",
      label: "Multi-Layered",
    },
  ]);
  expect(studioNavigationItems(true, false, categories).map((item) => item.label)).toEqual([
    "Scenes",
    "Effects",
    "Multi-Layered",
  ]);
});

test("active context requires exact available saved identity", () => {
  const saved: LibrarySummary = {
    id: "effect-a",
    version: 1,
    updated_at: "2026-08-17T00:00:00Z",
    name: "Saved",
    kind: "h617a_single",
    content_hash: "a".repeat(64),
    origin: { kind: "authored", source_id: null },
  };
  const active = device("entry-a", "supported");
  active.active_state = {
    config_entry_id: active.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-17T00:00:00Z",
    confidence: "activation_match",
    diy_code: 800,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-a",
    active_effect: {
      source_kind: "saved_effect",
      selector_label: saved.name,
      content_hash: saved.content_hash,
      origin: saved.origin,
      observable_signature: "custom:800",
      confidence: "activation_match",
      item_id: saved.id,
      item_version: saved.version,
    },
  };

  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "saved",
    item: saved,
  });

  active.active_state!.active_effect!.item_version = saved.version + 1;
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "root",
  });
  active.active_state!.active_effect!.item_version = saved.version;
  active.active_state!.active_effect!.content_hash = "b".repeat(64);
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "root",
  });
  active.active_state!.active_effect!.content_hash = saved.content_hash;
  active.active_state!.active_effect!.confidence = "unknown";
  active.active_state!.confidence = "unknown";
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "saved",
    item: saved,
  });
  active.active_state!.diy_code = 801;
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "root",
  });
  active.active_state!.diy_code = 800;
  active.active_state!.active_effect!.confidence = "activation_match";
  active.active_state!.confidence = "activation_match";
  expect(activeStudioContext(active, [saved], () => false, catalogue)).toEqual({
    kind: "root",
  });
  active.active_state!.active_effect = {
    ...active.active_state!.active_effect!,
    source_kind: "snapshot",
    item_id: null,
    item_version: null,
  };
  active.active_state!.mode = "scene";
  active.active_state!.effect = "rainbow";
  active.active_state!.native_mode = "rainbow";
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "root",
  });
});

test("canonical active workspace defensively precedes an exact saved hint", () => {
  const saved: LibrarySummary = {
    id: "effect-a",
    version: 1,
    updated_at: "2026-08-17T00:00:00Z",
    name: "Saved",
    kind: "h617a_single",
    content_hash: "a".repeat(64),
    origin: { kind: "authored", source_id: null },
  };
  const active = device("entry-a", "supported");
  const workspaceContent = {
    kind: "h617a_single" as const,
    family: 1,
    variant: 0,
    speed: 73,
    palette: [[1, 2, 3]] as [[number, number, number]],
  };
  active.active_state = {
    config_entry_id: active.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-17T00:00:00Z",
    confidence: "activation_match",
    diy_code: 800,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-a",
    active_effect: {
      source_kind: "saved_effect",
      selector_label: saved.name,
      content_hash: saved.content_hash,
      origin: saved.origin,
      observable_signature: "custom:800",
      confidence: "activation_match",
      item_id: saved.id,
      item_version: saved.version,
    },
  };
  active.active_workspace = {
    config_entry_id: active.config_entry_id,
    model: active.model,
    selector_label: "Flow",
    content: workspaceContent,
    content_hash: "b".repeat(64),
    origin: {
      kind: "catalogue_template",
      source_id: "template:single:1:0",
    },
    observable_signature: "custom:800",
    updated_at: "2026-08-17T00:00:00Z",
    generation: 1,
    confidence: "write_completed",
  };

  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "workspace",
    section: "custom",
    category: "single-layer",
    content: workspaceContent,
    origin: active.active_workspace.origin,
    label: "Flow",
  });

  active.active_state.active_effect!.item_version = saved.version + 1;
  expect(activeStudioContext(active, [saved], () => true, catalogue)).toEqual({
    kind: "workspace",
    section: "custom",
    category: "single-layer",
    content: workspaceContent,
    origin: active.active_workspace.origin,
    label: "Flow",
  });
});

test("fresh native identities are catalogue validated without confidence gating", () => {
  const active = device("entry-a", "supported");
  active.active_state = {
    config_entry_id: active.config_entry_id,
    mode: "scene",
    observed_at: "2026-08-17T00:00:00Z",
    confidence: "unknown",
    diy_code: null,
    effect: "rainbow",
    native_mode: "rainbow",
    matched_operation_id: null,
    active_effect: null,
  };
  expect(activeStudioContext(active, [], () => true, catalogue)).toEqual({
    kind: "native-scene",
    effect: "rainbow",
  });
  active.active_state.mode = "video";
  active.active_state.effect = null;
  active.active_state.native_mode = "movie";
  expect(activeStudioContext(active, [], () => true, catalogue)).toEqual({
    kind: "native-profile",
    section: "video",
    mode: "movie",
    label: "Movie",
  });
  active.active_state.mode = "music";
  active.active_state.native_mode = "separation";
  expect(activeStudioContext(active, [], () => true, catalogue)).toEqual({
    kind: "native-profile",
    section: "custom",
    category: "music",
    mode: "separation",
    label: "Separation",
  });
  active.active_state.native_mode = "shared-diy-code";
  expect(activeStudioContext(active, [], () => true, catalogue)).toEqual({
    kind: "root",
  });
});

test("device selection gives exact deep links precedence over remembered state", () => {
  const devices = [device("first", "unsupported"), device("painted", "supported")];

  expect(
    deviceIdFromEditorPath("/ha-govee-led-ble/editor/device%20a"),
  ).toBe("device a");
  expect(
    deviceIdFromEditorPath("/prefix/ha-govee-led-ble/editor/device"),
  ).toBeUndefined();
  expect(
    deviceIdFromEditorPath("/ha-govee-led-ble/editor/%E0%A4%A"),
  ).toBeUndefined();
  expect(editorDevicePath("device a")).toBe(
    "/ha-govee-led-ble/editor/device%20a",
  );
  expect(
    initialDeviceId(
      "/ha-govee-led-ble/editor/linked",
      devices,
      "painted",
    ),
  ).toBe("linked");
  expect(
    initialDeviceId("/ha-govee-led-ble", devices, "painted"),
  ).toBe("painted");
  expect(
    initialDeviceId("/ha-govee-led-ble", devices, "missing"),
  ).toBe("first");
});
