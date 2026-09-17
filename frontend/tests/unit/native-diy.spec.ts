import { expect, test } from "vitest";
import { blankLayer, cloneAdvancedContent, layerBrightness, nativeDiyPalette, selectionQuantity, updateNativeDiy, withLayerBrightness, withSelectionQuantity } from "../../src/advanced-effect-model";
import { AdvancedEffectEditorController } from "../../src/advanced-effect-editor-controller";
import type { AdvancedContent, RGB } from "../../src/types";
import { decodeCatalogueTemplateDefaultDetail, decodeEffectContent } from "../../src/validation";
import { decodeCustomCataloguePayload } from "../../src/catalogue-validation";
import { buildCustomEffectEntries } from "../../src/custom-effect-list";
import backendContracts from "../fixtures/backend-contracts.json";

test("APK Meteor Shower 3/1/1 seed preserves every original slot on same-length edits", () => {
  const template = backendContracts.responses.custom_catalogue.models.H617A.templates.find(
    (template) => template.id === "template:native-diy:504",
  )!;
  const content = decodeEffectContent(template.content) as AdvancedContent;
  expect(content.layers.map(layer => layer.palette)).toEqual([
    [[255, 0, 0], [0, 0, 255], [255, 123, 255]],
    [[0, 255, 0]],
    [[245, 0, 255]],
  ]);
  const original = structuredClone(content);
  const palette = nativeDiyPalette(content);
  expect(updateNativeDiy(content, { palette })).toEqual(content);
  const slots = [[0, 0], [1, 0], [2, 0], [0, 1], [0, 2]];
  slots.forEach(([layer, slot], position) => {
    const changed = palette.map(rgb => [...rgb] as RGB);
    changed[position] = [17, 34, 51];
    const expected = structuredClone(content);
    expected.layers[layer].palette[slot] = changed[position];
    const edited = updateNativeDiy(content, { palette: changed });
    expect(edited).toEqual(expected);
    expect(nativeDiyPalette(edited)).toEqual(changed);
    changed[position][0] = 99;
    expect(edited.layers[layer].palette[slot]).toEqual([17, 34, 51]);
  });
  expect(content).toEqual(original);
  const longer: RGB[] = [...palette, [12, 34, 56]];
  const resized = updateNativeDiy(content, { palette: longer });
  expect(resized.layers.map(layer => layer.palette)).toEqual([
    [longer[0], longer[3]], [longer[1], longer[4]], [longer[2], longer[5]],
  ]);
  expect(nativeDiyPalette(resized)).toEqual(longer);
});

test("native DIY catalogue entries reach the existing template loader keys", () => {
  const payload = structuredClone(backendContracts.responses.custom_catalogue);
  const templates = Array.from({ length: 7 }, (_, index) => ({
    id: `template:native-diy:${501 + index}`, label: `Native ${501 + index}`, category: "advanced",
    content: { kind: "advanced", native_diy: 501 + index, layers: [blankLayer()] },
  }));
  Object.assign(payload.models.H617A, { templates });
  Object.assign(payload, { templates });
  const catalogue = decodeCustomCataloguePayload(payload, decodeEffectContent).models.H617A;
  const entries = buildCustomEffectEntries({ model: "H617A", catalogue, libraryItems: [] }, "advanced");
  expect(entries.map(entry => entry.key)).toEqual(templates.map(template => template.id));
  expect(entries.every(entry => entry.kind === "native-diy")).toBe(true);
});

test("canonical packed controls preserve siblings, BE high byte, and extension bits", () => {
  const layer = blankLayer();
  layer.unknown_flags = 0x21;
  layer.brightness_gradient = true;
  expect(layerBrightness(layer)).toEqual({ algorithm: 2, type: 3 });
  Object.assign(layer, withLayerBrightness(layer, { algorithm: 1 }));
  expect(layerBrightness(layer)).toEqual({ algorithm: 1, type: 3 });
  Object.assign(layer, withLayerBrightness(layer, { type: 0 }));
  expect(layerBrightness(layer)).toEqual({ algorithm: 1, type: 0 });
  expect(withSelectionQuantity(0x1234)).toEqual({ param_1: 0x12, param_2: 0x34 });
  expect(selectionQuantity({ type: 0, ...withSelectionQuantity(0x1234) })).toBe(0x1234);
  layer.distribution.method = 0x72;
  const content: AdvancedContent = { kind: "advanced", native_diy: 507, layers: [layer, blankLayer()] };
  const controller = new AdvancedEffectEditorController();
  controller.sync(content, false);
  const edited = controller.updateNested("distribution", { method: 3 })!;
  expect(edited.native_diy).toBe(507);
  expect(edited.layers[0].distribution).toEqual({ method: 3, extensions: 0x70, backwards: false });
  expect(cloneAdvancedContent(edited)).toEqual(edited);
  expect(decodeEffectContent(edited)).toEqual(edited);
  expect(decodeCatalogueTemplateDefaultDetail({ template_id: "template:native-diy:507",
    content: edited, catalogue_content: content, has_default: true }).content).toEqual(edited);
  expect(edited.layers[1]).toEqual(content.layers[1]);
});

test("all seven named edits retain identity and follow APK producers", () => {
  const colours: RGB[] = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]];
  for (const code of [501, 502, 503, 504, 505, 506, 507]) {
    const count = [3, 2, 1, 3, 2, 4, 2][code - 501];
    const content: AdvancedContent = { kind: "advanced", native_diy: code, layers: Array.from({ length: count }, blankLayer) };
    if (code === 506) content.layers[2].area.width_tenths = 5;
    const edited = updateNativeDiy(content, { palette: colours });
    expect(edited.native_diy).toBe(code);
    expect(nativeDiyPalette(edited)).toEqual(colours);
    expect(content.layers[0].palette).not.toEqual(colours);
  }
  const stack: AdvancedContent = { kind: "advanced", native_diy: 507, layers: [blankLayer(), blankLayer()] };
  const edited = updateNativeDiy(stack, { brightness: 140, direction: 0, secondary: colours });
  expect(edited.layers.map(layer => layer.selected_movement.direction)).toEqual([2, 0]);
  expect(edited.layers.map(layer => layer.brightness_patterns[0].scope_low)).toEqual([140, 140]);
  expect(nativeDiyPalette(edited, true)).toEqual(colours);
});

test("physical IC controls fail closed while independent colours remain editable", () => {
  const sky: AdvancedContent = { kind: "advanced", native_diy: 502, layers: [blankLayer(), blankLayer()] };
  expect(() => updateNativeDiy(sky, { starMax: 4 })).toThrow("physical IC count");
  const edited = updateNativeDiy(sky, { starMin: 2, starMax: 25 }, 50);
  expect(edited.layers[0].selection).toEqual({ type: 2, param_1: 25, param_2: 2 });
  expect(() => updateNativeDiy(sky, { starMin: 1, starMax: 25 }, 10)).toThrow("bounds");
  const bloom: AdvancedContent = { kind: "advanced", native_diy: 506, layers: Array.from({ length: 4 }, blankLayer) };
  expect(() => updateNativeDiy(bloom, { direction: 0 })).toThrow("physical IC count");
  const directional = updateNativeDiy(bloom, { direction: 2 }, 520);
  expect(directional.layers.slice(2).map(layer => selectionQuantity(layer.selection))).toEqual([260, 260]);
  expect(directional.layers.slice(2).map(layer => layer.area)).toEqual([
    { start_tenths: 0, width_tenths: 5 }, { start_tenths: 5, width_tenths: 5 },
  ]);
});
