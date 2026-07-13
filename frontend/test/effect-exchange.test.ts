import { describe, expect, it } from "vitest";
import {
  buildComboContent,
  buildFlatContent,
  buildSketchContent,
  buildEffectExchangeDocument,
  effectFileName,
  FLAT_CATALOGUE,
  flatFamilyByCode,
  flatVariantLabel,
  parseEffectContent,
  parseEffectExchangeJson,
  parseEntityExportResponse,
  parseEntityRawExportResponse,
  parseExportedEffect,
  normaliseEffectName,
  resolveImportName,
  studioKindForContent,
  sketchPreviewColors,
  SKETCH_MOTIONS,
  suggestDuplicateName,
} from "../src/effect-exchange";

const exported = {
  id: "a1b2c3d4",
  name: "Sunset wash",
  model: "H617A",
  segment_count: 15,
  content: {
    kind: "vibrant",
    stops: [
      [255, 89, 94],
      [255, 202, 58],
    ],
  },
};

describe("effect exchange", () => {
  it("parses a response and builds a versioned exchange document", () => {
    const effect = parseExportedEffect(exported);
    expect(buildEffectExchangeDocument(effect)).toEqual({
      schema_version: 1,
      integration: "ha_govee_led_ble",
      source: { model: "H617A", segment_count: 15 },
      effect: {
        name: "Sunset wash",
        content: exported.content,
      },
    });
  });

  it("extracts the response for the targeted entity service call", () => {
    expect(
      parseEntityExportResponse({ "light.cupboard_skirt": exported }, "light.cupboard_skirt"),
    ).toEqual(parseExportedEffect(exported));
    expect(() =>
      parseEntityExportResponse({ "light.other": exported }, "light.cupboard_skirt"),
    ).toThrow("did not include light.cupboard_skirt");
  });

  it("exports preserved future kinds opaquely while keeping editor parsing strict", () => {
    const future = {
      ...exported,
      content: { kind: "future_kind", payload: [1, 2, 3] },
    };
    const raw = parseEntityRawExportResponse(
      { "light.cupboard_skirt": future },
      "light.cupboard_skirt",
    );
    expect(buildEffectExchangeDocument(raw).effect.content).toEqual(future.content);
    expect(() =>
      parseEntityExportResponse(
        { "light.cupboard_skirt": future },
        "light.cupboard_skirt",
      ),
    ).toThrow('Unsupported effect kind "future_kind"');
  });

  it("round-trips a compatible JSON document", () => {
    const document = buildEffectExchangeDocument(parseExportedEffect(exported));
    expect(
      parseEffectExchangeJson(JSON.stringify(document), {
        model: "H617A",
        segmentCount: 15,
      }),
    ).toEqual(document);
  });

  it("rejects malformed, foreign and incompatible documents", () => {
    expect(() =>
      parseEffectExchangeJson("{", { model: "H617A", segmentCount: 15 }),
    ).toThrow("not valid JSON");
    expect(() =>
      parseEffectExchangeJson(
        JSON.stringify({ ...buildEffectExchangeDocument(parseExportedEffect(exported)), integration: "other" }),
        { model: "H617A", segmentCount: 15 },
      ),
    ).toThrow("not a Govee LED BLE effect");
    expect(() =>
      parseEffectExchangeJson(
        JSON.stringify(buildEffectExchangeDocument(parseExportedEffect(exported))),
        { model: "H6199", segmentCount: 15 },
      ),
    ).toThrow("exported for H617A");
    expect(() =>
      parseEffectExchangeJson(
        JSON.stringify(buildEffectExchangeDocument(parseExportedEffect(exported))),
        { model: "H617A", segmentCount: 12 },
      ),
    ).toThrow("needs 15 segments");
  });

  it("rejects content that cannot be rendered safely", () => {
    expect(() => parseEffectContent({ kind: "vibrant", stops: [] })).toThrow(
      "2 to 5 colours",
    );
    expect(() =>
      parseEffectContent({
        kind: "sketch",
        motion: 0,
        speed: 50,
        brightness: 50,
        background: [0, 0, 0],
        colors: [],
      }),
    ).toThrow("motion is not supported");
    expect(() =>
      parseEffectContent({
        kind: "combo",
        variant: 0,
        speed: 50,
        palette: [],
        effects: [[1, 1]],
      }),
    ).toThrow("Unknown variant");
    expect(() =>
      parseEffectContent({
        kind: "combo",
        variant: 256,
        speed: 50,
        palette: [],
        effects: [[0, 0]],
      }),
    ).toThrow("variant must be from 0 to 255");
  });

  it("parses every typed content kind and maps it to the Studio kind", () => {
    const contents = [
      { kind: "segments", colors: [[1, 2, 3], null], brightness: [50, null] },
      {
        kind: "sketch",
        motion: 9,
        speed: 51,
        brightness: 100,
        background: [0, 0, 0],
        colors: [[1, 2, 3], null],
      },
      { kind: "vibrant", stops: [[1, 2, 3], [4, 5, 6]] },
      { kind: "flat", family: 1, variant: 2, speed: 50, palette: [[1, 2, 3]] },
      {
        kind: "combo",
        variant: 0,
        speed: 50,
        palette: [[1, 2, 3]],
        effects: [[1, 2], [3, 4]],
      },
    ] as const;
    expect(contents.map((content) => studioKindForContent(parseEffectContent(content)))).toEqual([
      "static",
      "sketch",
      "gradient",
      "flat",
      "combo",
    ]);
  });

  it("chooses a unique duplicate name case-insensitively", () => {
    expect(suggestDuplicateName("Glow", ["Other"])).toBe("Glow copy");
    expect(suggestDuplicateName("Glow", ["glow COPY", "Glow copy 2"])).toBe(
      "Glow copy 3",
    );
    expect(
      suggestDuplicateName('"MY   Cool Effect"', ["My Cool Effect", "MY COOL EFFECT COPY"]),
    ).toBe("MY Cool Effect copy 2");
  });

  it("preserves an imported name unless it collides", () => {
    expect(resolveImportName("Dawn", ["Sunset"])).toBe("Dawn");
    expect(resolveImportName("Dawn", ["dawn", "Dawn copy"])).toBe("Dawn copy 2");
    expect(resolveImportName('"MY   Cool Effect"', ["My Cool Effect"])).toBe(
      "MY Cool Effect copy",
    );
    expect(normaliseEffectName(" Straße ")).toBe("strasse");
  });

  it("creates a filesystem-safe JSON name", () => {
    expect(effectFileName("  Sunset / Wash  ")).toBe("sunset-wash.json");
    expect(effectFileName("***")).toBe("govee-effect.json");
  });
});

