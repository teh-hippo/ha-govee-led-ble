import "../../../src/music-profile-editor";
import type { GoveeMusicProfileEditor } from "../../../src/music-profile-editor";
import { decodeCustomCataloguePayload } from "../../../src/catalogue-validation";
import { decodeEffectContent } from "../../../src/validation";
import contracts from "../../fixtures/backend-contracts.json";

const editor = document.querySelector<GoveeMusicProfileEditor>("govee-music-profile-editor")!;
// Synthetic alternative exercises the existing control contract, not device support.
const catalogue = decodeCustomCataloguePayload(contracts.responses.custom_catalogue, decodeEffectContent).models.H617A;
editor.catalogue = catalogue;
catalogue.music_settings.separation.parameters.point = {
  kind: "number", default: 8, min: 6, max: 12, options: [],
};
catalogue.music_settings.separation.parameters.gradient.default = false;
catalogue.music_settings.separation.colour = false;
if (new URLSearchParams(location.search).has("unknown")) {
  catalogue.music_settings.separation.parameters = {};
}
editor.content = {
  kind: "music_profile", model: "H617A", mode: "separation", sensitivity: 50,
  colour: null, calm: null, parameters: {},
};
editor.modeSelectionEnabled = true;
