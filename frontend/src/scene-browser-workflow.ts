import { cloneLayeredSceneContent } from "./advanced-effect-model";
import type { EffectStudioApi } from "./api";
import { AsyncRequestController, type AsyncRequestToken } from "./async-request-controller";
import { libraryItemSyncResult } from "./effect-editor-model";
import {
  buildScenePreviewRequest,
  cloneSceneContent,
  compatibleCustomScenes,
  findCatalogueScene,
  findNativeScene,
  hasCurrentSceneContent,
  initialSceneBrowserState,
  isSceneContent,
  normaliseSceneName,
  sceneContentAtSpeed,
  sceneIsDirty,
  sceneKey,
  visibleCategoryForBuiltin,
  visibleCategoryForCustom,
  type CategorySelection,
  type SceneBrowserViewState,
  type SceneContent,
  type SceneInitialSelection,
  type ScenePreviewRequest,
} from "./scene-browser-model";
import type {
  DeviceCapabilities,
  LayeredSceneContent,
  LibraryItem,
  LibrarySnapshot,
  LibrarySummary,
  PreviewStatus,
  SceneDetail,
  SceneSummary,
} from "./types";
import { errorCode, errorMessage } from "./ui-utils";

type SceneRequestState = {
  api: EffectStudioApi;
  deviceId: string;
  category: CategorySelection;
  selectionIdentity?: string;
};
type SceneRequestContext = AsyncRequestToken<SceneRequestState>;

type SceneDefaultSnapshot = {
  scene: SceneSummary;
  content: SceneContent;
  speedIndex: number | null;
  hasDefault: boolean;
};

type SceneDefaultWrite = {
  content: SceneContent;
  api: EffectStudioApi;
  deviceId: string;
  scene: SceneSummary;
  selectionIdentity: string;
  selectionRevision: number;
  speedRevision: number;
};

type SerialWrite<T> = {
  generation: number;
  payload: T;
  resolve: () => void;
};

class SerialLatestWriter<T> {
  private generation = 0;
  private active = false;
  private pending?: SerialWrite<T>;

  public constructor(
    private readonly execute: (write: Readonly<SerialWrite<T>>) => Promise<void>,
  ) {}

  public get currentGeneration(): number {
    return this.generation;
  }

  public get busy(): boolean {
    return this.active || this.pending !== undefined;
  }

  public enqueue(payload: T): Promise<void> {
    this.generation += 1;
    this.pending?.resolve();
    return new Promise((resolve) => {
      this.pending = { generation: this.generation, payload, resolve };
      void this.drain();
    });
  }

  public invalidate(): void {
    this.generation += 1;
    this.pending?.resolve();
    this.pending = undefined;
  }

  public isLatest(generation: number): boolean {
    return generation === this.generation;
  }

  private async drain(): Promise<void> {
    if (this.active) {
      return;
    }
    this.active = true;
    try {
      while (this.pending) {
        const write = this.pending;
        this.pending = undefined;
        try {
          await this.execute(write);
        } finally {
          write.resolve();
        }
      }
    } finally {
      this.active = false;
    }
  }
}

export interface SceneEditSelection {
  content: LayeredSceneContent;
  catalogue_content?: LayeredSceneContent;
  has_default?: boolean;
  config_entry_id: string;
  item?: LibraryItem;
  name: string;
}

export interface SceneBrowserWorkflowEffects {
  changed: (state: SceneBrowserViewState) => void;
  initialSelectionFinished: (opened: boolean) => void;
  libraryItemSaved: (
    item: LibraryItem,
    configEntryId: string,
    selectionIsCurrent: boolean,
    panelTransitionEpoch: number,
  ) => void;
  error: (
    message: string,
    options?: { title?: string; key?: string },
  ) => void;
  workStateChanged: (dirty: boolean) => void;
}

