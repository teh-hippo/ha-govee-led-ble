export const REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS = 50;

const REACTIVE_START = "ha_govee_led_ble/reactive/start";
const REACTIVE_UPDATE = "ha_govee_led_ble/reactive/update";
const REACTIVE_STOP = "ha_govee_led_ble/reactive/stop";

export interface ReactiveRgb {
  r: number;
  g: number;
  b: number;
}

export interface ReactiveRgbStatus {
  phase: "idle" | "starting" | "active" | "error";
  message: string;
}

interface ReactiveBackendStatus {
  session_id?: unknown;
  state?: unknown;
  stop_reason?: unknown;
}

interface VisibilityDocument {
  readonly hidden: boolean;
  addEventListener(type: "visibilitychange", listener: EventListener): void;
  removeEventListener(type: "visibilitychange", listener: EventListener): void;
}

interface ReactiveRgbControllerOptions {
  callWS: (message: Record<string, unknown>) => Promise<unknown>;
  configEntryId: () => string;
  legacyColourOrder?: () => boolean;
  statusChanged?: (status: ReactiveRgbStatus) => void;
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  createAudioContext?: () => AudioContext;
  visibilityDocument?: VisibilityDocument;
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (frame: number) => void;
  setTimer?: (callback: () => void, delay: number) => number;
  clearTimer?: (timer: number) => void;
  now?: () => number;
}

interface ReactiveSession {
  configEntryId: string;
  sessionId: string;
}

export function deriveReactiveRgb(data: ArrayLike<number>): ReactiveRgb {
  const sums = [0, 0, 0];
  const counts = [0, 0, 0];
  for (let index = 0; index < data.length; index += 1) {
    const band = Math.min(2, Math.floor((index * 3) / data.length));
    const value = data[index] ?? 0;
    sums[band] += Number.isFinite(value)
      ? Math.min(255, Math.max(0, value))
      : 0;
    counts[band] += 1;
  }
  return {
    r: counts[0] === 0 ? 0 : Math.round(sums[0] / counts[0]),
    g: counts[1] === 0 ? 0 : Math.round(sums[1] / counts[1]),
    b: counts[2] === 0 ? 0 : Math.round(sums[2] / counts[2]),
  };
}

export class ReactiveRgbController {
  private readonly callWS: ReactiveRgbControllerOptions["callWS"];
  private readonly configEntryId: ReactiveRgbControllerOptions["configEntryId"];
  private readonly legacyColourOrder: () => boolean;
  private readonly statusChanged: (status: ReactiveRgbStatus) => void;
  private readonly mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  private readonly createAudioContext: () => AudioContext;
  private readonly visibilityDocument: VisibilityDocument;
  private readonly requestFrame: (callback: FrameRequestCallback) => number;
  private readonly cancelFrame: (frame: number) => void;
  private readonly setTimer: (callback: () => void, delay: number) => number;
  private readonly clearTimer: (timer: number) => void;
  private readonly now: () => number;

  private generation = 0;
  private session?: ReactiveSession;
  private stream?: MediaStream;
  private audioContext?: AudioContext;
  private source?: MediaStreamAudioSourceNode;
  private analyser?: AnalyserNode;
  private frequencyData?: Uint8Array<ArrayBuffer>;
  private frame?: number;
  private timer?: number;
  private pendingRgb?: ReactiveRgb;
  private updateInFlight = false;
  private lastSentAt = Number.NEGATIVE_INFINITY;
  private listeningForVisibility = false;
  private currentStatus: ReactiveRgbStatus = {
    phase: "idle",
    message: "Microphone reactive colour is stopped.",
  };

  public constructor(options: ReactiveRgbControllerOptions) {
    this.callWS = options.callWS;
    this.configEntryId = options.configEntryId;
    this.legacyColourOrder = options.legacyColourOrder ?? (() => false);
    this.statusChanged = options.statusChanged ?? (() => undefined);
    this.mediaDevices = options.mediaDevices ?? navigator.mediaDevices;
    this.createAudioContext =
      options.createAudioContext ?? (() => new AudioContext());
    this.visibilityDocument = options.visibilityDocument ?? document;
    this.requestFrame =
      options.requestFrame ?? ((callback) => requestAnimationFrame(callback));
    this.cancelFrame =
      options.cancelFrame ?? ((frame) => cancelAnimationFrame(frame));
    this.setTimer =
      options.setTimer ??
      ((callback, delay) => window.setTimeout(callback, delay));
    this.clearTimer =
      options.clearTimer ?? ((timer) => window.clearTimeout(timer));
    this.now = options.now ?? (() => performance.now());
  }

