import { expect, test } from "vitest";

import {
  arrayValue,
  assertBoundedJson,
  boundedString,
  enumString,
  integerValue,
  objectValue,
  requireUnique,
} from "../../src/payload-validation";

test("scalar and collection guards return narrowed values", () => {
  expect(boundedString("effect", "name", 10)).toBe("effect");
  expect(integerValue(4, "revision", 1, 5)).toBe(4);
  expect(enumString("one", ["one", "two"] as const, "mode")).toBe("one");
  expect(objectValue({ id: 1 }, "item")).toEqual({ id: 1 });
  expect(arrayValue([1, 2], "items", 2)).toEqual([1, 2]);
});

test("guards use the shared malformed-payload error contract", () => {
  expect(() => integerValue(1.5, "revision", 1, 5)).toThrow(
    "Malformed Effect Studio server payload: revision must be an integer from 1 to 5.",
  );
  expect(() => objectValue([], "item")).toThrow(
    "Malformed Effect Studio server payload: item must be an object.",
  );
  expect(() =>
    requireUnique(
      [{ id: "same" }, { id: "same" }],
      (item) => item.id,
      "item IDs",
    ),
  ).toThrow(
    "Malformed Effect Studio server payload: item IDs must be unique.",
  );
});

test("bounded JSON rejects oversized, unsafe, and non-JSON values", () => {
  expect(() => assertBoundedJson({ value: "long" }, "body", 4)).toThrow(
    "Malformed Effect Studio server payload: body must not exceed 4 bytes.",
  );
  expect(() => assertBoundedJson({ value: Number.NaN }, "body", 100)).toThrow(
    "Malformed Effect Studio server payload: body.value must be a finite JSON number.",
  );
  expect(() => assertBoundedJson({ value: undefined }, "body", 100)).toThrow(
    "Malformed Effect Studio server payload: body.value contains a non-JSON value.",
  );
  expect(() => assertBoundedJson([1, 2], "body", 100, 2)).toThrow(
    "Malformed Effect Studio server payload: body must not exceed 2 JSON values.",
  );
});
