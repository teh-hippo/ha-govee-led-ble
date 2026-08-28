import type {
  AdvancedContent,
  BuiltinSceneContent,
  CatalogueTemplateDefaultDetail,
  DeviceCapabilities,
  EditorApiInfo,
  EffectContent,
  EffectUserState,
  EffectLayer,
  JsonObject,
  KnownEffectContent,
  LayeredSceneContent,
  LibraryItem,
  LibrarySnapshot,
  ModelSku,
  MusicProfileContent,
  PaletteSceneContent,
  PaletteDiyEffectContent,
  PreviewHealthStatus,
  PreviewStatus,
  RelativeBrightness,
  RGB,
  SceneCatalogue,
  SceneDetail,
  SceneSummary,
  VideoProfileContent,
  WorkshopContent,
} from "./types";
import { decodeCustomCataloguePayload } from "./catalogue-validation";
import {
  EDITOR_API_VERSION,
  EFFECT_COMPILER_VERSION,
  EFFECT_SCHEMA_VERSION,
} from "./contracts";
import {
  arrayValue,
  assertBoundedJson,
  booleanValue,
  boundedString,
  boundedStringAllowEmpty,
  byteValue,
  capabilityValue,
  enumString,
  exactInteger,
  hexString,
  integerValue,
  invalid,
  MAX_JSON_COLLECTION_ITEMS,
  MAX_SAFE_REVISION,
  nullableInteger,
  objectValue,
  requireUnique,
  stringValue,
} from "./payload-validation";
import { PREVIEW_PHASES } from "./types";
import { installLibraryItemEditorMetadata } from "./effect-editor-model";
import {
  LAYER_UNKNOWN_FLAGS_MASK,
  MAX_CATALOGUE_BYTES,
  MAX_CATALOGUE_JSON_NODES,
  MAX_DEPLOYMENT_RECORDS,
  MAX_EDITOR_DEVICES,
  MAX_EFFECT_DOCUMENT_BYTES,
  MAX_EFFECT_NAME_LENGTH,
  MAX_IDENTIFIER_LENGTH,
  MAX_LIBRARY_ITEMS,
  MAX_SCENE_CATALOGUE_ENTRIES,
  MAX_TIMESTAMP_LENGTH,
  MAX_USER_STATE_NAVIGATION_BYTES,
  MODEL_SKUS,
  MOVEMENT_UNKNOWN_FLAGS_MASK,
  PALETTE_CONFIG_RESERVED_MASK,
  SCENE_TRAILING_PADDING_MAX,
  VIDEO_MODE_IDS,
} from "./validation-constants";

const VERIFICATION_CONFIDENCE = [
  "exact_session",
  "activation_match",
  "settings_match",
  "mode_match",
  "write_completed",
  "unknown",
] as const;
type WireOpaqueContent = Record<string, unknown> & { kind: string };
type WireEffectContent = KnownEffectContent | WireOpaqueContent;

export function decodeCustomCatalogue(value: unknown) {
  return decodeCustomCataloguePayload(value, decodeEffectContent);
}

export function decodeEditorApiInfo(value: unknown): EditorApiInfo {
  const info = objectValue(value, "editor info");
  const limits = objectValue(info.limits, "editor limits");
  return {
    api_version: integerValue(info.api_version, "API version", 1),
    effect_schema_version: integerValue(
      info.effect_schema_version,
      "effect schema version",
      1,
    ),
    compiler_version: integerValue(
      info.compiler_version,
      "compiler version",
      1,
    ),
    limits: {
      effect_name: exactInteger(
        limits.effect_name,
        MAX_EFFECT_NAME_LENGTH,
        "effect-name limit",
      ),
      effect_document_bytes: exactInteger(
        limits.effect_document_bytes,
        MAX_EFFECT_DOCUMENT_BYTES,
        "effect-document limit",
      ),
      devices: exactInteger(
        limits.devices,
        MAX_EDITOR_DEVICES,
        "device limit",
      ),
      library_items: exactInteger(
        limits.library_items,
        MAX_LIBRARY_ITEMS,
        "library-item limit",
      ),
      deployment_records: exactInteger(
        limits.deployment_records,
        MAX_DEPLOYMENT_RECORDS,
        "deployment limit",
      ),
      scene_catalogue_entries: exactInteger(
        limits.scene_catalogue_entries,
        MAX_SCENE_CATALOGUE_ENTRIES,
        "scene catalogue limit",
      ),
    },
  };
}

