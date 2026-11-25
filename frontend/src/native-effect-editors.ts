import type { LivePreviewInteraction } from "./live-preview-controller";
import { renderH60B0Editor } from "./h60b0-native-editor";
import { renderH7025Editor } from "./h7025-native-editor";
import { renderDualSourceSectionEditor, renderNativeZoneEditor } from "./native-zone-editor";
import { isNativeEffectModel, nativeEffectPolicy } from "./native-effect-policies";
import { renderProjectorEditor } from "./projector-editor";
import type { ModelEffectCatalogue, NativeDiyLayer, NativeEffectContent } from "./types";

type ContentChange = (content: NativeEffectContent, interaction?: LivePreviewInteraction) => void;
type ZoneChange = (
  index: number,
  update: Partial<NativeDiyLayer>,
  family: number,
  kind: number,
  interaction?: LivePreviewInteraction,
) => void;

export function renderNativeEffectEditor(
  content: NativeEffectContent,
  catalogue: ModelEffectCatalogue,
  disabled: boolean,
  change: ContentChange,
  zoneChange: ZoneChange,
) {
  if (!isNativeEffectModel(content.model)) return undefined;
  switch (nativeEffectPolicy(content.model).editor) {
    case "projector":
      return renderProjectorEditor(content, disabled, change);
    case "revisioned":
      return renderH60B0Editor(content, catalogue, disabled, change);
    case "single-palette":
      return renderH7025Editor(content, disabled, change);
    case "dual-source":
      return renderDualSourceSectionEditor(content, catalogue, disabled, zoneChange);
    case "zones":
      return renderNativeZoneEditor(content, catalogue, disabled, zoneChange);
    case "generic":
      return undefined;
  }
}
