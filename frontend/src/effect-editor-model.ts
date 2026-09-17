import {
  advancedLayerLabels,
  cloneAdvancedContent,
  cloneLayeredSceneContent,
  installAdvancedLayerLabels,
} from "./advanced-effect-model";
import {
  cloneMusicProfileContent,
  cloneVideoProfileContent,
} from "./profile-model";
import type {
  AdvancedContent,
  CustomEffectContent,
  EffectContent,
  LayeredSceneContent,
  LibraryItem,
  LibrarySummary,
  LibrarySnapshot,
  LibraryOrigin,
  ModelEffectCatalogue,
  ModelSku,
  MusicProfileContent,
  OpaqueContent,
  PaletteDiyEffectContent,
  PaintedContent,
  RGB,
  VideoProfileContent,
  WorkshopContent,
} from "./types";
import { clonePalette, cloneRgb, sameRgb } from "./ui-utils";
import { LEGACY_CUSTOM_CATALOGUE_SKU } from "./validation-constants";

type AdvancedEditableContent =
  | AdvancedContent
  | LayeredSceneContent
  | WorkshopContent;
type ProfileContent =
  | PaletteDiyEffectContent
  | MusicProfileContent
  | VideoProfileContent;
export type EditableEffectContent =
  | CustomEffectContent
  | ProfileContent
  | AdvancedEditableContent;
export type NewEffectKind =
  | CustomEffectContent["kind"]
  | PaletteDiyEffectContent["kind"]
  | MusicProfileContent["kind"]
  | AdvancedContent["kind"];
export type CustomEffectCategory =
  | "all"
  | "music"
  | "single-layer"
  | "multi-layer"
  | "advanced"
  | "my-effects";
export type LibraryItemSyncResult =
  | { action: "none" }
  | { action: "removed" }
  | { action: "conflict"; summary: LibrarySummary }
  | { action: "reload"; summary: LibrarySummary };

export const PAINTED_SEGMENT_COUNT = 15;
export type PaintedSegmentDraft = PaintedContent["segments"][number];
export const EDITOR_EXTENSION_KEY = "ha_govee_led_ble.editor";

export function reactiveParameterValueText(
  parameter: string,
  value: number,
): string | undefined {
  return parameter === "point" ||
    parameter === "key_count" ||
    parameter === "segment_count"
    ? String(value)
    : undefined;
}

export function effectOriginDescription(
  origin: LibraryOrigin | undefined,
  sourceName?: string,
): string | undefined {
  const source = sourceName?.trim();
  if (!origin) {
    return source ? `Govee catalogue: ${source}` : undefined;
  }
  switch (origin.kind) {
    case "authored":
      return source ? `Based on ${source}` : undefined;
    case "catalogue_template":
      return `Govee catalogue: ${source ?? origin.source_id ?? "template"}`;
    case "imported":
      return `Imported${origin.source_id ? ` from ${origin.source_id}` : ""}`;
    case "captured_fixture":
      return `Captured source${origin.source_id ? `: ${origin.source_id}` : ""}`;
    case "migrated":
      return `Migrated effect${origin.source_id ? `: ${origin.source_id}` : ""}`;
    default:
      return source ?? origin.kind;
  }
}

export function blankPainted(): PaintedContent {
  return {
    kind: "h617a_painted",
    effect: "clockwise",
    speed: 50,
    brightness: 100,
    segments: blankPaintedSegments(),
  };
}