export function decodeDevices(value: unknown): DeviceCapabilities[] {
  const devices = arrayValue(value, "devices", MAX_EDITOR_DEVICES).map((item, index) => {
    const device = objectValue(item, `devices[${index}]`);
    const effects = objectValue(
      device.custom_effects,
      `devices[${index}].custom_effects`,
    );
    const profiles = objectValue(
      device.profiles,
      `devices[${index}].profiles`,
    );
    return {
      config_entry_id: boundedString(
        device.config_entry_id,
        `devices[${index}].config_entry_id`,
        MAX_IDENTIFIER_LENGTH,
      ),
      light_entity_id: optionalLightEntityId(
        device.light_entity_id,
        `devices[${index}].light_entity_id`,
      ),
      model: boundedString(
        device.model,
        `devices[${index}].model`,
        MAX_IDENTIFIER_LENGTH,
      ),
      display_name: boundedString(
        device.display_name,
        `devices[${index}].display_name`,
        MAX_IDENTIFIER_LENGTH,
      ),
      segment_count: integerValue(
        device.segment_count,
        `devices[${index}].segment_count`,
        0,
        65_535,
      ),
      custom_effects: {
        painted: capabilityValue(effects.painted, "painted capability"),
        single: capabilityValue(effects.single, "single capability"),
        multi: capabilityValue(effects.multi, "multi capability"),
        palette_diy: capabilityValue(
          effects.palette_diy,
          "palette DIY capability",
        ),
        advanced: capabilityValue(effects.advanced, "advanced capability"),
        workshop: capabilityValue(effects.workshop, "Workshop capability"),
      },
      profiles: {
        music: capabilityValue(profiles.music, "music profile capability"),
        video: capabilityValue(profiles.video, "video profile capability"),
      },
      readback: boundedString(
        device.readback,
        `devices[${index}].readback`,
        MAX_IDENTIFIER_LENGTH,
      ),
      effect_categories: stringArray(
        device.effect_categories,
        `devices[${index}].effect_categories`,
        MAX_IDENTIFIER_LENGTH,
      ),
      preview_health: decodePreviewHealthStatus(
        device.preview_health,
      ),
      active_state:
        device.active_state === null
          ? null
          : decodeObservedEffectState(
              device.active_state,
              `devices[${index}].active_state`,
            ),
      ...(device.active_workspace === undefined
        ? {}
        : {
            active_workspace:
              device.active_workspace === null
                ? null
                : decodeActiveEffectWorkspace(
                    device.active_workspace,
                    `devices[${index}].active_workspace`,
                  ),
          }),
    };
  });
  requireUnique(devices, (device) => device.config_entry_id, "device IDs");
  return devices;
}

function optionalLightEntityId(value: unknown, name: string): string | null {
  if (value === undefined || value === null) {
    return null;
  }
  const entityId = boundedString(value, name, MAX_IDENTIFIER_LENGTH);
  if (!entityId.startsWith("light.") || entityId.length === "light.".length) {
    invalid(`${name} must identify a light entity`);
  }
  return entityId;
}

export function decodeEffectUserState(value: unknown): EffectUserState {
  const state = objectValue(value, "user state");
  assertBoundedJson(
    state.navigation,
    "user-state navigation",
    MAX_USER_STATE_NAVIGATION_BYTES,
  );
  return {
    owner_id: boundedString(
      state.owner_id,
      "user-state owner",
      MAX_IDENTIFIER_LENGTH,
    ),
    recent_colours: arrayValue(
      state.recent_colours,
      "user-state recent colours",
      12,
    ).map((colour, index) =>
      rgbValue(colour, `user-state recent colours[${index}]`),
    ),
    selected_config_entry_id: nullableBoundedString(
      state.selected_config_entry_id,
      "user-state selected config entry ID",
    ),
    navigation: objectValue(
      state.navigation,
      "user-state navigation",
    ) as JsonObject,
  };
}

function decodeObservedEffectState(value: unknown, name: string) {
  const state = objectValue(value, name);
  const activeEffect =
    state.active_effect === null
      ? null
      : decodeActiveEffectHint(state.active_effect, `${name}.active_effect`);
  const confidence = enumString(
    state.confidence,
    VERIFICATION_CONFIDENCE,
    `${name}.confidence`,
  );
  if (activeEffect !== null && activeEffect.confidence !== confidence) {
    invalid(`${name} active-effect confidence does not match the observation`);
  }

  return {
    config_entry_id: boundedString(
      state.config_entry_id,
      `${name}.config_entry_id`,
      MAX_IDENTIFIER_LENGTH,
    ),
    mode: boundedString(state.mode, `${name}.mode`, MAX_IDENTIFIER_LENGTH),
    observed_at: timestampString(state.observed_at, `${name}.observed_at`),
    confidence,
    diy_code: nullableInteger(state.diy_code, `${name}.diy_code`, 0, 65_535),
    effect:
      state.effect === null
        ? null
        : boundedString(state.effect, `${name}.effect`, MAX_IDENTIFIER_LENGTH),
    native_mode:
      state.native_mode === null
        ? null
        : boundedString(
            state.native_mode,
            `${name}.native_mode`,
            MAX_IDENTIFIER_LENGTH,
          ),
    matched_operation_id:
      state.matched_operation_id === null
        ? null
        : boundedString(
            state.matched_operation_id,
            `${name}.matched_operation_id`,
            MAX_IDENTIFIER_LENGTH,
          ),
    active_effect: activeEffect,
  };
}

