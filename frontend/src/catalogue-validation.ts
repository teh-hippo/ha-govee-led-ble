import {
  arrayValue,
  assertBoundedJson,
  booleanValue,
  boundedString,
  capabilityValue,
  enumString,
  exactInteger,
  integerValue,
  invalid,
  MAX_JSON_COLLECTION_ITEMS,
  objectValue,
  requireUnique,
} from "./payload-validation";
import type {
  CatalogueTemplate,
  CustomEffectCatalogue,
  EffectContent,
  EffectStudioCatalogue,
  EffectStudioModeOption,
  ModelEffectCatalogue,
  MusicSettings,
  PaintedContent,
  PaintedEffectTemplate,
  PaletteDiyFamily,
  ReleaseWorkflowCapability,
  ReleaseWorkflowId,
  VideoProfileSetting,
  VideoControls,
  WorkshopTemplate,
} from "./types";
import {
  CUSTOM_CATALOGUE_SCHEMA_VERSION,
  LEGACY_CUSTOM_CATALOGUE_SKU,
  MAX_CATALOGUE_BYTES,
  MAX_CATALOGUE_JSON_NODES,
  MAX_EFFECT_NAME_LENGTH,
  MAX_IDENTIFIER_LENGTH,
} from "./validation-constants";

const RELEASE_WORKFLOW_IDS = [
  "native_scenes",
  "edited_palette_scenes",
  "layered_scenes",
  "painted",
  "single",
  "multi",
  "native_music",
  "video",
  "palette_diy",
  "advanced",
  "workshop",
] as const;
const RELEASE_WORKFLOW_APPLICATIONS = [
  "studio",
  "home_assistant",
  "planned",
] as const;
function decodeVideoControls(value: unknown): VideoControls {
  const controls = objectValue(value, "video controls");
  const white = objectValue(controls.white_balance, "white balance control");
  return {
    white_balance: {
      representation: enumString(white.representation, ["position", "scalar"] as const, "white balance representation"),
      minimum: integerValue(white.minimum, "white balance minimum", 0, 255),
      maximum: integerValue(white.maximum, "white balance maximum", 0, 255),
      default: integerValue(white.default, "white balance default", 0, 255),
    },
    brightness_zones: arrayValue(controls.brightness_zones, "brightness zones", 6).map(zone =>
      enumString(zone, ["left", "top", "right", "bottom", "strip_left", "strip_right"] as const, "brightness zone")),
  };
}

const VIDEO_PROFILE_SETTINGS = [
  "capture_region",
  "saturation",
  "sound_effects",
  "white_balance",
  "relative_brightness",
  "blank_screen",
] as const;
export function decodeCustomCataloguePayload(
  value: unknown,
  decodeContent: (value: unknown) => EffectContent,
): CustomEffectCatalogue {
  assertBoundedJson(
    value,
    "custom-effect catalogue",
    MAX_CATALOGUE_BYTES,
    MAX_CATALOGUE_JSON_NODES,
  );
  const catalogue = objectValue(value, "custom-effect catalogue");
  const models = decodeModelCatalogues(catalogue.models, decodeContent);
  const legacy = decodeModelEffectCatalogue(
    catalogue,
    "custom-effect catalogue",
    LEGACY_CUSTOM_CATALOGUE_SKU,
    decodeContent,
  );
  if (
    JSON.stringify(legacy) !==
    JSON.stringify(models[LEGACY_CUSTOM_CATALOGUE_SKU])
  ) {
    throw new Error(
      `Malformed Effect Studio server payload: legacy custom-effect catalogue view does not match models.${LEGACY_CUSTOM_CATALOGUE_SKU}.`,
    );
  }
  exactInteger(
    catalogue.schema_version,
    CUSTOM_CATALOGUE_SCHEMA_VERSION,
    "catalogue schema",
  );
  const decoded: EffectStudioCatalogue = {
    ...legacy,
    schema_version: CUSTOM_CATALOGUE_SCHEMA_VERSION,
    sku: LEGACY_CUSTOM_CATALOGUE_SKU,
    models,
  };
  return decoded;
}

function decodeModelCatalogues(
  value: unknown,
  decodeContent: (value: unknown) => EffectContent,
): Record<string, ModelEffectCatalogue> {
  const models = objectValue(value, "custom-effect catalogue models");
  if (!Object.hasOwn(models, LEGACY_CUSTOM_CATALOGUE_SKU)) {
    throw new Error(
      `Malformed Effect Studio server payload: missing catalogue model ${LEGACY_CUSTOM_CATALOGUE_SKU}.`,
    );
  }
  return Object.fromEntries(
    Object.entries(models).map(([key, catalogue]) => {
      const model = boundedString(
        key,
        "catalogue model key",
        MAX_IDENTIFIER_LENGTH,
      );
      return [
        model,
        decodeModelEffectCatalogue(
          catalogue,
          `catalogue model ${model}`,
          model,
          decodeContent,
        ),
      ];
    }),
  );
}

