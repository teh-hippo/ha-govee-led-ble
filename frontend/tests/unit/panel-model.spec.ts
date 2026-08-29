import { expect, test, vi } from "vitest";

import type { EffectStudioApi } from "../../src/api";
import {
  PanelController,
  restoredAutoSave,
  restoredCustomEffectCategory,
} from "../../src/panel-controller";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModalController } from "../../src/panel-modal-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import {
  activeStudioContext,
  synchroniseDeviceSelect,
} from "../../src/studio-navigation";
import {
  blankPainted,
  blankVideoProfile,
  serialiseEditable,
} from "../../src/effect-editor-model";
import { blankAdvancedContent } from "../../src/advanced-effect-model";
import { cloneBuiltInDefaultBaselines } from "../../src/built-in-default-state";
import type {
  CustomEffectCatalogue,
  CatalogueTemplateDefaultDetail,
  DeviceCapabilities,
  HomeAssistant,
  LibraryItem,
  ModelEffectCatalogue,
  ModelSku,
  MusicProfileContent,
  PaintedContent,
  PaletteDiyEffectContent,
} from "../../src/types";

function device(
  id: string,
  model: ModelSku,
): DeviceCapabilities {
  return {
    config_entry_id: id,
    light_entity_id: `light.${id}`,
    model,
    display_name: id,
    segment_count: 15,
    custom_effects: {
      painted: "supported",
      single: "unsupported",
      multi: "unsupported",
      palette_diy: "unsupported",
      advanced: "unsupported",
      workshop: "unsupported",
    },
    profiles: {
      music: "unsupported",
      video: "unsupported",
    },
    readback: "supported",
    preview_health: {
      config_entry_id: id,
      revision: 0,
      phase: "healthy",
      incident_id: null,
      error_code: null,
      error_message: null,
      write_disposition: "not_started",
      checked_at: "2026-08-24T00:00:00Z",
    },
    effect_categories: [
      "scenes",
      "video",
      "effects",
      "multi_layered",
      "reactive",
      "advanced",
    ],
    active_state: null,
  };
}

function painted(): PaintedContent {
  return {
    kind: "h617a_painted",
    effect: "cycle",
    speed: 50,
    brightness: 100,
    segments: [
      [1, 2, 3],
      ...Array.from({ length: 14 }, () => null),
    ],
  };
}

