import { expect, test, vi } from "vitest";

import type { EffectStudioApi } from "../../src/api";
import { cloneBuiltInDefaultBaselines } from "../../src/built-in-default-state";
import { LivePreviewProgressController } from "../../src/live-preview-controller";
import { PanelModel } from "../../src/panel-model";
import {
  createPreviewChannelId,
  editorSnapshotProvenance,
  EffectStudioPreviewSession,
  snapshotPreviewRequest,
  type PanelPreviewRequest,
} from "../../src/panel-preview";
import {
  PanelPreviewController,
  previewStatusMessage,
} from "../../src/panel-preview-controller";
import type { PreviewStatus } from "../../src/types";

test("preview channels fall back to getRandomValues outside secure contexts", () => {
  const channelId = createPreviewChannelId(
    null,
    (values) => {
      values.forEach((_value, index) => {
        values[index] = index;
      });
      return values;
    },
  );

  expect(channelId).toBe("00010203-0405-4607-8809-0a0b0c0d0e0f");
});

test("snapshot provenance uses only exact catalogue template identity", () => {
  const catalogueSource = {
    kind: "catalogue" as const,
    owner: { section: "custom" as const, category: "single-layer" as const },
    selectionIdentity: "template:single:1:0",
    label: "Flow",
  };
  const provenance = editorSnapshotProvenance(catalogueSource);
  const request = snapshotPreviewRequest(
    "entry-a",
    "Flow",
    {
      kind: "h617a_single",
      family: 1,
      variant: 0,
      speed: 50,
      palette: [[255, 0, 0]],
    },
    false,
    provenance,
  );

  expect(provenance).toEqual({
    origin_kind: "catalogue_template",
    origin_id: catalogueSource.selectionIdentity,
  });
  expect(request).toMatchObject({ provenance });
  expect(
    editorSnapshotProvenance({
      kind: "saved",
      owner: catalogueSource.owner,
      itemId: "saved-a",
    }),
  ).toBeUndefined();
  expect(
    editorSnapshotProvenance({
      kind: "new",
      owner: catalogueSource.owner,
    }),
  ).toBeUndefined();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

function request(name: string): PanelPreviewRequest & { kind: "snapshot" } {
  return {
    kind: "snapshot",
    configEntryId: "entry-a",
    name,
    content: {
      kind: "h617a_single",
      family: 0,
      variant: 0,
      speed: 50,
      palette: [[255, 0, 0]],
    },
    fingerprint: name,
  };
}

function status(
  sequence: number,
  phase: PreviewStatus["phase"],
  sessionId = "session-a",
  configEntryId = "entry-a",
): PreviewStatus {
  return {
    session_id: sessionId,
    sequence,
    config_entry_id: configEntryId,
    phase,
    content_kind: "advanced",
    confidence: "unknown",
    error_code: null,
    error_message: null,
    write_disposition: "unknown",
    persist_default: false,
    scene_id: null,
    effect_id: null,
    default_action: null,
  };
}

test("latest desired request replaces pending admissions without local statuses", async () => {
  const first = deferred<void>();
  const previewSnapshot = vi
    .fn()
    .mockReturnValueOnce(first.promise)
    .mockResolvedValue(undefined);
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    previewSnapshot,
  } as unknown as EffectStudioApi;
  const statuses: (PreviewStatus | undefined)[] = [];
  const session = new EffectStudioPreviewSession(
    api,
    (value) => statuses.push(value),
    () => undefined,
  );
  await session.open();

  session.submit(request("First"));
  session.submit(request("Second"));
  session.submit(request("Third"));

  expect(previewSnapshot).toHaveBeenCalledTimes(1);
  expect(previewSnapshot).toHaveBeenNthCalledWith(
    1,
    expect.any(String),
    1,
    "entry-a",
    "First",
    expect.any(Object),
    undefined,
    undefined,
  );
  expect(statuses).toEqual([]);

  first.resolve();
  await vi.waitFor(() => {
    expect(previewSnapshot).toHaveBeenCalledTimes(2);
  });
  expect(previewSnapshot).toHaveBeenNthCalledWith(
    2,
    expect.any(String),
    3,
    "entry-a",
    "Third",
    expect.any(Object),
    undefined,
    undefined,
  );
});

test("catalogue provenance reaches snapshot admission unchanged", async () => {
  const previewSnapshot = vi.fn().mockResolvedValue(undefined);
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    previewSnapshot,
  } as unknown as EffectStudioApi;
  const session = new EffectStudioPreviewSession(
    api,
    () => undefined,
    () => undefined,
  );
  await session.open();
  const provenance = {
    origin_kind: "catalogue_template" as const,
    origin_id: "template:single:1:0",
  };
  session.submit({
    ...request("Flow"),
    provenance,
  });

  await vi.waitFor(() => expect(previewSnapshot).toHaveBeenCalledOnce());
  expect(previewSnapshot).toHaveBeenCalledWith(
    expect.any(String),
    1,
    "entry-a",
    "Flow",
    expect.any(Object),
    undefined,
    provenance,
  );
});

