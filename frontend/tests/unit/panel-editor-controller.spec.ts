import { expect, test, vi } from "vitest";
import backendContracts from "../fixtures/backend-contracts.json";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import type { LivePreviewInteraction } from "../../src/live-preview-controller";
import { blankAdvancedContent } from "../../src/advanced-effect-model";
import { buildCustomEffectEntries } from "../../src/custom-effect-list";
import { decodeCustomCatalogue } from "../../src/validation";
import type { CustomEffectCatalogue, LibraryItem, ModelSku, MusicProfileContent } from "../../src/types";
import { device, painted, h6199Catalogue, installH6199Catalogue, item, panelModal, panelControllerHarness } from "./panel-test-support";

function installFutureCatalogue(
  model: PanelModel,
  sku: ModelSku,
  musicSensitivityMaximum: number,
): void {
  const catalogue = structuredClone(h6199Catalogue());
  catalogue.sku = sku;
  catalogue.limits.music_sensitivity_max = musicSensitivityMaximum;
  for (const template of catalogue.templates ?? []) {
    if ("model" in template.content) {
      template.content.model = sku;
    }
  }
  model.customCatalogue = {
    ...catalogue,
    schema_version: 12,
    sku: "H617A",
    models: {
      H617A: { ...catalogue, sku: "H617A" },
      [sku]: catalogue,
    },
  } as CustomEffectCatalogue;
}

function musicItem(content: MusicProfileContent): LibraryItem {
  return {
    schema_version: 1,
    id: "music-1",
    version: 2,
    updated_at: "2026-08-18T00:00:00Z",
    name: "Saved Reactive",
    content,
    content_hash: "music-hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
}

function editor(
  model: PanelModel,
  preview = new PanelPreviewController(model),
  contentCommitted: (interaction: LivePreviewInteraction) => void = () => undefined,
): PanelEditorController {
  const modal = panelModal(model);
  return new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted,
  });
}

test("actual paint and single controller paths use target defaults on open, reset and mode changes", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const target = device("restricted", "H9908");
  target.custom_effects.single = "supported";
  model.devices = [target];
  model.selectedDeviceId = target.config_entry_id;
  installFutureCatalogue(model, target.model, 100);
  const catalogue = model.modelCatalogue!;
  catalogue.apply.painted = catalogue.apply.single = "supported";
  catalogue.painted_effects = [{ id: "clockwise", label: "Clockwise" }];
  catalogue.limits = { ...catalogue.limits, brightness_max: 60, speed_min: 30, speed_max: 60,
    palette_min: 2, palette_max: 2 };
  catalogue.effects = [
    { ...catalogue.effects[0], id: "slow", family: 0, rate_min: 0, rate_max: 10 },
    { ...catalogue.effects[0], id: "fast", family: 1, rate_min: 80, rate_max: 90 },
  ];
  const controller = editor(model);
  const paintEntry = { kind: "paint", key: "template:paint", label: "Paint", category: "single-layer" } as const;
  const singleEntry = { kind: "single", key: "template:single:1:0", label: "Fast", category: "single-layer", family: 1, variant: 0 } as const;
  for (const entry of [paintEntry, singleEntry]) {
    controller.selectCustomEffectEntry(entry);
    expect(model.previewCapability).toBe("supported");
    expect(model.content).toMatchObject(entry.kind === "paint" ? { brightness: 60 } : { family: 1, speed: 80 });
    const initial = structuredClone(model.content);
    expect(controller.openActiveWorkspace({ kind: "workspace", section: "custom", category: "single-layer",
      label: entry.label, origin: { kind: "catalogue_template", source_id: entry.key },
      content: { ...initial, speed: 99 } as typeof initial }, model.editorTransitionEpoch)).toBe(true);
    controller.resetContent();
    expect(model.content).toEqual(initial);
    expect(model.previewCapability).toBe("supported");
  }
  controller.openDefaultAvailableTemplate("single-layer", model.editorTransitionEpoch);
  expect(model.content).toMatchObject({ kind: "h617a_painted", brightness: 60 });
  catalogue.apply.painted = "unsupported";
  controller.openDefaultAvailableTemplate("single-layer", model.editorTransitionEpoch);
  expect(model.content).toMatchObject({ kind: "h617a_single", family: 0, speed: 10 });
  catalogue.apply.painted = "supported";
  controller.newEffect("h617a_painted");
  expect(model.previewCapability).toBe("supported");
  controller.updatePaintedContent({ brightness: 59 });
  controller.resetContent();
  expect(model.content).toMatchObject({ brightness: 60 });
  controller.selectSingleEffect("fast");
  expect(model.content).toMatchObject({ kind: "h617a_single", family: 1, speed: 80 });
  expect(model.previewCapability).toBe("supported");
  controller.selectSingleEffect("slow");
  expect(model.content).toMatchObject({ family: 0, speed: 10 });
  expect(model.previewCapability).toBe("supported");
  controller.selectSingleEffect("paint");
  expect(model.content).toMatchObject({ kind: "h617a_painted", brightness: 60, speed: 30 });
  expect(model.previewCapability).toBe("supported");
});