function decodeActiveEffectWorkspace(value: unknown, name: string) {
  const workspace = objectValue(value, name);
  return {
    config_entry_id: boundedString(
      workspace.config_entry_id,
      `${name}.config_entry_id`,
      MAX_IDENTIFIER_LENGTH,
    ),
    model: boundedString(
      workspace.model,
      `${name}.model`,
      MAX_IDENTIFIER_LENGTH,
    ),
    selector_label: boundedString(
      workspace.selector_label,
      `${name}.selector_label`,
      MAX_EFFECT_NAME_LENGTH,
    ),
    content: decodeEffectContent(workspace.content),
    content_hash: contentHash(
      workspace.content_hash,
      `${name}.content_hash`,
    ),
    origin: decodeOrigin(workspace.origin),
    observable_signature: boundedString(
      workspace.observable_signature,
      `${name}.observable_signature`,
      MAX_IDENTIFIER_LENGTH,
    ),
    updated_at: timestampString(workspace.updated_at, `${name}.updated_at`),
    generation: integerValue(
      workspace.generation,
      `${name}.generation`,
      1,
      MAX_SAFE_REVISION,
    ),
    confidence: enumString(
      workspace.confidence,
      VERIFICATION_CONFIDENCE,
      `${name}.confidence`,
    ),
  };
}

function decodeActiveEffectHint(value: unknown, name: string) {
  const hint = objectValue(value, name);
  const origin = objectValue(hint.origin, `${name}.origin`);
  const sourceKind = enumString(
    hint.source_kind,
    ["saved_effect", "snapshot", "deleted_effect"] as const,
    `${name}.source_kind`,
  );
  const itemId =
    hint.item_id === null
      ? null
      : boundedString(hint.item_id, `${name}.item_id`, MAX_IDENTIFIER_LENGTH);
  const itemVersion = nullableInteger(
    hint.item_version,
    `${name}.item_version`,
    1,
    MAX_SAFE_REVISION,
  );
  if (sourceKind === "saved_effect" ? itemId === null || itemVersion === null : itemId !== null || itemVersion !== null) {
    invalid(`${name} has inconsistent library identity`);
  }
  return {
    source_kind: sourceKind,
    selector_label: boundedString(
      hint.selector_label,
      `${name}.selector_label`,
      MAX_IDENTIFIER_LENGTH,
    ),
    content_hash: contentHash(hint.content_hash, `${name}.content_hash`),
    origin: {
      kind: boundedString(
        origin.kind,
        `${name}.origin.kind`,
        MAX_IDENTIFIER_LENGTH,
      ),
      source_id:
        origin.source_id === null
          ? null
          : boundedString(
              origin.source_id,
              `${name}.origin.source_id`,
              MAX_IDENTIFIER_LENGTH,
            ),
    },
    observable_signature: boundedString(
      hint.observable_signature,
      `${name}.observable_signature`,
      MAX_IDENTIFIER_LENGTH,
    ),
    confidence: enumString(
      hint.confidence,
      VERIFICATION_CONFIDENCE,
      `${name}.confidence`,
    ),
    item_id: itemId,
    item_version: itemVersion,
  };
}

export function decodeLibrarySnapshot(value: unknown): LibrarySnapshot {
  const snapshot = objectValue(value, "library snapshot");
  const decoded: LibrarySnapshot = {
    generation:
      snapshot.generation === undefined
        ? 0
        : integerValue(
            snapshot.generation,
            "library generation",
            0,
            MAX_SAFE_REVISION,
          ),
    items: arrayValue(
      snapshot.items,
      "library items",
      MAX_LIBRARY_ITEMS,
    ).map((item, index) => {
      const summary = objectValue(item, `library items[${index}]`);
      const template =
        summary.template === undefined
          ? undefined
          : catalogueRef(summary.template, `library items[${index}].template`);
      const model =
        summary.model === undefined
          ? undefined
          : knownModelSku(summary.model);
      return {
        id: boundedString(summary.id, "library item ID", MAX_IDENTIFIER_LENGTH),
        version: revisionValue(summary.version, "library item version", 1),
        updated_at: timestampString(summary.updated_at, "library item timestamp"),
        name: boundedString(
          summary.name,
          "library item name",
          MAX_EFFECT_NAME_LENGTH,
        ),
        kind: boundedString(
          summary.kind,
          "library item kind",
          MAX_IDENTIFIER_LENGTH,
        ),
        content_hash: contentHash(summary.content_hash, "library item content hash"),
        origin: decodeOrigin(summary.origin),
        ...(model ? { model } : {}),
        ...(template ? { template } : {}),
      };
    }),
  };
  requireUnique(decoded.items, (item) => item.id, "library item IDs");
  return decoded;
}

export function decodeLibraryItem(value: unknown): LibraryItem {
  assertBoundedJson(value, "library item", MAX_EFFECT_DOCUMENT_BYTES);
  const item = objectValue(value, "library item");
  const target =
    item.target_hint === undefined
      ? undefined
      : objectValue(item.target_hint, "target hint");
  return installLibraryItemEditorMetadata({
    schema_version: exactInteger(
      item.schema_version,
      EFFECT_SCHEMA_VERSION,
      "effect schema version",
    ),
    id: boundedString(item.id, "effect ID", MAX_IDENTIFIER_LENGTH),
    version: revisionValue(item.version, "effect version", 1),
    updated_at: timestampString(item.updated_at, "effect timestamp"),
    name: boundedString(item.name, "effect name", MAX_EFFECT_NAME_LENGTH),
    content: decodeEffectContent(item.content),
    content_hash: contentHash(item.content_hash, "effect content hash"),
    origin: decodeOrigin(item.origin),
    extensions: boundedRecord(item.extensions, "effect extensions"),
    ...(target
      ? {
          target_hint: {
            model:
              target.model === null
                ? null
                : boundedString(
                    target.model,
                    "target model",
                    MAX_IDENTIFIER_LENGTH,
                  ),
            segment_count:
              target.segment_count === null
                ? null
                : integerValue(
                    target.segment_count,
                    "target segment count",
                    1,
                    65_535,
                  ),
          },
        }
      : {}),
  });
}

