import { expect, test } from "vitest";

import {
  AdvancedEffectEditorController,
  AUTHORING_LAYER_LIMIT,
} from "../../src/advanced-effect-editor-controller";
import {
  advancedLayerLabels,
  blankAdvancedContent,
  blankBrightnessPattern,
  blankLayer,
  installAdvancedLayerLabels,
} from "../../src/advanced-effect-model";

test("content synchronisation keeps layer and pattern selections in range", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers.push(blankLayer());
  content.layers[1].brightness_patterns.push(blankBrightnessPattern());

  controller.sync(content, false);
  expect(controller.selectLayer(1)).toBe(true);
  expect(controller.selectPattern(1)).toBe(true);
  expect(controller.activeLayerIndex).toBe(1);
  expect(controller.activePatternIndex).toBe(1);

  controller.sync(blankAdvancedContent(), false);
  expect(controller.activeLayerIndex).toBe(0);
  expect(controller.activePatternIndex).toBe(0);

  controller.sync({ kind: "advanced", layers: [] }, false);
  expect(controller.activeLayerIndex).toBe(0);
  expect(controller.activePatternIndex).toBe(0);
});

test("focused layer updates clone nested content without installing it", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers.push(blankLayer());
  controller.sync(content, false);
  controller.selectLayer(1);

  const selection = controller.updateNested("selection", {
    type: 2,
    param_1: 7,
  })!;
  const brightness = controller.updateBrightnessPattern({ scope_low: 44 })!;
  const movement = controller.updateNested("overall_movement", {
    enabled: true,
    distance: 5,
  })!;
  const distribution = controller.updateNested("distribution", {
    method: 2,
    backwards: true,
  })!;
  const area = controller.updateNested("area", { start_tenths: 4 })!;
  const palette = controller.updatePalette([[1, 2, 3]])!;

  expect(controller.isCurrentContent(selection)).toBe(false);
  expect(selection.layers[1].selection).toEqual({
    type: 2,
    param_1: 7,
    param_2: 1,
  });

  expect(brightness.layers[1].brightness_patterns[0].scope_low).toBe(44);
  expect(movement.layers[1].overall_movement).toMatchObject({
    enabled: true,
    distance: 5,
  });
  expect(distribution.layers[1].distribution).toEqual({
    method: 2,
    backwards: true,
  });
  expect(area.layers[1].area.start_tenths).toBe(4);
  expect(palette.layers[1].palette).toEqual([[1, 2, 3]]);
  expect(content.layers[1].selection.type).toBe(0);
  expect(selection.layers[0]).not.toBe(content.layers[0]);
});

test("visual edits preserve hidden and unsupported wire values", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers[0].selection.type = 255;
  content.layers[0].distribution.method = 255;
  content.layers[0].brightness_patterns[0].order = 255;
  content.layers[0].priority = 255;
  content.layers[0].unknown_flags = 0x80;
  content.layers[0].selected_movement.unknown_flags = 0x20;
  content.layers[0].overall_movement.enter_exit = true;
  content.layers[0].overall_movement.unknown_flags = 0x40;
  content.layers[0].excess = "aabb";
  controller.sync(content, false);

  const updated = controller.updateLayer({ colour_speed: 3 })!;

  expect(updated.layers[0]).toMatchObject({
    colour_speed: 3,
    selection: { type: 255 },
    distribution: { method: 255 },
    brightness_patterns: [{ order: 255 }],
    priority: 255,
    unknown_flags: 0x80,
    excess: "aabb",
    selected_movement: { unknown_flags: 0x20 },
    overall_movement: { enter_exit: true, unknown_flags: 0x40 },
  });
});

