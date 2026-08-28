import { EffectStudioApi } from "./api";
import { cloneBuiltInDefaultBaselines } from "./built-in-default-state";
import {
  LivePreviewProgressController,
  type LivePreviewInteraction,
} from "./live-preview-controller";
import { PanelModel } from "./panel-model";
import {
  editorSnapshotProvenance,
  EffectStudioPreviewSession,
  scenePreviewRequest,
  snapshotPreviewRequest,
  type PanelPreviewRequest,
} from "./panel-preview";
import type { ScenePreviewRequest } from "./scene-browser";
import {
  cloneEditableEffect,
  isEditableEffectContent,
} from "./effect-editor-model";
import { errorCode, errorMessage } from "./ui-utils";
import type {
  CatalogueTemplateDefaultDetail,
  PreviewStatus,
  SceneDetail,
} from "./types";

export function previewStatusMessage(
  status: PreviewStatus | undefined,
): string | undefined {
  if (
    status === undefined ||
    (status.phase !== "failed" && status.phase !== "unconfirmed")
  ) {
    return undefined;
  }
  if (status.error_message) {
    return status.error_message;
  }
  switch (status.error_code) {
    case "transport_failed":
      return "Live apply could not reach the light. Turn Live off and on to try again.";
    case "compilation_failed":
      return "Live apply could not prepare this effect.";
    case "storage_failed":
      return "The light changed, but its scene default could not be saved.";
    case "device_state_mismatch":
      return "The light accepted the write, but its reported state did not match the requested change.";
    case "device_readback_unknown":
      return "The light accepted the write, but did not provide state readback to confirm it.";
    default:
      return "Effect Studio could not confirm whether the Live change completed.";
  }
}

export class PanelPreviewController {
  private api?: EffectStudioApi;
  private session?: EffectStudioPreviewSession;
  private rejectedRequestSequence = 0;
  private readonly refreshedDefaultSequences = new Set<string>();
  private readonly reportedPreviewErrors = new Set<string>();
  private readonly progress = new LivePreviewProgressController({
    changed: (visible) => {
      this.model.patch({ previewProgressVisible: visible });
    },
  });
  public constructor(private readonly model: PanelModel) {}

  public async open(
    api: EffectStudioApi,
    subscriptionFailed: (error: Error) => void,
  ): Promise<boolean> {
    this.api = api;
    this.reportedPreviewErrors.clear();
    this.refreshedDefaultSequences.clear();
    const session = new EffectStudioPreviewSession(
      api,
      (status) => {
        if (
          status !== undefined &&
          status.config_entry_id !== this.model.selectedDeviceId
        ) {
          return;
        }
        if (status) {
          this.progress.accept(status);
        } else {
          this.progress.clear();
        }
        this.model.update((model) => {
          model.previewStatus = status;
          model.previewNotice = undefined;
        });
        this.updateBuiltInDefaultStatus(status);
        const message = previewStatusMessage(status);
        if (message && status) {
          const key = `preview:${status.session_id}:${status.sequence}:${status.phase}:${status.error_code ?? ""}`;
          if (!this.reportedPreviewErrors.has(key)) {
            this.reportedPreviewErrors.add(key);
            this.model.reportError(message, {
              title: "Live change failed",
              key,
            });
          }
        }
      },
      subscriptionFailed,
      (error) => {
        this.progress.clear();
        this.model.patch({
          previewStatus: undefined,
          previewNotice: undefined,
          previewProgressVisible: false,
        });
        this.rejectedRequestSequence += 1;
        this.model.reportError(
          `Live request was not accepted: ${errorMessage(error)}`,
          {
            title: "Live request failed",
            key: `preview-rejected:${this.rejectedRequestSequence}`,
          },
        );
      },
    );
    this.session = session;
    this.progress.reset();
    const opened = await session.open();
    if (!opened || this.session !== session) {
      session.close();
      if (this.session === session) {
        this.api = undefined;
      }
      return false;
    }
    return true;
  }

  public beginEditorTransition(cancelBackend = true): number {
    const editorTransitionEpoch = this.model.editorTransitionEpoch + 1;
    if (cancelBackend) {
      void this.cancel();
    } else {
      this.session?.transition();
    }
    this.progress.clear();
    this.refreshedDefaultSequences.clear();
    this.model.patch({
      editorTransitionEpoch,
      previewStatus: undefined,
      previewNotice: undefined,
      previewProgressVisible: false,
    });
    return editorTransitionEpoch;
  }

  public scheduleEdited(
    _interaction: LivePreviewInteraction = "committed",
    scene?: ScenePreviewRequest,
  ): void {
    const request = this.currentRequest(scene);
    if (request) {
      this.submit(request);
    }
  }

  public scheduleTemplateSelection(): void {
    const request = this.currentRequest();
    if (request) {
      this.submit(request);
    }
  }

  public scheduleScene(request: ScenePreviewRequest): void {
    const deviceId = this.model.selectedDeviceId;
    if (!this.model.liveApplyEnabled || !deviceId) {
      return;
    }
    this.submit(scenePreviewRequest(request, deviceId));
  }

  public toggle(scene?: ScenePreviewRequest): void {
    if (this.model.liveApplyEnabled) {
      this.model.update((model) => {
        model.liveApplyEnabled = false;
        model.previewStatus = undefined;
        model.previewNotice = undefined;
        model.previewProgressVisible = false;
      });
      this.progress.clear();
      void this.cancel();
      return;
    }
    this.model.update((model) => {
      model.liveApplyEnabled = true;
    });
    const request = this.currentRequest(scene);
    if (request) {
      this.submit(request);
    }
  }

