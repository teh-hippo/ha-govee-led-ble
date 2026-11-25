import { expect, test, vi } from "vitest";
import backendContracts from "../fixtures/backend-contracts.json";
import type { EffectStudioApi } from "../../src/api";
import { PanelController, restoredAutoSave } from "../../src/panel-controller";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import { serialiseEditable } from "../../src/effect-editor-model";
import { blankAdvancedContent } from "../../src/advanced-effect-model";
import { decodeCustomCatalogue } from "../../src/validation";
import type { BuiltinSceneContent, LibraryItem, PaintedContent } from "../../src/types";
import { device, painted, videoProfile, installH6199Catalogue, item, panelModal, panelControllerHarness, flowWorkspaceDevice } from "./panel-test-support";

function installPaintCatalogue(model: PanelModel): void {
  installH6199Catalogue(model);
  model.customCatalogue!.models.H617A.painted_effects = [{ id: "cycle", label: "Cycle" }];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
}

test("Auto Save keeps partial native paints out of the saved library and resumes after the layout is complete", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.autoSaveEnabled = true;
  const { controller, editorController } = panelControllerHarness(model);
  const saved: LibraryItem = {
    ...item(painted()), content: { kind: "static_rgb", segments: Array.from({ length: 15 }, () => [255, 0, 0]), rgb_scale: 100 },
  };
  const updateItem = vi.fn(async (base: LibraryItem, name: string, content: LibraryItem["content"]) =>
    ({ ...base, name, content, version: base.version + 1 }));
  controller.api = { updateItem } as unknown as EffectStudioApi;
  editorController.applyLibraryItem(saved);
  editorController.fillStaticSegments(null);
  controller.contentCommitted("committed");
  expect(updateItem).not.toHaveBeenCalled();
  expect(model.dirty).toBe(true);
  expect(model.editorAction("saveAs")?.enabled).toBe(false);
  editorController.fillStaticSegments([0, 0, 255]);
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(model.dirty).toBe(false));
  expect(updateItem).toHaveBeenCalledTimes(1);
  expect(model.currentItem?.content).toEqual({ kind: "static_rgb", segments: Array(15).fill([0, 0, 255]), rgb_scale: 100 });
  controller.disconnect();
});

test.each(["manual save", "reload"])("autosave uses the accepted item version after %s", async (transition) => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  let server = item(painted());
  const updateItem = vi.fn(async (base: LibraryItem, name: string, content: PaintedContent) => {
    if (base.version !== server.version) throw new Error("Stale version");
    server = { ...server, name, content, version: server.version + 1 };
    return server;
  });
  controller.api = { updateItem } as unknown as EffectStudioApi;
  editorController.applyLibraryItem(server);
  model.autoSaveEnabled = true;
  editorController.updatePaintedContent({ speed: 60 }, "committed");
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(model.autoSaveInProgress).toBe(false));
  expect(server.version).toBe(3);

  controller.toggleAutoSave();
  if (transition === "manual save") {
    editorController.updatePaintedContent({ speed: 70 }, "committed");
    expect(await controller.save()).toBe(true);
  } else {
    server = { ...server, version: 4, content: { ...painted(), speed: 70 } };
    editorController.applyLibraryItem(server);
  }
  controller.toggleAutoSave();
  editorController.updatePaintedContent({ speed: 80 }, "committed");
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(model.autoSaveInProgress).toBe(false));

  expect(updateItem.mock.calls.map(([base]) => base.version)).toEqual(
    transition === "manual save" ? [2, 3, 4] : [2, 4],
  );
  expect(server.version).toBe(5);
  expect(model.autoSaveFailed).toBe(false);
  expect(model.dirty).toBe(false);
  controller.disconnect();
});

test.each([false, true])("explicit Live choices survive reopening, including saved items (%s)", async (savedItem) => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
  try {
    const model = new PanelModel(() => undefined);
    const selected = device("entry-a", "H617A");
    model.isAdmin = true;
    model.devices = [selected];
    model.selectedDeviceId = selected.config_entry_id;
    installPaintCatalogue(model);
    const { controller, editorController } = panelControllerHarness(model);
    controller.api = {
      applySavedEffect: vi.fn().mockResolvedValue(undefined),
      device: vi.fn().mockResolvedValue(selected),
    } as unknown as EffectStudioApi;
    expect(model.liveApplyEnabled).toBe(true);
    await controller.toggleLive();
    expect(new PanelModel(() => undefined).liveApplyEnabled).toBe(false);
    if (savedItem) editorController.applyLibraryItem(item(painted()));
    await controller.toggleLive();
    expect(new PanelModel(() => undefined).liveApplyEnabled).toBe(true);
    controller.stateUpdatesFailed(new Error("Connection lost."));
    expect(model.liveApplyEnabled).toBe(false);
    expect(new PanelModel(() => undefined).liveApplyEnabled).toBe(true);
  } finally {
    vi.unstubAllGlobals();
  }
});

