import { describe, it, expect } from "vitest";
import {
  coerceCustomEffects,
  errorMessage,
  type CustomEffectEntry,
} from "../src/logic";

describe("coerceCustomEffects", () => {
  it("maps an id -> name record to sorted { id, name } entries", () => {
    const entries: CustomEffectEntry[] = coerceCustomEffects({
      b2: "Ocean",
      a1: "Sunset",
      c3: "forest",
    });
    expect(entries).toEqual([
      { id: "c3", name: "forest" },
      { id: "b2", name: "Ocean" },
      { id: "a1", name: "Sunset" },
    ]);
  });

  it("sorts case-insensitively, breaking name ties by id", () => {
    expect(
      coerceCustomEffects({ z9: "Glow", a1: "glow", m5: "GLOW" }),
    ).toEqual([
      { id: "a1", name: "glow" },
      { id: "m5", name: "GLOW" },
      { id: "z9", name: "Glow" },
    ]);
  });

  it("trims names and drops blank or non-string values", () => {
    expect(
      coerceCustomEffects({
        keep: "  Dawn  ",
        blank: "   ",
        empty: "",
        num: 42,
        nil: null,
      }),
    ).toEqual([{ id: "keep", name: "Dawn" }]);
  });

  it("returns an empty list for non-object, array, or null input", () => {
    expect(coerceCustomEffects(null)).toEqual([]);
    expect(coerceCustomEffects(undefined)).toEqual([]);
    expect(coerceCustomEffects("Sunset")).toEqual([]);
    expect(coerceCustomEffects(["Sunset"])).toEqual([]);
    expect(coerceCustomEffects({})).toEqual([]);
  });
});

describe("errorMessage", () => {
  it("returns a non-blank string error verbatim", () => {
    expect(errorMessage("An effect with that name already exists.")).toBe(
      "An effect with that name already exists.",
    );
  });

  it("reads the translated `.message` off a ServiceValidationError-like object", () => {
    expect(
      errorMessage({
        code: "service_validation_error",
        message: "That name matches a built-in scene. Choose a different name.",
      }),
    ).toBe("That name matches a built-in scene. Choose a different name.");
  });

  it("falls back to a nested error.message then body.message", () => {
    expect(errorMessage({ error: { message: "Provide a non-empty effect name." } })).toBe(
      "Provide a non-empty effect name.",
    );
    expect(errorMessage({ body: { message: "Unknown effect \"x\"." } })).toBe(
      'Unknown effect "x".',
    );
  });

  it("uses the fallback for empty, blank, or messageless inputs", () => {
    expect(errorMessage(null)).toBe("Something went wrong.");
    expect(errorMessage("")).toBe("Something went wrong.");
    expect(errorMessage("   ")).toBe("Something went wrong.");
    expect(errorMessage({ code: "x" })).toBe("Something went wrong.");
    expect(errorMessage({ message: "  " })).toBe("Something went wrong.");
    expect(errorMessage({}, "Custom fallback")).toBe("Custom fallback");
  });
});