test("queued default persistence remains dirty when Live is cancelled", async () => {
  vi.stubGlobal("window", {
    setTimeout: vi.fn().mockReturnValue(1),
    clearTimeout: vi.fn(),
  });
  let subscribed!: (status: PreviewStatus) => void;
  let channelId!: string;
  const api = {
    subscribePreview: vi.fn().mockImplementation(
      async (
        sessionId: string,
        callback: (value: PreviewStatus) => void,
      ) => {
        channelId = sessionId;
        subscribed = callback;
        return () => undefined;
      },
    ),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    cancelPreview: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;
  const model = new PanelModel(() => undefined);
  const catalogue = {
    kind: "h617a_single" as const,
    family: 0,
    variant: 0,
    speed: 50,
    palette: [[255, 0, 0] as [number, number, number]],
  };
  const edited = { ...catalogue, speed: 75 };
  model.selectedDeviceId = "entry-a";
  model.editorSource = {
    kind: "catalogue",
    owner: { section: "custom", category: "single-layer" },
    selectionIdentity: "template:single:0:0",
    label: "Flow",
  };
  model.content = edited;
  model.builtInBaselines = cloneBuiltInDefaultBaselines(
    catalogue,
    catalogue,
    false,
  );
  const preview = new PanelPreviewController(model);
  await preview.open(api, () => undefined);

  subscribed({
    ...status(1, "queued", channelId),
    content_kind: edited.kind,
    persist_default: true,
    default_action: "set",
  });
  expect(model.builtInDefaultDirty).toBe(true);

  await preview.cancel();

  expect(model.builtInDefaultDirty).toBe(true);
  vi.unstubAllGlobals();
});

test("written default persistence refreshes the authoritative baseline", async () => {
  let subscribed!: (status: PreviewStatus) => void;
  let channelId!: string;
  const catalogue = {
    kind: "h617a_single" as const,
    family: 0,
    variant: 0,
    speed: 50,
    palette: [[255, 0, 0] as [number, number, number]],
  };
  const edited = { ...catalogue, speed: 75 };
  const templateDefault = vi.fn().mockResolvedValue({
    template_id: "template:single:0:0",
    content: edited,
    catalogue_content: catalogue,
    has_default: true,
  });
  const api = {
    subscribePreview: vi.fn().mockImplementation(
      async (
        sessionId: string,
        callback: (value: PreviewStatus) => void,
      ) => {
        channelId = sessionId;
        subscribed = callback;
        return () => undefined;
      },
    ),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    templateDefault,
  } as unknown as EffectStudioApi;
  const model = new PanelModel(() => undefined);
  model.selectedDeviceId = "entry-a";
  model.editorSource = {
    kind: "catalogue",
    owner: { section: "custom", category: "single-layer" },
    selectionIdentity: "template:single:0:0",
    label: "Flow",
  };
  model.content = edited;
  model.builtInBaselines = cloneBuiltInDefaultBaselines(
    catalogue,
    catalogue,
    false,
  );
  const preview = new PanelPreviewController(model);
  await preview.open(api, () => undefined);

  subscribed({
    ...status(1, "written", channelId),
    content_kind: edited.kind,
    persist_default: true,
    default_action: "set",
  });

  await vi.waitFor(() => expect(templateDefault).toHaveBeenCalledOnce());
  expect(model.builtInDefaultDirty).toBe(false);
  expect(model.builtInBaselines?.hasDefault).toBe(true);
});

test("connection loss retains and resubmits the same desired revision", async () => {
  let ready!: () => void;
  const connectionLost = {
    type: "result",
    success: false,
    error: { code: 3, message: "Connection lost" },
  };
  const previewSnapshot = vi
    .fn()
    .mockRejectedValueOnce(connectionLost)
    .mockResolvedValueOnce(undefined);
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockImplementation((callback: () => void) => {
      ready = callback;
      return () => undefined;
    }),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    previewSnapshot,
  } as unknown as EffectStudioApi;
  const requestFailed = vi.fn();
  const session = new EffectStudioPreviewSession(
    api,
    () => undefined,
    () => undefined,
    requestFailed,
  );
  await session.open();
  session.submit(request("Reconnect"));
  await vi.waitFor(() => {
    expect(previewSnapshot).toHaveBeenCalledTimes(1);
  });

  ready();
  await vi.waitFor(() => {
    expect(previewSnapshot).toHaveBeenCalledTimes(2);
  });

  const first = previewSnapshot.mock.calls[0];
  const second = previewSnapshot.mock.calls[1];
  expect(second.slice(0, 2)).toEqual(first.slice(0, 2));
  expect(requestFailed).not.toHaveBeenCalled();
});