test.each([null, "invalid", "true", "false"])("Live preference storage failures never block toggling (%s)", async (stored) => {
  vi.stubGlobal("localStorage", {
    getItem: () => {
      if (stored === null) throw new Error("Storage unavailable");
      return stored;
    },
    setItem: () => { throw new Error("Storage unavailable"); },
  });
  try {
    const model = new PanelModel(() => undefined);
    expect(model.liveApplyEnabled).toBe(stored !== "false");
    const { controller } = panelControllerHarness(model);
    await expect(controller.toggleLive()).resolves.toBeUndefined();
    expect(model.liveApplyEnabled).toBe(stored === "false");
  } finally {
    vi.unstubAllGlobals();
  }
});

test("subscription failure disables Live and blocks mutation until reload", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = true;
  const { controller } = panelControllerHarness(model);

  controller.stateUpdatesFailed(new Error("Connection lost."));

  expect(model.liveApplyEnabled).toBe(false);
  expect(model.stateUpdatesUnavailable).toBe(true);
  expect(model.editorReadOnly).toBe(true);
  expect(model.editorActions.every((action) => !action.enabled)).toBe(true);
  expect(model.modalState).toMatchObject({
    kind: "error",
    title: "State updates stopped",
    message: "Connection lost. Reload the page before making further changes.",
  });
});

test("subscription failure cancels queued auto-save and blocks dirty transitions", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  const { controller, editorController, modal } =
    panelControllerHarness(model);
  const source = item(painted());
  editorController.applyLibraryItem(source);
  let resolveUpdate!: (item: LibraryItem) => void;
  const updating = new Promise<LibraryItem>((resolve) => {
    resolveUpdate = resolve;
  });
  const updateItem = vi.fn().mockReturnValue(updating);
  controller.api = { updateItem } as unknown as EffectStudioApi;

  editorController.updatePaintedContent({ speed: 60 }, "committed");
  controller.contentCommitted("committed");
  editorController.updatePaintedContent({ speed: 70 }, "committed");
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(updateItem).toHaveBeenCalledOnce());

  controller.stateUpdatesFailed(new Error("Connection lost."));
  resolveUpdate({
    ...source,
    version: source.version + 1,
    updated_at: "2026-08-27T00:00:00Z",
    content: { ...painted(), speed: 60 },
  });
  await vi.waitFor(() => expect(model.autoSaveInProgress).toBe(false));
  modal.closeError();
  await controller.selectSection("scenes");

  expect(updateItem).toHaveBeenCalledOnce();
  expect(model.section).toBe("custom");
  expect(model.dirty).toBe(true);
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: "Reload the page before continuing.",
  });
});

test("pending transitions save named new drafts directly", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const { controller, editorController } = panelControllerHarness(model);

  editorController.newEffect("advanced");
  model.name = "Named Advanced effect";
  await controller.requestTransition(() => undefined);

  expect(model.pendingTransitionDialog).toMatchObject({
    primaryLabel: "Save",
    saveName: "Named Advanced effect",
    requiresName: true,
  });
});

test("controlling non-admin transitions discard local work without a save action", async () => {
  const model = new PanelModel(() => undefined);
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const { controller, editorController } = panelControllerHarness(model);
  editorController.newEffect("advanced");
  model.name = "Local draft";

  await controller.requestTransition(() => undefined);

  expect(model.pendingTransitionDialog?.canSave).toBe(false);
  await controller.savePendingTransition();
  expect(model.pendingTransitionDialog?.busy).toBe(false);
});

test("scene-owned transitions use the scene save continuation", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.sceneWorkDirty = true;
  const { controller } = panelControllerHarness(model);
  const execute = vi.fn();
  const saveScene = vi.fn().mockResolvedValue(true);

  await controller.requestTransition(execute, undefined, saveScene);
  expect(model.pendingTransitionDialog).toMatchObject({
    primaryLabel: "Save",
    requiresName: false,
  });

  await controller.savePendingTransition();

  expect(saveScene).toHaveBeenCalledOnce();
  expect(execute).toHaveBeenCalledOnce();
});

test("top-level transitions use the registered scene-work saver", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const first = device("entry-a", "H6199");
  const second = device("entry-b", "H6199");
  model.devices = [first, second];
  model.selectedDeviceId = first.config_entry_id;
  model.section = "scenes";
  model.sceneWorkDirty = true;
  installH6199Catalogue(model);
  const saveSceneWork = vi.fn().mockResolvedValue(true);
  const { controller } = panelControllerHarness(
    model,
    saveSceneWork,
  );
  controller.api = {
    subscribeDevice: vi.fn().mockResolvedValue(() => undefined),
    updateUserState: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;

  await controller.selectSection("custom", "single-layer");
  await controller.savePendingTransition();
  expect(model.section).toBe("custom");

  model.section = "scenes";
  model.sceneWorkDirty = true;
  await controller.deviceChanged(second.config_entry_id);
  await controller.savePendingTransition();
  expect(model.selectedDeviceId).toBe(second.config_entry_id);

  model.sceneWorkDirty = true;
  const followLink = vi.fn();
  await controller.requestTransition(followLink);
  await controller.savePendingTransition();

  expect(followLink).toHaveBeenCalledOnce();
  expect(saveSceneWork).toHaveBeenCalledTimes(3);
});

