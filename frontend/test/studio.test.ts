import { describe, it, expect } from "vitest";
import {
  buildSegmentContent,
  buildVibrantContent,
  nextTabIndex,
  segmentDraftHasContent,
  STUDIO_KINDS,
  TABS,
  type RGB,
} from "../src/logic";

describe("TABS / STUDIO_KINDS", () => {
  it("exposes the three workspaces in order", () => {
    expect(TABS.map((t) => t.id)).toEqual(["now", "studio", "library"]);
  });

  it("marks only Static and Gradient available in cycle 1", () => {
    const available = STUDIO_KINDS.filter((k) => k.available).map((k) => k.id);
    expect(available).toEqual(["static", "gradient"]);
    expect(STUDIO_KINDS.map((k) => k.id)).toEqual([
      "static",
      "gradient",
      "sketch",
      "flat",
      "combo",
    ]);
  });
});

describe("nextTabIndex", () => {
  it("steps forward and wraps on ArrowRight/ArrowDown", () => {
    expect(nextTabIndex(0, "ArrowRight", 3)).toBe(1);
    expect(nextTabIndex(2, "ArrowRight", 3)).toBe(0);
    expect(nextTabIndex(1, "ArrowDown", 3)).toBe(2);
  });

  it("steps back and wraps on ArrowLeft/ArrowUp", () => {
    expect(nextTabIndex(1, "ArrowLeft", 3)).toBe(0);
    expect(nextTabIndex(0, "ArrowLeft", 3)).toBe(2);
    expect(nextTabIndex(2, "ArrowUp", 3)).toBe(1);
  });

  it("jumps to the ends on Home/End", () => {
    expect(nextTabIndex(2, "Home", 3)).toBe(0);
    expect(nextTabIndex(0, "End", 3)).toBe(2);
  });

  it("returns the current index for any other key or empty tablist", () => {
    expect(nextTabIndex(1, "Enter", 3)).toBe(1);
    expect(nextTabIndex(1, "a", 3)).toBe(1);
    expect(nextTabIndex(1, "ArrowRight", 0)).toBe(1);
  });
});

describe("buildSegmentContent", () => {
  it("maps a sparse draft to a segments dict, preserving unchanged nulls", () => {
    const red: RGB = [255, 0, 0];
    const black: RGB = [0, 0, 0];
    expect(buildSegmentContent([red, null, black])).toEqual({
      kind: "segments",
      colors: [[255, 0, 0], null, [0, 0, 0]],
      brightness: null,
    });
  });

  it("keeps 'off' (black) distinct from 'unchanged' (null)", () => {
    const result = buildSegmentContent([[0, 0, 0], null]);
    expect(result.colors[0]).toEqual([0, 0, 0]);
    expect(result.colors[1]).toBeNull();
  });

  it("collapses an all-null brightness track to null", () => {
    expect(buildSegmentContent([[1, 2, 3]], [null, null]).brightness).toBeNull();
  });

  it("keeps a brightness track with any set value", () => {
    expect(buildSegmentContent([[1, 2, 3]], [50, null]).brightness).toEqual([50, null]);
  });
});

describe("segmentDraftHasContent", () => {
  it("is false for an all-unchanged draft", () => {
    expect(segmentDraftHasContent([null, null, null])).toBe(false);
    expect(segmentDraftHasContent([null], [null])).toBe(false);
  });

  it("is true once any segment carries colour or brightness", () => {
    expect(segmentDraftHasContent([null, [0, 0, 0]])).toBe(true);
    expect(segmentDraftHasContent([null], [10])).toBe(true);
  });
});

describe("buildVibrantContent", () => {
  it("maps ordered stops to a vibrant dict", () => {
    expect(
      buildVibrantContent([
        [255, 89, 94],
        [25, 130, 196],
      ]),
    ).toEqual({
      kind: "vibrant",
      stops: [
        [255, 89, 94],
        [25, 130, 196],
      ],
    });
  });
});
