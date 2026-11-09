import "../../../src/custom-effect-editor";
import type { GoveeCustomEffectEditor } from "../../../src/custom-effect-editor";
import { decodeCustomCataloguePayload } from "../../../src/catalogue-validation";
import type { NativeEffectContent } from "../../../src/types";
import { decodeEffectContent } from "../../../src/validation";
import contracts from "../../fixtures/backend-contracts.json";

const editor = document.querySelector<GoveeCustomEffectEditor>("govee-custom-effect-editor")!;
const catalogue = decodeCustomCataloguePayload(contracts.responses.custom_catalogue, decodeEffectContent).models.H60B0;
const id = new URLSearchParams(location.search).get("template") ?? "template:h60b0:3:1:2";
const template = catalogue.templates!.find(candidate => candidate.id === id)!;
if (template.content.kind !== "native_effect") throw new Error("Missing native template");
editor.catalogue = catalogue;
editor.nativeContent = structuredClone(template.content);
editor.addEventListener("native-content-changed", event => {
  editor.nativeContent = (event as CustomEvent<{ content: NativeEffectContent }>).detail.content;
});