test("every native DIY and paint template opens with Apply available in its declared category", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.customCatalogue = decodeCustomCatalogue(backendContracts.responses.custom_catalogue);
  const selected = device("ceiling", "H60A6");
  selected.custom_effects.single = selected.custom_effects.multi = selected.custom_effects.advanced = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.section = "custom";
  const { editorController } = panelControllerHarness(model);
  const templates = model.modelCatalogue!.templates!.filter(template => template.content.kind === "native_effect");
  const entries = buildCustomEffectEntries(model.customEffectListContext, "all");
  expect(entries.map(entry => entry.key).sort()).toEqual(templates.map(template => template.id).sort());
  expect(model.customEffectCategoryAvailable("single-layer")).toBe(true);
  for (const entry of entries) {
    model.customEffectCategory = entry.category;
    editorController.selectCustomEffectEntry(entry);
    expect(model.content).toEqual(templates.find(template => template.id === entry.key)!.content);
    expect(model.previewCapability).toBe("supported");
    expect(model.editorAction("apply")!.enabled).toBe(true);
  }
});

test("installs saved content as an isolated editable baseline", () => {
  const model = new PanelModel(() => undefined);
  const controller = editor(model);
  const source = painted();
  model.sceneEditorOpen = true;

  expect(controller.applyLibraryItem(item(source))).toBe(true);
  expect(model.dirty).toBe(false);
  expect(model.sceneEditorOpen).toBe(false);

  if (model.content.kind !== "h617a_painted") {
    throw new Error("saved painted content changed kind");
  }
  model.content.segments[0] = [255, 0, 0];

  expect(source.segments[0]).toEqual([1, 2, 3]);
  expect(model.dirty).toBe(true);
});

test("paint editing applies colour and off as distinct draft states", () => {
  const model = new PanelModel(() => undefined);
  const controller = editor(model);

  controller.paintColourChanged([12, 34, 56]);
  expect(controller.setSegmentColour(2, "committed")).toBe(true);
  expect(model.content).toMatchObject({
    kind: "h617a_painted",
    segments: expect.arrayContaining([[12, 34, 56]]),
  });
  expect(controller.setSegmentColour(2, "committed")).toBe(false);

  controller.selectPaintOff();
  controller.setSegmentColour(2, "committed");
  if (model.content.kind !== "h617a_painted") {
    throw new Error("paint content changed kind");
  }
  expect(model.content.segments[2]).toBeNull();

  controller.paintColourChanged([90, 80, 70]);
  controller.setSegmentColour(4, "committed");
  model.resetBaseline = {
    ...painted(),
    segments: Array.from({ length: 15 }, () => null),
  };
  controller.resetContent();
  if (model.content.kind !== "h617a_painted") {
    throw new Error("paint content changed kind");
  }
  expect(model.content.segments.every((segment) => segment === null)).toBe(true);
  expect(model.content).toMatchObject({
    kind: "h617a_painted",
    effect: "cycle",
    speed: 50,
    brightness: 100,
    segments: Array.from({ length: 15 }, () => null),
  });
});

test("paint gestures commit after their live segment update", () => {
  const model = new PanelModel(() => undefined);
  const preview = new PanelPreviewController(model);
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const committed = vi.fn();
  const controller = editor(model, preview, committed);

  controller.paintColourChanged([12, 34, 56]);
  expect(controller.setSegmentColour(2, "changing")).toBe(true);
  expect(controller.setSegmentColour(2, "committed")).toBe(false);

  expect(scheduleEdited).toHaveBeenLastCalledWith(
    "committed",
    undefined,
  );
  expect(committed).toHaveBeenLastCalledWith("committed");
});

test("catalogue templates edit directly without creating a Cancel breadcrumb", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const controller = editor(model);

  controller.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  const templateEpoch = model.editorTransitionEpoch;
  expect(model.editorSource.kind).toBe("catalogue");
  expect(model.dirty).toBe(false);
  expect(model.editorAction("cancel")?.visible).toBe(false);
  expect(model.editorAction("save")?.visible).toBe(false);
  expect(model.editorAction("saveAs")).toMatchObject({
    visible: true,
    enabled: true,
  });

  controller.updatePaintedContent({ speed: 75 }, "committed");
  expect(model.editorTransitionEpoch).toBe(templateEpoch);
  expect(model.name).toBe("Paint");
  expect(model.resetDirty).toBe(true);
  expect(model.editorAction("cancel")?.visible).toBe(false);

  controller.resetContent();
  expect(model.content).toEqual(painted());
  expect(model.name).toBe("Paint");
  expect(model.resetDirty).toBe(false);
});