export class SceneBrowserWorkflow {
  private stateValue = initialSceneBrowserState();
  private api?: EffectStudioApi;
  private device?: DeviceCapabilities;
  private library: LibrarySnapshot = { items: [] };
  private initialSelection?: SceneInitialSelection;
  private activeSelectionIdentity?: string;
  private openedInitialSelection?: string;
  private defaultSelectionRevision = 0;
  private speedRevision = 0;
  private defaultRefreshGeneration = 0;
  private defaultRefreshPending = false;
  private defaultPreviewPending = false;
  private defaultBaseline?: SceneDefaultSnapshot;
  private errorSequence = 0;
  private stateUpdatesAvailable = true;
  private readonly defaultWriter = new SerialLatestWriter<SceneDefaultWrite>((write) =>
    this.performDefaultWrite(write),
  );
  private readonly requests = new AsyncRequestController<SceneRequestState>(
    (left, right) =>
      left.api === right.api &&
      left.deviceId === right.deviceId &&
      left.category === right.category &&
      left.selectionIdentity === right.selectionIdentity,
  );

  public constructor(private readonly effects: SceneBrowserWorkflowEffects) {}

  public get state(): SceneBrowserViewState {
    return this.stateValue;
  }

  public get compatibleCustomScenes(): LibrarySummary[] {
    return compatibleCustomScenes(this.library.items, this.stateValue.catalogue);
  }

  public get sceneDirty(): boolean {
    return sceneIsDirty(this.stateValue);
  }

  public get sceneDefaultDirty(): boolean {
    const { content, editingCopy, selectedItem, speedIndex } =
      this.stateValue;
    return Boolean(
      content &&
        selectedItem === undefined &&
        !editingCopy &&
        this.defaultBaseline &&
        JSON.stringify(sceneContentAtSpeed(content, speedIndex)) !==
          JSON.stringify(this.defaultBaseline.content),
    );
  }

  public get sceneCatalogueDirty(): boolean {
    const { catalogueContent, content, editingCopy, selectedItem, speedIndex } =
      this.stateValue;
    return Boolean(
      catalogueContent &&
        content &&
        selectedItem === undefined &&
        !editingCopy &&
        JSON.stringify(sceneContentAtSpeed(content, speedIndex)) !==
          JSON.stringify(catalogueContent),
    );
  }

  public get protectedWorkDirty(): boolean {
    const workflowOwnsSceneDraft =
      this.stateValue.editingCopy ||
      this.stateValue.selectedItem !== undefined;
    return (
      (workflowOwnsSceneDraft && this.sceneDirty) ||
      this.sceneDefaultDirty
    );
  }

  public get defaultWritePending(): boolean {
    return this.defaultWriter.busy || this.defaultPreviewPending;
  }

  public hasCurrentSceneContent(): boolean {
    return hasCurrentSceneContent(this.stateValue, this.activeSelectionIdentity);
  }

  public previewRequest(
    isAdmin: boolean,
    persistDefault = false,
  ): ScenePreviewRequest | undefined {
    if (!this.stateUpdatesAvailable) {
      return undefined;
    }
    const request = buildScenePreviewRequest(
      this.stateValue,
      this.activeSelectionIdentity,
      Boolean(this.device),
      isAdmin,
    );
    return request
      ? {
          ...request,
          persistDefault: persistDefault && this.sceneDefaultDirty,
        }
      : undefined;
  }

  public configure(api: EffectStudioApi | undefined, device: DeviceCapabilities | undefined): void {
    this.api = api;
    this.device = device;
    this.invalidateRequests();
    this.openedInitialSelection = undefined;
    this.patch({
      catalogue: undefined,
      category: "all",
      selectedScene: undefined,
      selectedItem: undefined,
      content: undefined,
      catalogueContent: undefined,
      hasDefault: false,
      defaultSaveFailed: false,
      editingCopy: false,
      notice: undefined,
      error: undefined,
      loading: Boolean(api && device),
    });
  }

  public setInitialSelection(selection: SceneInitialSelection | undefined): void {
    this.initialSelection = selection;
    this.openedInitialSelection = undefined;
  }

  public setLibrary(library: LibrarySnapshot): void {
    this.library = library;
    const selectedItem = this.stateValue.selectedItem;
    if (!selectedItem || this.stateValue.saving) {
      return;
    }
    const sync = libraryItemSyncResult(selectedItem, library.items, this.sceneDirty);
    if (sync.action === "removed") {
      this.invalidateRequests();
      this.patch({
        selectedScene: undefined,
        selectedItem: undefined,
        content: undefined,
        catalogueContent: undefined,
        hasDefault: false,
        defaultSaveFailed: false,
        editingCopy: false,
        notice: undefined,
      });
    } else if (sync.action === "conflict") {
      this.patch({ notice: "This custom scene changed elsewhere. Reload it before saving." });
    } else if (sync.action === "reload") {
      void this.reloadSelectedCustom(sync.summary, selectedItem);
    }
  }

