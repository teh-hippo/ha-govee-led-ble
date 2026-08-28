import { describe, expect, test } from "vitest";

import { AsyncRequestController } from "../../src/async-request-controller";

type Context = {
  api: object;
  deviceId: string;
  selection?: string;
};

const matches = (left: Context, right: Context) =>
  left.api === right.api &&
  left.deviceId === right.deviceId &&
  left.selection === right.selection;

describe("AsyncRequestController", () => {
  test("only the newest request remains current", () => {
    const api = {};
    const controller = new AsyncRequestController<Context>(matches);
    const first = controller.begin({ api, deviceId: "a" });
    const second = controller.begin({ api, deviceId: "a" });

    expect(controller.isCurrent(first, { api, deviceId: "a" })).toBe(false);
    expect(controller.isCurrent(second, { api, deviceId: "a" })).toBe(true);
  });

  test("context changes reject stale responses without starting a request", () => {
    const api = {};
    const controller = new AsyncRequestController<Context>(matches);
    const request = controller.begin({
      api,
      deviceId: "a",
      selection: "scene:1",
    });

    expect(
      controller.isCurrent(request, {
        api,
        deviceId: "b",
        selection: "scene:1",
      }),
    ).toBe(false);
    expect(
      controller.isCurrent(request, {
        api,
        deviceId: "a",
        selection: "scene:2",
      }),
    ).toBe(false);
  });

  test("captured work shares a generation until explicitly invalidated", () => {
    const api = {};
    const controller = new AsyncRequestController<Context>(matches);
    controller.begin({ api, deviceId: "a" });
    const request = controller.capture({ api, deviceId: "a" });

    expect(controller.isCurrent(request, { api, deviceId: "a" })).toBe(true);
    controller.invalidate();
    expect(controller.isCurrent(request, { api, deviceId: "a" })).toBe(false);
  });
});
