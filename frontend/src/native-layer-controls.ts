import { html, nothing } from "lit";
import type { NativeEffectContent, NativePaintLayer, ProjectorLayer } from "./types";

type Layer = NativeEffectContent["layers"][number] | ProjectorLayer;

function isPaint(layer: Layer): layer is NativePaintLayer {
  return "type" in layer && layer.type === "paint";
}

export function renderNativeLayerControls<T extends Layer>(
  layers: readonly T[],
  index: number,
  disabled: boolean,
  change: (layers: T[], selected: number) => void,
) {
  const layer = layers[index];
  const opaque = "type" in layer && layer.type === "opaque";
  const move = (offset: -1 | 1) => {
    const updated = [...layers];
    [updated[index], updated[index + offset]] = [updated[index + offset], updated[index]];
    change(updated, index + offset);
  };
  return html`
    <div>
      ${!opaque ? html`
        <button type="button" ?disabled=${disabled || layers.length === 255} @click=${() => {
          const copied = structuredClone(layer);
          if (isPaint(copied)) copied.groups = [];
          change([...layers, copied], layers.length);
        }}>${isPaint(layer) ? "Add empty paint layer" : "Duplicate layer"}</button>
        <button type="button" ?disabled=${disabled || layers.length === 1} @click=${() =>
          change(layers.filter((_, position) => position !== index), Math.min(index, layers.length - 2))
        }>${isPaint(layer) ? "Remove paint layer" : "Remove layer"}</button>
      ` : nothing}
      <button type="button" ?disabled=${disabled || index === 0} @click=${() => move(-1)}>Move earlier</button>
      <button type="button" ?disabled=${disabled || index === layers.length - 1} @click=${() => move(1)}>Move later</button>
    </div>
  `;
}
