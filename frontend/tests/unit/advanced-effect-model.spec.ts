import { expect, test } from "vitest";

import {
  advancedLayerLabels,
  adjustAppliedAreaLeftEdge,
  adjustAppliedAreaRightEdge,
  appliedAreaEffectiveWidth,
  appliedAreaSegments,
  appliedAreaWireBounds,
  blankAdvancedContent,
  blankLayer,
  bytePercent,
  cloneAdvancedContent,
  cloneLayer,
  cloneLayeredSceneContent,
  layerAppliedAreaSegments,
  moveAppliedArea,
  installAdvancedLayerLabels,
  withAppliedAreaSegments,
} from "../../src/advanced-effect-model";

test("blank advanced content contains an editable default layer", () => {
  const content = blankAdvancedContent();

  expect(content.layers).toHaveLength(1);
  expect(content.layers[0].area).toEqual({
    start_tenths: 0,
    width_tenths: 10,
  });
  expect(content.layers[0].brightness_patterns).toHaveLength(1);
  expect(content.layers[0].palette).toEqual([
    [255, 0, 0],
    [0, 0, 255],
  ]);
});

test("advanced and layered scene clones do not share nested state", () => {
  const source = blankAdvancedContent();
  installAdvancedLayerLabels(source, [7]);
  const advancedClone = cloneAdvancedContent(source);
  const scene = {
    kind: "scene_layered" as const,
    template: {
      sku: "H6199",
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
    effect: { layers: source.layers },
    speed_index: null,
    raw_param: "",
  };
  const sceneClone = cloneLayeredSceneContent(scene);

  advancedClone.layers[0].palette[0][0] = 0;
  sceneClone.template.scene_id = 9;
  sceneClone.effect.layers[0].area.start_tenths = 4;

  expect(source.layers[0].palette[0]).toEqual([255, 0, 0]);
  expect(scene.template.scene_id).toBe(1);
  expect(source.layers[0].area.start_tenths).toBe(0);
  expect(advancedLayerLabels(advancedClone)).toEqual([7]);
  expect(advancedLayerLabels({
    kind: "advanced",
    layers: sceneClone.effect.layers,
  })).toEqual([7]);
});

test("invalid layer metadata falls back to positional labels", () => {
  const content = blankAdvancedContent();
  content.layers.push(blankLayer());

  installAdvancedLayerLabels(content, [4, 4]);

  expect(advancedLayerLabels(content)).toEqual([1, 2]);

  installAdvancedLayerLabels(content, [255, 256]);
  expect(advancedLayerLabels(content)).toEqual([1, 2]);
});

test("byte percentages clamp to the supported range", () => {
  expect(bytePercent(128)).toBe(50);
  expect(bytePercent(300)).toBe(100);
});

test("applied area left edge resizes without moving the right edge", () => {
  expect(adjustAppliedAreaLeftEdge(8, 1)).toEqual({
    start: 1,
    end: 8,
  });
  expect(adjustAppliedAreaLeftEdge(8, 3)).toEqual({
    start: 3,
    end: 8,
  });
  expect(adjustAppliedAreaLeftEdge(8, 9)).toEqual({
    start: 7,
    end: 8,
  });
  expect(adjustAppliedAreaLeftEdge(12, 4, 15)).toEqual({
    start: 4,
    end: 12,
  });
});

test("applied area right edge resizes without moving the left edge", () => {
  expect(adjustAppliedAreaRightEdge(3, 8)).toEqual({
    start: 3,
    end: 8,
  });
  expect(adjustAppliedAreaRightEdge(3, 2)).toEqual({
    start: 3,
    end: 4,
  });
  expect(adjustAppliedAreaRightEdge(3, 12)).toEqual({
    start: 3,
    end: 10,
  });
});

test("applied area movement preserves width and stops at strip edges", () => {
  expect(moveAppliedArea(2, 8, 1)).toEqual({ start: 1, end: 7 });
  expect(moveAppliedArea(2, 8, 9)).toEqual({ start: 4, end: 10 });
  expect(moveAppliedArea(2, 8, -4)).toEqual({ start: 0, end: 6 });
});

test("applied area segments preserve visual length while moving", () => {
  expect(appliedAreaSegments(0, 2, 15)).toEqual({
    start: 0,
    end: 3,
    length: 3,
  });
  expect(appliedAreaSegments(1, 2, 15)).toEqual({
    start: 1,
    end: 4,
    length: 3,
  });
  expect(appliedAreaSegments(8, 2, 15)).toEqual({
    start: 12,
    end: 15,
    length: 3,
  });
});

test("raw zero width remains encoded while displaying the full strip", () => {
  const layer = blankLayer();
  layer.area.width_tenths = 0;

  expect(appliedAreaEffectiveWidth(layer.area.width_tenths)).toBe(10);
  expect(layerAppliedAreaSegments(layer, 15)).toEqual({
    start: 0,
    end: 15,
    length: 15,
  });
  expect(cloneLayer(layer).area.width_tenths).toBe(0);
});

test("exact segment bounds survive clones while serialising nearest wire values", () => {
  const layer = withAppliedAreaSegments(blankLayer(), 2, 5, 15);

  expect(appliedAreaWireBounds(2, 5, 15)).toEqual({
    start: 1,
    end: 3,
  });
  expect(layer.area).toEqual({
    start_tenths: 1,
    width_tenths: 2,
  });
  expect(layerAppliedAreaSegments(layer, 15)).toEqual({
    start: 2,
    end: 5,
    length: 3,
  });
  expect(layerAppliedAreaSegments(cloneLayer(layer), 15)).toEqual({
    start: 2,
    end: 5,
    length: 3,
  });
  expect(JSON.parse(JSON.stringify(layer)).area).toEqual(layer.area);
});