test.each(["manual", "auto"] as const)("native scene %s saving persists manual layer speeds without applying", async (mode) => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = mode === "auto";
  model.liveApplyEnabled = false;
  model.section = "scenes";
  model.customCatalogue = decodeCustomCatalogue(backendContracts.responses.custom_catalogue);
  const selected = device("ceiling", "H60A6");
  selected.custom_effects.single = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const template = model.modelCatalogue!.templates!.find(template => template.content.kind === "native_effect")!;
  if (template.content.kind !== "native_effect") throw new Error("Expected native template");
  const scene = {
    ...structuredClone(template.content),
    preset_id: null,
    template: { sku: "H60A6" as const, scene_id: 1, effect_id: 2, catalogue_schema_version: 2 },
  };
  const edited = structuredClone(scene);
  const layer = edited.layers[0];
  if (layer.type === "opaque") throw new Error("Expected editable native layer");
  layer.speed = layer.speed === 85 ? 58 : 85;
  edited.speed_index = null;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openSceneEditor({ content: scene, config_entry_id: selected.config_entry_id, name: "Native scene" });
  const setSceneDefault = vi.fn().mockResolvedValue({
    content: edited, catalogue_content: scene, has_default: true,
  });
  const applySnapshot = vi.fn();
  controller.api = { setSceneDefault, applySnapshot } as unknown as EffectStudioApi;
  editorController.nativeContentChanged(edited, "committed");
  if (mode === "manual") {
    await expect(controller.save()).resolves.toBe(true);
  } else {
    controller.contentCommitted("committed");
    await vi.waitFor(() => expect(setSceneDefault).toHaveBeenCalledOnce());
  }
  expect(setSceneDefault).toHaveBeenCalledWith(selected.config_entry_id, edited);
  expect(applySnapshot).not.toHaveBeenCalled();
  expect(model.builtInDefaultDirty).toBe(false);
});

test("external layered-scene transitions use the panel editor save", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.section = "scenes";
  const saveSceneWork = vi.fn().mockResolvedValue(true);
  const { controller, editorController } = panelControllerHarness(
    model,
    saveSceneWork,
  );
  const scene = {
    kind: "scene_layered" as const,
    template: {
      sku: "H617A" as const,
      scene_id: 1,
      effect_id: 2,
      catalogue_schema_version: 1,
    },
    effect: { layers: blankAdvancedContent().layers },
    speed_index: null,
    raw_param: "",
  };
  editorController.openSceneEditor({
    content: scene,
    config_entry_id: selected.config_entry_id,
    name: "Layered scene",
  });
  const edited = blankAdvancedContent();
  edited.layers[0].priority = 4;
  editorController.advancedContentChanged(edited, "committed");
  model.sceneWorkDirty = true;
  const execute = vi.fn();
  await controller.selectScene(execute);
  const savedContent = {
    ...scene,
    effect: { layers: edited.layers },
  };
  const setSceneDefault = vi.fn().mockResolvedValue({
    scene: {
      scene_id: 1,
      effect_id: 2,
      category_id: 1,
      category: "Natural",
      name: "Layered",
      variant: "",
      display_name: "Layered",
      scene_type: 2,
      parameter_kind: "layers",
      speed: null,
    },
    content: savedContent,
    catalogue_content: scene,
    has_default: true,
  });
  controller.api = { setSceneDefault } as unknown as EffectStudioApi;

  await controller.savePendingTransition();

  expect(setSceneDefault).toHaveBeenCalledWith(
    selected.config_entry_id,
    savedContent,
  );
  expect(saveSceneWork).not.toHaveBeenCalled();
  expect(execute).toHaveBeenCalledOnce();
});

test("catalogue drafts take precedence over stale scene-work ownership", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.customEffectCategory = "advanced";
  const saveSceneWork = vi.fn().mockResolvedValue(true);
  const { controller, editorController } = panelControllerHarness(
    model,
    saveSceneWork,
  );
  editorController.openEditableTemplate(
    "Template",
    blankAdvancedContent(),
    "template:advanced",
    { section: "custom", category: "advanced" },
  );
  const edited = blankAdvancedContent();
  edited.layers[0].priority = 4;
  editorController.advancedContentChanged(edited, "committed");
  model.sceneWorkDirty = true;
  const execute = vi.fn();
  await controller.requestTransition(execute);
  const setTemplateDefault = vi.fn().mockResolvedValue({
    template_id: "template:advanced",
    content: edited,
    catalogue_content: blankAdvancedContent(),
    has_default: true,
  });
  controller.api = { setTemplateDefault } as unknown as EffectStudioApi;

  expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
  await controller.savePendingTransition();

  expect(setTemplateDefault).toHaveBeenCalled();
  expect(saveSceneWork).not.toHaveBeenCalled();
  expect(execute).toHaveBeenCalledOnce();
});

