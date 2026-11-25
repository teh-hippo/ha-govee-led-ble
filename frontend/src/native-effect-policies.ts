type NativeEffectLayout = {
  family: number;
  revision: number | undefined;
  layerCount: number;
};

type NativeEffectEditor = "generic" | "projector" | "revisioned" | "single-palette" | "dual-source" | "zones";

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
  combinedFamily?: number;
  diyFamily?: number;
  paintFamily?: number;
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
  },
} satisfies Record<NativeEffectModel, NativeEffectPolicy>;

export function nativeEffectPolicy(model: NativeEffectModel): NativeEffectPolicy {
  return POLICIES[model];
}

export function isNativeEffectModel(model: string): model is NativeEffectModel {
  return NATIVE_EFFECT_MODELS.some(candidate => candidate === model);
}
