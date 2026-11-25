import type { LibrarySummary, ModelEffectCatalogue, NativeEffectContent } from "./types";

type NativeEffectLayout = {
  family: number;
  revision: number | undefined;
  layerCount: number;
};

type NativeEffectEditor = "generic" | "projector" | "revisioned" | "single-palette" | "dual-source" | "zones";
type NativeEffectWorkflow = NonNullable<LibrarySummary["native_workflow"]>;

export type NativeEffectPolicy = {
  acceptsFamily: (family: number) => boolean;
  acceptsLayout: (layout: NativeEffectLayout) => boolean;
  layoutError: string;
  zoned: boolean;
  projector: boolean;
  revisioned: boolean;
  sectionTail: boolean;
  temperatures: boolean;
  editor: NativeEffectEditor;
  workflow: (content: NativeEffectContent) => NativeEffectWorkflow;
  acceptsCatalogueContent?: (
    content: NativeEffectContent,
    catalogue: ModelEffectCatalogue | undefined,
    model: string,
  ) => boolean;
  combinedFamily?: number;
  diyFamily?: number;
  paintFamily?: number;
  sectionTemplatePrefix?: (index: number) => string;
};

export const NATIVE_EFFECT_MODELS = [
  "H60A6",
  "H607C",
  "H1771",
  "H60B0",
  "H60B2",
  "H1AB2",
  "H6093",
  "H7025",
] as const;

export type NativeEffectModel = typeof NATIVE_EFFECT_MODELS[number];

function h60b0Workflow(content: NativeEffectContent): NativeEffectWorkflow {
  return [13, 923].includes(content.family)
    ? "advanced"
    : content.family === 81 || content.revision === 3 ? "multi" : "single";
}

function h60b0AcceptsCatalogueContent(
  content: NativeEffectContent,
  catalogue: ModelEffectCatalogue | undefined,
  model: string,
): boolean {
  if (catalogue?.sku !== model || model !== content.model) return false;
  if (content.layers.some(layer => layer.type !== "diy")) return false;
  if (content.revision === 3) {
    const [top, side, bottom] = content.layers;
    if (top?.type !== "diy" || side?.type !== "diy" || bottom?.type !== "diy") return false;
    if (side.kind !== 1 && bottom.kind !== 1 && (top.enabled === false || top.kind !== 1)) return false;
  }
  const workflow = h60b0Workflow(content);
  return catalogue.workflows.some(candidate => candidate.id === workflow && candidate.content_kind === "native_effect") &&
    (content.family === 81 || catalogue.templates?.some(candidate =>
      candidate.content.kind === "native_effect" && candidate.content.model === model &&
      candidate.content.revision === content.revision) === true);
}

const POLICIES = {
  H60A6: {
    acceptsFamily: family => family === 797 || family === 798,
    acceptsLayout: ({ layerCount }) => layerCount > 0,
    layoutError: "native effects require at least one layer",
    zoned: false,
    projector: false,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "generic",
    workflow: content => content.family === 798
      ? "painted"
      : content.preset_id === 11 || content.preset_id === 12 ? "advanced" : "single",
    diyFamily: 797,
    paintFamily: 798,
  },
  H607C: {
    acceptsFamily: family => family <= 255,
    acceptsLayout: ({ layerCount }) => layerCount >= 1 && layerCount <= 2,
    layoutError: "native zoned effects require one or two sections",
    zoned: true,
    projector: false,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "zones",
    workflow: content => content.family === 153 ? "multi" : "single",
  },
  H1771: {
    acceptsFamily: family => family === 957,
    acceptsLayout: ({ layerCount }) => layerCount === 2,
    layoutError: "native dual-source effects require two sections",
    zoned: true,
    projector: false,
    revisioned: false,
    sectionTail: true,
    temperatures: false,
    editor: "dual-source",
    workflow: () => "multi",
    sectionTemplatePrefix: index => `template:h1771:${index}:`,
  },
  H60B0: {
    acceptsFamily: () => true,
    acceptsLayout: ({ family, revision, layerCount }) =>
      family === 81
        ? revision === 0 && layerCount === 0
        : revision === 1
          ? (family >= 1 && family <= 10 && layerCount === 1) || (family === 13 && layerCount === 2)
          : revision === 3 && (family === 922 || family === 923) && layerCount === 3,
    layoutError: "native family does not match its revision",
    zoned: true,
    projector: false,
    revisioned: true,
    sectionTail: true,
    temperatures: true,
    editor: "revisioned",
    workflow: h60b0Workflow,
    acceptsCatalogueContent: h60b0AcceptsCatalogueContent,
    combinedFamily: 81,
  },
  H60B2: {
    acceptsFamily: family => family === 803,
    acceptsLayout: ({ layerCount }) => layerCount === 1,
    layoutError: "native palette effects require one section",
    zoned: true,
    projector: false,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "zones",
    workflow: () => "single",
  },
  H1AB2: {
    acceptsFamily: family => family === 948,
    acceptsLayout: ({ layerCount }) => layerCount === 1,
    layoutError: "native palette effects require one section",
    zoned: true,
    projector: false,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "zones",
    workflow: () => "single",
  },
  H6093: {
    acceptsFamily: family => family === 712,
    acceptsLayout: ({ layerCount }) => layerCount === 0,
    layoutError: "projector content cannot contain other layer kinds",
    zoned: true,
    projector: true,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "projector",
    workflow: content => content.preset_id === null ? "advanced" : "single",
  },
  H7025: {
    acceptsFamily: family => family === 767,
    acceptsLayout: ({ layerCount }) => layerCount === 1,
    layoutError: "H7025 native DIY requires one layer",
    zoned: true,
    projector: false,
    revisioned: false,
    sectionTail: false,
    temperatures: false,
    editor: "single-palette",
    workflow: () => "single",
  },
} satisfies Record<NativeEffectModel, NativeEffectPolicy>;

export function nativeEffectPolicy(model: NativeEffectModel): NativeEffectPolicy {
  return POLICIES[model];
}

export function isNativeEffectModel(model: string): model is NativeEffectModel {
  return NATIVE_EFFECT_MODELS.some(candidate => candidate === model);
}
