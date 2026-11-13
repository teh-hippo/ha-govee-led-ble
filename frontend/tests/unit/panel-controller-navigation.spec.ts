import { expect, test, vi } from "vitest";
import type { EffectStudioApi } from "../../src/api";
import { PanelController, restoredCustomEffectCategory } from "../../src/panel-controller";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import { activeStudioContext, editorDevicePath, synchroniseDeviceSelect } from "../../src/studio-navigation";
import { blankCustomEffect, blankPainted } from "../../src/effect-editor-model";
import { blankAdvancedContent } from "../../src/advanced-effect-model";
import { cloneBuiltInDefaultBaselines } from "../../src/built-in-default-state";
import type { CatalogueTemplateDefaultDetail, DeviceCapabilities, LibraryItem, ModelSku, PaintedContent, PaletteDiyEffectContent } from "../../src/types";
import { device, painted, videoProfile, installH6199Catalogue, item, panelModal, flowWorkspaceDevice, installFlowCatalogue, panelControllerHarness } from "./panel-test-support";

function templateDefaultDetail(
  templateId: string,
  model: ModelSku = "H6199",
): CatalogueTemplateDefaultDetail {
  const content =
    templateId.startsWith("template:video:")
      ? videoProfile(model, templateId.endsWith(":game") ? "game" : "movie")
      : templateId.startsWith("template:music:")
        ? {
            kind: "music_profile" as const,
            model,
            mode: templateId.slice("template:music:".length),
            sensitivity: model === "H6199" ? 100 : 99,
            colour: null,
            calm: null,
            parameters: {},
          }
        : model === "H6199"
          ? {
              kind: "palette_diy" as const,
              model,
              family: 1,
              variant: 0,
              speed: 50,
              palette: [[255, 0, 0] as [number, number, number]],
            }
          : blankPainted();
  return {
    template_id: templateId,
    content,
    catalogue_content: content,
    has_default: false,
  };
}

function workspaceModel(selected: DeviceCapabilities): PanelModel {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.section = "scenes";
  model.userState = {
    owner_id: "user-a",
    recent_colours: [],
    selected_config_entry_id: selected.config_entry_id,
    navigation: { section: "scenes" },
  };
  installFlowCatalogue(model);
  return model;
}

test.each(["cancel", "subscribe", "remember"])("a superseded device transition stops after %s", async (pause) => {
  const model = new PanelModel(() => undefined);
  model.devices = ["entry-a", "entry-b", "entry-c"].map(id => device(id, "H6199"));
  model.selectedDeviceId = "entry-a";
  model.liveApplyEnabled = false;
  const preview = new PanelPreviewController(model);
  const modal = panelModal(model);
  const editor = new PanelEditorController(model, preview, modal, {
    apiReady: () => true, selectItem: () => undefined,
    editorTransitionStarted: () => undefined, contentCommitted: () => undefined,
  });
  const replacePath = vi.fn();
  const controller = new PanelController(model, editor, preview, modal, {
    connected: () => true, pathname: () => "/ha-govee-led-ble", replacePath,
  });
  let release!: () => void;
  const blocked = new Promise<void>(resolve => { release = resolve; });
  let entered!: () => void;
  const waiting = new Promise<void>(resolve => { entered = resolve; });
  const wait = async () => { entered(); await blocked; };
  const unsubscribeB = vi.fn();
  const unsubscribeC = vi.fn();
  vi.spyOn(preview, "cancel").mockImplementation(async id => {
    if (pause === "cancel" && id === "entry-a") await wait();
  });
  const subscribeDevice = vi.fn(async id => {
    if (pause === "subscribe" && id === "entry-b") await wait();
    return id === "entry-b" ? unsubscribeB : unsubscribeC;
  });
  const updateUserState = vi.fn(async (id, navigation) => {
    if (pause === "remember" && id === "entry-b") await wait();
    return { owner_id: "user", recent_colours: [], selected_config_entry_id: id, navigation };
  });
  controller.api = { subscribeDevice, updateUserState } as unknown as EffectStudioApi;
  try {
    const toB = controller.deviceChanged("entry-b");
    await waiting;
    await controller.deviceChanged("entry-c");
    release();
    await toB;
    expect(model.selectedDeviceId).toBe("entry-c");
    expect(replacePath).toHaveBeenLastCalledWith(editorDevicePath("entry-c"));
    expect(model.userState?.selected_config_entry_id).toBe("entry-c");
    expect(subscribeDevice.mock.calls.filter(([id]) => id === "entry-c")).toHaveLength(1);
    expect(unsubscribeC).not.toHaveBeenCalled();
  } finally {
    release();
    controller.disconnect();
  }
});

test("subscription failure aborts armed transitions and overwrite confirmation", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "advanced" },
  };
  model.name = "Draft";
  model.content = blankAdvancedContent();
  model.resetBaseline = blankAdvancedContent();
  model.resetNameBaseline = "New Advanced effect";
  const { controller, modal } = panelControllerHarness(model);
  const execute = vi.fn();
  await controller.requestTransition(execute);
  const overwrite = modal.requestOverwrite("Existing");

  controller.stateUpdatesFailed(new Error("Connection lost."));
  await expect(overwrite).resolves.toBe(false);
  modal.closeError();
  await controller.declinePendingTransition();

  expect(execute).not.toHaveBeenCalled();
  expect(model.pendingTransitionDialog).toBeUndefined();
});