export function decodePreviewStatus(value: unknown): PreviewStatus {
  const status = objectValue(value, "preview status");
  return {
    session_id: boundedString(
      status.session_id,
      "preview session ID",
      MAX_IDENTIFIER_LENGTH,
    ),
    sequence: integerValue(
      status.sequence,
      "preview sequence",
      0,
      MAX_SAFE_REVISION,
    ),
    config_entry_id: boundedString(
      status.config_entry_id,
      "preview config entry ID",
      MAX_IDENTIFIER_LENGTH,
    ),
    phase: enumString(status.phase, PREVIEW_PHASES, "preview phase"),
    content_kind: boundedString(
      status.content_kind,
      "preview content kind",
      MAX_IDENTIFIER_LENGTH,
    ),
    confidence: enumString(
      status.confidence,
      VERIFICATION_CONFIDENCE,
      "preview confidence",
    ),
    error_code:
      status.error_code === null
        ? null
        : boundedString(
            status.error_code,
            "preview error code",
            MAX_IDENTIFIER_LENGTH,
          ),
    error_message:
      status.error_message === null
          ? null
          : boundedString(
              status.error_message,
              "preview error message",
              MAX_EFFECT_NAME_LENGTH,
            ),
    write_disposition: enumString(
      status.write_disposition,
      ["not_started", "may_have_started", "completed", "unknown"],
      "preview write disposition",
    ),
    persist_default: booleanValue(
      status.persist_default,
      "preview persist default",
    ),
    scene_id:
      status.scene_id === null
        ? null
        : integerValue(
            status.scene_id,
            "preview scene ID",
            0,
            0xffff,
          ),
    effect_id:
      status.effect_id === null
        ? null
        : integerValue(
            status.effect_id,
            "preview effect ID",
            0,
            0xffff,
          ),
    default_action:
      status.default_action === null
        ? null
        : enumString(
            status.default_action,
            ["set", "reset"],
            "preview default action",
          ),
  };
}

export function decodePreviewHealthStatus(
  value: unknown,
): PreviewHealthStatus {
  const status = objectValue(value, "preview health");
  return {
    config_entry_id: boundedString(
      status.config_entry_id,
      "preview health config entry ID",
      MAX_IDENTIFIER_LENGTH,
    ),
    revision: integerValue(
      status.revision,
      "preview health revision",
      0,
      MAX_SAFE_REVISION,
    ),
    phase: enumString(
      status.phase,
      ["healthy", "checking", "degraded"],
      "preview health phase",
    ),
    incident_id:
      status.incident_id === null
        ? null
        : boundedString(
            status.incident_id,
            "preview health incident ID",
            MAX_IDENTIFIER_LENGTH,
          ),
    error_code:
      status.error_code === null
        ? null
        : boundedString(
            status.error_code,
            "preview health error code",
            MAX_IDENTIFIER_LENGTH,
          ),
    error_message:
      status.error_message === null
        ? null
        : boundedString(
            status.error_message,
            "preview health error message",
            MAX_EFFECT_NAME_LENGTH,
          ),
    write_disposition: enumString(
      status.write_disposition,
      ["not_started", "may_have_started", "completed", "unknown"],
      "preview health write disposition",
    ),
    checked_at: timestampString(
      status.checked_at,
      "preview health checked time",
    ),
  };
}

export function decodeSceneCatalogue(value: unknown): SceneCatalogue {
  assertBoundedJson(
    value,
    "scene catalogue",
    MAX_CATALOGUE_BYTES,
    MAX_CATALOGUE_JSON_NODES,
  );
  const catalogue = objectValue(value, "scene catalogue");
  return {
    schema_version: integerValue(
      catalogue.schema_version,
      "scene catalogue schema",
      1,
    ),
    sku: boundedString(catalogue.sku, "scene catalogue SKU", MAX_IDENTIFIER_LENGTH),
    enabled: booleanValue(catalogue.enabled, "scene catalogue enabled"),
    categories: arrayValue(
      catalogue.categories,
      "scene categories",
      MAX_JSON_COLLECTION_ITEMS,
    ).map((item, index) => {
      const category = objectValue(item, `scene categories[${index}]`);
      return {
        id: integerValue(category.id, "scene category ID", 0, 65_535),
        name: boundedString(
          category.name,
          "scene category name",
          MAX_EFFECT_NAME_LENGTH,
        ),
      };
    }),
    scenes: arrayValue(
      catalogue.scenes,
      "scenes",
      MAX_SCENE_CATALOGUE_ENTRIES,
    ).map(decodeSceneSummary),
  };
}