  public async cancel(
    configEntryId = this.model.selectedDeviceId,
  ): Promise<void> {
    const session = this.session;
    if (!session) {
      return;
    }
    try {
      await session.cancel(configEntryId);
    } catch (error) {
      if (errorCode(error) !== "preview_session_not_found") {
        this.model.update((model) => {
          model.notice = `Could not cancel Live: ${errorMessage(error)}`;
        });
      }
    }
  }

  public dispose(): void {
    this.progress.reset();
    this.session?.close();
    this.session = undefined;
    this.api = undefined;
    this.reportedPreviewErrors.clear();
    this.refreshedDefaultSequences.clear();
    this.model.update((model) => {
      model.previewStatus = undefined;
      model.previewNotice = undefined;
      model.previewProgressVisible = false;
    });
  }

  private submit(request: PanelPreviewRequest): void {
    if (
      this.model.liveApplyEnabled &&
      request.configEntryId === this.model.selectedDeviceId
    ) {
      this.session?.submit(request);
    }
  }

  private currentRequest(
    scene?: ScenePreviewRequest,
  ): PanelPreviewRequest | undefined {
    if (!this.model.liveApplyEnabled || !this.model.selectedDeviceId) {
      return undefined;
    }
    if (this.model.section === "scenes" && !this.model.sceneEditorOpen) {
      return scene
        ? scenePreviewRequest(scene, this.model.selectedDeviceId)
        : undefined;
    }
    if (
      !this.canPreview ||
      !this.model.editorOwnedByActiveView ||
      !isEditableEffectContent(this.model.content)
    ) {
      return undefined;
    }
    return snapshotPreviewRequest(
      this.model.selectedDeviceId,
      this.model.name.trim() || "Live preview",
      this.model.content,
      this.model.autoSaveEnabled && this.model.builtInDefaultDirty,
      editorSnapshotProvenance(this.model.editorSource),
    );
  }

  private updateBuiltInDefaultStatus(status: PreviewStatus | undefined): void {
    if (
      !status?.persist_default ||
      !this.model.builtInDefaultSource ||
      !isEditableEffectContent(this.model.content)
    ) {
      return;
    }
    if (status.phase === "failed") {
      this.model.patch({ autoSaveFailed: true });
      return;
    }
    if (status.phase !== "written") {
      return;
    }
    const key = `${status.session_id}:${status.sequence}`;
    if (this.refreshedDefaultSequences.has(key)) {
      return;
    }
    this.refreshedDefaultSequences.add(key);
    void this.refreshBuiltInDefault(key);
  }

  private async refreshBuiltInDefault(key: string): Promise<void> {
    const api = this.api;
    const configEntryId = this.model.selectedDeviceId;
    const transitionEpoch = this.model.editorTransitionEpoch;
    const source = this.model.editorSource;
    const content = isEditableEffectContent(this.model.content)
      ? cloneEditableEffect(this.model.content)
      : undefined;
    if (!api || !configEntryId || !content) {
      return;
    }
    try {
      const detail =
        source.kind === "catalogue"
          ? await api.templateDefault(
              configEntryId,
              source.selectionIdentity,
            )
          : source.kind === "scene" &&
              source.itemId === undefined &&
              content.kind === "scene_layered"
            ? await api.sceneDetail(
                configEntryId,
                content.template.scene_id,
                content.template.effect_id,
              )
            : undefined;
      if (
        !detail ||
        api !== this.api ||
        configEntryId !== this.model.selectedDeviceId ||
        transitionEpoch !== this.model.editorTransitionEpoch ||
        !this.sameBuiltInSource(source) ||
        !isEditableEffectContent(detail.content) ||
        !isEditableEffectContent(detail.catalogue_content)
      ) {
        return;
      }
      this.installBuiltInDefaultDetail(detail);
    } catch (error) {
      if (
        api === this.api &&
        configEntryId === this.model.selectedDeviceId &&
        transitionEpoch === this.model.editorTransitionEpoch &&
        this.sameBuiltInSource(source)
      ) {
        this.model.patch({
          autoSaveFailed: true,
          notice: `The default was saved, but its state could not be refreshed: ${errorMessage(error)}`,
        });
      }
    } finally {
      this.refreshedDefaultSequences.delete(key);
    }
  }

  private sameBuiltInSource(source: PanelModel["editorSource"]): boolean {
    const current = this.model.editorSource;
    return (
      (source.kind === "catalogue" &&
        current.kind === "catalogue" &&
        current.selectionIdentity === source.selectionIdentity) ||
      (source.kind === "scene" &&
        source.itemId === undefined &&
        current.kind === "scene" &&
        current.itemId === undefined)
    );
  }

  private installBuiltInDefaultDetail(
    detail: CatalogueTemplateDefaultDetail | SceneDetail,
  ): void {
    if (
      !isEditableEffectContent(detail.content) ||
      !isEditableEffectContent(detail.catalogue_content)
    ) {
      return;
    }
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

  private get canPreview(): boolean {
    return (
      isEditableEffectContent(this.model.content) &&
      this.model.isAdmin &&
      !this.model.deletingCurrentItem &&
      this.model.previewCapability === "supported" &&
      this.model.selectedDevice !== undefined &&
      this.session?.ready === true
    );
  }
}
