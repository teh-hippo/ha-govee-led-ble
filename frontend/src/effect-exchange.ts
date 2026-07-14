import type {
  RGB,
  SegmentContentDict,
  StudioKind,
  VibrantContentDict,
} from "./logic";
import flatCatalogue from "./flat-catalogue.json";

export interface SketchContentDict {
  kind: "sketch";
  motion: number;
  speed: number;
  brightness: number;
  background: RGB;
  colors: (RGB | null)[];
}

export interface FlatContentDict {
  kind: "flat";
  family: number;
  variant: number;
  speed: number;
  palette: RGB[];
}

export interface ComboContentDict {
  kind: "combo";
  variant: number;
  speed: number;
  palette: RGB[];
  effects: [number, number][];
}

export type EffectContentDict =
  | SegmentContentDict
  | VibrantContentDict
  | SketchContentDict
  | FlatContentDict
  | ComboContentDict;

export interface ExportedEffect<TContent = EffectContentDict> {
  id: string;
  name: string;
  model: string;
  segment_count: number;
  content: TContent;
}

export type RawExportedEffect = ExportedEffect<Record<string, unknown>>;

export interface EffectExchangeDocument<TContent = EffectContentDict> {
  schema_version: 1;
  integration: "ha_govee_led_ble";
  source: {
    model: string;
    segment_count: number;
  };
  effect: {
    name: string;
    content: TContent;
  };
}

export interface EffectExchangeTarget {
  model: string | null;
  segmentCount: number;
}

export interface FlatVariant {
  id: string;
  label: string;
  variant: number;
}

export interface FlatFamily {
  id: string;
  label: string;
  family: number;
  palette_max: number;
  control_label: string;
  description: string;
  variants: FlatVariant[];
}

export const FLAT_CATALOGUE: readonly FlatFamily[] = flatCatalogue;
const COMBO_FAMILY_CODES = new Set([0x00, 0x01, 0x02, 0x03, 0x08, 0x09]);
export const COMBO_CATALOGUE: readonly FlatFamily[] = FLAT_CATALOGUE.filter(
  (family) => COMBO_FAMILY_CODES.has(family.family),
);

export const SKETCH_MOTIONS: readonly { code: number; label: string }[] = [
  { code: 0x02, label: "Cycle" },
  { code: 0x09, label: "Clockwise" },
  { code: 0x0a, label: "Counter-clockwise" },
  { code: 0x0f, label: "Twinkle" },
  { code: 0x13, label: "Gradient" },
  { code: 0x14, label: "Breathe" },
];

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function nonBlankString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return value.trim();
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error(`${label} must be an integer.`);
  }
  return value;
}

function percentage(value: unknown, label: string): number {
  const parsed = integer(value, label);
  if (parsed < 0 || parsed > 100) {
    throw new Error(`${label} must be from 0 to 100.`);
  }
  return parsed;
}