test("remembered All category migrates to the available fallback", () => {
  expect(
    restoredCustomEffectCategory(
      "all",
      (category) => category === "all",
      "music",
    ),
  ).toBe("music");
  expect(
    restoredCustomEffectCategory(
      "my-effects",
      () => false,
      "single-layer",
    ),
  ).toBe("single-layer");
});

test("opening the layered editor transfers scene-work ownership", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.sceneWorkDirty = true;
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller } = panelControllerHarness(model);
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

  await controller.openSceneEditor({
    content: scene,
    config_entry_id: selected.config_entry_id,
    name: "Layered scene",
  });
  await controller.declinePendingTransition();

  expect(model.sceneEditorOpen).toBe(true);
  expect(model.sceneWorkDirty).toBe(false);
  expect(model.editorSource.kind).toBe("scene");
});

test("category transitions stay blank without a matching active item", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.custom_effects = {
    painted: "unsupported",
    single: "unsupported",
    multi: "unsupported",
    palette_diy: "supported",
    advanced: "supported",
    workshop: "unsupported",
  };
  selected.profiles = { music: "supported", video: "supported" };
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.section = "video";
  installH6199Catalogue(model);
  const { controller, editorController, preview } = panelControllerHarness(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");

  const videoEpoch = editorController.beginSelectionTransition();
  editorController.openVideoTemplate("movie", "Movie", false, videoEpoch);
  expect(model.editorOwnedByActiveView).toBe(true);
  expect(templatePreview).not.toHaveBeenCalled();

  await controller.selectSection("custom", "single-layer");
  expect(model.name).toBe("");
  expect(model.editorSource.kind).toBe("none");
  expect(templatePreview).not.toHaveBeenCalled();

  await controller.selectSection("custom", "music");
  expect(model.editorSource.kind).toBe("none");
  expect(model.name).toBe("");
  expect(model.content.kind).not.toBe("palette_diy");

  editorController.openMusicTemplate("energetic", "Energetic");
  expect(model.editorAction("cancel")?.visible).toBe(false);
  editorController.openMusicTemplate("rhythm", "Rhythm");
  expect(model.editorAction("cancel")?.visible).toBe(false);

  await controller.selectSection("video");
  expect(model.name).toBe("");
  await controller.selectSection("custom", "music");
  expect(model.editorSource.kind).toBe("none");
  await controller.selectSection("custom", "single-layer");
  expect(model.name).toBe("");
  await controller.selectSection("video");
  expect(model.name).toBe("");
});

test("automatic restoration selects only a matching fresh native category", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.profiles = { music: "supported", video: "supported" };
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.userState = {
    owner_id: "user-a",
    recent_colours: [],
    selected_config_entry_id: selected.config_entry_id,
    navigation: { section: "scenes" },
  };
  installH6199Catalogue(model);
  const { controller, preview } = panelControllerHarness(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  let refreshed = structuredClone(selected);
  refreshed.active_state = {
    config_entry_id: selected.config_entry_id,
    mode: "scene",
    observed_at: "2026-08-23T00:00:00Z",
    confidence: "unknown",
    diy_code: null,
    effect: "candlelight",
    native_mode: "candlelight",
    matched_operation_id: null,
    active_effect: null,
  };
  selected.active_state = structuredClone(refreshed.active_state);
  const applySavedEffect = vi.fn();
  controller.api = {
    device: vi.fn().mockImplementation(async () => structuredClone(selected)),
    updateUserState: vi.fn().mockResolvedValue(model.userState),
    applySavedEffect,
    templateDefault: vi
      .fn()
      .mockImplementation(async (_deviceId: string, templateId: string) =>
        templateDefaultDetail(templateId, "H6199")),
  } as unknown as EffectStudioApi;

  await controller.openInitialContext();
  expect(model.sceneInitialSelection).toEqual({
    kind: "native",
    effect: "candlelight",
  });

  await controller.selectSection("video");
  expect(model.editorSource.kind).toBe("none");
  expect(model.name).toBe("");

  refreshed.active_state = {
    ...refreshed.active_state!,
    mode: "video",
    effect: null,
    native_mode: "movie",
  };
  selected.active_state = structuredClone(refreshed.active_state);
  await controller.selectSection("video");
  expect(model.templateSelection).toBe("template:video:movie");

  refreshed.active_state = {
    ...refreshed.active_state!,
    mode: "music",
    native_mode: "energetic",
  };
  selected.active_state = structuredClone(refreshed.active_state);
  await controller.selectSection("custom", "music");
  expect(model.templateSelection).toBe("template:music:energetic");
  expect(templatePreview).not.toHaveBeenCalled();
  expect(applySavedEffect).not.toHaveBeenCalled();
});

test("navigation does not request device refreshes", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.profiles = { music: "supported", video: "supported" };
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  const { controller } = panelControllerHarness(model);
  const deviceRefresh = vi.fn();
  controller.api = {
    device: deviceRefresh,
    updateUserState: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;

  await controller.selectSection("video");
  await controller.selectSection("custom", "music");

  expect(model.section).toBe("custom");
  expect(model.customEffectCategory).toBe("music");
  expect(model.editorSource.kind).toBe("none");
  expect(deviceRefresh).not.toHaveBeenCalled();
});