  public synchroniseSavedSelection(item: LibraryItem): void {
    const { catalogue, selectedItem } = this.stateValue;
    if (
      selectedItem?.id !== item.id ||
      !catalogue ||
      !isSceneContent(item.content) ||
      item.content.template.sku !== catalogue.sku
    ) {
      return;
    }
    const scene = findCatalogueScene(catalogue, item.content);
    if (!scene) {
      return;
    }
    this.requests.invalidate();
    this.activeSelectionIdentity = `custom:${item.id}`;
    this.commitCustomSelection(item, scene, item.content);
    this.patch({ notice: undefined });
  }

  public setCategory(category: CategorySelection): void {
    this.invalidateRequests();
    this.patch({
      category,
      selectedScene: undefined,
      selectedItem: undefined,
      content: undefined,
      catalogueContent: undefined,
      hasDefault: false,
      editingCopy: false,
      notice: undefined,
    });
  }

  public setName(name: string): void {
    if (this.stateValue.saving || !this.stateUpdatesAvailable) {
      return;
    }
    this.patch({ name });
  }

  public setSpeedIndex(speedIndex: number): void {
    if (this.stateValue.saving || !this.stateUpdatesAvailable) {
      return;
    }
    this.speedRevision += 1;
    this.patch({
      speedIndex,
      ...(this.stateValue.content
        ? { content: sceneContentAtSpeed(this.stateValue.content, speedIndex) }
        : {}),
    });
  }

  public async loadCatalogue(): Promise<void> {
    if (!this.api || !this.device) {
      return;
    }
    const request = this.beginRequest();
    this.patch({
      loading: true,
      error: undefined,
      notice: undefined,
      selectedScene: undefined,
      selectedItem: undefined,
      content: undefined,
      catalogueContent: undefined,
      hasDefault: false,
    });
    try {
      const catalogue = await request.api.sceneCatalogue(request.deviceId);
      if (!this.requestIsCurrent(request)) {
        return;
      }
      this.patch({ catalogue, category: "all", loading: false });
      await this.openInitialSelection();
    } catch (error) {
      if (this.requestIsCurrent(request)) {
        this.patch({ error: errorMessage(error) });
      }
    } finally {
      if (this.requestIsCurrent(request)) {
        this.patch({ loading: false });
      }
    }
  }

  public async selectBuiltin(scene: SceneSummary): Promise<boolean> {
    if (!this.api || !this.device) {
      return false;
    }
    const category = visibleCategoryForBuiltin(this.stateValue.category, scene);
    if (category !== this.stateValue.category) {
      this.invalidateRequests();
      this.patch({ category });
    }
    const identity = sceneKey(scene);
    const request = this.beginRequest(identity);
    this.patch({
      notice: undefined,
      selectedScene: scene,
      selectedItem: undefined,
      editingCopy: false,
      content: undefined,
      catalogueContent: undefined,
      name: scene.display_name,
      speedIndex: scene.speed?.default_index ?? null,
    });
    try {
      const detail = await request.api.sceneDetail(request.deviceId, scene.scene_id, scene.effect_id);
      if (!this.requestIsCurrent(request) || sceneKey(detail.scene) !== identity) {
        return false;
      }
      this.defaultBaseline = this.snapshotFromDetail(detail);
      this.patch({
        selectedScene: detail.scene,
        content: detail.content,
        catalogueContent: detail.catalogue_content,
        hasDefault: detail.has_default,
        defaultSaveFailed: false,
        name: detail.scene.display_name,
        speedIndex: detail.content.speed_index,
      });
      return true;
    } catch (error) {
      if (this.requestIsCurrent(request)) {
        this.patch({ notice: errorMessage(error) });
      }
      return false;
    }
  }