export function effectContentEligible(
  content: EffectContent,
  catalogue: ModelEffectCatalogue | undefined,
  model: string,
  segmentCount: number,
): boolean {
  if (content.kind === "advanced" && content.native_diy !== undefined) {
    return catalogue?.sku === model && catalogue?.templates?.some((template) =>
      template.content.kind === "advanced" && template.content.native_diy === content.native_diy) === true;
  }
  if (content.kind === "music_profile") {
    if (!catalogue || catalogue.sku !== model || content.model !== model ||
        !catalogue.music_modes.some((mode) => mode.id === content.mode)) return false;
    const settings = catalogue.music_settings[content.mode];
    if (!settings?.available || !Number.isInteger(content.sensitivity) ||
        content.sensitivity < catalogue.limits.music_sensitivity_min ||
        content.sensitivity > catalogue.limits.music_sensitivity_max) return false;
    if (content.calm !== null && (!settings.style || typeof content.calm !== "boolean")) return false;
    if (content.colour !== null && (!settings.colour || content.colour.length !== 3 ||
        !content.colour.every((channel) => Number.isInteger(channel) && channel >= 0 && channel <= 255))) return false;
    if (Object.keys(content.parameters).some((key) => !Object.hasOwn(settings.parameters, key))) return false;
    if (content.palette !== undefined && (!settings.palette ||
        content.palette.length < settings.palette.min || content.palette.length > settings.palette.max ||
        !content.palette.every(rgb => rgb.length === 3 && rgb.every(channel =>
          Number.isInteger(channel) && channel >= 0 && channel <= 255)))) return false;
    return Object.entries(settings.parameters).every(([key, spec]) => {
      const value = Object.hasOwn(content.parameters, key) ? content.parameters[key] : spec.default;
      if (spec.kind === "number") return typeof value === "number" && Number.isInteger(value) && value >= spec.min && value <= spec.max;
      if (spec.kind === "switch") return typeof value === "boolean";
      return typeof value === "string" && spec.options.includes(value);
    });
  }
  if (
    content.kind !== "h617a_painted" && content.kind !== "h617a_single" &&
    content.kind !== "h617a_multi" && content.kind !== "palette_diy"
  ) return true;
  if (!catalogue || catalogue.sku !== model) return false;
  const limits = catalogue.limits;
  if (content.kind === "h617a_painted") {
    return (
      catalogue.apply.painted === "supported" &&
      catalogue.painted_effects.some((effect) => effect.id === content.effect) &&
      (content.addressing ?? "segments") === (catalogue.painted_addressing ?? "segments") &&
      content.segments.length === (catalogue.painted_addressing === "physical_ic" ? catalogue.physical_ic_count : segmentCount) &&
      content.speed >= limits.speed_min && content.speed <= limits.speed_max &&
      content.brightness >= limits.brightness_min && content.brightness <= limits.brightness_max
    );
  }
  if (content.kind === "palette_diy" && (content.model !== model || catalogue.apply.palette_diy !== "supported")) return false;
  if (content.kind === "h617a_single" && catalogue.apply.single !== "supported") return false;
  if (content.palette.length < limits.palette_min || content.palette.length > limits.palette_max) return false;
  if (
    content.kind === "h617a_multi" && (
      catalogue.apply.multi !== "supported" || content.effects.length < 1 ||
      content.effects.length > limits.multi_max || content.speed < limits.speed_min ||
      content.speed > limits.speed_max
    )
  ) return false;
  const pairs = content.kind === "h617a_multi" ? content.effects : [content];
  return pairs.every((pair) => {
    const family = catalogue.effects.find((effect) => effect.family === pair.family);
    return (
      family !== undefined &&
      family.variations.some((variation) => variation.variant === pair.variant) &&
      (content.kind !== "h617a_multi" || family.supports_multi) &&
      content.palette.length <= (family.palette_max ?? limits.palette_max) &&
      content.speed >= (content.kind === "h617a_multi" ? family.multi_rate_min ?? family.rate_min : family.rate_min) && content.speed <= family.rate_max
    );
  });
}

export function blankPaintedSegments(): PaintedSegmentDraft[] {
  return Array.from({ length: PAINTED_SEGMENT_COUNT }, () => null);
}

