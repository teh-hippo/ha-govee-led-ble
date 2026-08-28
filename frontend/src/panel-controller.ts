import { EffectStudioApi } from "./api";
import { AsyncRequestController, type AsyncRequestToken } from "./async-request-controller";
import { cloneBuiltInDefaultBaselines } from "./built-in-default-state";
import type { CustomEffectListEntry } from "./custom-effect-list";
import {
  cloneEditableEffect, customEffectCategoryForKind, isEditableEffectContent,
  libraryItemSyncResult, sameLibraryItemVersion, serialiseEditable, upsertSummary, type CustomEffectCategory,
  type EditableEffectContent,
} from "./effect-editor-model";
import type { EditorOwner } from "./editor-state";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { PanelEditorController } from "./panel-editor-controller";
import { PanelModalController } from "./panel-modal-controller";
import { PanelModel } from "./panel-model";
import { PanelPreviewController } from "./panel-preview-controller";
import {
  activeStudioContext,
  editorDevicePath,
  initialDeviceId,
  rememberedStudioSection,
  type StudioSection,
} from "./studio-navigation";
import type {
  CatalogueTemplateContent,
  DeviceCapabilities,
  EffectUserState,
  HomeAssistant,
  LibraryItem,
  LibrarySnapshot,
} from "./types";
import type { SceneEditSelection } from "./scene-browser-workflow";
import type { ScenePreviewRequest } from "./scene-browser";
import { errorCode, errorMessage } from "./ui-utils";
import { isCompatibleEditorInfo } from "./validation";

type LoadRequest = AsyncRequestToken<{ api: EffectStudioApi }>;
interface LibraryAutoSaveTarget {
  kind: "library";
  epoch: number;
  item: LibraryItem;
  name: string;
  content: EditableEffectContent;
}

interface BuiltInAutoSaveTarget {
  kind: "built-in";
  epoch: number;
  configEntryId: string;
  templateId?: string;
  content: EditableEffectContent;
}

type AutoSaveTarget = LibraryAutoSaveTarget | BuiltInAutoSaveTarget;

interface LibraryReloadGuard {
  itemId: string;
  version: number;
  document: string;
}

interface PendingTransition {
  epoch: number;
  itemId?: string;
  execute: () => void | Promise<void>;
  save?: () => Promise<boolean>;
}

interface PanelControllerOptions {
  connected(): boolean;
  pathname(): string;
  replacePath(path: string): void;
  saveSceneWork?(): Promise<boolean>;
}

export class PanelController {
  public api?: EffectStudioApi;

  private unsubscribeLibrary?: () => void;
  private unsubscribeDevice?: () => void;
  private autoSavePending?: AutoSaveTarget;
  private autoSaveRunning = false;
  private autoSaveDrain?: Promise<boolean>;
  private lastSaveCancelled = false;
  private stateUpdatesGeneration = 0;
  private pendingTransition?: PendingTransition;
  private deviceRefresh?: {
    api: EffectStudioApi;
    configEntryId: string;
    promise: Promise<DeviceCapabilities>;
  };
  private readonly latestSavedItems = new Map<string, LibraryItem>();
  private readonly loadRequests = new AsyncRequestController<{ api: EffectStudioApi }>(
    (left, right) => left.api === right.api,
  );

  public constructor(
    private readonly model: PanelModel,
    private readonly editor: PanelEditorController,
    private readonly preview: PanelPreviewController,
    private readonly modal: PanelModalController,
    private readonly options: PanelControllerOptions,
  ) {
    this.modal.setTransitionDialogTeardown(() => {
      this.pendingTransition = undefined;
    });
  }

  public async load(hass: HomeAssistant, isAdmin: boolean): Promise<void> {
    this.stateUpdatesGeneration += 1;
    this.model.patch({
      loading: true,
      error: undefined,
      previewStatus: undefined,
      previewNotice: undefined,
      stateUpdatesUnavailable: false,
      sceneWorkDirty: false,
      isAdmin,
    });
    const api = new EffectStudioApi(hass);
    api.setLibrarySnapshotHandler((snapshot) =>
      this.libraryChanged(snapshot),
    );
    api.setOverwriteConfirmation((effectName) =>
      this.confirmOverwrite(effectName),
    );
    this.api = api;
    const request = this.loadRequests.begin({ api });
    try {
      const [info, devices, library, customCatalogue, userState] = await Promise.all([
        api.info(), api.devices(), api.library(), api.customCatalogue(), api.userState(),
      ]);
      if (!this.loadIsCurrent(request)) return;
      if (!isCompatibleEditorInfo(info)) {
        throw new Error("This editor bundle is not compatible with the installed backend.");
      }
      this.model.patch({
        devices,
        library,
        customCatalogue,
        userState,
        autoSaveEnabled: restoredAutoSave(userState.navigation.auto_save),
      });
      await this.initialiseSelectedDevice();
      if (!this.model.customEffectsAvailable) this.model.patch({ section: "scenes" });
      const unsubscribeLibrary = await api.subscribeLibrary(
        (snapshot) => void this.libraryChanged(snapshot),
        (error) => this.subscriptionFailed(error, request),
      );
      if (
        !this.loadIsCurrent(request) ||
        this.model.error ||
        this.model.stateUpdatesUnavailable
      ) {
        unsubscribeLibrary();
        return;
      }
      this.unsubscribeLibrary = unsubscribeLibrary;
      await this.subscribeSelectedDevice(api);
      if (
        !this.loadIsCurrent(request) ||
        this.model.error ||
        this.model.stateUpdatesUnavailable
      ) {
        return;
      }
      if (isAdmin) {
        const opened = await this.preview.open(api, (error) => this.subscriptionFailed(error, request));
        if (
          !opened ||
          !this.loadIsCurrent(request) ||
          this.model.error ||
          this.model.stateUpdatesUnavailable
        ) {
          this.preview.dispose();
          return;
        }
      }
      await this.openInitialContext();
    } catch (error) {
      if (this.loadIsCurrent(request)) {
        this.stopSubscriptions();
        this.model.patch({ error: errorMessage(error) });
      }
    } finally {
      if (this.loadIsCurrent(request)) this.model.patch({ loading: false });
    }
  }

  public disconnect(): void {
    this.cancelPendingAutoSave();
    this.pendingTransition = undefined;
    this.modal.closeTransition(false);
    this.loadRequests.invalidate();
    this.stopSubscriptions();
    this.api = undefined;
  }

  public async deviceChanged(
    selectedDeviceId: string,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    if (
      !selectedDeviceId || selectedDeviceId === this.model.selectedDeviceId ||
      !this.model.devices.some((device) => device.config_entry_id === selectedDeviceId)
    ) return;
    await this.requestTransition(
      () => this.performDeviceChange(selectedDeviceId),
      returnFocus,
    );
  }

  private async performDeviceChange(selectedDeviceId: string): Promise<void> {
    const previousDeviceId = this.model.selectedDeviceId;
    const transitionEpoch = this.editor.beginTransition();
    this.editor.clearSelection(transitionEpoch);
    this.model.patch({
      selectedDeviceId,
      previewStatus: undefined,
      previewNotice: undefined,
      notice: undefined,
    });
    this.openRootCreateView();
    const rootEpoch = this.model.editorTransitionEpoch;
    await this.preview.cancel(previousDeviceId);
    if (this.api) {
      await this.subscribeSelectedDevice(this.api);
    }
    if (this.model.stateUpdatesUnavailable) {
      return;
    }
    this.options.replacePath(editorDevicePath(selectedDeviceId));
    const updatesGeneration = this.stateUpdatesGeneration;
    try {
      const userState = await this.api?.updateUserState(
        selectedDeviceId,
        this.navigationPreferences,
      );
      if (
        userState &&
        !this.model.stateUpdatesUnavailable &&
        updatesGeneration === this.stateUpdatesGeneration
      ) {
        this.model.patch({ userState });
      }
    } catch (error) {
      console.warn("Could not remember the selected light", error);
    }
    if (
      !this.model.stateUpdatesUnavailable &&
      updatesGeneration === this.stateUpdatesGeneration &&
      rootEpoch === this.model.editorTransitionEpoch &&
      selectedDeviceId === this.model.selectedDeviceId
    ) {
      await this.restoreActiveSelection(rootEpoch, true);
    }
  }

