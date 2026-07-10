import { describe, it, expect } from "vitest";
import {
  ALL_SEGMENTS_MASK,
  SEGMENT_COUNT,
  clamp,
  clearSelection,
  groupSegments,
  hexToRgb,
  interpolateSegments,
  maskToBytes,
  pyRound,
  rangeSelection,
  rgbToHex,
  sampleStops,
  segmentsToMask,
  selectAll,
  selectionToSegments,
  toggleSegment,
  type RGB,
  type SegmentGroup,
} from "../src/logic";

describe("clamp", () => {
  it("clamps below, within, and above", () => {
    expect(clamp(-5, 0, 255)).toBe(0);
    expect(clamp(128, 0, 255)).toBe(128);
    expect(clamp(300, 0, 255)).toBe(255);
  });
});

describe("hexToRgb / rgbToHex", () => {
  it("parses hex with and without a leading '#'", () => {
    expect(hexToRgb("#33cc66")).toEqual([51, 204, 102]);
    expect(hexToRgb("33cc66")).toEqual([51, 204, 102]);
  });

  it("formats an rgb triple as lowercase #rrggbb", () => {
    expect(rgbToHex([51, 204, 102])).toBe("#33cc66");
    expect(rgbToHex([0, 0, 0])).toBe("#000000");
    expect(rgbToHex([255, 255, 255])).toBe("#ffffff");
  });

  it("clamps and rounds out-of-range channels", () => {
    expect(rgbToHex([-5, 300, 127.6])).toBe("#00ff80");
  });

  it("round-trips integer colours", () => {
    for (const hex of ["#000000", "#ffffff", "#33cc66", "#ff595e", "#1982c4"]) {
      expect(rgbToHex(hexToRgb(hex))).toBe(hex);
    }
  });
});

describe("sampleStops", () => {
  it("returns the single stop unchanged (as a copy)", () => {
    const stops: RGB[] = [[10, 20, 30]];
    expect(sampleStops(stops, 0)).toEqual([10, 20, 30]);
    expect(sampleStops(stops, 1)).toEqual([10, 20, 30]);
    expect(sampleStops(stops, 0.5)).not.toBe(stops[0]);
  });

  it("hits the endpoints exactly", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [100, 100, 100],
      [200, 200, 200],
    ];
    expect(sampleStops(stops, 0)).toEqual([0, 0, 0]);
    expect(sampleStops(stops, 1)).toEqual([200, 200, 200]);
  });

  it("interpolates midpoints", () => {
    const two: RGB[] = [
      [0, 0, 0],
      [255, 255, 255],
    ];
    expect(sampleStops(two, 0.5)).toEqual([127.5, 127.5, 127.5]);

    const three: RGB[] = [
      [0, 0, 0],
      [100, 100, 100],
      [200, 200, 200],
    ];
    expect(sampleStops(three, 0.5)).toEqual([100, 100, 100]);
    expect(sampleStops(three, 0.25)).toEqual([50, 50, 50]);
    expect(sampleStops(three, 0.75)).toEqual([150, 150, 150]);
  });

  it("clamps t outside [0, 1]", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [200, 200, 200],
    ];
    expect(sampleStops(stops, -1)).toEqual([0, 0, 0]);
    expect(sampleStops(stops, 5)).toEqual([200, 200, 200]);
  });

  it("throws on an empty stop list", () => {
    expect(() => sampleStops([], 0)).toThrow();
  });
});

describe("pyRound", () => {
  it("rounds fractions below/above the half toward the nearest integer", () => {
    expect(pyRound(126.4)).toBe(126);
    expect(pyRound(126.6)).toBe(127);
    expect(pyRound(0.2)).toBe(0);
    expect(pyRound(9.99)).toBe(10);
  });

  it("breaks exact halves toward even (banker's rounding)", () => {
    expect(pyRound(0.5)).toBe(0);
    expect(pyRound(1.5)).toBe(2);
    expect(pyRound(2.5)).toBe(2);
    expect(pyRound(126.5)).toBe(126);
    expect(pyRound(127.5)).toBe(128);
  });

  it("is a no-op on integers", () => {
    for (const n of [0, 1, 42, 200, 255]) expect(pyRound(n)).toBe(n);
  });
});