describe("Sketch authoring", () => {
  it("exposes every validated motion with a plain-language label", () => {
    expect(SKETCH_MOTIONS).toEqual([
      { code: 0x02, label: "Cycle" },
      { code: 0x09, label: "Clockwise" },
      { code: 0x0a, label: "Counter-clockwise" },
      { code: 0x0f, label: "Twinkle" },
      { code: 0x13, label: "Gradient" },
      { code: 0x14, label: "Breathe" },
    ]);
  });

  describe("Flat catalogue", () => {
    it("contains the exact 19 accepted family/variant pairs", () => {
      expect(
        FLAT_CATALOGUE.flatMap((family) =>
          family.variants.map((variant) => [family.family, variant.variant]),
        ),
      ).toEqual([
        [0, 0], [0, 1], [0, 2],
        [1, 0], [1, 2],
        [2, 0], [2, 1], [2, 2],
        [3, 3], [3, 4], [3, 5],
        [4, 8], [4, 6], [4, 7],
        [8, 9], [8, 10],
        [9, 9], [9, 10],
        [10, 0],
      ]);
      expect(flatFamilyByCode(10).palette_max).toBe(3);
      expect(flatFamilyByCode(4).control_label).toBe("Sensitivity");
    });

    it("builds valid content and rejects invalid variants or palette sizes", () => {
      expect(buildFlatContent(3, 4, 50, [[1, 2, 3]])).toEqual({
        kind: "flat",
        family: 3,
        variant: 4,
        speed: 50,
        palette: [[1, 2, 3]],
      });
      expect(() => buildFlatContent(1, 1, 50, [[1, 2, 3]])).toThrow(
        "Unknown variant",
      );
      expect(() =>
        buildFlatContent(10, 0, 50, [
          [1, 2, 3],
          [4, 5, 6],
          [7, 8, 9],
          [10, 11, 12],
        ]),
      ).toThrow("up to 3 colours");
      expect(() => buildFlatContent(0, 0, 50, [])).toThrow(
        "at least one palette colour",
      );
    });
  });

  describe("Combo authoring", () => {
    it("builds an ordered chain with a shared palette and hidden default variant", () => {
      expect(
        buildComboContent(
          [[0, 0], [3, 4], [9, 10]],
          62,
          [[255, 0, 0], [0, 0, 255]],
          7,
        ),
      ).toEqual({
        kind: "combo",
        variant: 7,
        speed: 62,
        palette: [[255, 0, 0], [0, 0, 255]],
        effects: [[0, 0], [3, 4], [9, 10]],
      });
      expect(flatVariantLabel(1, 0)).toBe("Jumping1");
      expect(flatVariantLabel(3, 4)).toBe("Marquee2");
    });

    it("rejects empty, oversized or invalid chains and palettes", () => {
      expect(() => buildComboContent([], 50, [[1, 2, 3]])).toThrow(
        "at least one Combo step",
      );
      expect(() =>
        buildComboContent(
          [[0, 0], [0, 1], [0, 2], [1, 0], [1, 2]],
          50,
          [[1, 2, 3]],
        ),
      ).toThrow("up to four steps");
      expect(() => buildComboContent([[1, 1]], 50, [[1, 2, 3]])).toThrow(
        "Unknown variant",
      );
      expect(() => buildComboContent([[0, 0]], 50, [])).toThrow(
        "at least one palette colour",
      );
      expect(() =>
        buildComboContent([[0, 0]], 50, [[1, 2, 3]], 256),
      ).toThrow("variant must be from 0 to 255");
    });
  });

  it("builds sparse content and resolves a brightness-scaled representative preview", () => {
    const content = buildSketchContent(
      [[100, 50, 0], null],
      0x09,
      51,
      50,
      [20, 40, 60],
    );
    expect(content).toEqual({
      kind: "sketch",
      motion: 0x09,
      speed: 51,
      brightness: 50,
      background: [20, 40, 60],
      colors: [[100, 50, 0], null],
    });
    expect(sketchPreviewColors(content)).toEqual([
      [50, 25, 0],
      [10, 20, 30],
    ]);
  });
});