test("adding and copying layers install content and move selection", () => {
  const controller = new AdvancedEffectEditorController();
  controller.sync(blankAdvancedContent(), false);

  const added = controller.addLayer()!;
  expect(controller.isCurrentContent(added)).toBe(true);
  expect(added.layers).toHaveLength(2);
  expect(advancedLayerLabels(added)).toEqual([1, 2]);
  expect(controller.activeLayerIndex).toBe(1);

  const copied = controller.copyLayer()!;
  expect(controller.isCurrentContent(copied)).toBe(true);
  expect(copied.layers).toHaveLength(3);
  expect(advancedLayerLabels(copied)).toEqual([1, 2, 3]);
  expect(controller.activeLayerIndex).toBe(2);
  copied.layers[2].palette[0][0] = 12;
  expect(copied.layers[1].palette[0][0]).toBe(255);
});

test("deleting and reordering layers retain the active logical layer", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers.push(blankLayer(), blankLayer());
  content.layers[0].priority = 1;
  content.layers[1].priority = 2;
  content.layers[2].priority = 3;
  installAdvancedLayerLabels(content, [3, 1, 2]);
  controller.sync(content, false);
  controller.selectLayer(1);

  const reordered = controller.reorderLayer(0, 2)!;
  expect(reordered.layers.map((layer) => layer.priority)).toEqual([
    2, 3, 1,
  ]);
  expect(advancedLayerLabels(reordered)).toEqual([1, 2, 3]);
  expect(controller.activeLayerIndex).toBe(0);
  expect(controller.isCurrentContent(reordered)).toBe(false);

  controller.sync(reordered, false);
  const deleted = controller.deleteLayer()!;
  expect(deleted.layers.map((layer) => layer.priority)).toEqual([3, 1]);
  expect(advancedLayerLabels(deleted)).toEqual([2, 3]);
  expect(controller.activeLayerIndex).toBe(0);
  expect(controller.activePatternIndex).toBe(0);
});

test("positional labels are materialised before the first reorder", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers.push(blankLayer());
  controller.sync(content, false);

  const reordered = controller.reorderLayer(1, 0)!;

  expect(advancedLayerLabels(reordered)).toEqual([2, 1]);
});

test("renumbering and reuse preserve stable numeric identities", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  content.layers.push(blankLayer(), blankLayer());
  installAdvancedLayerLabels(content, [3, 1, 2]);
  controller.sync(content, false);

  const reordered = controller.reorderLayer(0, 2)!;
  expect(advancedLayerLabels(reordered)).toEqual([1, 2, 3]);

  controller.sync(reordered, false);
  controller.selectLayer(1);
  const deleted = controller.deleteLayer()!;
  expect(advancedLayerLabels(deleted)).toEqual([1, 3]);

  controller.sync(deleted, false);
  const added = controller.addLayer()!;
  expect(advancedLayerLabels(added)).toEqual([1, 3, 2]);

  const renumbered = controller.renumberLayers()!;
  expect(advancedLayerLabels(renumbered)).toEqual([1, 2, 3]);
});

test("brightness pattern operations share selection state", () => {
  const controller = new AdvancedEffectEditorController();
  controller.sync(blankAdvancedContent(), false);

  const added = controller.addBrightnessPattern()!;
  expect(added.layers[0].brightness_patterns).toHaveLength(2);
  expect(controller.activePatternIndex).toBe(1);
  controller.sync(added, false);

  expect(controller.visiblePatternIndex(1)).toBe(0);

  const deleted = controller.deleteBrightnessPattern()!;
  expect(deleted.layers[0].brightness_patterns).toHaveLength(1);
  expect(controller.activePatternIndex).toBe(0);
});

test("authoring limits and disabled state reject mutations", () => {
  const controller = new AdvancedEffectEditorController();
  const content = blankAdvancedContent();
  while (content.layers.length < AUTHORING_LAYER_LIMIT) {
    content.layers.push(blankLayer());
  }
  controller.sync(content, false);
  expect(controller.addLayer()).toBeUndefined();
  expect(controller.copyLayer()).toBeUndefined();

  controller.sync(blankAdvancedContent(), true);
  expect(controller.updateLayer({ priority: 2 })).toBeUndefined();
  expect(controller.addBrightnessPattern()).toBeUndefined();
  expect(controller.deleteLayer()).toBeUndefined();
});
