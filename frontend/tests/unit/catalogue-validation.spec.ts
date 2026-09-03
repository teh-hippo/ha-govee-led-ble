import { expect, test } from "vitest";

import backendContracts from "../fixtures/backend-contracts.json";
import { decodeCustomCataloguePayload } from "../../src/catalogue-validation";
import { decodeEffectContent } from "../../src/validation";
import type { WorkshopTemplate } from "../../src/types";

function decodeCatalogue(value: unknown) {
  return decodeCustomCataloguePayload(value, decodeEffectContent);
}

test("canonical backend catalogue decodes through the production catalogue validator", () => {
  const decoded = decodeCatalogue(
    backendContracts.responses.custom_catalogue,
  );
  expect(decoded.sku).toBe("H617A");
  expect(Object.keys(decoded.models)).toEqual([
    "H617A",
    "H617E",
    "H6179",
    "H6199",
  ]);
  expect(decoded.models.H6179).toMatchObject({
    limits: {
      palette_min: 1,
      palette_max: 8,
      multi_max: 4,
      music_sensitivity_min: 0,
      music_sensitivity_max: 99,
    },
    music_modes: [
      { id: "mode_0", label: "Mode 1" },
      { id: "mode_1", label: "Mode 2" },
    ],
  });
});

test("catalogue families require variations and the single-layer category", () => {
  const noVariations = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  noVariations.effects[0].variations = [];
  noVariations.models.H617A.effects[0].variations = [];
  expect(() => decodeCatalogue(noVariations)).toThrow(
    "custom-effect template has no variations",
  );

  const wrongCategory = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  wrongCategory.effects[0].category = "music";
  wrongCategory.models.H617A.effects[0].category = "music";
  expect(() => decodeCatalogue(wrongCategory)).toThrow(
    "category is invalid",
  );
});

test("model catalogues require every release workflow", () => {
  const payload = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  payload.models.H6199.workflows = payload.models.H6199.workflows.filter(
    (workflow) => workflow.id !== "workshop",
  );
  expect(() => decodeCatalogue(payload)).toThrow(
    "release workflows does not match H6199",
  );
});

test("H6179 catalogue rejects unsupported controls and family pairs", () => {
  const wrongPair = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  wrongPair.models.H6179.effects[0].variations[0].variant = 1;
  expect(() => decodeCatalogue(wrongPair)).toThrow(
    "H6179 DIY families are incompatible",
  );

  const advanced = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  advanced.models.H6179.supports.advanced = "supported";
  expect(() => decodeCatalogue(advanced)).toThrow(
    "H6179 capability projection is incompatible",
  );
});

test("catalogue keys and embedded template models must agree", () => {
  const wrongSku = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  wrongSku.models.H6199.sku = "H617A";
  expect(() => decodeCatalogue(wrongSku)).toThrow(
    "catalogue model H6199 is keyed as H6199 but declares H617A",
  );

  const wrongTemplateModel = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  const workshopTemplates: WorkshopTemplate[] = [
    {
      id: "protocol-fixture",
      label: "Protocol fixture",
      content: structuredClone(
        backendContracts.content_samples.workshop,
      ) as WorkshopTemplate["content"],
    },
  ];
  workshopTemplates[0].content.model = "H6199";
  (
    wrongTemplateModel.models.H617A as {
      workshop_templates: WorkshopTemplate[];
    }
  ).workshop_templates = workshopTemplates;
  expect(() => decodeCatalogue(wrongTemplateModel)).toThrow(
    "content does not target H617A",
  );
});