test("late device restoration cannot clear newer editor work", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const first = device("entry-a", "H617A");
  const second = device("entry-b", "H617A");
  model.devices = [first, second];
  model.selectedDeviceId = first.config_entry_id;
  installH6199Catalogue(model);
  const { controller, editorController } = panelControllerHarness(model);
  let finishRemembering!: () => void;
  const remembering = new Promise<void>((resolve) => {
    finishRemembering = resolve;
  });
  controller.api = {
    subscribeDevice: vi.fn().mockResolvedValue(() => undefined),
    updateUserState: vi.fn().mockReturnValue(remembering),
  } as unknown as EffectStudioApi;

  const changingDevice = controller.deviceChanged(second.config_entry_id);
  await Promise.resolve();
  await controller.selectSection("custom", "advanced");
  editorController.newCustomEffect("advanced");
  expect(model.editorSource.kind).toBe("new");

  finishRemembering();
  await changingDevice;

  expect(model.selectedDeviceId).toBe(second.config_entry_id);
  expect(model.section).toBe("custom");
  expect(model.customEffectCategory).toBe("advanced");
  expect(model.editorSource.kind).toBe("new");
  expect(model.content.kind).toBe("advanced");
});

test("Flow selection and edits survive Effects to Scenes to Effects navigation", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H617A");
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openEditableTemplate(
    "Flow",
    painted(),
    "template:single:1:0",
    { section: "custom", category: "single-layer" },
  );
  editorController.updatePaintedContent({ speed: 73 }, "committed");
  model.builtInBaselines = cloneBuiltInDefaultBaselines(
    painted(),
    model.content as PaintedContent,
    true,
  );

  await controller.selectSection("scenes");

  expect(model.section).toBe("scenes");
  expect(model.sceneInitialSelection).toEqual({ kind: "none" });
  expect(model.editorOwnedByActiveView).toBe(false);

  await controller.selectSection("custom", "single-layer");

  expect(model.section).toBe("custom");
  expect(model.templateSelection).toBe("template:single:1:0");
  expect(model.catalogueSourceLabel).toBe("Flow");
  expect(model.content).toMatchObject({ kind: "h617a_painted", speed: 73 });
  expect(model.editorOwnedByActiveView).toBe(true);
});

