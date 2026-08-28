import { describe, expect, test, vi } from "vitest";

import type { EffectStudioApi } from "../../src/api";
import { SceneBrowserWorkflow } from "../../src/scene-browser-workflow";
import type {
  BuiltinSceneContent,
  DeviceCapabilities,
  LibraryItem,
  LibrarySummary,
  SceneCatalogue,
  SceneDetail,
  SceneSummary,
} from "../../src/types";

const firstScene: SceneSummary = {
  scene_id: 1,
  effect_id: 11,
  category_id: 1,
  category: "Natural",
  name: "Glacier",
  variant: "",
  display_name: "Glacier",
  scene_type: 1,
  parameter_kind: "none",
  speed: { option_count: 3, default_index: 1 },
};
const secondScene: SceneSummary = {
  ...firstScene,
  scene_id: 2,
  effect_id: 22,
  name: "Sunrise",
  display_name: "Sunrise",
};
const catalogue: SceneCatalogue = {
  schema_version: 1,
  sku: "H617A",
  enabled: true,
  categories: [{ id: 1, name: "Natural" }],
  scenes: [firstScene, secondScene],
};
const device = {
  config_entry_id: "device-a",
} as DeviceCapabilities;

function content(scene: SceneSummary, speedIndex: number | null = null): BuiltinSceneContent {
  return {
    kind: "scene_builtin",
    template: {
      sku: catalogue.sku,
      scene_id: scene.scene_id,
      effect_id: scene.effect_id,
      catalogue_schema_version: catalogue.schema_version,
    },
    speed_index: speedIndex,
  };
}

function detail(
  scene: SceneSummary,
  speedIndex: number | null = null,
  hasDefault = false,
): SceneDetail {
  return {
    scene,
    content: content(scene, speedIndex),
    catalogue_content: content(
      scene,
      scene.speed?.default_index ?? null,
    ),
    has_default: hasDefault,
  };
}