  public async selectCustom(summary: LibrarySummary): Promise<boolean> {
    if (!this.api || !this.device || !this.stateValue.catalogue) {
      return false;
    }
    const catalogue = this.stateValue.catalogue;
    const category = visibleCategoryForCustom(this.stateValue.category);
    if (category !== this.stateValue.category) {
      this.invalidateRequests();
      this.patch({ category });
    }
    const request = this.beginRequest(`custom:${summary.id}`);
    this.patch({
      notice: undefined,
      selectedScene: undefined,
      selectedItem: undefined,
      editingCopy: false,
      content: undefined,
      catalogueContent: undefined,
      hasDefault: false,
      name: summary.name,
    });
    try {
      const item = await request.api.item(summary.id);
      if (!this.requestIsCurrent(request)) {
        return false;
      }
      if (!isSceneContent(item.content)) {
        throw new Error("This custom scene uses an unsupported definition.");
      }
      const content = item.content;
      if (content.template.sku !== catalogue.sku) {
        throw new Error(`This custom scene targets ${content.template.sku}, not ${catalogue.sku}.`);
      }
      const scene = findCatalogueScene(catalogue, content);
      if (!scene) {
        throw new Error("The source scene is not in this device catalogue.");
      }
      const detail = await request.api.sceneDetail(
        request.deviceId,
        content.template.scene_id,
        content.template.effect_id,
      );
      if (!this.requestIsCurrent(request) || sceneKey(detail.scene) !== sceneKey(scene)) {
        return false;
      }
      this.commitCustomSelection(item, scene, content);
      return true;
    } catch (error) {
      if (this.requestIsCurrent(request)) {
        this.patch({ notice: errorMessage(error) });
      }
      return false;
    }
  }

  public async openInitialSelection(): Promise<void> {
    const selection = this.initialSelection;
    const catalogue = this.stateValue.catalogue;
    if (!selection || !catalogue) {
      return;
    }
    const key =
      selection.kind === "none"
        ? "none"
        : selection.kind === "saved"
          ? `saved:${selection.itemId}`
          : `native:${normaliseSceneName(selection.effect)}`;
    if (this.openedInitialSelection === key) {
      return;
    }
    this.openedInitialSelection = key;
    const opened =
      selection.kind === "none"
        ? this.clearSelection()
        : selection.kind === "saved"
          ? await this.openInitialSavedScene(selection.itemId)
          : await this.openInitialNativeScene(selection.effect);
    if (this.initialSelection === selection) {
      this.effects.initialSelectionFinished(opened);
    }
  }

  public async save(
    isAdmin: boolean,
    panelTransitionEpoch = 0,
  ): Promise<boolean> {
    const { catalogue, content, selectedItem, selectedScene } = this.stateValue;
    if (
      !this.stateUpdatesAvailable ||
      !this.api ||
      !this.device ||
      !catalogue ||
      !selectedScene ||
      !content ||
      !this.hasCurrentSceneContent() ||
      (content.kind !== "scene_builtin" && content.kind !== "scene_palette") ||
      !isAdmin ||
      this.stateValue.saving
    ) {
      return false;
    }
    const name = this.stateValue.name.trim();
    if (!name) {
      this.patch({ notice: "Give this custom scene a name before saving." });
      return false;
    }
    const savedContent = sceneContentAtSpeed(content, this.stateValue.speedIndex);
    const request = this.captureRequest();
    const document = this.currentDocument();
    const guard = () =>
      this.stateUpdatesAvailable &&
      this.requestIsCurrent(request) &&
      this.currentDocument() === document;
    this.patch({ saving: true, notice: undefined });
    try {
      const result = selectedItem
        ? await request.api.updateItem(
            selectedItem,
            name,
            savedContent,
            guard,
          )
        : await request.api.createItem(name, savedContent, guard);
      if (result.content.kind !== "scene_builtin" && result.content.kind !== "scene_palette") {
        throw new Error("The saved scene returned an unsupported definition.");
      }
      const selectionIsCurrent =
        this.requestIsCurrent(request) &&
        this.currentDocument() === document;
      this.effects.libraryItemSaved(
        result,
        request.deviceId,
        selectionIsCurrent,
        panelTransitionEpoch,
      );
      if (!selectionIsCurrent) {
        return true;
      }
      this.activeSelectionIdentity = `custom:${result.id}`;
      this.requests.invalidate();
      this.patch({
        selectedItem: result,
        editingCopy: false,
        content: result.content,
        name: result.name,
        category: "custom",
        notice: undefined,
      });
      return true;
    } catch (error) {
      if (
        this.requestIsCurrent(request) &&
        errorCode(error) !== "save_cancelled"
      ) {
        const code = errorCode(error);
        this.patch({
          notice:
            code === "conflict"
              ? "The library changed elsewhere. Reload the scene before saving."
              : code === "reserved_name"
                ? errorMessage(error)
                : `Save failed: ${errorMessage(error)}`,
        });
      }
      return false;
    } finally {
      this.patch({ saving: false });
    }
  }

