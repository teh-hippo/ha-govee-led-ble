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
  NativeEffectContent,
  NativePaintLayer,
  OpaqueContent,
  PaletteDiyEffectContent,
  PaintedContent,
  StaticRgbContent,
  RGB,
  VideoProfileContent,
  LayeredRetainedSceneContent,
  RgbRetainedSceneContent,
} from "./types";
import { isNativeEffectModel, nativeEffectPolicy } from "./native-effect-policies";
import { clonePalette, cloneRgb, sameRgb } from "./ui-utils";
import { LEGACY_CUSTOM_CATALOGUE_SKU } from "./validation-constants";
import {
  MULTI_EFFECT_KIND,
  PAINTED_EFFECT_KIND,
  SINGLE_EFFECT_KIND,
  TYPED_MIXED_DIY_KIND,
  TYPED_SINGLE_DIY_KIND,
  customEffectCategoryForKind,
  isCustomEffectKind,
  isMultiEffectContent,
  isPaintedEffectContent,
  isPaintedEffectKind,
  isMultiEffectKind,
  isSingleEffectContent,
  isSingleEffectKind,
  isTypedDiyContent,
  isTypedMixedDiyContent,
  isTypedSingleDiyContent,
  normaliseCustomEffectKind,
  type CustomEffectCategory,
} from "./custom-effect-policies";

export { customEffectCategoryForKind };
export type { CustomEffectCategory } from "./custom-effect-policies";

type AdvancedEditableContent =
  | AdvancedContent
  | LayeredSceneContent
  | LayeredRetainedSceneContent;

export function paintNativeLayerPoint(layer: NativePaintLayer, index: number, colour: RGB | null): NativePaintLayer {
  if (!Number.isInteger(index) || index < 0 || index >= 133) throw new Error("Native paint point is outside the 133-point geometry.");
  const groups = layer.groups.map(group => ({ colour: [...group.colour] as RGB, indices: group.indices.filter(point => point !== index) }));
  if (colour !== null) {
    const group = groups.find(group => sameRgb(group.colour, colour));
    if (group) group.indices.push(index);
    else groups.push({ colour: [...colour], indices: [index] });
  }
  return { ...layer, groups };
}

type ProfileContent =
  | PaletteDiyEffectContent
  | NativeEffectContent
  | MusicProfileContent
  | VideoProfileContent;
export type EditableEffectContent =
  | StaticRgbContent
  | CustomEffectContent
  | ProfileContent
  | RgbRetainedSceneContent
  | AdvancedEditableContent;
export type NewEffectKind =
  | StaticRgbContent["kind"]
  | CustomEffectContent["kind"]
  | PaletteDiyEffectContent["kind"]
  | MusicProfileContent["kind"]
  | AdvancedContent["kind"];
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
    case "migrated":
      return `Migrated effect${origin.source_id ? `: ${origin.source_id}` : ""}`;
    default:
      return source ?? origin.kind;
  }
}

export function blankPainted(segmentCount = PAINTED_SEGMENT_COUNT): PaintedContent {
  return {
    kind: PAINTED_EFFECT_KIND,
    effect: "clockwise",
    speed: 50,
    brightness: 100,
    segments: blankPaintedSegments(segmentCount),
  };
}

