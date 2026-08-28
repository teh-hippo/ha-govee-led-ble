import type {
  AdvancedContent,
  BrightnessOrder,
  BrightnessPattern,
  EffectLayer,
  LayeredSceneContent,
  Movement,
  SelectionType,
} from "./types";
import { clampInteger, clonePalette } from "./ui-utils";

export const KNOWN_SELECTION_TYPES: readonly SelectionType[] = [1, 2, 0, 3];
export const KNOWN_BRIGHTNESS_ORDERS: readonly BrightnessOrder[] = [0, 1, 2, 3];
const APPLIED_AREA_SEGMENTS = Symbol("applied-area-segments");
const LAYER_LABEL = Symbol("layer-label");

interface EffectLayerWithAppliedAreaSegments extends EffectLayer {
  [APPLIED_AREA_SEGMENTS]?: {
    segmentCount: number;
    start: number;
    end: number;
  };
  [LAYER_LABEL]?: number;
}

export function blankAdvancedContent(): AdvancedContent {
  return {
    kind: "advanced",
    layers: [blankLayer()],
  };
}

export function cloneAdvancedContent(
  content: AdvancedContent,
): AdvancedContent {
  return {
    kind: "advanced",
    layers: content.layers.map(cloneLayer),
  };
}

export function cloneLayeredSceneContent(
  content: LayeredSceneContent,
): LayeredSceneContent {
  return {
    ...content,
    template: { ...content.template },
    effect: {
      layers: cloneAdvancedContent({
        kind: "advanced",
        layers: content.effect.layers,
      }).layers,
    },
  };
}

export function blankLayer(): EffectLayer {
  return {
    area: {
      start_tenths: 0,
      width_tenths: 10,
    },
    selection: {
      type: 0,
      param_1: 0,
      param_2: 1,
    },
    brightness_gradient: false,
    brightness_patterns: [blankBrightnessPattern()],
    distribution: {
      method: 1,
      backwards: false,
    },
    colour_speed: 128,
    colour_retention: 20,
    palette: [
      [255, 0, 0],
      [0, 0, 255],
    ],
    selected_movement: blankMovement(),
    overall_movement: blankMovement(),
    priority: 0,
    unknown_flags: 0,
    excess: "",
  };
}

export function blankBrightnessPattern(): BrightnessPattern {
  return {
    scope_high: 255,
    scope_low: 0,
    order: 0,
    change_speed: 128,
    brightest_retention: 20,
    darkest_retention: 20,
  };
}

function blankMovement(): Movement {
  return {
    enabled: false,
    enter_exit: false,
    direction: 0,
    distance: 1,
    speed: 128,
    unknown_flags: 0,
  };
}

export function cloneLayer(layer: EffectLayer): EffectLayer {
  const clone: EffectLayerWithAppliedAreaSegments = {
    ...layer,
    area: { ...layer.area },
    selection: { ...layer.selection },
    brightness_patterns: layer.brightness_patterns.map((pattern) => ({
      ...pattern,
    })),
    distribution: { ...layer.distribution },
    palette: clonePalette(layer.palette),
    selected_movement: { ...layer.selected_movement },
    overall_movement: { ...layer.overall_movement },
  };
  const appliedAreaSegments = (
    layer as EffectLayerWithAppliedAreaSegments
  )[APPLIED_AREA_SEGMENTS];
  if (appliedAreaSegments) {
    Object.defineProperty(clone, APPLIED_AREA_SEGMENTS, {
      value: { ...appliedAreaSegments },
      configurable: true,
    });
  }
  const layerLabel = (layer as EffectLayerWithAppliedAreaSegments)[LAYER_LABEL];
  if (layerLabel !== undefined) {
    setLayerLabel(clone, layerLabel);
  }
  return clone;
}

export function advancedLayerLabels(content: AdvancedContent): number[] {
  const labels = content.layers.map(
    (layer, index) =>
      (layer as EffectLayerWithAppliedAreaSegments)[LAYER_LABEL] ?? index + 1,
  );
  return validLayerLabels(labels, content.layers.length)
    ? labels
    : content.layers.map((_layer, index) => index + 1);
}

export function installAdvancedLayerLabels(
  content: AdvancedContent,
  labels: unknown,
): void {
  const resolved =
    Array.isArray(labels) && validLayerLabels(labels, content.layers.length)
      ? labels
      : content.layers.map((_layer, index) => index + 1);
  content.layers.forEach((layer, index) =>
    setLayerLabel(layer, resolved[index]),
  );
}

export function setAdvancedLayerLabel(
  layer: EffectLayer,
  label: number,
): void {
  setLayerLabel(layer, label);
}

export function nextAdvancedLayerLabel(content: AdvancedContent): number {
  const used = new Set(advancedLayerLabels(content));
  let candidate = 1;
  while (used.has(candidate)) {
    candidate += 1;
  }
  return candidate;
}

function setLayerLabel(layer: EffectLayer, label: number): void {
  Object.defineProperty(layer, LAYER_LABEL, {
    value: label,
    configurable: true,
    writable: true,
  });
}

function validLayerLabels(
  labels: readonly unknown[],
  layerCount: number,
): labels is number[] {
  return (
    labels.length === layerCount &&
    labels.every(
      (label) =>
        Number.isInteger(label) &&
        typeof label === "number" &&
        label > 0 &&
        label <= 255,
    ) &&
    new Set(labels).size === labels.length
  );
}

export function isKnownSelectionType(value: number): value is SelectionType {
  return KNOWN_SELECTION_TYPES.includes(value as SelectionType);
}

export function isKnownBrightnessOrder(
  value: number,
): value is BrightnessOrder {
  return KNOWN_BRIGHTNESS_ORDERS.includes(value as BrightnessOrder);
}

