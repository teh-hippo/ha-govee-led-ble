import "../../../src/video-profile-editor";
import type { GoveeVideoProfileEditor } from "../../../src/video-profile-editor";

const editor = document.querySelector<GoveeVideoProfileEditor>(
  "govee-video-profile-editor",
);
if (!editor) {
  throw new Error("Video profile editor fixture is missing.");
}

editor.settings = ["saturation"];
editor.content = {
  kind: "video_profile",
  model: "H7000",
  mode: "movie",
  full_screen: null,
  saturation: 50,
  sound_effects: null,
  sound_effects_softness: null,
  white_balance_position: null,
  relative_brightness: null,
  blank_screen: null,
};
