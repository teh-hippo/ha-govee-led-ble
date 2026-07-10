/**
 * govee-led-ble-card — Lovelace custom card for the ha_govee_led_ble integration.
 *
 * Two direct-manipulation editors for a segment-capable Govee strip, both of
 * which write through the `ha_govee_led_ble.paint_segments` entity service and
 * read live colour back from the light entity's `segment_colors` attribute:
 *
 *   1. a `SEGMENT_COUNT`-cell DRAG PAINTER — pointer-drag and keyboard
 *      multi-select, a colour picker, and Apply that paints the selection;
 *   2. a 2-to-5 stop GRADIENT editor — draggable stops that interpolate across
 *      the strip (Python-parity rounding), grouped into the fewest paint groups,
 *      with a live canvas preview that falls back to a static frame under
 *      `prefers-reduced-motion`.
 *
 * A row of one-tap PRESETS (built-in gradients and solid fills) paints the
 * whole strip instantly through the same service.
 *
 * All maths lives in `./logic` (pure, unit-tested for numeric parity with the
 * integration). lit is vendored (`../vendor/lit.js`) and inlined by `bun build`,
 * so the Home Assistant runtime needs no npm packages. Styling uses Home
 * Assistant theme tokens only; the sole bespoke CSS is layout.
 */

import { LitElement, html, nothing } from "../vendor/lit.js";
import { cardStyles } from "./card-styles";
import "./card-editor";
import type { GoveeLedBleCardConfig, HassEntityState, HassLike } from "./types";
import {
  SEGMENT_COUNT,
  clamp,
  clearSelection,
  coerceCustomEffects,
  errorMessage,
  GRADIENT_PRESETS,
  groupSegments,
  hexToRgb,
  interpolateSegments,
  presetGroups,
  rangeSelection,
  rgbToHex,
  sampleStops,
  selectAll,
  selectionToSegments,
  toggleSegment,
  type CustomEffectEntry,
  type GradientPreset,
  type RGB,
  type SegmentGroup,
} from "./logic";

/** A transient status banner surfaced after a custom-effect service call. */
interface Feedback {
  kind: "error" | "info";
  text: string;
}

/** Default gradient palette (three evenly spaced stops). */
const DEFAULT_STOPS = ["#ff595e", "#ffca3a", "#1982c4"];
/** Default paint colour for the segment painter. */
const DEFAULT_PAINT = "#33cc66";
/** Gradient stop count bounds. */
const MIN_STOPS = 2;
const MAX_STOPS = 5;

/** Coerce a raw `segment_colors` attribute into RGB triples, or null if absent/malformed. */
function coerceSegmentColors(raw: unknown): RGB[] | null {
  if (!Array.isArray(raw)) return null;
  const out: RGB[] = [];
  for (const entry of raw) {
    if (!Array.isArray(entry) || entry.length < 3) return null;
    const [r, g, b] = entry;
    if (typeof r !== "number" || typeof g !== "number" || typeof b !== "number") {
      return null;
    }
    out.push([r, g, b]);
  }
  return out;
}

class GoveeLedBleCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _selection: { state: true },
    _cursor: { state: true },
    _paintColor: { state: true },
    _stops: { state: true },
    _dragStop: { state: true },
    _dragFrac: { state: true },
    _reduce: { state: true },
    _effectName: { state: true },
    _renamingId: { state: true },
    _renameValue: { state: true },
    _feedback: { state: true },
  };

  declare hass?: HassLike;
  declare private _config?: GoveeLedBleCardConfig;
  // Selection state is 1-based (segments 1..SEGMENT_COUNT) so the logic-module
  // reducers can be reused unchanged.
  declare private _selection: Set<number>;
  declare private _cursor: number;
  declare private _paintColor: string;
  declare private _stops: string[];
  declare private _dragStop: number | null;
  declare private _dragFrac: number | null;
  declare private _reduce: boolean;
  declare private _effectName: string;
  declare private _renamingId: string | null;
  declare private _renameValue: string;
  declare private _feedback: Feedback | null;

  private _dragging = false;
  private _dragAnchor = 1;
  private _raf: number | null = null;
  private _t0 = 0;
  private _mq?: MediaQueryList;

  constructor() {
    super();
    this._selection = new Set();
    this._cursor = 1;
    this._paintColor = DEFAULT_PAINT;
    this._stops = [...DEFAULT_STOPS];
    this._dragStop = null;
    this._dragFrac = null;
    this._reduce = false;
    this._effectName = "";
    this._renamingId = null;
    this._renameValue = "";
    this._feedback = null;
  }

  static getStubConfig(hass?: HassLike): GoveeLedBleCardConfig {
    const entity = hass
      ? Object.keys(hass.states).find(
          (id) =>
            id.startsWith("light.") &&
            Array.isArray(hass.states[id].attributes?.segment_colors),
        )
      : undefined;
    return { entity: entity ?? "" };
  }

  static getConfigElement(): HTMLElement {
    return document.createElement("govee-led-ble-card-editor");
  }

  setConfig(config: GoveeLedBleCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    this._config = { ...config };
  }

  getCardSize(): number {
    return 10;
  }

  connectedCallback(): void {
    super.connectedCallback();
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    this._reduce = mq.matches;
    this._mq = mq;
    mq.addEventListener("change", this._onReduceChange);
    this._raf = requestAnimationFrame((ts) => this._tick(ts));
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._raf !== null) cancelAnimationFrame(this._raf);
    this._raf = null;
    this._mq?.removeEventListener("change", this._onReduceChange);
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
    window.removeEventListener("pointermove", this._onStopMove);
    window.removeEventListener("pointerup", this._onStopUp);
  }

  private readonly _onReduceChange = (ev: MediaQueryListEvent): void => {
    this._reduce = ev.matches;
  };

  // --- live per-segment read-back -----------------------------------------

  private _segmentColors(): RGB[] | null {
    const entity = this._config?.entity;
    if (!entity || !this.hass) return null;
    const state = this.hass.states[entity];
    if (!state) return null;
    return coerceSegmentColors(state.attributes?.segment_colors);
  }

  // --- segment painter: pointer drag --------------------------------------

  /** Map a client x-coordinate to a 1-based segment index within the strip. */
  private _cellFromClientX(clientX: number): number {
    const strip = this.renderRoot.querySelector<HTMLElement>(".strip");
    if (!strip) return 1;
    const rect = strip.getBoundingClientRect();
    const w = rect.width / SEGMENT_COUNT;
    return clamp(Math.floor((clientX - rect.left) / w), 0, SEGMENT_COUNT - 1) + 1;
  }

  private _onDown(ev: PointerEvent): void {
    ev.preventDefault();
    this._dragging = true;
    this._dragAnchor = this._cellFromClientX(ev.clientX);
    this._cursor = this._dragAnchor;
    this._selection = new Set([this._dragAnchor]);
    this.renderRoot.querySelector<HTMLElement>(".strip")?.focus();
    window.addEventListener("pointermove", this._onMove);
    window.addEventListener("pointerup", this._onUp);
  }

  private readonly _onMove = (ev: PointerEvent): void => {
    if (!this._dragging) return;
    const cur = this._cellFromClientX(ev.clientX);
    this._selection = rangeSelection(this._dragAnchor, cur);
    this._cursor = cur;
  };

  private readonly _onUp = (): void => {
    this._dragging = false;
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
  };

  // --- segment painter: keyboard model ------------------------------------

  private _onKey(ev: KeyboardEvent): void {
    const k = ev.key;
    if (k === "ArrowRight" || k === "ArrowDown") {
      this._cursor = clamp(this._cursor + 1, 1, SEGMENT_COUNT);
      ev.preventDefault();
    } else if (k === "ArrowLeft" || k === "ArrowUp") {
      this._cursor = clamp(this._cursor - 1, 1, SEGMENT_COUNT);
      ev.preventDefault();
    } else if (k === "Home") {
      this._cursor = 1;
      ev.preventDefault();
    } else if (k === "End") {
      this._cursor = SEGMENT_COUNT;
      ev.preventDefault();
    } else if (k === " " || k === "Spacebar") {
      this._selection = toggleSegment(this._selection, this._cursor);
      ev.preventDefault();
    } else if (k === "Enter") {
      this._applyPaint();
      ev.preventDefault();
    } else if (k === "Escape") {
      this._dragging = false;
      this._selection = clearSelection();
      ev.preventDefault();
    }
  }

  private _selectAll(): void {
    this._selection = selectAll(SEGMENT_COUNT);
  }

  private _clear(): void {
    this._selection = clearSelection();
  }

  private _applyPaint(): void {
    const entity = this._config?.entity;
    if (!this.hass || !entity || this._selection.size === 0) return;
    const groups: SegmentGroup[] = [
      { segments: selectionToSegments(this._selection), rgb_color: hexToRgb(this._paintColor) },
    ];
    this.hass.callService(
      "ha_govee_led_ble",
      "paint_segments",
      { groups },
      { entity_id: entity },
    );
  }

  // --- colour-stop editor --------------------------------------------------

  private _addStop(): void {
    if (this._stops.length >= MAX_STOPS) return;
    const mid = sampleStops(this._stops.map(hexToRgb), 0.5);
    this._stops = [...this._stops, rgbToHex(mid)];
  }

  private _removeStop(i: number): void {
    if (this._stops.length <= MIN_STOPS) return;
    this._stops = this._stops.filter((_unused, idx) => idx !== i);
  }

  private _recolourStop(i: number, hex: string): void {
    const next = [...this._stops];
    next[i] = hex;
    this._stops = next;
  }

  private _stopTargetIndex(clientX: number): number {
    const bar = this.renderRoot.querySelector<HTMLElement>(".gradient-bar");
    if (!bar) return this._dragStop ?? 0;
    const rect = bar.getBoundingClientRect();
    const frac = clamp((clientX - rect.left) / rect.width, 0, 1);
    return clamp(Math.round(frac * (this._stops.length - 1)), 0, this._stops.length - 1);
  }

  private _startStopDrag(ev: PointerEvent, i: number): void {
    ev.preventDefault();
    this._dragStop = i;
    window.addEventListener("pointermove", this._onStopMove);
    window.addEventListener("pointerup", this._onStopUp);
  }

  private readonly _onStopMove = (ev: PointerEvent): void => {
    if (this._dragStop === null) return;
    const bar = this.renderRoot.querySelector<HTMLElement>(".gradient-bar");
    if (!bar) return;
    const rect = bar.getBoundingClientRect();
    this._dragFrac = clamp((ev.clientX - rect.left) / rect.width, 0, 1);
  };

  private readonly _onStopUp = (ev: PointerEvent): void => {
    if (this._dragStop === null) return;
    const from = this._dragStop;
    const to = this._stopTargetIndex(ev.clientX);
    if (from !== to) {
      const next = [...this._stops];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      this._stops = next;
    }
    this._dragStop = null;
    this._dragFrac = null;
    window.removeEventListener("pointermove", this._onStopMove);
    window.removeEventListener("pointerup", this._onStopUp);
  };

  private _applyGradient(): void {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    const groups = groupSegments(
      interpolateSegments(this._stops.map(hexToRgb), SEGMENT_COUNT),
    );
    this.hass.callService(
      "ha_govee_led_ble",
      "paint_segments",
      { groups },
      { entity_id: entity },
    );
  }

  // --- presets -------------------------------------------------------------

  private _applyPreset(preset: GradientPreset): void {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    this.hass.callService(
      "ha_govee_led_ble",
      "paint_segments",
      { groups: presetGroups(preset) },
      { entity_id: entity },
    );
  }

  private _presetSwatch(stops: RGB[]): string {
    if (stops.length === 1) {
      const [r, g, b] = stops[0];
      return `rgb(${r},${g},${b})`;
    }
    const parts = stops.map(
      ([r, g, b], i) => `rgb(${r},${g},${b}) ${(i / (stops.length - 1)) * 100}%`,
    );
    return `linear-gradient(90deg, ${parts.join(", ")})`;
  }

  // --- custom effects ------------------------------------------------------

  private async _saveEffect(): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    const name = this._effectName.trim();
    try {
      await this.hass.callService(
        "ha_govee_led_ble",
        "save_effect",
        { name, capture_current: true },
        { entity_id: entity },
      );
      this._effectName = "";
      this._feedback = { kind: "info", text: `Saved "${name}".` };
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private async _applyEffect(effect: CustomEffectEntry): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    this._feedback = null;
    try {
      await this.hass.callService(
        "light",
        "turn_on",
        { effect: effect.name },
        { entity_id: entity },
      );
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private _startRename(effect: CustomEffectEntry): void {
    this._feedback = null;
    this._renamingId = effect.id;
    this._renameValue = effect.name;
    void this.updateComplete.then(() => {
      const input = this.renderRoot.querySelector<HTMLInputElement>(".rename-input");
      input?.focus();
      input?.select();
    });
  }

  private _cancelRename(): void {
    this._renamingId = null;
    this._renameValue = "";
  }

  private async _commitRename(effect: CustomEffectEntry): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    const to = this._renameValue.trim();
    try {
      await this.hass.callService(
        "ha_govee_led_ble",
        "rename_effect",
        { id: effect.id, to },
        { entity_id: entity },
      );
      this._renamingId = null;
      this._renameValue = "";
      this._feedback = { kind: "info", text: `Renamed to "${to}".` };
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private async _deleteEffect(effect: CustomEffectEntry): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    if (this._renamingId === effect.id) this._cancelRename();
    try {
      await this.hass.callService(
        "ha_govee_led_ble",
        "delete_effect",
        { id: effect.id },
        { entity_id: entity },
      );
      this._feedback = { kind: "info", text: `Deleted "${effect.name}".` };
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private _onEffectNameKey(ev: KeyboardEvent): void {
    if (ev.key === "Enter") {
      ev.preventDefault();
      void this._saveEffect();
    }
  }

  private _onRenameKey(ev: KeyboardEvent, effect: CustomEffectEntry): void {
    if (ev.key === "Enter") {
      ev.preventDefault();
      void this._commitRename(effect);
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      this._cancelRename();
    }
  }

  // --- canvas preview ------------------------------------------------------

  private _tick(ts: number): void {
    if (!this._t0) this._t0 = ts;
    const canvas = this.renderRoot?.querySelector<HTMLCanvasElement>("canvas.preview");
    if (canvas) this._draw(canvas, (ts - this._t0) / 1000);
    this._raf = requestAnimationFrame((t) => this._tick(t));
  }

  private _draw(canvas: HTMLCanvasElement, elapsed: number): void {
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 480;
    const cssH = canvas.clientHeight || 44;
    if (canvas.width !== Math.round(cssW * dpr)) {
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const stops = this._stops.map(hexToRgb);
    const n = SEGMENT_COUNT;
    // Static frame under reduced motion: the resolved gradient the strip would
    // show once applied. Otherwise the palette travels for a live preview.
    const t = this._reduce ? 0 : elapsed * 0.25;
    const gap = 3;
    const cellW = (cssW - gap * (n - 1)) / n;
    for (let i = 0; i < n; i++) {
      const pos = this._reduce ? i / (n - 1) : (((i / n + t) % 1) + 1) % 1;
      const rgb = sampleStops(stops, pos);
      ctx.fillStyle = `rgb(${rgb.map((c) => Math.round(c)).join(",")})`;
      const x = i * (cellW + gap);
      ctx.beginPath();
      ctx.roundRect(x, 0, cellW, cssH, 4);
      ctx.fill();
    }
  }

  // --- render --------------------------------------------------------------

  render(): unknown {
    if (!this._config) return nothing;
    const entity = this._config.entity;
    if (!entity) {
      return this._notice("Select a light entity in the card configuration.");
    }
    const state = this.hass?.states?.[entity];
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      return this._notice(`${entity} is unavailable.`);
    }
    const segColours = this._segmentColors();
    if (!segColours) {
      return this._notice(
        `${entity} exposes no segment colours; this model has no addressable segments.`,
      );
    }
    const gradientCss = `linear-gradient(90deg, ${this._stops
      .map((c, i) => `${c} ${(i / (this._stops.length - 1)) * 100}%`)
      .join(", ")})`;

    return html`
      <ha-card header="Govee segment painter">
        <div class="body">
          ${this._renderPainter(segColours)}
          ${this._renderGradient(gradientCss)}
          ${this._renderPresets()}
          ${this._renderEffects(state)}
          ${this._renderPreview()}
        </div>
      </ha-card>
    `;
  }

  private _notice(message: string): unknown {
    return html`
      <ha-card header="Govee segment painter">
        <div class="notice">${message}</div>
      </ha-card>
    `;
  }

  private _renderPainter(segColours: RGB[]): unknown {
    const cells = [];
    for (let seg = 1; seg <= SEGMENT_COUNT; seg++) {
      const rgb = segColours[seg - 1];
      const colour = rgb ? rgbToHex(rgb) : null;
      const selected = this._selection.has(seg);
      const cursor = seg === this._cursor;
      cells.push(html`
        <div
          class="cell ${selected ? "sel" : ""} ${cursor ? "cursor" : ""} ${colour
            ? ""
            : "off"}"
          style=${colour ? `background:${colour}` : ""}
          role="option"
          aria-selected=${selected ? "true" : "false"}
          aria-label=${`Segment ${seg}`}
          title=${`Segment ${seg}`}
        >
          <span class="cell-num">${seg}</span>
        </div>
      `);
    }
    return html`
      <section>
        <div class="row heading">
          <span class="label">Segment painter</span>
          <span class="hint">${this._selection.size} selected</span>
        </div>
        <div
          class="strip"
          style="grid-template-columns: repeat(${SEGMENT_COUNT}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-label=${`Segment painter, ${SEGMENT_COUNT} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${cells}
        </div>
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(e: Event) =>
              (this._paintColor = (e.target as HTMLInputElement).value)}
          />
          <button class="btn primary" @click=${this._applyPaint}>
            Apply to selection
          </button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._clear}>Clear</button>
        </div>
      </section>
    `;
  }

  private _renderGradient(gradientCss: string): unknown {
    const n = this._stops.length;
    return html`
      <section>
        <div class="row heading">
          <span class="label">Gradient stops</span>
          <span class="hint">${n} of ${MIN_STOPS} to ${MAX_STOPS}</span>
        </div>
        <div class="gradient-bar" style="background:${gradientCss}">
          ${this._stops.map(
            (c, i) => html`
              <div
                class="handle ${this._dragStop === i ? "dragging" : ""}"
                style="left:${this._dragStop === i && this._dragFrac !== null
                  ? this._dragFrac * 100
                  : (i / (n - 1)) * 100}%;background:${c}"
                @pointerdown=${(e: PointerEvent) => this._startStopDrag(e, i)}
                title=${`Stop ${i + 1}`}
              ></div>
            `,
          )}
        </div>
        <div class="stops">
          ${this._stops.map(
            (c, i) => html`
              <div class="stop">
                <input
                  type="color"
                  aria-label=${`Stop ${i + 1} colour`}
                  .value=${c}
                  @input=${(e: Event) =>
                    this._recolourStop(i, (e.target as HTMLInputElement).value)}
                />
                <button
                  class="btn tiny"
                  ?disabled=${n <= MIN_STOPS}
                  @click=${() => this._removeStop(i)}
                  title="Remove stop"
                >
                  &times;
                </button>
              </div>
            `,
          )}
          <button
            class="btn tiny add"
            ?disabled=${n >= MAX_STOPS}
            @click=${this._addStop}
            title="Add stop"
          >
            +
          </button>
        </div>
        <div class="row controls">
          <button class="btn primary" @click=${this._applyGradient}>
            Apply gradient
          </button>
        </div>
      </section>
    `;
  }

  private _renderPresets(): unknown {
    return html`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${GRADIENT_PRESETS.map(
            (preset) => html`
              <button
                class="preset"
                @click=${() => this._applyPreset(preset)}
                title=${preset.name}
                aria-label=${preset.name}
              >
                <span
                  class="swatch"
                  style="background:${this._presetSwatch(preset.stops)}"
                ></span>
                <span class="preset-name">${preset.name}</span>
              </button>
            `,
          )}
        </div>
      </section>
    `;
  }

  private _renderPreview(): unknown {
    return html`
      <section>
        <div class="row heading">
          <span class="label">Live preview</span>
        </div>
        <canvas class="preview" height="44"></canvas>
      </section>
    `;
  }

  private _renderEffects(state: HassEntityState): unknown {
    const effects = coerceCustomEffects(state.attributes?.custom_effects);
    const active =
      typeof state.attributes?.effect === "string" ? state.attributes.effect : null;
    return html`
      <section>
        <div class="row heading">
          <span class="label">Custom effects</span>
          <span class="hint">${effects.length} saved</span>
        </div>
        <div class="row controls">
          <input
            class="effect-name"
            type="text"
            aria-label="New effect name"
            placeholder="New effect name"
            .value=${this._effectName}
            @input=${(e: Event) =>
              (this._effectName = (e.target as HTMLInputElement).value)}
            @keydown=${this._onEffectNameKey}
          />
          <button class="btn primary" @click=${this._saveEffect}>
            Save as effect
          </button>
        </div>
        <p class="help">Saves the strip's current colours as a named effect.</p>
        ${this._feedback
          ? html`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`
          : nothing}
        ${effects.length === 0
          ? html`<p class="help">No custom effects saved yet.</p>`
          : html`<ul class="effects" role="list">
              ${effects.map((effect) => this._renderEffectRow(effect, active))}
            </ul>`}
      </section>
    `;
  }

  private _renderEffectRow(effect: CustomEffectEntry, active: string | null): unknown {
    if (this._renamingId === effect.id) {
      return html`
        <li class="effect renaming">
          <input
            class="effect-name rename-input"
            type="text"
            aria-label=${`New name for ${effect.name}`}
            .value=${this._renameValue}
            @input=${(e: Event) =>
              (this._renameValue = (e.target as HTMLInputElement).value)}
            @keydown=${(e: KeyboardEvent) => this._onRenameKey(e, effect)}
          />
          <button class="btn primary" @click=${() => this._commitRename(effect)}>
            Save
          </button>
          <button class="btn" @click=${this._cancelRename}>Cancel</button>
        </li>
      `;
    }
    const isActive = active !== null && active === effect.name;
    return html`
      <li class="effect ${isActive ? "active" : ""}">
        <button
          class="btn effect-apply"
          @click=${() => this._applyEffect(effect)}
          aria-label=${`Apply ${effect.name}`}
          aria-pressed=${isActive ? "true" : "false"}
          title=${`Apply ${effect.name}`}
        >
          <span class="effect-label">${effect.name}</span>
        </button>
        <button
          class="btn"
          @click=${() => this._startRename(effect)}
          aria-label=${`Rename ${effect.name}`}
        >
          Rename
        </button>
        <button
          class="btn"
          @click=${() => this._deleteEffect(effect)}
          aria-label=${`Delete ${effect.name}`}
        >
          Delete
        </button>
      </li>
    `;
  }

  static styles = cardStyles;
}

customElements.define("govee-led-ble-card", GoveeLedBleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "govee-led-ble-card",
  name: "Govee LED BLE",
  description:
    "Drag-paint segments and edit a colour-stop gradient for the ha_govee_led_ble integration.",
  preview: false,
});

console.info(
  "%c govee-led-ble-card ",
  "background:#1982c4;color:#fff;border-radius:3px",
  "loaded",
);