test("edited Flow workspace restores on initial load with catalogue Reset defaults", async () => {
  const model = workspaceModel(flowWorkspaceDevice("entry-a"));
  const { controller, editorController, preview } =
    panelControllerHarness(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  const editedPreview = vi.spyOn(preview, "scheduleEdited");

  await controller.openInitialContext();

  expect(model.section).toBe("custom");
  expect(model.customEffectCategory).toBe("single-layer");
  expect(model.templateSelection).toBe("template:single:1:0");
  expect(model.catalogueSourceLabel).toBe("Flow");
  expect(model.content).toMatchObject({
    kind: "palette_diy",
    family: 1,
    variant: 0,
    speed: 73,
    palette: [[12, 34, 56]],
  });
  expect(model.resetBaseline).toMatchObject({
    kind: "palette_diy",
    family: 1,
    variant: 0,
    speed: 50,
  });
  expect(templatePreview).not.toHaveBeenCalled();
  expect(editedPreview).not.toHaveBeenCalled();

  editorController.resetContent();
  expect(model.content).toMatchObject({
    kind: "palette_diy",
    family: 1,
    variant: 0,
    speed: 50,
  });
});

test("Effects to Scenes to Effects reopens the active Flow workspace", async () => {
  const model = workspaceModel(flowWorkspaceDevice("entry-a"));
  const { controller } = panelControllerHarness(model);
  await controller.openInitialContext();

  await controller.selectSection("scenes");
  if (model.content.kind !== "palette_diy") {
    throw new Error("Flow workspace content changed kind");
  }
  model.content = {
    ...model.content,
    speed: 99,
  };
  await controller.selectSection("custom", "single-layer");

  expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
  expect(model.section).toBe("scenes");
  await controller.declinePendingTransition();
  expect(model.section).toBe("custom");
  expect(model.templateSelection).toBe("template:single:1:0");
  expect(model.content).toMatchObject({
    kind: "palette_diy",
    speed: 73,
    palette: [[12, 34, 56]],
  });
});

test("device switching opens the target device Flow workspace", async () => {
  const first = device("entry-a", "H6199");
  const second = flowWorkspaceDevice("entry-b");
  const model = workspaceModel(first);
  model.devices = [first, second];
  const { controller, preview } = panelControllerHarness(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  controller.api = {
    subscribeDevice: vi.fn().mockResolvedValue(() => undefined),
    updateUserState: vi.fn().mockResolvedValue(model.userState),
    templateDefault: vi
      .fn()
      .mockImplementation(async (_deviceId: string, templateId: string) =>
        templateDefaultDetail(templateId, "H6199")),
  } as unknown as EffectStudioApi;

  await controller.deviceChanged(second.config_entry_id);

  expect(model.selectedDeviceId).toBe(second.config_entry_id);
  expect(model.section).toBe("custom");
  expect(model.templateSelection).toBe("template:single:1:0");
  expect(model.content).toMatchObject({
    kind: "palette_diy",
    speed: 73,
  });
  expect(templatePreview).not.toHaveBeenCalled();
});

test("page-style controller reinitialisation recovers the same Flow workspace", async () => {
  const payload = flowWorkspaceDevice("entry-a");
  const firstModel = workspaceModel(structuredClone(payload));
  const first = panelControllerHarness(firstModel);
  await first.controller.openInitialContext();

  const reloadedModel = workspaceModel(structuredClone(payload));
  const reloaded = panelControllerHarness(reloadedModel);
  const templatePreview = vi.spyOn(
    reloaded.preview,
    "scheduleTemplateSelection",
  );
  await reloaded.controller.openInitialContext();

  expect(reloadedModel.templateSelection).toBe("template:single:1:0");
  expect(reloadedModel.content).toEqual(firstModel.content);
  expect(reloadedModel.resetBaseline).toEqual(firstModel.resetBaseline);
  expect(templatePreview).not.toHaveBeenCalled();
});

test("workspace recovery infers only unambiguous structural identity", async () => {
  const inferredDevice = flowWorkspaceDevice("entry-a");
  if (!inferredDevice.active_workspace) {
    throw new Error("Flow device is missing its active workspace");
  }
  inferredDevice.active_workspace.origin = {
    kind: "authored",
    source_id: null,
  };
  const inferredModel = workspaceModel(inferredDevice);
  const inferred = panelControllerHarness(inferredModel);
  await inferred.controller.openInitialContext();
  expect(inferredModel.templateSelection).toBe("template:single:1:0");

  const ambiguousDevice = flowWorkspaceDevice("entry-ambiguous");
  ambiguousDevice.active_workspace!.origin = {
    kind: "authored",
    source_id: null,
  };
  ambiguousDevice.active_workspace!.selector_label = "Unsaved effect";
  const ambiguousModel = workspaceModel(ambiguousDevice);
  ambiguousModel.customCatalogue!.models.H6199.effects.push({
    ...ambiguousModel.customCatalogue!.models.H6199.effects[0],
    id: "duplicate-flow",
    label: "Duplicate Flow",
  });
  const ambiguous = panelControllerHarness(ambiguousModel);
  await ambiguous.controller.openInitialContext();
  expect(ambiguousModel.editorSource.kind).toBe("new");
  expect(ambiguousModel.templateSelection).toBeUndefined();
  expect(ambiguousModel.currentItem).toBeUndefined();
  expect(ambiguousModel.name).toBe("Unsaved effect");

  const invalidDevice = flowWorkspaceDevice("entry-b");
  if (!invalidDevice.active_workspace) {
    throw new Error("Flow device is missing its active workspace");
  }
  invalidDevice.active_workspace.origin.source_id =
    "template:single:999:0";
  const invalidModel = workspaceModel(invalidDevice);
  const invalid = panelControllerHarness(invalidModel);
  await invalid.controller.openInitialContext();

  expect(invalidModel.editorSource.kind).toBe("none");
  expect(invalidModel.name).toBe("");
});

test("painted workspace restoration keeps variation content under the fixed Paint identity", async () => {
  const selected = device("entry-painted", "H617A");
  const workspaceContent: PaintedContent = {
    ...painted(),
    effect: "clockwise",
    speed: 64,
    brightness: 83,
  };
  selected.active_workspace = {
    config_entry_id: selected.config_entry_id,
    model: selected.model,
    selector_label: "Clockwise",
    content: workspaceContent,
    content_hash: "painted-workspace",
    origin: { kind: "authored", source_id: null },
    observable_signature: "custom:1",
    updated_at: "2026-08-26T00:00:00Z",
    generation: 1,
    confidence: "write_completed",
  };
  const model = workspaceModel(selected);
  model.customCatalogue!.models.H617A.painted_effects = [
    { id: "cycle", label: "Cycle" },
    { id: "clockwise", label: "Clockwise" },
    { id: "twinkle", label: "Twinkle" },
  ];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
  const { controller } = panelControllerHarness(model);

  await controller.openInitialContext();

  expect(model.templateSelection).toBe("template:paint");
  expect(model.editorSource).toMatchObject({
    kind: "catalogue",
    selectionIdentity: "template:paint",
    label: "Paint",
  });
  expect(model.catalogueSourceLabel).toBe("Paint");
  expect(model.name).toBe("Paint");
  expect(model.content).toEqual(workspaceContent);
  expect(model.resetBaseline).toEqual(blankCustomEffect("h617a_painted", model.modelCatalogue!));
});

test("active workspace does not open a category disabled by options", async () => {
  const selected = flowWorkspaceDevice("entry-a");
  selected.effect_categories = ["scenes"];
  const model = workspaceModel(selected);
  const { controller } = panelControllerHarness(model);

  await controller.openInitialContext();

  expect(model.section).toBe("scenes");
  expect(model.customEffectsAvailable).toBe(false);
  expect(model.editorSource.kind).toBe("none");
  expect(model.name).toBe("");
});

test("initial load and device switching navigate to each active context", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const first = device("entry-a", "H6199");
  first.profiles.video = "supported";
  first.active_state = {
    config_entry_id: first.config_entry_id,
    mode: "video",
    observed_at: "2026-08-25T00:00:00Z",
    confidence: "unknown",
    diy_code: null,
    effect: null,
    native_mode: "movie",
    matched_operation_id: null,
    active_effect: null,
  };
  const second = device("entry-b", "H6199");
  second.active_state = {
    config_entry_id: second.config_entry_id,
    mode: "scene",
    observed_at: "2026-08-25T00:00:01Z",
    confidence: "unknown",
    diy_code: null,
    effect: "Candlelight",
    native_mode: "Candlelight",
    matched_operation_id: null,
    active_effect: null,
  };
  model.devices = [first, second];
  model.selectedDeviceId = first.config_entry_id;
  model.userState = {
    owner_id: "user-a",
    recent_colours: [],
    selected_config_entry_id: first.config_entry_id,
    navigation: { section: "scenes" },
  };
  installH6199Catalogue(model);
  const { controller } = panelControllerHarness(model);
  controller.api = {
    subscribeDevice: vi.fn().mockResolvedValue(() => undefined),
    updateUserState: vi.fn().mockResolvedValue(model.userState),
    templateDefault: vi
      .fn()
      .mockImplementation(async (_deviceId: string, templateId: string) =>
        templateDefaultDetail(templateId, "H6199")),
  } as unknown as EffectStudioApi;

  await controller.openInitialContext();

  expect(model.section).toBe("video");
  expect(model.templateSelection).toBe("template:video:movie");

  await controller.deviceChanged(second.config_entry_id);

  expect(model.section).toBe("scenes");
  expect(model.sceneInitialSelection).toEqual({
    kind: "native",
    effect: "Candlelight",
  });
  expect(model.editorSource.kind).toBe("none");
});

test("a library subscription reload cannot clobber a mid-flight local edit", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const { controller, editorController } = panelControllerHarness(model);
  const source = item(painted());
  editorController.applyLibraryItem(source);
  let resolveRemote!: (value: LibraryItem) => void;
  const remoteItem = new Promise<LibraryItem>((resolve) => {
    resolveRemote = resolve;
  });
  controller.api = {
    item: vi.fn().mockReturnValue(remoteItem),
  } as unknown as EffectStudioApi;
  const remote = {
    ...source,
    version: source.version + 1,
    updated_at: "2026-08-25T00:00:00Z",
    content: { ...source.content, speed: 55 },
  };

  const reload = controller.libraryChanged({
    items: [
      {
        id: remote.id,
        version: remote.version,
        updated_at: remote.updated_at,
        name: remote.name,
        kind: remote.content.kind,
        content_hash: remote.content_hash,
        origin: remote.origin,
      },
    ],
  });
  await Promise.resolve();
  editorController.updatePaintedContent({ speed: 73 }, "committed");
  resolveRemote(remote);
  await reload;

  expect(model.currentItem?.version).toBe(source.version);
  expect(model.content).toMatchObject({ kind: "h617a_painted", speed: 73 });
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: "This effect changed elsewhere. Reload it before saving.",
  });
});

