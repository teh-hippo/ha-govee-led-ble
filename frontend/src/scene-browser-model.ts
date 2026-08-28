import { cloneLayeredSceneContent } from "./advanced-effect-model";
import type { SegmentedControlOption } from "./segmented-control";
import type {
  BuiltinSceneContent,
  DeviceCapabilities,
  LayeredSceneContent,
  LibraryItem,
  LibrarySummary,
  PaletteSceneContent,
  PreviewStatus,
  SceneCatalogue,
  SceneSummary,
} from "./types";
import { compareLabels } from "./ui-utils";

export type CategorySelection = "all" | "custom" | number;
export type SceneContent = BuiltinSceneContent | PaletteSceneContent | LayeredSceneContent;
export type SceneListEntry =
  | { kind: "custom"; item: LibrarySummary; label: string }
  | { kind: "builtin"; scene: SceneSummary; label: string };
export type SceneInitialSelection =
  | { kind: "none" }
  | { kind: "saved"; itemId: string }
  | { kind: "native"; effect: string };
export type ScenePreviewRequest =
  | {
      kind: "scene";
      scene: SceneSummary;
      speedIndex: number | null;
      persistDefault?: boolean;
    }
  | {
      kind: "snapshot";
      name: string;
      content: SceneContent;
      persistDefault?: boolean;
    };

type SceneDeviceIdentity = Pick<
  DeviceCapabilities,
  "config_entry_id" | "model"
>;

export function sameSceneDeviceIdentity(
  left: SceneDeviceIdentity | undefined,
  right: SceneDeviceIdentity | undefined,
): boolean {
  return (
    left?.config_entry_id === right?.config_entry_id &&
    left?.model === right?.model
  );
}
export type NativeSceneActionId =
  | "apply"
  | "save-as"
  | "reset-default"
  | "edit"
  | "save-default";

export interface NativeSceneAction {
  id: NativeSceneActionId;
  label: string;
  style: "primary" | "secondary";
  disabled?: boolean;
}

export interface SceneBrowserViewState {
  catalogue?: SceneCatalogue;
  category: CategorySelection;
  selectedScene?: SceneSummary;
  selectedItem?: LibraryItem;
  content?: SceneContent;
  catalogueContent?: SceneContent;
  name: string;
  speedIndex: number | null;
  hasDefault: boolean;
  loading: boolean;
  saving: boolean;
  applying: boolean;
  defaultSaveFailed: boolean;
  editingCopy: boolean;
  notice?: string;
  error?: string;
}

export function initialSceneBrowserState(): SceneBrowserViewState {
  return {
    category: "all",
    name: "",
    speedIndex: null,
    hasDefault: false,
    loading: false,
    saving: false,
    applying: false,
    defaultSaveFailed: false,
    editingCopy: false,
  };
}

export function sceneKey(scene: SceneSummary): string {
  return `builtin:${scene.scene_id}:${scene.effect_id}`;
}

export function sceneSelectionKey(state: SceneBrowserViewState): string | undefined {
  if (state.selectedItem) {
    return `custom:${state.selectedItem.id}`;
  }
  return state.selectedScene ? sceneKey(state.selectedScene) : undefined;
}