test("busy pending-transition saves ignore cancellation until persistence finishes", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
  installH6199Catalogue(model);
  const { controller, editorController, modal } =
    panelControllerHarness(model);
  editorController.newEffect("advanced");
  model.name = "Named Advanced effect";
  const execute = vi.fn();
  await controller.requestTransition(execute);
  let resolveCreate!: (item: LibraryItem) => void;
  const creating = new Promise<LibraryItem>((resolve) => {
    resolveCreate = resolve;
  });
  const created: LibraryItem = {
    ...item(painted()),
    id: "advanced-created",
    name: model.name,
    content: blankAdvancedContent(),
  };
  controller.api = {
    createItem: vi.fn().mockReturnValue(creating),
  } as unknown as EffectStudioApi;

  const saving = controller.savePendingTransition();
  await Promise.resolve();
  modal.showError("Unrelated subscription failure.", {
    key: "unrelated-subscription",
  });
  modal.closeError();
  controller.cancelPendingTransition();

  expect(model.pendingTransitionDialog).toMatchObject({ busy: true });
  expect(execute).not.toHaveBeenCalled();

  resolveCreate(created);
  await saving;

  expect(execute).toHaveBeenCalledOnce();
  expect(model.pendingTransitionDialog).toBeUndefined();
});

test("navigation after a committed save ignores an obsolete Live request rejection", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  selected.effect_compatibilities = {};
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  const { controller, editorController, preview } = panelControllerHarness(model);
  editorController.newEffect("advanced");
  model.name = "Named Advanced effect";
  const execute = vi.fn(() => {
    editorController.beginTransition();
  });
  await controller.requestTransition(execute);
  model.liveApplyEnabled = true;
  const created: LibraryItem = {
    ...item(painted()),
    id: "advanced-created",
    name: model.name,
    content: blankAdvancedContent(),
  };
  const api = {
    createItem: vi.fn().mockResolvedValue(created),
    previewSnapshot: vi.fn().mockRejectedValue(new Error("offline")),
    subscribePreview: vi.fn().mockResolvedValue(vi.fn()),
    onConnectionReady: vi.fn().mockReturnValue(vi.fn()),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    cancelPreview: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;
  controller.api = api;
  await preview.open(api, vi.fn());

  await controller.savePendingTransition();

  expect(execute).toHaveBeenCalledOnce();
  expect(model.currentItem?.id).toBe(created.id);
  expect(api.previewSnapshot).toHaveBeenCalledOnce();
  expect(api.cancelPreview).toHaveBeenCalledOnce();
  expect(model.modalState).toBeUndefined();
  preview.dispose();
});

test("auto-save restores only an explicit true preference", () => {
  expect(restoredAutoSave(true)).toBe(true);
  expect(restoredAutoSave(false)).toBe(false);
  expect(restoredAutoSave("true")).toBe(false);
  expect(restoredAutoSave(undefined)).toBe(false);
});

test("auto-save coalesces committed edits onto the returned item version", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = false;
  const preview = new PanelPreviewController(model);
  const modal = panelModal(model);
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: (interaction) =>
      controller.contentCommitted(interaction),
  });
  controller = new PanelController(
    model,
    editorController,
    preview,
    modal,
    {
      connected: () => true,
      pathname: () => "/ha-govee-led-ble",
      replacePath: () => undefined,
    },
  );
  const sourceContent = painted();
  const source = item(sourceContent);
  editorController.applyLibraryItem(source);
  let resolveFirst!: (value: LibraryItem) => void;
  const first = new Promise<LibraryItem>((resolve) => {
    resolveFirst = resolve;
  });
  const updateItem = vi
    .fn()
    .mockReturnValueOnce(first)
    .mockImplementation(
      async (
        current: LibraryItem,
        name: string,
        content: PaintedContent,
      ) => ({
        ...current,
        version: current.version + 1,
        updated_at: "2026-08-18T00:00:02Z",
        name,
        content,
      }),
    );
  controller.api = { updateItem } as unknown as EffectStudioApi;

  editorController.updatePaintedContent({ speed: 60 }, "committed");
  editorController.updatePaintedContent({ speed: 70 }, "committed");
  resolveFirst({
    ...source,
    version: 3,
    updated_at: "2026-08-18T00:00:01Z",
    content: { ...sourceContent, speed: 60 },
  });

  await vi.waitFor(() => expect(updateItem).toHaveBeenCalledTimes(2));

  expect(updateItem.mock.calls[1][0]).toMatchObject({ version: 3 });
  expect(updateItem.mock.calls[1][2]).toMatchObject({ speed: 70 });
  expect(model.currentItem).toMatchObject({ version: 4 });
  expect(model.resetDirty).toBe(true);
  expect(model.notice).toBeUndefined();

  editorController.resetContent();
  await vi.waitFor(() => expect(updateItem).toHaveBeenCalledTimes(3));
  expect(updateItem.mock.calls[2][2]).toMatchObject({ speed: 50 });
  expect(model.resetDirty).toBe(false);
});

