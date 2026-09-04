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
  expect(Object.keys(decoded.models)).toEqual(["H617A", "H617E", "H6199"]);
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

test("release workflows remain bounded and unique without model-specific lists", () => {
  const payload = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  payload.models.H6199.workflows.push(
    structuredClone(payload.models.H6199.workflows[0]),
  );
  expect(() => decodeCatalogue(payload)).toThrow(
    "release workflows IDs must be unique",
  );
});

test("catalogue model keys are dynamic and embedded models must agree", () => {
  const futureModel = structuredClone(
    backendContracts.responses.custom_catalogue.models.H6199,
  ) as unknown as {
    sku: string;
    templates: Array<{ content: Record<string, unknown> }>;
    workshop_templates: Array<{ content: { model: string } }>;
  };
  futureModel.sku = "H7000";
  for (const template of futureModel.templates) {
    if ("model" in template.content) {
      template.content.model = "H7000";
    }
  }
  for (const template of futureModel.workshop_templates) {
    template.content.model = "H7000";
  }
  const futurePayload = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  (futurePayload.models as Record<string, unknown>).H7000 = futureModel;
  expect(decodeCatalogue(futurePayload).models.H7000.sku).toBe("H7000");

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

  const invalidKey = structuredClone(
    backendContracts.responses.custom_catalogue,
  );
  (invalidKey.models as Record<string, unknown>)["x".repeat(256)] = structuredClone(
    invalidKey.models.H6199,
  );
  expect(() => decodeCatalogue(invalidKey)).toThrow(
    "catalogue model key must contain 1 to 255 characters",
  );
});
