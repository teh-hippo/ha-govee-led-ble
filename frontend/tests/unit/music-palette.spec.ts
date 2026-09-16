import { describe, expect, it } from "vitest";
import { decodeEffectContent } from "../../src/validation";
import { decodeMusicSettings, decodeCustomCataloguePayload } from "../../src/catalogue-validation";
import { cloneMusicProfileContent } from "../../src/profile-model";
import { effectContentEligible } from "../../src/effect-editor-model";
import type { MusicProfileContent } from "../../src/types";
import contracts from "../fixtures/backend-contracts.json";

const content: MusicProfileContent = {
  kind: "music_profile", model: "H617A", mode: "bloom", sensitivity: 42,
  colour: null, calm: null, parameters: {},
};

describe("optional music palette", () => {
  it("preserves absent documents and independently clones authored colours", () => {
    expect(decodeEffectContent(content)).toEqual(content);
    expect(cloneMusicProfileContent(content)).not.toHaveProperty("palette");
    const authored: MusicProfileContent = {...content, palette: [[12, 34, 56]]};
    expect(decodeEffectContent(authored)).toEqual(authored);
    const clone = cloneMusicProfileContent(authored);
    clone.palette![0][0] = 255;
    expect(authored.palette).toEqual([[12, 34, 56]]);
  });

  it.each([null, [], [[true, 2, 3]], [[-1, 2, 3]], [[256, 2, 3]], [[1, 2]], Array(9).fill([1, 2, 3])])(
    "rejects malformed palette %j", palette => {
      expect(() => decodeEffectContent({...content, palette})).toThrow();
    },
  );

  it("uses device-qualified palette availability and bounds", () => {
    const catalogue = decodeCustomCataloguePayload(contracts.responses.custom_catalogue, decodeEffectContent).models.H617A;
    catalogue.music_modes = [{id: "bloom", label: "Bloom"}];
    const authored: MusicProfileContent = {...content, palette: [[12, 34, 56]]};
    expect(effectContentEligible(authored, catalogue, "H617A", 15)).toBe(true);
    delete catalogue.music_settings.bloom.palette;
    expect(effectContentEligible(authored, catalogue, "H617A", 15)).toBe(false);
    catalogue.music_settings.bloom.palette = {min: 1, max: 8, default: [[12, 34, 56]]};
    expect(decodeMusicSettings(catalogue.music_settings).bloom.palette).toEqual(catalogue.music_settings.bloom.palette);
    expect(effectContentEligible(authored, catalogue, "H617A", 15)).toBe(true);
    expect(effectContentEligible({...authored, palette: Array(9).fill([1, 2, 3])}, catalogue, "H617A", 15)).toBe(false);
    catalogue.music_settings.bloom.palette.default = [];
    expect(() => decodeMusicSettings(catalogue.music_settings)).toThrow();
  });
});
