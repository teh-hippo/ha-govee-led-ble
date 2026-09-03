import { expect, test, vi } from "vitest";

import backendContracts from "../fixtures/backend-contracts.json";
import type { EffectStudioApi } from "../../src/api";
import { PanelController } from "../../src/panel-controller";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModalController } from "../../src/panel-modal-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import {
  decodeCustomCatalogue,
  decodeDevices,
  decodeEffectContent,
} from "../../src/validation";

function controllerFor(model: PanelModel): {
  controller: PanelController;
  preview: PanelPreviewController;
} {
  const preview = new PanelPreviewController(model);
  const modal = new PanelModalController(model, {
    updateComplete: () => Promise.resolve(true),
    root: () => null,
    canMutate: () => true,
  });
  const editor = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => undefined,
    contentCommitted: () => undefined,
  });
  return {
    controller: new PanelController(model, editor, preview, modal, {
      connected: () => true,
      pathname: () => "/",
      replacePath: () => undefined,
    }),
    preview,
  };
}

function h6179Model(observedDiyCode?: number): PanelModel {
  const model = new PanelModel(() => undefined);
  model.devices = decodeDevices(backendContracts.responses.devices);
  model.selectedDeviceId = "h6179-main";
  if (observedDiyCode !== undefined) {
    model.selectedDevice!.active_state = {
      config_entry_id: "h6179-main",
      mode: "custom",
      observed_at: "2026-09-03T00:00:00Z",
      confidence: "activation_match",
      diy_code: observedDiyCode,
      effect: null,
      native_mode: null,
      matched_operation_id: null,
      active_effect: null,
    };
  }
  model.customCatalogue = decodeCustomCatalogue(
    backendContracts.responses.custom_catalogue,
  );
  model.content = decodeEffectContent(
    backendContracts.content_samples.h6179_single_diy,
  );
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "single-layer" },
  };
  model.name = "Disposable";
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  return model;
}

test("observed H6179 DIY code is discoverable but requires explicit adoption", async () => {
  const model = h6179Model(0x1234);
  const applySnapshot = vi.fn().mockResolvedValue(undefined);
  const { controller } = controllerFor(model);
  controller.api = {
    applySnapshot,
    device: vi.fn().mockResolvedValue(model.selectedDevice),
  } as unknown as EffectStudioApi;

  expect(model.h6179ExperimentalSupport).toBe(true);
  expect(model.h6179DiyCodeRequired).toBe(true);
  expect(model.h6179ObservedDiyCode).toBe(0x1234);
  expect(model.h6179ApprovedDiyCode).toBeUndefined();
  expect(model.h6179DiyCode).toBeUndefined();
  expect(model.editorAction("apply")?.enabled).toBe(false);
  expect(await controller.applyCurrentDraft()).toBe(false);
  expect(applySnapshot).not.toHaveBeenCalled();

  expect(await controller.useObservedH6179DiyCode()).toBe(true);
  expect(model.h6179ApprovedDiyCode).toBe(0x1234);
  expect(model.h6179DiyCode).toBe(0x1234);
  expect(model.editorAction("apply")?.enabled).toBe(true);
  expect(await controller.applyCurrentDraft()).toBe(true);
  expect(applySnapshot).toHaveBeenCalledWith(
    "h6179-main",
    "Disposable",
    expect.objectContaining({ kind: "h6179_single_diy" }),
    undefined,
    0x1234,
  );

  await controller.toggleLive();
  expect(model.liveApplyEnabled).toBe(true);
});

test("H6179 DIY stays blocked when no disposable item is observed", async () => {
  const model = h6179Model();
  const applySnapshot = vi.fn().mockResolvedValue(undefined);
  const { controller } = controllerFor(model);
  controller.api = {
    applySnapshot,
    device: vi.fn().mockResolvedValue(model.selectedDevice),
  } as unknown as EffectStudioApi;
  expect(model.h6179ObservedDiyCode).toBeUndefined();
  expect(model.h6179ObservedDiyCode).toBeUndefined();
  expect(model.h6179DiyCode).toBeUndefined();
  expect(await controller.useObservedH6179DiyCode()).toBe(false);
  expect(await controller.applyCurrentDraft()).toBe(false);
  expect(model.modalState).toMatchObject({
    kind: "error",
    message: expect.stringContaining("Select a disposable H6179 DIY item"),
  });
  await controller.toggleLive();
  expect(model.liveApplyEnabled).toBe(false);
  expect(applySnapshot).not.toHaveBeenCalled();
});

test("non-H6179 apply calls retain the legacy payload shape", async () => {
  const model = new PanelModel(() => undefined);
  model.devices = decodeDevices(backendContracts.responses.devices);
  model.selectedDeviceId = "h617a-main";
  model.content = decodeEffectContent(
    backendContracts.content_samples.h617a_single,
  );
  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "single-layer" },
  };
  model.name = "Compatible";
  model.isAdmin = true;
  model.liveApplyEnabled = false;
  const applySnapshot = vi.fn().mockResolvedValue(undefined);
  const { controller } = controllerFor(model);
  controller.api = {
    applySnapshot,
    device: vi.fn().mockResolvedValue(model.selectedDevice),
  } as unknown as EffectStudioApi;

  expect(await controller.applyCurrentDraft()).toBe(true);
  expect(applySnapshot).toHaveBeenCalledWith(
    "h617a-main",
    "Compatible",
    expect.objectContaining({ kind: "h617a_single" }),
    undefined,
  );
});

test("H6179 Live preview forwards the disposable code", async () => {
  const model = h6179Model(0x1234);
  model.liveApplyEnabled = true;
  const previewSnapshot = vi.fn().mockResolvedValue(undefined);
  const api = {
    subscribePreview: vi.fn().mockResolvedValue(() => undefined),
    onConnectionReady: vi.fn().mockReturnValue(() => undefined),
    closePreviewSession: vi.fn().mockResolvedValue(undefined),
    cancelPreview: vi.fn().mockResolvedValue(undefined),
    previewSnapshot,
  } as unknown as EffectStudioApi;
  const { controller, preview } = controllerFor(model);
  await preview.open(api, () => undefined);

  await controller.useObservedH6179DiyCode();

  await vi.waitFor(() => expect(previewSnapshot).toHaveBeenCalledOnce());
  expect(previewSnapshot).toHaveBeenCalledWith(
    expect.any(String),
    1,
    "h6179-main",
    "Disposable",
    expect.objectContaining({ kind: "h6179_single_diy" }),
    false,
    undefined,
    0x1234,
  );
});
