import { expect, test, vi } from "vitest";
import backendContracts from "../fixtures/backend-contracts.json";
import { PanelModel } from "../../src/panel-model";
import { serialiseEditable } from "../../src/effect-editor-model";
import { decodeCustomCatalogue, decodeDevices } from "../../src/validation";
import type { HomeAssistant, MusicProfileContent } from "../../src/types";
import { device, painted, videoProfile, installH6199Catalogue, item, flowWorkspaceDevice, installFlowCatalogue } from "./panel-test-support";

test("experimental feedback stays visible without enabled workflows and uses only explicit report fields", () => {
  const model = new PanelModel(() => undefined);
  const selected = {
    ...device("private-entry", "H6125"),
    display_name: "Private device name",
    support_quality: "experimental" as const,
    confirmation_issue: 447,
    hw_version: "3.01.10",
    fw_version: "3.04.37",
    effect_categories: [],
  };
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  model.integrationVersion = "7.24.4rc1";
  expect(model.experimentalSupport).toBe(true);
  expect(model.showFeedbackNotice).toBe(true);
  const report = model.deviceFeedbackReport(selected);
  expect(report).toContain("- Model: H6125");
  expect(report).toContain("- Hardware version: 3.01.10");
  expect(report).toContain("- Firmware version: 3.04.37");
  expect(report).toContain("- Integration version: 7.24.4rc1");
  expect(report).not.toContain("private-entry");
  expect(report).not.toContain("Private device name");
  expect(model.deviceFeedbackReport({ ...selected, hw_version: null, fw_version: null })).toContain("not yet observed");
  model.devices = [{ ...selected, support_quality: "supported" }];
  expect(model.experimentalSupport).toBe(false);
});

test("feedback visibility is per light and does not change support classification", () => {
  const model = new PanelModel(() => undefined);
  model.devices = ["first", "second"].map(id => ({ ...device(id, "H6125"), support_quality: "experimental" }));
  model.selectedDeviceId = "first";
  model.sessionHiddenFeedback.add("first");
  expect(model.showFeedbackNotice).toBe(false);
  expect(model.experimentalSupport).toBe(true);
  model.selectedDeviceId = "second";
  expect(model.showFeedbackNotice).toBe(true);
  model.devices[1] = { ...model.devices[1], show_experimental_feedback: false };
  expect(model.showFeedbackNotice).toBe(false);
  expect(model.experimentalSupport).toBe(true);
});

test("device music geometry replaces catalogue defaults without leaking across devices", () => {
  const model = new PanelModel(() => undefined);
  installH6199Catalogue(model);
  const catalogue = model.customCatalogue!.models.H6199;
  model.customCatalogue!.models.H6099 = { ...catalogue, sku: "H6099", painted_addressing: "physical_ic" };
  const settings = {
    piano_keys: {
      available: true, style: false, calm_default: false, colour: false, evidence: "template", palette_size: 7,
      parameters: { key_count: { kind: "number", default: 18, min: 9, max: 36, options: [] } },
    },
    hopping: {
      available: true, style: false, calm_default: false, colour: false, evidence: "template", palette_size: 7,
      parameters: { background: { kind: "number", default: 0x010101, min: 0, max: 0xffffff, options: [] } },
    },
  };
  model.devices = decodeDevices([
    { ...device("known", "H6099"), physical_ic_count: 60, music_settings: settings },
    { ...device("unknown", "H6099"), physical_ic_count: null, music_settings: {} },
  ]);
  model.selectedDeviceId = "known";
  expect(model.modelCatalogue?.physical_ic_count).toBe(60);
  expect(model.modelCatalogue?.music_settings.piano_keys.parameters.key_count.max).toBe(36);
  model.selectedDeviceId = "unknown";
  expect(model.modelCatalogue?.physical_ic_count).toBeUndefined();
  expect(model.modelCatalogue?.music_settings).toEqual({});
  expect(model.customCatalogue!.models.H6099.music_settings).toBe(catalogue.music_settings);
  for (const count of [0, 32768]) {
    expect(() => decodeDevices([{ ...device("invalid", "H6099"), physical_ic_count: count }])).toThrow();
  }
  expect(() => decodeDevices([{ ...device("large", "H6099"), physical_ic_count: 32767 }])).not.toThrow();
});