test("definite admission rejection is surfaced without a fabricated status", async () => {
  const rejection = {
    code: "invalid_format",
    message: "The preview effect is invalid.",
  };
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    previewSnapshot: vi.fn().mockRejectedValue(rejection),
  } as unknown as EffectStudioApi;
  const statuses: (PreviewStatus | undefined)[] = [];
  const requestFailed = vi.fn();
  const session = new EffectStudioPreviewSession(
    api,
    (value) => statuses.push(value),
    () => undefined,
    requestFailed,
  );
  await session.open();
  session.submit(request("Invalid"));

  await vi.waitFor(() => {
    expect(requestFailed).toHaveBeenCalledWith(rejection);
  });
  expect(statuses).toEqual([]);
});

test("editor transitions reject late status from the stable channel", async () => {
  let subscribed!: (status: PreviewStatus) => void;
  let channelId!: string;
  const api = {
    subscribePreview: vi.fn().mockImplementation(
      async (
        sessionId: string,
        callback: (value: PreviewStatus) => void,
      ) => {
        channelId = sessionId;
        subscribed = callback;
        return () => undefined;
      },
    ),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    previewSnapshot: vi.fn().mockResolvedValue(undefined),
  } as unknown as EffectStudioApi;
  const statuses: (PreviewStatus | undefined)[] = [];
  const session = new EffectStudioPreviewSession(
    api,
    (value) => statuses.push(value),
    () => undefined,
  );
  await session.open();
  session.submit(request("Preview"));
  const failed = {
    ...status(1, "failed", channelId),
    error_code: "transport_failed",
  };

  subscribed(failed);
  session.transition();
  subscribed(failed);

  expect(statuses).toEqual([failed, undefined]);
  session.close();
  expect(api.closePreviewSession).toHaveBeenCalledWith(channelId);
});

test("closing an expired preview channel does not log a warning", async () => {
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockRejectedValue({
      code: "preview_session_not_found",
    }),
  } as unknown as EffectStudioApi;
  const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  const session = new EffectStudioPreviewSession(
    api,
    () => undefined,
    () => undefined,
  );
  await session.open();

  session.close();
  await vi.waitFor(() => {
    expect(api.closePreviewSession).toHaveBeenCalledOnce();
  });
  expect(warning).not.toHaveBeenCalled();
  warning.mockRestore();
});

test("slow writes show delayed progress and terminal statuses clear it", () => {
  let nextTimer = 1;
  const timers = new Map<number, () => void>();
  const visible: boolean[] = [];
  const progress = new LivePreviewProgressController({
    changed: (value) => visible.push(value),
    now: () => 0,
    setTimer: (callback) => {
      const id = nextTimer++;
      timers.set(id, callback);
      return id;
    },
    clearTimer: (id) => {
      timers.delete(id);
    },
  });

  progress.accept(status(1, "queued"));
  expect(timers.size).toBe(1);
  const [timerId, showProgress] = [...timers.entries()][0];
  timers.delete(timerId);
  showProgress();
  expect(visible).toEqual([true]);
  progress.accept(status(1, "written"));
  expect(visible).toEqual([true, false]);

  progress.accept(status(2, "queued"));
  progress.accept(status(2, "failed"));
  expect(timers.size).toBe(0);
});

test("device changes reset progress ownership", () => {
  let nextTimer = 1;
  const timers = new Map<number, () => void>();
  const progress = new LivePreviewProgressController({
    changed: () => undefined,
    setTimer: (callback) => {
      const id = nextTimer++;
      timers.set(id, callback);
      return id;
    },
    clearTimer: (id) => {
      timers.delete(id);
    },
  });

  progress.accept(status(1, "queued", "session-a", "entry-a"));
  progress.accept(status(2, "queued", "session-a", "entry-b"));

  expect(timers.size).toBe(1);
});

test("preview failure messages distinguish failures from unconfirmed readback", () => {
  expect(
    previewStatusMessage({
      ...status(1, "failed"),
      error_code: "transport_failed",
    }),
  ).toBe(
    "Live apply could not reach the light. Turn Live off and on to try again.",
  );
  expect(
    previewStatusMessage({
      ...status(2, "unconfirmed"),
      error_code: "device_state_mismatch",
    }),
  ).toContain("reported state did not match");
  expect(previewStatusMessage(status(3, "confirmed"))).toBeUndefined();
});
