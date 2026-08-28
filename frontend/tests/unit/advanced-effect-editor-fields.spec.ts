import { expect, test } from "vitest";

import {
  advancedBrightnessPatternItems,
  advancedLayerActions,
  advancedLayerItems,
  DISTRIBUTION_COLOUR_FIELDS,
  FILL_PATTERN_LABELS,
  fillPatternParameters,
} from "../../src/advanced-effect-editor-model";

test("fill pattern labels retain the wire selection mappings", () => {
  expect(FILL_PATTERN_LABELS).toEqual({
    0: "Segment",
    1: "Continuous",
    2: "Random",
    3: "Custom",
  });
  expect(fillPatternParameters(0)).toEqual([
    ["param_2", "Segment Count", "segmentCount"],
  ]);
  expect(fillPatternParameters(1)).toEqual([
    ["param_2", "LED Count"],
  ]);
  expect(fillPatternParameters(2)).toEqual([
    ["param_2", "Minimum LED Count"],
    ["param_1", "Maximum LED Count"],
  ]);
  expect(fillPatternParameters(3)).toEqual([
    ["param_1", "Lit Length"],
    ["param_2", "Gap"],
  ]);
});

test("Distribution presents retention before speed with matching help", () => {
  expect(DISTRIBUTION_COLOUR_FIELDS).toEqual([
    {
      key: "colour_retention",
      label: "Colour Retention",
      help: "colourRetention",
    },
    {
      key: "colour_speed",
      label: "Colour Speed",
      help: "colourSpeed",
    },
  ]);
});

test("unknown fill pattern values remain unsupported rather than remapped", () => {
  expect(fillPatternParameters(255)).toEqual([]);
});

test("layer and brightness pattern items use numeric labels and exact accessible names", () => {
  expect(advancedLayerItems([3, 1])).toEqual([
    {
      key: "layer-0",
      label: "3",
      ariaLabel: "Layer 3",
      ariaDescription:
        "Drag to reorder or use the Left and Right Arrow keys.",
      id: "advanced-layer-tab-0",
      ariaControls: "advanced-layer-panel",
    },
    {
      key: "layer-1",
      label: "1",
      ariaLabel: "Layer 1",
      ariaDescription:
        "Drag to reorder or use the Left and Right Arrow keys.",
      id: "advanced-layer-tab-1",
      ariaControls: "advanced-layer-panel",
    },
  ]);
  expect(advancedBrightnessPatternItems(2)).toEqual([
    {
      key: "pattern-0",
      label: "1",
      ariaLabel: "Pattern 1",
      ariaDescription: undefined,
      id: "advanced-pattern-tab-0",
      ariaControls: "advanced-pattern-panel",
    },
    {
      key: "pattern-1",
      label: "2",
      ariaLabel: "Pattern 2",
      ariaDescription: undefined,
      id: "advanced-pattern-tab-1",
      ariaControls: "advanced-pattern-panel",
    },
  ]);
});

test("compact layer actions retain labels, tone, and authoring limits", () => {
  expect(advancedLayerActions(1)).toEqual([
    {
      kind: "copy",
      label: "Copy current layer",
      icon: "mdi:content-copy",
      danger: false,
      disabled: false,
      visible: true,
    },
    {
      kind: "renumber",
      label: "Renumber layers",
      icon: "mdi:format-list-numbered",
      danger: false,
      disabled: false,
      visible: false,
    },
    {
      kind: "delete",
      label: "Delete current layer",
      glyph: "×",
      danger: true,
      disabled: false,
      visible: false,
    },
  ]);
  expect(advancedLayerActions(5).map(({ kind, disabled, visible }) => ({
    kind,
    disabled,
    visible,
  }))).toEqual([
    { kind: "copy", disabled: true, visible: true },
    { kind: "renumber", disabled: false, visible: true },
    { kind: "delete", disabled: false, visible: true },
  ]);
});
