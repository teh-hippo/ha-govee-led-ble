import {
  editableLayerLabels,
  type CustomEffectCategory,
  type EditableEffectContent,
} from "./effect-editor-model";

export type EditorOwner =
  | { section: "custom"; category: CustomEffectCategory }
  | { section: "video" }
  | { section: "scenes" };

export type EditorSource =
  | { kind: "none" }
  | {
      kind: "catalogue";
      owner: EditorOwner;
      selectionIdentity: string;
      label: string;
    }
  | { kind: "new"; owner: EditorOwner }
  | { kind: "saved"; owner: EditorOwner; itemId: string }
  | { kind: "scene"; owner: { section: "scenes" }; itemId?: string };

export type EditorAction =
  | "apply"
  | "saveAs"
  | "reset"
  | "cancel"
  | "delete"
  | "save";

export interface EditorActionDescriptor {
  id: EditorAction;
  label: string;
  style: "primary" | "secondary" | "delete";
  visible: boolean;
  enabled: boolean;
}

export interface EditorActionContext {
  resetAvailable: boolean;
  resetDirty: boolean;
  defaultDirty?: boolean;
  autoSaveEnabled: boolean;
  autoSaveFailed: boolean;
  liveApplyEnabled?: boolean;
  canApply?: boolean;
  canSave: boolean;
  canMutate: boolean;
  busy: boolean;
}

export const NO_EDITOR_SOURCE: EditorSource = { kind: "none" };

export function newEditorSourceSelected(
  source: EditorSource,
  category: CustomEffectCategory,
): boolean {
  return (
    source.kind === "new" &&
    source.owner.section === "custom" &&
    source.owner.category === category
  );
}

export function reactiveEffectSelectorVisible(source: EditorSource): boolean {
  return (
    (source.kind === "new" || source.kind === "saved") &&
    source.owner.section === "custom" &&
    source.owner.category === "music"
  );
}

export function editorActionOrder(
  actions: readonly EditorActionDescriptor[],
): EditorAction[] {
  return actions.filter((action) => action.visible).map((action) => action.id);
}

export function editorOwnerMatches(
  source: EditorSource,
  section: "custom" | "video" | "scenes",
  customCategory: CustomEffectCategory,
): boolean {
  if (source.kind === "none" || source.owner.section !== section) {
    return false;
  }
  return (
    source.owner.section !== "custom" ||
    source.owner.category === customCategory
  );
}

export function editorActionDescriptors(
  source: EditorSource,
  context: EditorActionContext,
): EditorActionDescriptor[] {
  const visible = new Set<EditorAction>();
  if (
    source.kind !== "none" &&
    !context.liveApplyEnabled &&
    context.canApply
  ) {
    visible.add("apply");
  }
  switch (source.kind) {
    case "catalogue":
      visible.add("saveAs");
      if (context.resetDirty) visible.add("reset");
      if (
        context.defaultDirty &&
        (!context.autoSaveEnabled || context.autoSaveFailed)
      ) {
        visible.add("save");
      }
      break;
    case "new":
      if (context.resetAvailable) visible.add("reset");
      visible.add("save");
      break;
    case "saved":
      visible.add("saveAs");
      if (context.resetDirty) visible.add("reset");
      visible.add("delete");
      if (!context.autoSaveEnabled || context.autoSaveFailed) {
        visible.add("save");
      }
      break;
    case "scene":
      visible.add("saveAs");
      if (context.resetDirty) visible.add("reset");
      visible.add("cancel");
      if (source.itemId !== undefined) visible.add("delete");
      if (
        source.itemId !== undefined ||
        (context.defaultDirty &&
          (!context.autoSaveEnabled || context.autoSaveFailed))
      ) {
        visible.add("save");
      }
      break;
    case "none":
      break;
  }
  return (["apply", "saveAs", "reset", "cancel", "delete", "save"] as const).map(
    (id): EditorActionDescriptor => {
      const isVisible = visible.has(id);
      const enabled =
        isVisible &&
        !context.busy &&
        (id === "reset"
          ? context.resetDirty
          : id === "apply"
            ? context.canApply === true
          : id === "cancel"
            ? true
            : context.canMutate &&
              (id === "save" ? context.canSave : true));
      return {
        id,
        label:
          id === "saveAs"
            ? "Save As"
            : id[0].toUpperCase() + id.slice(1),
        style:
          id === "save"
            ? "primary"
            : id === "delete"
              ? "delete"
              : "secondary",
        visible: isVisible,
        enabled,
      };
    },
  );
}

export function serialiseEditableContent(
  content: EditableEffectContent,
): string {
  return JSON.stringify({
    content,
    layer_labels: editableLayerLabels(content),
  });
}