export function decodeSceneDetail(value: unknown): SceneDetail {
  const detail = objectValue(value, "scene detail");
  assertBoundedJson(
    {
      scene: detail.scene,
      content: detail.content,
      catalogue_content: detail.catalogue_content,
    },
    "scene detail",
    MAX_EFFECT_DOCUMENT_BYTES * 2,
  );
  const content = decodeEffectContent(detail.content);
  const catalogueContent = decodeEffectContent(detail.catalogue_content);
  if (
    content.kind !== "scene_builtin" &&
    content.kind !== "scene_palette" &&
    content.kind !== "scene_layered"
  ) {
    invalid("scene detail content is unsupported");
  }
  if (
    catalogueContent.kind !== "scene_builtin" &&
    catalogueContent.kind !== "scene_palette" &&
    catalogueContent.kind !== "scene_layered"
  ) {
    invalid("scene detail catalogue content is unsupported");
  }
  const scene = decodeSceneSummary(detail.scene);
  return {
    scene,
    content,
    catalogue_content: catalogueContent,
    has_default: booleanValue(detail.has_default, "scene stored default"),
  };
}

export function decodeCatalogueTemplateDefaultDetail(
  value: unknown,
): CatalogueTemplateDefaultDetail {
  const detail = objectValue(value, "catalogue-template default detail");
  assertBoundedJson(
    {
      content: detail.content,
      catalogue_content: detail.catalogue_content,
    },
    "catalogue-template default detail",
    MAX_EFFECT_DOCUMENT_BYTES * 2,
  );
  const content = decodeEffectContent(detail.content);
  const catalogueContent = decodeEffectContent(detail.catalogue_content);
  const supported = new Set([
    "h617a_painted",
    "h617a_single",
    "palette_diy",
    "music_profile",
    "video_profile",
  ]);
  if (!supported.has(content.kind) || !supported.has(catalogueContent.kind)) {
    invalid("catalogue-template default content is unsupported");
  }
  return {
    template_id: boundedString(
      detail.template_id,
      "catalogue-template ID",
      MAX_IDENTIFIER_LENGTH,
    ),
    content: content as CatalogueTemplateDefaultDetail["content"],
    catalogue_content:
      catalogueContent as CatalogueTemplateDefaultDetail["catalogue_content"],
    has_default: booleanValue(
      detail.has_default,
      "catalogue-template stored default",
    ),
  };
}

export function decodeEffectContent(value: unknown): EffectContent {
  assertBoundedJson(value, "effect content", MAX_EFFECT_DOCUMENT_BYTES);
  const content = objectValue(value, "effect content");
  const kind = boundedString(
    content.kind,
    "effect content kind",
    MAX_IDENTIFIER_LENGTH,
  );
  switch (kind) {
    case "h617a_painted":
      const paintedSegments = arrayValue(
        content.segments,
        "painted segments",
        15,
      );
      if (paintedSegments.length !== 15) {
        invalid("painted effect must contain exactly 15 segments");
      }
      return {
        kind,
        effect: enumString(
          content.effect,
          [
            "cycle",
            "clockwise",
            "counter_clockwise",
            "twinkle",
            "gradient",
            "breathe",
          ],
          "painted effect",
        ),
        speed: integerValue(content.speed, "painted speed", 0, 100),
        brightness: integerValue(
          content.brightness,
          "painted brightness",
          0,
          100,
        ),
        segments: paintedSegments.map((segment, index) =>
          segment === null
            ? null
            : rgbValue(segment, `painted segments[${index}]`),
        ),
      };
    case "h617a_single":
      return {
        kind,
        family: integerValue(content.family, "Single family", 0, 254),
        variant: integerValue(content.variant, "Single variant", 0, 255),
        speed: integerValue(content.speed, "Single speed", 0, 100),
        palette: paletteValue(content.palette, "Single palette", 8),
      };
    case "h617a_multi":
      return {
        kind,
        effects: arrayValue(content.effects, "Multi effects", 4).map(
          (item, index) => {
            const effect = objectValue(item, `Multi effects[${index}]`);
            return {
              family: integerValue(effect.family, "Multi family", 0, 254),
              variant: integerValue(effect.variant, "Multi variant", 0, 255),
            };
          },
        ),
        speed: integerValue(content.speed, "Multi speed", 0, 100),
        palette: paletteValue(content.palette, "Multi palette", 8),
      };
    case "palette_diy":
      return {
        kind,
        model: enumString(
          content.model,
          MODEL_SKUS,
          "palette DIY model",
        ) as ModelSku,
        family: integerValue(content.family, "palette DIY family", 0, 255),
        variant: integerValue(content.variant, "palette DIY variant", 0, 255),
        speed: integerValue(content.speed, "palette DIY speed", 0, 100),
        palette: paletteValue(content.palette, "palette DIY palette", 8),
      } satisfies PaletteDiyEffectContent;
    case "music_profile":
      return {
        kind,
        model: enumString(
          content.model,
          MODEL_SKUS,
          "music profile model",
        ) as ModelSku,
        mode: boundedString(
          content.mode,
          "music profile mode",
          MAX_IDENTIFIER_LENGTH,
        ),
        sensitivity: integerValue(
          content.sensitivity,
          "music profile sensitivity",
          0,
          100,
        ),
        colour: nullableRgbValue(content.colour, "music profile colour"),
        calm: nullableBooleanValue(content.calm, "music profile calm"),
        parameters: boundedRecord(
          content.parameters,
          "music profile parameters",
        ) as JsonObject,
      } satisfies MusicProfileContent;
    case "video_profile":
      return {
        kind,
        model: enumString(content.model, ["H6199"], "video profile model"),
        mode: enumString(content.mode, VIDEO_MODE_IDS, "video profile mode"),
        full_screen: booleanValue(
          content.full_screen,
          "video profile full-screen flag",
        ),
        saturation: integerValue(
          content.saturation,
          "video profile saturation",
          0,
          100,
        ),
        sound_effects: booleanValue(
          content.sound_effects,
          "video profile sound-effects flag",
        ),
        sound_effects_softness: integerValue(
          content.sound_effects_softness,
          "video profile sound-effects softness",
          1,
          100,
        ),
        white_balance_position: integerValue(
          content.white_balance_position,
          "video profile white-balance position",
          1,
          20,
        ),
        relative_brightness: relativeBrightnessValue(
          content.relative_brightness,
          "video profile relative brightness",
        ),
        blank_screen: booleanValue(
          content.blank_screen,
          "video profile blank-screen flag",
        ),
      } satisfies VideoProfileContent;
    case "advanced":
      return {
        kind,
        layers: layerArray(content.layers, "Advanced layers"),
      } satisfies AdvancedContent;
    case "workshop": {
      const effect = objectValue(content.effect, "Workshop effect");
      return {
        kind,
        model: enumString(
          content.model,
          MODEL_SKUS,
          "Workshop model",
        ) as ModelSku,
        template: boundedString(
          content.template,
          "Workshop template",
          MAX_IDENTIFIER_LENGTH,
        ),
        effect: {
          layers: layerArray(effect.layers, "Workshop layers"),
        },
        raw_param: hexString(
          content.raw_param,
          "Workshop source parameter",
        ),
        trailing_padding: integerValue(
          content.trailing_padding,
          "Workshop trailing padding",
          0,
          SCENE_TRAILING_PADDING_MAX,
        ),
      } satisfies WorkshopContent;
    }
    case "scene_builtin":
      return {
        kind,
        template: catalogueRef(content.template, "scene template"),
        speed_index: nullableInteger(
          content.speed_index,
          "scene speed index",
          0,
          255,
        ),
      } satisfies BuiltinSceneContent;
    case "scene_palette":
      return paletteSceneContent(content);
    case "scene_layered": {
      const effect = objectValue(content.effect, "layered scene effect");
      const trailingPadding = sceneTrailingPadding(
        content.trailing_padding,
        "layered scene trailing padding",
      );
      return {
        kind,
        template: catalogueRef(content.template, "layered scene template"),
        effect: {
          layers: layerArray(effect.layers, "layered scene layers"),
        },
        speed_index: nullableInteger(
          content.speed_index,
          "layered scene speed index",
          0,
          255,
        ),
        raw_param: hexString(content.raw_param, "layered scene raw parameter"),
        ...(trailingPadding === undefined
          ? {}
          : { trailing_padding: trailingPadding }),
      } satisfies LayeredSceneContent;
    }

    default: {
      const { kind: _kind, ...body } = content;
      return {
        kind: "opaque",
        source_kind: kind,
        body,
      };
    }
  }
}

