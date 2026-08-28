import { expect, test } from "vitest";

import {
  reorderableStripKeyboardAction,
  reorderableStripModel,
  reorderableStripPointerIntent,
} from "../../src/reorderable-strip-model";

test("tab and action models keep Add separate from item semantics", () => {
  expect(
    reorderableStripModel("tab", "Add layer", false, false),
  ).toEqual({
    listRole: "tablist",
    addAction: {
      label: "Add layer",
      disabled: false,
    },
  });
  expect(
    reorderableStripModel("button", "Add colour", true, false),
  ).toEqual({
    listRole: undefined,
    addAction: {
      label: "Add colour",
      disabled: true,
    },
  });
  expect(
    reorderableStripModel("tab", "Add pattern", false, true),
  ).toEqual({
    listRole: "tablist",
    addAction: undefined,
  });
});

test("keyboard actions calculate adjacent reorder targets", () => {
  expect(
    reorderableStripKeyboardAction(0, "ArrowRight", 2, false, "tab"),
  ).toEqual({
    kind: "reorder",
    from: 0,
    to: 1,
    focusIndex: 1,
  });
  expect(
    reorderableStripKeyboardAction(1, "ArrowLeft", 2, false, "button"),
  ).toEqual({
    kind: "reorder",
    from: 1,
    to: 0,
    focusIndex: 0,
  });
  expect(
    reorderableStripKeyboardAction(0, "ArrowLeft", 2, false, "tab"),
  ).toBeUndefined();
  expect(
    reorderableStripKeyboardAction(1, "ArrowRight", 2, false, "tab"),
  ).toBeUndefined();
  expect(
    reorderableStripKeyboardAction(0, "Enter", 2, false, "tab"),
  ).toBeUndefined();
});

test("non-reorderable tabs select while buttons ignore arrow keys", () => {
  expect(
    reorderableStripKeyboardAction(0, "ArrowRight", 2, true, "tab"),
  ).toEqual({
    kind: "select",
    index: 1,
    focusIndex: 1,
  });
  expect(
    reorderableStripKeyboardAction(
      0,
      "ArrowRight",
      2,
      true,
      "button",
    ),
  ).toBeUndefined();
});

test("pointer intent distinguishes taps, scrolling, and reordering", () => {
  expect(reorderableStripPointerIntent(4, 5, false)).toBe("pending");
  expect(reorderableStripPointerIntent(9, 0, false)).toBe("pending");
  expect(reorderableStripPointerIntent(4, 12, false)).toBe("cancel");
  expect(reorderableStripPointerIntent(12, 4, false)).toBe("reorder");
  expect(reorderableStripPointerIntent(12, 4, true)).toBe("cancel");
});
