import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { paintNativeLayerPoint } from "./effect-editor-model";

import type { LivePreviewInteraction } from "./live-preview-controller";
import "./palette-editor";
import "./painted-segment-editor";
import "./single-colour-field";
import type { SliderControlChange } from "./slider-control";
import "./slider-control";
import {
  studioActionStyles,
  studioBaseStyles,
  studioCardStyles,
  studioFormStyles,
} from "./studio-styles";
import type {
  DiyEffectFamily,
  EffectPair,
  H6179MixedDiyContent,
  H6179SingleDiyContent,
  ModelEffectCatalogue,
  MultiContent,
  NativeEffectContent,
  NativePaintLayer,
  PaletteDiyEffectContent,
  RGB,
  SingleContent,
} from "./types";
import { clonePalette } from "./ui-utils";

type PaletteContent =
  | SingleContent
  | MultiContent
  | H6179SingleDiyContent
  | H6179MixedDiyContent
  | PaletteDiyEffectContent;
type SinglePaletteContent =
  | SingleContent
  | H6179SingleDiyContent
  | PaletteDiyEffectContent;
type MixedPaletteContent = MultiContent | H6179MixedDiyContent;

function isSinglePaletteContent(
  content: PaletteContent | undefined,
): content is SinglePaletteContent {
  return (
    content?.kind === "h617a_single" ||
    content?.kind === "h6179_single_diy" ||
    content?.kind === "palette_diy"
  );
}

function isMixedPaletteContent(
  content: PaletteContent | undefined,
): content is MixedPaletteContent {
  return (
    content?.kind === "h617a_multi" ||
    content?.kind === "h6179_mixed_diy"
  );
}

function mixedPairs(content: MixedPaletteContent): EffectPair[] {
  return content.kind === "h6179_mixed_diy"
    ? content.components
    : content.effects;
}

function withMixedPairs(
  content: MixedPaletteContent,
  pairs: EffectPair[],
): MixedPaletteContent {
  return content.kind === "h6179_mixed_diy"
    ? { ...content, components: pairs }
    : { ...content, effects: pairs };
}

export class GoveeCustomEffectEditor extends LitElement {
  @property({ attribute: false })
  public content?: PaletteContent;

  @property({ attribute: false })
  public nativeContent?: NativeEffectContent;

  @property({ attribute: false })
  public catalogue?: ModelEffectCatalogue;

  @property({ type: Boolean })
  public disabled = false;

  @state()
  private openRowMenuIndex?: number;

  @state()
  private nativeLayerIndex = 0;

  @state()
  private nativePaintColour: RGB = [255, 0, 0];

  @state()
  private nativeErase = false;

  private draggedEffectIndex?: number;
  private pointerDragId?: number;
  private pointerDragIndex?: number;
  private pointerDropIndex?: number;
  private pointerDragHandle?: HTMLElement;
  private pointerDragActive = false;
  private pointerStartX = 0;
  private pointerStartY = 0;

  private readonly windowPointerDown = (event: PointerEvent): void => {
    if (this.openRowMenuIndex === undefined) {
      return;
    }
    const menu = this.shadowRoot?.querySelector(
      `details[data-row-menu-index="${this.openRowMenuIndex}"]`,
    );
    if (menu && !event.composedPath().includes(menu)) {
      this.openRowMenuIndex = undefined;
    }
  };