  public async selectSection(
    section: StudioSection,
    customEffectCategory?: CustomEffectCategory,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    if (
      (section === "scenes" && !this.model.scenesAvailable) ||
      (section === "custom" &&
        (!this.model.customEffectsAvailable ||
          (customEffectCategory !== undefined &&
            !this.model.customEffectCategoryAvailable(customEffectCategory)))) ||
      (section === "video" && !this.model.videoAvailable)
    ) return;
    const nextCategory =
      section === "custom" && customEffectCategory !== undefined
        ? customEffectCategory
        : this.model.customEffectCategory;
    const previousSection = this.model.section;
    const navigationChanged =
      section !== this.model.section ||
      (section === "custom" &&
        nextCategory !== this.model.customEffectCategory);
    const selectionOwned =
      this.model.editorOwnedByActiveView &&
      section === this.model.section &&
      (section !== "custom" ||
        nextCategory === this.model.customEffectCategory);
    if (!navigationChanged && selectionOwned) {
      if (section === "scenes" && this.model.sceneEditorOpen) {
        this.editor.cancelSceneEdit();
      }
      return;
    }
    await this.requestTransition(() =>
      this.performSectionChange(section, nextCategory, previousSection),
      returnFocus,
    );
  }

  private async performSectionChange(
    section: StudioSection,
    nextCategory: CustomEffectCategory,
    previousSection: StudioSection,
  ): Promise<void> {
    const transitionEpoch = this.editor.beginTransition();
    this.model.patch({
      sceneEditorOpen: false,
      sceneInitialSelection: undefined,
      section,
      customEffectCategory: nextCategory,
      notice: undefined,
    });
    const preserveWhileBrowsingScenes =
      section === "scenes" && this.model.editorSource.kind !== "scene";
    const returningToRetainedSelection =
      previousSection === "scenes" && this.model.editorOwnedByActiveView;
    if (
      this.model.editorSource.kind === "scene" ||
      (!preserveWhileBrowsingScenes && !returningToRetainedSelection)
    ) {
      this.editor.clearSelection(transitionEpoch);
    }
    this.remember();
    await this.restoreActiveSelection(transitionEpoch);
  }

  public async selectCustomEffectEntry(
    entry: CustomEffectListEntry,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    if (entry.kind !== "saved") {
      await this.requestTransition(
        async () => {
          const owner: EditorOwner = {
            section: "custom",
            category: entry.category,
          };
          await this.openCatalogueTemplate(
            entry.key,
            entry.label,
            owner,
            this.editor.beginSelectionTransition(),
            true,
          );
        },
        returnFocus,
      );
      return;
    }
    await this.requestTransition(
      () => this.editor.selectCustomEffectEntry(entry),
      returnFocus,
    );
  }

  public async newCustomEffect(
    category: CustomEffectCategory,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    await this.requestTransition(
      () => this.editor.newCustomEffect(category),
      returnFocus,
    );
  }

  public async openSceneEditor(
    detail: SceneEditSelection,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    await this.requestTransition(
      () => {
        this.model.patch({ sceneWorkDirty: false });
        this.editor.openSceneEditor(detail);
      },
      returnFocus,
    );
  }

  public async selectVideoTemplate(
    mode: string,
    label: string,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    await this.requestTransition(
      async () => {
        await this.openCatalogueTemplate(
          `template:video:${mode}`,
          label,
          { section: "video" },
          this.editor.beginSelectionTransition(),
          true,
        );
      },
      returnFocus,
    );
  }

  public async selectCatalogueTemplate(
    templateId: string,
    label: string,
    owner: EditorOwner,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    await this.requestTransition(
      async () => {
        await this.openCatalogueTemplate(
          templateId,
          label,
          owner,
          this.editor.beginSelectionTransition(),
          true,
        );
      },
      returnFocus,
    );
  }

  public async selectItemFromList(
    itemId: string,
    returnFocus?: HTMLElement,
  ): Promise<void> {
    await this.requestTransition(
      async () => {
        await this.selectItem(
          itemId,
          this.editor.beginSelectionTransition(),
        );
      },
      returnFocus,
    );
  }

  public async selectScene(
    selection: () => void | Promise<void>,
    returnFocus?: HTMLElement,
    save?: () => Promise<boolean>,
  ): Promise<void> {
    await this.requestTransition(async () => {
      if (this.model.editorSource.kind !== "none") {
        const transitionEpoch = this.editor.beginTransition();
        this.editor.clearSelection(transitionEpoch);
        this.model.patch({ sceneEditorOpen: false });
      }
      await selection();
    }, returnFocus, save);
  }

  public async openInitialContext(): Promise<void> {
    this.openRootCreateView();
    await this.restoreActiveSelection(this.model.editorTransitionEpoch, true);
  }

  private async restoreActiveSelection(
    transitionEpoch: number,
    navigateToContext = false,
  ): Promise<void> {
    const device = this.model.selectedDevice;
    if (
      !device ||
      transitionEpoch !== this.model.editorTransitionEpoch
    ) {
      return;
    }
    const context = activeStudioContext(
      device,
      this.model.library.items,
      (candidate) =>
        candidate.kind === "scene_builtin" || candidate.kind === "scene_palette" || candidate.kind === "scene_layered"
          ? candidate.template?.sku === this.model.selectedModel
          : this.model.libraryItemAvailable(candidate),
      this.model.modelCatalogue,
    );
    if (context.kind === "native-scene") {
      if (!this.model.scenesAvailable) {
        return;
      }
      if (navigateToContext) {
        this.model.patch({
          section: "scenes",
          sceneEditorOpen: false,
          notice: undefined,
        });
      }
      if (this.model.section === "scenes") {
        this.model.patch({ sceneInitialSelection: { kind: "native", effect: context.effect } });
      }
      return;
    }
    if (this.model.section === "scenes") {
      this.model.patch({ sceneInitialSelection: { kind: "none" } });
    }
    if (context.kind === "native-profile") {
      if (
        (context.section === "video" && !this.model.videoAvailable) ||
        (context.section === "custom" &&
          (!context.category ||
            !this.model.customEffectCategoryAvailable(context.category)))
      ) {
        return;
      }
      if (navigateToContext) {
        this.model.patch({
          section: context.section,
          ...(context.section === "custom" && context.category
            ? { customEffectCategory: context.category }
            : {}),
          sceneEditorOpen: false,
          notice: undefined,
        });
      }
      if (
        context.section !== this.model.section ||
        (context.section === "custom" &&
          context.category !== this.model.customEffectCategory)
      ) {
        return;
      }
      if (context.section === "video") {
        await this.openCatalogueTemplate(
          `template:video:${context.mode}`,
          context.label,
          { section: "video" },
          transitionEpoch,
          false,
        );
      } else {
        await this.openCatalogueTemplate(
          `template:music:${context.mode}`,
          context.label,
          {
            section: "custom",
            category: context.category ?? "music",
          },
          transitionEpoch,
          false,
        );
      }
      return;
    }
    if (context.kind === "workspace") {
      if (
        (context.section === "video" && !this.model.videoAvailable) ||
        (context.section === "custom" &&
          (!context.category ||
            !this.model.customEffectCategoryAvailable(context.category)))
      ) {
        return;
      }
      if (navigateToContext) {
        this.model.patch({
          section: context.section,
          ...(context.section === "custom" && context.category
            ? { customEffectCategory: context.category }
            : {}),
          sceneEditorOpen: false,
          notice: undefined,
        });
      }
      if (
        context.section !== this.model.section ||
        (context.section === "custom" &&
          context.category !== this.model.customEffectCategory)
      ) {
        return;
      }
      if (!this.editor.openActiveWorkspace(context, transitionEpoch)) {
        this.editor.clearSelection(transitionEpoch);
      } else if (this.model.editorSource.kind === "catalogue") {
        await this.refreshCurrentBuiltInBaselines(
          this.model.editorSource.selectionIdentity,
          transitionEpoch,
        );
      }
      return;
    }
    if (context.kind === "root") {
      return;
    }
    const item = context.item;
    if (item.kind === "scene_builtin" || item.kind === "scene_palette" || item.kind === "scene_layered") {
      if (!this.model.scenesAvailable) {
        return;
      }
      if (navigateToContext) {
        this.model.patch({
          section: "scenes",
          sceneEditorOpen: false,
          notice: undefined,
        });
      }
      if (this.model.section === "scenes") {
        this.model.patch({ sceneInitialSelection: { kind: "saved", itemId: item.id } });
      }
      return;
    }
    if (
      (item.kind === "video_profile" && !this.model.videoAvailable) ||
      (item.kind !== "video_profile" &&
        !this.model.customEffectCategoryAvailable(
          this.categoryForKind(item.kind),
        ))
    ) {
      return;
    }
    if (navigateToContext) {
      this.model.patch(
        item.kind === "video_profile"
          ? {
              section: "video",
              sceneEditorOpen: false,
              notice: undefined,
            }
          : {
              section: "custom",
              customEffectCategory: this.categoryForKind(item.kind),
              sceneEditorOpen: false,
              notice: undefined,
            },
      );
    }
    if (
      (item.kind === "video_profile" && this.model.section !== "video") ||
      (item.kind !== "video_profile" &&
        (this.model.section !== "custom" ||
          this.categoryForKind(item.kind) !==
            this.model.customEffectCategory))
    ) {
      return;
    }
    if (!(await this.selectItem(item.id, transitionEpoch, false))) {
      this.editor.clearSelection(transitionEpoch);
    }
  }