test("auto-save overwrite retains pending navigation ownership", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  const { controller, editorController } = panelControllerHarness(model);
  const source = item(painted());
  editorController.applyLibraryItem(source);
  editorController.updatePaintedContent({ speed: 61 }, "committed");
  const target = {
    ...source,
    id: "target",
    version: 5,
    updated_at: "2026-08-27T00:00:00Z",
    content: { ...source.content, speed: 61 },
  };
  controller.api = {
    updateItem: vi.fn().mockResolvedValue(target),
  } as unknown as EffectStudioApi;

  await controller.selectSection("scenes");

  expect(model.section).toBe("scenes");
  expect(model.currentItem?.id).toBe("target");
});

test("saved item selection previews content only while Live is enabled", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  installPaintCatalogue(model);
  const preview = new PanelPreviewController(model);
  const modal = panelModal(model);
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: (interaction) =>
      controller.contentCommitted(interaction),
  });

  controller = new PanelController(
    model,
    editorController,
    preview,
    modal,
    {
      connected: () => true,
      pathname: () => "/ha-govee-led-ble",
      replacePath: () => undefined,
    },
  );
  const saved = item(painted());
  const submit = vi.spyOn(preview, "submit");
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  controller.api = {
    item: vi.fn().mockResolvedValue(saved),
    applySavedEffect,
  } as unknown as EffectStudioApi;

  model.liveApplyEnabled = false;
  await expect(controller.selectItem(saved.id)).resolves.toBe(true);
  expect(model.currentItem?.id).toBe(saved.id);
  expect(model.editorSource).toMatchObject({
    kind: "saved",
    itemId: saved.id,
  });
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();

  model.liveApplyEnabled = true;
  await expect(controller.selectItem(saved.id)).resolves.toBe(true);
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    configEntryId: "entry-a",
    name: saved.name,
    content: saved.content,
  }));
  expect(applySavedEffect).not.toHaveBeenCalled();
});

test("saved scene callbacks cannot enqueue older content after a newer Live edit", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = true;
  model.section = "scenes";
  const content: BuiltinSceneContent = {
    kind: "scene_builtin",
    template: { sku: "H617A", scene_id: 1, effect_id: 2, catalogue_schema_version: 1 },
    speed_index: 0,
  };
  const saved: LibraryItem = { ...item(painted()), content };
  model.devices = [{
    ...device("entry-a", "H617A"), effect_compatibilities: {
      [saved.id]: {version: saved.version, state: "compatible", reasons: []},
    },
  }];
  model.selectedDeviceId = "entry-a";
  installPaintCatalogue(model);
  const {controller, preview} = panelControllerHarness(model);
  const submit = vi.spyOn(preview, "submit");
  let finish!: (result: unknown) => void;
  const validation = new Promise(resolve => {finish = resolve;});
  controller.api = {
    contentCompatibility: vi.fn().mockReturnValue(validation),
  } as unknown as EffectStudioApi;
  const notification = controller.sceneItemSaved(saved, "entry-a", true, model.editorTransitionEpoch);
  const newerContent = { ...content, speed_index: 1 };
  preview.scheduleScene({ kind: "snapshot", name: saved.name, content: newerContent });
  finish({state: "compatible", reasons: []});
  await notification;

  expect(submit.mock.calls.map(([request]) => request.kind === "snapshot" && request.content)).toEqual([
    saved.content,
    newerContent,
  ]);
  expect(model.library.items).toEqual([expect.objectContaining({ id: saved.id, version: saved.version })]);
});