function byte(value: unknown, label: string): number {
  const parsed = integer(value, label);
  if (parsed < 0 || parsed > 255) {
    throw new Error(`${label} must be from 0 to 255.`);
  }
  return parsed;
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array.`);
  return value;
}

function rgb(value: unknown, label: string): RGB {
  const channels = array(value, label);
  if (
    channels.length !== 3 ||
    channels.some(
      (channel) =>
        typeof channel !== "number" ||
        !Number.isInteger(channel) ||
        channel < 0 ||
        channel > 255,
    )
  ) {
    throw new Error(`${label} must contain three channels from 0 to 255.`);
  }
  return [channels[0] as number, channels[1] as number, channels[2] as number];
}

function optionalRgb(value: unknown, label: string): RGB | null {
  return value === null ? null : rgb(value, label);
}

function rgbList(value: unknown, label: string): RGB[] {
  return array(value, label).map((entry, index) => rgb(entry, `${label}[${index}]`));
}

function optionalRgbList(value: unknown, label: string): (RGB | null)[] {
  return array(value, label).map((entry, index) =>
    optionalRgb(entry, `${label}[${index}]`),
  );
}

export function parseEffectContent(value: unknown): EffectContentDict {
  const content = record(value, "Effect content");
  const kind = nonBlankString(content.kind, "Effect kind");
  switch (kind) {
    case "segments": {
      const rawBrightness = content.brightness;
      let brightness: (number | null)[] | null = null;
      if (rawBrightness !== null) {
        brightness = array(rawBrightness, "Segment brightness").map(
          (entry, index) =>
            entry === null ? null : percentage(entry, `Segment brightness[${index}]`),
        );
      }
      return {
        kind,
        colors: optionalRgbList(content.colors, "Segment colours"),
        brightness,
      };
    }
    case "vibrant": {
      const stops = rgbList(content.stops, "Gradient stops");
      if (stops.length < 2 || stops.length > 5) {
        throw new Error("Gradient stops must contain from 2 to 5 colours.");
      }
      return {
        kind,
        stops,
      };
    }
    case "sketch": {
      const motion = integer(content.motion, "Sketch motion");
      if (!SKETCH_MOTIONS.some((entry) => entry.code === motion)) {
        throw new Error("Sketch motion is not supported.");
      }
      return {
        kind,
        motion,
        speed: percentage(content.speed, "Sketch speed"),
        brightness: percentage(content.brightness, "Sketch brightness"),
        background: rgb(content.background, "Sketch background"),
        colors: optionalRgbList(content.colors, "Sketch colours"),
      };
    }
    case "flat": {
      const family = integer(content.family, "Flat family");
      const variant = integer(content.variant, "Flat variant");
      flatVariantLabel(family, variant);
      const palette = rgbList(content.palette, "Flat palette");
      const familyEntry = flatFamilyByCode(family);
      if (palette.length > familyEntry.palette_max) {
        throw new Error(
          `${familyEntry.label} accepts up to ${familyEntry.palette_max} colours.`,
        );
      }
      return {
        kind,
        family,
        variant,
        speed: percentage(content.speed, "Flat speed"),
        palette,
      };
    }
    case "combo": {
      const effects = array(content.effects, "Combo effects").map((entry, index) => {
        const pair = array(entry, `Combo effects[${index}]`);
        if (pair.length !== 2) {
          throw new Error(`Combo effects[${index}] must contain a family and variant.`);
        }
        const family = integer(pair[0], `Combo effects[${index}].family`);
        const variant = integer(pair[1], `Combo effects[${index}].variant`);
        comboVariantLabel(family, variant);
        return [family, variant] as [number, number];
      });
      if (effects.length === 0) throw new Error("Combo requires at least one step.");
      if (effects.length > 4) throw new Error("Combo accepts up to four steps.");
      const palette = rgbList(content.palette, "Combo palette");
      if (palette.length === 0) throw new Error("Combo requires at least one palette colour.");
      if (palette.length > 8) throw new Error("Combo accepts up to 8 colours.");
      const variant = byte(content.variant, "Combo variant");
      if (variant !== 0) throw new Error("Combo variant must be 0.");
      return {
        kind,
        variant,
        speed: percentage(content.speed, "Combo speed"),
        palette,
        effects,
      };
    }
    default:
      throw new Error(`Unsupported effect kind "${kind}".`);
  }
}

export function parseRawExportedEffect(value: unknown): RawExportedEffect {
  const effect = record(value, "Export response");
  const segmentCount = integer(effect.segment_count, "Export segment count");
  if (segmentCount <= 0) throw new Error("Export segment count must be positive.");
  return {
    id: nonBlankString(effect.id, "Effect ID"),
    name: nonBlankString(effect.name, "Effect name"),
    model: nonBlankString(effect.model, "Effect model"),
    segment_count: segmentCount,
    content: record(effect.content, "Effect content"),
  };
}

export function parseExportedEffect(value: unknown): ExportedEffect {
  const effect = parseRawExportedEffect(value);
  return {
    ...effect,
    content: parseEffectContent(effect.content),
  };
}

export function parseEntityExportResponse(
  value: unknown,
  entityId: string,
): ExportedEffect {
  const responses = record(value, "Entity service response");
  if (!(entityId in responses)) {
    throw new Error(`The export response did not include ${entityId}.`);
  }
  return parseExportedEffect(responses[entityId]);
}

export function parseEntityRawExportResponse(
  value: unknown,
  entityId: string,
): RawExportedEffect {
  const responses = record(value, "Entity service response");
  if (!(entityId in responses)) {
    throw new Error(`The export response did not include ${entityId}.`);
  }
  return parseRawExportedEffect(responses[entityId]);
}

export function buildEffectExchangeDocument<TContent>(
  effect: ExportedEffect<TContent>,
): EffectExchangeDocument<TContent> {
  return {
    schema_version: 1,
    integration: "ha_govee_led_ble",
    source: {
      model: effect.model,
      segment_count: effect.segment_count,
    },
    effect: {
      name: effect.name,
      content: effect.content,
    },
  };
}

export function parseEffectExchangeJson(
  text: string,
  target: EffectExchangeTarget,
): EffectExchangeDocument<EffectContentDict> {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("This is not valid JSON.");
  }
  const document = record(value, "Effect document");
  if (document.schema_version !== 1) {
    throw new Error("This effect uses an unsupported schema version.");
  }
  if (document.integration !== "ha_govee_led_ble") {
    throw new Error("This file is not a Govee LED BLE effect.");
  }
  const source = record(document.source, "Effect source");
  const model = nonBlankString(source.model, "Source model");
  const segmentCount = integer(source.segment_count, "Source segment count");
  if (segmentCount <= 0) throw new Error("Source segment count must be positive.");
  if (segmentCount !== target.segmentCount) {
    throw new Error(
      `This effect needs ${segmentCount} segments; this light has ${target.segmentCount}.`,
    );
  }
  if (target.model !== null && target.model !== model) {
    throw new Error(
      `This effect was exported for ${model}; this light is ${target.model}.`,
    );
  }
  const effect = record(document.effect, "Effect");
  const content = parseEffectContent(effect.content);
  if (
    (content.kind === "segments" || content.kind === "sketch") &&
    content.colors.length > segmentCount
  ) {
    throw new Error(`This effect contains more than ${segmentCount} segments.`);
  }
  if (
    content.kind === "segments" &&
    content.brightness !== null &&
    content.brightness.length > segmentCount
  ) {
    throw new Error(`This effect contains more than ${segmentCount} brightness values.`);
  }
  return {
    schema_version: 1,
    integration: "ha_govee_led_ble",
    source: { model, segment_count: segmentCount },
    effect: {
      name: nonBlankString(effect.name, "Effect name"),
      content,
    },
  };
}

export function studioKindForContent(content: EffectContentDict): StudioKind {
  switch (content.kind) {
    case "segments":
      return "static";
    case "vibrant":
      return "gradient";
    default:
      return content.kind;
  }
}

export function buildSketchContent(
  colors: readonly (RGB | null)[],
  motion: number,
  speed: number,
  brightness: number,
  background: RGB,
): SketchContentDict {
  return {
    kind: "sketch",
    motion,
    speed,
    brightness,
    background: [background[0], background[1], background[2]],
    colors: colors.map((color) =>
      color === null ? null : [color[0], color[1], color[2]],
    ),
  };
}

export function flatFamilyByCode(family: number): FlatFamily {
  const entry = FLAT_CATALOGUE.find((candidate) => candidate.family === family);
  if (entry === undefined) throw new Error(`Unknown Flat family ${family}.`);
  return entry;
}

export function comboFamilyByCode(family: number): FlatFamily {
  const entry = COMBO_CATALOGUE.find((candidate) => candidate.family === family);
  if (entry === undefined) throw new Error(`Flat family ${family} is not available in Combo.`);
  return entry;
}

export function buildFlatContent(
  family: number,
  variant: number,
  speed: number,
  palette: readonly RGB[],
): FlatContentDict {
  const familyEntry = flatFamilyByCode(family);
  if (!familyEntry.variants.some((entry) => entry.variant === variant)) {
    throw new Error(`Unknown variant for ${familyEntry.label}.`);
  }
  if (palette.length === 0) throw new Error("Add at least one palette colour.");
  if (palette.length > familyEntry.palette_max) {
    throw new Error(
      `${familyEntry.label} accepts up to ${familyEntry.palette_max} colours.`,
    );
  }
  return {
    kind: "flat",
    family,
    variant,
    speed,
    palette: palette.map((color) => [color[0], color[1], color[2]]),
  };
}

export function flatVariantLabel(family: number, variant: number): string {
  const familyEntry = flatFamilyByCode(family);
  const variantEntry = familyEntry.variants.find(
    (candidate) => candidate.variant === variant,
  );
  if (variantEntry === undefined) {
    throw new Error(`Unknown variant for ${familyEntry.label}.`);
  }
  return variantEntry.label;
}

export function comboVariantLabel(family: number, variant: number): string {
  const familyEntry = comboFamilyByCode(family);
  const variantEntry = familyEntry.variants.find(
    (candidate) => candidate.variant === variant,
  );
  if (variantEntry === undefined) {
    throw new Error(`Unknown Combo variant for ${familyEntry.label}.`);
  }
  return variantEntry.label;
}

export function buildComboContent(
  effects: readonly (readonly [number, number])[],
  speed: number,
  palette: readonly RGB[],
  variant = 0,
): ComboContentDict {
  if (variant !== 0) throw new Error("Combo variant must be 0.");
  if (effects.length === 0) throw new Error("Add at least one Combo step.");
  if (effects.length > 4) throw new Error("Combo accepts up to four steps.");
  for (const [family, variant] of effects) comboVariantLabel(family, variant);
  if (palette.length === 0) throw new Error("Add at least one palette colour.");
  if (palette.length > 8) throw new Error("Combo accepts up to 8 colours.");
  return {
    kind: "combo",
    variant,
    speed,
    palette: palette.map((color) => [color[0], color[1], color[2]]),
    effects: effects.map(([family, variant]) => [family, variant]),
  };
}

export function sketchPreviewColors(content: SketchContentDict): RGB[] {
  const level = Math.max(0, Math.min(100, content.brightness)) / 100;
  return content.colors.map((color) => {
    const source = color ?? content.background;
    return source.map((channel) => Math.round(channel * level)) as RGB;
  });
}

export function suggestDuplicateName(
  name: string,
  existingNames: readonly string[],
): string {
  const taken = new Set(existingNames.map(normaliseEffectName));
  const base = `${effectNameCore(name)} copy`;
  if (!taken.has(normaliseEffectName(base))) return base;
  for (let suffix = 2; ; suffix += 1) {
    const candidate = `${base} ${suffix}`;
    if (!taken.has(normaliseEffectName(candidate))) return candidate;
  }
}

function effectNameCore(name: string): string {
  return name
    .trim()
    .replace(/^["'“”‘’]+|["'“”‘’]+$/gu, "")
    .trim()
    .replace(/\s+/gu, " ");
}

export function normaliseEffectName(name: string): string {
  return effectNameCore(name)
    .toLocaleLowerCase()
    .replaceAll("ß", "ss")
    .replaceAll("ς", "σ");
}

export function resolveImportName(
  name: string,
  existingNames: readonly string[],
): string {
  const trimmed = name.trim();
  const taken = existingNames.some(
    (entry) => normaliseEffectName(entry) === normaliseEffectName(trimmed),
  );
  return taken ? suggestDuplicateName(trimmed, existingNames) : trimmed;
}

export function effectFileName(name: string): string {
  const safe = name
    .trim()
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${safe || "govee-effect"}.json`;
}