export function normaliseSceneName(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

export function compatibleCustomScenes(items: LibrarySummary[], catalogue: SceneCatalogue | undefined): LibrarySummary[] {
  return items.filter(
    (item) =>
      isSceneKind(item.kind) &&
      item.template?.sku === catalogue?.sku,
  );
}

export function sceneBrowserCategories(
  catalogue: SceneCatalogue | undefined,
  customScenes: LibrarySummary[],
): { id: CategorySelection; label: string }[] {
  const categories: { id: CategorySelection; label: string }[] = [];
  if (catalogue?.scenes.length) {
    categories.push({ id: "all", label: "All" });
  }
  if (customScenes.length) {
    categories.push({ id: "custom", label: "My Effects" });
  }
  const nativeCategories =
    catalogue?.categories
      .filter((category) => catalogue.scenes.some((scene) => scene.category_id === category.id))
      .map((category) => ({ id: category.id, label: category.name }))
      .sort((left, right) => compareLabels(left.label, right.label)) ?? [];
  return [...categories, ...nativeCategories];
}

export function sceneBrowserEntries(
  state: SceneBrowserViewState,
  customScenes: LibrarySummary[],
): SceneListEntry[] {
  const custom = state.category === "all" || state.category === "custom" ? customScenes : [];
  const builtin =
    !state.catalogue || state.category === "custom"
      ? []
      : state.category === "all"
        ? state.catalogue.scenes
        : state.catalogue.scenes.filter((scene) => scene.category_id === state.category);
  return [
    ...custom.map((item): SceneListEntry => ({ kind: "custom", item, label: item.name })),
    ...builtin.map((scene): SceneListEntry => ({ kind: "builtin", scene, label: scene.display_name })),
  ].sort((left, right) => compareLabels(left.label, right.label));
}

export function visibleCategoryForBuiltin(
  category: CategorySelection,
  scene: SceneSummary,
): CategorySelection {
  return category === "all" || category === scene.category_id
    ? category
    : scene.category_id;
}

export function visibleCategoryForCustom(
  category: CategorySelection,
): CategorySelection {
  return category === "all" || category === "custom" ? category : "custom";
}

export function findCatalogueScene(catalogue: SceneCatalogue, content: SceneContent): SceneSummary | undefined {
  return catalogue.scenes.find(
    (scene) =>
      scene.scene_id === content.template.scene_id &&
      scene.effect_id === content.template.effect_id,
  );
}

export function findNativeScene(catalogue: SceneCatalogue, effect: string): SceneSummary | undefined {
  const key = normaliseSceneName(effect);
  return catalogue.scenes.find(
    (scene) => normaliseSceneName(scene.display_name) === key || normaliseSceneName(scene.name) === key,
  );
}

export function isSceneContent(content: LibraryItem["content"]): content is SceneContent {
  return isSceneKind(content.kind);
}

function isSceneKind(kind: string): boolean {
  return kind === "scene_builtin" || kind === "scene_palette" || kind === "scene_layered";
}

export function previewMayChangeSceneDefault(status: PreviewStatus | undefined, configEntryId: string | undefined): boolean {
  return Boolean(
    status &&
      configEntryId &&
      status.config_entry_id === configEntryId &&
      ["scene_builtin", "scene_palette", "scene_layered"].includes(status.content_kind) &&
        ["confirmed", "unconfirmed", "failed", "cancelled"].includes(status.phase) &&
        ["may_have_started", "completed", "unknown"].includes(status.write_disposition),
  );
}

export function sceneSpeedOptions(optionCount: number, defaultIndex: number): SegmentedControlOption<number>[] {
  return Array.from({ length: optionCount }, (_unused, index) => ({
    value: index,
    label: "▸".repeat(index + 1),
    ariaLabel: sceneSpeedAriaLabel(index, defaultIndex, optionCount),
  }));
}

export function nativeSceneActions(
  catalogueDirty: boolean,
  defaultDirty: boolean,
  autoSaveEnabled: boolean,
  autoSaveFailed = false,
  _liveApplyEnabled = true,
  defaultWritePending = false,
): NativeSceneAction[] {
  const actions: NativeSceneAction[] = [];
  actions.push({ id: "save-as", label: "Save As", style: "secondary" });
  if (catalogueDirty) {
    actions.push({
      id: "reset-default",
      label: "Reset",
      style: "secondary",
      ...(defaultWritePending ? { disabled: true } : {}),
    });
  }
  actions.push({ id: "edit", label: "Edit", style: "secondary" });
  if (
    !defaultWritePending &&
    defaultDirty &&
    (!autoSaveEnabled || autoSaveFailed)
  ) {
    actions.push({
      id: "save-default",
      label: "Save",
      style: "primary",
    });
  }
  return actions;
}

export function sceneHasParameterSurface(scene: SceneSummary): boolean {
  return scene.speed !== null;
}

function sceneSpeedAriaLabel(index: number, defaultIndex: number, optionCount: number): string {
  const names =
    optionCount === 3
      ? ["Slow", "Medium", "Fast"]
      : optionCount === 4
        ? ["Slowest", "Slow", "Fast", "Fastest"]
        : [];
  const label = names[index] ?? `Speed ${index + 1}`;
  return index === defaultIndex ? `${label}, catalogue default` : label;
}

export function clonePaletteSceneContent(content: PaletteSceneContent): PaletteSceneContent {
  return {
    ...content,
    template: { ...content.template },
    steps: content.steps.map((step) => ({
      ...step,
      colour: [...step.colour],
      inline_colour: step.inline_colour === null ? null : [...step.inline_colour],
    })),
    palette: content.palette.map((colour) => [...colour]),
  };
}

export function cloneSceneContent(content: SceneContent): SceneContent {
  if (content.kind === "scene_palette") {
    return clonePaletteSceneContent(content);
  }
  if (content.kind === "scene_layered") {
    return cloneLayeredSceneContent(content);
  }
  return { ...content, template: { ...content.template } };
}

export function sceneContentAtSpeed(content: SceneContent, speedIndex: number | null): SceneContent {
  return { ...cloneSceneContent(content), speed_index: speedIndex };
}

export function hasCurrentSceneContent(state: SceneBrowserViewState, activeSelectionIdentity: string | undefined): boolean {
  const { catalogue, selectedScene, content } = state;
  return Boolean(
    catalogue &&
      selectedScene &&
      content &&
      content.template.sku === catalogue.sku &&
      content.template.scene_id === selectedScene.scene_id &&
      content.template.effect_id === selectedScene.effect_id &&
      activeSelectionIdentity === sceneSelectionKey(state),
  );
}

export function sceneIsDirty(state: SceneBrowserViewState): boolean {
  if (!state.selectedItem || !state.content) {
    return true;
  }
  return (
    state.name.trim() !== state.selectedItem.name ||
    JSON.stringify(sceneContentAtSpeed(state.content, state.speedIndex)) !== JSON.stringify(state.selectedItem.content)
  );
}

export function buildScenePreviewRequest(
  state: SceneBrowserViewState,
  activeSelectionIdentity: string | undefined,
  available: boolean,
  isAdmin: boolean,
): ScenePreviewRequest | undefined {
  if (
    !available ||
    !state.selectedScene ||
    !state.content ||
    !hasCurrentSceneContent(state, activeSelectionIdentity) ||
    !isAdmin
  ) {
    return undefined;
  }
  const content = sceneContentAtSpeed(state.content, state.speedIndex);
  return content.kind === "scene_builtin"
    ? { kind: "scene", scene: state.selectedScene, speedIndex: state.speedIndex }
    : {
        kind: "snapshot",
        name: state.name.trim() || state.selectedScene.display_name,
        content,
      };
}