test("older library generations cannot replace newer subscription state", async () => {
  const model = new PanelModel(() => undefined);
  const { controller } = panelControllerHarness(model);
  model.library = {
    generation: 4,
    items: [
      {
        id: "newer",
        version: 1,
        updated_at: "2026-08-27T00:00:00Z",
        name: "Newer",
        kind: "advanced",
        content_hash: "4".repeat(64),
        origin: { kind: "authored", source_id: null },
      },
    ],
  };

  await expect(
    controller.libraryChanged({
      generation: 3,
      items: [],
    }),
  ).resolves.toBe(false);

  expect(model.library.generation).toBe(4);
  expect(model.library.items.map((item) => item.id)).toEqual(["newer"]);
});

test("inactive retained editors clear silently when a scene overwrite changes their item", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const { controller, editorController } = panelControllerHarness(model);
  const source = item(painted());
  editorController.applyLibraryItem(source);
  model.section = "scenes";

  await controller.libraryChanged({
    generation: 1,
    items: [
      {
        id: source.id,
        version: source.version + 1,
        updated_at: "2026-08-27T00:00:00Z",
        name: source.name,
        kind: "scene_builtin",
        content_hash: "5".repeat(64),
        origin: source.origin,
      },
    ],
  });

  expect(model.currentItem).toBeUndefined();
  expect(model.editorSource.kind).toBe("none");
  expect(model.modalState).toBeUndefined();
});