function sceneTrailingPadding(
  value: unknown,
  label: string,
): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  return integerValue(value, label, 0, SCENE_TRAILING_PADDING_MAX);
}

function paletteSceneContent(
  content: Record<string, unknown>,
): PaletteSceneContent {
  const layoutValue = integerValue(
    content.layout,
    "palette scene layout",
    0,
    1,
  );
  const layout: 0 | 1 = layoutValue === 0 ? 0 : 1;
  const steps = arrayValue(
    content.steps,
    "palette scene steps",
    255,
  ).map((item, index) => {
    const step = objectValue(item, `palette scene steps[${index}]`);
    const inlineColour =
      layout === 0
        ? (() => {
            if (step.inline_colour !== null) {
              invalid(
                `palette scene steps[${index}].inline_colour must be null for layout 0`,
              );
            }
            return null;
          })()
        : rgbValue(
            step.inline_colour,
            `palette scene steps[${index}].inline_colour`,
          );
    return {
      value: integerValue(
        step.value,
        `palette scene steps[${index}].value`,
        0,
        65_535,
      ),
      colour: rgbValue(
        step.colour,
        `palette scene steps[${index}].colour`,
      ),
      inline_colour: inlineColour,
    };
  });
  const palette = paletteValue(
    content.palette,
    "palette scene shared palette",
    255,
    true,
  );
  if (layout === 1 && palette.length !== 0) {
    invalid("palette scene layout 1 must not have a shared palette");
  }
  let configFlags: number | undefined;
  if (content.config_flags !== undefined) {
    configFlags = integerValue(content.config_flags, "palette scene config flags", 0, 255);
    if (configFlags & ~PALETTE_CONFIG_RESERVED_MASK) {
      invalid("palette scene config flags must only set reserved config bits");
    }
  }
  const trailingPadding = sceneTrailingPadding(
    content.trailing_padding,
    "palette scene trailing padding",
  );
  return {
    kind: "scene_palette",
    template: catalogueRef(content.template, "palette scene template"),
    layout,
    brightness_flag: booleanValue(
      content.brightness_flag,
      "palette scene brightness flag",
    ),
    steps,
    palette,
    speed_index: nullableInteger(
      content.speed_index,
      "palette scene speed index",
      0,
      255,
    ),
    ...(configFlags === undefined ? {} : { config_flags: configFlags }),
    ...(trailingPadding === undefined
      ? {}
      : { trailing_padding: trailingPadding }),
  };
}

