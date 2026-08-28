import {
  cloneEditableEffect,
  editableLayerLabels,
  type EditableEffectContent,
} from "./effect-editor-model";

export interface BuiltInDefaultBaselines {
  catalogue: EditableEffectContent;
  persisted: EditableEffectContent;
  hasDefault: boolean;
}

export function cloneBuiltInDefaultBaselines(
  catalogue: EditableEffectContent,
  persisted: EditableEffectContent,
  hasDefault: boolean,
): BuiltInDefaultBaselines {
  return {
    catalogue: cloneEditableEffect(catalogue),
    persisted: cloneEditableEffect(persisted),
    hasDefault,
  };
}

export function builtInContentEquals(
  left: EditableEffectContent,
  right: EditableEffectContent,
): boolean {
  const serialise = (content: EditableEffectContent) =>
    JSON.stringify({ content, layer_labels: editableLayerLabels(content) });
  return serialise(left) === serialise(right);
}

export function builtInCatalogueDirty(
  content: EditableEffectContent,
  baselines: BuiltInDefaultBaselines | undefined,
): boolean {
  return Boolean(
    baselines && !builtInContentEquals(content, baselines.catalogue),
  );
}

export function builtInDefaultDirty(
  content: EditableEffectContent,
  baselines: BuiltInDefaultBaselines | undefined,
): boolean {
  return Boolean(
    baselines && !builtInContentEquals(content, baselines.persisted),
  );
}

export function builtInDefaultAction(
  content: EditableEffectContent,
  baselines: BuiltInDefaultBaselines,
): "set" | "reset" {
  return builtInContentEquals(content, baselines.catalogue) ? "reset" : "set";
}