export function effectContentEligible(
  content: EffectContent,
  catalogue: ModelEffectCatalogue | undefined,
  model: string,
  segmentCount: number,
): boolean {
  if (content.kind === "shared_scene_rgb" || content.kind === "shared_scene_rgbic_v1") {
    const workflow = content.kind === "shared_scene_rgb" ? "native_scenes" : "layered_scenes";
    return content.model === model && catalogue?.sku === model &&
      catalogue.workflows.some(candidate => candidate.id === workflow && candidate.application !== "planned");
  }
  if (content.kind === "workshop_rgb" || content.kind === "workshop_rgbic_v2") {
    return content.model === model && catalogue?.apply.workshop === "supported";
  }
  if (content.kind === "static_rgb") return content.segments.length === segmentCount && content.segments.some(colour => colour !== null);
  if (content.kind === "native_effect") {
    if (content.projector_layers) {
      const workflow = nativeEffectWorkflow(content);
      return catalogue?.sku === model && content.model === model &&
        catalogue.workflows.some(candidate => candidate.id === workflow && candidate.content_kind === "native_effect") &&
        content.projector_layers.some(layer => layer.coarse.enabled || layer.fine?.enabled || layer.stars.enabled);
    }
    const policy = isNativeEffectModel(content.model) ? nativeEffectPolicy(content.model) : undefined;
    if (policy?.acceptsCatalogueContent) return policy.acceptsCatalogueContent(content, catalogue, model);
    return catalogue?.sku === model && content.model === model &&
      (content.layers.length > 1 && catalogue.native_zones?.length === content.layers.length
        ? catalogue.apply.multi === "supported"
        : content.family === 798 ? catalogue.apply.painted === "supported" : catalogue.apply.single === "supported");
  }
  if (content.kind === "advanced" && content.native_diy !== undefined) {
    return catalogue?.sku === model && catalogue?.templates?.some((template) =>
      template.content.kind === "advanced" && template.content.native_diy === content.native_diy) === true;
  }
  if (content.kind === "advanced") {
    return catalogue === undefined || (
      catalogue.sku === model &&
      catalogue.advanced_create !== false &&
      catalogue.supports.advanced !== "unsupported"
    );
  }
  if (content.kind === "music_profile") {
    if (!catalogue || catalogue.sku !== model || content.model !== model ||
        !catalogue.music_modes.some((mode) => mode.id === content.mode)) return false;
    if (content.zones !== undefined) {
      const template = catalogue.templates?.find(candidate => candidate.content.kind === "music_profile" && candidate.content.mode === content.mode);
      if (template?.content.kind !== "music_profile" || template.content.zones === undefined ||
          content.zones.length !== catalogue.native_zones?.length ||
          content.zones.length !== template.content.zones.length) return false;
      if (!content.zones.every((zone, index) => zone.id === catalogue.native_zones![index].id &&
          zone.mode !== content.mode && (!catalogue.music_zone_modes || catalogue.music_zone_modes[zone.id]?.includes(zone.mode)) &&
          effectContentEligible({
            kind: "music_profile", model: content.model, mode: zone.mode, sensitivity: content.sensitivity,
            colour: null, calm: zone.calm ?? null, parameters: zone.parameters,
            ...(zone.palette === undefined ? {} : { palette: zone.palette }),
          }, catalogue.music_zone_modes ? {
            ...catalogue,
            music_modes: (catalogue.music_zone_modes[zone.id] ?? []).map(id => ({ id, label: id })),
          } : catalogue, model, segmentCount))) return false;
    }
    const settings = catalogue.music_settings[content.mode];
    if (!settings?.available || !Number.isInteger(content.sensitivity) ||
        content.sensitivity < catalogue.limits.music_sensitivity_min ||
        content.sensitivity > catalogue.limits.music_sensitivity_max) return false;
    if (content.calm !== null && (!settings.style || typeof content.calm !== "boolean")) return false;
    if (content.colour === null && settings.colour_default !== undefined) return false;
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
    !isPaintedEffectContent(content) &&
    !isSingleEffectContent(content) &&
    !isMultiEffectContent(content) &&
    content.kind !== "palette_diy"
  ) return true;
  if (!catalogue || catalogue.sku !== model) return false;
  const limits = catalogue.limits;
  if (isPaintedEffectContent(content)) {
    return (
      (content.model === undefined || content.model === model) &&
      catalogue.apply.painted === "supported" &&
      catalogue.painted_effects.some((effect) => effect.id === content.effect) &&
      (content.addressing ?? "segments") === (catalogue.painted_addressing ?? "segments") &&
      content.segments.length === (catalogue.painted_addressing === "physical_ic" ? catalogue.physical_ic_count : segmentCount) &&
      content.speed >= limits.speed_min && content.speed <= limits.speed_max &&
      content.brightness >= limits.brightness_min && content.brightness <= limits.brightness_max
    );
  }
  if (content.kind === "palette_diy" && (content.model !== model || catalogue.apply.palette_diy !== "supported")) return false;
  if (isSingleEffectContent(content) && catalogue.apply.single !== "supported") return false;
  if (content.palette.length < limits.palette_min || content.palette.length > limits.palette_max) return false;
  if (
    isMultiEffectContent(content) && (
      catalogue.apply.multi !== "supported" || content.effects.length < 1 ||
      content.effects.length > limits.multi_max || content.speed < limits.speed_min ||
      content.speed > limits.speed_max
    )
  ) return false;
  const multi = isMultiEffectContent(content);
  const pairs = multi ? content.effects : [content];
  return pairs.every((pair) => {
    const family = catalogue.effects.find((effect) => effect.family === pair.family);
    return (
      family !== undefined &&
      family.category === "single_layer" &&
      family.variations.some((variation) => variation.variant === pair.variant) &&
      (!multi || family.supports_multi) &&
      content.palette.length <= (family.palette_max ?? limits.palette_max) &&
      content.speed >= (multi ? family.multi_rate_min ?? family.rate_min : family.rate_min) && content.speed <= family.rate_max
    );
  });
}

export function blankPaintedSegments(segmentCount = PAINTED_SEGMENT_COUNT): PaintedSegmentDraft[] {
  return Array.from({ length: segmentCount }, () => null);
}