export function effectContentToWire(
  content: EffectContent,
): WireEffectContent {
  if (content.kind !== "opaque") {
    return content;
  }
  assertBoundedJson(content.body, "opaque content", MAX_EFFECT_DOCUMENT_BYTES);
  return {
    ...content.body,
    kind: boundedString(
      content.source_kind,
      "opaque source kind",
      MAX_IDENTIFIER_LENGTH,
    ),
  };
}

export function decodeSceneSummary(value: unknown): SceneSummary {
  const scene = objectValue(value, "scene");
  const parameterKind = stringValue(
    scene.parameter_kind,
    "scene parameter kind",
  );
  if (
    parameterKind !== "none" &&
    parameterKind !== "palette" &&
    parameterKind !== "layers" &&
    parameterKind !== "opaque"
  ) {
    invalid("scene parameter kind is invalid");
  }
  const speed =
    scene.speed === null
      ? null
      : (() => {
          const raw = objectValue(scene.speed, "scene speed");
          return {
            option_count: integerValue(
              raw.option_count,
              "scene speed option count",
              1,
              256,
            ),
            default_index: integerValue(
              raw.default_index,
              "scene default speed",
              0,
              255,
            ),
          };
        })();
  return {
    scene_id: integerValue(scene.scene_id, "scene ID", 0, 65_535),
    effect_id: integerValue(scene.effect_id, "scene effect ID", 0, 65_535),
    category_id: integerValue(scene.category_id, "scene category ID", 0, 65_535),
    category: boundedString(
      scene.category,
      "scene category",
      MAX_EFFECT_NAME_LENGTH,
    ),
    name: boundedString(scene.name, "scene name", MAX_EFFECT_NAME_LENGTH),
    variant: boundedStringAllowEmpty(
      scene.variant,
      "scene variant",
      MAX_IDENTIFIER_LENGTH,
    ),
    display_name: boundedString(
      scene.display_name,
      "scene display name",
      MAX_EFFECT_NAME_LENGTH,
    ),
    scene_type: integerValue(scene.scene_type, "scene type", 0, 255),
    parameter_kind: parameterKind,
    speed,
  };
}

function layerArray(value: unknown, name: string): EffectLayer[] {
  return arrayValue(value, name, 255).map((item, index) =>
    layerValue(item, `${name}[${index}]`),
  );
}

function layerValue(value: unknown, name: string): EffectLayer {
  const layer = objectValue(value, name);
  const area = objectValue(layer.area, `${name}.area`);
  const selection = objectValue(layer.selection, `${name}.selection`);
  const distribution = objectValue(
    layer.distribution,
    `${name}.distribution`,
  );
  return {
    area: {
      start_tenths: integerValue(
        area.start_tenths,
        `${name}.area.start_tenths`,
        0,
        15,
      ),
      width_tenths: integerValue(
        area.width_tenths,
        `${name}.area.width_tenths`,
        0,
        15,
      ),
    },
    selection: {
      type: byteValue(selection.type, `${name}.selection.type`),
      param_1: byteValue(selection.param_1, `${name}.selection.param_1`),
      param_2: byteValue(selection.param_2, `${name}.selection.param_2`),
    },
    brightness_gradient: booleanValue(
      layer.brightness_gradient,
      `${name}.brightness_gradient`,
    ),
    brightness_patterns: arrayValue(
      layer.brightness_patterns,
      `${name}.brightness_patterns`,
      255,
    ).map((item, index) => {
      const pattern = objectValue(
        item,
        `${name}.brightness_patterns[${index}]`,
      );
      return {
        scope_high: byteValue(pattern.scope_high, "brightness scope high"),
        scope_low: byteValue(pattern.scope_low, "brightness scope low"),
        order: byteValue(pattern.order, "brightness order"),
        change_speed: byteValue(pattern.change_speed, "brightness change speed"),
        brightest_retention: byteValue(
          pattern.brightest_retention,
          "brightest retention",
        ),
        darkest_retention: byteValue(
          pattern.darkest_retention,
          "darkest retention",
        ),
      };
    }),
    distribution: {
      method: integerValue(
        distribution.method,
        `${name}.distribution.method`,
        0,
        127,
      ),
      backwards: booleanValue(
        distribution.backwards,
        `${name}.distribution.backwards`,
      ),
    },
    colour_speed: byteValue(layer.colour_speed, `${name}.colour_speed`),
    colour_retention: byteValue(
      layer.colour_retention,
      `${name}.colour_retention`,
    ),
    palette: paletteValue(layer.palette, `${name}.palette`, 255, true),
    selected_movement: movementValue(
      layer.selected_movement,
      `${name}.selected_movement`,
    ),
    overall_movement: movementValue(
      layer.overall_movement,
      `${name}.overall_movement`,
    ),
    priority: byteValue(layer.priority, `${name}.priority`),
    unknown_flags: unknownFlagsValue(
      layer.unknown_flags,
      LAYER_UNKNOWN_FLAGS_MASK,
      `${name}.unknown_flags`,
    ),
    excess: hexString(layer.excess, `${name}.excess`),
  };
}

