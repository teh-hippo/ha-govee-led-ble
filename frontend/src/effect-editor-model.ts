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
): CustomEffectContent {
  if (kind === "h617a_painted") {
    return blankPainted();
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
      : catalogue.effects[0]);
  if (!first) {
    throw new Error("The custom-effect catalogue has no compatible effects.");
  }
  const variation =
    (kind === "h617a_multi"
      ? first.variations.find((candidate) => candidate.id === "clockwise")
      : undefined) ?? first.variations[0];
  const pair = {
    family: first.family,
    variant: variation.variant,
  };
  if (kind === "h617a_single") {
    return {
      kind,
      ...pair,
      speed: 50,
      palette: defaultPalette(),
    };
  }
  return {
    kind,
    effects: [pair],
    speed: 50,
    palette: defaultPalette(),
  };
}

export function blankPaletteDiy(
  catalogue: ModelEffectCatalogue,
  model: string,
  family?: number,
  variant?: number,
): PaletteDiyEffectContent {
  if (model !== "H617A" && model !== "H6199") {
    throw new Error(`Unsupported custom-effect model ${model}.`);
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
    speed: 50,
    palette: defaultPalette(),
  };
}

export function blankVideoProfile(mode: string): VideoProfileContent {
  return {
    kind: "video_profile",
    model: "H6199",
    mode: mode === "game" ? "game" : "movie",
    full_screen: true,
    saturation: 50,
    sound_effects: false,
    sound_effects_softness: 50,
    white_balance_position: 17,
    relative_brightness: {
      left: 100,
      top: 100,
      right: 100,
      bottom: 100,
    },
    blank_screen: false,
  };
}

function clonePainted(content: PaintedContent): PaintedContent {
  return {
    ...content,
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

export function defaultPalette(): RGB[] {
  return [
    [255, 0, 0],
    [255, 127, 0],
    [255, 255, 0],
    [0, 255, 0],
    [0, 0, 255],
    [0, 255, 255],
    [139, 0, 255],
  ];
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
  model: ModelSku | undefined,
): number {
  const order =
    model === "H6199"
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
    return "H617A";
  }
  if (
    content.kind === "scene_builtin" ||
    content.kind === "scene_palette" ||
    content.kind === "scene_layered"
  ) {
    return knownModel(content.template.sku);
  }
  return knownModel(item.target_hint?.model);
}

function knownModel(
  model: string | null | undefined,
): ModelSku | undefined {
  return model === "H617A" || model === "H6199" ? model : undefined;
}