  public async savePendingWork(
    isAdmin: boolean,
    panelTransitionEpoch: number,
  ): Promise<boolean> {
    if (
      (this.stateValue.editingCopy ||
        this.stateValue.selectedItem !== undefined) &&
      this.sceneDirty
    ) {
      return this.save(isAdmin, panelTransitionEpoch);
    }
    if (this.sceneDefaultDirty) {
      await this.setCurrentDefault(isAdmin);
      return !this.sceneDefaultDirty;
    }
    return true;
  }

  public async applyCurrent(isAdmin: boolean): Promise<boolean> {
    const { content, selectedItem, selectedScene, speedIndex } =
      this.stateValue;
    if (
      !this.stateUpdatesAvailable ||
      !this.api ||
      !this.device ||
      !content ||
      !selectedScene ||
      !isAdmin ||
      this.stateValue.applying ||
      this.stateValue.saving ||
      !this.hasCurrentSceneContent()
    ) {
      return false;
    }
    const request = this.captureRequest();
    const document = this.currentDocument();
    const current = sceneContentAtSpeed(content, speedIndex);
    this.patch({ applying: true, notice: undefined });
    try {
      if (selectedItem && !this.sceneDirty) {
        await request.api.applySavedEffect(request.deviceId, selectedItem);
      } else {
        await request.api.applySnapshot(
          request.deviceId,
          this.stateValue.name.trim() || selectedScene.display_name,
          current,
        );
      }
      return (
        this.requestIsCurrent(request) &&
        this.currentDocument() === document
      );
    } catch (error) {
      if (this.requestIsCurrent(request)) {
        this.effects.error(`Apply failed: ${errorMessage(error)}`, {
          title: "Apply failed",
          key: `scene-apply:${request.generation}:${errorCode(error)}`,
        });
      }
      return false;
    } finally {
      this.patch({ applying: false });
    }
  }

  public async resetToCatalogue(isAdmin: boolean): Promise<void> {
    const {
      catalogueContent,
      selectedItem,
      selectedScene,
    } = this.stateValue;
    if (
      !this.stateUpdatesAvailable ||
      !selectedScene ||
      !catalogueContent ||
      selectedItem !== undefined ||
      this.stateValue.editingCopy ||
      !this.sceneCatalogueDirty ||
      !isAdmin ||
      !this.hasCurrentSceneContent()
    ) {
      return;
    }
    const content = cloneSceneContent(catalogueContent);
    const speedIndex = content.speed_index;
    this.speedRevision += 1;
    this.defaultRefreshGeneration += 1;
    this.patch({
      content,
      speedIndex,
      notice: undefined,
    });
  }

  public async setCurrentDefault(isAdmin: boolean): Promise<void> {
    const { content, selectedItem, selectedScene, speedIndex } = this.stateValue;
    if (
      !this.stateUpdatesAvailable ||
      !this.api ||
      !this.device ||
      !selectedScene ||
      !content ||
      selectedItem !== undefined ||
      this.stateValue.editingCopy ||
      !this.sceneDefaultDirty ||
      !isAdmin ||
      !this.hasCurrentSceneContent()
    ) {
      return;
    }
    this.defaultRefreshGeneration += 1;
    const savedContent = sceneContentAtSpeed(content, speedIndex);
    this.patch({ content: savedContent, notice: undefined });
    await this.defaultWriter.enqueue(
      this.defaultWrite(savedContent),
    );
    this.patch({});
    await this.flushPendingDefaultRefresh();
  }