function templateDefaultDetail(
  templateId: string,
  model: ModelSku = "H6199",
): CatalogueTemplateDefaultDetail {
  const content =
    templateId.startsWith("template:video:")
      ? blankVideoProfile(templateId.endsWith(":game") ? "game" : "movie")
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

function h6199Catalogue(): ModelEffectCatalogue {
  return {
    sku: "H6199",
    painted_effects: [],
    effects: [
      {
        id: "fade",
        label: "Fade",
        family: 1,
        variations: [{ id: "base", label: "Base", variant: 0 }],
        supports_multi: false,
        rate: "speed",
        category: "single_layer",
      },
    ],
    music_modes: [
      { id: "energetic", label: "Energetic" },
      { id: "rhythm", label: "Rhythm" },
    ],
    video_modes: [
      { id: "movie", label: "Movie" },
      { id: "game", label: "Game" },
    ],
    workshop_templates: [],
    workflows: [],
    supports: {
      multi: "unsupported",
      advanced: "supported",
      workshop: "unsupported",
    },
    limits: {
      palette_min: 1,
      palette_max: 8,
      multi_max: 5,
      music_sensitivity_min: 0,
      music_sensitivity_max: 100,
    },
    apply: {
      painted: "unsupported",
      single: "unsupported",
      multi: "unsupported",
      palette_diy: "supported",
      workshop: "unsupported",
    },
  };
}

function installH6199Catalogue(model: PanelModel): void {
  const catalogue = h6199Catalogue();
  model.customCatalogue = {
    ...catalogue,
    schema_version: 9,
    sku: "H617A",
    models: {
      H6125: {
        ...catalogue,
        sku: "H6125",
        painted_effects: [],
        effects: [],
        music_modes: [],
        video_modes: [],
        templates: [],
        workshop_templates: [],
      },
      H617A: { ...catalogue, sku: "H617A" },
      H617E: { ...catalogue, sku: "H617E" },
      H6199: catalogue,
    },
  } as CustomEffectCatalogue;
}

function item(content: PaintedContent): LibraryItem {
  return {
    schema_version: 1,
    id: "item-1",
    version: 2,
    updated_at: "2026-08-18T00:00:00Z",
    name: "Saved paint",
    content,
    content_hash: "hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
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

function editor(model: PanelModel): PanelEditorController {
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  return new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: () => undefined,
  });
}

function flowWorkspaceDevice(id: string): DeviceCapabilities {
  const selected = device(id, "H6199");
  selected.custom_effects.palette_diy = "supported";
  const content: PaletteDiyEffectContent = {
    kind: "palette_diy",
    model: "H6199",
    family: 1,
    variant: 0,
    speed: 73,
    palette: [[12, 34, 56]],
  };
  selected.active_state = {
    config_entry_id: selected.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-25T00:00:00Z",
    confidence: "write_completed",
    diy_code: 601,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-flow",
    active_effect: {
      source_kind: "snapshot",
      selector_label: "Flow",
      content_hash: "a".repeat(64),
      origin: {
        kind: "catalogue_template",
        source_id: "template:single:1:0",
      },
      observable_signature: "custom:601",
      confidence: "write_completed",
      item_id: null,
      item_version: null,
    },
  };
  selected.active_workspace = {
    config_entry_id: selected.config_entry_id,
    model: selected.model,
    selector_label: "Flow",
    content,
    content_hash: "a".repeat(64),
    origin: {
      kind: "catalogue_template",
      source_id: "template:single:1:0",
    },
    observable_signature: "custom:601",
    updated_at: "2026-08-25T00:00:00Z",
    generation: 1,
    confidence: "write_completed",
  };
  return selected;
}

function installFlowCatalogue(model: PanelModel): void {
  installH6199Catalogue(model);
  model.customCatalogue!.models.H6199.effects[0] = {
    ...model.customCatalogue!.models.H6199.effects[0],
    id: "flow",
    label: "Flow",
  };
}

function panelControllerHarness(
  model: PanelModel,
  saveSceneWork?: () => Promise<boolean>,
) {
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
      saveSceneWork,
    },
  );
  return { controller, editorController, preview, modal };
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

test("derives selected-device and preview decisions from panel state", () => {
  const model = new PanelModel(() => undefined);
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  model.isAdmin = true;

  expect(model.selectedDevice?.display_name).toBe("entry-a");
  expect(model.selectedModel).toBe("H617A");
  expect(model.previewCapability).toBe("supported");
  expect(model.showDeviceSelector).toBe(false);

  model.selectedDeviceId = "missing";
  expect(model.selectedDevice).toBeUndefined();
  expect(model.showDeviceSelector).toBe(true);
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

test("administrator state follows late Home Assistant user updates", () => {
  const changed = vi.fn();
  const model = new PanelModel(changed);

  model.syncAdmin({ user: undefined } as unknown as HomeAssistant);
  expect(model.isAdmin).toBe(false);

  model.syncAdmin({
    user: { is_admin: true },
  } as unknown as HomeAssistant);
  expect(model.isAdmin).toBe(true);
  expect(changed).toHaveBeenCalledOnce();
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

test("save and effect-family controls distinguish starters, New drafts, and saved effects", () => {
  const model = new PanelModel(() => undefined);
  model.name = "Jumping";
  model.content = painted();
  model.savedBaseline = serialiseEditable(model.name, model.content);
  model.editorSource = {
    kind: "catalogue",
    owner: { section: "custom", category: "single-layer" },
    selectionIdentity: "template:paint",
    label: "Paint",
  };

  expect(model.dirty).toBe(false);
  expect(model.canSaveCurrentDraft).toBe(false);
  expect(model.showSingleEffectSelector).toBe(false);

  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "single-layer" },
  };
  expect(model.showSingleEffectSelector).toBe(true);

  model.currentItem = item(painted());
  model.editorSource = {
    kind: "saved",
    owner: { section: "custom", category: "single-layer" },
    itemId: model.currentItem.id,
  };
  expect(model.showSingleEffectSelector).toBe(true);
  expect(model.canSaveCurrentDraft).toBe(false);
});

test("unchanged explicit New drafts save directly with the header name", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.name = "Jumping";
  model.content = painted();
  model.savedBaseline = serialiseEditable(model.name, model.content);
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "single-layer" },
  };
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const save = vi.fn();

  modal.requestSave(save);

  expect(save).toHaveBeenCalledOnce();
  expect(model.saveNameDialogOpen).toBe(false);
});

