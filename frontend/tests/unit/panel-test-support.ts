import { PanelController } from "../../src/panel-controller";
import { PanelEditorController } from "../../src/panel-editor-controller";
import { PanelModalController } from "../../src/panel-modal-controller";
import { PanelModel } from "../../src/panel-model";
import { PanelPreviewController } from "../../src/panel-preview-controller";
import type {
  CustomEffectCatalogue,
  DeviceCapabilities,
  LibraryItem,
  ModelEffectCatalogue,
  ModelSku,
  PaintedContent,
  PaletteDiyEffectContent,
  VideoProfileContent,
} from "../../src/types";

export function device(
  id: string,
  model: ModelSku,
): DeviceCapabilities {
  return {
    config_entry_id: id,
    light_entity_id: `light.${id}`,
    model,
    support_quality: "supported",
    display_name: id,
    segment_count: 15,
    custom_effects: {
      painted: "supported",
      single: "unsupported",
      multi: "unsupported",
      palette_diy: "unsupported",
      advanced: "unsupported",
      workshop: "unsupported",
    },
    profiles: {
      music: "unsupported",
      video: "unsupported",
    },
    readback: "supported",
    preview_health: {
      config_entry_id: id,
      revision: 0,
      phase: "healthy",
      incident_id: null,
      error_code: null,
      error_message: null,
      write_disposition: "not_started",
      checked_at: "2026-08-24T00:00:00Z",
    },
    effect_categories: [
      "scenes",
      "video",
      "effects",
      "multi_layered",
      "reactive",
      "advanced",
    ],
    active_state: null,
  };
}

export function painted(): PaintedContent {
  return {
    kind: "h617a_painted",
    effect: "cycle",
    speed: 50,
    brightness: 100,
    segments: [
      [1, 2, 3],
      ...Array.from({ length: 14 }, () => null),
    ],
  };
}

export function videoProfile(
  model: ModelSku,
  mode: string,
): VideoProfileContent {
  return {
    kind: "video_profile",
    model,
    mode,
    full_screen: true,
    saturation: 50,
    sound_effects: false,
    sound_effects_softness: 50,
    white_balance_position: 17,
    relative_brightness: {
      left: 100,
      top: 100,
      right: 100,
      bottom: 100,
    },
    blank_screen: false,
  };
}

export function h6199Catalogue(): ModelEffectCatalogue {
  return {
    sku: "H6199",
    painted_effects: [],
    effects: [
      {
        id: "fade",
        label: "Fade",
        family: 1,
        variations: [{ id: "base", label: "Base", variant: 0 }],
        supports_multi: false,
        rate: "speed",
        rate_min: 0,
        rate_max: 100,
        category: "single_layer",
      },
    ],
    music_settings: {
      energetic: {available: true, style: false, calm_default: false, colour: true, evidence: "fixture", palette_size: 0, parameters: {}},
      rhythm: {available: true, style: true, calm_default: false, colour: true, evidence: "fixture", palette_size: 0, parameters: {}},
    },
    music_modes: [
      { id: "energetic", label: "Energetic" },
      { id: "rhythm", label: "Rhythm" },
    ],
    video_modes: [
      { id: "movie", label: "Movie" },
      { id: "game", label: "Game" },
    ],
    video_settings: [
      "capture_region",
      "saturation",
      "sound_effects",
      "white_balance",
      "relative_brightness",
      "blank_screen",
    ],
    templates: [
      {
        id: "template:video:movie",
        label: "Movie",
        category: "video",
        content: videoProfile("H6199", "movie"),
      },
      {
        id: "template:video:game",
        label: "Game",
        category: "video",
        content: videoProfile("H6199", "game"),
      },
    ],
    workshop_templates: [],
    workflows: [],
    supports: {
      multi: "unsupported",
      advanced: "supported",
      workshop: "unsupported",
    },
    limits: {
      palette_min: 1,
      speed_min: 0,
      speed_max: 100,
      brightness_min: 0,
      brightness_max: 100,
      palette_max: 8,
      multi_max: 5,
      music_sensitivity_min: 0,
      music_sensitivity_max: 100,
    },
    apply: {
      painted: "unsupported",
      single: "unsupported",
      multi: "unsupported",
      palette_diy: "supported",
      workshop: "unsupported",
    },
  };
}

export function installH6199Catalogue(model: PanelModel): void {
  const catalogue = h6199Catalogue();
  model.customCatalogue = {
    ...catalogue,
    schema_version: 12,
    sku: "H617A",
    models: {
      H617A: { ...catalogue, sku: "H617A" },
      H617E: { ...catalogue, sku: "H617E" },
      H6199: catalogue,
    },
  } as CustomEffectCatalogue;
}

export function item(content: PaintedContent): LibraryItem {
  return {
    schema_version: 1,
    id: "item-1",
    version: 2,
    updated_at: "2026-08-18T00:00:00Z",
    name: "Saved paint",
    content,
    content_hash: "hash",
    origin: { kind: "authored", source_id: null },
    extensions: {},
  };
}

export function panelModal(model: PanelModel): PanelModalController {
  return new PanelModalController(model, {
    updateComplete: async () => undefined,
    root: () => null,
    canMutate: () => true,
  });
}

export function flowWorkspaceDevice(id: string): DeviceCapabilities {
  const selected = device(id, "H6199");
  selected.custom_effects.palette_diy = "supported";
  const content: PaletteDiyEffectContent = {
    kind: "palette_diy",
    model: "H6199",
    family: 1,
    variant: 0,
    speed: 73,
    palette: [[12, 34, 56]],
  };
  selected.active_state = {
    config_entry_id: selected.config_entry_id,
    mode: "custom",
    observed_at: "2026-08-25T00:00:00Z",
    confidence: "write_completed",
    diy_code: 601,
    effect: null,
    native_mode: null,
    matched_operation_id: "operation-flow",
    active_effect: {
      source_kind: "snapshot",
      selector_label: "Flow",
      content_hash: "a".repeat(64),
      origin: {
        kind: "catalogue_template",
        source_id: "template:single:1:0",
      },
      observable_signature: "custom:601",
      confidence: "write_completed",
      item_id: null,
      item_version: null,
    },
  };
  selected.active_workspace = {
    config_entry_id: selected.config_entry_id,
    model: selected.model,
    selector_label: "Flow",
    content,
    content_hash: "a".repeat(64),
    origin: {
      kind: "catalogue_template",
      source_id: "template:single:1:0",
    },
    observable_signature: "custom:601",
    updated_at: "2026-08-25T00:00:00Z",
    generation: 1,
    confidence: "write_completed",
  };
  return selected;
}

export function installFlowCatalogue(model: PanelModel): void {
  installH6199Catalogue(model);
  model.customCatalogue!.models.H6199.effects[0] = {
    ...model.customCatalogue!.models.H6199.effects[0],
    id: "flow",
    label: "Flow",
  };
}

export function panelControllerHarness(
  model: PanelModel,
  saveSceneWork?: () => Promise<boolean>,
) {
  const preview = new PanelPreviewController(model);
  const modal = panelModal(model);
  let controller!: PanelController;
  const editorController = new PanelEditorController(model, preview, modal, {
    apiReady: () => true,
    selectItem: () => undefined,
    editorTransitionStarted: () => controller.cancelPendingAutoSave(),
    contentCommitted: () => undefined,
  });
  controller = new PanelController(
    model,
    editorController,
    preview,
    modal,
    {
      connected: () => true,
      pathname: () => "/ha-govee-led-ble",
      replacePath: () => undefined,
      saveSceneWork,
    },
  );
  return { controller, editorController, preview, modal };
}