test.each(["H617A", "H6199"] as const)("clean saved %s Live uses the cancellable preview session", async (sku) => {
  const selected = sku === "H6199" ? flowWorkspaceDevice("entry-a") : device("entry-a", sku);
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installPaintCatalogue(model);
  model.liveApplyEnabled = false;
  model.h6179ApprovedDiyCode = 73;
  const { controller, editorController, preview } = panelControllerHarness(model);
  const saved: LibraryItem = {
    ...item(painted()),
    content: sku === "H6199"
      ? { kind: "palette_diy", model: sku, family: 1, variant: 0, speed: 50, palette: [[255, 0, 0], [0, 0, 255]] }
      : painted(),
  };
  editorController.applyLibraryItem(saved);
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  const previewSnapshot = vi.fn().mockResolvedValue(undefined);
  const cancelPreview = vi.fn().mockResolvedValue(undefined);
  const api = {
    applySavedEffect,
    previewSnapshot,
    cancelPreview,
    subscribePreview: vi.fn().mockResolvedValue(vi.fn()),
    onConnectionReady: vi.fn().mockReturnValue(vi.fn()),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;
  controller.api = api;
  await preview.open(api, vi.fn());

  await controller.toggleLive();

  expect(model.liveApplyEnabled).toBe(true);
  await vi.waitFor(() => expect(previewSnapshot).toHaveBeenCalledOnce());
  expect(previewSnapshot).toHaveBeenCalledWith(
    expect.any(String),
    1,
    selected.config_entry_id,
    saved.name,
    saved.content,
    false,
    undefined,
    ...(sku === "H6199" ? [73] : []),
  );
  expect(applySavedEffect).not.toHaveBeenCalled();

  await controller.toggleLive();
  await preview.cancel();

  expect(model.liveApplyEnabled).toBe(false);
  expect(cancelPreview).toHaveBeenCalledWith(previewSnapshot.mock.calls[0][0], selected.config_entry_id);
  preview.dispose();
});

test("enabling Live while browsing Scenes does not apply a retained hidden editor item", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = false;
  const { controller, editorController, preview } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  model.section = "scenes";
  const toggle = vi.spyOn(preview, "toggle");
  const applySavedEffect = vi.fn();
  controller.api = {
    applySavedEffect,
  } as unknown as EffectStudioApi;

  await controller.toggleLive();

  expect(toggle).toHaveBeenCalledOnce();
  expect(applySavedEffect).not.toHaveBeenCalled();
});

test("new saves preview saved content only while Live remains enabled", async () => {
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = true;
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "advanced" },
  };
  model.name = "BugToFix";
  model.content = blankAdvancedContent();
  const { controller, preview } = panelControllerHarness(model);
  const submit = vi.spyOn(preview, "submit");
  const created: LibraryItem = {
    ...item(painted()),
    id: "bug-to-fix",
    version: 1,
    name: model.name,
    content: blankAdvancedContent(),
  };
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  controller.api = {
    createItem: vi.fn().mockResolvedValue(created),
    applySavedEffect,
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;

  await expect(controller.save()).resolves.toBe(true);

  expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    configEntryId: selected.config_entry_id,
    name: created.name,
    content: created.content,
  }));
  expect(applySavedEffect).not.toHaveBeenCalled();

  model.liveApplyEnabled = false;
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "advanced" },
  };
  model.currentItem = undefined;
  model.name = "StoredOnly";
  model.content = blankAdvancedContent();
  const stored = { ...created, id: "stored-only", name: model.name };
  controller.api.createItem = vi.fn().mockResolvedValue(stored);
  submit.mockClear();

  await expect(controller.save()).resolves.toBe(true);

  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();
});

test("a rejected Live request does not turn a committed save into a persistence failure", async () => {
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  selected.effect_compatibilities = {};
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = true;
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "advanced" },
  };
  model.name = "Stored";
  model.content = blankAdvancedContent();
  const { controller, preview } = panelControllerHarness(model);
  const created: LibraryItem = {
    ...item(painted()),
    id: "stored",
    version: 1,
    name: model.name,
    content: blankAdvancedContent(),
  };
  const api = {
    createItem: vi.fn().mockResolvedValue(created),
    previewSnapshot: vi.fn().mockRejectedValue(new Error("offline")),
    subscribePreview: vi.fn().mockResolvedValue(vi.fn()),
    onConnectionReady: vi.fn().mockReturnValue(vi.fn()),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    cancelPreview: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;
  controller.api = api;
  await preview.open(api, vi.fn());

  await expect(controller.save()).resolves.toBe(true);

  expect(model.currentItem?.id).toBe(created.id);
  expect(model.dirty).toBe(false);
  await vi.waitFor(() => expect(model.modalState).toMatchObject({
    kind: "error",
    message: expect.stringContaining("offline"),
  }));
  preview.dispose();
});

test("disabling Live while a new save is pending suppresses its preview", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = true;
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "advanced" },
  };
  model.name = "Delayed";
  model.content = blankAdvancedContent();
  const { controller, preview } = panelControllerHarness(model);
  const submit = vi.spyOn(preview, "submit");
  let resolveCreate!: (item: LibraryItem) => void;
  const create = new Promise<LibraryItem>((resolve) => {
    resolveCreate = resolve;
  });
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  controller.api = {
    createItem: vi.fn().mockReturnValue(create),
    applySavedEffect,
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;

  const save = controller.save();
  model.liveApplyEnabled = false;
  resolveCreate({
    ...item(painted()),
    id: "delayed",
    version: 1,
    name: model.name,
    content: blankAdvancedContent(),
  });

  await expect(save).resolves.toBe(true);
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();
});

