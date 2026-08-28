export const ADVANCED_HELP_CONTENT = {
  appliedArea: {
    label: "Applied area information",
    text: "Sets the physical LED boundary for this layer.",
  },
  fillPattern: {
    label: "Fill pattern information",
    text: "Controls how LEDs inside the applied area take part in the effect.",
  },
  fillPatternType: {
    label: "Fill pattern type information",
    text: "Segment repeats the applied area according to Segment Count.  Continuous uses runs of the selected LED Count.  Random varies runs between Minimum LED Count and Maximum LED Count.  Custom alternates Lit Length with Gap.",
  },
  segmentCount: {
    label: "Segment Count information",
    text: "Sets how many repeated sections divide the applied area for the Segmented fill pattern.",
  },
  distribution: {
    label: "Distribution information",
    text: "Controls whether participating LEDs share colours or receive colours by IC or segment.",
  },
  distributionMethod: {
    label: "Distribution method information",
    text: "Unified gives all participating LEDs the same colour.  By IC assigns colours by independently controlled LED group.  By Segment assigns colours by fill-pattern segment.",
  },
  colourSpeed: {
    label: "Colour speed information",
    text: "Controls how quickly the layer changes between palette colours.",
  },
  colourRetention: {
    label: "Colour retention information",
    text: "Controls how long a palette colour is retained before the next change.",
  },
  patterns: {
    label: "Brightness patterns information",
    text: "Each pattern defines an ordered brightness change for this layer.",
  },
  brightnessScopeLow: {
    label: "Scope low information",
    text: "Sets the lowest brightness the pattern can use.",
  },
  brightnessScopeHigh: {
    label: "Scope high information",
    text: "Sets the highest brightness the pattern can use.",
  },
  changingSpeed: {
    label: "Brightness changing speed information",
    text: "Controls how quickly the brightness pattern changes.",
  },
  brightestRetention: {
    label: "Brightest retention information",
    text: "Controls how long the pattern remains at its brightest level before continuing.",
  },
  darkestRetention: {
    label: "Darkest retention information",
    text: "Controls how long the pattern remains at its darkest level before continuing.",
  },
  inAreaMovement: {
    label: "In-area movement information",
    text: "Moves the effect inside the applied area.",
  },
  wholeLayerMovement: {
    label: "Whole-layer movement information",
    text: "Moves the complete layer.",
  },
  icsPerStep: {
    label: "ICs per Step information",
    text: "Sets how many independently controlled LED groups are advanced for each movement step.",
  },
  pauseBeforeReentry: {
    label: "Pause before re-entry information",
    text: "Pauses the moving effect before it enters the applied area again.",
  },
  priority: {
    label: "Layer overlap priority information",
    text: "When layers target the same LEDs, the layer with the higher priority is shown.  A dash leaves the layer without an explicit overlap priority.",
  },
} as const;

export type AdvancedHelpKey = keyof typeof ADVANCED_HELP_CONTENT;