test("Save As retains the dedicated naming dialog", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const saveAs = vi.fn().mockResolvedValue(true);

  modal.requestSaveAs({} as HTMLElement, "Jumping copy");
  expect(model.saveNameDialogOpen).toBe(true);
  expect(model.saveNameValue).toBe("Jumping copy");

  await modal.confirmNamedSave(saveAs);
  expect(saveAs).toHaveBeenCalledWith("Jumping copy");
  expect(model.saveNameDialogOpen).toBe(false);
});

test("Save As overwrite cancellation resumes naming and preserves return focus", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const focus = vi.fn();
  const returnFocus = {
    isConnected: true,
    focus,
  } as unknown as HTMLElement;

  modal.requestSaveAs(returnFocus, "Existing");
  const save = vi.fn(async () => {
    const overwrite = modal.requestOverwrite("Existing");
    modal.cancelOverwrite();
    return overwrite;
  });

  await modal.confirmNamedSave(save);

  expect(model.saveNameDialogOpen).toBe(true);
  expect(model.saveNameValue).toBe("Existing");
  modal.cancelSaveName();
  await Promise.resolve();
  expect(focus).toHaveBeenCalledOnce();
});

test("busy Save As ignores cancellation until persistence finishes", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let resolveSave!: (saved: boolean) => void;
  const saving = new Promise<boolean>((resolve) => {
    resolveSave = resolve;
  });

  modal.requestSaveAs({} as HTMLElement, "Existing");
  const operation = modal.confirmNamedSave(() => saving);
  await Promise.resolve();
  modal.showError("Unrelated preview failure.", {
    key: "unrelated-preview",
  });
  modal.closeError();
  modal.cancelSaveName();

  expect(model.modalState).toMatchObject({
    kind: "save-name",
    busy: true,
  });

  resolveSave(true);
  await operation;
  expect(model.modalState).toBeUndefined();
});

test("successful persistence keeps an apply error without resuming Save As", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });

  modal.requestSaveAs({} as HTMLElement, "Existing");
  await modal.confirmNamedSave(async () => {
    model.reportError("Apply failed.", {
      title: "Live change failed",
      key: "apply-failed",
    });
    return true;
  });

  expect(model.modalState).toMatchObject({
    kind: "error",
    message: "Apply failed.",
  });
  expect(
    model.modalState?.kind === "error"
      ? model.modalState.resume
      : undefined,
  ).toBeUndefined();
  modal.closeError();
  expect(model.modalState).toBeUndefined();
});

test("error modals suspend and resume the active naming workflow", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });

  modal.requestSaveAs({} as HTMLElement, "Jumping copy");
  modal.showError("The library is unavailable.", {
    title: "Save failed",
    key: "save-failed",
  });

  expect(model.modalState).toMatchObject({
    kind: "error",
    title: "Save failed",
    resume: { kind: "save-name" },
  });

  modal.closeError();
  expect(model.saveNameDialogOpen).toBe(true);
  expect(model.saveNameValue).toBe("Jumping copy");
});