export function bytePercent(value: number): number {
  return Math.round((clampInteger(value, 0, 255) / 255) * 100);
}

interface AppliedAreaBounds {
  start: number;
  end: number;
}

interface AppliedAreaSegments extends AppliedAreaBounds {
  length: number;
}

export function adjustAppliedAreaLeftEdge(
  end: number,
  nextStart: number,
  maximum = 10,
): AppliedAreaBounds {
  const boundedEnd = clampInteger(
    end,
    1,
    Math.max(1, Math.round(maximum)),
  );
  return {
    start: clampInteger(nextStart, 0, boundedEnd - 1),
    end: boundedEnd,
  };
}

export function adjustAppliedAreaRightEdge(
  start: number,
  nextEnd: number,
  maximum = 10,
): AppliedAreaBounds {
  const boundedMaximum = Math.max(1, Math.round(maximum));
  const boundedStart = clampInteger(start, 0, boundedMaximum - 1);
  return {
    start: boundedStart,
    end: clampInteger(nextEnd, boundedStart + 1, boundedMaximum),
  };
}

export function moveAppliedArea(
  start: number,
  end: number,
  nextStart: number,
  maximum = 10,
): AppliedAreaBounds {
  const boundedMaximum = Math.max(1, Math.round(maximum));
  const currentStart = clampInteger(start, 0, boundedMaximum - 1);
  const currentEnd = clampInteger(
    end,
    currentStart + 1,
    boundedMaximum,
  );
  const width = currentEnd - currentStart;
  const boundedStart = clampInteger(
    nextStart,
    0,
    boundedMaximum - width,
  );
  return {
    start: boundedStart,
    end: boundedStart + width,
  };
}

export function appliedAreaSegments(
  start: number,
  width: number,
  segmentCount: number,
): AppliedAreaSegments {
  const boundedSegmentCount = Math.max(1, Math.round(segmentCount));
  const effectiveWidth = appliedAreaEffectiveWidth(width);
  const startSegment = Math.min(
    boundedSegmentCount - 1,
    Math.floor(
      (clampInteger(start, 0, 9) * boundedSegmentCount) / 10,
    ),
  );
  const length = Math.max(
    1,
    Math.round(
      (clampInteger(
        effectiveWidth,
        1,
        10 - clampInteger(start, 0, 9),
      ) *
        boundedSegmentCount) /
        10,
    ),
  );
  const endSegment = Math.min(boundedSegmentCount, startSegment + length);
  return {
    start: startSegment,
    end: endSegment,
    length: endSegment - startSegment,
  };
}

export function appliedAreaEffectiveWidth(width: number): number {
  return width === 0 ? 10 : width;
}

export function appliedAreaWireBounds(
  start: number,
  end: number,
  segmentCount: number,
): AppliedAreaBounds {
  const boundedSegmentCount = Math.max(1, Math.round(segmentCount));
  const boundedStart = clampInteger(
    start,
    0,
    boundedSegmentCount - 1,
  );
  const boundedEnd = clampInteger(
    end,
    boundedStart + 1,
    boundedSegmentCount,
  );
  const wireStart = clampInteger(
    (boundedStart * 10) / boundedSegmentCount,
    0,
    9,
  );
  return {
    start: wireStart,
    end: clampInteger(
      (boundedEnd * 10) / boundedSegmentCount,
      wireStart + 1,
      10,
    ),
  };
}

export function layerAppliedAreaSegments(
  layer: EffectLayer,
  segmentCount: number,
): AppliedAreaSegments {
  const appliedAreaSegments = (
    layer as EffectLayerWithAppliedAreaSegments
  )[APPLIED_AREA_SEGMENTS];
  if (
    appliedAreaSegments?.segmentCount === segmentCount &&
    appliedAreaSegments.start >= 0 &&
    appliedAreaSegments.end <= segmentCount &&
    appliedAreaSegments.end > appliedAreaSegments.start
  ) {
    const wire = appliedAreaWireBounds(
      appliedAreaSegments.start,
      appliedAreaSegments.end,
      segmentCount,
    );
    if (
      layer.area.start_tenths === wire.start &&
      layer.area.width_tenths === wire.end - wire.start
    ) {
      return {
        start: appliedAreaSegments.start,
        end: appliedAreaSegments.end,
        length: appliedAreaSegments.end - appliedAreaSegments.start,
      };
    }
  }
  return appliedAreaSegmentsFromWire(layer, segmentCount);
}

export function withAppliedAreaSegments(
  layer: EffectLayer,
  start: number,
  end: number,
  segmentCount: number,
): EffectLayer {
  const boundedSegmentCount = Math.max(1, Math.round(segmentCount));
  const boundedStart = clampInteger(
    start,
    0,
    boundedSegmentCount - 1,
  );
  const boundedEnd = clampInteger(
    end,
    boundedStart + 1,
    boundedSegmentCount,
  );
  const wire = appliedAreaWireBounds(
    boundedStart,
    boundedEnd,
    boundedSegmentCount,
  );
  const clone = cloneLayer({
    ...layer,
    area: {
      start_tenths: wire.start,
      width_tenths: wire.end - wire.start,
    },
  }) as EffectLayerWithAppliedAreaSegments;
  Object.defineProperty(clone, APPLIED_AREA_SEGMENTS, {
    value: {
      segmentCount: boundedSegmentCount,
      start: boundedStart,
      end: boundedEnd,
    },
    configurable: true,
  });
  return clone;
}

function appliedAreaSegmentsFromWire(
  layer: EffectLayer,
  segmentCount: number,
): AppliedAreaSegments {
  return appliedAreaSegments(
    layer.area.start_tenths,
    layer.area.width_tenths,
    segmentCount,
  );
}