export function blankCustomEffect(
  kind: "h617a_painted",
  catalogue: ModelEffectCatalogue,
): PaintedContent;
export function blankCustomEffect(
  kind: "h617a_single",
  catalogue: ModelEffectCatalogue,
  family?: number,
  variant?: number,
): Extract<CustomEffectContent, { kind: "h617a_single" }>;
export function blankCustomEffect(
  kind: "h617a_multi",
  catalogue: ModelEffectCatalogue,
): Extract<CustomEffectContent, { kind: "h617a_multi" }>;
export function blankCustomEffect(
  kind: CustomEffectContent["kind"],
  catalogue: ModelEffectCatalogue,
): CustomEffectContent;
export function blankCustomEffect(
  kind: CustomEffectContent["kind"],
  catalogue: ModelEffectCatalogue,
  family?: number,
  variant?: number,
): CustomEffectContent {
  if (kind === "h617a_painted") {
    const effect = catalogue.painted_effects.find((effect) => effect.id === "clockwise") ?? catalogue.painted_effects[0];
    if (!effect) throw new Error("The target catalogue has no painted effects.");
    return {
      ...blankPainted(), effect: effect.id,
      ...(catalogue.painted_addressing === "physical_ic" ? {
        addressing: "physical_ic" as const,
        background: cloneRgb(catalogue.painted_background ?? [255, 255, 255]),
        segments: Array.from({ length: catalogue.physical_ic_count ?? 0 }, () => null),
      } : {}),
      speed: Math.max(catalogue.limits.speed_min, Math.min(50, catalogue.limits.speed_max)),
      brightness: catalogue.limits.brightness_max,
    };
  }
  const preferred =
    kind === "h617a_multi"
      ? catalogue.effects.find(
          (effect) =>
            effect.supports_multi &&
            effect.id === "flow" &&
            effect.variations.length > 0,
        )
      : undefined;
  const first =
    preferred ??
    (kind === "h617a_multi"
      ? catalogue.effects.find(
          (effect) =>
            effect.supports_multi && effect.variations.length > 0,
        )
      : family === undefined
        ? catalogue.effects[0]
        : catalogue.effects.find((effect) => effect.family === family));
  if (!first) {
    throw new Error("The custom-effect catalogue has no compatible effects.");
  }
  const variation =
    variant !== undefined
      ? first.variations.find((candidate) => candidate.variant === variant)
      : (kind === "h617a_multi"
        ? first.variations.find((candidate) => candidate.id === "clockwise")
        : undefined) ?? first.variations[0];
  if (!variation) throw new Error("The target catalogue has no matching variation.");
  const pair = {
    family: first.family,
    variant: variation.variant,
  };
  if (kind === "h617a_single") {
    return {
      kind,
      ...pair,
      speed: Math.max(first.rate_min, Math.min(50, first.rate_max)),
      palette: first.palette_max === 3 ? [[255, 0, 0], [0, 255, 0], [0, 0, 255]] : defaultPalette(catalogue).slice(0, first.palette_max),
    };
  }
  return {
    kind,
    effects: [pair],
    speed: Math.max(catalogue.limits.speed_min, first.rate_min, Math.min(50, first.rate_max, catalogue.limits.speed_max)),
    palette: defaultPalette(catalogue),
  };
}

export function blankPaletteDiy(
  catalogue: ModelEffectCatalogue,
  model: string,
  family?: number,
  variant?: number,
): PaletteDiyEffectContent {
  if (catalogue.sku !== model) {
    throw new Error(
      `Custom-effect catalogue ${catalogue.sku} does not target ${model}.`,
    );
  }
  const selected =
    catalogue.effects.find((effect) => effect.family === family) ??
    catalogue.effects[0];
  if (!selected) {
    throw new Error("The custom-effect catalogue has no compatible effects.");
  }
  return {
    kind: "palette_diy",
    model,
    family: family ?? selected.family,
    variant: variant ?? selected.variations[0].variant,
    speed: Math.max(selected.rate_min, Math.min(50, selected.rate_max)),
    palette: defaultPalette(catalogue),
  };
}

function clonePainted(content: PaintedContent): PaintedContent {
  return {
    ...content,
    ...(content.background ? { background: cloneRgb(content.background) } : {}),
    segments: content.segments.map((segment) =>
      segment === null ? null : cloneRgb(segment),
    ),
  };
}

export function cloneCustomEffect(
  content: CustomEffectContent,
): CustomEffectContent {
  if (content.kind === "h617a_painted") {
    return clonePainted(content);
  }
  if (content.kind === "h617a_single") {
    return {
      ...content,
      palette: clonePalette(content.palette),
    };
  }
  return {
    ...content,
    effects: content.effects.map((effect) => ({ ...effect })),
    palette: clonePalette(content.palette),
  };
}

export function clonePaletteDiy(
  content: PaletteDiyEffectContent,
): PaletteDiyEffectContent {
  return {
    ...content,
    palette: clonePalette(content.palette),
  };
}

function cloneWorkshop(content: WorkshopContent): WorkshopContent {
  return {
    ...content,
    effect: {
      layers: cloneAdvancedContent({
        kind: "advanced",
        layers: content.effect.layers,
      }).layers,
    },
  };
}

export function cloneEditableEffect(
  content: EditableEffectContent,
): EditableEffectContent {
  if (content.kind === "advanced") {
    return cloneAdvancedContent(content);
  }
  if (content.kind === "scene_layered") {
    return cloneLayeredSceneContent(content);
  }
  if (content.kind === "workshop") {
    return cloneWorkshop(content);
  }
  if (content.kind === "palette_diy") {
    return clonePaletteDiy(content);
  }
  if (content.kind === "music_profile") {
    return cloneMusicProfileContent(content);
  }
  if (content.kind === "video_profile") {
    return cloneVideoProfileContent(content);
  }
  return cloneCustomEffect(content);
}