  public connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("pointerdown", this.windowPointerDown);
  }

  public disconnectedCallback(): void {
    window.removeEventListener("pointerdown", this.windowPointerDown);
    super.disconnectedCallback();
  }

  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    if (
      changed.has("content") &&
      this.openRowMenuIndex !== undefined &&
      (!isMixedPaletteContent(this.content) ||
        this.openRowMenuIndex >= mixedPairs(this.content).length)
    ) {
      this.openRowMenuIndex = undefined;
    }
  }

  protected updated(): void {
    if (this.nativeContent) {
      const index = Math.min(this.nativeLayerIndex, this.nativeContent.layers.length - 1);
      const layer = this.nativeContent.layers[index];
      const selector = this.shadowRoot?.querySelector<HTMLSelectElement>("select[data-native-layer]");
      const action = this.shadowRoot?.querySelector<HTMLSelectElement>("select[data-native-action]");
      if (selector) selector.value = String(index);
      if (action && layer.type === "paint") action.value = String(layer.action);
      return;
    }
    if (!this.content) {
      return;
    }
    if (isSinglePaletteContent(this.content)) {
      const variation = this.shadowRoot?.querySelector<HTMLSelectElement>(
        "select[data-single-variation]",
      );
      if (variation) {
        variation.value = String(this.content.variant);
      }
      return;
    }
    mixedPairs(this.content).forEach((pair, index) => {
      const family = this.effectFamily(pair, true);
      const effect = this.shadowRoot?.querySelector<HTMLSelectElement>(
        `select[data-effect-index="${index}"]`,
      );
      const variation = this.shadowRoot?.querySelector<HTMLSelectElement>(
        `select[data-variation-index="${index}"]`,
      );
      if (effect) {
        effect.value = family?.id ?? `unknown:${pair.family}`;
      }
      if (variation) {
        variation.value = String(pair.variant);
      }
    });
  }

  protected render() {
    if (this.nativeContent && this.catalogue) {
      return this.renderNative();
    }
    if (!this.content || !this.catalogue) {
      return nothing;
    }
    return this.renderPaletteContent();
  }

  private nativeChanged(content: NativeEffectContent, interaction: LivePreviewInteraction = "committed"): void {
      if (this.disabled) return;
      this.dispatchEvent(new CustomEvent("native-content-changed", {
        detail: { content, interaction }, bubbles: true, composed: true,
      }));
    }

    private nativeLayerChanged(update: Partial<NativeEffectContent["layers"][number]>, interaction?: LivePreviewInteraction): void {
      if (!this.nativeContent) return;
      const layers = structuredClone(this.nativeContent.layers);
      const index = Math.min(this.nativeLayerIndex, layers.length - 1);
      layers[index] = { ...layers[index], ...update } as NativeEffectContent["layers"][number];
      this.nativeChanged({ ...this.nativeContent, layers, speed_index: null }, interaction);
    }

    private nativeNumber(label: string, value: number, maximum: number, change: (value: number) => void) {
      return html`<label>${label}<input type="number" min="0" max=${maximum} .value=${String(value)}
        ?disabled=${this.disabled} @change=${(event: Event) => {
          const input = event.target as HTMLInputElement;
          if (input.validity.valid && Number.isInteger(input.valueAsNumber)) change(input.valueAsNumber);
        }}></label>`;
    }

    private nativeSlider(label: string, value: number, change: (value: number, interaction: LivePreviewInteraction) => void) {
      return html`<govee-slider-control .label=${label} .value=${value} .minimum=${0} .maximum=${Math.max(100, value)}
        .disabled=${this.disabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) => change(event.detail.value, event.detail.interaction)}
      ></govee-slider-control>`;
    }

    private paintNativePoint(index: number, interaction: LivePreviewInteraction): void {
      if (!this.nativeContent) return;
      const layer = this.nativeContent.layers[Math.min(this.nativeLayerIndex, this.nativeContent.layers.length - 1)];
      if (layer.type !== "paint" || index < 0 || index >= 133) return;
      this.nativeLayerChanged(paintNativeLayerPoint(layer, index, this.nativeErase ? null : this.nativePaintColour), interaction);
    }

    private renderNativePaint(layer: NativePaintLayer) {
      const segments: (RGB | null)[] = Array.from({ length: 133 }, () => null);
      for (const group of layer.groups) for (const point of group.indices) segments[point] = group.colour;
      const actions = this.catalogue?.native_actions ?? [];
      return html`
        <govee-painted-segment-editor .segments=${segments} .physical=${true}
          .background=${this.nativeContent!.background} .disabled=${this.disabled}
          @segment-selected=${(event: CustomEvent<{ index: number; interaction: LivePreviewInteraction }>) =>
            this.paintNativePoint(event.detail.index, event.detail.interaction)}
        ></govee-painted-segment-editor>
        <govee-single-colour-field label="Paint colour" .colour=${this.nativePaintColour} .disabled=${this.disabled}
          @colour-changed=${(event: CustomEvent<{ colour: RGB }>) => {
            this.nativePaintColour = event.detail.colour; this.nativeErase = false;
          }}
        ></govee-single-colour-field>
        <button type="button" ?disabled=${this.disabled} aria-pressed=${this.nativeErase}
          @click=${() => { this.nativeErase = !this.nativeErase; }}>Background brush</button>
        <label>Action<select data-native-action ?disabled=${this.disabled} @change=${(event: Event) =>
          this.nativeLayerChanged({ action: Number((event.target as HTMLSelectElement).value) })}>
          ${!actions.some(action => Number(action.id) === layer.action) ? html`
            <option selected value=${layer.action}>Unknown action ${layer.action}</option>` : nothing}
          ${actions.map(action => html`<option value=${action.id} ?selected=${Number(action.id) === layer.action}>${action.label}</option>`)}
        </select></label>
        ${this.nativeSlider("Layer brightness", layer.brightness, (brightness, interaction) => this.nativeLayerChanged({ brightness }, interaction))}
        ${this.nativeNumber("Priority", layer.priority, 255, priority => this.nativeLayerChanged({ priority }))}
        ${this.nativeNumber("Duration (wire units)", layer.duration, 65535, duration => this.nativeLayerChanged({ duration }))}
      `;
    }

    private renderNative() {
      const content = this.nativeContent!;
      const index = Math.min(this.nativeLayerIndex, content.layers.length - 1);
      const layer = content.layers[index];
      return html`
        <section class="card">
          <label>Layer<select data-native-layer ?disabled=${this.disabled} @change=${(event: Event) => {
            this.nativeLayerIndex = Number((event.target as HTMLSelectElement).value);
          }}>
            ${content.layers.map((item, layerIndex) => html`
              <option value=${layerIndex} ?selected=${layerIndex === index}>Layer ${layerIndex + 1} (${item.type})</option>`)}
          </select></label>
          <div>
            ${layer.type !== "opaque" ? html`
              <button type="button" ?disabled=${this.disabled || content.layers.length === 255} @click=${() => {
                const copied = structuredClone(layer);
                if (copied.type === "paint") copied.groups = [];
                const layers = [...content.layers, copied];
                this.nativeLayerIndex = layers.length - 1;
                this.nativeChanged({ ...content, layers, speed_index: null });
              }}>${layer.type === "paint" ? "Add empty paint layer" : "Duplicate layer"}</button>
              <button type="button" ?disabled=${this.disabled || content.layers.length === 1} @click=${() => {
                const layers = content.layers.filter((_, layerIndex) => layerIndex !== index);
                this.nativeLayerIndex = Math.min(index, layers.length - 1);
                this.nativeChanged({ ...content, layers, speed_index: null });
              }}>${layer.type === "paint" ? "Remove paint layer" : "Remove layer"}</button>
            ` : nothing}
            <button type="button" ?disabled=${this.disabled || index === 0} @click=${() => {
              const layers = [...content.layers];
              [layers[index - 1], layers[index]] = [layers[index], layers[index - 1]];
              this.nativeLayerIndex = index - 1; this.nativeChanged({ ...content, layers, speed_index: null });
            }}>Move earlier</button>
            <button type="button" ?disabled=${this.disabled || index === content.layers.length - 1} @click=${() => {
              const layers = [...content.layers];
              [layers[index + 1], layers[index]] = [layers[index], layers[index + 1]];
              this.nativeLayerIndex = index + 1; this.nativeChanged({ ...content, layers, speed_index: null });
            }}>Move later</button>
          </div>
          ${layer.type === "opaque" ? html`<p>Unknown layer ${layer.kind} is retained unchanged.</p>` : html`
            ${this.nativeSlider("Speed", layer.speed, (speed, interaction) => this.nativeLayerChanged({ speed }, interaction))}
            ${layer.type === "diy" ? html`
              <govee-palette-editor .palette=${layer.palette} .minColours=${1} .maxColours=${Math.max(8, layer.palette.length)}
                .disabled=${this.disabled} @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                  this.nativeLayerChanged({ palette: clonePalette(event.detail.palette) }, event.detail.interaction)}
              ></govee-palette-editor>
              ${layer.kind === 4 ? html`
                ${this.nativeNumber("Direction (code)", layer.direction, 255, direction => this.nativeLayerChanged({ direction }))}
                ${this.nativeNumber("Angle", layer.angle, 65535, angle => this.nativeLayerChanged({ angle }))}
              ` : nothing}
            ` : this.renderNativePaint(layer)}
          `}
        </section>
        <section class="card">
          ${content.family === 797 ? html`
            <h3>Background palette</h3>
            ${this.nativeNumber("Background flag (code)", content.background_flag, 255, background_flag =>
              this.nativeChanged({ ...content, background_flag }))}
            <govee-palette-editor .palette=${content.backgrounds} .minColours=${0} .maxColours=${Math.max(8, content.backgrounds.length)}
              .disabled=${this.disabled} @palette-changed=${(event: CustomEvent<{ palette: RGB[]; interaction: LivePreviewInteraction }>) =>
                this.nativeChanged({ ...content, backgrounds: clonePalette(event.detail.palette) }, event.detail.interaction)}
            ></govee-palette-editor>
          ` : html`
            <govee-single-colour-field label="Background colour" .colour=${content.background} .disabled=${this.disabled}
              @colour-changed=${(event: CustomEvent<{ colour: RGB }>) =>
                this.nativeChanged({ ...content, background: event.detail.colour })}
            ></govee-single-colour-field>
            ${this.nativeSlider("Background brightness", content.background_brightness, (background_brightness, interaction) =>
              this.nativeChanged({ ...content, background_brightness }, interaction))}
            ${this.nativeNumber("Show type (code)", content.show_type, 255, show_type => this.nativeChanged({ ...content, show_type }))}
          `}
        </section>
      `;
    }
  private renderPaletteContent() {
    if (!this.content || !this.catalogue) return nothing;
    const rateLabel =
      isSinglePaletteContent(this.content) &&
      this.effectFamily(this.content)?.rate === "sensitivity"
        ? "Sensitivity"
        : "Speed";
    const pairs = isMixedPaletteContent(this.content)
      ? mixedPairs(this.content)
      : isSinglePaletteContent(this.content)
        ? [this.content]
        : [];
    const minimum = Math.max(
      this.content.kind === "h617a_multi" ? this.catalogue.limits.speed_min : 0,
      ...pairs.map((pair) => this.content?.kind === "h617a_multi"
        ? this.effectFamily(pair)?.multi_rate_min ?? this.effectFamily(pair)?.rate_min ?? 0
        : this.effectFamily(pair)?.rate_min ?? 0),
    );
    const maximum = Math.min(
      this.content.kind === "h617a_multi" ? this.catalogue.limits.speed_max : 100,
      ...pairs.map((pair) => this.effectFamily(pair)?.rate_max ?? 100),
    );

    return html`
      ${isMixedPaletteContent(this.content)
        ? html`
            <section class="card effect-card">
              <h3 class="section-title">
                ${this.content.kind === "h6179_mixed_diy"
                  ? "Effect Components"
                  : "Effect Layers"}
              </h3>
              ${this.renderSequence(this.content)}
            </section>
          `
        : nothing}

      <section class="card parameters-card">
        <div class="parameter-stack">
          ${this.renderSingleVariation()}
          <div class="parameter-group">
            <span class="parameter-label">Colours</span>
            ${this.renderPalette()}
          </div>
          ${minimum === maximum ? nothing : html`<govee-slider-control
            .label=${rateLabel}
            .value=${this.content.speed}
            .minimum=${minimum}
            .maximum=${maximum}
            .disabled=${this.disabled || minimum > maximum}
            @value-changed=${(event: CustomEvent<SliderControlChange>) =>
              this.emitContent({
                ...this.content!,
                speed: event.detail.value,
              }, event.detail.interaction)}
          ></govee-slider-control>`}
        </div>
      </section>
    `;
  }

  private renderSingleVariation() {
    if (
      !this.content ||
      !isSinglePaletteContent(this.content)
    ) {
      return nothing;
    }
    const content = this.content;
    const family = this.effectFamily(content);
    const variations = family?.variations ?? [];
    const knownVariation = variations.some(
      (variation) => variation.variant === content.variant,
    );
    if (knownVariation && variations.length <= 1) {
      return nothing;
    }
    return html`
      <label class="field parameter-group">
        <span class="parameter-label">Variation</span>
        <select
          aria-label="Variation"
          data-single-variation
          ?disabled=${this.disabled}
          @change=${(event: Event) => {
            const variant = Number(
              (event.target as HTMLSelectElement).value,
            );
            this.emitContent(
              { ...content, variant },
            );
          }}
        >
          ${knownVariation
            ? nothing
            : html`
                <option value=${String(content.variant)} .selected=${true}>
                  Unknown variation ${content.variant}
                </option>
              `}
          ${variations.map(
            (variation) => html`
              <option
                value=${String(variation.variant)}
                .selected=${variation.variant === content.variant}
              >
                ${variation.label}
              </option>
            `,
          )}
        </select>
      </label>
    `;
  }

  private renderSequence(content: MixedPaletteContent) {
    const atCapacity =
      mixedPairs(content).length >= this.catalogue!.limits.multi_max;
    return html`
      <div class="sequence-table">
        <div class="sequence-header" aria-hidden="true">
          <span>Order</span>
          <span>Effect</span>
          <span>Variation</span>
          <span></span>
        </div>
        <ol class="sequence">
          ${mixedPairs(content).map((pair, index) => this.effectRow(pair, index))}
        </ol>
      </div>
      ${atCapacity
        ? nothing
        : html`
            <button
              class="add-step"
              type="button"
              title="Add layer"
              aria-label="Add layer"
              ?disabled=${this.disabled}
              @click=${this.addEffect}
            >
              +
            </button>
          `}
    `;
  }

  private effectRow(pair: EffectPair, index: number) {
    const family = this.effectFamily(pair, true);
    const variations = family?.variations ?? [];
    return html`
      <li
        class="effect-row"
        data-effect-index=${index}
        @dragover=${this.effectDraggedOver}
        @dragleave=${this.effectDragLeft}
        @drop=${(event: DragEvent) => this.effectDropped(index, event)}
      >
        <div class="order-cell">
          ${this.disabled
            ? nothing
            : html`
                <button
                  class="drag-handle"
                  type="button"
                  draggable="true"
                  title="Drag Layer ${index + 1} to reorder"
                  aria-label="Reorder Layer ${index +
                  1}. Drag or use Arrow Up and Arrow Down."
                  @dragstart=${(event: DragEvent) =>
                    this.effectDragStarted(index, event)}
                  @dragend=${this.effectDragEnded}
                  @pointerdown=${(event: PointerEvent) =>
                    this.effectPointerStarted(index, event)}
                  @pointermove=${this.effectPointerMoved}
                  @pointerup=${this.effectPointerFinished}
                  @pointercancel=${this.effectPointerFinished}
                  @keydown=${(event: KeyboardEvent) =>
                    this.effectDragKeyPressed(index, event)}
                >
                  ⋮⋮
                </button>
              `}
          <span class="layer-heading">Layer ${index + 1}</span>
        </div>
        <label class="field effect-field">
          <span class="field-label">Effect</span>
          <select
            aria-label="Layer ${index + 1} effect"
            data-effect-index=${index}
            ?disabled=${this.disabled}
            @change=${(event: Event) =>
              this.effectFamilyChanged(
                index,
                (event.target as HTMLSelectElement).value,
              )}
          >
            ${family
              ? nothing
              : html`
                  <option
                    value=${`unknown:${pair.family}`}
                    .selected=${true}
                  >
                    Unknown effect ${pair.family}
                  </option>
                `}
            ${this.multiFamilies.map(
              (effect) => html`
                <option
                  value=${effect.id}
                  .selected=${effect.id === family?.id}
                >
                  ${effect.label}
                </option>
              `,
            )}
          </select>
        </label>
        <label class="field effect-field">
          <span class="field-label">Variation</span>
          <select
            aria-label="Layer ${index + 1} variation"
            data-variation-index=${index}
            ?disabled=${this.disabled}
            @change=${(event: Event) =>
              this.effectVariationChanged(
                index,
                Number((event.target as HTMLSelectElement).value),
              )}
          >
            ${variations.some(
              (variation) => variation.variant === pair.variant,
            )
              ? nothing
              : html`
                  <option value=${String(pair.variant)} .selected=${true}>
                    Unknown variation ${pair.variant}
                  </option>
                `}
            ${variations.map(
              (variation) => html`
                <option
                  value=${String(variation.variant)}
                  .selected=${variation.variant === pair.variant}
                >
                  ${variation.label}
                </option>
              `,
            )}
          </select>
        </label>
        ${isMixedPaletteContent(this.content) &&
        mixedPairs(this.content).length > 1
          ? this.disabled
            ? html`
                <button
                  class="row-menu-trigger"
                  type="button"
                  aria-label="Layer actions for Layer ${index + 1}"
                  disabled
                >
                  ⋮
                </button>
              `
            : html`
                <details
                  class="row-menu"
                  data-row-menu-index=${index}
                  ?open=${this.openRowMenuIndex === index}
                  @toggle=${(event: Event) =>
                    this.rowMenuToggled(index, event)}
                  @keydown=${(event: KeyboardEvent) =>
                    this.rowMenuKeyPressed(index, event)}
                >
                  <summary aria-label="Layer actions for Layer ${index + 1}">
                    ⋮
                  </summary>
                  <div class="row-menu-popover">
                    <button
                      class="danger delete-action"
                      type="button"
                      @click=${() => {
                        this.openRowMenuIndex = undefined;
                        this.removeEffect(index);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </details>
              `
          : nothing}
      </li>
    `;
  }

  private get multiFamilies(): DiyEffectFamily[] {
    return this.catalogue?.effects.filter((effect) => effect.supports_multi) ?? [];
  }

  private renderPalette() {
    return html`
      <govee-palette-editor
        .palette=${this.content!.palette}
        .minColours=${this.catalogue!.limits.palette_min}
        .maxColours=${this.content!.kind === "h617a_multi" ? this.catalogue!.limits.palette_max :
          this.effectFamily(this.content! as EffectPair)?.palette_max ?? this.catalogue!.limits.palette_max}
        .disabled=${this.disabled}
        @palette-changed=${(
          event: CustomEvent<{
            palette: RGB[];
            interaction: LivePreviewInteraction;
          }>,
        ) => {
          this.emitContent({
            ...this.content!,
            palette: clonePalette(event.detail.palette),
          }, event.detail.interaction);
        }}
      ></govee-palette-editor>
    `;
  }

  private effectFamilyChanged(index: number, familyId: string): void {
    const family = this.multiFamilies.find((effect) => effect.id === familyId);
    const variation = family?.variations[0];
    if (!family || !variation) {
      return;
    }
    this.replaceEffect(index, {
      family: family.family,
      variant: variation.variant,
    });
  }

  private effectVariationChanged(index: number, variant: number): void {
    if (!isMixedPaletteContent(this.content)) {
      return;
    }
    const current = mixedPairs(this.content)[index];
    if (!current) {
      return;
    }
    this.replaceEffect(index, { ...current, variant });
  }

  private replaceEffect(index: number, pair: EffectPair): void {
    if (!isMixedPaletteContent(this.content)) {
      return;
    }
    const effects = mixedPairs(this.content).map((effect, effectIndex) =>
      effectIndex === index ? pair : effect,
    );
    this.emitContent(withMixedPairs(this.content, effects));
  }

  private addEffect(): void {
    if (
      this.disabled ||
      !isMixedPaletteContent(this.content) ||
      mixedPairs(this.content).length >= this.catalogue!.limits.multi_max
    ) {
      return;
    }
    const next =
      this.multiFamilies[mixedPairs(this.content).length] ??
      this.multiFamilies[0];
    const variation = next?.variations[0];
    if (!next || !variation) {
      return;
    }
    const effects = [
      ...mixedPairs(this.content),
      { family: next.family, variant: variation.variant },
    ];
    this.emitContent(withMixedPairs(this.content, effects));
  }

  private removeEffect(index: number): void {
    if (!isMixedPaletteContent(this.content)) {
      return;
    }
    const effects = mixedPairs(this.content).filter(
      (_effect, effectIndex) => effectIndex !== index,
    );
    this.emitContent(withMixedPairs(this.content, effects));
    const focusIndex = Math.min(index, effects.length - 1);
    void this.updateComplete.then(() => {
      requestAnimationFrame(() => {
        this.shadowRoot
          ?.querySelector<HTMLElement>(
            `[data-effect-index="${focusIndex}"] select`,
          )
          ?.focus();
      });
    });
  }

  private reorderEffect(from: number, to: number): void {
    if (
      this.disabled ||
      !isMixedPaletteContent(this.content) ||
      from === to
    ) {
      return;
    }
    const effects = [...mixedPairs(this.content)];
    const [moving] = effects.splice(from, 1);
    effects.splice(to, 0, moving);
    this.emitContent(withMixedPairs(this.content, effects));
  }

  private effectDragStarted(index: number, event: DragEvent): void {
    if (this.disabled) {
      event.preventDefault();
      return;
    }
    this.draggedEffectIndex = index;
    const row = (event.currentTarget as HTMLElement).closest<HTMLElement>(
      ".effect-row",
    );
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
      if (row && typeof event.dataTransfer.setDragImage === "function") {
        const bounds = row.getBoundingClientRect();
        event.dataTransfer.setDragImage(
          row,
          Math.max(0, event.clientX - bounds.left),
          Math.max(0, event.clientY - bounds.top),
        );
      }
    }
    row?.classList.add("dragging");
  }

  private readonly effectDraggedOver = (event: DragEvent): void => {
    if (this.disabled || this.draggedEffectIndex === undefined) {
      return;
    }
    event.preventDefault();
    this.shadowRoot
      ?.querySelectorAll(".effect-row.drop-target")
      .forEach((row) => row.classList.remove("drop-target"));
    (event.currentTarget as HTMLElement).classList.add("drop-target");
  };

  private readonly effectDragLeft = (event: DragEvent): void => {
    const row = event.currentTarget as HTMLElement;
    if (
      event.relatedTarget instanceof Node &&
      row.contains(event.relatedTarget)
    ) {
      return;
    }
    row.classList.remove("drop-target");
  };

  private effectDropped(index: number, event: DragEvent): void {
    event.preventDefault();
    if (this.draggedEffectIndex === undefined) {
      return;
    }
    this.reorderEffect(this.draggedEffectIndex, index);
    this.draggedEffectIndex = undefined;
    this.clearEffectDragClasses();
  }

  private readonly effectDragEnded = (): void => {
    this.draggedEffectIndex = undefined;
    this.clearEffectDragClasses();
  };

  private effectPointerStarted(index: number, event: PointerEvent): void {
    if (this.disabled || event.pointerType === "mouse") {
      return;
    }
    this.pointerDragId = event.pointerId;
    this.pointerDragIndex = index;
    this.pointerDropIndex = index;
    this.pointerDragHandle = event.currentTarget as HTMLElement;
    this.pointerDragActive = false;
    this.pointerStartX = event.clientX;
    this.pointerStartY = event.clientY;
  }

  private readonly effectPointerMoved = (event: PointerEvent): void => {
    if (
      event.pointerId !== this.pointerDragId ||
      this.pointerDragIndex === undefined
    ) {
      return;
    }
    const handle = this.pointerDragHandle;
    if (!handle) {
      return;
    }
    const row = handle?.closest<HTMLElement>(".effect-row");
    if (!this.pointerDragActive) {
      const distance = Math.hypot(
        event.clientX - this.pointerStartX,
        event.clientY - this.pointerStartY,
      );
      if (distance < 8) {
        return;
      }
      this.pointerDragActive = true;
      row?.classList.add("dragging");
    }
    event.preventDefault();
    const target = this.shadowRoot
      ?.elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>(".effect-row");
    const targetIndex = Number(target?.dataset.effectIndex);
    if (!Number.isInteger(targetIndex)) {
      return;
    }
    this.pointerDropIndex = targetIndex;
    this.shadowRoot
      ?.querySelectorAll(".effect-row.drop-target")
      .forEach((candidate) => candidate.classList.remove("drop-target"));
    target?.classList.add("drop-target");
  };

  private readonly effectPointerFinished = (event: PointerEvent): void => {
    if (event.pointerId !== this.pointerDragId) {
      return;
    }
    const from = this.pointerDragIndex;
    const to = this.pointerDropIndex;
    this.pointerDragId = undefined;
    this.pointerDragIndex = undefined;
    this.pointerDropIndex = undefined;
    this.pointerDragHandle = undefined;
    this.pointerDragActive = false;
    this.clearEffectDragClasses();
    if (event.type === "pointercancel") {
      return;
    }
    if (from !== undefined && to !== undefined) {
      this.reorderEffect(from, to);
    }
  };

  private effectDragKeyPressed(
    index: number,
    event: KeyboardEvent,
  ): void {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") {
      return;
    }
    event.preventDefault();
    const target = index + (event.key === "ArrowUp" ? -1 : 1);
    if (
      !this.content ||
      !isMixedPaletteContent(this.content) ||
      target < 0 ||
      target >= mixedPairs(this.content).length
    ) {
      return;
    }
    this.reorderEffect(index, target);
    void this.updateComplete.then(() => {
      this.shadowRoot
        ?.querySelectorAll<HTMLButtonElement>(".drag-handle")
        [target]?.focus();
    });
  }

  private clearEffectDragClasses(): void {
    this.shadowRoot
      ?.querySelectorAll(".effect-row.dragging, .effect-row.drop-target")
      .forEach((row) => row.classList.remove("dragging", "drop-target"));
  }

  private rowMenuToggled(index: number, event: Event): void {
    const details = event.currentTarget as HTMLDetailsElement;
    if (details.open) {
      this.openRowMenuIndex = index;
    } else if (this.openRowMenuIndex === index) {
      this.openRowMenuIndex = undefined;
    }
  }

  private rowMenuKeyPressed(index: number, event: KeyboardEvent): void {
    if (event.key !== "Escape") {
      return;
    }
    event.preventDefault();
    this.openRowMenuIndex = undefined;
    void this.updateComplete.then(() => {
      this.shadowRoot
        ?.querySelectorAll<HTMLElement>(".row-menu summary")
        [index]?.focus();
    });
  }

  private effectFamily(
    pair: EffectPair,
    multiOnly = false,
  ): DiyEffectFamily | undefined {
    return (multiOnly ? this.multiFamilies : this.catalogue?.effects)?.find(
      (effect) => effect.family === pair.family,
    );
  }

  private emitContent(
    content: PaletteContent,
    interaction: LivePreviewInteraction = "committed",
  ): void {
    this.dispatchEvent(
      new CustomEvent<{
        content: PaletteContent;
        interaction: LivePreviewInteraction;
      }>("content-changed", {
        detail: { content, interaction },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    studioBaseStyles,
    studioCardStyles,
    studioActionStyles,
    studioFormStyles,
    css`
    :host {
      --effect-layer-drag-handle-width: 32px;
      --effect-layer-drag-icon-size: 18px;
      --effect-layer-drag-letter-spacing: -5px;
      --effect-layer-order-min-width: 72px;
      --effect-layer-menu-icon-size: 22px;
      --effect-layer-menu-width: 120px;
      display: block;
    }

    p {
      margin-top: 0;
    }

    .parameters-card {
      margin-top: var(--studio-section-gap);
    }

    .sequence-table {
      --effect-layer-columns:
        minmax(var(--effect-layer-order-min-width), 0.45fr)
        minmax(0, 1fr)
        minmax(0, 1fr)
        var(--studio-control-height);
      container-type: inline-size;
    }

    .sequence-header,
    .effect-row {
      display: grid;
      grid-template-columns: var(--effect-layer-columns);
      align-items: center;
      gap: var(--studio-spacing-lg);
    }

    .sequence-header {
      margin-bottom: var(--studio-spacing-sm);
      color: var(--studio-muted);
      font-size: var(--studio-caption-size);
      font-weight: var(--studio-font-weight-bold);
    }

    .sequence {
      display: grid;
      gap: var(--studio-compact-gap);
      margin: 0 0 var(--studio-spacing-sm);
      padding: 0;
      list-style: none;
    }

    .effect-row {
      position: relative;
      transition:
        background-color var(--studio-transition-duration) ease,
        box-shadow var(--studio-transition-duration) ease,
        opacity var(--studio-transition-duration) ease;
    }

    .effect-row.dragging {
      opacity: 0.5;
    }

    .effect-row.drop-target {
      border-radius: var(--studio-control-radius);
      background: var(--studio-blue-soft);
      box-shadow: inset 0 calc(0px - var(--studio-strong-border-width))
        var(--studio-blue);
    }

    .order-cell {
      display: flex;
      align-items: center;
      gap: var(--studio-compact-gap);
      min-width: 0;
    }

    .drag-handle {
      display: grid;
      width: var(--effect-layer-drag-handle-width);
      height: var(--studio-control-height);
      flex: 0 0 var(--effect-layer-drag-handle-width);
      place-items: center;
      padding: 0;
      border: 0;
      border-radius: var(--studio-control-radius);
      color: var(--studio-muted);
      background: transparent;
      cursor: grab;
      font-size: var(--effect-layer-drag-icon-size);
      letter-spacing: var(--effect-layer-drag-letter-spacing);
      touch-action: none;
      user-select: none;
    }

    .drag-handle:active {
      cursor: grabbing;
    }

    .drag-handle:focus-visible {
      outline: var(--studio-focus-width) solid var(--studio-blue);
      outline-offset: var(--studio-focus-offset);
    }

    .layer-heading {
      overflow: hidden;
      color: var(--primary-text-color);
      font-size: var(--studio-subheading-size);
      font-weight: var(--studio-font-weight-emphasis);
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .effect-field {
      margin-top: 0;
      min-width: 0;
    }

    .field-label {
      display: none;
      font-size: var(--studio-caption-size);
      font-weight: var(--studio-font-weight-emphasis);
    }

    .effect-field select {
      width: 100%;
      min-height: var(--studio-control-height);
      padding: var(--studio-field-padding);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-control-radius);
      color: var(--primary-text-color);
      background: var(--secondary-background-color, #f5f6f8);
    }

    .row-menu {
      position: relative;
      width: var(--studio-control-height);
      justify-self: end;
    }

    .row-menu summary,
    .row-menu-trigger {
      display: grid;
      width: var(--studio-control-height);
      height: var(--studio-control-height);
      place-items: center;
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-round-radius);
      color: var(--studio-muted);
      background: var(--studio-card);
      cursor: pointer;
      list-style: none;
    }

    .row-menu-trigger {
      cursor: not-allowed;
      font-size: var(--effect-layer-menu-icon-size);
    }

    .row-menu summary::-webkit-details-marker {
      display: none;
    }

    .row-menu-popover {
      position: absolute;
      z-index: var(--studio-z-popover);
      top: calc(var(--studio-control-height) + var(--studio-tight-gap));
      right: 0;
      display: grid;
      width: var(--effect-layer-menu-width);
      padding: var(--studio-tight-gap);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-popover-radius);
      background: var(--studio-card);
      box-shadow: var(--studio-popover-shadow);
    }

    .row-menu-popover button {
      padding: var(--studio-field-padding);
      border: 0;
      border-radius: var(--studio-swatch-radius);
      color: var(--primary-text-color);
      background: transparent;
      text-align: start;
      cursor: pointer;
    }

    .row-menu-popover .danger.delete-action {
      border: var(--studio-border-width) solid var(--studio-danger);
      color: var(--text-primary-color, #fff);
      background: var(--studio-danger);
    }

    .row-menu-popover .danger.delete-action:hover,
    .row-menu-popover .danger.delete-action:focus-visible {
      background: color-mix(in srgb, var(--studio-danger) 84%, #000);
    }

    .add-step {
      display: grid;
      width: var(--studio-control-height);
      height: var(--studio-control-height);
      place-items: center;
      padding: 0;
      border: var(--studio-border-width) dashed var(--studio-border);
      border-radius: var(--studio-control-radius);
      color: var(--studio-blue);
      background: transparent;
      cursor: pointer;
      font-size: var(--studio-editor-heading-size);
    }

    /* Converts the effect-layer table into labelled cards when its own column is narrow. */
    @container (max-width: 520px) {
      .sequence {
        gap: var(--studio-spacing-lg);
      }

      .sequence-header {
        display: none;
      }

      .effect-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: start;
        gap: var(--studio-control-gap);
        padding: var(--studio-spacing-lg);
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-control-radius);
        background: var(--secondary-background-color, #f5f6f8);
      }

      .order-cell {
        align-self: center;
      }

      .effect-field {
        grid-column: 1 / -1;
      }

      .row-menu {
        grid-column: 2;
        grid-row: 1;
      }
    }

  `];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-custom-effect-editor": GoveeCustomEffectEditor;
  }
}

if (!customElements.get("govee-custom-effect-editor")) {
  customElements.define(
    "govee-custom-effect-editor",
    GoveeCustomEffectEditor,
  );
}