test("automatic saved restoration reads without applying, previewing, or saving", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = true;
  const selected = device("entry-a", "H617A");
  const saved = item(painted());
  const summary = {
    id: saved.id,
    version: saved.version,
    updated_at: saved.updated_at,
    name: saved.name,
    kind: saved.content.kind,
    content_hash: saved.content_hash,
    origin: saved.origin,
  };
  selected.active_state = {
    config_entry_id: selected.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-23T00:00:00Z",
    confidence: "activation_match",
    diy_code: 800,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-a",
    active_effect: {
      source_kind: "saved_effect",
      selector_label: saved.name,
      content_hash: saved.content_hash,
      origin: saved.origin,
      observable_signature: "custom:800",
      confidence: "activation_match",
      item_id: saved.id,
      item_version: saved.version,
    },
  };
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  model.customCatalogue!.models.H617A.painted_effects = [
    { id: "cycle", label: "Cycle" },
  ];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
  model.library = { items: [summary] };
  model.userState = {
    owner_id: "user-a",
    recent_colours: [],
    selected_config_entry_id: selected.config_entry_id,
    navigation: {
      section: "custom",
      custom_category: "single-layer",
      auto_save: true,
    },
  };
  const preview = new PanelPreviewController(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  const modal = panelModal(model);
  const contentCommitted = vi.fn();
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted,
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
  const applySavedEffect = vi.fn();
  const updateItem = vi.fn();
  const createItem = vi.fn();
  controller.api = {
    device: vi.fn().mockResolvedValue(selected),
    item: vi.fn().mockResolvedValue(saved),
    applySavedEffect,
    updateItem,
    createItem,
  } as unknown as EffectStudioApi;

  await controller.openInitialContext();

  expect(model.currentItem?.id).toBe(saved.id);
  expect(model.editorSource.kind).toBe("saved");
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(templatePreview).not.toHaveBeenCalled();
  expect(contentCommitted).not.toHaveBeenCalled();
  expect(updateItem).not.toHaveBeenCalled();
  expect(createItem).not.toHaveBeenCalled();
});

test("initial navigation preserves unavailable deep links without a feedback banner", async () => {
  const model = new PanelModel(() => undefined);
  model.devices = [device("entry-a", "H617A")];
  model.userState = {
    owner_id: "user-a",
    recent_colours: [],
    selected_config_entry_id: "entry-a",
    navigation: {},
  };
  const preview = new PanelPreviewController(model);
  const modal = panelModal(model);
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: (itemId) => void controller.selectItem(itemId),
    editorTransitionStarted: () => undefined,
    contentCommitted: () => undefined,
  });
  controller = new PanelController(
    model,
    editorController,
    preview,
    modal,
    {
      connected: () => true,
      pathname: () => "/ha-govee-led-ble/editor/unavailable",
      replacePath: () => undefined,
    },
  );

  expect(await controller.initialiseSelectedDevice()).toBeUndefined();
  expect(model.selectedDeviceId).toBe("unavailable");
  expect(model.notice).toBeUndefined();
});

test("dirty saved transitions prompt before mutation and Cancel is inert", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = true;
  const { controller, editorController } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  editorController.updatePaintedContent({ speed: 67 }, "committed");
  const before = {
    epoch: model.editorTransitionEpoch,
    section: model.section,
    device: model.selectedDeviceId,
    source: structuredClone(model.editorSource),
    content: structuredClone(model.content),
  };

  await controller.selectSection("scenes");

  expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
  expect(model.editorTransitionEpoch).toBe(before.epoch);
  expect(model.section).toBe(before.section);
  expect(model.selectedDeviceId).toBe(before.device);
  expect(model.editorSource).toEqual(before.source);
  expect(model.content).toEqual(before.content);

  controller.cancelPendingTransition();

  expect(model.pendingTransitionDialog).toBeUndefined();
  expect(model.editorTransitionEpoch).toBe(before.epoch);
  expect(model.section).toBe(before.section);
  expect(model.editorSource).toEqual(before.source);
  expect(model.content).toEqual(before.content);
});