// Numeric parity with the Python reference `_interpolate` (services.py).
// Expected arrays are the exact output of that function, captured from
// CPython, for `count = 15` (and 5 for the single-stop case).
describe("interpolateSegments", () => {
  it("throws on an empty stop list", () => {
    expect(() => interpolateSegments([], 15)).toThrow();
  });

  it("defaults to SEGMENT_COUNT segments", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [255, 255, 255],
    ];
    expect(interpolateSegments(stops)).toHaveLength(SEGMENT_COUNT);
  });

  it("fills every segment with a lone stop", () => {
    const out = interpolateSegments([[10, 20, 30]], 15);
    expect(out).toHaveLength(15);
    for (const seg of out) expect(seg).toEqual([10, 20, 30]);
  });

  it("matches the Python _interpolate reference (2 stops, integer step)", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [140, 140, 140],
    ];
    const expected: RGB[] = Array.from(
      { length: 15 },
      (_unused, i) => [10 * i, 10 * i, 10 * i] as RGB,
    );
    expect(interpolateSegments(stops, 15)).toEqual(expected);
  });

  it("matches the Python _interpolate reference (3 symmetric stops)", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [100, 100, 100],
      [200, 200, 200],
    ];
    const expected: RGB[] = [
      [0, 0, 0],
      [14, 14, 14],
      [29, 29, 29],
      [43, 43, 43],
      [57, 57, 57],
      [71, 71, 71],
      [86, 86, 86],
      [100, 100, 100],
      [114, 114, 114],
      [129, 129, 129],
      [143, 143, 143],
      [157, 157, 157],
      [171, 171, 171],
      [186, 186, 186],
      [200, 200, 200],
    ];
    expect(interpolateSegments(stops, 15)).toEqual(expected);
  });

  it("matches the Python _interpolate reference (colourful 3 stops)", () => {
    const stops: RGB[] = [
      [255, 89, 94],
      [255, 202, 58],
      [25, 130, 196],
    ];
    const expected: RGB[] = [
      [255, 89, 94],
      [255, 105, 89],
      [255, 121, 84],
      [255, 137, 79],
      [255, 154, 73],
      [255, 170, 68],
      [255, 186, 63],
      [255, 202, 58],
      [222, 192, 78],
      [189, 181, 97],
      [156, 171, 117],
      [124, 161, 137],
      [91, 151, 157],
      [58, 140, 176],
      [25, 130, 196],
    ];
    expect(interpolateSegments(stops, 15)).toEqual(expected);
  });

  it("matches the Python _interpolate reference (single stop)", () => {
    const expected: RGB[] = Array.from(
      { length: 5 },
      () => [10, 20, 30] as RGB,
    );
    expect(interpolateSegments([[10, 20, 30]], 5)).toEqual(expected);
  });
});

describe("groupSegments", () => {
  it("emits one single-segment group per distinct colour", () => {
    const stops: RGB[] = [
      [0, 0, 0],
      [140, 140, 140],
    ];
    const groups = groupSegments(interpolateSegments(stops, 15));
    expect(groups).toHaveLength(15);
    for (let i = 0; i < 15; i++) {
      expect(groups[i]).toEqual({
        segments: [i + 1],
        rgb_color: [10 * i, 10 * i, 10 * i],
      });
    }
  });

  it("collapses a single colour into one group over all segments", () => {
    const groups = groupSegments(interpolateSegments([[7, 8, 9]], 15));
    expect(groups).toEqual([
      {
        segments: Array.from({ length: 15 }, (_unused, i) => i + 1),
        rgb_color: [7, 8, 9],
      },
    ]);
  });

  it("merges equal colours whether contiguous or not, using 1-based indices", () => {
    const colours: RGB[] = [
      [1, 1, 1],
      [2, 2, 2],
      [1, 1, 1],
      [2, 2, 2],
      [3, 3, 3],
    ];
    const groups: SegmentGroup[] = groupSegments(colours);
    expect(groups).toEqual([
      { segments: [1, 3], rgb_color: [1, 1, 1] },
      { segments: [2, 4], rgb_color: [2, 2, 2] },
      { segments: [5], rgb_color: [3, 3, 3] },
    ]);
  });

  it("returns an empty list for no colours", () => {
    expect(groupSegments([])).toEqual([]);
  });

  it("paints every segment exactly once, each group valid for segmentsToMask", () => {
    const stops: RGB[] = [
      [255, 89, 94],
      [255, 202, 58],
      [25, 130, 196],
    ];
    const groups = groupSegments(interpolateSegments(stops, SEGMENT_COUNT));
    const painted = groups.flatMap((g) => g.segments).sort((a, b) => a - b);
    expect(painted).toEqual(
      Array.from({ length: SEGMENT_COUNT }, (_unused, i) => i + 1),
    );
    for (const group of groups) {
      expect(() => segmentsToMask(group.segments)).not.toThrow();
    }
  });
});

