import { LitElement, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import {
  isKnownBrightnessOrder,
  KNOWN_BRIGHTNESS_ORDERS,
  layerBrightness,
  withLayerBrightness,
  nativeDiyPalette,
  updateNativeDiy,
  type NativeDiyEdit,
} from "./advanced-effect-model";
import {
  AdvancedEffectEditorController,
  type MovementKey,
} from "./advanced-effect-editor-controller";
import {
  renderAdvancedHelp,
  renderDistribution,
  renderFillPatternControls,
  renderNumberField,
  renderRangeField,
} from "./advanced-effect-editor-fields";
import {
  advancedBrightnessPatternItems,
  advancedLayerActions,
  advancedLayerItems,
  AUTHORING_LAYER_LIMIT,
  AUTHORING_PALETTE_LIMIT,
  DEFAULT_SEGMENT_COUNT,
} from "./advanced-effect-editor-model";
import { advancedEffectEditorStyles } from "./advanced-effect-editor-styles";
import type { AppliedAreaChange } from "./applied-area-control";
import "./applied-area-control";
import type { LivePreviewInteraction } from "./live-preview-controller";
import "./palette-editor";
export {
  blankAdvancedContent,
  cloneAdvancedContent,
  cloneLayeredSceneContent,
} from "./advanced-effect-model";
import type { CheckboxControlChange } from "./checkbox-control";
import "./checkbox-control";
import "./reorderable-strip";
import type {
  GoveeReorderableStrip,
} from "./reorderable-strip";
import type {
  SegmentedControlChange,
  SegmentedControlOption,
} from "./segmented-control";
import "./segmented-control";
import "./slider-control";
import type { SwitchControlChange } from "./switch-control";
import "./switch-control";
import type {
  AdvancedContent,
  BrightnessOrder,
  BrightnessPattern,
  EffectLayer,
  Movement,
  RGB,
} from "./types";

const PRIORITY_OPTIONS = [
  { value: 0, label: "-", ariaLabel: "No priority" },
  ...[1, 2, 3, 4, 5].map((value) => ({
    value,
    label: String(value),
  })),
] satisfies readonly SegmentedControlOption<number>[];

const BRIGHTNESS_LABELS: Record<BrightnessOrder, string> = {
  0: "Brightest to Darkest",
  1: "Brightest, Darkest, Brightest",
  2: "Darkest to Brightest",
  3: "Darkest, Brightest, Darkest",
};

const MOVEMENT_LABELS: Record<number, string> = {
  0: "Forward",
  1: "Backward",
  2: "Forward and Back",
  3: "Back and Forward",
};

export class GoveeAdvancedEffectEditor extends LitElement {
  @property({ attribute: false })
  public content?: AdvancedContent;

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Number })
  public segmentCount = DEFAULT_SEGMENT_COUNT;

  @property({ attribute: false })
  public physicalIcCount?: number | null;

  @state()
  private movementAnnouncement = "";

  private readonly controller = new AdvancedEffectEditorController();
  private previewInteraction: LivePreviewInteraction = "committed";

  public connectedCallback(): void {
    super.connectedCallback();
    this.addEventListener("value-changed", this.capturePreviewInteraction, true);
    this.addEventListener("palette-changed", this.capturePreviewInteraction, true);
  }

  public disconnectedCallback(): void {
    this.removeEventListener("value-changed", this.capturePreviewInteraction, true);
    this.removeEventListener("palette-changed", this.capturePreviewInteraction, true);
    super.disconnectedCallback();
  }

  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("content") || changed.has("disabled")) {
      this.controller.sync(this.content, this.disabled);
    }
  }

  protected render() {
    if (!this.content) {
      return nothing;
    }
    if (this.content.layers.length === 0) {
      return this.renderEmptyLayers();
    }
    const layer = this.activeLayer;
    const layerItems = advancedLayerItems(this.controller.layerLabels);
    const layerActions = advancedLayerActions(
      this.content.layers.length,
      this.disabled,
    ).filter((action) => action.visible && (!this.content?.native_diy || action.kind === "renumber"));
    return html`
      <div class="visually-hidden" aria-live="polite">
        ${this.movementAnnouncement}
      </div>
      ${this.renderNativeDiy()}

      <section class="card layer-card">
        <h3 class="section-title">Layers</h3>
        <govee-reorderable-strip
          class="layer-strip"
          .items=${layerItems}
          .activeIndex=${this.controller.activeLayerIndex}
          ariaLabel="Effect layers"
          itemRole="tab"
          addLabel="Add layer"
          .addDisabled=${this.disabled}
          .addHidden=${Boolean(this.content.native_diy) || this.content.layers.length >= AUTHORING_LAYER_LIMIT}
          .reorderDisabled=${this.disabled || Boolean(this.content.native_diy)}
          .separateActions=${layerActions.length > 0}
          @item-selected=${(event: CustomEvent<{ index: number }>) =>
            this.selectLayer(event.detail.index)}
          @items-reordered=${(
            event: CustomEvent<{ from: number; to: number }>,
          ) => this.reorderLayer(event.detail.from, event.detail.to)}
          @item-added=${this.addLayer}
        >
          ${layerActions.map(
                (action) => html`
                  <button
                    slot="actions"
                    class=${action.danger
                      ? "compact-action danger-action"
                      : "compact-action"}
                    type="button"
                    title=${action.label}
                    aria-label=${action.label}
                    ?disabled=${action.disabled}
                    @click=${action.kind === "copy"
                      ? this.copyLayer
                      : action.kind === "renumber"
                        ? this.renumberLayers
                        : this.deleteLayer}
                  >
                    ${action.icon
                      ? html`
                          <ha-icon
                            class="compact-action-icon"
                            icon=${action.icon}
                            aria-hidden="true"
                          ></ha-icon>
                        `
                      : html`<span aria-hidden="true">${action.glyph}</span>`}
                  </button>
                `,
              )}
        </govee-reorderable-strip>
      </section>

      <section
        class="selected-record-panel"
        id="advanced-layer-panel"
        role="tabpanel"
        aria-labelledby="advanced-layer-tab-${this.controller.activeLayerIndex}"
      >
        <div class="control-grid">
          ${this.renderPriority(layer)}
          ${this.renderPalette(layer)}
          ${this.renderAppliedArea(layer)}
          ${this.renderBrightness(layer)}
          ${renderDistribution(
            layer,
            this.disabled,
            (update) =>
              this.applyContentChange(
                this.controller.updateNested("distribution", update),
              ),
            (update) => this.updateLayer(update),
          )}
          ${this.renderMovement(
            layer,
            "selected_movement",
            "Move Effect within Applied Area",
            true,
          )}
          ${this.renderMovement(
            layer,
            "overall_movement",
            "Move Entire Layer",
            false,
          )}
        </div>
      </section>
    `;
  }

  private renderEmptyLayers() {
    return html`
      <section class="card empty-state" role="status">
        <h3 class="section-title">No Layer Records</h3>
        <p class="muted">
          This layered content contains no layer records. It remains preserved
          until you add one.
        </p>
        <button
          class="add-button"
          type="button"
          ?disabled=${this.disabled}
          @click=${this.addLayer}
        >
          Add layer
        </button>
      </section>
    `;
  }

  private get activeLayer(): EffectLayer {
    return this.controller.activeLayer;
  }

  private renderAppliedArea(layer: EffectLayer) {
    const geometryUnknown = this.nativeGeometryUnknown;
    return html`
      <section class="card">
        <div class="section-heading">
          <h3 class="section-title">Applied Area</h3>
          ${renderAdvancedHelp("appliedArea")}
        </div>
        <govee-applied-area-control
          .layer=${layer}
          .disabled=${this.disabled || (geometryUnknown && this.content?.native_diy === 506)}
          .segmentCount=${this.segmentCount}
          @area-changed=${(event: CustomEvent<AppliedAreaChange>) =>
            this.applyContentChange(
              this.controller.replaceActiveLayer(event.detail.layer),
              event.detail.interaction,
            )}
        ></govee-applied-area-control>
        ${renderFillPatternControls(
          layer,
          this.disabled || geometryUnknown,
          (update) =>
            this.applyContentChange(
              this.controller.updateNested("selection", update),
            ),
        )}
        ${geometryUnknown ? html`<p>Physical IC count is unknown. This template's IC-dependent area/selection controls retain their preset values.</p>` : nothing}
      </section>
    `;
  }

  private renderPalette(layer: EffectLayer) {
    const meteor = this.content?.native_diy === 503;
    const maximum = meteor
      ? this.physicalIcCount == null ? layer.palette.length : Math.min(8, Math.max(1, Math.floor(this.physicalIcCount / 5)))
      : AUTHORING_PALETTE_LIMIT;
    return html`
      <section class="card">
        <h3 class="section-title">Colours</h3>
        <govee-palette-editor
          .palette=${layer.palette}
          .minColours=${meteor && this.physicalIcCount == null ? layer.palette.length : 1}
          .maxColours=${maximum}
          .disabled=${this.disabled}
          @palette-changed=${(event: CustomEvent<{ palette: RGB[] }>) =>
            this.applyContentChange(
              this.controller.updatePalette(event.detail.palette),
            )}
        ></govee-palette-editor>
      </section>
    `;
  }

  private renderBrightness(layer: EffectLayer) {
    if (layer.brightness_patterns.length === 0) {
      return html`
        <section class="card empty-state" role="status">
          <h3 class="section-title">No Brightness Pattern Records</h3>
          <p class="muted">
            This layer contains no brightness pattern records. It remains
            preserved until you add one.
          </p>
          <button
            class="add-button"
            type="button"
            ?disabled=${this.disabled}
            @click=${this.addBrightnessPattern}
          >
            Add brightness pattern
          </button>
        </section>
      `;
    }
    const activeIndex = this.controller.visiblePatternIndex(
      layer.brightness_patterns.length,
    );
    const pattern = layer.brightness_patterns[activeIndex];
    const knownOrder = isKnownBrightnessOrder(pattern.order);
    const brightness = layerBrightness(layer);
    return html`
      <section class="card">
        <h3 class="section-title">Brightness</h3>
        <div class="parameter-stack">
          ${(["algorithm", "type"] as const).map((key) => html`
            <label class="field">
              <span>Brightness ${key}</span>
              <select aria-label=${`Brightness ${key}`} ?disabled=${this.disabled}
                @change=${(event: Event) => this.updateLayer(withLayerBrightness(layer, {
                  [key]: Number((event.target as HTMLSelectElement).value),
                }))}>
                ${brightness[key] > (key === "algorithm" ? 2 : 3)
                  ? html`<option selected disabled>Unknown (${brightness[key]})</option>` : nothing}
                ${(key === "algorithm" ? [0, 1, 2] : [0, 1, 2, 3]).map((value) => html`
                  <option value=${value} .selected=${brightness[key] === value}>${value}</option>
                `)}
              </select>
            </label>
          `)}

          <div class="patterns-section">
            <div class="subsection-heading">
              <h4>Patterns</h4>
              ${renderAdvancedHelp("patterns")}
            </div>
            <govee-reorderable-strip
              class="pattern-strip"
              .items=${advancedBrightnessPatternItems(
                layer.brightness_patterns.length,
              )}
              .activeIndex=${activeIndex}
              ariaLabel="Patterns"
              itemRole="tab"
              addLabel="Add brightness pattern"
              .addDisabled=${this.disabled}
              .addHidden=${layer.brightness_patterns.length >= 3}
              .reorderDisabled=${true}
              .separateActions=${layer.brightness_patterns.length > 1}
              @item-selected=${(event: CustomEvent<{ index: number }>) =>
                this.selectPattern(event.detail.index)}
              @item-added=${this.addBrightnessPattern}
            >
              ${layer.brightness_patterns.length > 1
                ? html`
                    <button
                      slot="actions"
                      class="compact-action danger-action"
                      type="button"
                      title="Delete current brightness pattern"
                      aria-label="Delete current brightness pattern"
                      ?disabled=${this.disabled}
                      @click=${this.deleteBrightnessPattern}
                    >
                      <span aria-hidden="true">×</span>
                    </button>
                  `
                : nothing}
            </govee-reorderable-strip>

            <div
              class="brightness-fields parameter-stack"
              id="advanced-pattern-panel"
              role="tabpanel"
              aria-labelledby="advanced-pattern-tab-${activeIndex}"
            >
              <label class="field">
                <span>Order</span>
                <select
                  aria-label="Brightness order"
                  ?disabled=${this.disabled}
                  @change=${(event: Event) =>
                    this.updateBrightnessPattern({
                      order: Number((event.target as HTMLSelectElement).value),
                    })}
                >
                  ${!knownOrder
                    ? html`<option value="" disabled .selected=${true}>
                        Choose an order
                      </option>`
                    : nothing}
                  ${KNOWN_BRIGHTNESS_ORDERS.map(
                    (order) =>
                      html`<option
                        value=${order}
                        .selected=${pattern.order === order}
                      >
                        ${BRIGHTNESS_LABELS[order]}
                      </option>`,
                  )}
                </select>
              </label>
              <div class="parameter-grid">
                ${renderRangeField(
                  "Scope Low",
                  pattern.scope_low,
                  (value) =>
                    this.updateBrightnessPattern({ scope_low: value }),
                  this.disabled,
                  "brightnessScopeLow",
                )}
                ${renderRangeField(
                  "Scope High",
                  pattern.scope_high,
                  (value) =>
                    this.updateBrightnessPattern({ scope_high: value }),
                  this.disabled,
                  "brightnessScopeHigh",
                )}
              </div>
              <div class="parameter-grid">
                ${renderRangeField(
                  "Changing Speed",
                  pattern.change_speed,
                  (value) =>
                    this.updateBrightnessPattern({ change_speed: value }),
                  this.disabled,
                  "changingSpeed",
                )}
              </div>
              <div class="parameter-grid">
                ${renderRangeField(
                  "Brightest Retention",
                  pattern.brightest_retention,
                  (value) =>
                    this.updateBrightnessPattern({
                      brightest_retention: value,
                    }),
                  this.disabled,
                  "brightestRetention",
                )}
                ${renderRangeField(
                  "Darkest Retention",
                  pattern.darkest_retention,
                  (value) =>
                    this.updateBrightnessPattern({
                      darkest_retention: value,
                    }),
                  this.disabled,
                  "darkestRetention",
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  private renderMovement(
    layer: EffectLayer,
    key: "selected_movement" | "overall_movement",
    label: string,
    showEnterExit: boolean,
  ) {
    const movement = layer[key];
    const help =
      key === "selected_movement"
        ? "inAreaMovement"
        : "wholeLayerMovement";
    const knownDirection = Object.hasOwn(
      MOVEMENT_LABELS,
      movement.direction,
    );
    return html`
      <section class="card">
        <div class="card-heading">
          <div class="section-heading">
            <h3 class="section-title">${label}</h3>
            ${renderAdvancedHelp(help)}
          </div>
          <govee-switch-control
            .label=${`${label} enabled`}
            .checked=${movement.enabled}
            .disabled=${this.disabled}
            @checked-changed=${(
              event: CustomEvent<SwitchControlChange>,
            ) =>
              this.updateMovement(
                key,
                { enabled: event.detail.checked },
                `${label} ${event.detail.checked ? "enabled" : "disabled"}.`,
              )}
          ></govee-switch-control>
        </div>
        ${movement.enabled
          ? html`
              <div class="parameter-stack">
                ${renderNumberField(
                  "ICs per Step",
                  movement.distance,
                  (value) =>
                    this.updateMovement(
                      key,
                      { distance: value },
                      `${label} distance ${value}.`,
                    ),
                  this.disabled,
                  {
                    help: "icsPerStep",
                  },
                )}
                <label class="field">
                  <span>Direction</span>
                  <select
                    .value=${knownDirection
                      ? String(movement.direction)
                      : ""}
                    ?disabled=${this.disabled || (this.nativeGeometryUnknown && this.content?.native_diy === 506)}
                    @change=${(event: Event) => {
                      const direction = Number(
                        (event.target as HTMLSelectElement).value,
                      );
                      this.updateMovement(
                        key,
                        { direction },
                        `${label} direction ${MOVEMENT_LABELS[direction]}.`,
                      );
                    }}
                  >
                    ${knownDirection
                      ? nothing
                      : html`<option value="" disabled .selected=${true}>
                          Choose a direction
                        </option>`}
                    ${Object.entries(MOVEMENT_LABELS).map(
                      ([value, direction]) =>
                        html`<option
                          value=${value}
                          .selected=${movement.direction === Number(value)}
                        >
                          ${direction}
                        </option>`,
                    )}
                  </select>
                </label>
                ${renderRangeField(
                  "Speed",
                  movement.speed,
                  (value) =>
                    this.updateMovement(
                      key,
                      { speed: value },
                      `${label} speed ${value}.`,
                    ),
                  this.disabled,
                )}
                ${showEnterExit
                  ? html`
                      <govee-checkbox-control
                        label="Pause Before Re-entering"
                        .checked=${movement.enter_exit}
                        .disabled=${this.disabled}
                        @checked-changed=${(
                          event: CustomEvent<CheckboxControlChange>,
                        ) => {
                          const enterExit = event.detail.checked;
                          this.updateMovement(
                            key,
                            { enter_exit: enterExit },
                            `${label} pause before re-entering ${enterExit
                              ? "enabled"
                              : "disabled"}.`,
                          );
                        }}
                      >
                        ${renderAdvancedHelp("pauseBeforeReentry", "help")}
                      </govee-checkbox-control>
                    `
                  : nothing}
              </div>
            `
          : nothing}
      </section>
    `;
  }

  private renderPriority(layer: EffectLayer) {
    return html`
      <section class="card">
        <div class="section-heading">
          <h3 class="section-title">Priority</h3>
          ${renderAdvancedHelp("priority")}
        </div>
        <div class="parameter-stack">
          <govee-segmented-control
            label="Priority"
            .value=${layer.priority}
            .options=${PRIORITY_OPTIONS}
            .disabled=${this.disabled}
            .hideLabel=${true}
            @value-changed=${(
              event: CustomEvent<SegmentedControlChange<number>>,
            ) => this.updateLayer({ priority: event.detail.value })}
          ></govee-segmented-control>
        </div>
      </section>
    `;
  }

  private get nativeGeometryUnknown(): boolean {
    const code = this.content?.native_diy;
    return this.physicalIcCount == null && (
      code === 502 || code === 504 || (code === 506 && this.controller.activeLayerIndex >= 2)
    );
  }

  private renderNativeDiy() {
    const content = this.content!;
    const code = content.native_diy;
    if (code === undefined) return nothing;
    const layers = content.layers;
    const names = ["Brilliant / Colorful", "Colorful Sky", "Meteor", "Meteor Shower", "Shine", "Bloom DIY", "Stack"];
    const change = (edit: NativeDiyEdit) => this.applyContentChange(updateNativeDiy(content, edit, this.physicalIcCount));
    const palette = (label: string, secondary = false) => {
      const colours = nativeDiyPalette(content, secondary);
      const min = code === 501 ? 4 : code === 502 || code === 506 ? 2 : code === 504 ? 3 : 1;
      const unknownMeteor = code === 503 && this.physicalIcCount == null;
      const max = code === 503 && this.physicalIcCount != null
        ? Math.min(8, Math.max(1, Math.floor(this.physicalIcCount / 5))) : 8;
      return html`<h4>${label}</h4><govee-palette-editor
        .palette=${colours} .minColours=${unknownMeteor ? colours.length : min}
        .maxColours=${unknownMeteor ? colours.length : max} .disabled=${this.disabled}
        @palette-changed=${(event: CustomEvent<{ palette: RGB[] }>) => change({ [secondary ? "secondary" : "palette"]: event.detail.palette })}
      ></govee-palette-editor>`;
    };
    const first = layers[code === 501 ? 1 : 0];
    const pattern = first.brightness_patterns[0];
    return html`<section class="card">
      <h3>${names[code - 501]} · Native DIY ${code}</h3>
      <p>APK template preset. Playback and rendering await device qualification.</p>
      ${palette(code === 506 ? "Bloom colours" : code === 507 ? "Moving colours" : "Effect colours")}
      ${code === 506 || code === 507 ? palette(code === 506 ? "Moving colours" : "Stack colours", true) : nothing}
      ${code === 501 || code === 505 ? html`<h4>Background</h4><govee-palette-editor
        .palette=${layers[code === 501 ? 0 : 1].palette} .minColours=${1} .maxColours=${1} .disabled=${this.disabled}
        @palette-changed=${(event: CustomEvent<{ palette: RGB[] }>) => change({ background: event.detail.palette[0] })}
      ></govee-palette-editor>` : nothing}
      ${code <= 505 ? renderNumberField("Template speed", code === 503 || code === 504 ? first.overall_movement.speed : first.colour_speed,
        (speed) => change({ speed }), this.disabled, { minimum: code === 501 ? 0 : code === 502 ? 150 : 200, maximum: code === 505 ? 245 : 255 }) : nothing}
      ${pattern && (code === 501 || code === 505) ? html`
        ${renderNumberField("Minimum brightness", pattern.scope_low, (low) => change({ low }), this.disabled, { maximum: Math.max(0, pattern.scope_high - 76) })}
        ${renderNumberField("Maximum brightness", pattern.scope_high, (high) => change({ high }), this.disabled, { minimum: Math.min(255, pattern.scope_low + 76) })}
      ` : nothing}
      ${pattern && (code === 502 || code === 506 || code === 507) ? renderNumberField("Template brightness", pattern.scope_high,
        (brightness) => change({ brightness }), this.disabled, { minimum: code === 507 ? 25 : 50 }) : nothing}
      ${code === 501 ? html`<label><input type="checkbox" .checked=${first.colour_retention === 50} ?disabled=${this.disabled}
        @change=${(event: Event) => change({ gradient: (event.target as HTMLInputElement).checked })}>Colour gradient</label>` : nothing}
      ${code === 502 ? html`
        ${renderNumberField("Minimum star IC count", first.selection.param_2, (starMin) => change({ starMin }), this.disabled || this.physicalIcCount == null, { minimum: 1, maximum: first.selection.param_1 })}
        ${renderNumberField("Maximum star IC count", first.selection.param_1, (starMax) => change({ starMax }), this.disabled || this.physicalIcCount == null, { minimum: first.selection.param_2, maximum: this.physicalIcCount == null ? first.selection.param_1 : Math.min(25, Math.floor(this.physicalIcCount * 4 / 5)) })}
      ` : nothing}
      ${code === 503 || code === 504 || code === 506 || code === 507 ? html`<label class="field"><span>Template direction</span>
        <select aria-label="Template direction" ?disabled=${this.disabled || (code === 506 && this.physicalIcCount == null)}
          @change=${(event: Event) => change({ direction: Number((event.target as HTMLSelectElement).value) })}>
          <option value="" selected disabled>Choose direction</option>
          <option value="0">Clockwise</option><option value="1">Counterclockwise</option>
          ${code === 506 ? html`<option value="2">Two-way</option>` : nothing}
        </select></label>` : nothing}
      ${this.physicalIcCount == null && [502, 503, 504, 506].includes(code)
        ? html`<p>Physical IC count is unknown; dependent controls retain the APK seed. Logical segment count is not used as IC geometry.</p>` : nothing}
    </section>`;
  }

  private updateLayer(update: Partial<EffectLayer>, interaction?: LivePreviewInteraction): void {
    this.applyContentChange(this.controller.updateLayer(update), interaction);
  }

  private updateBrightnessPattern(
    update: Partial<BrightnessPattern>,
    interaction?: LivePreviewInteraction,
  ): void {
    this.applyContentChange(
      this.controller.updateBrightnessPattern(update),
      interaction,
    );
  }

  private updateMovement(key: MovementKey, update: Partial<Movement>, announcement?: string): void {
    this.applyContentChange(this.controller.updateNested(key, update));
    if (announcement) {
      this.movementAnnouncement = announcement;
    }
  }

  private addLayer(): void {
    this.applyLayerChange(this.controller.addLayer());
  }

  private copyLayer(): void {
    this.applyLayerChange(this.controller.copyLayer());
  }

  private renumberLayers(): void {
    this.applyLayerChange(this.controller.renumberLayers());
  }

  private deleteLayer(): void {
    this.applyLayerChange(this.controller.deleteLayer());
  }

  private reorderLayer(from: number, to: number): void {
    this.applySelectionChange(this.controller.reorderLayer(from, to));
  }

  private addBrightnessPattern(): void {
    this.applySelectionChange(this.controller.addBrightnessPattern());
  }

  private deleteBrightnessPattern(): void {
    if (this.applySelectionChange(this.controller.deleteBrightnessPattern())) {
      void this.updateComplete.then(() => {
        this.shadowRoot
          ?.querySelector<GoveeReorderableStrip>(".pattern-strip")
          ?.focusItem(this.controller.activePatternIndex);
      });
    }
  }

  private selectLayer(index: number): void {
    if (this.controller.selectLayer(index)) {
      this.requestUpdate();
    }
  }

  private selectPattern(index: number): void {
    if (this.controller.selectPattern(index)) {
      this.requestUpdate();
    }
  }

  private focusActiveTab(): void {
    void this.updateComplete.then(() => {
      this.shadowRoot
        ?.querySelector<GoveeReorderableStrip>("govee-reorderable-strip")
        ?.focusItem(this.controller.activeLayerIndex);
    });
  }

  private readonly capturePreviewInteraction = (event: Event): void => {
    const source = event.composedPath()[0];
    if (
      event.type === "value-changed" &&
      source instanceof HTMLElement &&
      source.tagName === "GOVEE-SLIDER-CONTROL"
    ) {
      const interaction = (
        event as CustomEvent<{ interaction?: LivePreviewInteraction }>
      ).detail.interaction;
      this.previewInteraction = interaction ?? "committed";
      return;
    }
    if (event.type === "palette-changed") {
      const interaction = (
        event as CustomEvent<{ interaction?: LivePreviewInteraction }>
      ).detail.interaction;
      if (interaction) {
        this.previewInteraction = interaction;
      }
    }
  };

  private applyLayerChange(content: AdvancedContent | undefined): void {
    if (this.applySelectionChange(content)) {
      this.focusActiveTab();
    }
  }

  private applySelectionChange(content: AdvancedContent | undefined): boolean {
    if (!this.applyContentChange(content)) {
      return false;
    }
    this.requestUpdate();
    return true;
  }

  private applyContentChange(content: AdvancedContent | undefined, interaction?: LivePreviewInteraction): boolean {
    if (!content) {
      return false;
    }
    if (this.controller.isCurrentContent(content)) {
      this.content = content;
    }
    this.emitContent(content, interaction);
    return true;
  }

  private emitContent(
    content: AdvancedContent,
    interaction: LivePreviewInteraction = this.previewInteraction,
  ): void {
    this.previewInteraction = "committed";
    this.dispatchEvent(
      new CustomEvent<{
        content: AdvancedContent;
        interaction: LivePreviewInteraction;
      }>("content-changed", {
        detail: { content, interaction },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = advancedEffectEditorStyles;
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-advanced-effect-editor": GoveeAdvancedEffectEditor;
  }
}

if (!customElements.get("govee-advanced-effect-editor")) {
  customElements.define(
    "govee-advanced-effect-editor",
    GoveeAdvancedEffectEditor,
  );
}
