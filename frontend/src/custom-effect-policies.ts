import type {
  CustomEffectContent,
  H6179MixedDiyContent,
  H6179SingleDiyContent,
  MultiContent,
  PaintedContent,
  PaletteDiyEffectContent,
  SingleContent,
} from "./types";

export const PAINTED_EFFECT_KIND = "h617a_painted";
export const SINGLE_EFFECT_KIND = "h617a_single";
export const MULTI_EFFECT_KIND = "h617a_multi";

export type CustomEffectCategory =
  | "all"
  | "static"
  | "music"
  | "single-layer"
  | "multi-layer"
  | "advanced"
  | "my-effects";
export type CustomEffectWorkflow = "painted" | "single" | "multi";
export type CustomEffectEditor = "painted" | "palette";

export function isPaintedEffectKind(
  kind: unknown,
): kind is PaintedContent["kind"] {
  return kind === PAINTED_EFFECT_KIND;
}

export function isSingleEffectKind(
  kind: unknown,
): kind is SingleContent["kind"] {
  return kind === SINGLE_EFFECT_KIND;
}

export function isMultiEffectKind(
  kind: unknown,
): kind is MultiContent["kind"] {
  return kind === MULTI_EFFECT_KIND;
}

export function isCustomEffectKind(
  kind: unknown,
): kind is CustomEffectContent["kind"] {
  return (
    isPaintedEffectKind(kind) ||
    isSingleEffectKind(kind) ||
    isMultiEffectKind(kind) ||
    kind === "h6179_single_diy" ||
    kind === "h6179_mixed_diy"
  );
}

export function normaliseCustomEffectKind(
  kind: unknown,
): CustomEffectWorkflow | undefined {
  if (isPaintedEffectKind(kind)) return "painted";
  if (
    isSingleEffectKind(kind) ||
    kind === "h6179_single_diy" ||
    kind === "palette_diy"
  ) return "single";
  if (isMultiEffectKind(kind) || kind === "h6179_mixed_diy") return "multi";
  return undefined;
}

export function isPaintedEffectContent(
  content: { kind: unknown } | undefined,
): content is PaintedContent {
  return isPaintedEffectKind(content?.kind);
}

export function isSingleEffectContent(
  content: { kind: unknown } | undefined,
): content is SingleContent {
  return isSingleEffectKind(content?.kind);
}

export function isMultiEffectContent(
  content: { kind: unknown } | undefined,
): content is MultiContent {
  return isMultiEffectKind(content?.kind);
}

export type SinglePaletteEffectContent =
  | SingleContent
  | H6179SingleDiyContent
  | PaletteDiyEffectContent;

export function isSinglePaletteEffectContent(
  content: { kind: unknown } | undefined,
): content is SinglePaletteEffectContent {
  return normaliseCustomEffectKind(content?.kind) === "single";
}

export type MixedPaletteEffectContent = MultiContent | H6179MixedDiyContent;

export function isMixedPaletteEffectContent(
  content: { kind: unknown } | undefined,
): content is MixedPaletteEffectContent {
  return normaliseCustomEffectKind(content?.kind) === "multi";
}

export function customEffectEditorForKind(
  kind: unknown,
): CustomEffectEditor | undefined {
  if (kind === "static_rgb") return "painted";
  const workflow = normaliseCustomEffectKind(kind);
  if (workflow === "painted") return "painted";
  if (workflow !== undefined || kind === "native_effect") return "palette";
  return undefined;
}

export function customEffectCategoryForKind(
  kind: string,
): Exclude<CustomEffectCategory, "all" | "my-effects"> {
  if (kind === "static_rgb") return "static";
  if (kind === "music_profile") return "music";
  const workflow = normaliseCustomEffectKind(kind);
  if (workflow === "multi") return "multi-layer";
  if (workflow === "painted" || workflow === "single") return "single-layer";
  return "advanced";
}

export function isPortableLibraryEffectKind(kind: string): boolean {
  return (
    kind === "static_rgb" ||
    kind === "advanced" ||
    isPaintedEffectKind(kind) ||
    isSingleEffectKind(kind) ||
    isMultiEffectKind(kind)
  );
}