  public async refreshSelectedDefault(): Promise<void> {
    const selected = this.stateValue.selectedScene;
    if (!this.api || !this.device || !selected || this.defaultWriter.busy) {
      if (this.defaultWriter.busy) {
        this.defaultRefreshPending = true;
      }
      return;
    }

    const request = this.captureRequest();
    const selectionRevision = this.defaultSelectionRevision;
    const writerGeneration = this.defaultWriter.currentGeneration;
    const refreshGeneration = ++this.defaultRefreshGeneration;
    try {
      const detail = await request.api.sceneDetail(
        request.deviceId,
        selected.scene_id,
        selected.effect_id,
      );
      if (
        this.requestIsCurrent(request) &&
        selectionRevision === this.defaultSelectionRevision &&
        writerGeneration === this.defaultWriter.currentGeneration &&
        refreshGeneration === this.defaultRefreshGeneration &&
        !this.defaultWriter.busy &&
        this.stateValue.selectedScene &&
        sceneKey(this.stateValue.selectedScene) === sceneKey(selected) &&
        sceneKey(detail.scene) === sceneKey(selected)
      ) {
        this.defaultBaseline = this.snapshotFromDetail(detail);
        this.patch({
          catalogueContent: cloneSceneContent(detail.catalogue_content),
          hasDefault: detail.has_default,
        });
      }
    } catch (error) {
      if (
        this.requestIsCurrent(request) &&
        selectionRevision === this.defaultSelectionRevision &&
        writerGeneration === this.defaultWriter.currentGeneration &&
        refreshGeneration === this.defaultRefreshGeneration &&
        !this.defaultWriter.busy
      ) {
        this.patch({ notice: `Could not refresh the scene default: ${errorMessage(error)}` });
      }
    }
  }

  public previewStatusChanged(status: PreviewStatus | undefined): void {
    const selected = this.stateValue.selectedScene;
    if (!status) {
      if (this.defaultPreviewPending) {
        this.defaultPreviewPending = false;
        this.patch({});
      }
      return;
    }
    if (
      !selected ||
      status.config_entry_id !== this.device?.config_entry_id ||
      status.scene_id !== selected.scene_id ||
      status.effect_id !== selected.effect_id
    ) {
      return;
    }
    if (
      status.phase === "queued" &&
      status.persist_default &&
      status.default_action !== null
    ) {
      this.defaultPreviewPending = true;
      this.patch({
        defaultSaveFailed: false,
        notice: undefined,
      });
      return;
    }
    if (!this.defaultPreviewPending) {
      return;
    }
    if (
      status.phase !== "written" &&
      status.phase !== "failed" &&
      status.phase !== "cancelled"
    ) {
      return;
    }
    this.defaultPreviewPending = false;
    if (status.phase === "failed" || status.phase === "cancelled") {
      this.patch({
        defaultSaveFailed: status.phase === "failed",
      });
      return;
    }
    this.patch({ defaultSaveFailed: false });
    void this.refreshSelectedDefault();
  }

  private async flushPendingDefaultRefresh(): Promise<void> {
    if (!this.defaultRefreshPending) {
      return;
    }
    this.defaultRefreshPending = false;
    await this.refreshSelectedDefault();
  }

  public edit(isAdmin: boolean): SceneEditSelection | undefined {
    const { content, selectedItem, selectedScene } = this.stateValue;
    if (!isAdmin || !selectedScene || !this.hasCurrentSceneContent()) {
      return undefined;
    }
    if (!selectedItem) {
      this.invalidateDefaultWrites(true);
    }
    if (selectedScene.scene_type === 2 && content?.kind === "scene_layered") {
      const catalogueContent =
        selectedItem?.content.kind === "scene_layered"
          ? selectedItem.content
          : this.stateValue.catalogueContent?.kind === "scene_layered"
            ? this.stateValue.catalogueContent
            : content;
      return {
        content: cloneLayeredSceneContent({ ...content, speed_index: this.stateValue.speedIndex }),
        catalogue_content: cloneLayeredSceneContent(catalogueContent),
        has_default: selectedItem ? false : this.stateValue.hasDefault,
        config_entry_id: this.device!.config_entry_id,
        ...(selectedItem ? { item: selectedItem } : {}),
        name: selectedItem?.name ?? selectedScene.display_name,
      };
    }
    this.patch({
      editingCopy: true,
      name: `${selectedScene.display_name} copy`,
      notice: undefined,
    });
    return undefined;
  }