function decodeModelEffectCatalogue(
  value: unknown,
  name: string,
  expectedSku: string,
  decodeContent: (value: unknown) => EffectContent,
): ModelEffectCatalogue {
  const catalogue = objectValue(value, name);
  const limits = objectValue(catalogue.limits, `${name} limits`);
  const supports = objectValue(
    catalogue.supports,
    `${name} support capabilities`,
  );
  const apply = objectValue(catalogue.apply, `${name} Apply capabilities`);
  const sku = boundedString(
    catalogue.sku,
    `${name} SKU`,
    MAX_IDENTIFIER_LENGTH,
  );
  if (sku !== expectedSku) {
    throw new Error(
      `Malformed Effect Studio server payload: ${name} is keyed as ${expectedSku} but declares ${sku}.`,
    );
  }
  const musicSensitivityMinimum = integerValue(
    limits.music_sensitivity_min,
    `${name} minimum music sensitivity`,
    0,
    100,
  );
  const musicSensitivityMaximum = integerValue(
    limits.music_sensitivity_max,
    `${name} maximum music sensitivity`,
    0,
    100,
  );
  if (musicSensitivityMinimum > musicSensitivityMaximum) {
    invalid(`${name} music sensitivity limits are inverted`);
  }
  for (const field of ["palette", "speed", "brightness"]) {
    if (Number(limits[`${field}_min`]) > Number(limits[`${field}_max`])) {
      invalid(`${name} ${field} limits are inverted`);
    }
  }
  return {
    sku,
    painted_effects: decodePaintedEffectTemplates(
      catalogue.painted_effects,
      `${name} painted-effect templates`,
    ),
    effects: decodePaletteDiyFamilies(
      catalogue.effects,
      `${name} custom-effect templates`,
    ),
    music_modes: decodeModeOptions(
      catalogue.music_modes,
      `${name} music modes`,
    ),
    music_settings: decodeMusicSettings(catalogue.music_settings),
    video_modes: decodeModeOptions(
      catalogue.video_modes,
      `${name} video modes`,
    ),
    video_settings: decodeVideoSettings(
      catalogue.video_settings,
      `${name} video settings`,
    ),
    ...(catalogue.video_controls === undefined ? {} : {video_controls: decodeVideoControls(catalogue.video_controls)}),
    templates: decodeCatalogueTemplates(
      catalogue.templates,
      `${name} catalogue templates`,
      expectedSku,
      decodeContent,
    ),
    workshop_templates: decodeWorkshopTemplates(
      catalogue.workshop_templates,
      `${name} Workshop templates`,
      expectedSku,
      decodeContent,
    ),
    workflows: decodeReleaseWorkflows(
      catalogue.workflows,
      `${name} release workflows`,
    ),
    supports: {
      multi: capabilityValue(supports.multi, `${name} Multi support`),
      advanced: capabilityValue(
        supports.advanced,
        `${name} advanced support`,
      ),
      workshop: capabilityValue(
        supports.workshop,
        `${name} Workshop support`,
      ),
    },
    limits: {
      speed_min: integerValue(limits.speed_min, `${name} minimum speed`, 0, 100),
      speed_max: integerValue(limits.speed_max, `${name} maximum speed`, 0, 100),
      brightness_min: integerValue(limits.brightness_min, `${name} minimum brightness`, 0, 100),
      brightness_max: integerValue(limits.brightness_max, `${name} maximum brightness`, 0, 100),
      palette_min: integerValue(
        limits.palette_min,
        `${name} minimum palette`,
        1,
        8,
      ),
      palette_max: integerValue(
        limits.palette_max,
        `${name} maximum palette`,
        1,
        8,
      ),
      multi_max: integerValue(
        limits.multi_max,
        `${name} maximum Multi effects`,
        1,
        4,
      ),
      music_sensitivity_min: musicSensitivityMinimum,
      music_sensitivity_max: musicSensitivityMaximum,
    },
    apply: {
      painted: capabilityValue(
        apply.painted,
        `${name} Painted Apply capability`,
      ),
      single: capabilityValue(
        apply.single,
        `${name} Single Apply capability`,
      ),
      multi: capabilityValue(apply.multi, `${name} Multi Apply capability`),
      palette_diy: capabilityValue(
        apply.palette_diy,
        `${name} palette DIY Apply capability`,
      ),
      workshop: capabilityValue(
        apply.workshop,
        `${name} Workshop Apply capability`,
      ),
    },
  };
}