test("explicit template selection previews once while automatic opening only populates the editor", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const preview = new PanelPreviewController(model);
  const schedule = vi.spyOn(preview, "scheduleTemplateSelection");
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const committed = vi.fn();
  const controller = editor(model, preview, committed);

  controller.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
    true,
  );
  expect(schedule).toHaveBeenCalledOnce();

  schedule.mockClear();
  const transitionEpoch = controller.beginSelectionTransition();
  controller.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
    false,
    transitionEpoch,
  );
  expect(schedule).not.toHaveBeenCalled();

  controller.updatePaintedContent({ speed: 80 }, "committed");
  scheduleEdited.mockClear();
  committed.mockClear();
  controller.resetContent();
  expect(scheduleEdited).toHaveBeenCalledWith("committed", undefined);
  expect(committed).toHaveBeenCalledWith("committed");
});

test.each([false, true])("actual music controller uses Bloom variant style %s through open/create/reset/mode change", (style) => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.profiles.music = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.customEffectCategory = "music";
  installH6199Catalogue(model);
  const catalogue = model.modelCatalogue!;
  catalogue.music_modes.unshift({id: "bloom", label: "Bloom"});
  catalogue.music_settings.bloom = {
    available: true, style, calm_default: true, colour: true, evidence: "synthetic", palette_size: 7, parameters: {},
  };
  const preview = new PanelPreviewController(model);
  vi.spyOn(preview, "scheduleEdited");
  const controller = editor(model, preview);
  controller.openMusicTemplate("bloom", "Bloom");
  expect(model.content).toMatchObject({mode: "bloom", calm: style ? true : null});
  expect(model.previewCapability).toBe("supported");
  controller.newCustomEffect("music");
  expect(model.content).toMatchObject({mode: "bloom", calm: style ? true : null});
  controller.musicModeChanged("rhythm");
  expect(model.content).toMatchObject({mode: "rhythm", calm: false});
  controller.resetContent();
  expect(model.content).toMatchObject({mode: "bloom", calm: style ? true : null});
  controller.musicModeChanged("rhythm");
  controller.musicModeChanged("bloom");
  expect(model.content).toMatchObject({mode: "bloom", calm: style ? true : null});
  expect(model.previewCapability).toBe("supported");
});

test("Reactive Reset restores its baseline immediately and previews only once", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.profiles.music = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.customEffectCategory = "music";
  installH6199Catalogue(model);
  const preview = new PanelPreviewController(model);
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const committed = vi.fn();
  const controller = editor(model, preview, committed);

  controller.newCustomEffect("music");
  controller.musicModeChanged("rhythm");
  expect(model.resetDirty).toBe(true);
  scheduleEdited.mockClear();
  committed.mockClear();

  controller.resetContent();
  expect(model.content).toMatchObject({
    kind: "music_profile",
    mode: "energetic",
  });
  expect(model.resetDirty).toBe(false);
  expect(model.editorAction("reset")).toMatchObject({
    visible: true,
    enabled: false,
  });
  expect(scheduleEdited).toHaveBeenCalledTimes(1);
  expect(scheduleEdited).toHaveBeenCalledWith("committed", undefined);
  expect(committed).toHaveBeenCalledTimes(1);

  controller.resetContent();
  expect(scheduleEdited).toHaveBeenCalledTimes(1);
  expect(committed).toHaveBeenCalledTimes(1);
});