  public async cancelCopy(): Promise<boolean> {
    const scene = this.stateValue.selectedScene;
    return this.stateValue.editingCopy && scene ? this.selectBuiltin(scene) : false;
  }

  private defaultWrite(content: SceneContent): SceneDefaultWrite {
    const scene = this.stateValue.selectedScene!;
    return {
      content: cloneSceneContent(content),
      api: this.api!,
      deviceId: this.device!.config_entry_id,
      scene,
      selectionIdentity: sceneKey(scene),
      selectionRevision: this.defaultSelectionRevision,
      speedRevision: this.speedRevision,
    };
  }

  private async performDefaultWrite(write: Readonly<SerialWrite<SceneDefaultWrite>>): Promise<void> {
    const operation = write.payload;
    try {
      const detail = await operation.api.setSceneDefault(
        operation.deviceId,
        operation.content,
      );
      if (sceneKey(detail.scene) !== operation.selectionIdentity) {
        throw new Error("The scene default response did not match the selected scene.");
      }
      if (!this.defaultWriteBelongsToCurrentSelection(operation)) {
        return;
      }
      this.defaultBaseline = this.snapshotFromDetail(detail);
      if (!this.defaultWriter.isLatest(write.generation)) {
        return;
      }
      const speedIndex =
        this.speedRevision === operation.speedRevision
          ? detail.content.speed_index
          : this.stateValue.speedIndex;
      this.patch({
        selectedScene: detail.scene,
        catalogueContent: cloneSceneContent(detail.catalogue_content),
        ...(this.speedRevision === operation.speedRevision
          ? { content: cloneSceneContent(detail.content) }
          : {}),
        speedIndex,
        hasDefault: detail.has_default,
        defaultSaveFailed: false,
        notice: undefined,
      });
    } catch (error) {
      if (
        !this.defaultWriter.isLatest(write.generation) ||
        !this.defaultWriteBelongsToCurrentSelection(operation)
      ) {
        return;
      }
      this.patch({
        defaultSaveFailed: true,
        notice: `Save failed: ${errorMessage(error)}`,
      });
    }
  }

  private snapshotFromDetail(detail: SceneDetail): SceneDefaultSnapshot {
    return {
      scene: { ...detail.scene },
      content: cloneSceneContent(detail.content),
      speedIndex: detail.content.speed_index,
      hasDefault: detail.has_default,
    };
  }

  private defaultWriteBelongsToCurrentSelection(operation: SceneDefaultWrite): boolean {
    return Boolean(
      operation.selectionRevision === this.defaultSelectionRevision &&
        this.activeSelectionIdentity === operation.selectionIdentity &&
        this.stateValue.selectedItem === undefined &&
        !this.stateValue.editingCopy &&
        this.stateValue.selectedScene &&
        sceneKey(this.stateValue.selectedScene) === operation.selectionIdentity,
    );
  }

  private invalidateDefaultWrites(preserveBaseline = false): void {
    this.defaultSelectionRevision += 1;
    this.speedRevision = 0;
    this.defaultRefreshGeneration += 1;
    if (!preserveBaseline) {
      this.defaultBaseline = undefined;
    }
    this.defaultRefreshPending = false;
    this.defaultPreviewPending = false;
    this.defaultWriter.invalidate();
  }

  private async openInitialSavedScene(itemId: string): Promise<boolean> {
    const summary = this.compatibleCustomScenes.find((item) => item.id === itemId);
    return summary ? this.selectCustom(summary) : false;
  }

  private async openInitialNativeScene(effect: string): Promise<boolean> {
    const catalogue = this.stateValue.catalogue;
    const scene = catalogue ? findNativeScene(catalogue, effect) : undefined;
    return scene ? this.selectBuiltin(scene) : false;
  }

  private clearSelection(): boolean {
    this.invalidateRequests();
    this.patch({
      selectedScene: undefined,
      selectedItem: undefined,
      content: undefined,
      catalogueContent: undefined,
      name: "",
      speedIndex: null,
      hasDefault: false,
      editingCopy: false,
      notice: undefined,
    });
    return true;
  }

