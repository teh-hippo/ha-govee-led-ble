import { EffectStudioApi } from "./api";
import type { LivePreviewRequest } from "./live-preview-controller";
import type { ScenePreviewRequest } from "./scene-browser";
import type { EditorSource } from "./editor-state";
import type {
  EffectContent,
  PreviewSnapshotProvenance,
  PreviewStatus,
} from "./types";
import { errorCode } from "./ui-utils";

export type PanelPreviewRequest = LivePreviewRequest &
  (
    | {
        kind: "snapshot";
        configEntryId: string;
        name: string;
        content: EffectContent;
        provenance?: PreviewSnapshotProvenance;
      }
    | {
        kind: "scene";
        configEntryId: string;
        scene: ScenePreviewRequest & { kind: "scene" };
      }
  );

export function snapshotPreviewRequest(
  configEntryId: string,
  name: string,
  content: EffectContent,
  persistDefault = false,
  provenance?: PreviewSnapshotProvenance,
): PanelPreviewRequest {
  return {
    kind: "snapshot",
    configEntryId,
    name,
    content,
    ...(provenance ? { provenance } : {}),
    fingerprint: JSON.stringify({
      configEntryId,
      name,
      content,
      provenance,
      persistDefault,
    }),
    persistDefault,
  };
}

export function editorSnapshotProvenance(
  source: EditorSource,
): PreviewSnapshotProvenance | undefined {
  return source.kind === "catalogue"
    ? {
        origin_kind: "catalogue_template",
        origin_id: source.selectionIdentity,
      }
    : undefined;
}

export function scenePreviewRequest(
  request: ScenePreviewRequest,
  configEntryId: string,
): PanelPreviewRequest {
  if (request.kind !== "scene") {
    return snapshotPreviewRequest(
      configEntryId,
      request.name,
      request.content,
      request.persistDefault === true,
    );
  }
  return {
    kind: "scene",
    configEntryId,
    scene: request,
    fingerprint: JSON.stringify({
      configEntryId,
      sceneId: request.scene.scene_id,
      effectId: request.scene.effect_id,
      speedIndex: request.speedIndex,
      persistDefault: request.persistDefault === true,
    }),
    persistDefault: request.persistDefault,
  };
}

interface PreviewSubmission {
  request: PanelPreviewRequest;
  sequence: number;
}

function isConnectionLost(error: unknown): boolean {
  if (error === 3) {
    return true;
  }
  if (typeof error !== "object" || error === null) {
    return false;
  }
  if ("code" in error && error.code === 3) {
    return true;
  }
  return (
    "error" in error &&
    typeof error.error === "object" &&
    error.error !== null &&
    "code" in error.error &&
    error.error.code === 3
  );
}

export function createPreviewChannelId(
  randomUuid: (() => string) | null | undefined =
    typeof crypto.randomUUID === "function"
      ? crypto.randomUUID.bind(crypto)
      : undefined,
  randomValues: (
    values: Uint8Array<ArrayBuffer>,
  ) => Uint8Array<ArrayBuffer> = (values) =>
    crypto.getRandomValues(values),
): string {
  if (randomUuid) {
    return randomUuid();
  }
  const bytes = randomValues(new Uint8Array(new ArrayBuffer(16)));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10).join(""),
  ].join("-");
}

export class EffectStudioPreviewSession {
  private readonly sessionId = createPreviewChannelId();
  private readyState = false;
  private sequence = 0;
  private generation = 0;
  private latestStatusSequence = 0;
  private unsubscribe?: () => void;
  private unsubscribeConnectionReady?: () => void;
  private desired?: PreviewSubmission;
  private inFlight?: PreviewSubmission;
  private drainTask?: Promise<void>;
  private waitingForConnection = false;
  private connectionRevision = 0;

  public constructor(
    private readonly api: EffectStudioApi,
    private readonly statusChanged: (
      status: PreviewStatus | undefined,
    ) => void,
    private readonly subscriptionFailed: (error: Error) => void,
    private readonly requestFailed: (error: unknown) => void = () => undefined,
  ) {}

  public get ready(): boolean {
    return this.readyState;
  }