function movementValue(value: unknown, name: string) {
  const movement = objectValue(value, name);
  return {
    enabled: booleanValue(movement.enabled, `${name}.enabled`),
    enter_exit: booleanValue(movement.enter_exit, `${name}.enter_exit`),
    direction: integerValue(movement.direction, `${name}.direction`, 0, 3),
    distance: byteValue(movement.distance, `${name}.distance`),
    speed: byteValue(movement.speed, `${name}.speed`),
    unknown_flags: unknownFlagsValue(
      movement.unknown_flags,
      MOVEMENT_UNKNOWN_FLAGS_MASK,
      `${name}.unknown_flags`,
    ),
  };
}

function catalogueRef(value: unknown, name: string) {
  const reference = objectValue(value, name);
  return {
    sku: boundedString(reference.sku, `${name}.sku`, MAX_IDENTIFIER_LENGTH),
    scene_id: integerValue(reference.scene_id, `${name}.scene_id`, 0, 65_535),
    effect_id: integerValue(
      reference.effect_id,
      `${name}.effect_id`,
      0,
      65_535,
    ),
    catalogue_schema_version: integerValue(
      reference.catalogue_schema_version,
      `${name}.catalogue_schema_version`,
      1,
      MAX_SAFE_REVISION,
    ),
  };
}

function paletteValue(
  value: unknown,
  name: string,
  maximum: number,
  allowEmpty = false,
): RGB[] {
  const palette = arrayValue(value, name, maximum);
  if (!allowEmpty && palette.length === 0) {
    invalid(`${name} must not be empty`);
  }
  return palette.map((colour, index) =>
    rgbValue(colour, `${name}[${index}]`),
  );
}

function rgbValue(value: unknown, name: string): RGB {
  const channels = arrayValue(value, name, 3);
  if (channels.length !== 3) {
    invalid(`${name} must contain three channels`);
  }
  return channels.map((channel) =>
    integerValue(channel, `${name} channel`, 0, 255),
  ) as RGB;
}

function nullableRgbValue(value: unknown, name: string): RGB | null {
  return value === null ? null : rgbValue(value, name);
}

function nullableBooleanValue(value: unknown, name: string): boolean | null {
  return value === null ? null : booleanValue(value, name);
}

function relativeBrightnessValue(
  value: unknown,
  name: string,
): RelativeBrightness {
  const brightness = objectValue(value, name);
  return {
    left: integerValue(brightness.left, `${name}.left`, 1, 100),
    top: integerValue(brightness.top, `${name}.top`, 1, 100),
    right: integerValue(brightness.right, `${name}.right`, 1, 100),
    bottom: integerValue(brightness.bottom, `${name}.bottom`, 1, 100),
  };
}

function boundedRecord(value: unknown, name: string): Record<string, unknown> {
  assertBoundedJson(value, name, MAX_EFFECT_DOCUMENT_BYTES);
  return objectValue(value, name);
}

function stringArray(
  value: unknown,
  name: string,
  maximumItemLength: number,
): string[] {
  if (!Array.isArray(value)) {
    invalid(`${name} must be an array`);
  }
  return value.map((item, index) =>
    boundedString(item, `${name}[${index}]`, maximumItemLength),
  );
}


function decodeOrigin(value: unknown): LibraryItem["origin"] {
  const origin = objectValue(value, "effect origin");
  return {
    kind: boundedString(origin.kind, "effect origin kind", MAX_IDENTIFIER_LENGTH),
    source_id: nullableBoundedString(origin.source_id, "effect origin source ID"),
  };
}


function contentHash(value: unknown, name: string): string {
  const hash = hexString(value, name);
  if (hash.length !== 64) {
    invalid(`${name} must contain 64 hexadecimal characters`);
  }
  return hash;
}


function nullableBoundedString(value: unknown, name: string): string | null {
  return value === null
    ? null
    : boundedString(value, name, MAX_IDENTIFIER_LENGTH);
}

function timestampString(value: unknown, name: string): string {
  const timestamp = boundedString(value, name, MAX_TIMESTAMP_LENGTH);
  if (
    !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp) ||
    Number.isNaN(Date.parse(timestamp))
  ) {
    invalid(`${name} must be an ISO 8601 timestamp with a UTC offset`);
  }
  return timestamp;
}

function knownModelSku(value: unknown): ModelSku | undefined {
  return typeof value === "string" && MODEL_SKUS.includes(value as ModelSku)
    ? (value as ModelSku)
    : undefined;
}

function revisionValue(
  value: unknown,
  name: string,
  minimum: number,
): number {
  return integerValue(value, name, minimum, MAX_SAFE_REVISION);
}

function unknownFlagsValue(value: unknown, mask: number, name: string): number {
  const flags = byteValue(value, name);
  if (flags & ~mask) {
    invalid(`${name} must only set reserved bits, not bits explicit fields carry`);
  }
  return flags;
}

export function isCompatibleEditorInfo(info: EditorApiInfo): boolean {
  return (
    info.api_version === EDITOR_API_VERSION &&
    info.effect_schema_version === EFFECT_SCHEMA_VERSION &&
    info.compiler_version === EFFECT_COMPILER_VERSION
  );
}
