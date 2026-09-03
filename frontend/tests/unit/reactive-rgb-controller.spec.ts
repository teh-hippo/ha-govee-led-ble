import { expect, test, vi } from "vitest";

import {
  deriveReactiveRgb,
  REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS,
  ReactiveRgbController,
  type ReactiveRgbStatus,
} from "../../src/reactive-rgb-controller";

const SESSION_ID = "00000000-0000-4000-8000-000000000001";

class TestTrack extends EventTarget {
  public readonly stop = vi.fn();

  public end(): void {
    this.dispatchEvent(new Event("ended"));
  }
}

class TestDocument extends EventTarget {
  public hidden = false;

  public hide(): void {
    this.hidden = true;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}

class TestScheduler {
  public now = 0;
  private nextId = 1;
  private readonly frames = new Map<number, FrameRequestCallback>();
  private readonly timers = new Map<
    number,
    { callback: () => void; due: number }
  >();

  public requestFrame = (callback: FrameRequestCallback): number => {
    const id = this.nextId++;
    this.frames.set(id, callback);
    return id;
  };

  public cancelFrame = (id: number): void => {
    this.frames.delete(id);
  };

  public setTimer = (callback: () => void, delay: number): number => {
    const id = this.nextId++;
    this.timers.set(id, {
      callback,
      due: this.now + delay,
    });
    return id;
  };

  public clearTimer = (id: number): void => {
    this.timers.delete(id);
  };

  public runFrame(): void {
    const pending = [...this.frames.values()];
    this.frames.clear();
    for (const callback of pending) {
      callback(this.now);
    }
  }

  public advance(milliseconds: number): void {
    this.now += milliseconds;
    this.runDueTimers();
  }

  public runDueTimers(): void {
    while (true) {
      const due = [...this.timers.entries()]
        .filter(([, timer]) => timer.due <= this.now)
        .sort((left, right) => left[1].due - right[1].due)[0];
      if (!due) {
        return;
      }
      this.timers.delete(due[0]);
      due[1].callback();
    }
  }

  public get frameCount(): number {
    return this.frames.size;
  }