test("effective music roster filters modes and templates on device subscription replacement", () => {
  const model = new PanelModel(() => undefined);
  model.customCatalogue = decodeCustomCatalogue(backendContracts.responses.custom_catalogue);
  const catalogue = model.customCatalogue!.models.H6102;
  const originalMode = catalogue.music_modes[0];
  const originalSettings = catalogue.music_settings[originalMode.id];
  const originalTemplate = catalogue.templates!.find(t => t.content.kind === "music_profile")!;
  catalogue.music_modes = Array.from({length: 11}, (_, index) => ({...originalMode, id: `mode_${index}`}));
  catalogue.music_settings = Object.fromEntries(catalogue.music_modes.map(mode => [mode.id, originalSettings]));
  catalogue.templates = catalogue.music_modes.map(mode => ({...originalTemplate, id: `template:${mode.id}`,
    content: {...originalTemplate.content as MusicProfileContent, mode: mode.id}}));
  const modes = catalogue.music_modes;
  expect(modes.length).toBeGreaterThan(4);
  const basic = Object.fromEntries(modes.slice(0, 4).map(mode => [mode.id, catalogue.music_settings[mode.id]]));
  model.devices = [{ ...device("target", "H6102"), music_settings: basic }];
  model.selectedDeviceId = "target";
  expect(model.modelCatalogue!.music_modes).toHaveLength(4);
  expect(model.modelCatalogue!.templates!.filter(t => t.content.kind === "music_profile")).toHaveLength(4);
  model.devices = [{ ...device("target", "H6102"), music_settings: catalogue.music_settings }];
  expect(model.modelCatalogue!.music_modes).toHaveLength(modes.length);
  model.devices = [{ ...device("target", "H6102"), music_settings: {} }];
  expect(model.modelCatalogue!.music_modes).toEqual([]);
  expect(catalogue.music_modes).toBe(modes);
});

test("two controller revisions use their complete device catalogues without changing the SKU ceiling", () => {
  const model = new PanelModel(() => undefined);
  model.customCatalogue = decodeCustomCatalogue(backendContracts.responses.custom_catalogue);
  const ceiling = structuredClone(model.customCatalogue.models.H6125);
  model.devices = decodeDevices(Object.values(backendContracts.device_profile_samples));
  model.selectedDeviceId = "h6125-original";
  expect(model.modelCatalogue!.apply.painted).toBe("unsupported");
  expect(model.modelCatalogue!.painted_effects).toEqual([]);
  expect(model.modelCatalogue!.templates!.some(template => template.id === "template:paint")).toBe(false);
  const rhythm = model.modelCatalogue!.templates!.find(template => template.id === "template:music:rhythm")!;
  expect(rhythm.content).toMatchObject({kind: "music_profile", calm: null});
  expect(model.modelCatalogue!.music_modes).toHaveLength(4);

  model.selectedDeviceId = "h6125-modern";
  expect(model.modelCatalogue!.apply.painted).toBe("supported");
  const paint = model.modelCatalogue!.templates!.find(template => template.id === "template:paint")!;
  expect(paint).toHaveProperty("content.segments.length", 50);
  expect(model.modelCatalogue!.music_modes).toHaveLength(11);
  expect(model.customCatalogue.models.H6125).toEqual(ceiling);

  model.selectedDeviceId = "h6125-original";
  expect(model.modelCatalogue!.apply.painted).toBe("unsupported");
  const foreign = structuredClone(backendContracts.device_profile_samples.original);
  foreign.catalogue.sku = "H6199";
  expect(() => decodeDevices([foreign])).toThrow();
});

test("live video conditions reject requested settings without stripping persisted content", () => {
  const model = new PanelModel(() => undefined);
  const target = device("video", "H6199");
  installH6199Catalogue(model);
  target.custom_effects.palette_diy = "supported";
  target.profiles.video = "supported";
  target.video_control_states = {white_balance: "evidence_gap"};
  model.devices = [target];
  model.selectedDeviceId = "video";
  model.content = videoProfile("H6199", "movie");
  expect(model.previewCapability).toBe("evidence_gap");
  expect(model.content.white_balance_position).toBe(17);
  target.video_control_states.white_balance = "unsupported";
  expect(model.previewCapability).toBe("unsupported");
  model.content = {...model.content, white_balance_position: null};
  expect(model.previewCapability).toBe("supported");
  model.content = {
    kind: "palette_diy", model: "H6199", family: 1, variant: 0,
    speed: 50, palette: [[255, 0, 0]],
  };
  expect(model.previewCapability).toBe("supported");
});

test("unknown border firmware blocks only profiles requesting border removal", () => {
  const model = new PanelModel(() => undefined);
  const target = device("video", "H6099");
  target.profiles.video = "supported";
  target.video_control_states = {black_border: "evidence_gap"};
  model.devices = [target];
  model.selectedDeviceId = "video";
  model.content = videoProfile("H6099", "movie");
  expect(model.previewCapability).toBe("supported");
  model.content = {...model.content, black_border: false};
  expect(model.previewCapability).toBe("evidence_gap");
  target.video_control_states.black_border = "unsupported";
  expect(model.previewCapability).toBe("unsupported");
  target.video_control_states.black_border = "supported";
  expect(model.previewCapability).toBe("supported");
  target.video_control_states.black_border = "evidence_gap";
  delete model.content.black_border;
  expect(model.previewCapability).toBe("supported");
});

