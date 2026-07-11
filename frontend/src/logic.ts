/**
 * Pure, dependency-free logic for the Govee LED BLE segment painter card.
 *
 * This module is imported by both the LitElement card and the vitest unit
 * tests. It contains no DOM, no lit, and no Home Assistant coupling so it can
 * be exercised in isolation.
 *
 * Conventions:
 * - Segment indices are 1-based (1..15), matching the device/protocol domain
 *   (`custom_components/ha_govee_led_ble/protocol.py` `segments_to_mask`).
 * - A selection is a `Set<number>` of 1-based segment indices.
 * - Colours are `[r, g, b]` triples with channels in 0..255.
 */

/** An `[r, g, b]` colour triple, channels 0..255. */
export type RGB = [number, number, number];

/** Number of addressable segments on the supported strips. */
export const SEGMENT_COUNT = 15;

/** Mask with every segment selected (segments 1..15 -> bits 0..14). */
export const ALL_SEGMENTS_MASK = 0x7fff;

/** Clamp `n` into the inclusive range `[lo, hi]`. */
export function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/** Parse a `#rrggbb` (or `rrggbb`) hex string into an `[r, g, b]` triple. */
export function hexToRgb(hex: string): RGB {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

/** Format an `[r, g, b]` triple as `#rrggbb`, clamping and rounding channels. */
export function rgbToHex(rgb: readonly number[]): string {
  return (
    "#" +
    rgb
      .map((c) => clamp(Math.round(c), 0, 255).toString(16).padStart(2, "0"))
      .join("")
  );
}

/**
 * Sample a list of `[r, g, b]` stops as a smooth gradient at position `t`.
 *
 * `t` is clamped to `[0, 1]`. The returned channels are floats (not rounded)
 * so the card can drive CSS gradients directly. Rounding these samples at the
 * evenly-spaced segment positions reproduces the device-resolved segment
 * colours; see the numeric-parity tests against the Python `_interpolate`
 * reference.
 */
export function sampleStops(stops: readonly RGB[], t: number): RGB {
  if (stops.length === 0) throw new Error("no stops");
  if (stops.length === 1) {
    const only = stops[0];
    return [only[0], only[1], only[2]];
  }
  const span = stops.length - 1;
  const pos = clamp(t, 0, 1) * span;
  const lo = clamp(Math.floor(pos), 0, span - 1);
  const frac = pos - lo;
  const a = stops[lo];
  const b = stops[lo + 1];
  return [
    a[0] + (b[0] - a[0]) * frac,
    a[1] + (b[1] - a[1]) * frac,
    a[2] + (b[2] - a[2]) * frac,
  ];
}

/**
 * Round `x` half-to-even (banker's rounding), matching CPython's built-in
 * `round()`. The Python gradient reference (`_interpolate` in the mock
 * integration's `services.py`) rounds each interpolated channel with `round()`,
 * so reproducing the device-resolved segment colours requires the same
 * tie-breaking: `pyRound(126.5) === 126`, `pyRound(127.5) === 128`.
 */
export function pyRound(x: number): number {
  const floor = Math.floor(x);
  const frac = x - floor;
  if (frac < 0.5) return floor;
  if (frac > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** One paint group: a single `[r, g, b]` applied to a set of 1-based segments. */
export interface SegmentGroup {
  /** 1-based segment indices this colour is applied to. */
  segments: number[];
  /** The `[r, g, b]` colour for these segments (integer channels 0..255). */
  rgb_color: RGB;
}

/**
 * Resolve `stops` to one integer `[r, g, b]` per segment by sampling the
 * gradient at the `count` evenly-spaced positions `i / (count - 1)` and
 * rounding each channel like CPython (`pyRound`).
 *
 * This is the client-side twin of the device/reference interpolation
 * (`_interpolate` in the mock integration's `services.py`); the numeric-parity
 * tests assert the two agree channel-for-channel. A single stop fills every
 * segment with that colour; an empty stop list throws.
 */
export function interpolateSegments(
  stops: readonly RGB[],
  count: number = SEGMENT_COUNT,
): RGB[] {
  if (stops.length === 0) throw new Error("no stops");
  if (count <= 0) return [];
  if (stops.length === 1) {
    const only = stops[0];
    return Array.from(
      { length: count },
      () => [only[0], only[1], only[2]] as RGB,
    );
  }
  return Array.from({ length: count }, (_unused, i) => {
    const t = count > 1 ? i / (count - 1) : 0;
    return sampleStops(stops, t).map(pyRound) as RGB;
  });
}

/**
 * Collapse a per-segment colour list into `paint_segments` groups: one group
 * per distinct colour, its `segments` the 1-based indices sharing that colour,
 * in first-appearance order. Feeding these groups to
 * `ha_govee_led_ble.paint_segments` repaints exactly the sampled gradient with
 * the fewest writes (equal colours, contiguous or not, share a single packet).
 */
export function groupSegments(colors: readonly RGB[]): SegmentGroup[] {
  const byColour = new Map<string, SegmentGroup>();
  const order: SegmentGroup[] = [];
  colors.forEach((rgb, i) => {
    const key = `${rgb[0]},${rgb[1]},${rgb[2]}`;
    let group = byColour.get(key);
    if (group === undefined) {
      group = { segments: [], rgb_color: [rgb[0], rgb[1], rgb[2]] };
      byColour.set(key, group);
      order.push(group);
    }
    group.segments.push(i + 1);
  });
  return order;
}

/** A named gradient or solid fill; a single stop is a solid fill. */
export interface GradientPreset {
  /** Stable identifier, used as the button key. */
  id: string;
  /** User-facing label. */
  name: string;
  /** Colour stops in `[r, g, b]`; one stop fills the whole strip. */
  stops: RGB[];
}

/** Built-in one-tap gradients and solid fills for the preset row. */
export const GRADIENT_PRESETS: readonly GradientPreset[] = [
  { id: "sunset", name: "Sunset", stops: [[255, 89, 94], [255, 146, 76], [255, 202, 58]] },
  { id: "ocean", name: "Ocean", stops: [[15, 32, 89], [25, 130, 196], [112, 193, 179]] },
  { id: "forest", name: "Forest", stops: [[27, 67, 50], [45, 106, 79], [149, 213, 178]] },
  {
    id: "rainbow",
    name: "Rainbow",
    stops: [[255, 0, 0], [255, 183, 0], [0, 200, 83], [0, 145, 234], [170, 0, 255]],
  },
  { id: "warm-white", name: "Warm white", stops: [[255, 183, 107]] },
  { id: "cool-white", name: "Cool white", stops: [[188, 220, 255]] },
];

/**
 * Resolve a preset to `paint_segments` groups by sampling its stops across
 * `count` segments (`interpolateSegments`) and collapsing equal colours
 * (`groupSegments`), so applying it repaints the whole strip in the fewest
 * writes with the same Python-parity rounding as the gradient editor.
 */
export function presetGroups(
  preset: GradientPreset,
  count: number = SEGMENT_COUNT,
): SegmentGroup[] {
  return groupSegments(interpolateSegments(preset.stops, count));
}

/** Return the selection as a sorted array of 1-based segment indices. */
export function selectionToSegments(selection: Iterable<number>): number[] {
  return [...new Set(selection)].sort((a, b) => a - b);
}

/**
 * Map 1-based segment indices to the 15-bit little-endian segment mask
 * (segment `k` -> bit `k-1`; all 15 -> `0x7FFF`).
 *
 * Mirrors `segments_to_mask` in
 * `custom_components/ha_govee_led_ble/protocol.py`, including its validation:
 * an empty selection or an out-of-range index throws.
 */
export function segmentsToMask(segments: Iterable<number>): number {
  const selected = new Set(segments);
  if (selected.size === 0) throw new Error("no segments selected");
  let mask = 0;
  for (const segment of selected) {
    if (!Number.isInteger(segment) || segment < 1 || segment > SEGMENT_COUNT) {
      throw new Error(`segment ${segment} out of range 1..${SEGMENT_COUNT}`);
    }
    mask |= 1 << (segment - 1);
  }
  return mask;
}

/**
 * Split a segment mask into its little-endian `[lo, hi]` bytes, matching the
 * on-wire order used by `build_segment_color` in `protocol.py`
 * (`lo = mask & 0xFF`, `hi = (mask >> 8) & 0xFF`).
 */
export function maskToBytes(mask: number): [number, number] {
  return [mask & 0xff, (mask >> 8) & 0xff];
}

/** Contiguous drag range: every index between `anchor` and `focus` inclusive. */
export function rangeSelection(anchor: number, focus: number): Set<number> {
  const lo = Math.min(anchor, focus);
  const hi = Math.max(anchor, focus);
  const set = new Set<number>();
  for (let i = lo; i <= hi; i++) set.add(i);
  return set;
}

/** Return a new selection with `index` toggled (non-contiguous editing). */
export function toggleSegment(
  selection: ReadonlySet<number>,
  index: number,
): Set<number> {
  const next = new Set(selection);
  if (next.has(index)) next.delete(index);
  else next.add(index);
  return next;
}

/** Select every segment `1..count`. */
export function selectAll(count: number = SEGMENT_COUNT): Set<number> {
  const set = new Set<number>();
  for (let i = 1; i <= count; i++) set.add(i);
  return set;
}

/** An empty selection. */
export function clearSelection(): Set<number> {
  return new Set<number>();
}

/** A saved custom effect, as surfaced by the light's `custom_effects` attribute. */
export interface CustomEffectEntry {
  /** Stable effect id, used to rename/delete a specific effect. */
  id: string;
  /** User-facing display name. */
  name: string;
}

/**
 * Coerce the light's `custom_effects` attribute (an `id -> display name` map)
 * into a display-ordered `{ id, name }` list. Non-string or blank names are
 * dropped and names are trimmed; the result is sorted by name
 * (case-insensitive, ties broken by id) so the card's list order is stable
 * regardless of object-key order. A non-object (or array) yields an empty list.
 */
export function coerceCustomEffects(raw: unknown): CustomEffectEntry[] {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return [];
  const out: CustomEffectEntry[] = [];
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== "string") continue;
    const name = value.trim();
    if (name === "") continue;
    out.push({ id, name });
  }
  out.sort((a, b) => {
    const an = a.name.toLowerCase();
    const bn = b.name.toLowerCase();
    if (an !== bn) return an < bn ? -1 : 1;
    if (a.id !== b.id) return a.id < b.id ? -1 : 1;
    return 0;
  });
  return out;
}

// --- Studio shell: tabs and kinds ---------------------------------------

/** The three top-level workspaces of the card. */
export type TabId = "now" | "studio" | "library";

/** Ordered tab descriptors driving the card's `role="tablist"`. */
export const TABS: readonly { id: TabId; label: string }[] = [
  { id: "now", label: "Now" },
  { id: "studio", label: "Studio" },
  { id: "library", label: "Library" },
];

/**
 * Resolve a roving-tabindex keyboard event to the next tab index:
 * `ArrowRight`/`ArrowDown` step forward, `ArrowLeft`/`ArrowUp` step back (both
 * wrap), `Home`/`End` jump to the ends. Any other key returns `current`.
 */
export function nextTabIndex(current: number, key: string, count: number): number {
  if (count <= 0) return current;
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return (current + 1) % count;
    case "ArrowLeft":
    case "ArrowUp":
      return (current - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return current;
  }
}

/** The five authorable effect kinds in the Studio. */
export type StudioKind = "static" | "gradient" | "sketch" | "flat" | "combo";

/**
 * Studio kind descriptors. `available` gates kinds whose complete authoring
 * surface has landed.
 */
export const STUDIO_KINDS: readonly { id: StudioKind; label: string; available: boolean }[] = [
  { id: "static", label: "Static", available: true },
  { id: "gradient", label: "Gradient", available: true },
  { id: "sketch", label: "Sketch", available: true },
  { id: "flat", label: "Flat", available: true },
  { id: "combo", label: "Combo", available: true },
];

// --- Studio: typed content builders (twins of custom_effects.content_from_dict) ---

/** JSON shape of a `SegmentContent` effect, as `save_effect(content=)` expects. */
export interface SegmentContentDict {
  kind: "segments";
  colors: (RGB | null)[];
  brightness: (number | null)[] | null;
}

/** JSON shape of a `VibrantContent` (gradient) effect. */
export interface VibrantContentDict {
  kind: "vibrant";
  stops: RGB[];
}

/**
 * Build a `segments` content dict from a per-segment draft. A `null` colour
 * means "leave this segment unchanged"; `[0,0,0]` means "off" — the two stay
 * distinct. `brightness` collapses to `null` when every entry is `null`, so an
 * unset brightness track is omitted rather than sent as all-null.
 */
export function buildSegmentContent(
  colors: readonly (RGB | null)[],
  brightness: readonly (number | null)[] | null = null,
): SegmentContentDict {
  const hasBrightness = brightness !== null && brightness.some((b) => b !== null);
  return {
    kind: "segments",
    colors: colors.map((c) => (c === null ? null : [c[0], c[1], c[2]])),
    brightness: hasBrightness ? brightness.map((b) => (b === null ? null : b)) : null,
  };
}

/** True when a Static draft carries at least one painted colour or brightness. */
export function segmentDraftHasContent(
  colors: readonly (RGB | null)[],
  brightness: readonly (number | null)[] | null = null,
): boolean {
  return (
    colors.some((c) => c !== null) ||
    (brightness !== null && brightness.some((b) => b !== null))
  );
}

/** Build a `vibrant` (gradient) content dict from ordered colour stops. */
export function buildVibrantContent(stops: readonly RGB[]): VibrantContentDict {
  return { kind: "vibrant", stops: stops.map((s) => [s[0], s[1], s[2]]) };
}

/** Read a non-blank `message` string off an object, or null. */
function messageOf(value: unknown): string | null {
  if (value !== null && typeof value === "object") {
    const message = (value as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim() !== "") return message;
  }
  return null;
}

/**
 * Extract a human-readable message from a rejected `hass.callService` promise.
 *
 * Home Assistant rejects service calls with a translated `ServiceValidationError`
 * whose text is carried on `.message` (websocket errors may nest it under
 * `.error.message`, REST errors under `.body.message`). Falls back to `fallback`
 * when no usable message string is present.
 */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (typeof err === "string" && err.trim() !== "") return err;
  const direct = messageOf(err);
  if (direct !== null) return direct;
  if (err !== null && typeof err === "object") {
    const record = err as Record<string, unknown>;
    const nested = messageOf(record.error) ?? messageOf(record.body);
    if (nested !== null) return nested;
  }
  return fallback;
}