test("replacement errors preserve suspended workflows and retry after close", () => {
  const model = new PanelModel(() => undefined);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });

  modal.requestTransition("Save", "Draft", false);
  modal.showError("First failure.", { key: "first" });
  modal.showError("Second failure.", { key: "second" });

  expect(model.modalState).toMatchObject({
    kind: "error",
    message: "Second failure.",
    resume: { kind: "pending-transition", saveName: "Draft" },
  });

  modal.closeError();
  expect(model.pendingTransitionDialog?.saveName).toBe("Draft");

  modal.showError("Second failure.", { key: "second" });
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: "Second failure.",
  });
});

test("overwrite confirmation resolves without stacking modal workflows", async () => {
  const model = new PanelModel(() => undefined);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });

  const cancelled = modal.requestOverwrite("Existing");
  modal.cancelOverwrite();
  await expect(cancelled).resolves.toBe(false);
  expect(model.modalState).toBeUndefined();

  const confirmed = modal.requestOverwrite("Existing");
  modal.confirmOverwrite();
  await expect(confirmed).resolves.toBe(true);
  expect(model.modalState).toBeUndefined();
});

test("nested overwrite cancellation preserves transition return focus", async () => {
  const model = new PanelModel(() => undefined);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const focus = vi.fn();
  const returnFocus = {
    isConnected: true,
    focus,
  } as unknown as HTMLElement;

  modal.requestTransition("Save", "Draft", false, returnFocus);
  const overwrite = modal.requestOverwrite("Existing");
  modal.cancelOverwrite();
  await expect(overwrite).resolves.toBe(false);
  modal.closeTransition(true);
  await Promise.resolve();

  expect(focus).toHaveBeenCalledOnce();
});

test("pending transitions save named new drafts directly", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  model.devices = [device("entry-a", "H617A")];
  model.devices[0].custom_effects.advanced = "supported";
  model.selectedDeviceId = "entry-a";
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

test("scene-owned transitions use the scene save continuation", async () => {
  const model = new PanelModel(() => undefined);
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

test("pending-transition navigation preserves a standalone Live apply error", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const selected = device("entry-a", "H617A");
  selected.custom_effects.advanced = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller, editorController } = panelControllerHarness(model);
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
  controller.api = {
    createItem: vi.fn().mockResolvedValue(created),
    applySavedEffect: vi.fn().mockRejectedValue(new Error("offline")),
  } as unknown as EffectStudioApi;

  await controller.savePendingTransition();

  expect(execute).toHaveBeenCalledOnce();
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: expect.stringContaining("offline"),
  });
  expect(
    model.modalState?.kind === "error"
      ? model.modalState.resume
      : undefined,
  ).toBeUndefined();
});

test("auto-save restores only an explicit true preference", () => {
  expect(restoredAutoSave(true)).toBe(true);
  expect(restoredAutoSave(false)).toBe(false);
  expect(restoredAutoSave("true")).toBe(false);
  expect(restoredAutoSave(undefined)).toBe(false);
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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const controller = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: committed,
  });

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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const controller = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: committed,
  });

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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const controller = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: committed,
  });

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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const controller = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: committed,
  });

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
  const preview = new PanelPreviewController(model);
  const scheduleEdited = vi.spyOn(preview, "scheduleEdited");
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  const controller = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: () => undefined,
  });

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
  const preview = new PanelPreviewController(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const templatePreview = vi.spyOn(preview, "scheduleTemplateSelection");
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  expect(model.resetBaseline).toEqual(blankPainted());
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });

  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
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
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
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

test("auto-save coalesces committed edits onto the returned item version", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.autoSaveEnabled = true;
  model.liveApplyEnabled = false;
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
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

test("saved item selection applies identity only while Live is enabled", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
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

  model.liveApplyEnabled = true;
  await expect(controller.selectItem(saved.id)).resolves.toBe(true);
  expect(applySavedEffect).toHaveBeenCalledWith(
    "entry-a",
    saved,
  );
});

