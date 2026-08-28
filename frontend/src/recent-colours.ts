import type { RGB } from "./types";
import { clonePalette, rgbToHex } from "./ui-utils";

const RECENT_COLOUR_LIMIT = 17;
const RECENT_COLOURS_STORAGE_KEY =
  "ha_govee_led_ble/effect_studio/recent_colours";
const DEFAULT_RECENT_COLOURS: RGB[] = [
  [255, 69, 58],
  [255, 159, 10],
  [255, 214, 10],
  [48, 209, 88],
  [99, 230, 226],
  [100, 210, 255],
  [10, 132, 255],
  [94, 92, 230],
  [191, 90, 242],
  [255, 45, 85],
  [172, 142, 104],
  [255, 255, 255],
  [174, 174, 178],
  [99, 99, 102],
  [28, 28, 30],
  [255, 127, 0],
  [139, 0, 255],
];
let recentColours = loadRecentColours();

export function recentColour(index: number): RGB {
  return [...recentColours[index % recentColours.length]];
}

export function recentColourPalette(): RGB[] {
  return clonePalette(recentColours);
}

export function rememberRecentColour(colour: RGB): void {
  const hex = rgbToHex(colour);
  recentColours = fillRecentColours([
    [...colour],
    ...recentColours.filter((recent) => rgbToHex(recent) !== hex),
  ]);
  localStorage.setItem(
    RECENT_COLOURS_STORAGE_KEY,
    JSON.stringify(recentColours),
  );
}

function loadRecentColours(): RGB[] {
  const stored = localStorage.getItem(RECENT_COLOURS_STORAGE_KEY);
  if (!stored) {
    return clonePalette(DEFAULT_RECENT_COLOURS);
  }
  let value: unknown;
  try {
    value = JSON.parse(stored);
  } catch (error) {
    if (error instanceof SyntaxError) {
      return clonePalette(DEFAULT_RECENT_COLOURS);
    }
    throw error;
  }
  if (!Array.isArray(value)) {
    return clonePalette(DEFAULT_RECENT_COLOURS);
  }
  const loaded = value
    .filter(isRGB)
    .map((colour) => [...colour] as RGB)
    .slice(0, RECENT_COLOUR_LIMIT);
  return fillRecentColours(loaded);
}

function fillRecentColours(colours: RGB[]): RGB[] {
  const filled = clonePalette(colours);
  for (const fallback of DEFAULT_RECENT_COLOURS) {
    if (
      filled.length >= RECENT_COLOUR_LIMIT ||
      filled.some((colour) => rgbToHex(colour) === rgbToHex(fallback))
    ) {
      continue;
    }
    filled.push([...fallback]);
  }
  return filled.slice(0, RECENT_COLOUR_LIMIT);
}

function isRGB(value: unknown): value is RGB {
  return (
    Array.isArray(value) &&
    value.length === 3 &&
    value.every(
      (channel) =>
        Number.isInteger(channel) && channel >= 0 && channel <= 255,
    )
  );
}