function decodeMusicSettings(value: unknown): Record<string, MusicSettings> {
  return Object.fromEntries(Object.entries(objectValue(value, "music settings")).map(([mode, raw]) => {
    const settings = objectValue(raw, "music mode settings");
    const parameters = objectValue(settings.parameters, "music parameters");
    return [mode, {
      style: booleanValue(settings.style, "music style"),
      calm_default: booleanValue(settings.calm_default, "music default style"),
      colour: booleanValue(settings.colour, "music colour"),
      evidence: settings.evidence === null ? null : boundedString(settings.evidence, "music evidence", 1024),
      palette_size: integerValue(settings.palette_size, "music palette size", 0, 255),
      parameters: Object.fromEntries(Object.entries(parameters).map(([key, rawSpec]) => {
        const spec = objectValue(rawSpec, "music parameter");
        const kind = enumString(spec.kind, ["number", "switch", "select"] as const, "music parameter kind");
        const min = integerValue(spec.min, "music minimum", 0, 255);
        const max = integerValue(spec.max, "music maximum", min, 255);
        const options = arrayValue(spec.options, "music options", 255).map((option) => boundedString(option, "music option", 128));
        const defaultValue = kind === "number" ? integerValue(spec.default, "music default", min, max)
          : kind === "switch" ? booleanValue(spec.default, "music default")
          : enumString(spec.default, options, "music default");
        return [key, {kind, default: defaultValue, min, max, options}];
      })),
    }];
  }));
}

function decodeVideoSettings(
  value: unknown,
  name: string,
): VideoProfileSetting[] {
  const settings = arrayValue(value, name, VIDEO_PROFILE_SETTINGS.length).map(
    (setting, index) =>
      enumString(
        setting,
        VIDEO_PROFILE_SETTINGS,
        `${name}[${index}]`,
      ) as VideoProfileSetting,
  );
  requireUnique(settings, (setting) => setting, name);
  return settings;
}


function decodeCatalogueTemplates(
  value: unknown,
  name: string,
  model: string,
  decodeContent: (value: unknown) => EffectContent,
): CatalogueTemplate[] {
  const templates = arrayValue(value, name, MAX_JSON_COLLECTION_ITEMS).map(
    (item, index): CatalogueTemplate => {
      const template = objectValue(item, `${name}[${index}]`);
      const content = decodeContent(template.content);
      if (
        content.kind !== "h617a_painted" &&
        content.kind !== "h617a_single" &&
        content.kind !== "palette_diy" &&
        content.kind !== "music_profile" &&
        content.kind !== "video_profile"
      ) {
        invalid(`${name}[${index}] content is not a supported built-in template`);
      }
      if (
        "model" in content &&
        content.model !== model
      ) {
        invalid(`${name}[${index}] content does not target ${model}`);
      }
      return {
        id: boundedString(
          template.id,
          `${name}[${index}] ID`,
          MAX_IDENTIFIER_LENGTH,
        ),
        label: boundedString(
          template.label,
          `${name}[${index}] label`,
          MAX_EFFECT_NAME_LENGTH,
        ),
        category: enumString(
          template.category,
          ["single-layer", "music", "video"],
          `${name}[${index}] category`,
        ) as CatalogueTemplate["category"],
        content,
      };
    },
  );
  requireUnique(templates, (template) => template.id, `${name} IDs`);
  return templates;
}

function decodeReleaseWorkflows(
  value: unknown,
  name: string,
): ReleaseWorkflowCapability[] {
  const workflows = arrayValue(value, name, RELEASE_WORKFLOW_IDS.length).map(
    (item, index): ReleaseWorkflowCapability => {
      const workflow = objectValue(item, `${name}[${index}]`);
      return {
        id: enumString(
          workflow.id,
          RELEASE_WORKFLOW_IDS,
          `${name}[${index}] ID`,
        ) as ReleaseWorkflowId,
        label: boundedString(
          workflow.label,
          `${name}[${index}] label`,
          MAX_EFFECT_NAME_LENGTH,
        ),
        content_kind: boundedString(
          workflow.content_kind,
          `${name}[${index}] content kind`,
          MAX_IDENTIFIER_LENGTH,
        ),
        application: enumString(
          workflow.application,
          RELEASE_WORKFLOW_APPLICATIONS,
          `${name}[${index}] application`,
        ) as ReleaseWorkflowCapability["application"],
      };
    },
  );
  requireUnique(workflows, (workflow) => workflow.id, `${name} IDs`);
  return workflows;
}

function decodePaintedEffectTemplates(
  value: unknown,
  name: string,
): PaintedEffectTemplate[] {
  const templates = arrayValue(
    value,
    name,
    MAX_JSON_COLLECTION_ITEMS,
  ).map((item, index) => {
    const effect = objectValue(item, `${name}[${index}]`);
    return {
      id: enumString(
        effect.id,
        [
          "cycle",
          "clockwise",
          "counter_clockwise",
          "twinkle",
          "gradient",
          "breathe",
        ],
        `${name} ID`,
      ) as PaintedContent["effect"],
      label: boundedString(
        effect.label,
        `${name} label`,
        MAX_EFFECT_NAME_LENGTH,
      ),
    };
  });
  requireUnique(templates, (template) => template.id, `${name} IDs`);
  return templates;
}

