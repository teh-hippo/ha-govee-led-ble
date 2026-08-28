import { isKnownSelectionType } from "./advanced-effect-model";
import type { AdvancedHelpKey } from "./advanced-help";
import type { ReorderableStripItem } from "./reorderable-strip-model";
import type { SelectionType } from "./types";

export const AUTHORING_LAYER_LIMIT = 5;
export const AUTHORING_PALETTE_LIMIT = 8;
export const DEFAULT_SEGMENT_COUNT = 15;

export const FILL_PATTERN_LABELS: Record<SelectionType, string> = {
  0: "Segment",
  1: "Continuous",
  2: "Random",
  3: "Custom",
};

export type FillPatternParameterKey = "param_1" | "param_2";
export type FillPatternParameter = readonly [
  FillPatternParameterKey,
  string,
  AdvancedHelpKey?,
];

export const FILL_PATTERN_PARAMETERS: Record<
  SelectionType,
  readonly FillPatternParameter[]
> = {
  0: [["param_2", "Segment Count", "segmentCount"]],
  1: [["param_2", "LED Count"]],
  2: [
    ["param_2", "Minimum LED Count"],
    ["param_1", "Maximum LED Count"],
  ],
  3: [
    ["param_1", "Lit Length"],
    ["param_2", "Gap"],
  ],
};

export const DISTRIBUTION_COLOUR_FIELDS = [
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
] as const satisfies ReadonlyArray<{
  key: "colour_retention" | "colour_speed";
  label: string;
  help: AdvancedHelpKey;
}>;

export type AdvancedLayerActionKind = "copy" | "renumber" | "delete";

export interface AdvancedLayerAction {
  kind: AdvancedLayerActionKind;
  label: string;
  icon?: string;
  glyph?: string;
  danger: boolean;
  disabled: boolean;
  visible: boolean;
}

export function fillPatternParameters(
  type: number,
): readonly FillPatternParameter[] {
  return isKnownSelectionType(type)
    ? FILL_PATTERN_PARAMETERS[type]
    : [];
}

export function advancedLayerItems(
  layerLabels: readonly number[],
): ReorderableStripItem[] {
  return numberedStripItems(
    layerLabels,
    "layer",
    "Layer",
    "advanced-layer-tab",
    "advanced-layer-panel",
    "Drag to reorder or use the Left and Right Arrow keys.",
  );
}

export function advancedBrightnessPatternItems(
  patternCount: number,
): ReorderableStripItem[] {
  return numberedStripItems(
    Array.from({ length: patternCount }, (_item, index) => index + 1),
    "pattern",
    "Pattern",
    "advanced-pattern-tab",
    "advanced-pattern-panel",
  );
}

export function advancedLayerActions(
  layerCount: number,
  disabled = false,
): AdvancedLayerAction[] {
  return [
    {
      kind: "copy",
      label: "Copy current layer",
      icon: "mdi:content-copy",
      danger: false,
      disabled: disabled || layerCount >= AUTHORING_LAYER_LIMIT,
      visible: true,
    },
    {
      kind: "renumber",
      label: "Renumber layers",
      icon: "mdi:format-list-numbered",
      danger: false,
      disabled,
      visible: layerCount > 1,
    },
    {
      kind: "delete",
      label: "Delete current layer",
      glyph: "×",
      danger: true,
      disabled,
      visible: layerCount > 1,
    },
  ];
}

function numberedStripItems(
  labels: readonly number[],
  keyPrefix: string,
  ariaPrefix: string,
  idPrefix: string,
  ariaControls: string,
  ariaDescription?: string,
): ReorderableStripItem[] {
  return labels.map((label, index) => ({
    key: `${keyPrefix}-${index}`,
    label: String(label),
    ariaLabel: `${ariaPrefix} ${label}`,
    ariaDescription,
    id: `${idPrefix}-${index}`,
    ariaControls,
  }));
}
