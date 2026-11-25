type NativeEffectLayout = {
  family: number;
  revision: number | undefined;
  layerCount: number;
};

export type NativeEffectPolicy = {
  acceptsFamily: (family: number) => boolean;
  acceptsLayout: (layout: NativeEffectLayout) => boolean;
  layoutError: string;
  zoned: boolean;
  projector: boolean;
  revisioned: boolean;
  sectionTail: boolean;
  temperatures: boolean;
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
  },
} satisfies Record<NativeEffectModel, NativeEffectPolicy>;

export function nativeEffectPolicy(model: NativeEffectModel): NativeEffectPolicy {
  return POLICIES[model];
}