function decodePaletteDiyFamilies(
  value: unknown,
  name: string,
): PaletteDiyFamily[] {
  const effects = arrayValue(value, name, MAX_JSON_COLLECTION_ITEMS).map(
    (item, index) => {
      const effect = objectValue(item, `${name}[${index}]`);
      const variations = arrayValue(
        effect.variations,
        `${name}[${index}].variations`,
        MAX_JSON_COLLECTION_ITEMS,
      );
      if (variations.length === 0) {
        throw new Error(
          "Malformed Effect Studio server payload: custom-effect template has no variations.",
        );
      }
      const decoded: PaletteDiyFamily = {
        rate_min: integerValue(effect.rate_min, `${name} minimum rate`, 0, 100),
        rate_max: integerValue(effect.rate_max, `${name} maximum rate`, 0, 100),
        id: boundedString(
          effect.id,
          `${name}[${index}] ID`,
          MAX_IDENTIFIER_LENGTH,
        ),
        label: boundedString(
          effect.label,
          `${name}[${index}] label`,
          MAX_EFFECT_NAME_LENGTH,
        ),
        family: integerValue(
          effect.family,
          `${name}[${index}] family`,
          0,
          255,
        ),
        variations: variations.map((item, variationIndex) => {
          const variation = objectValue(
            item,
            `${name}[${index}].variations[${variationIndex}]`,
          );
          return {
            id: boundedString(
              variation.id,
              `${name}[${index}].variations[${variationIndex}] ID`,
              MAX_IDENTIFIER_LENGTH,
            ),
            label: boundedString(
              variation.label,
              `${name}[${index}].variations[${variationIndex}] label`,
              MAX_EFFECT_NAME_LENGTH,
            ),
            variant: integerValue(
              variation.variant,
              `${name}[${index}].variations[${variationIndex}] variant`,
              0,
              255,
            ),
          };
        }),
        supports_multi: booleanValue(
          effect.supports_multi,
          `${name}[${index}] Multi support`,
        ),
        rate: enumString(
          effect.rate,
          ["speed", "sensitivity"],
          `${name}[${index}] rate parameter`,
        ) as "speed" | "sensitivity",
        category: enumString(
          effect.category,
          ["single_layer"],
          `${name}[${index}] category`,
        ) as "single_layer",
      };
      requireUnique(
        decoded.variations,
        (variation) => variation.id,
        `${name}[${index}] variation IDs`,
      );
      if (decoded.rate_min > decoded.rate_max) invalid(`${name} rate limits are inverted`);
      requireUnique(decoded.variations, (variation) => String(variation.variant), `${name} variation values`);
      return decoded;
    },
  );
  requireUnique(effects, (effect) => effect.id, `${name} IDs`);
  requireUnique(effects, (effect) => String(effect.family), `${name} family values`);
  return effects;
}

function decodeModeOptions(
  value: unknown,
  name: string,
): EffectStudioModeOption[] {
  const modes = arrayValue(value, name, MAX_JSON_COLLECTION_ITEMS).map(
    (item, index) => {
      const mode = objectValue(item, `${name}[${index}]`);
      return {
        id: boundedString(
          mode.id,
          `${name}[${index}] ID`,
          MAX_IDENTIFIER_LENGTH,
        ),
        label: boundedString(
          mode.label,
          `${name}[${index}] label`,
          MAX_EFFECT_NAME_LENGTH,
        ),
      };
    },
  );
  requireUnique(modes, (mode) => mode.id, `${name} IDs`);
  return modes;
}

function decodeWorkshopTemplates(
  value: unknown,
  name: string,
  model: string,
  decodeContent: (value: unknown) => EffectContent,
): WorkshopTemplate[] {
  const templates = arrayValue(value, name, MAX_JSON_COLLECTION_ITEMS).map(
    (item, index): WorkshopTemplate => {
      const template = objectValue(item, `${name}[${index}]`);
      const content = decodeContent(template.content);
      if (content.kind !== "workshop" || content.model !== model) {
        invalid(`${name}[${index}] content does not target ${model}`);
      }
      return {
        id: boundedString(
          template.id,
          `${name}[${index}] ID`,
          MAX_IDENTIFIER_LENGTH,
        ),
        label: boundedString(
          template.label,
          `${name}[${index}] label`,
          MAX_EFFECT_NAME_LENGTH,
        ),
        content,
      };
    },
  );
  requireUnique(templates, (template) => template.id, `${name} IDs`);
  return templates;
}