export function cloneOpaqueContent(content: OpaqueContent): OpaqueContent {
  return {
    ...content,
    body: structuredClone(content.body),
  };
}

export function advancedEditorContent(
  content: AdvancedEditableContent,
): AdvancedContent {
  return content.kind === "advanced"
    ? content
    : {
        kind: "advanced",
        layers: content.effect.layers,
      };
}

export function updateAdvancedEditorContent(
  current: AdvancedEditableContent,
  edited: AdvancedContent,
): AdvancedEditableContent {
  if (current.kind === "advanced") {
    return cloneAdvancedContent(edited);
  }
  if (current.kind === "workshop") {
    return {
      ...cloneWorkshop(current),
      effect: {
        layers: cloneAdvancedContent(edited).layers,
      },
    };
  }
  return {
    ...cloneLayeredSceneContent(current),
    effect: {
      layers: cloneAdvancedContent(edited).layers,
    },
  };
}

export function defaultPalette(catalogue?: ModelEffectCatalogue): RGB[] {
  const colours: RGB[] = [
    [255, 0, 0],
    [255, 127, 0],
    [255, 255, 0],
    [0, 255, 0],
    [0, 0, 255],
    [0, 255, 255],
    [139, 0, 255],
  ];
  if (!catalogue) return colours;
  const count = Math.max(catalogue.limits.palette_min, Math.min(colours.length, catalogue.limits.palette_max));
  return Array.from({ length: count }, (_, index) => cloneRgb(colours[index % colours.length]));
}

export function mergedPaintBrushes(colours: RGB[]): RGB[] {
  const brushes: RGB[] = [];
  for (const colour of [...colours, ...defaultPalette()]) {
    if (!brushes.some((brush) => sameRgb(brush, colour))) {
      brushes.push(cloneRgb(colour));
    }
    if (brushes.length === 8) {
      break;
    }
  }
  return brushes;
}

export function uniquePaintedPalette(content: PaintedContent): RGB[] {
  const palette: RGB[] = [];
  for (const colour of content.segments) {
    if (
      colour !== null &&
      !palette.some((existing) => sameRgb(existing, colour))
    ) {
      palette.push(cloneRgb(colour));
    }
    if (palette.length === 8) {
      break;
    }
  }
  return palette;
}

export function serialiseEditable(
  name: string,
  content: EditableEffectContent,
): string {
  return JSON.stringify({
    name: name.trim(),
    content,
    layer_labels: editableLayerLabels(content),
  });
}

export function editableLayerLabels(
  content: EffectContent,
): number[] | undefined {
  if (!isAdvancedEditableContent(content)) {
    return undefined;
  }
  return advancedLayerLabels(advancedEditorContent(content));
}

export function installLibraryItemEditorMetadata(
  item: LibraryItem,
): LibraryItem {
  if (!isAdvancedEditableContent(item.content)) {
    return item;
  }
  const extension = item.extensions[EDITOR_EXTENSION_KEY];
  const layerLabels =
    typeof extension === "object" &&
    extension !== null &&
    !Array.isArray(extension)
      ? (extension as Record<string, unknown>).layer_labels
      : undefined;
  installAdvancedLayerLabels(
    advancedEditorContent(item.content),
    layerLabels,
  );
  return item;
}

function isCustomEffectKind(
  kind: unknown,
): kind is CustomEffectContent["kind"] {
  return (
    kind === "h617a_painted" ||
    kind === "h617a_single" ||
    kind === "h617a_multi"
  );
}

export function isCustomEffectContent(
  content: unknown,
): content is CustomEffectContent {
  return (
    typeof content === "object" &&
    content !== null &&
    "kind" in content &&
    isCustomEffectKind(content.kind)
  );
}

export function isEditableEffectContent(
  content: unknown,
): content is EditableEffectContent {
  return (
    isCustomEffectContent(content) ||
    (typeof content === "object" &&
      content !== null &&
      "kind" in content &&
      (isAdvancedEditableKind(content.kind) ||
        content.kind === "palette_diy" ||
        content.kind === "music_profile" ||
        content.kind === "video_profile"))
  );
}

function isAdvancedEditableKind(
  kind: unknown,
): kind is AdvancedEditableContent["kind"] {
  return (
    kind === "advanced" ||
    kind === "scene_layered" ||
    kind === "workshop"
  );
}

export function isAdvancedEditableContent(
  content: EffectContent,
): content is AdvancedEditableContent {
  return isAdvancedEditableKind(content.kind);
}