test("enabling Live on a clean saved item applies its stable identity", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.liveApplyEnabled = false;
  const { controller, editorController } = panelControllerHarness(model);
  const saved = item(painted());
  editorController.applyLibraryItem(saved);
  const applySavedEffect = vi.fn().mockResolvedValue(undefined);
  controller.api = {
    applySavedEffect,
    device: vi.fn().mockResolvedValue(selected),
  } as unknown as EffectStudioApi;

  await controller.toggleLive();

  expect(model.liveApplyEnabled).toBe(true);
  expect(applySavedEffect).toHaveBeenCalledWith(
    selected.config_entry_id,
    saved,
  );
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

test("new saves promote stable identity only while Live remains enabled", async () => {
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
  const { controller } = panelControllerHarness(model);
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

  expect(applySavedEffect).toHaveBeenCalledWith(
    selected.config_entry_id,
    created,
  );

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
  applySavedEffect.mockClear();

  await expect(controller.save()).resolves.toBe(true);

  expect(applySavedEffect).not.toHaveBeenCalled();
});

test("a failed Live apply does not turn a committed save into a persistence failure", async () => {
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
  model.name = "Stored";
  model.content = blankAdvancedContent();
  const { controller } = panelControllerHarness(model);
  const created: LibraryItem = {
    ...item(painted()),
    id: "stored",
    version: 1,
    name: model.name,
    content: blankAdvancedContent(),
  };
  controller.api = {
    createItem: vi.fn().mockResolvedValue(created),
    applySavedEffect: vi.fn().mockRejectedValue(new Error("offline")),
  } as unknown as EffectStudioApi;

  await expect(controller.save()).resolves.toBe(true);

  expect(model.currentItem?.id).toBe(created.id);
  expect(model.dirty).toBe(false);
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: expect.stringContaining("offline"),
  });
});

test("disabling Live while a new save is pending suppresses saved identity application", async () => {
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
  const { controller } = panelControllerHarness(model);
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
});

test("scene saves follow strict Live semantics", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  const { controller } = panelControllerHarness(model);
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

  model.liveApplyEnabled = true;
  model.section = "scenes";
  await controller.sceneItemSaved(
    saved,
    selected.config_entry_id,
    true,
    model.editorTransitionEpoch,
  );
  expect(applySavedEffect).toHaveBeenCalledWith(
    selected.config_entry_id,
    saved,
  );

  applySavedEffect.mockClear();
  await controller.sceneItemSaved(
    saved,
    "entry-b",
    false,
    model.editorTransitionEpoch,
  );
  expect(applySavedEffect).not.toHaveBeenCalled();

  await controller.sceneItemSaved(
    saved,
    selected.config_entry_id,
    true,
    model.editorTransitionEpoch - 1,
  );
  expect(applySavedEffect).not.toHaveBeenCalled();
});

test("manual Save adopts the saved content as the next Reset baseline", async () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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
    content: blankVideoProfile("movie"),
    content_hash: "video-hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
  model.currentItem = source;
  model.name = source.name;
  model.content = source.content;
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
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

test("manual Apply writes the current built-in draft without saving it", async () => {
  const selected = device("entry-a", "H617A");
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
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
  const { controller, editorController, modal } = panelControllerHarness(model);
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
  expect(applySavedEffect).toHaveBeenCalledWith(
    selected.config_entry_id,
    expect.objectContaining({
      id: saved.id,
      version: 3,
    }),
  );
  expect(loadDevice).toHaveBeenCalledWith(selected.config_entry_id);

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
  const content = blankVideoProfile("movie");
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

  await controller.selectVideoTemplate("game", "Game", returnFocus);

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

  await controller.selectVideoTemplate("game", "Game", returnFocus);
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