test("Live-on No and reload present an authored Sena workspace as structural Flow", async () => {
  const selected = flowWorkspaceDevice("entry-a");
  selected.active_state!.active_effect = null;
  selected.active_workspace = {
    ...selected.active_workspace!,
    selector_label: "Sena",
    origin: { kind: "authored", source_id: null },
  };
  const model = workspaceModel(selected);
  model.section = "custom";
  model.customEffectCategory = "single-layer";
  model.liveApplyEnabled = true;
  const { controller, editorController } = panelControllerHarness(model);
  const saved: LibraryItem = {
    schema_version: 1,
    id: "sena",
    version: 4,
    updated_at: "2026-08-25T00:00:00Z",
    name: "Sena",
    content: {
      ...selected.active_workspace!.content,
      speed: 68,
    } as PaletteDiyEffectContent,
    content_hash: "s".repeat(64),
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
  editorController.applyLibraryItem(saved);
  if (model.content.kind !== "palette_diy") {
    throw new Error("saved content changed kind");
  }
  editorController.customContentChanged(
    { ...model.content, speed: 91 },
    "committed",
  );
  const updateItem = vi.fn();
  const applySavedEffect = vi.fn();
  controller.api = {
    updateItem,
    applySavedEffect,
    updateUserState: vi.fn().mockResolvedValue(model.userState),
  } as unknown as EffectStudioApi;

  await controller.selectSection("scenes");
  await controller.declinePendingTransition();
  await controller.selectSection("custom", "single-layer");

  expect(updateItem).not.toHaveBeenCalled();
  expect(applySavedEffect).not.toHaveBeenCalled();
  expect(model.editorSource.kind).toBe("catalogue");
  expect(model.templateSelection).toBe("template:single:1:0");
  expect(model.name).toBe("Flow");
  expect(model.catalogueSourceLabel).toBe("Flow");
  expect(model.currentItem).toBeUndefined();
  expect(model.content).toMatchObject({ speed: 73 });
  expect(model.resetBaseline).toMatchObject({ speed: 50 });

  const reloadedModel = workspaceModel(structuredClone(selected));
  const reloaded = panelControllerHarness(reloadedModel);
  await reloaded.controller.openInitialContext();

  expect(reloadedModel.templateSelection).toBe("template:single:1:0");
  expect(reloadedModel.editorSource).toMatchObject({
    kind: "catalogue",
    label: "Flow",
    selectionIdentity: "template:single:1:0",
  });
  expect(reloadedModel.name).toBe("Flow");
  expect(reloadedModel.currentItem).toBeUndefined();
  expect(reloadedModel.content).toMatchObject({ speed: 73 });
  expect(reloadedModel.resetBaseline).toMatchObject({ speed: 50 });
});

test("catalogue default drafts are protected regardless of Live state", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.openEditableTemplate(
    "Flow",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  editorController.updatePaintedContent({ speed: 81 }, "committed");

  model.liveApplyEnabled = true;
  await controller.selectSection("scenes");
  expect(model.pendingTransitionDialog).toMatchObject({
    primaryLabel: "Save",
    requiresName: false,
  });
  expect(model.section).toBe("custom");
  await controller.declinePendingTransition();
  expect(model.section).toBe("scenes");

  await controller.selectSection("custom", "single-layer");
  editorController.openEditableTemplate(
    "Flow",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  editorController.updatePaintedContent({ speed: 81 }, "committed");
  model.liveApplyEnabled = false;
  await controller.selectSection("scenes");
  expect(model.pendingTransitionDialog).toMatchObject({
    primaryLabel: "Save",
    saveName: "Flow",
    requiresName: false,
  });
  const savedContent = { ...painted(), speed: 81 };
  const setTemplateDefault = vi.fn().mockResolvedValue({
    template_id: "template:paint",
    content: savedContent,
    catalogue_content: painted(),
    has_default: true,
  });
  controller.api = {
    setTemplateDefault,
  } as unknown as EffectStudioApi;

  await controller.savePendingTransition();

  expect(setTemplateDefault).toHaveBeenCalledWith(
    selected.config_entry_id,
    "template:paint",
    savedContent,
  );
  expect(model.section).toBe("scenes");
});

test("unload protection covers only unrecoverable work", () => {
  const model = new PanelModel(() => undefined);
  const { controller, editorController } = panelControllerHarness(model);
  model.isAdmin = true;
  editorController.openEditableTemplate(
    "Flow",
    painted(),
    "template:paint",
    { section: "custom", category: "single-layer" },
  );
  editorController.updatePaintedContent({ speed: 75 }, "committed");

  model.liveApplyEnabled = true;
  expect(controller.unloadProtectionRequired).toBe(true);
  model.liveApplyEnabled = false;
  expect(controller.unloadProtectionRequired).toBe(true);

  editorController.applyLibraryItem(item(painted()));
  editorController.updatePaintedContent({ speed: 76 }, "committed");
  model.liveApplyEnabled = true;
  expect(controller.unloadProtectionRequired).toBe(true);
});

test("Live-off No discards local saved edits and reopens the clean active item", async () => {
  const selected = device("entry-a", "H617A");
  const saved = item(painted());
  const summary = { ...saved, kind: saved.content.kind };
  selected.active_state = {
    config_entry_id: selected.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-26T00:00:00Z",
    confidence: "activation_match",
    diy_code: 24,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-sena",
    active_effect: {
      source_kind: "saved_effect",
      selector_label: saved.name,
      content_hash: saved.content_hash,
      origin: saved.origin,
      observable_signature: "custom:24",
      confidence: "activation_match",
      item_id: saved.id,
      item_version: saved.version,
    },
  };
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.library = { items: [summary] };
  model.liveApplyEnabled = false;
  installH6199Catalogue(model);
  model.customCatalogue!.models.H617A.painted_effects = [
    { id: "cycle", label: "Cycle" },
  ];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
  const { controller, editorController } = panelControllerHarness(model);
  editorController.applyLibraryItem(saved);
  editorController.updatePaintedContent({ speed: 92 }, "committed");
  const loadItem = vi.fn().mockResolvedValue(saved);
  controller.api = {
    item: loadItem,
    updateUserState: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;

  await controller.selectSection("scenes");
  await controller.declinePendingTransition();
  expect(model.libraryItemAvailable(summary)).toBe(true);
  expect(
    activeStudioContext(
      selected,
      model.library.items,
      (candidate) => model.libraryItemAvailable(candidate),
      model.modelCatalogue,
    ).kind,
  ).toBe("saved");
  expect(model.section).toBe("scenes");
  expect(model.customEffectsAvailable).toBe(true);
  await controller.selectSection("custom", "single-layer");

  expect(model.section).toBe("custom");
  expect(loadItem).toHaveBeenCalledWith(saved.id);
  expect(model.editorSource).toMatchObject({
    kind: "saved",
    itemId: saved.id,
  });
  expect(model.content).toMatchObject({ speed: 50 });
  expect(model.dirty).toBe(false);
});

test("guarded Home Assistant navigation redispatches once after resolution", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.applyLibraryItem(item(painted()));
  editorController.updatePaintedContent({ speed: 84 }, "committed");
  const redispatch = vi.fn();

  await controller.requestTransition(redispatch);
  expect(redispatch).not.toHaveBeenCalled();

  controller.cancelPendingTransition();
  expect(redispatch).not.toHaveBeenCalled();

  await controller.requestTransition(redispatch);
  await controller.declinePendingTransition();
  expect(redispatch).toHaveBeenCalledOnce();
});

test("device, item, scene, and New transitions share the pre-mutation guard", async () => {
  const first = device("entry-a", "H617A");
  const second = device("entry-b", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [first, second];
  model.selectedDeviceId = first.config_entry_id;
  installH6199Catalogue(model);
  model.customCatalogue!.models.H617A.painted_effects = [
    { id: "cycle", label: "Cycle" },
  ];
  model.customCatalogue!.models.H617A.apply.painted = "supported";
  const { controller, editorController } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  editorController.updatePaintedContent({ speed: 86 }, "committed");
  const epoch = model.editorTransitionEpoch;
  const sceneSelection = vi.fn();
  const requests = [
    () => controller.deviceChanged(second.config_entry_id),
    () =>
      controller.selectCustomEffectEntry({
        kind: "paint",
        key: "template:paint",
        label: "Paint",
        category: "single-layer",
      }),
    () => controller.newCustomEffect("single-layer"),
    () => controller.selectScene(sceneSelection),
  ];

  for (const request of requests) {
    await request();
    expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
    expect(model.editorTransitionEpoch).toBe(epoch);
    expect(model.selectedDeviceId).toBe(first.config_entry_id);
    expect(model.editorSource).toMatchObject({
      kind: "saved",
      itemId: saved.id,
    });
    expect(sceneSelection).not.toHaveBeenCalled();
    controller.cancelPendingTransition();
  }
});

test("video template selection is guarded and restores focus on Cancel", async () => {
  const selected = device("entry-a", "H6199");
  selected.profiles.video = "supported";
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.section = "video";
  installH6199Catalogue(model);
  const { controller, editorController } = panelControllerHarness(model);
  controller.api = {
    templateDefault: vi
      .fn()
      .mockImplementation(async (_deviceId: string, templateId: string) =>
        templateDefaultDetail(templateId, "H6199")),
  } as unknown as EffectStudioApi;
  const content = videoProfile("H6199", "movie");
  const saved: LibraryItem = {
    schema_version: 1,
    id: "saved-video",
    version: 2,
    updated_at: "2026-08-26T00:00:00Z",
    name: "Saved movie",
    content,
    content_hash: "video-hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
  editorController.applyLibraryItem(saved);
  editorController.videoContentChanged(
    { ...content, saturation: 77 },
    "committed",
  );
  const focus = vi.fn();
  const returnFocus = {
    isConnected: true,
    focus,
  } as unknown as HTMLElement;
  const epoch = model.editorTransitionEpoch;

  await controller.selectVideoTemplate("template:video:game", "Game", returnFocus);

  expect(model.pendingTransitionDialog?.primaryLabel).toBe("Save");
  expect(model.editorTransitionEpoch).toBe(epoch);
  expect(model.content).toMatchObject({
    kind: "video_profile",
    mode: "movie",
    saturation: 77,
  });

  controller.cancelPendingTransition();
  await Promise.resolve();
  expect(focus).toHaveBeenCalledOnce();

  await controller.selectVideoTemplate("template:video:game", "Game", returnFocus);
  await controller.declinePendingTransition();
  expect(model.editorSource.kind).toBe("catalogue");
  expect(model.templateSelection).toBe("template:video:game");
  expect(model.content).toMatchObject({
    kind: "video_profile",
    mode: "game",
  });
});

test("cancelled device selection restores the visible value and remains operable", async () => {
  const first = device("entry-a", "H617A");
  const second = device("entry-b", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [first, second];
  model.selectedDeviceId = first.config_entry_id;
  const { controller, editorController } = panelControllerHarness(model);
  editorController.applyLibraryItem(item(painted()));
  editorController.updatePaintedContent({ speed: 87 }, "committed");
  const select = { value: second.config_entry_id };

  await controller.deviceChanged(second.config_entry_id);
  synchroniseDeviceSelect(select, model.selectedDeviceId);
  expect(select.value).toBe(first.config_entry_id);
  expect(model.pendingTransitionDialog).toBeDefined();

  controller.cancelPendingTransition();
  synchroniseDeviceSelect(select, model.selectedDeviceId);
  expect(select.value).toBe(first.config_entry_id);

  select.value = second.config_entry_id;
  await controller.deviceChanged(second.config_entry_id);
  synchroniseDeviceSelect(select, model.selectedDeviceId);
  expect(select.value).toBe(first.config_entry_id);
  await controller.declinePendingTransition();
  synchroniseDeviceSelect(select, model.selectedDeviceId);
  expect(select.value).toBe(second.config_entry_id);

  await controller.deviceChanged(first.config_entry_id);
  synchroniseDeviceSelect(select, model.selectedDeviceId);
  expect(select.value).toBe(first.config_entry_id);
});

test("external editor teardown clears controller-owned pending transitions", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  editorController.updatePaintedContent({ speed: 88 }, "committed");

  await controller.requestTransition(() => undefined);
  expect(model.pendingTransitionDialog).toBeDefined();

  editorController.beginTransition();
  expect(model.pendingTransitionDialog).toBeUndefined();
  editorController.applyLibraryItem(saved);

  const navigate = vi.fn();
  await controller.requestTransition(navigate);
  expect(navigate).toHaveBeenCalledOnce();
});