  public get status(): ReactiveRgbStatus {
    return this.currentStatus;
  }

  public get running(): boolean {
    return (
      this.currentStatus.phase === "starting" ||
      this.currentStatus.phase === "active"
    );
  }

  public async start(): Promise<void> {
    if (this.running) {
      return;
    }
    const configEntryId = this.configEntryId().trim();
    if (!configEntryId) {
      this.publish("error", "Select a light before starting reactive colour.");
      return;
    }
    if (this.visibilityDocument.hidden) {
      this.publish("error", "Open this page before starting reactive colour.");
      return;
    }
    if (!this.mediaDevices?.getUserMedia) {
      this.publish(
        "error",
        "Microphone access is unavailable in this browser.",
      );
      return;
    }

    const generation = ++this.generation;
    this.listenForVisibility();
    this.publish("starting", "Requesting microphone access…");
    let acquiredStream: MediaStream | undefined;
    try {
      const context = this.createAudioContext();
      this.audioContext = context;
      acquiredStream = await this.mediaDevices.getUserMedia({ audio: true });
      if (!this.isCurrent(generation)) {
        this.releaseStream(acquiredStream);
        return;
      }

      this.stream = acquiredStream;
      for (const track of acquiredStream.getTracks()) {
        track.addEventListener("ended", this.trackEnded);
      }
      this.source = context.createMediaStreamSource(acquiredStream);
      this.analyser = context.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.5;
      this.source.connect(this.analyser);
      this.frequencyData = new Uint8Array(this.analyser.frequencyBinCount);
      if (context.state === "suspended") {
        await context.resume();
      }
      if (!this.isCurrent(generation)) {
        return;
      }

      const startMessage: Record<string, unknown> = {
        type: REACTIVE_START,
        config_entry_id: configEntryId,
      };
      if (this.legacyColourOrder()) {
        startMessage.legacy_colour_order = true;
      }
      const response = await this.callWS(startMessage);
      const sessionId = activeSessionId(response);
      if (!this.isCurrent(generation)) {
        if (sessionId) {
          void this.stopRemote({ configEntryId, sessionId }).catch(
            () => undefined,
          );
        }
        return;
      }
      if (!sessionId) {
        throw {
          code: "reactive_invalid_session",
          message: "The backend did not start a reactive session.",
        };
      }

      this.session = { configEntryId, sessionId };
      this.lastSentAt = this.now() - REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS;
      this.publish("active", "Microphone reactive colour is active.");
      this.frame = this.requestFrame(this.sampleFrame);
    } catch (error) {
      if (!this.isCurrent(generation)) {
        return;
      }
      this.generation += 1;
      this.cleanupLocal();
      this.publish("error", reactiveErrorMessage(error, "start"));
    }
  }

  public async stop(
    message = "Microphone reactive colour is stopped.",
  ): Promise<void> {
    await this.shutdown(
      { phase: "idle", message },
      true,
    );
  }

  public disconnect(): void {
    void this.shutdown(
      {
        phase: "idle",
        message: "Microphone reactive colour stopped when the panel closed.",
      },
      false,
    );
  }

  private readonly sampleFrame: FrameRequestCallback = () => {
    this.frame = undefined;
    if (!this.session || !this.analyser || !this.frequencyData) {
      return;
    }
    try {
      this.analyser.getByteFrequencyData(this.frequencyData);
      this.pendingRgb = deriveReactiveRgb(this.frequencyData);
    } catch (error) {
      void this.shutdown(
        {
          phase: "error",
          message: reactiveErrorMessage(error, "update"),
        },
        false,
      );
      return;
    }
    this.scheduleFlush();
    this.frame = this.requestFrame(this.sampleFrame);
  };