test("Reactive mode changes preserve common fields, identity, and generated names", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.customEffectCategory = "music";
  const selected = device("entry-a", "H6199");
  selected.profiles.music = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  const preview = new PanelPreviewController(model);
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const committed = vi.fn();
  const controller = editor(model, preview, committed);

  controller.newCustomEffect("music");
  controller.musicContentChanged({
    kind: "music_profile",
    model: "H6199",
    mode: "energetic",
    sensitivity: 61,
    colour: [1, 2, 3],
    calm: null,
    parameters: { point: 4, speed: 8 },
  });
  scheduleEdited.mockClear();
  committed.mockClear();

  controller.musicModeChanged("rhythm");
  expect(model.editorSource).toEqual({
    kind: "new",
    owner: { section: "custom", category: "music" },
  });
  expect(model.newCustomEffectSelected).toBe(true);
  expect(model.name).toBe("New Rhythm effect");
  expect(model.content).toEqual({
    kind: "music_profile",
    model: "H6199",
    mode: "rhythm",
    sensitivity: 61,
    colour: [1, 2, 3],
    calm: false,
    parameters: {},
  });
  expect(scheduleEdited).toHaveBeenCalledWith("committed", undefined);
  expect(committed).toHaveBeenCalledWith("committed");

  model.name = "My Reactive effect";
  controller.musicModeChanged("energetic");
  expect(model.name).toBe("My Reactive effect");

  const saved = musicItem({
    kind: "music_profile",
    model: "H6199",
    mode: "energetic",
    sensitivity: 72,
    colour: null,
    calm: null,
    parameters: { point: 5 },
  });
  controller.applyLibraryItem(saved);
  controller.musicModeChanged("rhythm");
  expect(model.editorSource).toMatchObject({
    kind: "saved",
    itemId: saved.id,
  });
  expect(model.dirty).toBe(true);
  expect(model.content).toMatchObject({
    mode: "rhythm",
    sensitivity: 72,
    colour: null,
    parameters: {},
  });
});

test("Reset restores a new effect name and blank content", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const controller = editor(model);

  controller.newEffect("advanced");
  expect(model.editorSource.kind).toBe("new");
  expect(model.editorAction("cancel")?.visible).toBe(false);
  expect(model.editorAction("reset")).toMatchObject({
    visible: true,
    enabled: false,
  });
  expect(model.name).toBe("New Advanced effect");

  model.name = "My effect";
  const edited = blankAdvancedContent();
  edited.layers[0].priority = 4;
  controller.advancedContentChanged(edited, "committed");
  expect(model.editorAction("reset")?.enabled).toBe(true);

  controller.resetContent();
  expect(model.name).toBe("New Advanced effect");
  expect(model.content).toEqual(blankAdvancedContent());
  expect(model.editorAction("reset")?.enabled).toBe(false);
});

test("name-only Reset restores a new draft without scheduling preview", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const preview = new PanelPreviewController(model);
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const controller = editor(model, preview);

  controller.newEffect("advanced");
  model.name = "Renamed";
  expect(model.resetNameDirty).toBe(true);

  controller.resetContent();
  expect(model.name).toBe("New Advanced effect");
  expect(model.resetDirty).toBe(false);
  expect(scheduleEdited).not.toHaveBeenCalled();
});

test("Advanced waits for New or a saved effect instead of opening a redundant starter", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const controller = editor(model);
  const transitionEpoch = controller.beginTransition();

  controller.openDefaultAvailableTemplate("advanced", transitionEpoch);

  expect(model.name).toBe("");
  expect(model.editorSource.kind).toBe("none");
  expect(model.editorAction("cancel")?.visible).toBe(false);
});

test("explicit New Reset restores its name while layered scene Reset retains its name", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const controller = editor(model);

  controller.newEffect("advanced");
  const newName = model.name;
  model.name = "Renamed Advanced effect";
  const editedNew = blankAdvancedContent();
  editedNew.layers[0].priority = 4;
  controller.advancedContentChanged(editedNew, "committed");
  expect(model.resetDirty).toBe(true);
  controller.resetContent();
  expect(model.name).toBe(newName);
  expect(model.content).toEqual(blankAdvancedContent());

  const scene = {
    kind: "scene_layered" as const,
    template: {
      sku: "H617A",
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
    effect: { layers: blankAdvancedContent().layers },
    speed_index: null,
    raw_param: "",
  };
  controller.openSceneEditor({
    content: scene,
    config_entry_id: "entry-a",
    name: "Scene heading",
  });
  const editedScene = blankAdvancedContent();
  editedScene.layers[0].priority = 5;
  controller.advancedContentChanged(editedScene, "committed");
  controller.resetContent();

  expect(model.name).toBe("Scene heading");
  expect(model.content).toEqual(scene);
});

test("future model profile defaults come from catalogue limits and templates", () => {
  const selected = device("entry-a", "H7000");
  selected.profiles = { music: "supported", video: "supported" };
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.customEffectCategory = "music";
  installFutureCatalogue(model, selected.model, 87);
  const controller = editor(model);

  controller.newCustomEffect("music");
  expect(model.content).toMatchObject({
    kind: "music_profile",
    model: "H7000",
    sensitivity: 87,
  });

  model.section = "video";
  controller.openVideoTemplate("movie", "Movie", false);
  expect(model.editorSource).toMatchObject({
    kind: "catalogue",
    selectionIdentity: "template:video:movie",
  });
  expect(model.content).toMatchObject({
    kind: "video_profile",
    model: "H7000",
    mode: "movie",
  });
});