  public get timerCount(): number {
    return this.timers.size;
  }
}

function createAudioRig(initialValues = [10, 20, 30, 40, 50, 60]) {
  const track = new TestTrack();
  const stream = {
    getTracks: () => [track],
  } as unknown as MediaStream;
  const source = {
    connect: vi.fn(),
    disconnect: vi.fn(),
  };
  let values = initialValues;
  const analyser = {
    fftSize: 0,
    smoothingTimeConstant: 0,
    frequencyBinCount: initialValues.length,
    connect: vi.fn(),
    disconnect: vi.fn(),
    getByteFrequencyData: vi.fn((target: Uint8Array) => {
      target.set(values);
    }),
  };
  const context = {
    state: "running",
    createMediaStreamSource: vi.fn(() => source),
    createAnalyser: vi.fn(() => analyser),
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
  } as unknown as AudioContext;
  return {
    analyser,
    context,
    source,
    stream,
    track,
    setValues(next: number[]) {
      values = next;
    },
  };
}

function createController(
  callWS: (message: Record<string, unknown>) => Promise<unknown>,
  options: {
    getUserMedia?: () => Promise<MediaStream>;
    legacyColourOrder?: boolean;
  } = {},
) {
  const rig = createAudioRig();
  const scheduler = new TestScheduler();
  const visibilityDocument = new TestDocument();
  const statuses: ReactiveRgbStatus[] = [];
  const getUserMedia =
    options.getUserMedia ?? vi.fn().mockResolvedValue(rig.stream);
  const controller = new ReactiveRgbController({
    callWS,
    configEntryId: () => "entry-a",
    legacyColourOrder: () => options.legacyColourOrder ?? false,
    statusChanged: (status) => statuses.push(status),
    mediaDevices: { getUserMedia },
    createAudioContext: () => rig.context,
    visibilityDocument,
    requestFrame: scheduler.requestFrame,
    cancelFrame: scheduler.cancelFrame,
    setTimer: scheduler.setTimer,
    clearTimer: scheduler.clearTimer,
    now: () => scheduler.now,
  });
  return {
    controller,
    getUserMedia,
    rig,
    scheduler,
    statuses,
    visibilityDocument,
  };
}

function successfulSocket(
  update?: (
    message: Record<string, unknown>,
  ) => Promise<unknown>,
) {
  return vi.fn(async (message: Record<string, unknown>) => {
    if (message.type === "ha_govee_led_ble/reactive/start") {
      return {
        state: "active",
        session_id: SESSION_ID,
        route: "music_stream_order",
      };
    }
    if (message.type === "ha_govee_led_ble/reactive/update") {
      return update
        ? update(message)
        : {
            state: "active",
            session_id: SESSION_ID,
            coalesced: false,
          };
    }
    return {
      state: "idle",
      session_id: null,
      stop_reason: "requested",
    };
  });
}

function websocketMessages(
  callWS: ReturnType<typeof successfulSocket>,
  type: string,
): Record<string, unknown>[] {
  return callWS.mock.calls
    .map(([message]) => message)
    .filter((message) => message.type === type);
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

function expectReleased(
  rig: ReturnType<typeof createAudioRig>,
  scheduler: TestScheduler,
): void {
  expect(rig.track.stop).toHaveBeenCalledOnce();
  expect(rig.source.disconnect).toHaveBeenCalledOnce();
  expect(rig.analyser.disconnect).toHaveBeenCalledOnce();
  expect(rig.context.close).toHaveBeenCalledOnce();
  expect(scheduler.frameCount).toBe(0);
  expect(scheduler.timerCount).toBe(0);
}

test("frequency bands derive one deterministic bounded RGB object", () => {
  expect(deriveReactiveRgb(new Uint8Array())).toEqual({ r: 0, g: 0, b: 0 });
  expect(deriveReactiveRgb(new Uint8Array([0, 10, 100, 120, 240, 255])))
    .toEqual({ r: 5, g: 110, b: 248 });
  expect(deriveReactiveRgb([-20, 300, Number.NaN])).toEqual({
    r: 0,
    g: 255,
    b: 0,
  });
});

test("updates contain only the three derived integer RGB channels", async () => {
  const callWS = successfulSocket();
  const { controller, scheduler } = createController(callWS);

  await controller.start();
  scheduler.runFrame();
  scheduler.runDueTimers();
  await settle();

  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/update"))
    .toEqual([
      {
        type: "ha_govee_led_ble/reactive/update",
        config_entry_id: "entry-a",
        session_id: SESSION_ID,
        rgb: { r: 15, g: 35, b: 55 },
      },
    ]);
  expect(JSON.stringify(callWS.mock.calls)).not.toMatch(
    /audio|pcm|sample|stream|buffer|blob/i,
  );
});

test("updates run at no more than 20 Hz and coalesce to the latest colour", async () => {
  const sentAt: number[] = [];
  let scheduler!: TestScheduler;
  const callWS = successfulSocket(async () => {
    sentAt.push(scheduler.now);
    return {
      state: "active",
      session_id: SESSION_ID,
    };
  });
  const setup = createController(callWS);
  scheduler = setup.scheduler;
  await setup.controller.start();

  setup.rig.setValues([255, 255, 0, 0, 0, 0]);
  scheduler.runFrame();
  scheduler.runDueTimers();
  await settle();

  scheduler.advance(10);
  setup.rig.setValues([0, 0, 255, 255, 0, 0]);
  scheduler.runFrame();
  scheduler.advance(10);
  setup.rig.setValues([0, 0, 0, 0, 255, 255]);
  scheduler.runFrame();
  scheduler.advance(REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS - 21);
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/update"))
    .toHaveLength(1);

  scheduler.advance(1);
  await settle();

  const updates = websocketMessages(
    callWS,
    "ha_govee_led_ble/reactive/update",
  );
  expect(sentAt).toEqual([0, REACTIVE_RGB_MIN_UPDATE_INTERVAL_MS]);
  expect(updates).toHaveLength(2);
  expect(updates[1].rgb).toEqual({ r: 0, g: 0, b: 255 });
});

test("permission denial closes the audio context and reports the error", async () => {
  const denied = new Error("denied");
  denied.name = "NotAllowedError";
  const callWS = successfulSocket();
  const setup = createController(callWS, {
    getUserMedia: vi.fn().mockRejectedValue(denied),
  });

  await setup.controller.start();

  expect(setup.getUserMedia).toHaveBeenCalledWith({ audio: true });
  expect(setup.rig.context.close).toHaveBeenCalledOnce();
  expect(callWS).not.toHaveBeenCalled();
  expect(setup.controller.status).toEqual({
    phase: "error",
    message: "Microphone permission was denied.",
  });
});

test("backend start failure releases every local audio resource", async () => {
  const callWS = vi.fn(async () => {
    throw { code: "reactive_unknown_firmware" };
  });
  const setup = createController(callWS);

  await setup.controller.start();

  expectReleased(setup.rig, setup.scheduler);
  expect(setup.controller.status).toEqual({
    phase: "error",
    message: "This light's firmware is not recognised for reactive colour.",
  });
});

test("legacy colour ordering is omitted unless explicitly opted in", async () => {
  const normalSocket = successfulSocket();
  const normal = createController(normalSocket);
  await normal.controller.start();
  expect(normalSocket.mock.calls[0][0]).not.toHaveProperty(
    "legacy_colour_order",
  );
  await normal.controller.stop();

  const legacySocket = successfulSocket();
  const legacy = createController(legacySocket, {
    legacyColourOrder: true,
  });
  await legacy.controller.start();
  expect(legacySocket.mock.calls[0][0]).toMatchObject({
    legacy_colour_order: true,
  });
});

test("explicit stop releases browser resources and stops the backend session", async () => {
  const callWS = successfulSocket();
  const setup = createController(callWS);
  await setup.controller.start();
  setup.scheduler.runFrame();

  await setup.controller.stop();

  expectReleased(setup.rig, setup.scheduler);
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/stop"))
    .toEqual([
      {
        type: "ha_govee_led_ble/reactive/stop",
        config_entry_id: "entry-a",
        session_id: SESSION_ID,
      },
    ]);
  expect(setup.controller.status.phase).toBe("idle");
});

test("document visibility loss stops and releases the active session", async () => {
  const callWS = successfulSocket();
  const setup = createController(callWS);
  await setup.controller.start();

  setup.visibilityDocument.hide();
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/stop"))
    .toHaveLength(1);
  expect(setup.controller.status.message).toContain("page is hidden");
});

test("panel disconnect stops and releases the active session", async () => {
  const callWS = successfulSocket();
  const setup = createController(callWS);
  await setup.controller.start();

  setup.controller.disconnect();
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/stop"))
    .toHaveLength(1);
  expect(setup.controller.status.message).toContain("panel closed");
});

test("microphone track ending stops and releases the active session", async () => {
  const callWS = successfulSocket();
  const setup = createController(callWS);
  await setup.controller.start();

  setup.rig.track.end();
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/stop"))
    .toHaveLength(1);
  expect(setup.controller.status).toEqual({
    phase: "error",
    message: "Microphone input ended. Start reactive colour again.",
  });
});

test("a stale backend start completion is stopped without reviving the controller", async () => {
  let resolveStart!: (value: unknown) => void;
  const pendingStart = new Promise<unknown>((resolve) => {
    resolveStart = resolve;
  });
  const callWS = vi.fn(async (message: Record<string, unknown>) => {
    if (message.type === "ha_govee_led_ble/reactive/start") {
      return pendingStart;
    }
    return {
      state: "idle",
      session_id: null,
      stop_reason: "requested",
    };
  });
  const setup = createController(callWS);

  const starting = setup.controller.start();
  await settle();
  expect(callWS).toHaveBeenCalledOnce();
  await setup.controller.stop();
  resolveStart({ state: "active", session_id: SESSION_ID });
  await starting;
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(websocketMessages(
    callWS as ReturnType<typeof successfulSocket>,
    "ha_govee_led_ble/reactive/stop",
  )).toHaveLength(1);
  expect(setup.controller.status.phase).toBe("idle");
});

test("backend supersession status stops the browser session", async () => {
  const callWS = successfulSocket(async () => ({
    state: "idle",
    session_id: null,
    stop_reason: "superseded",
  }));
  const setup = createController(callWS);
  await setup.controller.start();

  setup.scheduler.runFrame();
  setup.scheduler.runDueTimers();
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(setup.controller.status).toEqual({
    phase: "error",
    message:
      "Reactive colour stopped because another light command took control.",
  });
});

test.each([
  [
    "session expiry",
    { code: "reactive_session_expired" },
    "The reactive colour session expired. Start it again.",
  ],
  [
    "write failure",
    { code: "reactive_write_failed" },
    "The light could not accept reactive colour updates.",
  ],
  [
    "connection failure",
    new Error("connection lost"),
    "Reactive colour stopped because the connection or update failed.",
  ],
])("%s during an update stops and releases the session", async (
  _name,
  failure,
  expectedMessage,
) => {
  const callWS = successfulSocket(async () => {
    throw failure;
  });
  const setup = createController(callWS);
  await setup.controller.start();

  setup.scheduler.runFrame();
  setup.scheduler.runDueTimers();
  await settle();

  expectReleased(setup.rig, setup.scheduler);
  expect(setup.controller.status).toEqual({
    phase: "error",
    message: expectedMessage,
  });
  expect(websocketMessages(callWS, "ha_govee_led_ble/reactive/stop"))
    .toHaveLength(1);
});
