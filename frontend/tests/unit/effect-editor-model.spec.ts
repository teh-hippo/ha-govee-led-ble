import { expect, test } from "vitest";

import {
  EDITOR_EXTENSION_KEY,
  blankCustomEffect,
  blankPaintedSegments,
  cloneEditableEffect,
  customEffectCategoryForKind,
  effectOriginDescription,
  installLibraryItemEditorMetadata,
  isEditableEffectContent,
  libraryItemSyncResult,
  libraryKindPriority,
  mergedPaintBrushes,
  PAINTED_SEGMENT_COUNT,
  reactiveParameterValueText,
  serialiseEditable,
  uniquePaintedPalette,
  upsertSummary,
} from "../../src/effect-editor-model";
import {
  advancedLayerLabels,
  blankAdvancedContent,
  blankLayer,
  installAdvancedLayerLabels,
} from "../../src/advanced-effect-model";
import type {
  LibraryItem,
  ModelEffectCatalogue,
  PaintedContent,
} from "../../src/types";

const catalogue = {
  sku: "H617A",
  painted_effects: [],
  effects: [
    {
      id: "steady",
      label: "Steady",
      family: 1,
      variations: [{ id: "base", label: "Base", variant: 2 }],
      supports_multi: true,
      rate: "speed",
      category: "single_layer",
    },
    {
      id: "flow",
      label: "Flow",
      family: 9,
      variations: [
        { id: "counterclockwise", label: "Counterclockwise", variant: 8 },
        { id: "clockwise", label: "Clockwise", variant: 9 },
      ],
      supports_multi: true,
      rate: "speed",
      category: "single_layer",
    },
  ],
  music_modes: [],
  video_modes: [],
  workshop_templates: [],
  workflows: [],
  supports: {
    multi: "supported",
    advanced: "supported",
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
} satisfies ModelEffectCatalogue;

test("custom defaults use catalogue identities without sharing palettes", () => {
  const first = blankCustomEffect("h617a_single", catalogue);
  const second = blankCustomEffect("h617a_single", catalogue);

  first.palette[0][0] = 0;

  expect(first.family).toBe(1);
  expect(first.variant).toBe(2);
  expect(second.palette[0]).toEqual([255, 0, 0]);
});

test("multi defaults select Flow and Clockwise by catalogue identity", () => {
  expect(blankCustomEffect("h617a_multi", catalogue).effects).toEqual([
    { family: 9, variant: 9 },
  ]);
});

test("multi defaults retain a compatible fallback without Flow", () => {
  const fallbackCatalogue = {
    ...catalogue,
    effects: catalogue.effects.filter((effect) => effect.id !== "flow"),
  };

  expect(blankCustomEffect("h617a_multi", fallbackCatalogue).effects).toEqual([
    { family: 1, variant: 2 },
  ]);
});

test("painted content keeps Off separate from RGB black", () => {
  const content: PaintedContent = {
    kind: "h617a_painted",
    effect: "clockwise",
    speed: 50,
    brightness: 100,
    segments: [
      null,
      [255, 0, 0],
      [0, 0, 0],
      [0, 0, 255],
      ...Array.from({ length: 11 }, () => null),
    ],
  };

  expect(content.segments).toHaveLength(PAINTED_SEGMENT_COUNT);
  expect(content.segments[0]).toBeNull();
  expect(content.segments[2]).toEqual([0, 0, 0]);
  expect(uniquePaintedPalette(content)).toEqual([
    [255, 0, 0],
    [0, 0, 0],
    [0, 0, 255],
  ]);
});

test("paint draft defaults every segment to explicit off", () => {
  expect(blankPaintedSegments()).toEqual(
    Array.from({ length: PAINTED_SEGMENT_COUNT }, () => null),
  );
});

test("paint brushes remove duplicates and retain the eight-colour limit", () => {
  const brushes = mergedPaintBrushes([
    [255, 0, 0],
    [255, 0, 0],
    [1, 2, 3],
  ]);

  expect(brushes[0]).toEqual([255, 0, 0]);
  expect(brushes[1]).toEqual([1, 2, 3]);
  expect(brushes).toHaveLength(8);
});

test("editable clones and serialisation isolate nested state", () => {
  const source = {
    kind: "music_profile" as const,
    model: "H617A" as const,
    mode: "rhythm",
    sensitivity: 50,
    colour: [1, 2, 3] as [number, number, number],
    calm: null,
    parameters: { speed: 4 },
  };
  const cloned = cloneEditableEffect(source);

  if (cloned.kind !== "music_profile" || cloned.colour === null) {
    throw new Error("Expected a music profile clone.");
  }
  cloned.colour[0] = 9;
  cloned.parameters.speed = 8;

  expect(source.colour).toEqual([1, 2, 3]);
  expect(source.parameters).toEqual({ speed: 4 });
  expect(serialiseEditable("  Name  ", source)).toContain('"name":"Name"');
});

test("advanced layer labels survive clones, serialisation, and saved metadata", () => {
  const content = blankAdvancedContent();
  content.layers.push(blankLayer());
  installAdvancedLayerLabels(content, [3, 1]);

  const cloned = cloneEditableEffect(content);
  expect(cloned.kind).toBe("advanced");
  if (cloned.kind !== "advanced") {
    throw new Error("Expected advanced content.");
  }
  expect(advancedLayerLabels(cloned)).toEqual([3, 1]);
  expect(serialiseEditable("Layered", cloned)).toContain(
    '"layer_labels":[3,1]',
  );

  const item: LibraryItem = {
    schema_version: 1,
    id: "advanced",
    version: 1,
    updated_at: "2026-08-27T00:00:00Z",
    name: "Layered",
    content: blankAdvancedContent(),
    content_hash: "3".repeat(64),
    origin: { kind: "authored", source_id: null },
    extensions: {
      [EDITOR_EXTENSION_KEY]: { layer_labels: [7] },
    },
  };
  installLibraryItemEditorMetadata(item);
  expect(advancedLayerLabels(item.content as ReturnType<typeof blankAdvancedContent>)).toEqual([7]);
});

test("library summaries retain model metadata and stable ordering", () => {
  const item: LibraryItem = {
    schema_version: 1,
    id: "second",
    version: 2,
    updated_at: "2026-08-17T00:00:00Z",
    name: "Alpha",
    content: blankCustomEffect("h617a_single", catalogue),
    content_hash: "0".repeat(64),
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
  const summaries = upsertSummary(
    [
      {
        id: "first",
        version: 1,
        updated_at: "2026-08-17T00:00:00Z",
        name: "Zulu",
        kind: "h617a_single",
        content_hash: "1".repeat(64),
        origin: { kind: "authored", source_id: null },
        model: "H617A",
      },
    ],
    item,
  );

  expect(summaries.map((summary) => summary.name)).toEqual(["Alpha", "Zulu"]);
  expect(summaries[0].model).toBe("H617A");
  expect(isEditableEffectContent(item.content)).toBe(true);
  expect(customEffectCategoryForKind(item.content.kind)).toBe("single-layer");
  expect(libraryKindPriority("palette_diy", "H6199")).toBeLessThan(
    libraryKindPriority("advanced", "H6199"),
  );
});

test("library updates distinguish removal, conflicts, and safe reloads", () => {
  const current = { id: "effect-a", version: 1 };
  const updated = {
    id: "effect-a",
    version: 2,
    updated_at: "2026-08-17T00:01:00Z",
    name: "Updated",
    kind: "h617a_single",
    content_hash: "2".repeat(64),
    origin: { kind: "authored", source_id: null },
  };

  expect(libraryItemSyncResult(current, [], false)).toEqual({
    action: "removed",
  });
  expect(libraryItemSyncResult(current, [], false, current.id)).toEqual({
    action: "none",
  });
  expect(libraryItemSyncResult(current, [updated], true)).toEqual({
    action: "conflict",
    summary: updated,
  });
  expect(libraryItemSyncResult(current, [updated], false)).toEqual({
    action: "reload",
    summary: updated,
  });
});

test("effect origins retain both provenance and source names", () => {
  expect(
    effectOriginDescription(
      { kind: "authored", source_id: null },
      "Steady: Base",
    ),
  ).toBe("Based on Steady: Base");
  expect(
    effectOriginDescription(
      { kind: "imported", source_id: "backup" },
    ),
  ).toBe("Imported from backup");
});

test("Reactive numeric labels expose only Point, Key count, and Segment count", () => {
  expect(reactiveParameterValueText("point", 3)).toBe("3");
  expect(reactiveParameterValueText("key_count", 12)).toBe("12");
  expect(reactiveParameterValueText("segment_count", 6)).toBe("6");
  expect(reactiveParameterValueText("sensitivity", 80)).toBeUndefined();
  expect(reactiveParameterValueText("speed", 20)).toBeUndefined();
  expect(
    reactiveParameterValueText("relative_brightness", 40),
  ).toBeUndefined();
});