test("scene saves follow strict Live semantics", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installPaintCatalogue(model);
  const { controller, preview } = panelControllerHarness(model);
  const submit = vi.spyOn(preview, "submit");
  const saved = item(painted());
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  controller.api = {
    applySavedEffect,
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;

  model.liveApplyEnabled = false;
  await controller.sceneItemSaved(
    saved,
    selected.config_entry_id,
    true,
    model.editorTransitionEpoch,
  );
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();

  model.liveApplyEnabled = true;
  model.section = "scenes";
  await controller.sceneItemSaved(
    saved,
    selected.config_entry_id,
    true,
    model.editorTransitionEpoch,
  );
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    configEntryId: selected.config_entry_id,
    name: saved.name,
    content: saved.content,
  }));
  expect(applySavedEffect).not.toHaveBeenCalled();

  submit.mockClear();
  await controller.sceneItemSaved(
    saved,
    "entry-b",
    false,
    model.editorTransitionEpoch,
  );
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();

  await controller.sceneItemSaved(
    saved,
    selected.config_entry_id,
    true,
    model.editorTransitionEpoch - 1,
  );
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();
});

test("manual Save adopts the saved content as the next Reset baseline", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  const source = item(painted());
  editorController.applyLibraryItem(source);
  editorController.updatePaintedContent({ speed: 65 }, "committed");
  controller.api = {
    updateItem: vi.fn().mockResolvedValue({
      ...source,
      version: 3,
      content: { ...painted(), speed: 65 },
    }),
  } as unknown as EffectStudioApi;

  expect(model.resetDirty).toBe(true);
  await controller.save();

  expect(model.resetDirty).toBe(false);
  expect(model.resetBaseline).toMatchObject({ speed: 65 });
});

test("Save As rebinds a copy to its content category", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const source = item(painted());
  model.currentItem = source;
  model.name = source.name;
  model.content = painted();
  model.savedBaseline = serialiseEditable(model.name, model.content);
  model.customEffectCategory = "my-effects";
  vi.spyOn(model, "customEffectCategoryAvailable").mockImplementation(
    (category) => category === "single-layer",
  );
  const { controller } = panelControllerHarness(model);
  controller.api = {
    createItem: vi.fn().mockResolvedValue({
      ...source,
      id: "item-copy",
      version: 1,
      name: "Saved paint copy",
    }),
  } as unknown as EffectStudioApi;

  await controller.saveAs("Saved paint copy");

  expect(model.currentItem?.id).toBe("item-copy");
  expect(model.customEffectCategory).toBe("single-layer");
  expect(model.editorSource).toMatchObject({
    kind: "saved",
    itemId: "item-copy",
  });
  expect(model.resetDirty).toBe(false);
});

test("Save As keeps video profile copies in the Video section", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.section = "video";
  const source: LibraryItem = {
    schema_version: 1,
    id: "video-source",
    version: 2,
    updated_at: "2026-08-18T00:00:00Z",
    name: "Cinema",
    content: videoProfile("H6199", "movie"),
    content_hash: "video-hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
  model.currentItem = source;
  model.name = source.name;
  model.content = source.content;
  const { controller } = panelControllerHarness(model);
  controller.api = {
    createItem: vi.fn().mockResolvedValue({
      ...source,
      id: "video-copy",
      version: 1,
      name: "Cinema copy",
    }),
  } as unknown as EffectStudioApi;

  await controller.saveAs("Cinema copy");

  expect(model.currentItem?.id).toBe("video-copy");
  expect(model.section).toBe("video");
});

test("Live-off pending Save persists without applying before navigation", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  editorController.updatePaintedContent({ speed: 72 }, "committed");
  const calls: string[] = [];
  controller.api = {
    updateItem: vi.fn().mockImplementation(async () => {
      calls.push("save");
      return {
        ...saved,
        version: saved.version + 1,
        content: { ...painted(), speed: 72 },
      };
    }),
    applySavedEffect: vi.fn().mockImplementation(async () => {
      calls.push("apply");
    }),
    device: vi.fn().mockResolvedValue(selected),
    updateUserState: vi.fn().mockImplementation(async () => {
      calls.push("navigate");
      return undefined;
    }),
  } as unknown as EffectStudioApi;

  await controller.selectSection("scenes");
  await controller.savePendingTransition();

  expect(model.section).toBe("scenes");
  expect(model.currentItem).toMatchObject({ id: saved.id, version: 3 });
  expect(calls).not.toContain("apply");
  expect(calls[0]).toBe("save");
  expect(model.pendingTransitionDialog).toBeUndefined();
});

