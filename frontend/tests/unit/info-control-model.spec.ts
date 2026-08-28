import { expect, test } from "vitest";

import {
  anchoredPopoverLayout,
  INFO_GLYPH,
  popoverPosition,
  rectIntersectsViewport,
} from "../../src/info-control-model";

const viewport = { left: 0, top: 0, width: 400, height: 600 };

test("info glyph uses the text presentation code points", () => {
  expect([...INFO_GLYPH].map((character) => character.codePointAt(0))).toEqual([
    0x2139,
    0xfe0e,
  ]);
});

test("popover is centred below its trigger when space permits", () => {
  expect(
    popoverPosition(
      { left: 180, right: 204, top: 100, bottom: 124, width: 24, height: 24 },
      { width: 200, height: 80 },
      viewport,
      8,
      12,
    ),
  ).toEqual({ left: 92, top: 132 });
});

test("popover flips above and remains inside viewport gutters", () => {
  expect(
    popoverPosition(
      { left: 380, right: 404, top: 560, bottom: 584, width: 24, height: 24 },
      { width: 200, height: 100 },
      viewport,
      8,
      12,
    ),
  ).toEqual({ left: 188, top: 452 });
});

test("anchored popover remains below its trigger when it fits", () => {
  expect(
    anchoredPopoverLayout(
      { left: 32, right: 76, top: 400, bottom: 444, width: 44, height: 44 },
      { width: 280, height: 162 },
      { left: 0, top: 0, width: 393, height: 844 },
      8,
      12,
    ),
  ).toEqual({
    left: 12,
    top: 452,
    maxHeight: 380,
    placement: "below",
  });
});

test("anchored popover uses available height without intersecting its trigger", () => {
  const trigger = {
    left: 32,
    right: 76,
    top: 150,
    bottom: 194,
    width: 44,
    height: 44,
  };
  const layout = anchoredPopoverLayout(
    trigger,
    { width: 280, height: 162 },
    { left: 0, top: 0, width: 393, height: 330 },
    8,
    12,
  );

  expect(layout).toEqual({
    left: 12,
    top: 12,
    maxHeight: 130,
    placement: "above",
  });
  expect(layout.top + Math.min(162, layout.maxHeight)).toBeLessThan(
    trigger.top,
  );
});

test("anchored popover honours offset visual viewport gutters", () => {
  expect(
    anchoredPopoverLayout(
      { left: 370, right: 414, top: 220, bottom: 264, width: 44, height: 44 },
      { width: 280, height: 120 },
      { left: 20, top: 40, width: 400, height: 500 },
      8,
      12,
    ),
  ).toEqual({
    left: 128,
    top: 272,
    maxHeight: 256,
    placement: "below",
  });
});

test("viewport intersection includes partially visible triggers only", () => {
  expect(
    rectIntersectsViewport(
      { left: -5, right: 5, top: 10, bottom: 34, width: 10, height: 24 },
      viewport,
    ),
  ).toBe(true);
  expect(
    rectIntersectsViewport(
      { left: -25, right: -1, top: 10, bottom: 34, width: 24, height: 24 },
      viewport,
    ),
  ).toBe(false);
});