function isKnownEffectKind(kind: string): boolean {
  return (
    isCustomEffectKind(kind) ||
    isAdvancedEditableKind(kind) ||
    kind === "palette_diy" ||
    kind === "music_profile" ||
    kind === "video_profile" ||
    kind === "scene_builtin" ||
    kind === "scene_palette"
  );
}

export function customKindLabel(kind: unknown): string {
  switch (kind) {
    case "h617a_painted":
      return "Paint";
    case "h617a_single":
      return "Single";
    case "h617a_multi":
      return "Multi";
    case "advanced":
      return "Advanced";
    case "palette_diy":
      return "Single";
    case "workshop":
      return "Workshop";
    default:
      return "Custom";
  }
}

export function isMyEffectKind(kind: string): boolean {
  return (
    isCustomEffectKind(kind) ||
    isAdvancedEditableKind(kind) ||
    kind === "palette_diy" ||
    kind === "music_profile" ||
    !isKnownEffectKind(kind)
  );
}

export function libraryKindPriority(
  kind: string,
  catalogue: ModelEffectCatalogue | undefined,
): number {
  const paletteDiyFirst =
    catalogue?.apply.palette_diy !== "unsupported" &&
    catalogue?.apply.single === "unsupported";
  const order = paletteDiyFirst
    ? [
        "palette_diy",
        "workshop",
        "music_profile",
        "advanced",
        "scene_layered",
      ]
    : [
        "h617a_painted",
        "h617a_single",
        "h617a_multi",
        "music_profile",
        "workshop",
        "advanced",
        "scene_layered",
      ];
  const priority = order.indexOf(kind);
  return priority === -1 ? order.length : priority;
}

export function customEffectCategoryForKind(
  kind: string,
): Exclude<CustomEffectCategory, "all" | "my-effects"> {
  if (kind === "h617a_multi") {
    return "multi-layer";
  }
  if (kind === "music_profile") {
    return "music";
  }
  if (
    kind === "h617a_painted" ||
    kind === "h617a_single" ||
    kind === "palette_diy"
  ) {
    return "single-layer";
  }
  return "advanced";
}

export function sameLibraryItemVersion(
  left: LibraryItem | undefined,
  right: LibraryItem | undefined,
): boolean {
  return left?.id === right?.id && left?.version === right?.version;
}

export function libraryItemSyncResult(
  current: Pick<LibraryItem, "id" | "version"> | undefined,
  summaries: readonly LibrarySummary[],
  dirty: boolean,
  deletingItemId?: string,
): LibraryItemSyncResult {
  if (!current) {
    return { action: "none" };
  }
  const summary = summaries.find((item) => item.id === current.id);
  if (!summary) {
    return deletingItemId === current.id
      ? { action: "none" }
      : { action: "removed" };
  }
  if (summary.version === current.version) {
    return { action: "none" };
  }
  return dirty
    ? { action: "conflict", summary }
    : { action: "reload", summary };
}

export function upsertSummary(
  summaries: LibrarySnapshot["items"],
  item: LibraryItem,
): LibrarySnapshot["items"] {
  const model = libraryItemModel(item);
  return [
    ...summaries.filter((summary) => summary.id !== item.id),
    {
      id: item.id,
      version: item.version,
      updated_at: item.updated_at,
      name: item.name,
      kind:
        item.content.kind === "opaque"
          ? item.content.source_kind
          : item.content.kind,
      content_hash: item.content_hash,
      origin: item.origin,
      ...(model ? { model } : {}),
      ...(item.content.kind === "scene_builtin" ||
      item.content.kind === "scene_palette" ||
      item.content.kind === "scene_layered"
        ? { template: item.content.template }
        : {}),
    },
  ].sort((left, right) => left.name.localeCompare(right.name));
}

function libraryItemModel(item: LibraryItem): ModelSku | undefined {
  const content = item.content;
  if (
    content.kind === "palette_diy" ||
    content.kind === "workshop" ||
    content.kind === "music_profile" ||
    content.kind === "video_profile"
  ) {
    return content.model;
  }
  if (
    content.kind === "h617a_painted" ||
    content.kind === "h617a_single" ||
    content.kind === "h617a_multi"
  ) {
    return item.target_hint?.model ?? LEGACY_CUSTOM_CATALOGUE_SKU;
  }
  if (
    content.kind === "scene_builtin" ||
    content.kind === "scene_palette" ||
    content.kind === "scene_layered"
  ) {
    return content.template.sku;
  }
  return item.target_hint?.model ?? undefined;
}