export function blankCustomEffect(
  kind: typeof PAINTED_EFFECT_KIND,
  catalogue: ModelEffectCatalogue,
  segmentCount: number,
): PaintedContent;
export function blankCustomEffect(
  kind: typeof SINGLE_EFFECT_KIND,
  catalogue: ModelEffectCatalogue,
  family?: number,
  variant?: number,
): Extract<CustomEffectContent, { kind: typeof SINGLE_EFFECT_KIND }>;
export function blankCustomEffect(
  kind: typeof MULTI_EFFECT_KIND,
  catalogue: ModelEffectCatalogue,
): Extract<CustomEffectContent, { kind: typeof MULTI_EFFECT_KIND }>;
export function blankCustomEffect(
  kind: typeof TYPED_SINGLE_DIY_KIND,
  catalogue: ModelEffectCatalogue,
): Extract<CustomEffectContent, { kind: typeof TYPED_SINGLE_DIY_KIND }>;
export function blankCustomEffect(
  kind: typeof TYPED_MIXED_DIY_KIND,
  catalogue: ModelEffectCatalogue,
): Extract<CustomEffectContent, { kind: typeof TYPED_MIXED_DIY_KIND }>;
export function blankCustomEffect(
  kind: Exclude<CustomEffectContent["kind"], typeof PAINTED_EFFECT_KIND>,
  catalogue: ModelEffectCatalogue,
  family?: number,
  variant?: number,
): CustomEffectContent;
export function blankCustomEffect(
  kind: CustomEffectContent["kind"],
  catalogue: ModelEffectCatalogue,
  family?: number,
  variant?: number,
): CustomEffectContent {
  if (isPaintedEffectKind(kind)) {
    if (family === undefined) {
      throw new Error("The target segment count is required for painted effects.");
    }
    const effect = catalogue.painted_effects.find((effect) => effect.id === "clockwise") ?? catalogue.painted_effects[0];
    if (!effect) throw new Error("The target catalogue has no painted effects.");
    return {
      ...blankPainted(family), effect: effect.id,
      ...(catalogue.painted_addressing === "physical_ic" ? {
        addressing: "physical_ic" as const,
        background: cloneRgb(catalogue.painted_background ?? [255, 255, 255]),
        segments: Array.from({ length: catalogue.physical_ic_count ?? 0 }, () => null),
      } : {}),
      speed: Math.max(catalogue.limits.speed_min, Math.min(50, catalogue.limits.speed_max)),
      brightness: catalogue.limits.brightness_max,
      ...(catalogue.native_zones ? {model: catalogue.sku} : {}),
    };
  }
  const mixed = normaliseCustomEffectKind(kind) === "multi";
  const preferred =
    isMultiEffectKind(kind)
      ? catalogue.effects.find(
          (effect) =>
            effect.supports_multi &&
            effect.id === "flow" &&
            effect.variations.length > 0,
        )
      : undefined;
  const first =
    preferred ??
    (mixed
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
      : (mixed
        ? first.variations.find((candidate) => candidate.id === "clockwise")
        : undefined) ?? first.variations[0];
  if (!variation) throw new Error("The target catalogue has no matching variation.");
  const pair = {
    family: first.family,
    variant: variation.variant,
  };
  if (isSingleEffectKind(kind)) {
    return {
      kind,
      ...pair,
      speed: Math.max(first.rate_min, Math.min(50, first.rate_max)),
      palette: first.palette_max === 3 ? [[255, 0, 0], [0, 255, 0], [0, 0, 255]] : defaultPalette(catalogue).slice(0, first.palette_max),
    };
  }
  if (kind === TYPED_SINGLE_DIY_KIND) {
    return {
      kind,
      model: catalogue.sku,
      ...pair,
      speed: 50,
      palette: defaultPalette(),
    };
  }
  if (kind === TYPED_MIXED_DIY_KIND) {
    return {
      kind,
      model: catalogue.sku,
      components: [pair],
      speed: 50,
      palette: defaultPalette(),
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
  if (isPaintedEffectContent(content)) {
    return clonePainted(content);
  }
  if (isSingleEffectContent(content) || isTypedSingleDiyContent(content)) {
    return {
      ...content,
      palette: clonePalette(content.palette),
    };
  }
  if (isTypedMixedDiyContent(content)) {
    return {
      ...content,
      components: content.components.map((component) => ({ ...component })),
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

function cloneWorkshop(content: LayeredRetainedSceneContent): LayeredRetainedSceneContent {
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
  if (content.kind === "static_rgb" || content.kind === "native_effect" || content.kind === "workshop_rgb" || content.kind === "shared_scene_rgb") {
    return structuredClone(content);
  }
  if (content.kind === "advanced") {
    return cloneAdvancedContent(content);
  }
  if (content.kind === "scene_layered") {
    return cloneLayeredSceneContent(content);
  }
  if (content.kind === "workshop" || content.kind === "workshop_rgbic_v2" || content.kind === "shared_scene_rgbic_v1") {
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
  if (current.kind === "workshop" || current.kind === "workshop_rgbic_v2" || current.kind === "shared_scene_rgbic_v1") {
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
        content.kind === "workshop_rgb" ||
        content.kind === "shared_scene_rgb" ||
        content.kind === "static_rgb" ||
        content.kind === "palette_diy" ||
        content.kind === "native_effect" ||
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
    kind === "workshop" ||
    kind === "shared_scene_rgbic_v1" ||
    kind === "workshop_rgbic_v2"
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
    kind === "workshop_rgb" ||
    kind === "shared_scene_rgb" ||
    kind === "static_rgb" ||
    kind === "palette_diy" ||
    kind === "native_effect" ||
    kind === "music_profile" ||
    kind === "video_profile" ||
    kind === "scene_builtin" ||
    kind === "scene_palette"
  );
}

export function customKindLabel(kind: unknown): string {
  switch (kind) {
    case "static_rgb":
      return "Canvas";
    case PAINTED_EFFECT_KIND:
      return "Paint";
    case SINGLE_EFFECT_KIND:
      return "Single";
    case MULTI_EFFECT_KIND:
      return "Multi";
    case TYPED_SINGLE_DIY_KIND:
      return "Single DIY";
    case TYPED_MIXED_DIY_KIND:
      return "Mixed DIY";
    case "advanced":
      return "Advanced";
    case "palette_diy":
      return "Single";
    case "native_effect":
      return "Native layers";
    case "workshop":
    case "workshop_rgb":
    case "workshop_rgbic_v2":
      return "Workshop";
    case "shared_scene_rgb":
    case "shared_scene_rgbic_v1":
      return "Shared scene";
    default:
      return "Custom";
  }
}

export function isMyEffectKind(kind: string): boolean {
  return (
    kind === "static_rgb" ||
    isCustomEffectKind(kind) ||
    isAdvancedEditableKind(kind) ||
    kind === "workshop_rgb" ||
    kind === "shared_scene_rgb" ||
    kind === "palette_diy" ||
    kind === "native_effect" ||
    kind === "music_profile" ||
    !isKnownEffectKind(kind)
  );
}

export function nativeEffectWorkflow(content: NativeEffectContent): NonNullable<LibrarySummary["native_workflow"]> {
  if (content.template !== null) return "layered_scenes";
  if (isNativeEffectModel(content.model)) return nativeEffectPolicy(content.model).workflow(content);
  return content.family === 798 ? "painted" : [11, 12].includes(content.preset_id ?? -1) ? "advanced" : "single";
}

export function customEffectCategoryForItem(
  item: LibraryItem | LibrarySummary,
): Exclude<CustomEffectCategory, "all" | "my-effects"> {
  const workflow = "content" in item
    ? item.content.kind === "native_effect" ? nativeEffectWorkflow(item.content) : undefined
    : item.native_workflow;
  if (workflow === "single" || workflow === "painted") return "single-layer";
  if (workflow === "multi") return "multi-layer";
  if (workflow === "advanced") return "advanced";
  return customEffectCategoryForKind("content" in item ? item.content.kind : item.kind);
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
      ...(item.content.kind === "native_effect" ? { native_workflow: nativeEffectWorkflow(item.content) } : {}),
      ...(model ? { model } : {}),
      ...(item.content.kind === "scene_builtin" ||
      item.content.kind === "scene_palette" ||
      item.content.kind === "scene_layered" ||
      item.content.kind === "native_effect" && item.content.template !== null
        ? { template: item.content.template! }
        : {}),
    },
  ].sort((left, right) => left.name.localeCompare(right.name));
}

export function libraryItemModel(item: LibraryItem): ModelSku | undefined {
  const content = item.content;
  if (isPaintedEffectContent(content) && content.model !== undefined) return content.model;
  if (isTypedDiyContent(content)) return content.model;
  if (
    content.kind === "palette_diy" ||
    content.kind === "native_effect" ||
    content.kind === "workshop" ||
    content.kind === "workshop_rgb" ||
    content.kind === "workshop_rgbic_v2" ||
    content.kind === "shared_scene_rgb" ||
    content.kind === "shared_scene_rgbic_v1" ||
    content.kind === "music_profile" ||
    content.kind === "video_profile"
  ) {
    return content.model;
  }
  if (
    isPaintedEffectKind(content.kind) ||
    isSingleEffectKind(content.kind) ||
    isMultiEffectKind(content.kind)
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
