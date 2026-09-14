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

if (new URLSearchParams(location.search).has("alternate")) {
  editor.settings = ["white_balance", "relative_brightness"];
  editor.controls = {
    white_balance: {representation: "scalar", minimum: 0, maximum: 2, default: 1},
    brightness_zones: ["left", "top", "right", "bottom", "strip_left", "strip_right"],
  };
  editor.content = {...editor.content, saturation: null, white_balance_value: 1,
    relative_brightness: {left: 10, top: 20, right: 30, bottom: 40, strip_left: 50, strip_right: 60}};
  editor.addEventListener("content-changed", event => {
    editor.content = (event as CustomEvent).detail.content;
  });
}
if (new URLSearchParams(location.search).has("gated")) {
  editor.applicability = {white_balance: "evidence_gap"};
}