  private scheduleFlush(): void {
    if (
      this.timer !== undefined ||
      this.updateInFlight ||
      !this.pendingRgb ||
      !this.session
    ) {
      return;
    }
    const delay = Math.max(
      0,
      this.lastSentAt +
        REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS -
        this.now(),
    );
    this.timer = this.setTimer(() => {
      this.timer = undefined;
      this.flushLatest();
    }, delay);
  }

  private flushLatest(): void {
    const session = this.session;
    if (!session || !this.pendingRgb || this.updateInFlight) {
      return;
    }
    const remaining =
      this.lastSentAt +
      REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS -
      this.now();
    if (remaining > 0) {
      this.timer = this.setTimer(() => {
        this.timer = undefined;
        this.flushLatest();
      }, remaining);
      return;
    }

    const generation = this.generation;
    const rgb = this.pendingRgb;
    this.pendingRgb = undefined;
    this.updateInFlight = true;
    this.lastSentAt = this.now();
    void this.callWS({
      type: REACTIVE_UPDATE,
      config_entry_id: session.configEntryId,
      session_id: session.sessionId,
      rgb: { r: rgb.r, g: rgb.g, b: rgb.b },
    }).then(
      (response) => this.updateCompleted(generation, session, response),
      (error) => this.updateFailed(generation, session, error),
    );
  }

  private updateCompleted(
    generation: number,
    session: ReactiveSession,
    response: unknown,
  ): void {
    if (!this.isCurrentSession(generation, session)) {
      return;
    }
    this.updateInFlight = false;
    const status = backendStatus(response);
    if (
      status.state !== "active" ||
      status.session_id !== session.sessionId
    ) {
      void this.shutdown(
        {
          phase: "error",
          message: backendStopMessage(status.stop_reason),
        },
        false,
      );
      return;
    }
    this.scheduleFlush();
  }

  private updateFailed(
    generation: number,
    session: ReactiveSession,
    error: unknown,
  ): void {
    if (!this.isCurrentSession(generation, session)) {
      return;
    }
    this.updateInFlight = false;
    void this.shutdown(
      {
        phase: "error",
        message: reactiveErrorMessage(error, "update"),
      },
      false,
    );
  }

  private async shutdown(
    status: ReactiveRgbStatus,
    surfaceStopError: boolean,
  ): Promise<void> {
    const shutdownGeneration = ++this.generation;
    const session = this.session;
    this.session = undefined;
    this.cleanupLocal();
    this.publish(status.phase, status.message);
    if (!session) {
      return;
    }
    try {
      await this.stopRemote(session);
    } catch (error) {
      if (
        surfaceStopError &&
        this.generation === shutdownGeneration &&
        !this.session
      ) {
        this.publish("error", reactiveErrorMessage(error, "stop"));
      }
    }
  }

  private stopRemote(session: ReactiveSession): Promise<unknown> {
    return this.callWS({
      type: REACTIVE_STOP,
      config_entry_id: session.configEntryId,
      session_id: session.sessionId,
    });
  }

  private cleanupLocal(): void {
    if (this.frame !== undefined) {
      this.cancelFrame(this.frame);
      this.frame = undefined;
    }
    if (this.timer !== undefined) {
      this.clearTimer(this.timer);
      this.timer = undefined;
    }
    this.pendingRgb = undefined;
    this.updateInFlight = false;
    this.lastSentAt = Number.NEGATIVE_INFINITY;
    this.stopListeningForVisibility();

    const stream = this.stream;
    this.stream = undefined;
    if (stream) {
      for (const track of stream.getTracks()) {
        track.removeEventListener("ended", this.trackEnded);
      }
      this.releaseStream(stream);
    }
    disconnectNode(this.source);
    disconnectNode(this.analyser);
    this.source = undefined;
    this.analyser = undefined;
    this.frequencyData = undefined;

    const context = this.audioContext;
    this.audioContext = undefined;
    if (context && context.state !== "closed") {
      void context.close().catch(() => undefined);
    }
  }

  private releaseStream(stream: MediaStream): void {
    for (const track of stream.getTracks()) {
      track.stop();
    }
  }

  private listenForVisibility(): void {
    if (this.listeningForVisibility) {
      return;
    }
    this.visibilityDocument.addEventListener(
      "visibilitychange",
      this.visibilityChanged,
    );
    this.listeningForVisibility = true;
  }

