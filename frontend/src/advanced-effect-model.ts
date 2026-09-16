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
    ...content,
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

export function selectionQuantity(selection: EffectLayer["selection"]): number {
  return selection.param_1 * 256 + selection.param_2;
}

export function withSelectionQuantity(quantity: number): Pick<EffectLayer["selection"], "param_1" | "param_2"> {
  const value = clampInteger(quantity, 0, 65535);
  return { param_1: value >>> 8, param_2: value & 255 };
}

export function layerBrightness(layer: EffectLayer): { algorithm: number; type: number } {
  return {
    algorithm: layer.unknown_flags >>> 4,
    type: (layer.unknown_flags & 15) | (layer.brightness_gradient ? 2 : 0),
  };
}

export function withLayerBrightness(layer: EffectLayer, update: { algorithm?: number; type?: number }): Partial<EffectLayer> {
  const value = { ...layerBrightness(layer), ...update };
  return {
    brightness_gradient: Boolean(value.type & 2),
    unknown_flags: (value.algorithm << 4) | (value.type & 13),
  };
}

export interface NativeDiyEdit {
  palette?: EffectLayer["palette"];
  secondary?: EffectLayer["palette"];
  background?: EffectLayer["palette"][number];
  speed?: number;
  brightness?: number;
  low?: number;
  high?: number;
  direction?: number;
  gradient?: boolean;
  starMin?: number;
  starMax?: number;
}

export function nativeDiyPalette(content: AdvancedContent, secondary = false): EffectLayer["palette"] {
  const code = content.native_diy;
  const indices = code === 501 ? [1, 2] : code === 502 ? [0, 1]
    : code === 504 ? [0, 1, 2] : code === 506 ? secondary ? content.layers[2].area.width_tenths === 5 ? [2, 3] : [2] : [0, 1]
    : code === 507 ? secondary ? [0] : [1] : [0];
  const groups = indices.map((index) => content.layers[index].palette);
  return Array.from({ length: Math.max(...groups.map((group) => group.length)) }, (_, index) =>
    groups.flatMap((group) => group[index] ? [group[index]] : [])).flat();
}

/** APK ParamsV2 named edits over the same canonical layers used by the encoder. */
export function updateNativeDiy(content: AdvancedContent, edit: NativeDiyEdit, physicalIcCount?: number | null): AdvancedContent {
  const result = cloneAdvancedContent(content);
  const layers = result.layers;
  const code = content.native_diy;
  const palettes = (indices: number[], colours: EffectLayer["palette"]) => {
    const sizes = indices.map((index) => layers[index].palette.length);
    if (colours.length === sizes.reduce((sum, size) => sum + size, 0)) {
      let position = 0;
      for (let slot = 0; slot < Math.max(...sizes); slot++) {
        indices.forEach((index, group) => {
          if (slot < sizes[group]) layers[index].palette[slot] = [...colours[position++]];
        });
      }
      return;
    }
    indices.forEach((index, group) => {
      const palette = colours.filter((_rgb, position) => position % indices.length === group);
      if (palette.length) layers[index].palette = clonePalette(palette);
    });
  };
  const patterns = (indices: number[], update: Partial<BrightnessPattern>) => {
    indices.forEach((index) => {
      layers[index].brightness_patterns = layers[index].brightness_patterns.map((pattern) => ({ ...pattern, ...update }));
    });
  };
  const indices = layers.map((_layer, index) => index);
  if (edit.palette) palettes(code === 501 ? [1, 2] : code === 502 ? [0, 1]
    : code === 504 ? [0, 1, 2] : code === 506 ? [0, 1] : code === 507 ? [1] : [0], edit.palette);
  if (edit.secondary) palettes(code === 506 ? layers[2].area.width_tenths === 5 ? [2, 3] : [2] : [0], edit.secondary);
  if (edit.background) layers[code === 501 ? 0 : 1].palette = clonePalette([edit.background]);
  if (edit.speed !== undefined) {
    const speed = edit.speed;
    if (code === 503 || code === 504) layers.forEach((layer) => { layer.overall_movement.speed = speed; });
    else {
      const targets = code === 501 ? [1, 2] : code === 505 ? [0] : indices;
      targets.forEach((index) => { layers[index].colour_speed = speed; });
      if (code !== 501) patterns(targets, { change_speed: speed });
      if (code === 505) layers[0].selected_movement.speed = speed;
    }
  }
  if (edit.low !== undefined || edit.high !== undefined) {
    const targets = code === 501 ? [1, 2] : [0];
    const pattern = layers[targets[0]].brightness_patterns[0];
    const low = edit.low ?? pattern.scope_low;
    const high = edit.high ?? pattern.scope_high;
    patterns(targets, { scope_low: low, scope_high: high });
    patterns([code === 501 ? 0 : 1], { scope_low: Math.max(20, low), scope_high: Math.max(20, low) });
  }
  if (edit.brightness !== undefined) patterns(indices, {
    scope_high: edit.brightness,
    ...(code === 507 ? { scope_low: edit.brightness } : {}),
  });
  if (edit.gradient !== undefined && code === 501) {
    layers.forEach((layer, index) => { layer.colour_retention = edit.gradient ? 50 : index === 0 ? 250 : 10; });
  }
  if (edit.starMin !== undefined || edit.starMax !== undefined) {
    if (physicalIcCount == null) throw new Error("Sky star size requires physical IC count");
    const minimum = edit.starMin ?? layers[0].selection.param_2;
    const maximum = edit.starMax ?? layers[0].selection.param_1;
    if (minimum < 1 || maximum < minimum || maximum > Math.min(25, Math.floor(physicalIcCount * 4 / 5))) {
      throw new Error("Sky star size is outside APK physical-IC bounds");
    }
    layers.forEach((layer) => { layer.selection = { type: 2, param_1: maximum, param_2: minimum }; });
  }
  if (edit.direction !== undefined) {
    const forward = edit.direction === 0;
    if (code === 503 || code === 504) {
      layers.forEach((layer, index) => {
        layer.area = { width_tenths: 2, start_tenths: forward ? [0, 4, 7][index] : [9, 5, 2][index] };
        layer.overall_movement.direction = forward ? 0 : 2;
      });
      patterns(indices, { order: forward ? 2 : 0 });
    } else if (code === 507) {
      layers[0].selected_movement.direction = forward ? 2 : 0;
      layers[1].selected_movement.direction = forward ? 0 : 2;
    } else if (code === 506) {
      if (physicalIcCount == null) throw new Error("Bloom direction requires physical IC count");
      const colours = edit.secondary ?? nativeDiyPalette(content, true);
      layers.slice(2).forEach((layer, index) => {
        const both = edit.direction === 2;
        layer.area = { start_tenths: both ? index * 5 : 0, width_tenths: both ? 5 : 0 };
        layer.selection = { type: 1, ...withSelectionQuantity(both ? Math.floor(physicalIcCount / 2) : index === 0 ? physicalIcCount : 1) };
        layer.selected_movement.enter_exit = true;
        layer.selected_movement.direction = both ? index * 2 : forward ? 0 : 2;
        layer.priority = !both && index === 0 ? 1 : 0;
        if (!both) {
          layer.palette = index === 0 ? clonePalette(colours) : [[0, 0, 0]];
        }
      });
      if (edit.direction === 2) palettes([2, 3], colours);
    }
  }
  return result;
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
