/**
 * govee-led-ble-card — "Govee Effect Studio" Lovelace card for the
 * ha_govee_led_ble integration.
 *
 * One card, three workspaces (a `role="tablist"` shell); each panel opens with
 * a scope band stating whether it touches the strip:
 *
 *   - **Now** (live) — act on the strip immediately, nothing saved. A
 *     `SEGMENT_COUNT`-cell drag/keyboard painter, a 2-to-5 stop gradient editor
 *     with an animated preview, a row of one-tap presets, and a "save the
 *     current strip as an effect" shortcut. Writes go through
 *     `ha_govee_led_ble.paint_segments`; live colour is read back from the
 *     light's `segment_colors` attribute.
 *   - **Studio** (draft) — author one reusable, typed effect at a time without
 *     touching the strip. Static and Gradient are wired end-to-end and save via
 *     `ha_govee_led_ble.save_effect(content=)`; Sketch/Flat/Combo are shown as
 *     disabled "coming next" kinds until their editors land.
 *   - **Library** — apply, rename or delete a saved effect. Applying calls the
 *     native `light.turn_on(effect=…)` so automations and voice stay
 *     first-class; deletion is a two-tap confirm.
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
  buildSegmentContent,
  buildVibrantContent,
  clamp,
  clearSelection,
  coerceCustomEffects,
  errorMessage,
  GRADIENT_PRESETS,
  groupSegments,
  hexToRgb,
  interpolateSegments,
  nextTabIndex,
  presetGroups,
  rangeSelection,
  rgbToHex,
  sampleStops,
  segmentDraftHasContent,
  selectAll,
  selectionToSegments,
  STUDIO_KINDS,
  TABS,
  toggleSegment,
  type CustomEffectEntry,
  type GradientPreset,
  type RGB,
  type SegmentGroup,
  type StudioKind,
  type TabId,
} from "./logic";

/** A transient status banner surfaced after a custom-effect service call. */
interface Feedback {
  kind: "error" | "info";
  text: string;
}

