import { expect, test } from "vitest";

import { ADVANCED_HELP_CONTENT } from "../../src/advanced-help";

test("Advanced help registry covers supported evidence without time units", () => {
  expect(Object.keys(ADVANCED_HELP_CONTENT)).toEqual([
    "appliedArea",
    "fillPattern",
    "fillPatternType",
    "segmentCount",
    "distribution",
    "distributionMethod",
    "colourSpeed",
    "colourRetention",
    "patterns",
    "brightnessScopeLow",
    "brightnessScopeHigh",
    "changingSpeed",
    "brightestRetention",
    "darkestRetention",
    "inAreaMovement",
    "wholeLayerMovement",
    "icsPerStep",
    "pauseBeforeReentry",
    "priority",
  ]);

  expect(ADVANCED_HELP_CONTENT.appliedArea.text).toContain(
    "physical LED boundary",
  );
  expect(ADVANCED_HELP_CONTENT.fillPattern.text).toContain(
    "inside the applied area",
  );
  expect(ADVANCED_HELP_CONTENT.fillPatternType.text).toContain(
    "Segment Count",
  );
  expect(ADVANCED_HELP_CONTENT.fillPatternType.text).toContain(
    "Minimum LED Count",
  );
  expect(ADVANCED_HELP_CONTENT.fillPatternType.text).toContain(
    "Lit Length",
  );
  expect(ADVANCED_HELP_CONTENT.segmentCount.text).toBe(
    "Sets how many repeated sections divide the applied area for the Segmented fill pattern.",
  );
  expect(ADVANCED_HELP_CONTENT.distributionMethod.text).toContain(
    "Unified gives",
  );
  expect(ADVANCED_HELP_CONTENT.distributionMethod.text).toContain(
    "By IC assigns",
  );
  expect(ADVANCED_HELP_CONTENT.distributionMethod.text).toContain(
    "By Segment assigns",
  );
  expect(ADVANCED_HELP_CONTENT.icsPerStep.text).toContain(
    "independently controlled LED groups",
  );
  expect(ADVANCED_HELP_CONTENT.priority.text).toContain(
    "same LEDs",
  );
  expect(ADVANCED_HELP_CONTENT.priority.text).toContain(
    "A dash leaves the layer without an explicit overlap priority",
  );
  expect(ADVANCED_HELP_CONTENT.brightnessScopeLow.text).toContain(
    "lowest brightness",
  );
  expect(ADVANCED_HELP_CONTENT.brightnessScopeHigh.text).toContain(
    "highest brightness",
  );
  expect(
    [
      ADVANCED_HELP_CONTENT.colourRetention.text,
      ADVANCED_HELP_CONTENT.brightestRetention.text,
      ADVANCED_HELP_CONTENT.darkestRetention.text,
      ADVANCED_HELP_CONTENT.changingSpeed.text,
    ].join(" "),
  ).not.toMatch(/\b(?:milliseconds?|seconds?|minutes?)\b/i);
  expect(
    Object.values(ADVANCED_HELP_CONTENT).some(({ label }) =>
      label.startsWith("Brightness information"),
    ),
  ).toBe(false);
});