function libraryItem(id: string, scene: SceneSummary, name = "Saved Glacier"): LibraryItem {
  return {
    schema_version: 1,
    id,
    version: 1,
    updated_at: "2026-08-18T00:00:00Z",
    name,
    content: content(scene),
    content_hash: "a".repeat(64),
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
}

function summary(item: LibraryItem): LibrarySummary {
  return {
    id: item.id,
    version: item.version,
    updated_at: item.updated_at,
    name: item.name,
    kind: item.content.kind,
    content_hash: item.content_hash,
    origin: item.origin,
    template: item.content.kind === "scene_builtin" ? item.content.template : undefined,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((complete, fail) => {
    resolve = complete;
    reject = fail;
  });
  return { promise, reject, resolve };
}

function harness(api: EffectStudioApi) {
  const initialSelectionFinished = vi.fn();
  const libraryItemSaved = vi.fn();
  const error = vi.fn();
  const workStateChanged = vi.fn();
  const workflow = new SceneBrowserWorkflow({
    changed: vi.fn(),
    initialSelectionFinished,
    libraryItemSaved,
    error,
    workStateChanged,
  });
  workflow.configure(api, device);
  return {
    workflow,
    initialSelectionFinished,
    libraryItemSaved,
    error,
    workStateChanged,
  };
}

describe("SceneBrowserWorkflow", () => {
  test("a stale scene response cannot replace the latest selection", async () => {
    const first = deferred<SceneDetail>();
    const second = deferred<SceneDetail>();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn((_deviceId: string, sceneId: number) =>
        sceneId === firstScene.scene_id ? first.promise : second.promise,
      ),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();

    const selectFirst = workflow.selectBuiltin(firstScene);
    const selectSecond = workflow.selectBuiltin(secondScene);
    second.resolve(detail(secondScene, 2));
    await expect(selectSecond).resolves.toBe(true);
    first.resolve(detail(firstScene, 0));
    await expect(selectFirst).resolves.toBe(false);

    expect(workflow.state.selectedScene).toEqual(secondScene);
    expect(workflow.state.speedIndex).toBe(2);
  });

  test("untouched native and empty scene states do not report protected work", async () => {
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1)),
    } as unknown as EffectStudioApi;
    const { workflow, workStateChanged } = harness(api);

    await workflow.loadCatalogue();
    expect(workStateChanged).toHaveBeenLastCalledWith(false);

    await workflow.selectBuiltin(firstScene);
    expect(workflow.protectedWorkDirty).toBe(false);
    expect(workStateChanged).toHaveBeenLastCalledWith(false);
  });

  test("an initial saved selection opens once through the custom-scene path", async () => {
    const item = libraryItem("saved-a", firstScene);
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      item: vi.fn().mockResolvedValue(item),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
    } as unknown as EffectStudioApi;
    const { workflow, initialSelectionFinished } = harness(api);
    workflow.setLibrary({ items: [summary(item)] });
    workflow.setInitialSelection({ kind: "saved", itemId: item.id });

    await workflow.loadCatalogue();
    await workflow.openInitialSelection();

    expect(workflow.state.selectedItem).toEqual(item);
    expect(workflow.state.content).not.toBe(item.content);
    expect(initialSelectionFinished).toHaveBeenCalledOnce();
    expect(initialSelectionFinished).toHaveBeenCalledWith(true);
  });

  test("Spring category restoration reveals Candlelight and explicit clearing removes it", async () => {
    const spring = {
      ...firstScene,
      name: "Spring",
      display_name: "Spring",
    };
    const candlelight = {
      ...secondScene,
      category_id: 2,
      category: "Cosy",
      name: "Candlelight",
      display_name: "Candlelight",
    };
    const categorisedCatalogue: SceneCatalogue = {
      ...catalogue,
      categories: [
        { id: 1, name: "Spring" },
        { id: 2, name: "Cosy" },
      ],
      scenes: [spring, candlelight],
    };
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(categorisedCatalogue),
      sceneDetail: vi.fn(
        async (_deviceId: string, sceneId: number) =>
          detail(sceneId === spring.scene_id ? spring : candlelight),
      ),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    workflow.setCategory(spring.category_id);
    await workflow.selectBuiltin(spring);

    workflow.setInitialSelection({ kind: "native", effect: "Candlelight" });
    await workflow.openInitialSelection();

    expect(workflow.state.category).toBe(candlelight.category_id);
    expect(workflow.state.selectedScene).toEqual(candlelight);

    workflow.setInitialSelection({ kind: "none" });
    await workflow.openInitialSelection();

    expect(workflow.state.category).toBe(candlelight.category_id);
    expect(workflow.state.selectedScene).toBeUndefined();
    expect(workflow.state.content).toBeUndefined();
  });

  test("a subscription reload cannot replace edits made while its detail is loading", async () => {
    const original = {
      ...libraryItem("saved-a", firstScene),
      content: content(firstScene, 1),
    };
    const remote = {
      ...original,
      version: 2,
      updated_at: "2026-08-18T00:00:01Z",
      name: "Remote name",
    };
    const remoteItem = deferred<LibraryItem>();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      item: vi
        .fn()
        .mockResolvedValueOnce(original)
        .mockReturnValueOnce(remoteItem.promise),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
    } as unknown as EffectStudioApi;
    const { workflow, error } = harness(api);
    workflow.setLibrary({ items: [summary(original)] });
    await workflow.loadCatalogue();
    await workflow.selectCustom(summary(original));

    workflow.setLibrary({ items: [summary(remote)] });
    workflow.setName("Local edit");
    remoteItem.resolve(remote);
    await vi.waitFor(() => expect(api.sceneDetail).toHaveBeenCalledTimes(2));
    await Promise.resolve();

    expect(workflow.state.selectedItem?.version).toBe(original.version);
    expect(workflow.state.name).toBe("Local edit");
    expect(error).toHaveBeenCalledWith(
      "This custom scene changed elsewhere. Reload it before saving.",
      expect.objectContaining({ title: "Scene operation failed" }),
    );
  });

  test("saving owns persistence payloads and commits the returned library item", async () => {
    const saved = libraryItem("saved-copy", firstScene, "Glacier custom");
    const createItem = vi.fn().mockResolvedValue(saved);
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
      createItem,
    } as unknown as EffectStudioApi;
    const { workflow, libraryItemSaved } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.edit(true);
    workflow.setName("  Glacier custom  ");
    workflow.setSpeedIndex(2);

    await workflow.save(true);

    expect(createItem).toHaveBeenCalledWith(
      "Glacier custom",
      expect.objectContaining({ kind: "scene_builtin", speed_index: 2 }),
      expect.any(Function),
    );
    expect(libraryItemSaved).toHaveBeenCalledWith(saved, "device-a", true, 0);
    expect(workflow.state.selectedItem).toEqual(saved);
    expect(workflow.state.category).toBe("custom");
    expect(workflow.state.notice).toBeUndefined();
  });

  test("an existing custom scene blocks edits during save and adopts the returned version", async () => {
    const pending = deferred<LibraryItem>();
    const original = libraryItem("saved-copy", firstScene, "Glacier custom");
    const saved = {
      ...original,
      version: original.version + 1,
      updated_at: "2026-08-27T00:00:00Z",
      name: "Renamed",
    };
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
      item: vi.fn().mockResolvedValue(original),
      updateItem: vi.fn().mockReturnValue(pending.promise),
    } as unknown as EffectStudioApi;
    const { workflow, libraryItemSaved } = harness(api);
    workflow.setLibrary({ items: [summary(original)] });
    await workflow.loadCatalogue();
    await workflow.selectCustom(summary(original));
    workflow.setName("Renamed");

    const save = workflow.save(true);
    workflow.setName("Ignored");
    workflow.setSpeedIndex(2);
    pending.resolve(saved);
    await save;

    expect(libraryItemSaved).toHaveBeenCalledWith(saved, "device-a", true, 0);
    expect(workflow.state.selectedItem).toEqual(saved);
    expect(workflow.state.name).toBe("Renamed");
    expect(workflow.state.speedIndex).not.toBe(2);
  });

  test("cancelling a scene copy restores the selected catalogue scene", async () => {
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1)),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.edit(true);
    workflow.setName("Changed copy");
    workflow.setSpeedIndex(2);

    await expect(workflow.cancelCopy()).resolves.toBe(true);

    expect(workflow.state.editingCopy).toBe(false);
    expect(workflow.state.name).toBe(firstScene.display_name);
    expect(workflow.state.speedIndex).toBe(1);
    expect(api.sceneDetail).toHaveBeenCalledTimes(2);
  });

  test("setting a default immediately adopts the selected speed without shared saving state", async () => {
    const pending = deferred<SceneDetail>();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1)),
      setSceneDefault: vi.fn().mockReturnValue(pending.promise),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.setSpeedIndex(2);

    expect(workflow.sceneDefaultDirty).toBe(true);
    const saving = workflow.setCurrentDefault(true);

    expect(api.setSceneDefault).toHaveBeenCalledWith(
      device.config_entry_id,
      expect.objectContaining({ speed_index: 2 }),
    );
    expect(workflow.sceneDefaultDirty).toBe(true);
    expect(workflow.state.hasDefault).toBe(false);
    expect(workflow.state.content?.speed_index).toBe(2);
    expect(workflow.state.saving).toBe(false);

    pending.resolve(detail(firstScene, 2, true));
    await saving;

    expect(workflow.state.notice).toBeUndefined();
  });

  test("queued Live persistence stays dirty until storage completion", async () => {
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1, false)),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.setSpeedIndex(2);

    expect(workflow.previewRequest(true, true)).toMatchObject({
      persistDefault: true,
    });
    workflow.previewStatusChanged({
      session_id: "session-a",
      sequence: 1,
      config_entry_id: device.config_entry_id,
      phase: "queued",
      content_kind: "scene_builtin",
      confidence: "unknown",
      error_code: null,
      error_message: null,
      write_disposition: "not_started",
      persist_default: true,
      scene_id: firstScene.scene_id,
      effect_id: firstScene.effect_id,
      default_action: "set",
    });

    expect(workflow.state.hasDefault).toBe(false);
    expect(workflow.sceneDefaultDirty).toBe(true);
    expect(workflow.defaultWritePending).toBe(true);

    workflow.previewStatusChanged(undefined);

    expect(workflow.state.hasDefault).toBe(false);
    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.sceneDefaultDirty).toBe(true);
    expect(workflow.defaultWritePending).toBe(false);
  });

  test("written Live persistence refreshes the scene default baseline", async () => {
    const sceneDetail = vi
      .fn()
      .mockResolvedValueOnce(detail(firstScene, 1, false))
      .mockResolvedValueOnce(detail(firstScene, 2, true));
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail,
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.setSpeedIndex(2);

    workflow.previewStatusChanged({
      session_id: "session-a",
      sequence: 1,
      config_entry_id: device.config_entry_id,
      phase: "queued",
      content_kind: "scene_builtin",
      confidence: "unknown",
      error_code: null,
      error_message: null,
      write_disposition: "not_started",
      persist_default: true,
      scene_id: firstScene.scene_id,
      effect_id: firstScene.effect_id,
      default_action: "set",
    });
    workflow.previewStatusChanged({
      session_id: "session-a",
      sequence: 1,
      config_entry_id: device.config_entry_id,
      phase: "written",
      content_kind: "scene_builtin",
      confidence: "write_completed",
      error_code: null,
      error_message: null,
      write_disposition: "completed",
      persist_default: true,
      scene_id: firstScene.scene_id,
      effect_id: firstScene.effect_id,
      default_action: "set",
    });

    await vi.waitFor(() => expect(sceneDetail).toHaveBeenCalledTimes(2));
    expect(workflow.sceneDefaultDirty).toBe(false);
    expect(workflow.state.hasDefault).toBe(true);
  });

  test("rapid auto-save speed changes stay interactive and coalesce to the latest request", async () => {
    const firstWrite = deferred<SceneDetail>();
    const latestWrite = deferred<SceneDetail>();
    const setSceneDefault = vi
      .fn()
      .mockReturnValueOnce(firstWrite.promise)
      .mockReturnValueOnce(latestWrite.promise);
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1)),
      setSceneDefault,
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);

    workflow.setSpeedIndex(0);
    const first = workflow.setCurrentDefault(true);
    workflow.setSpeedIndex(1);
    const replaced = workflow.setCurrentDefault(true);
    workflow.setSpeedIndex(2);
    const latest = workflow.setCurrentDefault(true);

    expect(
      setSceneDefault.mock.calls.map((call) => call[1].speed_index),
    ).toEqual([0]);
    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.state.content?.speed_index).toBe(2);
    expect(workflow.state.saving).toBe(false);

    firstWrite.resolve(detail(firstScene, 0, true));
    await first;
    await replaced;

    expect(
      setSceneDefault.mock.calls.map((call) => call[1].speed_index),
    ).toEqual([0, 2]);
    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.state.content?.speed_index).toBe(2);

    latestWrite.resolve(detail(firstScene, 1, true));
    await latest;

    expect(workflow.state.speedIndex).toBe(1);
    expect(workflow.state.content?.speed_index).toBe(1);
    expect(workflow.state.hasDefault).toBe(true);
  });

  test("state-update failure invalidates queued scene-default writes", async () => {
    const firstWrite = deferred<SceneDetail>();
    const setSceneDefault = vi.fn().mockReturnValue(firstWrite.promise);
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1)),
      setSceneDefault,
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);

    workflow.setSpeedIndex(0);
    const first = workflow.setCurrentDefault(true);
    workflow.setSpeedIndex(2);
    const queued = workflow.setCurrentDefault(true);
    workflow.setStateUpdatesAvailable(false);
    firstWrite.resolve(detail(firstScene, 0, true));
    await first;
    await queued;

    expect(
      setSceneDefault.mock.calls.map((call) => call[1].speed_index),
    ).toEqual([0]);
    expect(workflow.defaultWritePending).toBe(false);
  });

  test("scene work reports dirty state and becomes immutable after update failure", async () => {
    const original = libraryItem("saved-copy", firstScene, "Glacier custom");
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
      item: vi.fn().mockResolvedValue(original),
    } as unknown as EffectStudioApi;
    const { workflow, workStateChanged } = harness(api);
    workflow.setLibrary({ items: [summary(original)] });
    await workflow.loadCatalogue();
    await workflow.selectCustom(summary(original));

    workflow.setName("Changed");
    expect(workStateChanged).toHaveBeenLastCalledWith(true);

    workflow.setStateUpdatesAvailable(false);
    workflow.setName("Ignored");
    workflow.setSpeedIndex(2);

    expect(workflow.state.name).toBe("Changed");
    expect(workflow.state.speedIndex).not.toBe(2);
    expect(workflow.state.notice).toBeUndefined();
  });

  test("reset restores the catalogue locally without persisting it", async () => {
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 2, true)),
      resetScene: vi.fn(),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);

    const reset = workflow.resetToCatalogue(true);

    expect(api.resetScene).not.toHaveBeenCalled();
    expect(workflow.state.speedIndex).toBe(firstScene.speed?.default_index);
    expect(workflow.state.content?.speed_index).toBe(firstScene.speed?.default_index);
    expect(workflow.state.hasDefault).toBe(true);
    expect(workflow.sceneDefaultDirty).toBe(true);
    expect(workflow.state.saving).toBe(false);

    await reset;

    expect(workflow.state.notice).toBeUndefined();
  });

  test("manual Apply writes the exact current scene without saving its default", async () => {
    const applySnapshot = vi.fn().mockResolvedValue(undefined);
    const setSceneDefault = vi.fn();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1, true)),
      applySnapshot,
      setSceneDefault,
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.setSpeedIndex(2);

    await expect(workflow.applyCurrent(true)).resolves.toBe(true);

    expect(applySnapshot).toHaveBeenCalledWith(
      device.config_entry_id,
      firstScene.display_name,
      expect.objectContaining({ speed_index: 2 }),
    );
    expect(setSceneDefault).not.toHaveBeenCalled();
    expect(workflow.sceneDefaultDirty).toBe(true);
  });

  test("the latest failed default write rolls back only its optimistic baseline fields", async () => {
    const pending = deferred<SceneDetail>();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1, false)),
      setSceneDefault: vi.fn().mockReturnValue(pending.promise),
    } as unknown as EffectStudioApi;
    const { workflow, error } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.setSpeedIndex(2);

    const saving = workflow.setCurrentDefault(true);
    pending.reject(new Error("offline"));
    await saving;

    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.state.content?.speed_index).toBe(2);
    expect(workflow.state.hasDefault).toBe(false);
    expect(workflow.sceneDefaultDirty).toBe(true);
    expect(error).toHaveBeenCalledWith(
      "Save failed: offline",
      expect.anything(),
    );
    expect(workflow.state.saving).toBe(false);
  });

  test("a latest failure rolls back past an earlier stale failure", async () => {
    const firstWrite = deferred<SceneDetail>();
    const latestWrite = deferred<SceneDetail>();
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene, 1, false)),
      setSceneDefault: vi
        .fn()
        .mockReturnValueOnce(firstWrite.promise)
        .mockReturnValueOnce(latestWrite.promise),
    } as unknown as EffectStudioApi;
    const { workflow, error } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);

    workflow.setSpeedIndex(0);
    const first = workflow.setCurrentDefault(true);
    workflow.setSpeedIndex(2);
    const latest = workflow.setCurrentDefault(true);
    firstWrite.reject(new Error("first failed"));
    await first;

    expect(workflow.state.notice).toBeUndefined();
    expect(workflow.state.content?.speed_index).toBe(2);

    latestWrite.reject(new Error("latest failed"));
    await latest;

    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.state.content?.speed_index).toBe(2);
    expect(workflow.state.hasDefault).toBe(false);
    expect(error).toHaveBeenCalledWith(
      "Save failed: latest failed",
      expect.anything(),
    );
  });

  test("a stale preview refresh cannot replace newer optimistic default state", async () => {
    const refresh = deferred<SceneDetail>();
    const save = deferred<SceneDetail>();
    const sceneDetail = vi
      .fn()
      .mockResolvedValueOnce(detail(firstScene, 1, false))
      .mockReturnValueOnce(refresh.promise);
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail,
      setSceneDefault: vi.fn().mockReturnValue(save.promise),
    } as unknown as EffectStudioApi;
    const { workflow } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);

    const refreshing = workflow.refreshSelectedDefault();
    workflow.setSpeedIndex(2);
    const saving = workflow.setCurrentDefault(true);
    refresh.resolve(detail(firstScene, 1, false));
    await refreshing;

    expect(workflow.state.speedIndex).toBe(2);
    expect(workflow.state.content?.speed_index).toBe(2);
    expect(workflow.state.hasDefault).toBe(false);

    save.resolve(detail(firstScene, 2, true));
    await saving;
  });

  test("a completed stale save is announced without restoring its old selection", async () => {
    const pendingSave = deferred<LibraryItem>();
    const saved = libraryItem("saved-copy", firstScene, "Glacier copy");
    const api = {
      sceneCatalogue: vi.fn().mockResolvedValue(catalogue),
      sceneDetail: vi.fn().mockResolvedValue(detail(firstScene)),
      createItem: vi.fn().mockReturnValue(pendingSave.promise),
    } as unknown as EffectStudioApi;
    const { workflow, libraryItemSaved } = harness(api);
    await workflow.loadCatalogue();
    await workflow.selectBuiltin(firstScene);
    workflow.edit(true);

    const save = workflow.save(true);
    workflow.setCategory("custom");
    pendingSave.resolve(saved);
    await save;

    expect(libraryItemSaved).toHaveBeenCalledWith(saved, "device-a", false, 0);
    expect(workflow.state.selectedItem).toBeUndefined();
    expect(workflow.state.category).toBe("custom");
  });
});