/** Default gradient palette (three evenly spaced stops). */
const DEFAULT_STOPS = ["#ff595e", "#ffca3a", "#1982c4"];
/** Default paint colour for the segment painters. */
const DEFAULT_PAINT = "#33cc66";
/** Gradient stop count bounds. */
const MIN_STOPS = 2;
const MAX_STOPS = 5;
/** Card title, shared by the live card and the unavailable/notice states. */
const CARD_TITLE = "Govee Effect Studio";
/** The Studio kinds that have a working editor this release. */
const AVAILABLE_KINDS = STUDIO_KINDS.filter((k) => k.available);
const SOON_KINDS = STUDIO_KINDS.filter((k) => !k.available);

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
    _tab: { state: true },
    _studioKind: { state: true },
    _selection: { state: true },
    _cursor: { state: true },
    _paintColor: { state: true },
    _staticColors: { state: true },
    _stops: { state: true },
    _studioStops: { state: true },
    _dragStop: { state: true },
    _dragFrac: { state: true },
    _reduce: { state: true },
    _effectName: { state: true },
    _studioName: { state: true },
    _renamingId: { state: true },
    _renameValue: { state: true },
    _deletingId: { state: true },
    _feedback: { state: true },
  };

  declare hass?: HassLike;
  declare private _config?: GoveeLedBleCardConfig;
  declare private _tab: TabId;
  declare private _studioKind: StudioKind;
  // Selection state is 1-based (segments 1..SEGMENT_COUNT) so the logic-module
  // reducers can be reused unchanged. The Now painter and the Studio Static
  // painter share it — only one is mounted at a time.
  declare private _selection: Set<number>;
  declare private _cursor: number;
  declare private _paintColor: string;
  // Studio Static draft: one hex colour per segment, or null for "unchanged".
  declare private _staticColors: (string | null)[];
  // Gradient stops are kept per-workspace: Now applies to the strip, Studio
  // saves a Vibrant effect — editing one must never disturb the other.
  declare private _stops: string[];
  declare private _studioStops: string[];
  declare private _dragStop: number | null;
  declare private _dragFrac: number | null;
  declare private _reduce: boolean;
  declare private _effectName: string;
  declare private _studioName: string;
  declare private _renamingId: string | null;
  declare private _renameValue: string;
  declare private _deletingId: string | null;
  declare private _feedback: Feedback | null;

  private _dragging = false;
  private _dragAnchor = 1;
  private _raf: number | null = null;
  private _t0 = 0;
  private _mq?: MediaQueryList;
  private _ro?: ResizeObserver;

  constructor() {
    super();
    this._tab = "now";
    this._studioKind = "static";
    this._selection = new Set();
    this._cursor = 1;
    this._paintColor = DEFAULT_PAINT;
    this._staticColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._stops = [...DEFAULT_STOPS];
    this._studioStops = [...DEFAULT_STOPS];
    this._dragStop = null;
    this._dragFrac = null;
    this._reduce = false;
    this._effectName = "";
    this._studioName = "";
    this._renamingId = null;
    this._renameValue = "";
    this._deletingId = null;
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
    return 12;
  }

  connectedCallback(): void {
    super.connectedCallback();
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    this._reduce = mq.matches;
    this._mq = mq;
    mq.addEventListener("change", this._onReduceChange);
    this._ro = new ResizeObserver(() => this._updateClipped());
    this._ro.observe(this);
    this._raf = requestAnimationFrame((ts) => this._tick(ts));
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._raf !== null) cancelAnimationFrame(this._raf);
    this._raf = null;
    this._mq?.removeEventListener("change", this._onReduceChange);
    this._ro?.disconnect();
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
    window.removeEventListener("pointermove", this._onStopMove);
    window.removeEventListener("pointerup", this._onStopUp);
  }

  updated(): void {
    this._updateClipped();
  }

  /** Flag any strip whose content overflows its scroll box, so the fade cue shows. */
  private _updateClipped(): void {
    for (const el of this.renderRoot.querySelectorAll<HTMLElement>(".strip-scroll")) {
      el.classList.toggle("clipped", el.scrollWidth > el.clientWidth + 1);
    }
  }

  private readonly _onReduceChange = (ev: MediaQueryListEvent): void => {
    this._reduce = ev.matches;
  };

  // --- shell: tabs --------------------------------------------------------

  private _selectTab(tab: TabId): void {
    if (this._tab === tab) return;
    this._tab = tab;
    // The painter selection is per-workspace; drop it so a stale highlight
    // never carries between Now and Studio.
    this._selection = clearSelection();
    this._cursor = 1;
  }

  private _onTabKey(ev: KeyboardEvent): void {
    const idx = TABS.findIndex((t) => t.id === this._tab);
    const next = nextTabIndex(idx, ev.key, TABS.length);
    if (next === idx) return;
    ev.preventDefault();
    this._selectTab(TABS[next].id);
    void this.updateComplete.then(() => {
      this.renderRoot
        .querySelector<HTMLButtonElement>(`#tab-${TABS[next].id}`)
        ?.focus();
    });
  }

  private _selectKind(kind: StudioKind): void {
    this._studioKind = kind;
  }

  private _onKindKey(ev: KeyboardEvent): void {
    const idx = AVAILABLE_KINDS.findIndex((k) => k.id === this._studioKind);
    const next = nextTabIndex(idx, ev.key, AVAILABLE_KINDS.length);
    if (next === idx) return;
    ev.preventDefault();
    this._studioKind = AVAILABLE_KINDS[next].id;
    void this.updateComplete.then(() => {
      this.renderRoot
        .querySelector<HTMLButtonElement>('.kinds .kind[aria-checked="true"]')
        ?.focus();
    });
  }

  // --- live per-segment read-back -----------------------------------------

  private _segmentColors(): RGB[] | null {
    const entity = this._config?.entity;
    if (!entity || !this.hass) return null;
    const state = this.hass.states[entity];
    if (!state) return null;
    return coerceSegmentColors(state.attributes?.segment_colors);
  }

  // --- segment painter: pointer drag (shared by Now + Studio Static) ------

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
    const moveKeys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
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
      if (this._tab === "studio") this._paintStatic();
      else this._applyPaint();
      ev.preventDefault();
    } else if (k === "Escape") {
      this._dragging = false;
      this._selection = clearSelection();
      ev.preventDefault();
    }
    if (moveKeys.includes(k)) this._scrollCursorIntoView();
  }

  /** Keep the keyboard cursor cell visible when the strip scrolls on narrow cards. */
  private _scrollCursorIntoView(): void {
    void this.updateComplete.then(() => {
      this.renderRoot
        .querySelector<HTMLElement>(".cell.cursor")
        ?.scrollIntoView({ inline: "nearest", block: "nearest" });
    });
  }

  private _selectAll(): void {
    this._selection = selectAll(SEGMENT_COUNT);
  }

  private _clear(): void {
    this._selection = clearSelection();
  }

  // --- Now painter: apply to the live strip -------------------------------

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

  // --- Studio Static: paint into the draft (never touches the strip) ------

  private _paintStatic(): void {
    if (this._selection.size === 0) return;
    const next = [...this._staticColors];
    for (const seg of this._selection) next[seg - 1] = this._paintColor;
    this._staticColors = next;
  }

  private _setUnchangedStatic(): void {
    if (this._selection.size === 0) return;
    const next = [...this._staticColors];
    for (const seg of this._selection) next[seg - 1] = null;
    this._staticColors = next;
  }

  private _resetStatic(): void {
    this._staticColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._selection = clearSelection();
  }

  // --- colour-stop editor (shared markup over per-workspace stops) --------

  /** The stops the mounted editor edits: Studio Gradient's draft, else Now's. */
  private _activeStops(): string[] {
    return this._tab === "studio" ? this._studioStops : this._stops;
  }

  private _setActiveStops(next: string[]): void {
    if (this._tab === "studio") this._studioStops = next;
    else this._stops = next;
  }

  private _addStop(): void {
    const stops = this._activeStops();
    if (stops.length >= MAX_STOPS) return;
    const mid = sampleStops(stops.map(hexToRgb), 0.5);
    this._setActiveStops([...stops, rgbToHex(mid)]);
  }

  private _removeStop(i: number): void {
    const stops = this._activeStops();
    if (stops.length <= MIN_STOPS) return;
    this._setActiveStops(stops.filter((_unused, idx) => idx !== i));
  }

  private _recolourStop(i: number, hex: string): void {
    const next = [...this._activeStops()];
    next[i] = hex;
    this._setActiveStops(next);
  }

  private _stopTargetIndex(clientX: number): number {
    const bar = this.renderRoot.querySelector<HTMLElement>(".gradient-bar");
    const stops = this._activeStops();
    if (!bar) return this._dragStop ?? 0;
    const rect = bar.getBoundingClientRect();
    const frac = clamp((clientX - rect.left) / rect.width, 0, 1);
    return clamp(Math.round(frac * (stops.length - 1)), 0, stops.length - 1);
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
      const next = [...this._activeStops()];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      this._setActiveStops(next);
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

  // --- custom effects: save (Now capture + Studio author) -----------------

  /** Now tab: snapshot the current strip as a named effect. */
  private async _saveCurrent(): Promise<void> {
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

  /** Studio tab: mint a typed effect from the active kind's draft. */
  private async _saveStudio(): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    const name = this._studioName.trim();
    const content =
      this._studioKind === "static"
        ? buildSegmentContent(
            this._staticColors.map((c) => (c === null ? null : hexToRgb(c))),
          )
        : buildVibrantContent(this._studioStops.map(hexToRgb));
    try {
      await this.hass.callService(
        "ha_govee_led_ble",
        "save_effect",
        { name, content },
        { entity_id: entity },
      );
      this._studioName = "";
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
    this._deletingId = null;
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

  private _askDelete(effect: CustomEffectEntry): void {
    this._feedback = null;
    if (this._renamingId === effect.id) this._cancelRename();
    this._deletingId = effect.id;
    void this.updateComplete.then(() => {
      this.renderRoot.querySelector<HTMLButtonElement>(".confirm-cancel")?.focus();
    });
  }

  private _cancelDelete(): void {
    this._deletingId = null;
  }

  private _onDeleteKey(ev: KeyboardEvent): void {
    if (ev.key === "Escape") {
      ev.preventDefault();
      this._cancelDelete();
    }
  }

  private async _deleteEffect(effect: CustomEffectEntry): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    this._deletingId = null;
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

  private _onSaveKey(ev: KeyboardEvent, save: () => void): void {
    if (ev.key === "Enter") {
      ev.preventDefault();
      save();
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

  // --- canvas preview (Now gradient) --------------------------------------

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

    return html`
      <ha-card>
        ${this._renderHeader(state)}
        <div class="body">
          ${this._tab === "now" ? this._renderNow(segColours) : nothing}
          ${this._tab === "studio" ? this._renderStudio() : nothing}
          ${this._tab === "library" ? this._renderLibrary(state) : nothing}
        </div>
      </ha-card>
    `;
  }

  private _notice(message: string): unknown {
    return html`
      <ha-card header=${CARD_TITLE}>
        <div class="notice">${message}</div>
      </ha-card>
    `;
  }

  private _renderHeader(state: HassEntityState): unknown {
    const effect =
      typeof state.attributes?.effect === "string" && state.attributes.effect !== ""
        ? state.attributes.effect
        : state.state === "on"
          ? "Colour"
          : "Off";
    return html`
      <div class="card-head">
        <div class="title">${CARD_TITLE}</div>
        <div class="status">
          <span>Current:</span>
          <span class="current">${effect}</span>
        </div>
        <div class="tabs" role="tablist" aria-label="Effect Studio sections">
          ${TABS.map(
            (t) => html`
              <button
                class="tab ${this._tab === t.id ? "active" : ""}"
                id=${`tab-${t.id}`}
                role="tab"
                aria-selected=${this._tab === t.id ? "true" : "false"}
                aria-controls=${`panel-${t.id}`}
                tabindex=${this._tab === t.id ? "0" : "-1"}
                @click=${() => this._selectTab(t.id)}
                @keydown=${this._onTabKey}
              >
                ${t.label}
              </button>
            `,
          )}
        </div>
        ${this._feedback
          ? html`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`
          : nothing}
      </div>
    `;
  }

  private _renderScopeBand(mode: "live" | "draft"): unknown {
    const text =
      mode === "live"
        ? "Applies to the strip — changes show instantly"
        : "Draft — builds a saved effect and never changes the strip";
    return html`
      <div class="scope-band ${mode}" role="note">
        <span class="dot" aria-hidden="true"></span>
        <span>${text}</span>
      </div>
    `;
  }

  // --- Now workspace -------------------------------------------------------

  private _renderNow(segColours: RGB[]): unknown {
    const cellColours = Array.from({ length: SEGMENT_COUNT }, (_unused, i) => {
      const rgb = segColours[i];
      return rgb ? rgbToHex(rgb) : null;
    });
    return html`
      <div id="panel-now" role="tabpanel" aria-labelledby="tab-now">
        ${this._renderScopeBand("live")}
        <section>
          <div class="row heading">
            <span class="label">Segment painter</span>
            <span class="hint">${this._selection.size} selected</span>
          </div>
          ${this._renderStrip(cellColours, "off")}
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
        ${this._renderGradient()}
        ${this._renderPresets()}
        ${this._renderSaveCurrent()}
      </div>
    `;
  }

  private _renderStrip(colours: (string | null)[], nullClass: "off" | "unchanged"): unknown {
    const cells = [];
    for (let seg = 1; seg <= SEGMENT_COUNT; seg++) {
      const colour = colours[seg - 1] ?? null;
      const selected = this._selection.has(seg);
      const cursor = seg === this._cursor;
      const stateWord = colour ? "painted" : nullClass === "off" ? "off" : "unchanged";
      cells.push(html`
        <div
          class="cell ${selected ? "sel" : ""} ${cursor ? "cursor" : ""} ${colour
            ? ""
            : nullClass}"
          style=${colour ? `background:${colour}` : ""}
          role="option"
          aria-selected=${selected ? "true" : "false"}
          aria-label=${`Segment ${seg}, ${stateWord}`}
          title=${`Segment ${seg}`}
        >
          <span class="cell-num">${seg}</span>
        </div>
      `);
    }
    return html`
      <div class="strip-scroll">
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
      </div>
    `;
  }

  private _renderGradient(): unknown {
    return html`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Gradient preview</span>
        </div>
        <canvas class="preview" height="44"></canvas>
        <div class="row controls">
          <button class="btn primary" @click=${this._applyGradient}>
            Apply gradient
          </button>
        </div>
      </section>
    `;
  }

  private _renderStopEditor(): unknown {
    const stops = this._activeStops();
    const n = stops.length;
    const gradientCss = `linear-gradient(90deg, ${stops
      .map((c, i) => `${c} ${(i / (n - 1)) * 100}%`)
      .join(", ")})`;
    return html`
      <div class="row heading">
        <span class="label">Gradient stops</span>
        <span class="hint">${n} of ${MIN_STOPS} to ${MAX_STOPS}</span>
      </div>
      <div class="gradient-track">
        <div class="gradient-bar" style="background:${gradientCss}">
          ${stops.map(
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
      </div>
      <div class="stops">
        ${stops.map(
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
                aria-label=${`Remove stop ${i + 1}`}
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
          aria-label="Add stop"
          title="Add stop"
        >
          +
        </button>
      </div>
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

  private _renderSaveCurrent(): unknown {
    return html`
      <section>
        <div class="row heading">
          <span class="label">Save current</span>
        </div>
        <div class="row controls">
          <input
            class="effect-name"
            type="text"
            aria-label="New effect name"
            placeholder="Name this look"
            .value=${this._effectName}
            @input=${(e: Event) =>
              (this._effectName = (e.target as HTMLInputElement).value)}
            @keydown=${(e: KeyboardEvent) => this._onSaveKey(e, () => void this._saveCurrent())}
          />
          <button
            class="btn primary"
            ?disabled=${this._effectName.trim() === ""}
            @click=${this._saveCurrent}
          >
            Save current as effect
          </button>
        </div>
        <p class="help">Snapshots the strip's current colours as a named effect.</p>
      </section>
    `;
  }

  // --- Studio workspace ----------------------------------------------------

  private _renderStudio(): unknown {
    return html`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${AVAILABLE_KINDS.map(
              (k) => html`
                <button
                  class="kind ${this._studioKind === k.id ? "active" : ""}"
                  role="radio"
                  aria-checked=${this._studioKind === k.id ? "true" : "false"}
                  tabindex=${this._studioKind === k.id ? "0" : "-1"}
                  @click=${() => this._selectKind(k.id)}
                >
                  ${k.label}
                </button>
              `,
            )}
          </div>
          <div class="kinds-soon">
            <span>Coming next:</span>
            ${SOON_KINDS.map(
              (k) => html`
                <button class="kind soon" disabled aria-disabled="true">
                  ${k.label}<span class="soon-tag">soon</span>
                </button>
              `,
            )}
          </div>
        </section>
        ${this._studioKind === "gradient" ? this._renderGradientAuthor() : this._renderStaticEditor()}
      </div>
    `;
  }

  private _renderStaticEditor(): unknown {
    const painted = this._staticColors.filter((c) => c !== null).length;
    const hasContent = segmentDraftHasContent(
      this._staticColors.map((c) => (c === null ? null : hexToRgb(c))),
    );
    return html`
      <section>
        <div class="row heading">
          <span class="label">Static segments</span>
          <span class="hint">${painted} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._staticColors, "unchanged")}
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(e: Event) =>
              (this._paintColor = (e.target as HTMLInputElement).value)}
          />
          <button class="btn primary" @click=${this._paintStatic}>Paint selected</button>
          <button class="btn" @click=${this._setUnchangedStatic}>Clear selected</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetStatic}>Reset</button>
        </div>
        <p class="help">
          Paint a colour onto chosen segments; hatched segments are left as they are on the strip.
        </p>
        ${this._renderStudioSave(hasContent, "Paint at least one segment to save.")}
      </section>
    `;
  }

  private _renderGradientAuthor(): unknown {
    const resolved = interpolateSegments(
      this._studioStops.map(hexToRgb),
      SEGMENT_COUNT,
    ).map(rgbToHex);
    return html`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Draft preview · ${SEGMENT_COUNT} segments</span>
        </div>
        ${this._renderPreviewStrip(resolved)}
        <p class="help">Saves the colour stops as a gradient effect.</p>
        ${this._renderStudioSave(true, "")}
      </section>
    `;
  }

  private _renderPreviewStrip(colours: string[]): unknown {
    return html`
      <div class="strip-scroll">
        <div
          class="strip preview-strip"
          style="grid-template-columns: repeat(${SEGMENT_COUNT}, 1fr)"
          aria-hidden="true"
        >
          ${colours.map(
            (c, i) => html`
              <div class="cell" style="background:${c}" title=${`Segment ${i + 1}`}>
                <span class="cell-num">${i + 1}</span>
              </div>
            `,
          )}
        </div>
      </div>
    `;
  }

  private _renderStudioSave(canSave: boolean, disabledHint: string): unknown {
    const named = this._studioName.trim() !== "";
    return html`
      <div class="row controls">
        <input
          class="effect-name"
          type="text"
          aria-label="Effect name"
          placeholder="Name this effect"
          .value=${this._studioName}
          @input=${(e: Event) =>
            (this._studioName = (e.target as HTMLInputElement).value)}
          @keydown=${(e: KeyboardEvent) => this._onSaveKey(e, () => void this._saveStudio())}
        />
        <button
          class="btn primary"
          ?disabled=${!named || !canSave}
          @click=${this._saveStudio}
        >
          Save effect
        </button>
      </div>
      ${!canSave && disabledHint !== ""
        ? html`<p class="help">${disabledHint}</p>`
        : nothing}
    `;
  }

  // --- Library workspace ---------------------------------------------------

  private _renderLibrary(state: HassEntityState): unknown {
    const effects = coerceCustomEffects(state.attributes?.custom_effects);
    const active =
      typeof state.attributes?.effect === "string" ? state.attributes.effect : null;
    return html`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${effects.length} saved</span>
          </div>
          ${effects.length === 0
            ? html`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`
            : html`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${effects.map((effect) => this._renderEffectRow(effect, active))}
                </ul>
              `}
        </section>
      </div>
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
    if (this._deletingId === effect.id) {
      return html`
        <li class="effect">
          <span class="confirm-text">Delete "${effect.name}"?</span>
          <button
            class="btn confirm-cancel"
            @click=${this._cancelDelete}
            @keydown=${this._onDeleteKey}
          >
            Cancel
          </button>
          <button
            class="btn danger primary"
            @click=${() => this._deleteEffect(effect)}
            @keydown=${this._onDeleteKey}
          >
            Delete
          </button>
        </li>
      `;
    }
    const isActive = active !== null && active === effect.name;
    return html`
      <li class="effect ${isActive ? "active" : ""}">
        ${isActive
          ? html`<span class="badge-active" aria-current="true">✓ Active</span>`
          : html`<button
              class="btn primary"
              @click=${() => this._applyEffect(effect)}
              aria-label=${`Apply ${effect.name}`}
            >
              Apply
            </button>`}
        <span class="effect-label" title=${effect.name}>${effect.name}</span>
        <button
          class="btn"
          @click=${() => this._startRename(effect)}
          aria-label=${`Rename ${effect.name}`}
        >
          Rename
        </button>
        <button
          class="btn danger"
          @click=${() => this._askDelete(effect)}
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
    "Paint, compose and save custom effects for a segment-capable Govee LED BLE light.",
  preview: false,
});

console.info(
  "%c govee-led-ble-card ",
  "background:#1982c4;color:#fff;border-radius:3px",
  "loaded",
);