  private async openCatalogueTemplate(
    templateId: string,
    label: string,
    owner: EditorOwner,
    transitionEpoch: number,
    preview: boolean,
  ): Promise<boolean> {
    const api = this.api;
    const device = this.model.selectedDevice;
    if (!api || !device) {
      return false;
    }
    try {
      const detail = await api.templateDefault(
        device.config_entry_id,
        templateId,
      );
      if (
        api !== this.api ||
        transitionEpoch !== this.model.editorTransitionEpoch ||
        device.config_entry_id !== this.model.selectedDeviceId ||
        !isEditableEffectContent(detail.content) ||
        !isEditableEffectContent(detail.catalogue_content)
      ) {
        return false;
      }
      this.editor.openEditableTemplate(
        label,
        detail.content,
        templateId,
        owner,
        preview,
        transitionEpoch,
        detail.catalogue_content,
        detail.has_default,
      );
      return true;
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice: `Could not load the built-in default: ${errorMessage(error)}`,
        });
      }
      return false;
    }
  }

  private async refreshCurrentBuiltInBaselines(
    templateId: string,
    transitionEpoch: number,
  ): Promise<void> {
    const api = this.api;
    const device = this.model.selectedDevice;
    if (!api || !device) {
      return;
    }
    try {
      const detail = await api.templateDefault(
        device.config_entry_id,
        templateId,
      );
      if (
        api === this.api &&
        transitionEpoch === this.model.editorTransitionEpoch &&
        this.model.editorSource.kind === "catalogue" &&
        this.model.editorSource.selectionIdentity === templateId &&
        isEditableEffectContent(detail.content) &&
        isEditableEffectContent(detail.catalogue_content)
      ) {
        this.model.patch({
          resetBaseline: cloneEditableEffect(detail.catalogue_content),
          builtInBaselines: cloneBuiltInDefaultBaselines(
            detail.catalogue_content,
            detail.content,
            detail.has_default,
          ),
        });
      }
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice: `Could not refresh the built-in default: ${errorMessage(error)}`,
        });
      }
    }
  }

  public sceneInitialSelectionOpened(): void {
    this.model.patch({ section: "scenes", sceneInitialSelection: undefined });
  }

  public sceneInitialSelectionFailed(): void {
    this.model.patch({ sceneInitialSelection: undefined });
  }

  public remember(): void {
    void this.rememberNavigation();
  }

  public toggleAutoSave(scene?: ScenePreviewRequest): void {
    if (this.model.stateUpdatesUnavailable) {
      return;
    }
    const autoSaveEnabled = !this.model.autoSaveEnabled;
    this.model.patch({
      autoSaveEnabled,
      autoSaveFailed: false,
    });
    if (autoSaveEnabled) {
      if (
        this.model.builtInDefaultSource &&
        this.model.builtInDefaultDirty &&
        this.model.liveApplyEnabled
      ) {
        this.preview.scheduleEdited("committed");
      } else if (
        this.model.section === "scenes" &&
        !this.model.sceneEditorOpen &&
        scene
      ) {
        if (this.model.liveApplyEnabled) {
          this.preview.scheduleScene({
            ...scene,
            persistDefault: true,
          });
        } else {
          void this.options.saveSceneWork?.();
        }
      } else {
        this.contentCommitted("committed");
      }
    } else {
      this.cancelPendingAutoSave();
    }
    this.remember();
  }

  public contentCommitted(interaction: LivePreviewInteraction): void {
    if (this.model.stateUpdatesUnavailable) {
      return;
    }
    if (
      interaction !== "committed" ||
      !this.model.isAdmin ||
      !this.model.autoSaveEnabled ||
      !isEditableEffectContent(this.model.content)
    ) {
      return;
    }
    if (this.model.builtInDefaultSource) {
      if (!this.model.builtInDefaultDirty || this.model.liveApplyEnabled) {
        return;
      }
      const configEntryId = this.model.selectedDeviceId;
      if (!configEntryId) {
        return;
      }
      this.autoSavePending = {
        kind: "built-in",
        epoch: this.model.editorTransitionEpoch,
        configEntryId,
        ...(this.model.editorSource.kind === "catalogue"
          ? { templateId: this.model.editorSource.selectionIdentity }
          : {}),
        content: cloneEditableEffect(this.model.content),
      };
      if (!this.autoSaveRunning) {
        this.autoSaveDrain = this.drainAutoSave();
      }
      return;
    }
    if (
      this.model.sceneEditorOpen ||
      !this.model.currentItem ||
      !this.model.dirty
    ) {
      return;
    }
    this.autoSavePending = {
      kind: "library",
      epoch: this.model.editorTransitionEpoch,
      item: this.model.currentItem,
      name: this.model.name.trim(),
      content: cloneEditableEffect(this.model.content),
    };
    if (!this.autoSaveRunning) {
      this.autoSaveDrain = this.drainAutoSave();
    }
  }

  public cancelPendingAutoSave(): void {
    this.autoSavePending = undefined;
  }

  public get unloadProtectionRequired(): boolean {
    return this.model.localWorkNeedsProtection;
  }

  public async requestTransition(
    execute: () => void | Promise<void>,
    returnFocus?: HTMLElement,
    save?: () => Promise<boolean>,
  ): Promise<boolean> {
    if (this.pendingTransition || this.modal.open) {
      return false;
    }
    if (this.model.stateUpdatesUnavailable) {
      this.modal.showError("Reload the page before continuing.", {
        title: "State updates stopped",
        key: "subscription:reload-before-transition",
        resumeWorkflow: false,
      });
      return false;
    }
    const updatesGeneration = this.stateUpdatesGeneration;
    const panelOwnsDirtyWork =
      this.model.editorOwnedByActiveView &&
      (this.model.builtInDefaultSource
        ? this.model.builtInDefaultDirty
        : this.model.dirty || this.model.resetDirty);
    const saveWork =
      save ??
      (this.model.sceneWorkDirty && !panelOwnsDirtyWork
        ? this.options.saveSceneWork ??
          (() => Promise.resolve(false))
        : undefined);
    const owner: PendingTransition = {
      epoch: this.model.editorTransitionEpoch,
      itemId: this.model.currentItem?.id,
      execute,
      save: saveWork,
    };
    if (
      this.model.editorSource.kind === "saved" &&
      this.model.dirty &&
      this.model.autoSaveEnabled &&
      !this.model.autoSaveFailed
    ) {
      if (await this.flushAutoSave(owner)) {
        if (
          this.model.stateUpdatesUnavailable ||
          updatesGeneration !== this.stateUpdatesGeneration
        ) {
          return false;
        }
        await this.executeOwnedTransition(owner);
        return true;
      }
      if (
        this.model.stateUpdatesUnavailable ||
        updatesGeneration !== this.stateUpdatesGeneration ||
        owner.epoch !== this.model.editorTransitionEpoch ||
        owner.itemId !== this.model.currentItem?.id
      ) {
        return false;
      }
    } else if (
      this.model.builtInDefaultSource &&
      this.model.builtInDefaultDirty &&
      this.model.autoSaveEnabled &&
      !this.model.autoSaveFailed
    ) {
      if (await this.saveBuiltInDefault()) {
        await this.executeOwnedTransition(owner);
        return true;
      }
    } else if (
      !this.model.localWorkNeedsProtection &&
      !(
        this.model.editorSource.kind === "saved" &&
        this.model.autoSaveFailed
      )
    ) {
      await this.executeOwnedTransition(owner);
      return true;
    }
    this.pendingTransition = owner;
    this.modal.requestTransition(
      "Save",
      this.model.name.trim(),
      !saveWork && this.model.editorSource.kind === "new",
      returnFocus,
    );
    return false;
  }

  public cancelPendingTransition(): void {
    if (
      !this.pendingTransition ||
      this.model.pendingTransitionDialog?.busy
    ) {
      return;
    }
    this.pendingTransition = undefined;
    this.modal.closeTransition(true);
  }

  public async declinePendingTransition(): Promise<void> {
    if (this.model.stateUpdatesUnavailable) {
      return;
    }
    const pending = this.takePendingTransition();
    if (
      pending &&
      pending.epoch === this.model.editorTransitionEpoch &&
      pending.itemId === this.model.currentItem?.id
    ) {
      this.editor.clearSelection(pending.epoch);
      await pending.execute();
    }
  }

  public async savePendingTransition(): Promise<void> {
    const pending = this.pendingTransition;
    const updatesGeneration = this.stateUpdatesGeneration;
    const dialog = this.model.pendingTransitionDialog;
    if (!pending || !dialog || dialog.busy) {
      return;
    }
    const name = dialog.saveName.trim();
    if (dialog.requiresName && !name) {
      this.modal.showError("Enter an effect name.", {
        title: "Effect name required",
        key: `transition-name-required:${pending.epoch}`,
      });
      return;
    }
    if (dialog.primaryLabel === "Save" && dialog.requiresName) {
      this.model.patch({ name });
    }
    this.modal.updateTransition({ busy: true, error: undefined });
    const saved =
      pending.save
        ? await pending.save()
        : dialog.primaryLabel === "Save"
        ? await this.save()
        : await this.saveAs(name);
    if (
      this.model.stateUpdatesUnavailable ||
      updatesGeneration !== this.stateUpdatesGeneration
    ) {
      return;
    }
    if (!saved) {
      if (this.lastSaveCancelled) {
        this.modal.updateTransition({ busy: false, error: undefined });
        return;
      }
      const errorAlreadyVisible =
        this.model.modalState?.kind === "error" &&
        this.model.modalState.resume?.kind === "pending-transition";
      this.modal.updateTransition({ busy: false, error: undefined });
      if (errorAlreadyVisible) {
        return;
      }
      if (this.model.modalState?.kind === "pending-transition") {
        this.modal.showError("The effect could not be saved.", {
          title: "Save failed",
          key: `transition-save-failed:${pending.epoch}`,
        });
      }
      return;
    }
    const owned = this.takePendingTransition();
    if (owned?.epoch === this.model.editorTransitionEpoch) {
      await owned.execute();
    }
  }

  private takePendingTransition(): PendingTransition | undefined {
    const pending = this.pendingTransition;
    this.pendingTransition = undefined;
    this.modal.closeTransition(false);
    return pending;
  }

  private async executeOwnedTransition(
    pending: PendingTransition,
  ): Promise<void> {
    if (
      this.model.stateUpdatesUnavailable ||
      pending.epoch !== this.model.editorTransitionEpoch ||
      pending.itemId !== this.model.currentItem?.id
    ) {
      return;
    }
    await pending.execute();
  }

  private async flushAutoSave(owner: PendingTransition): Promise<boolean> {
    if (
      this.model.stateUpdatesUnavailable ||
      !this.model.currentItem ||
      !isEditableEffectContent(this.model.content)
    ) {
      return false;
    }
    this.autoSavePending = {
      kind: "library",
      epoch: owner.epoch,
      item: this.model.currentItem,
      name: this.model.name.trim(),
      content: cloneEditableEffect(this.model.content),
    };
    if (!this.autoSaveRunning) {
      this.autoSaveDrain = this.drainAutoSave();
    }
    const succeeded = await this.autoSaveDrain;
    if (
      succeeded === true &&
      !this.model.stateUpdatesUnavailable &&
      owner.epoch === this.model.editorTransitionEpoch
    ) {
      owner.itemId = this.model.currentItem?.id;
      return !this.model.dirty;
    }
    return false;
  }

  public async libraryChanged(snapshot: LibrarySnapshot): Promise<boolean> {
    if (
      (snapshot.generation ?? 0) <
      (this.model.library.generation ?? 0)
    ) {
      return false;
    }
    this.model.patch({ library: snapshot });
    if (this.model.saving) {
      return true;
    }
    if (this.model.currentItem && !this.model.editorOwnedByActiveView) {
      const summary = snapshot.items.find(
        (item) => item.id === this.model.currentItem?.id,
      );
      if (
        !summary ||
        summary.version !== this.model.currentItem.version
      ) {
        this.editor.clearRetainedSelection();
      }
      return true;
    }
    const sync = libraryItemSyncResult(this.model.currentItem, snapshot.items, this.model.dirty, this.model.deletingItemId);
    if (sync.action === "none") return true;
    if (sync.action === "removed") {
      this.model.patch({ notice: undefined });
      return true;
    }
    if (sync.action === "conflict") {
      this.model.patch({ notice: "This effect changed elsewhere. Reload it before saving." });
      return true;
    }
    const currentItem = this.model.currentItem;
    if (!currentItem) {
      return true;
    }
    const guard: LibraryReloadGuard = {
      itemId: currentItem.id,
      version: currentItem.version,
      document: this.currentEditorDocument(),
    };
    const transitionEpoch = this.editor.beginTransition();
    const selected = await this.selectItem(
      sync.summary.id,
      transitionEpoch,
      false,
      guard,
    );
    if (selected && transitionEpoch === this.model.editorTransitionEpoch) {
      this.model.patch({ notice: undefined });
    } else if (
      transitionEpoch === this.model.editorTransitionEpoch &&
      this.model.currentItem?.id === guard.itemId &&
      this.currentEditorDocument() !== guard.document
    ) {
      this.model.patch({ notice: "This effect changed elsewhere. Reload it before saving." });
    }
    return true;
  }

  public async sceneItemSaved(
    item: LibraryItem,
    configEntryId: string,
    selectionIsCurrent: boolean,
    panelTransitionEpoch: number,
  ): Promise<void> {
    this.model.patch({
      library: {
        ...this.model.library,
        items: upsertSummary(this.model.library.items, item),
      },
    });
    if (
      selectionIsCurrent &&
      this.model.liveApplyEnabled &&
      this.model.selectedDeviceId === configEntryId &&
      this.model.section === "scenes" &&
      this.model.editorTransitionEpoch === panelTransitionEpoch
    ) {
      await this.applySavedIdentity(item, this.model.editorTransitionEpoch);
    }
  }

  public async toggleLive(scene?: ScenePreviewRequest): Promise<void> {
    if (this.model.stateUpdatesUnavailable) {
      return;
    }
    if (this.model.liveApplyEnabled) {
      this.preview.toggle(scene);
      if (this.model.autoSaveEnabled) {
        if (
          this.model.builtInDefaultSource &&
          this.model.builtInDefaultDirty
        ) {
          await this.saveBuiltInDefault();
        } else if (
          this.model.section === "scenes" &&
          !this.model.sceneEditorOpen &&
          scene?.persistDefault
        ) {
          await this.options.saveSceneWork?.();
        }
      }
      return;
    }
    const currentItem = this.model.currentItem;
    if (
      currentItem &&
      this.model.editorSource.kind === "saved" &&
      this.model.editorOwnedByActiveView &&
      !this.model.dirty
    ) {
      this.model.patch({ liveApplyEnabled: true });
      await this.applySavedIdentity(currentItem, this.model.editorTransitionEpoch);
      return;
    }
    this.preview.toggle(scene);
  }

  public async applyCurrentDraft(): Promise<boolean> {
    const api = this.api;
    const device = this.model.selectedDevice;
    if (
      !api ||
      !device ||
      !this.model.isAdmin ||
      this.model.liveApplyEnabled ||
      this.model.stateUpdatesUnavailable ||
      this.model.applying ||
      this.model.saving ||
      !isEditableEffectContent(this.model.content)
    ) {
      return false;
    }
    const transitionEpoch = this.model.editorTransitionEpoch;
    const content = cloneEditableEffect(this.model.content);
    this.model.patch({ applying: true, notice: undefined });
    try {
      if (
        this.model.editorSource.kind === "saved" &&
        this.model.currentItem &&
        !this.model.dirty
      ) {
        await api.applySavedEffect(
          device.config_entry_id,
          this.model.currentItem,
        );
      } else {
        await api.applySnapshot(
          device.config_entry_id,
          this.model.name.trim() || "Effect Studio draft",
          content,
          this.model.editorSource.kind === "catalogue"
            ? {
                origin_kind: "catalogue_template",
                origin_id: this.model.editorSource.selectionIdentity,
              }
            : undefined,
        );
      }
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        await this.refreshSelectedDevice(transitionEpoch);
      }
      return true;
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.reportError(`Apply failed: ${errorMessage(error)}`, {
          title: "Apply failed",
          key: `apply:${transitionEpoch}:${errorCode(error)}`,
        });
      }
      return false;
    } finally {
      this.model.patch({ applying: false });
    }
  }

  public async selectItem(
    itemId: string,
    existingTransitionEpoch?: number,
    applyLive = true,
    reloadGuard?: LibraryReloadGuard,
  ): Promise<boolean> {
    if (existingTransitionEpoch === undefined) {
      let selected = false;
      await this.requestTransition(async () => {
        selected = await this.selectItem(itemId, this.editor.beginSelectionTransition(), applyLive, reloadGuard);
      });
      return selected;
    }
    const transitionEpoch =
      existingTransitionEpoch;
    if (!this.api) return false;
    try {
      const item = await this.api.item(itemId);
      if (
        transitionEpoch !== this.model.editorTransitionEpoch ||
        (reloadGuard !== undefined &&
          (this.model.saving ||
            this.model.currentItem?.id !== reloadGuard.itemId ||
            this.model.currentItem.version !== reloadGuard.version ||
            this.currentEditorDocument() !== reloadGuard.document)) ||
        !this.editor.applyLibraryItem(item)
      ) {
        return false;
      }
      if (applyLive && this.model.liveApplyEnabled) {
        await this.applySavedIdentity(item, transitionEpoch);
      }
      return transitionEpoch === this.model.editorTransitionEpoch;
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) this.model.patch({ notice: errorMessage(error) });
      return false;
    }
  }

  public async confirmDelete(): Promise<void> {
    const candidate = this.modal.deleteCandidate;
    if (
      !candidate ||
      !this.api ||
      !this.model.isAdmin ||
      this.model.stateUpdatesUnavailable ||
      this.model.deletingItemId !== undefined
    ) return;
    this.modal.takeDeleteCandidate();
    this.model.patch({ deletingItemId: candidate.id, notice: undefined });
    try {
      await this.api.deleteItem(candidate);
      this.model.patch({
        library: {
          ...this.model.library,
          items: this.model.library.items.filter(
            (item) => item.id !== candidate.id,
          ),
        },
      });
      if (this.model.currentItem?.id === candidate.id && this.model.currentItem.version === candidate.version) {
        this.editor.clearCurrentAfterDelete();
      }
      this.model.patch({ notice: undefined });
    } catch (error) {
      const conflict = errorCode(error) === "conflict";
      const message = conflict
        ? "This effect or library changed elsewhere. Reload before deleting."
        : `Delete failed: ${errorMessage(error)}`;
      let finalMessage = message;
      if (conflict) {
        try {
          this.model.patch({ library: await this.api.library() });
        } catch (refreshError) {
          finalMessage = `${message} Library refresh failed: ${errorMessage(refreshError)}`;
        }
      }
      this.model.patch({ notice: finalMessage });
    } finally {
      this.model.patch({ deletingItemId: undefined });
      this.modal.focusActiveSectionIfNeeded();
    }
  }

  public async save(): Promise<boolean> {
    if (this.model.builtInDefaultSource) {
      return this.saveBuiltInDefault();
    }
    if (
      !this.api || !this.model.isAdmin || !this.model.canSaveCurrentDraft || this.model.saving ||
      this.model.stateUpdatesUnavailable || this.model.deletingCurrentItem ||
      !isEditableEffectContent(this.model.content)
    ) return false;
    const name = this.model.name.trim();
    if (!name) {
      this.model.patch({ notice: "Give this effect a name before saving." });
      return false;
    }

    const transitionEpoch = this.model.editorTransitionEpoch;
    this.lastSaveCancelled = false;
    const originatingItem = this.model.currentItem;
    const content = cloneEditableEffect(this.model.content);
    const api = this.api;
    const selectedDeviceId = this.model.selectedDeviceId;
    const sourceDocument = serialiseEditable(name, content);
    const updatesGeneration = this.stateUpdatesGeneration;
    const guard = () =>
      api === this.api &&
      !this.model.stateUpdatesUnavailable &&
      updatesGeneration === this.stateUpdatesGeneration &&
      transitionEpoch === this.model.editorTransitionEpoch &&
      selectedDeviceId === this.model.selectedDeviceId &&
      sameLibraryItemVersion(this.model.currentItem, originatingItem) &&
      isEditableEffectContent(this.model.content) &&
      this.currentEditorDocument() === sourceDocument;
    const savingSceneEditor = this.model.sceneEditorOpen;
    this.model.patch({ saving: true, notice: undefined });
    try {
      const result = originatingItem
        ? await api.updateItem(originatingItem, name, content, guard)
        : await api.createItem(name, content, guard);
      if (!isEditableEffectContent(result.content)) {
        throw new Error("The saved effect returned an unsupported definition.");
      }
      const savedContent = result.content;
      this.model.patch({
        library: {
          ...this.model.library,
          items: upsertSummary(this.model.library.items, result),
        },
      });
      const originIsCurrent =
        transitionEpoch === this.model.editorTransitionEpoch &&
        sameLibraryItemVersion(this.model.currentItem, originatingItem) &&
        isEditableEffectContent(this.model.content) &&
        serialiseEditable(this.model.name, this.model.content) === serialiseEditable(name, content);
      if (originIsCurrent) {
        this.model.patch({
          currentItem: result,
          editorSource: {
            kind: "saved",
            owner:
              result.content.kind === "video_profile"
                ? { section: "video" }
                : {
                    section: "custom",
                    category: this.categoryForKind(result.content.kind),
                  },
            itemId: result.id,
          },
          name: result.name, content: cloneEditableEffect(savedContent),
          savedBaseline: serialiseEditable(result.name, savedContent),
          resetBaseline: cloneEditableEffect(savedContent),
          resetNameBaseline: undefined,
          sceneEditorOpen: savingSceneEditor && savedContent.kind === "scene_layered" ? false : this.model.sceneEditorOpen,
          section: savingSceneEditor && savedContent.kind === "scene_layered" ? "custom" : this.model.section,
          customEffectCategory: savingSceneEditor && savedContent.kind === "scene_layered"
            ? this.categoryForKind(result.content.kind)
            : this.model.customEffectCategory,
          savedSceneSelection: originatingItem && savedContent.kind === "scene_layered" ? result : this.model.savedSceneSelection,
          autoSaveFailed: false,
        });
        if (savingSceneEditor && savedContent.kind === "scene_layered") this.remember();
        if (
          this.model.liveApplyEnabled &&
          !(await this.applySavedIdentity(result, transitionEpoch))
        ) {
          return true;
        }
      }

      const savedResultIsCurrent =
        transitionEpoch === this.model.editorTransitionEpoch &&
        sameLibraryItemVersion(this.model.currentItem, result) &&
        isEditableEffectContent(this.model.content) &&
        serialiseEditable(this.model.name, this.model.content) === serialiseEditable(result.name, savedContent);
      if (savedResultIsCurrent) {
        this.model.patch({ notice: undefined });
        return true;
      }
      return false;
    } catch (error) {
      const code = errorCode(error);
      if (code === "save_cancelled") {
        this.lastSaveCancelled = true;
      } else if (code === "conflict") {
        const conflictNotice = "This effect or library changed elsewhere. Reload before saving.";
        if (transitionEpoch === this.model.editorTransitionEpoch) this.model.patch({ notice: conflictNotice });
        try {
          this.model.patch({ library: await this.api.library() });
        } catch (refreshError) {
          if (transitionEpoch === this.model.editorTransitionEpoch) {
            this.model.patch({ notice: `${conflictNotice} Library refresh failed: ${errorMessage(refreshError)}` });
          }
        }
      } else if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice:
            code === "reserved_name"
              ? errorMessage(error)
              : `Save failed: ${errorMessage(error)}`,
        });
      }
      return false;
    } finally {
      this.model.patch({ saving: false });
    }
  }

  private async saveBuiltInDefault(): Promise<boolean> {
    const api = this.api;
    const configEntryId = this.model.selectedDeviceId;
    const source = this.model.editorSource;
    if (
      !api ||
      !configEntryId ||
      !this.model.isAdmin ||
      this.model.stateUpdatesUnavailable ||
      this.model.saving ||
      this.model.applying ||
      !this.model.builtInDefaultDirty ||
      !isEditableEffectContent(this.model.content)
    ) {
      return false;
    }
    const transitionEpoch = this.model.editorTransitionEpoch;
    const content = cloneEditableEffect(this.model.content);
    this.model.patch({
      saving: true,
      autoSaveFailed: false,
      notice: undefined,
    });
    try {
      if (source.kind === "catalogue") {
        const detail = await api.setTemplateDefault(
          configEntryId,
          source.selectionIdentity,
          content as CatalogueTemplateContent,
        );
        if (
          transitionEpoch === this.model.editorTransitionEpoch &&
          this.model.editorSource.kind === "catalogue" &&
          this.model.editorSource.selectionIdentity === source.selectionIdentity &&
          isEditableEffectContent(detail.content) &&
          isEditableEffectContent(detail.catalogue_content)
        ) {
          this.model.patch({
            builtInBaselines: cloneBuiltInDefaultBaselines(
              detail.catalogue_content,
              detail.content,
              detail.has_default,
            ),
            resetBaseline: cloneEditableEffect(detail.catalogue_content),
            autoSaveFailed: false,
          });
        }
      } else if (
        source.kind === "scene" &&
        source.itemId === undefined &&
        content.kind === "scene_layered"
      ) {
        const detail = await api.setSceneDefault(configEntryId, content);
        if (
          transitionEpoch === this.model.editorTransitionEpoch &&
          this.model.editorSource.kind === "scene" &&
          this.model.editorSource.itemId === undefined &&
          isEditableEffectContent(detail.content) &&
          isEditableEffectContent(detail.catalogue_content)
        ) {
          this.model.patch({
            builtInBaselines: cloneBuiltInDefaultBaselines(
              detail.catalogue_content,
              detail.content,
              detail.has_default,
            ),
            resetBaseline: cloneEditableEffect(detail.catalogue_content),
            autoSaveFailed: false,
          });
        }
      } else {
        return false;
      }
      return true;
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          autoSaveFailed: true,
          notice: `Save failed: ${errorMessage(error)}`,
        });
      }
      return false;
    } finally {
      this.model.patch({ saving: false });
    }
  }

  public async saveAs(name: string): Promise<boolean> {
    if (
      !this.api ||
      !this.model.isAdmin ||
      this.model.stateUpdatesUnavailable ||
      this.model.saving ||
      this.model.deletingCurrentItem ||
      !isEditableEffectContent(this.model.content)
    ) {
      return false;
    }
    const content = cloneEditableEffect(this.model.content);
    this.lastSaveCancelled = false;
    const transitionEpoch = this.model.editorTransitionEpoch;
    const api = this.api;
    const sourceItemId = this.model.currentItem?.id;
    const sourceDocument = this.currentEditorDocument();
    const selectedDeviceId = this.model.selectedDeviceId;
    const updatesGeneration = this.stateUpdatesGeneration;
    const guard = () =>
      api === this.api &&
      !this.model.stateUpdatesUnavailable &&
      updatesGeneration === this.stateUpdatesGeneration &&
      transitionEpoch === this.model.editorTransitionEpoch &&
      this.model.currentItem?.id === sourceItemId &&
      this.model.selectedDeviceId === selectedDeviceId &&
      this.currentEditorDocument() === sourceDocument;
    this.cancelPendingAutoSave();
    this.model.patch({ saving: true, notice: undefined });
    try {
      const result = await api.createItem(name, content, guard);
      this.model.patch({
        library: {
          ...this.model.library,
          items: upsertSummary(this.model.library.items, result),
        },
      });
      if (
        transitionEpoch === this.model.editorTransitionEpoch &&
        this.model.currentItem?.id === sourceItemId &&
        this.model.selectedDeviceId === selectedDeviceId &&
        this.currentEditorDocument() === sourceDocument
      ) {
        this.editor.applyLibraryItem(result);
        this.model.patch({
          ...(result.content.kind === "video_profile"
            ? {}
            : {
                section: "custom" as const,
                customEffectCategory: this.categoryForKind(
                  result.content.kind,
                ),
              }),
          autoSaveFailed: false,
        });
        this.remember();
        if (
          this.model.liveApplyEnabled &&
          !(await this.applySavedIdentity(result, transitionEpoch))
        ) {
          return true;
        }
        return true;
      }
      return false;
    } catch (error) {
      const code = errorCode(error);
      if (code === "save_cancelled") {
        this.lastSaveCancelled = true;
      } else if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice:
            code === "reserved_name"
              ? errorMessage(error)
              : `Save As failed: ${errorMessage(error)}`,
        });
      }
      return false;
    } finally {
      this.model.patch({ saving: false });
    }
  }

  public async initialiseSelectedDevice(): Promise<string | undefined> {
    const userState = this.model.userState;
    const selectedDeviceId = initialDeviceId(this.options.pathname(), this.model.devices, userState?.selected_config_entry_id);
    this.model.update((model) => {
      model.selectedDeviceId = selectedDeviceId;
      model.notice = undefined;
    });
    if (!userState || !this.model.selectedDevice || selectedDeviceId === userState.selected_config_entry_id) return undefined;
    try {
      const updated = await this.api?.updateUserState(
        selectedDeviceId,
        {
          ...userState.navigation,
          auto_save: this.model.autoSaveEnabled,
        },
      );
      if (updated) this.model.patch({ userState: updated });
      return undefined;
    } catch (error) {
      console.warn("Could not remember the selected light", error);
      return undefined;
    }
  }

  private openRootCreateView(): void {
    this.editor.reset();
    const navigation = this.model.userState?.navigation ?? {};
    const remembered = navigation.custom_category;
    const customEffectCategory = restoredCustomEffectCategory(
      remembered,
      (category) => this.model.customEffectCategoryAvailable(category),
      this.model.defaultCustomEffectCategory(),
    );
    this.model.patch({
      section: rememberedStudioSection(navigation, {
        scenes: this.model.scenesAvailable,
        custom: this.model.customEffectsAvailable,
        video: this.model.videoAvailable,
      }),
      customEffectCategory,
      autoSaveEnabled: restoredAutoSave(navigation.auto_save),
      notice: undefined,
    });
  }

  private async rememberNavigation(): Promise<void> {
    if (
      !this.api ||
      !this.model.userState ||
      this.model.stateUpdatesUnavailable
    ) return;
    const updatesGeneration = this.stateUpdatesGeneration;
    try {
      const userState = await this.api.updateUserState(this.model.selectedDeviceId, {
        ...this.navigationPreferences,
      });
      if (
        !this.model.stateUpdatesUnavailable &&
        updatesGeneration === this.stateUpdatesGeneration
      ) {
        this.model.patch({ userState });
      }
    } catch (error) {
      console.warn("Could not remember Studio navigation", error);
    }
  }

  private async confirmOverwrite(effectName: string): Promise<boolean> {
    const generation = this.stateUpdatesGeneration;
    const confirmed = await this.modal.requestOverwrite(effectName);
    return (
      confirmed &&
      !this.model.stateUpdatesUnavailable &&
      generation === this.stateUpdatesGeneration
    );
  }

  private async drainAutoSave(): Promise<boolean> {
    if (this.model.stateUpdatesUnavailable) {
      this.autoSavePending = undefined;
      return false;
    }
    this.autoSaveRunning = true;
    this.model.patch({ autoSaveInProgress: true });
    let succeeded = true;
    try {
      while (this.autoSavePending) {
        if (this.model.stateUpdatesUnavailable) {
          this.autoSavePending = undefined;
          succeeded = false;
          break;
        }
        const target = this.autoSavePending;
        this.autoSavePending = undefined;
        if (!(await this.persistAutoSave(target))) {
          succeeded = false;
          break;
        }
      }
    } finally {
      this.autoSaveRunning = false;
      this.autoSaveDrain = undefined;
      this.model.patch({ autoSaveInProgress: false });
    }
    return succeeded;
  }

  private async persistAutoSave(target: AutoSaveTarget): Promise<boolean> {
    if (target.kind === "built-in") {
      return this.persistBuiltInAutoSave(target);
    }
    if (
      this.model.stateUpdatesUnavailable ||
      !this.api ||
      !target.name
    ) {
      return false;
    }
    const base = this.latestSavedItems.get(target.item.id) ?? target.item;
    this.model.patch({
      saving: true,
      autoSaveFailed: false,
      notice: undefined,
    });
    try {
      const api = this.api;
      const updatesGeneration = this.stateUpdatesGeneration;
      const sourceDocument = serialiseEditable(
        target.name,
        target.content,
      );
      const result = await api.updateItem(
        base,
        target.name,
        target.content,
        () =>
          api === this.api &&
          !this.model.stateUpdatesUnavailable &&
          updatesGeneration === this.stateUpdatesGeneration &&
          target.epoch === this.model.editorTransitionEpoch &&
          this.model.currentItem?.id === target.item.id &&
          isEditableEffectContent(this.model.content) &&
          this.currentEditorDocument() === sourceDocument,
      );
      if (!isEditableEffectContent(result.content)) {
        throw new Error("The saved effect returned an unsupported definition.");
      }
      const savedContent = result.content;
      this.latestSavedItems.set(result.id, result);
      this.model.patch({
        library: {
          ...this.model.library,
          items: upsertSummary(this.model.library.items, result),
        },
      });
      if (
        target.epoch === this.model.editorTransitionEpoch &&
        this.model.currentItem?.id === target.item.id
      ) {
        const savedBaseline = serialiseEditable(
          result.name,
          savedContent,
        );
        const currentMatchesSaved =
          isEditableEffectContent(this.model.content) &&
          serialiseEditable(this.model.name, this.model.content) ===
            serialiseEditable(target.name, target.content);
        if (currentMatchesSaved && result.id !== target.item.id) {
          this.editor.applyLibraryItem(result);
        } else {
          this.model.patch({
            currentItem: result,
            editorSource: {
              kind: "saved",
              owner:
                result.content.kind === "video_profile"
                  ? { section: "video" }
                  : {
                      section: "custom",
                      category: this.categoryForKind(result.content.kind),
                    },
              itemId: result.id,
            },
            savedBaseline,
          });
        }
        this.model.patch({ autoSaveFailed: false, notice: undefined });
        if (
          this.autoSavePending?.kind === "library" &&
          this.autoSavePending.item.id === target.item.id
        ) {
          this.autoSavePending = {
            ...this.autoSavePending,
            item: result,
          };
        }
        if (
          this.model.liveApplyEnabled &&
          isEditableEffectContent(this.model.content) &&
          serialiseEditable(this.model.name, this.model.content) ===
            savedBaseline
        ) {
          if (!(await this.applySavedIdentity(result, target.epoch))) {
            return true;
          }
        }
      }
      return true;
    } catch (error) {
      if (
        target.epoch === this.model.editorTransitionEpoch &&
        this.model.currentItem?.id === target.item.id
      ) {
        const code = errorCode(error);
        this.model.patch({
          autoSaveFailed: true,
          ...(code === "save_cancelled"
            ? {}
            : {
                notice:
                  code === "conflict"
                    ? "This effect changed elsewhere. Reload it before saving."
                    : `Save failed: ${errorMessage(error)}`,
              }),
        });
      }
      this.autoSavePending = undefined;
      return false;
    } finally {
      this.model.patch({ saving: false });
    }
  }

  private async persistBuiltInAutoSave(
    target: BuiltInAutoSaveTarget,
  ): Promise<boolean> {
    const api = this.api;
    if (!api || this.model.stateUpdatesUnavailable) {
      return false;
    }
    this.model.patch({
      saving: true,
      autoSaveFailed: false,
      notice: undefined,
    });
    try {
      const detail = target.templateId
        ? await api.setTemplateDefault(
            target.configEntryId,
            target.templateId,
            target.content as CatalogueTemplateContent,
          )
        : target.content.kind === "scene_layered"
          ? await api.setSceneDefault(target.configEntryId, target.content)
          : undefined;
      if (!detail) {
        return false;
      }
      if (
        target.epoch === this.model.editorTransitionEpoch &&
        target.configEntryId === this.model.selectedDeviceId &&
        isEditableEffectContent(detail.content) &&
        isEditableEffectContent(detail.catalogue_content)
      ) {
        this.model.patch({
          builtInBaselines: cloneBuiltInDefaultBaselines(
            detail.catalogue_content,
            detail.content,
            detail.has_default,
          ),
          resetBaseline: cloneEditableEffect(detail.catalogue_content),
          autoSaveFailed: false,
        });
      }
      return true;
    } catch (error) {
      if (target.epoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          autoSaveFailed: true,
          notice: `Save failed: ${errorMessage(error)}`,
        });
      }
      this.autoSavePending = undefined;
      return false;
    } finally {
      this.model.patch({ saving: false });
    }
  }

  private get navigationPreferences(): EffectUserState["navigation"] {
    return {
      section: this.model.section,
      custom_category: this.model.customEffectCategory,
      auto_save: this.model.autoSaveEnabled,
    };
  }

  private currentEditorDocument(): string {
    return isEditableEffectContent(this.model.content)
      ? serialiseEditable(this.model.name, this.model.content)
      : JSON.stringify({
          name: this.model.name,
          content: this.model.content,
        });
  }

  private categoryForKind(kind: string): CustomEffectCategory {
    const category = customEffectCategoryForKind(kind);
    return this.model.customEffectCategoryAvailable(category)
      ? category
      : this.model.defaultCustomEffectCategory();
  }

  private async applySavedIdentity(
    item: LibraryItem,
    transitionEpoch: number,
  ): Promise<boolean> {
    const device = this.model.selectedDevice;
    if (!this.api || !device) {
      return false;
    }
    const configEntryId = device.config_entry_id;
    if (!this.model.liveApplyEnabled) {
      return false;
    }
    try {
      await this.api.applySavedEffect(configEntryId, item);
      if (
        !this.model.liveApplyEnabled ||
        this.model.selectedDeviceId !== configEntryId ||
        transitionEpoch !== this.model.editorTransitionEpoch
      ) {
        return false;
      }
      await this.refreshSelectedDevice(transitionEpoch);
      return transitionEpoch === this.model.editorTransitionEpoch;
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice: `Apply failed: ${errorMessage(error)}`,
        });
      }
      return false;
    }
  }

  private async refreshSelectedDevice(
    transitionEpoch: number,
  ): Promise<DeviceCapabilities | undefined> {
    const api = this.api;
    const selectedDeviceId = this.model.selectedDeviceId;
    if (!api || !selectedDeviceId) {
      return undefined;
    }
    let refreshed: DeviceCapabilities;
    try {
      refreshed = await this.requestDeviceRefresh(api, selectedDeviceId);
    } catch (error) {
      if (transitionEpoch === this.model.editorTransitionEpoch) {
        this.model.patch({
          notice: `Refresh failed: ${errorMessage(error)}`,
        });
      }
      return undefined;
    }
    if (
      api !== this.api ||
      transitionEpoch !== this.model.editorTransitionEpoch ||
      selectedDeviceId !== this.model.selectedDeviceId
    ) {
      return undefined;
    }
    this.model.patch({
      devices: this.model.devices.map((device) =>
        device.config_entry_id === selectedDeviceId ? refreshed : device,
      ),
    });
    return refreshed;
  }

  private requestDeviceRefresh(
    api: EffectStudioApi,
    configEntryId: string,
  ): Promise<DeviceCapabilities> {
    const current = this.deviceRefresh;
    if (
      current?.api === api &&
      current.configEntryId === configEntryId
    ) {
      return current.promise;
    }
    const promise = api.device(configEntryId).finally(() => {
      if (this.deviceRefresh?.promise === promise) {
        this.deviceRefresh = undefined;
      }
    });
    this.deviceRefresh = { api, configEntryId, promise };
    return promise;
  }

  private loadIsCurrent(request: LoadRequest): boolean {
    return this.options.connected() && this.api !== undefined && this.loadRequests.isCurrent(request, { api: this.api });
  }

  private subscriptionFailed(error: Error, request: LoadRequest): void {
    if (!this.loadIsCurrent(request)) return;
    this.stateUpdatesFailed(error);
  }

  public stateUpdatesFailed(error: Error): void {
    this.stateUpdatesGeneration += 1;
    this.cancelPendingAutoSave();
    this.pendingTransition = undefined;
    this.model.patch({
      liveApplyEnabled: false,
      stateUpdatesUnavailable: true,
      previewStatus: undefined,
      previewNotice: undefined,
      previewProgressVisible: false,
    });
    this.modal.showError(
      `${error.message} Reload the page before making further changes.`,
      {
        title: "State updates stopped",
        key: `subscription:${error.message}`,
        resumeWorkflow: false,
      },
    );
    queueMicrotask(() => this.stopSubscriptions());
  }

  private async subscribeSelectedDevice(api: EffectStudioApi): Promise<void> {
    const configEntryId = this.model.selectedDeviceId;
    this.unsubscribeDevice?.();
    this.unsubscribeDevice = undefined;
    if (!configEntryId) {
      return;
    }
    const updatesGeneration = this.stateUpdatesGeneration;
    let unsubscribe: () => void;
    try {
      unsubscribe = await api.subscribeDevice(
        configEntryId,
        (device) => {
          if (
            api !== this.api ||
            this.model.stateUpdatesUnavailable ||
            device.config_entry_id !== this.model.selectedDeviceId
          ) {
            return;
          }
          this.model.patch({
            devices: this.model.devices.map((current) =>
              current.config_entry_id === device.config_entry_id
                ? device
                : current,
            ),
          });
        },
        (error) => {
          if (api === this.api) {
            this.stateUpdatesFailed(error);
          }
        },
      );
    } catch (error) {
      if (
        api === this.api &&
        configEntryId === this.model.selectedDeviceId
      ) {
        this.stateUpdatesFailed(
          error instanceof Error
            ? error
            : new Error("Device state subscription failed."),
        );
      }
      return;
    }
    if (
      api !== this.api ||
      this.model.stateUpdatesUnavailable ||
      updatesGeneration !== this.stateUpdatesGeneration ||
      configEntryId !== this.model.selectedDeviceId
    ) {
      unsubscribe();
      return;
    }
    this.unsubscribeDevice = unsubscribe;
  }

  private stopSubscriptions(): void {
    this.unsubscribeLibrary?.();
    this.unsubscribeLibrary = undefined;
    this.unsubscribeDevice?.();
    this.unsubscribeDevice = undefined;
    this.preview.dispose();
  }
}

export function isCustomEffectCategory(value: unknown): value is CustomEffectCategory {
  return value === "all" || value === "music" || value === "single-layer" || value === "multi-layer" ||
    value === "advanced" || value === "my-effects";
}

export function restoredCustomEffectCategory(
  remembered: unknown,
  available: (category: CustomEffectCategory) => boolean,
  fallback: CustomEffectCategory,
): CustomEffectCategory {
  if (remembered === "all") {
    return fallback;
  }
  return isCustomEffectCategory(remembered) && available(remembered)
    ? remembered
    : fallback;
}

export function restoredAutoSave(value: unknown): boolean {
  return value === true;
}