test("video saturation eligibility uses the target catalogue minimum", () => {
  const model = new PanelModel(() => undefined);
  const target = device("video", "H6199");
  installH6199Catalogue(model);
  target.profiles.video = "supported";
  model.devices = [target];
  model.selectedDeviceId = "video";
  model.content = {...videoProfile("H6199", "movie"), saturation: 0};
  expect(model.previewCapability).toBe("supported");
  const catalogue = model.modelCatalogue;
  if (!catalogue) throw new Error("Missing video catalogue");
  const controls = catalogue.video_controls = {
    saturation_min: 0,
    white_balance: {representation: "position", minimum: 1, maximum: 20, default: 17},
    brightness_zones: ["left", "top", "right", "bottom"],
  };
  controls.saturation_min = 1;
  expect(model.previewCapability).toBe("unsupported");
  model.content.saturation = 1;
  expect(model.previewCapability).toBe("supported");
  model.content.saturation = null;
  expect(model.previewCapability).toBe("supported");
});

test("derives selected-device and preview decisions from panel state", () => {
  const model = new PanelModel(() => undefined);
  model.devices = [device("entry-a", "H617A")];
  model.selectedDeviceId = "entry-a";
  model.isAdmin = true;

  expect(model.selectedDevice?.display_name).toBe("entry-a");
  expect(model.selectedModel).toBe("H617A");
  expect(model.previewCapability).toBe("unsupported");
  installFlowCatalogue(model);
  model.content = { kind: "palette_diy", model: "H6199", family: 1, variant: 0, speed: 50, palette: [[255, 0, 0]] };
  model.devices = [flowWorkspaceDevice("entry-a")];
  expect(model.previewCapability).toBe("supported");
  expect(model.showDeviceSelector).toBe(false);

  model.selectedDeviceId = "missing";
  expect(model.selectedDevice).toBeUndefined();
  expect(model.showDeviceSelector).toBe(true);
});

test("administrator state follows late Home Assistant user updates", () => {
  const changed = vi.fn();
  const model = new PanelModel(changed);

  model.syncAdmin({ user: undefined } as unknown as HomeAssistant);
  expect(model.isAdmin).toBe(false);

  model.syncAdmin({
    user: { is_admin: true },
  } as unknown as HomeAssistant);
  expect(model.isAdmin).toBe(true);
  expect(changed).toHaveBeenCalledOnce();
});

test("save and effect-family controls distinguish starters, New drafts, and saved effects", () => {
  const model = new PanelModel(() => undefined);
  model.name = "Jumping";
  model.content = painted();
  model.savedBaseline = serialiseEditable(model.name, model.content);
  model.editorSource = {
    kind: "catalogue",
    owner: { section: "custom", category: "single-layer" },
    selectionIdentity: "template:paint",
    label: "Paint",
  };

  expect(model.dirty).toBe(false);
  expect(model.canSaveCurrentDraft).toBe(false);
  expect(model.showSingleEffectSelector).toBe(false);

  model.editorSource = {
    kind: "new",
    owner: { section: "custom", category: "single-layer" },
  };
  expect(model.showSingleEffectSelector).toBe(true);

  model.currentItem = item(painted());
  model.editorSource = {
    kind: "saved",
    owner: { section: "custom", category: "single-layer" },
    itemId: model.currentItem.id,
  };
  expect(model.showSingleEffectSelector).toBe(true);
  expect(model.canSaveCurrentDraft).toBe(false);
});

test("music eligibility rejects retained invalid parameters without changing the draft", () => {
  const model = new PanelModel(() => undefined);
  model.isAdmin = true;
  const selected = device("entry-a", "H6199");
  selected.profiles.music = "supported";
  model.devices = [selected];
  model.selectedDeviceId = selected.config_entry_id;
  installH6199Catalogue(model);
  const catalogue = model.modelCatalogue!;
  catalogue.music_modes.push({id: "separation", label: "Separation"});
  catalogue.music_settings.separation = {
    available: true, style: false, calm_default: false, colour: false, evidence: "synthetic", palette_size: 5,
    parameters: {point: {kind: "number", default: 1, min: 1, max: 5, options: []}},
  };
  const valid: MusicProfileContent = {kind: "music_profile", model: "H6199", mode: "separation", sensitivity: 50, colour: null, calm: null, parameters: {}};
  model.content = valid;
  expect(model.previewCapability).toBe("supported");
  const changesToReject: Partial<MusicProfileContent>[] = [
    {parameters: {point: 6}}, {parameters: {point: true}}, {parameters: {unknown: 1}},
    {calm: false}, {colour: [1, 2, 3] as [number, number, number]}, {sensitivity: 101},
  ];
  for (const changes of changesToReject) {
    const retained = {...valid, ...changes};
    model.content = retained;
    expect(model.previewCapability).toBe("unsupported");
    expect(model.content).toEqual(retained);
  }
  model.content = valid;
  catalogue.music_settings.separation.available = false;
  expect(model.previewCapability).toBe("unsupported");
});