  private async reloadSelectedCustom(
    summary: LibrarySummary,
    expectedItem: LibraryItem,
  ): Promise<void> {
    if (!this.api || !this.device || !this.stateValue.catalogue) {
      return;
    }
    const request = this.captureRequest();
    const catalogue = this.stateValue.catalogue;
    try {
      const item = await request.api.item(summary.id);
      if (!isSceneContent(item.content)) {
        throw new Error("This custom scene uses an unsupported definition.");
      }
      const content = item.content;
      if (content.template.sku !== catalogue.sku) {
        throw new Error(`This custom scene targets ${content.template.sku}, not ${catalogue.sku}.`);
      }
      const scene = findCatalogueScene(catalogue, content);
      if (!scene) {
        throw new Error("The source scene is not in this device catalogue.");
      }
      const detail = await request.api.sceneDetail(
        request.deviceId,
        content.template.scene_id,
        content.template.effect_id,
      );
      const currentItem = this.stateValue.selectedItem;
      if (
        !this.requestIsCurrent(request) ||
        this.stateValue.saving ||
        this.sceneDirty ||
        currentItem?.id !== expectedItem.id ||
        currentItem.version !== expectedItem.version ||
        sceneKey(detail.scene) !== sceneKey(scene)
      ) {
        if (currentItem?.id === expectedItem.id && this.sceneDirty) {
          this.patch({ notice: "This custom scene changed elsewhere. Reload it before saving." });
        }
        return;
      }
      this.commitCustomSelection(item, scene, content);
      this.patch({ notice: undefined });
    } catch (error) {
      if (this.requestIsCurrent(request)) {
        this.patch({ notice: errorMessage(error) });
      }
    }
  }

  private commitCustomSelection(item: LibraryItem, scene: SceneSummary, content: SceneContent): void {
    const selectedContent = cloneSceneContent(content);
    this.patch({
      category: visibleCategoryForCustom(this.stateValue.category),
      selectedScene: scene,
      selectedItem: item,
      editingCopy: false,
      content: selectedContent,
      hasDefault: false,
      name: item.name,
      speedIndex: selectedContent.speed_index ?? scene.speed?.default_index ?? null,
    });
  }

  private beginRequest(selectionIdentity?: string): SceneRequestContext {
    this.invalidateDefaultWrites();
    this.activeSelectionIdentity = selectionIdentity;
    return this.requests.begin(this.requestState());
  }

  private captureRequest(): SceneRequestContext {
    return this.requests.capture(this.requestState());
  }

  private invalidateRequests(): void {
    this.invalidateDefaultWrites();
    this.requests.invalidate();
    this.activeSelectionIdentity = undefined;
  }

  private requestIsCurrent(request: SceneRequestContext): boolean {
    return Boolean(this.api && this.device && this.requests.isCurrent(request, this.requestState()));
  }

  private requestState(): SceneRequestState {
    return {
      api: this.api!,
      deviceId: this.device!.config_entry_id,
      category: this.stateValue.category,
      selectionIdentity: this.activeSelectionIdentity,
    };
  }

  private currentDocument(): string {
    return JSON.stringify({
      name: this.stateValue.name,
      content: this.stateValue.content,
      speedIndex: this.stateValue.speedIndex,
      selectedItemId: this.stateValue.selectedItem?.id,
      selectedItemVersion: this.stateValue.selectedItem?.version,
    });
  }

  public setStateUpdatesAvailable(available: boolean): void {
    if (this.stateUpdatesAvailable === available) {
      return;
    }
    this.stateUpdatesAvailable = available;
    if (!available) {
      this.defaultWriter.invalidate();
      this.invalidateRequests();
      this.patch({ saving: false });
    }
  }

  private patch(values: Partial<SceneBrowserViewState>): void {
    const notice = values.notice;
    const error = values.error;
    if (notice) {
      this.effects.error(notice, {
        title: "Scene operation failed",
        key: `scene:${++this.errorSequence}`,
      });
    }
    if (error) {
      this.effects.error(error, {
        title: "Scenes unavailable",
        key: `scene-load:${error}`,
      });
    }
    this.stateValue = {
      ...this.stateValue,
      ...values,
      ...(notice ? { notice: undefined } : {}),
    };
    this.effects.changed(this.stateValue);
    this.effects.workStateChanged(
      this.protectedWorkDirty,
    );
  }
}
