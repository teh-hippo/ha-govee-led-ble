import { describe, it, expect } from "vitest";
import {
  GRADIENT_PRESETS,
  SEGMENT_COUNT,
  groupSegments,
  interpolateSegments,
  presetGroups,
  segmentsToMask,
  type RGB,
} from "../src/logic";

const ALL_SEGMENTS = Array.from({ length: SEGMENT_COUNT }, (_unused, i) => i + 1);

// Canonical example from the task: a two-stop red -> blue gradient sampled
// across 15 segments. Expected values are the exact CPython round() output of
// the reference interpolation, so this asserts channel-for-channel parity.
describe("interpolateSegments — two-stop red -> blue across 15 segments", () => {
  it("matches the Python reference channel-for-channel", () => {
    const expected: RGB[] = [
      [255, 0, 0],
      [237, 0, 18],
      [219, 0, 36],
      [200, 0, 55],
      [182, 0, 73],
      [164, 0, 91],
      [146, 0, 109],
      [128, 0, 128],
      [109, 0, 146],
      [91, 0, 164],
      [73, 0, 182],
      [55, 0, 200],
      [36, 0, 219],
      [18, 0, 237],
      [0, 0, 255],
    ];
    expect(
      interpolateSegments(
        [
          [255, 0, 0],
          [0, 0, 255],
        ],
        SEGMENT_COUNT,
      ),
    ).toEqual(expected);
  });
});

describe("GRADIENT_PRESETS", () => {
  it("has unique ids, a non-empty name, and at least one stop each", () => {
    const ids = GRADIENT_PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const preset of GRADIENT_PRESETS) {
      expect(preset.name.trim()).not.toBe("");
      expect(preset.stops.length).toBeGreaterThanOrEqual(1);
      for (const [r, g, b] of preset.stops) {
        for (const channel of [r, g, b]) {
          expect(Number.isInteger(channel)).toBe(true);
          expect(channel).toBeGreaterThanOrEqual(0);
          expect(channel).toBeLessThanOrEqual(255);
        }
      }
    }
  });

  it("ships at least one solid fill and one multi-stop gradient", () => {
    expect(GRADIENT_PRESETS.some((p) => p.stops.length === 1)).toBe(true);
    expect(GRADIENT_PRESETS.some((p) => p.stops.length > 1)).toBe(true);
  });
});

describe("presetGroups", () => {
  it("equals groupSegments(interpolateSegments(stops)) for every preset", () => {
    for (const preset of GRADIENT_PRESETS) {
      expect(presetGroups(preset)).toEqual(
        groupSegments(interpolateSegments(preset.stops, SEGMENT_COUNT)),
      );
    }
  });

  it("paints every segment exactly once, each group valid for segmentsToMask", () => {
    for (const preset of GRADIENT_PRESETS) {
      const groups = presetGroups(preset);
      const painted = groups.flatMap((g) => g.segments).sort((a, b) => a - b);
      expect(painted).toEqual(ALL_SEGMENTS);
      for (const group of groups) {
        expect(() => segmentsToMask(group.segments)).not.toThrow();
      }
    }
  });

  it("collapses a solid-fill preset into one group over all segments", () => {
    const solid = GRADIENT_PRESETS.find((p) => p.stops.length === 1);
    expect(solid).toBeDefined();
    const groups = presetGroups(solid!);
    expect(groups).toEqual([
      { segments: ALL_SEGMENTS, rgb_color: solid!.stops[0] },
    ]);
  });

  it("resolves the Sunset preset to the exact CPython per-segment groups", () => {
    const sunset = GRADIENT_PRESETS.find((p) => p.id === "sunset");
    expect(sunset).toBeDefined();
    const expected: RGB[] = [
      [255, 89, 94],
      [255, 97, 91],
      [255, 105, 89],
      [255, 113, 86],
      [255, 122, 84],
      [255, 130, 81],
      [255, 138, 79],
      [255, 146, 76],
      [255, 154, 73],
      [255, 162, 71],
      [255, 170, 68],
      [255, 178, 66],
      [255, 186, 63],
      [255, 194, 61],
      [255, 202, 58],
    ];
    expect(presetGroups(sunset!)).toEqual(
      expected.map((rgb, i) => ({ segments: [i + 1], rgb_color: rgb })),
    );
  });
});
