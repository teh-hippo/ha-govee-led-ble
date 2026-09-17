import "../../../src/music-profile-editor";
import type { GoveeMusicProfileEditor } from "../../../src/music-profile-editor";
import { decodeCustomCataloguePayload } from "../../../src/catalogue-validation";
import { decodeEffectContent } from "../../../src/validation";
import contracts from "../../fixtures/backend-contracts.json";
import { studioTokenStyles } from "../../../src/studio-styles";

const editor = document.querySelector<GoveeMusicProfileEditor>("govee-music-profile-editor")!;
await editor.updateComplete;
const tokens = new CSSStyleSheet();
tokens.replaceSync(studioTokenStyles.cssText);
editor.shadowRoot!.adoptedStyleSheets = [...editor.shadowRoot!.adoptedStyleSheets, tokens];
// Synthetic alternative exercises the existing control contract, not device support.
const catalogue = decodeCustomCataloguePayload(contracts.responses.custom_catalogue, decodeEffectContent).models.H617A;
editor.catalogue = catalogue;
catalogue.music_settings.separation.parameters.point = {
  kind: "number", default: 8, min: 6, max: 12, options: [],
};
catalogue.music_settings.separation.parameters.gradient = {
  kind: "switch", default: false, min: 0, max: 0, options: [],
};
catalogue.music_settings.separation.colour = false;
if (new URLSearchParams(location.search).has("unknown")) {
  catalogue.music_settings.separation.parameters = {};
  delete catalogue.music_settings.separation.palette;
}
editor.content = {
  kind: "music_profile", model: "H617A", mode: "separation", sensitivity: 50,
  colour: null, calm: null, parameters: {},
};
editor.modeSelectionEnabled = true;
if (new URLSearchParams(location.search).has("palette")) {
  // H6099 evidence-backed bounds with synthetic colours for editor interaction checks.
  catalogue.music_settings.separation.palette = { min: 1, max: 8, default: [[12, 34, 56], [78, 90, 123]] };
}
if (new URLSearchParams(location.search).has("fountain")) {
  catalogue.music_settings.fountain.parameters.direction = {
    kind: "select", default: "clockwise", min: 0, max: 0, options: ["clockwise", "counterclockwise", "two_way"],
  };
  catalogue.music_settings.fountain.parameters.speed = {
    kind: "number", default: 80, min: 16, max: 80, options: [],
  };
  editor.content = {...editor.content, mode: "fountain"};
}
const mode = new URLSearchParams(location.search).get("mode");
if (mode) editor.content = {...editor.content, mode};