  private stopListeningForVisibility(): void {
    if (!this.listeningForVisibility) {
      return;
    }
    this.visibilityDocument.removeEventListener(
      "visibilitychange",
      this.visibilityChanged,
    );
    this.listeningForVisibility = false;
  }

  private readonly visibilityChanged: EventListener = () => {
    if (this.visibilityDocument.hidden) {
      void this.shutdown(
        {
          phase: "idle",
          message: "Microphone reactive colour stopped while the page is hidden.",
        },
        false,
      );
    }
  };

  private readonly trackEnded: EventListener = () => {
    void this.shutdown(
      {
        phase: "error",
        message: "Microphone input ended. Start reactive colour again.",
      },
      false,
    );
  };

  private isCurrent(generation: number): boolean {
    return this.generation === generation;
  }

  private isCurrentSession(
    generation: number,
    session: ReactiveSession,
  ): boolean {
    return (
      this.generation === generation &&
      this.session?.sessionId === session.sessionId &&
      this.session.configEntryId === session.configEntryId
    );
  }

  private publish(
    phase: ReactiveRgbStatus["phase"],
    message: string,
  ): void {
    this.currentStatus = { phase, message };
    this.statusChanged(this.currentStatus);
  }
}

function activeSessionId(value: unknown): string | undefined {
  const status = backendStatus(value);
  return (
    status.state === "active" &&
    typeof status.session_id === "string" &&
    status.session_id.length > 0
  )
    ? status.session_id
    : undefined;
}

function backendStatus(value: unknown): ReactiveBackendStatus {
  return typeof value === "object" && value !== null
    ? value as ReactiveBackendStatus
    : {};
}

function disconnectNode(node: AudioNode | undefined): void {
  try {
    node?.disconnect();
  } catch {
    return;
  }
}

function errorCode(error: unknown): string | undefined {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
  ) {
    return error.code;
  }
  return undefined;
}

function reactiveErrorMessage(
  error: unknown,
  action: "start" | "update" | "stop",
): string {
  if (error instanceof Error) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Microphone permission was denied.";
    }
    if (error.name === "NotFoundError") {
      return "No microphone is available.";
    }
    if (error.name === "NotReadableError") {
      return "The microphone is unavailable or already in use.";
    }
  }
  const messages: Record<string, string> = {
    reactive_invalid_payload: "Home Assistant rejected the derived colour.",
    reactive_unknown_firmware:
      "This light's firmware is not recognised for reactive colour.",
    reactive_target_unsupported:
      "Reactive colour is only available for supported H6179 lights.",
    reactive_target_unavailable: "The light is unavailable.",
    reactive_session_active:
      "Reactive colour is already active for this light.",
    reactive_session_not_found:
      "The reactive colour session ended. Start it again.",
    reactive_session_unauthorized:
      "You do not have access to this reactive colour session.",
    reactive_session_expired:
      "The reactive colour session expired. Start it again.",
    reactive_session_superseded:
      "Reactive colour stopped because another light command took control.",
    reactive_write_failed:
      "The light could not accept reactive colour updates.",
    reactive_shutting_down: "Home Assistant is shutting down.",
    reactive_invalid_session:
      "The reactive colour session is invalid. Start it again.",
  };
  const code = errorCode(error);
  if (code && messages[code]) {
    return messages[code];
  }
  if (action === "start") {
    return "Could not start microphone reactive colour.";
  }
  if (action === "stop") {
    return "Reactive colour stopped locally, but Home Assistant could not be reached.";
  }
  return "Reactive colour stopped because the connection or update failed.";
}

function backendStopMessage(reason: unknown): string {
  if (reason === "superseded") {
    return "Reactive colour stopped because another light command took control.";
  }
  if (reason === "timeout") {
    return "The reactive colour session expired. Start it again.";
  }
  if (reason === "write_failed") {
    return "The light could not accept reactive colour updates.";
  }
  if (reason === "disconnected" || reason === "unloaded") {
    return "Reactive colour stopped because the light became unavailable.";
  }
  return "The reactive colour session ended. Start it again.";
}
