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
  ModelSku,
  PaintedContent,
  PaintedEffectTemplate,
  PaletteDiyFamily,
  ReleaseWorkflowCapability,
  ReleaseWorkflowId,
  WorkshopTemplate,
} from "./types";
import {
  CUSTOM_CATALOGUE_SCHEMA_VERSION,
  LEGACY_CUSTOM_CATALOGUE_SKU,
  MAX_CATALOGUE_BYTES,
  MAX_CATALOGUE_JSON_NODES,
  MAX_EFFECT_NAME_LENGTH,
  MAX_IDENTIFIER_LENGTH,
  MODEL_SKUS,
  isH617xModel,
  VIDEO_MODE_IDS,
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
const MODEL_RELEASE_WORKFLOWS: Record<ModelSku, readonly ReleaseWorkflowId[]> = {
  H6125: ["native_scenes"],
  H617A: [
    "native_scenes",
    "edited_palette_scenes",
    "layered_scenes",
    "painted",
    "single",
    "multi",
    "native_music",
    "advanced",
    "workshop",
  ],
  H617E: [
    "native_scenes",
    "edited_palette_scenes",
    "layered_scenes",
    "painted",
    "single",
    "multi",
    "native_music",
    "advanced",
    "workshop",
  ],
  H6199: [
    "native_scenes",
    "edited_palette_scenes",
    "layered_scenes",
    "palette_diy",
    "native_music",
    "video",
    "advanced",
    "workshop",
  ],
};

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
      "Malformed Effect Studio server payload: legacy custom-effect catalogue view does not match models.H617A.",
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
): Record<ModelSku, ModelEffectCatalogue> {
  const models = objectValue(value, "custom-effect catalogue models");
  const unexpected = Object.keys(models).filter(
    (key) => !MODEL_SKUS.includes(key as ModelSku),
  );
  if (unexpected.length > 0) {
    throw new Error(
      `Malformed Effect Studio server payload: unexpected catalogue models ${unexpected.join(", ")}.`,
    );
  }
  for (const sku of MODEL_SKUS) {
    if (!(sku in models)) {
      throw new Error(
        `Malformed Effect Studio server payload: missing catalogue model ${sku}.`,
      );
    }
  }
  return {
    H6125: decodeModelEffectCatalogue(
      models.H6125,
      "catalogue model H6125",
      "H6125",
      decodeContent,
    ),
    H617A: decodeModelEffectCatalogue(
      models.H617A,
      "catalogue model H617A",
      "H617A",
      decodeContent,
    ),
    H617E: decodeModelEffectCatalogue(
      models.H617E,
      "catalogue model H617E",
      "H617E",
      decodeContent,
    ),
    H6199: decodeModelEffectCatalogue(
      models.H6199,
      "catalogue model H6199",
      "H6199",
      decodeContent,
    ),
  };
}

function decodeModelEffectCatalogue(
  value: unknown,
  name: string,
  expectedSku: ModelSku,
  decodeContent: (value: unknown) => EffectContent,
): ModelEffectCatalogue {
  const catalogue = objectValue(value, name);
  const limits = objectValue(catalogue.limits, `${name} limits`);
  const supports = objectValue(
    catalogue.supports,
    `${name} support capabilities`,
  );
  const apply = objectValue(catalogue.apply, `${name} Apply capabilities`);
  const sku = enumString(catalogue.sku, MODEL_SKUS, `${name} SKU`) as ModelSku;
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
    video_modes: decodeModeOptions(
      catalogue.video_modes,
      `${name} video modes`,
      VIDEO_MODE_IDS,
    ),
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
      expectedSku,
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
      palette_min: integerValue(
        limits.palette_min,
        `${name} minimum palette`,
        1,
        255,
      ),
      palette_max: integerValue(
        limits.palette_max,
        `${name} maximum palette`,
        1,
        255,
      ),
      multi_max: integerValue(
        limits.multi_max,
        `${name} maximum Multi effects`,
        1,
        255,
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

function decodeCatalogueTemplates(
  value: unknown,
  name: string,
  model: ModelSku,
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
        ("model" in content && content.model !== model) ||
        (content.kind === "h617a_painted" && !isH617xModel(model)) ||
        (content.kind === "h617a_single" && !isH617xModel(model))
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
  model: ModelSku,
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
  const expected = MODEL_RELEASE_WORKFLOWS[model];
  const actual = new Set(workflows.map((workflow) => workflow.id));
  const missing = expected.filter((workflow) => !actual.has(workflow));
  const unexpected = workflows
    .map((workflow) => workflow.id)
    .filter((workflow) => !expected.includes(workflow));
  if (missing.length > 0 || unexpected.length > 0) {
    throw new Error(
      `Malformed Effect Studio server payload: ${name} does not match ${model}.`,
    );
  }
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
      return decoded;
    },
  );
  requireUnique(effects, (effect) => effect.id, `${name} IDs`);
  return effects;
}

function decodeModeOptions(
  value: unknown,
  name: string,
  allowedIds?: readonly string[],
): EffectStudioModeOption[] {
  const modes = arrayValue(value, name, MAX_JSON_COLLECTION_ITEMS).map(
    (item, index) => {
      const mode = objectValue(item, `${name}[${index}]`);
      return {
        id: allowedIds
          ? enumString(mode.id, allowedIds, `${name}[${index}] ID`)
          : boundedString(
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
  model: ModelSku,
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