  public async open(): Promise<boolean> {
    const generation = this.generation;
    const unsubscribe = await this.api.subscribePreview(
      this.sessionId,
      (status) => this.acceptStatus(status),
      (error) => {
        if (this.readyState) {
          this.subscriptionFailed(error);
        }
      },
    );
    if (generation !== this.generation) {
      unsubscribe();
      await this.closeRemoteSession(this.sessionId);
      return false;
    }
    this.unsubscribe = unsubscribe;
    this.unsubscribeConnectionReady = this.api.onConnectionReady(() => {
      this.connectionRevision += 1;
      this.waitingForConnection = false;
      this.drain();
    });
    this.readyState = true;
    return true;
  }

  public submit(request: PanelPreviewRequest): void {
    if (!this.readyState) {
      return;
    }
    this.desired = {
      request,
      sequence: ++this.sequence,
    };
    this.drain();
  }

  public async cancel(configEntryId?: string): Promise<void> {
    this.generation += 1;
    this.desired = undefined;
    this.waitingForConnection = false;
    this.latestStatusSequence = this.sequence + 1;
    this.statusChanged(undefined);
    const sessionId = this.sessionId;
    if (sessionId) {
      await this.api.cancelPreview(sessionId, configEntryId);
    }
  }

  public transition(): void {
    this.generation += 1;
    this.desired = undefined;
    this.waitingForConnection = false;
    this.latestStatusSequence = Math.max(
      this.latestStatusSequence,
      this.sequence + 1,
    );
    this.statusChanged(undefined);
  }

  public close(): void {
    this.generation += 1;
    this.readyState = false;
    this.desired = undefined;
    this.waitingForConnection = false;
    this.statusChanged(undefined);
    this.unsubscribeConnectionReady?.();
    this.unsubscribeConnectionReady = undefined;
    this.unsubscribe?.();
    this.unsubscribe = undefined;
    void this.closeRemoteSession(this.sessionId);
  }

  private drain(): void {
    if (
      !this.readyState ||
      this.waitingForConnection ||
      this.drainTask ||
      !this.desired
    ) {
      return;
    }
    const generation = this.generation;
    const task = this.drainDesired(generation).finally(() => {
      if (this.drainTask === task) {
        this.drainTask = undefined;
        if (
          this.readyState &&
          !this.waitingForConnection &&
          this.desired
        ) {
          queueMicrotask(() => this.drain());
        }
      }
    });
    this.drainTask = task;
  }

  private async drainDesired(generation: number): Promise<void> {
    while (
      this.readyState &&
      !this.waitingForConnection &&
      generation === this.generation &&
      this.desired
    ) {
      const submission = this.desired;
      const connectionRevision = this.connectionRevision;
      this.inFlight = submission;
      try {
        await this.send(submission);
        if (this.desired === submission) {
          this.desired = undefined;
        }
      } catch (error) {
        if (generation !== this.generation) {
          return;
        }
        if (isConnectionLost(error)) {
          if (connectionRevision === this.connectionRevision) {
            this.waitingForConnection = true;
            return;
          }
          continue;
        }
        if (this.desired === submission) {
          this.desired = undefined;
        }
        this.requestFailed(error);
      } finally {
        if (this.inFlight === submission) {
          this.inFlight = undefined;
        }
      }
    }
  }

  private async send(submission: PreviewSubmission): Promise<void> {
    const { request, sequence } = submission;
    if (request.kind === "scene") {
      await this.api.previewScene(
        this.sessionId,
        sequence,
        request.configEntryId,
        request.scene.scene,
        request.scene.speedIndex,
        request.persistDefault,
      );
      return;
    }
    await this.api.previewSnapshot(
      this.sessionId,
      sequence,
      request.configEntryId,
      request.name,
      request.content,
      request.persistDefault,
      request.provenance,
    );
  }

  private acceptStatus(status: PreviewStatus): void {
    if (
      status.session_id !== this.sessionId ||
      status.sequence < this.latestStatusSequence
    ) {
      return;
    }
    this.latestStatusSequence = status.sequence;
    this.statusChanged(status);
  }

  private async closeRemoteSession(sessionId: string): Promise<void> {
    try {
      await this.api.closePreviewSession(sessionId);
    } catch (error) {
      if (errorCode(error) !== "preview_session_not_found") {
        console.warn("Could not close Effect Studio preview session", error);
      }
    }
  }
}