test("manual Apply writes the current built-in draft without saving it", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installPaintCatalogue(model);
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  editorController.updatePaintedContent({ speed: 81 }, "committed");
  const applySnapshot = vi.fn().mockResolvedValue(undefined);
  const setTemplateDefault = vi.fn();
  controller.api = {
    applySnapshot,
    setTemplateDefault,
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;

  await expect(controller.applyCurrentDraft()).resolves.toBe(true);

  expect(applySnapshot).toHaveBeenCalledWith(
    selected.config_entry_id,
    "Paint",
    expect.objectContaining({ speed: 81 }),
    {
      origin_kind: "catalogue_template",
      origin_id: "template:paint",
    },
  );
  expect(setTemplateDefault).not.toHaveBeenCalled();
  expect(model.builtInDefaultDirty).toBe(true);
  applySnapshot.mockClear();
  editorController.updatePaintedContent({ effect: "twinkle" }, "committed");
  expect(model.previewCapability).toBe("unsupported");
  expect(model.content).toMatchObject({ effect: "twinkle" });
  await expect(controller.applyCurrentDraft()).resolves.toBe(false);
  expect(applySnapshot).not.toHaveBeenCalled();
});

test("Auto Save persists a built-in default without applying when Live is off", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = false;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  const savedContent = { ...painted(), speed: 81 };
  const setTemplateDefault = vi.fn().mockResolvedValue({
    template_id: "template:paint",
    content: savedContent,
    catalogue_content: painted(),
    has_default: true,
  });
  const applySnapshot = vi.fn();
  controller.api = {
    setTemplateDefault,
    applySnapshot,
  } as unknown as EffectStudioApi;

  editorController.updatePaintedContent({ speed: 81 }, "committed");
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(setTemplateDefault).toHaveBeenCalledOnce());

  expect(applySnapshot).not.toHaveBeenCalled();
  expect(model.builtInDefaultDirty).toBe(false);
});

test("disabling Live flushes a queued built-in Auto Save through persistence only", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openEditableTemplate(
    "Paint",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  const savedContent = { ...painted(), speed: 81 };
  editorController.updatePaintedContent({ speed: 81 }, "committed");
  const setTemplateDefault = vi.fn().mockResolvedValue({
    template_id: "template:paint",
    content: savedContent,
    catalogue_content: painted(),
    has_default: true,
  });
  const applySnapshot = vi.fn();
  controller.api = {
    setTemplateDefault,
    applySnapshot,
  } as unknown as EffectStudioApi;

  await controller.toggleLive();

  expect(model.liveApplyEnabled).toBe(false);
  expect(setTemplateDefault).toHaveBeenCalledWith(
    selected.config_entry_id,
    "template:paint",
    savedContent,
  );
  expect(applySnapshot).not.toHaveBeenCalled();
  expect(model.builtInDefaultDirty).toBe(false);
});

test("automatic save flushes before navigation and exposes failures to the transition dialog", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = true;
  installH6199Catalogue(model);
  model.customCatalogue!.models.H617A.painted_effects = [
    { id: "cycle", label: "Cycle" },
  ];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
  const { controller, editorController, modal, preview } = panelControllerHarness(model);
  const submit = vi.spyOn(preview, "submit");
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  let resolveSave!: (value: LibraryItem) => void;
  const saving = new Promise<LibraryItem>((resolve) => {
    resolveSave = resolve;
  });
  const updateItem = vi.fn().mockReturnValue(saving);
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  const loadDevice = vi.fn().mockResolvedValue(selected);
  controller.api = {
    updateItem,
    applySavedEffect,
    device: loadDevice,
  } as unknown as EffectStudioApi;
  editorController.updatePaintedContent({ speed: 62 }, "committed");

  const navigation = controller.selectSection("scenes");
  expect(model.section).toBe("custom");
  expect(model.autoSaveInProgress).toBe(true);
  resolveSave({
    ...saved,
    version: 3,
    content: { ...painted(), speed: 62 },
  });
  await navigation;

  expect(model.section).toBe("scenes");
  expect(model.autoSaveInProgress).toBe(false);
  expect(model.pendingTransitionDialog).toBeUndefined();
  expect(model.currentItem).toMatchObject({ id: saved.id, version: 3 });
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    configEntryId: selected.config_entry_id,
    name: saved.name,
    content: { ...painted(), speed: 62 },
  }));
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(loadDevice).not.toHaveBeenCalled();

  await controller.selectSection("custom", "single-layer");
  model.liveApplyEnabled = false;
  updateItem.mockRejectedValueOnce(new Error("storage unavailable"));
  editorController.updatePaintedContent({ speed: 63 }, "committed");
  controller.contentCommitted("committed");
  await vi.waitFor(() => expect(model.autoSaveFailed).toBe(true));
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: expect.stringContaining("storage unavailable"),
  });
  modal.closeError();
  expect(model.section).toBe("custom");
  expect(model.dirty).toBe(true);
  expect(model.localWorkNeedsProtection).toBe(true);
  await controller.selectSection("scenes");

  expect(model.section).toBe("custom");
  expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
});