describe("segmentsToMask", () => {
  it("throws on an empty selection", () => {
    expect(() => segmentsToMask([])).toThrow("no segments selected");
  });

  it("maps single segments to their bit (segment k -> bit k-1)", () => {
    expect(segmentsToMask([1])).toBe(0b1);
    expect(segmentsToMask([2])).toBe(0b10);
    expect(segmentsToMask([15])).toBe(1 << 14);
  });

  it("maps all 15 segments to 0x7FFF", () => {
    const all = Array.from({ length: SEGMENT_COUNT }, (_unused, i) => i + 1);
    expect(segmentsToMask(all)).toBe(0x7fff);
    expect(segmentsToMask(all)).toBe(ALL_SEGMENTS_MASK);
  });

  it("handles non-contiguous selections", () => {
    expect(segmentsToMask([1, 3, 5])).toBe(0b10101);
    expect(segmentsToMask([2, 4])).toBe(0b1010);
  });

  it("deduplicates repeated indices", () => {
    expect(segmentsToMask([1, 1, 1])).toBe(0b1);
  });

  it("throws on out-of-range or non-integer indices", () => {
    expect(() => segmentsToMask([0])).toThrow("out of range");
    expect(() => segmentsToMask([16])).toThrow("out of range");
    expect(() => segmentsToMask([-1])).toThrow("out of range");
    expect(() => segmentsToMask([1.5])).toThrow("out of range");
  });
});

describe("maskToBytes", () => {
  it("splits a mask into little-endian [lo, hi] bytes", () => {
    expect(maskToBytes(0x7fff)).toEqual([0xff, 0x7f]);
    expect(maskToBytes(0b1)).toEqual([1, 0]);
    expect(maskToBytes(1 << 14)).toEqual([0x00, 0x40]);
  });

  it("agrees with protocol.py's split for the all-segments mask", () => {
    const mask = segmentsToMask(
      Array.from({ length: SEGMENT_COUNT }, (_unused, i) => i + 1),
    );
    expect(maskToBytes(mask)).toEqual([0xff, 0x7f]);
  });
});

describe("selectionToSegments", () => {
  it("returns a sorted, de-duplicated 1-based list", () => {
    expect(selectionToSegments(new Set([3, 1, 2]))).toEqual([1, 2, 3]);
    expect(selectionToSegments([5, 5, 1, 10])).toEqual([1, 5, 10]);
  });
});

describe("selection reducers", () => {
  it("rangeSelection builds a contiguous inclusive range, order-independent", () => {
    expect([...rangeSelection(3, 7)]).toEqual([3, 4, 5, 6, 7]);
    expect([...rangeSelection(7, 3)]).toEqual([3, 4, 5, 6, 7]);
    expect([...rangeSelection(5, 5)]).toEqual([5]);
  });

  it("toggleSegment adds/removes without mutating the input", () => {
    const base = new Set([1, 2]);
    const added = toggleSegment(base, 3);
    expect([...added].sort((a, b) => a - b)).toEqual([1, 2, 3]);
    expect([...base].sort((a, b) => a - b)).toEqual([1, 2]);

    const removed = toggleSegment(base, 2);
    expect([...removed]).toEqual([1]);
    expect([...base].sort((a, b) => a - b)).toEqual([1, 2]);
  });

  it("selectAll selects 1..count (default SEGMENT_COUNT)", () => {
    expect([...selectAll(3)]).toEqual([1, 2, 3]);
    expect(selectAll().size).toBe(SEGMENT_COUNT);
    expect([...selectAll()]).toEqual(
      Array.from({ length: SEGMENT_COUNT }, (_unused, i) => i + 1),
    );
  });

  it("clearSelection returns an empty set", () => {
    expect(clearSelection().size).toBe(0);
  });
});
