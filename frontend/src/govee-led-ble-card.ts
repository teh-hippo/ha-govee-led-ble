/**
 * govee-led-ble-card — "Govee Effect Studio" Lovelace card for the
 * ha_govee_led_ble integration.
 *
 * One card, three workspaces (a `role="tablist"` shell); each panel opens with
 * a scope band stating whether it touches the strip:
 *
 *   - **Now** (live) — act on the strip immediately, nothing saved. A
 *     `SEGMENT_COUNT`-cell drag/keyboard painter, a 2-to-5 stop gradient editor
 *     with an exact static preview, a row of one-tap presets, and a "save the
 *     current strip as an effect" shortcut. Writes go through
 *     `ha_govee_led_ble.paint_segments`; live colour is read back from the
 *     light's `segment_colors` attribute.
 *   - **Studio** (draft) — author one reusable, typed effect at a time without
 *     touching the strip. Static, Gradient, Sketch, Flat and Combo are wired
 *     end-to-end and save via `ha_govee_led_ble.save_effect(content=)`.
 *   - **Library** — apply, edit, duplicate, rename, delete, export or import a
 *     saved effect. Applying calls the native `light.turn_on(effect=…)` so
 *     automations and voice stay first-class; deletion is a two-tap confirm.
 *
 * All maths lives in `./logic` (pure, unit-tested for numeric parity with the
 * integration). lit is vendored (`../vendor/lit.js`) and inlined by `bun build`,
 * so the Home Assistant runtime needs no npm packages. Styling uses Home
 * Assistant theme tokens only; the sole bespoke CSS is layout.
 */

import { LitElement, html, nothing } from "../vendor/lit.js";
import { cardStyles } from "./card-styles";
import "./card-editor";
import {
  buildComboContent,
  buildEffectExchangeDocument,
  buildFlatContent,
  buildSketchContent,
  effectFileName,
  FLAT_CATALOGUE,
  flatFamilyByCode,
  flatVariantLabel,
  parseEffectExchangeJson,
  parseEntityExportResponse,
  parseEntityRawExportResponse,
  resolveImportName,
  sketchPreviewColors,
  SKETCH_MOTIONS,
  studioKindForContent,
  suggestDuplicateName,
  type EffectContentDict,
} from "./effect-exchange";
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
  supportedStudioKinds,
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

interface ComboStep {
  family: number;
  variant: number;
}

interface PendingDraft {
  name: string;
  content: EffectContentDict;
  editingId: string | null;
  feedback: string;
  clearImport: boolean;
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

function createDownloadAnchor(fileName: string, url: string): HTMLAnchorElement {
  const anchor = window.document.createElement("a");
  anchor.download = fileName;
  anchor.href = url;
  return anchor;
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
    _staticBrightness: { state: true },
    _sketchColors: { state: true },
    _sketchMotion: { state: true },
    _sketchSpeed: { state: true },
    _sketchBrightness: { state: true },
    _sketchBackground: { state: true },
    _flatFamily: { state: true },
    _flatVariant: { state: true },
    _flatSpeed: { state: true },
    _flatPalette: { state: true },
    _comboEffects: { state: true },
    _comboVariant: { state: true },
    _comboSpeed: { state: true },
    _comboPalette: { state: true },
    _stops: { state: true },
    _studioStops: { state: true },
    _dragStop: { state: true },
    _dragFrac: { state: true },
    _effectName: { state: true },
    _studioName: { state: true },
    _editingId: { state: true },
    _loadedContent: { state: true },
    _pendingDraft: { state: true },
    _importText: { state: true },
    _busyKey: { state: true },
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
  // Brightness is not yet directly edited, but imported values must survive an edit.
  declare private _staticBrightness: (number | null)[] | null;
  declare private _sketchColors: (string | null)[];
  declare private _sketchMotion: number;
  declare private _sketchSpeed: number;
  declare private _sketchBrightness: number;
  declare private _sketchBackground: string;
  declare private _flatFamily: number;
  declare private _flatVariant: number;
  declare private _flatSpeed: number;
  declare private _flatPalette: string[];
  declare private _comboEffects: ComboStep[];
  declare private _comboVariant: number;
  declare private _comboSpeed: number;
  declare private _comboPalette: string[];
  // Gradient stops are kept per-workspace: Now applies to the strip, Studio
  // saves a Vibrant effect — editing one must never disturb the other.
  declare private _stops: string[];
  declare private _studioStops: string[];
  declare private _dragStop: number | null;
  declare private _dragFrac: number | null;
  declare private _effectName: string;
  declare private _studioName: string;
  declare private _editingId: string | null;
  declare private _loadedContent: EffectContentDict | null;
  declare private _pendingDraft: PendingDraft | null;
  declare private _importText: string;
  declare private _busyKey: string | null;
  declare private _renamingId: string | null;
  declare private _renameValue: string;
  declare private _deletingId: string | null;
  declare private _feedback: Feedback | null;

  private _dragging = false;
  private _dragAnchor = 1;
  private _touchStart: { x: number; y: number; cell: number } | null = null;
  private _ro?: ResizeObserver;
  private _draftBaseline = "";
  private _editingOriginalName: string | null = null;
  private _editingOriginalContent: string | null = null;

  constructor() {
    super();
    this._tab = "now";
    this._studioKind = "static";
    this._selection = new Set();
    this._cursor = 1;
    this._paintColor = DEFAULT_PAINT;
    this._staticColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._staticBrightness = null;
    this._sketchColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._sketchMotion = 0x09;
    this._sketchSpeed = 51;
    this._sketchBrightness = 100;
    this._sketchBackground = "#000000";
    this._flatFamily = FLAT_CATALOGUE[0].family;
    this._flatVariant = FLAT_CATALOGUE[0].variants[0].variant;
    this._flatSpeed = 50;
    this._flatPalette = [...DEFAULT_STOPS];
    this._comboEffects = [
      {
        family: FLAT_CATALOGUE[0].family,
        variant: FLAT_CATALOGUE[0].variants[0].variant,
      },
    ];
    this._comboVariant = 0;
    this._comboSpeed = 50;
    this._comboPalette = [...DEFAULT_STOPS];
    this._stops = [...DEFAULT_STOPS];
    this._studioStops = [...DEFAULT_STOPS];
    this._dragStop = null;
    this._dragFrac = null;
    this._effectName = "";
    this._studioName = "";
    this._editingId = null;
    this._loadedContent = null;
    this._pendingDraft = null;
    this._importText = "";
    this._busyKey = null;
    this._renamingId = null;
    this._renameValue = "";
    this._deletingId = null;
    this._feedback = null;
    this._draftBaseline = this._draftSignature();
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
    this._ro = new ResizeObserver(() => {
      this._updateClipped();
      this._drawNowPreview();
    });
    this._ro.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._ro?.disconnect();
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
    window.removeEventListener("pointercancel", this._onUp);
    window.removeEventListener("pointerup", this._onTouchUp);
    window.removeEventListener("pointercancel", this._onTouchCancel);
    window.removeEventListener("pointermove", this._onStopMove);
    window.removeEventListener("pointerup", this._onStopUp);
  }

  updated(): void {
    this._ensureSupportedStudioKind();
    this._reconcileDraftIds();
    this._updateClipped();
    this._drawNowPreview();
  }

  private _reconcileDraftIds(): void {
    const entity = this._config?.entity;
    const state = entity ? this.hass?.states[entity] : undefined;
    if (!state) return;
    const effects = coerceCustomEffects(state.attributes?.custom_effects);
    const ids = new Set(effects.map((effect) => effect.id));
    if (this._editingId !== null) {
      const current = effects.find((effect) => effect.id === this._editingId);
      if (current === undefined) {
        this._editingId = null;
        this._editingOriginalName = null;
        this._editingOriginalContent = null;
        this._draftBaseline = "";
        this._feedback = {
          kind: "info",
          text: "The saved effect was removed elsewhere. Its Studio draft is now a new effect.",
        };
      } else if (
        this._editingOriginalName !== null &&
        this._studioName.trim() === this._editingOriginalName &&
        current.name !== this._editingOriginalName
      ) {
        const contentUnchanged =
          this._currentContentSignature() === this._editingOriginalContent;
        this._studioName = current.name;
        this._editingOriginalName = current.name;
        if (contentUnchanged) this._draftBaseline = this._draftSignature();
      }
    }
    if (
      this._pendingDraft?.editingId !== null &&
      this._pendingDraft?.editingId !== undefined &&
      !ids.has(this._pendingDraft.editingId)
    ) {
      this._pendingDraft = {
        ...this._pendingDraft,
        editingId: null,
        feedback:
          "The saved effect was removed elsewhere. Its loaded content will open as a new draft.",
      };
    }
  }

  /** Flag any strip whose content overflows its scroll box, so the fade cue shows. */
  private _updateClipped(): void {
    for (const el of this.renderRoot.querySelectorAll<HTMLElement>(".strip-scroll")) {
      el.classList.toggle("clipped", el.scrollWidth > el.clientWidth + 1);
    }
  }

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

  private _draftSignature(): string {
    const common = { kind: this._studioKind, name: this._studioName };
    switch (this._studioKind) {
      case "static":
        return JSON.stringify({
          ...common,
          colors: this._staticColors,
          brightness: this._staticBrightness,
        });
      case "gradient":
        return JSON.stringify({ ...common, stops: this._studioStops });
      case "sketch":
        return JSON.stringify({
          ...common,
          colors: this._sketchColors,
          motion: this._sketchMotion,
          speed: this._sketchSpeed,
          brightness: this._sketchBrightness,
          background: this._sketchBackground,
        });
      case "flat":
        return JSON.stringify({
          ...common,
          family: this._flatFamily,
          variant: this._flatVariant,
          speed: this._flatSpeed,
          palette: this._flatPalette,
        });
      case "combo":
        return JSON.stringify({
          ...common,
          effects: this._comboEffects,
          variant: this._comboVariant,
          speed: this._comboSpeed,
          palette: this._comboPalette,
        });
    }
  }

  private _hasUnsavedDraft(): boolean {
    return this._draftSignature() !== this._draftBaseline;
  }

  private _selectKind(kind: StudioKind): void {
    if (!this._supportedStudioKinds().includes(kind)) return;
    if (this._editingId !== null && kind !== this._studioKind) return;
    const wasDirty = this._hasUnsavedDraft();
    this._studioKind = kind;
    this._loadedContent = null;
    if (!wasDirty && this._editingId === null) {
      this._draftBaseline = this._draftSignature();
    }
  }

  private _onKindKey(ev: KeyboardEvent): void {
    if (this._editingId !== null) return;
    const available = this._availableKindDescriptors();
    const idx = available.findIndex((kind) => kind.id === this._studioKind);
    const next = nextTabIndex(idx, ev.key, available.length);
    if (next === idx) return;
    ev.preventDefault();
    this._selectKind(available[next].id);
    void this.updateComplete.then(() => {
      this.renderRoot
        .querySelector<HTMLButtonElement>('.kinds .kind[aria-checked="true"]')
        ?.focus();
    });
  }

  private _focusChecked(selector: string): void {
    void this.updateComplete.then(() => {
      this.renderRoot
        .querySelector<HTMLButtonElement>(`${selector}[aria-checked="true"]`)
        ?.focus();
    });
  }

  private _onMotionKey(ev: KeyboardEvent): void {
    const codes = SKETCH_MOTIONS.map((motion) => motion.code);
    const index = codes.indexOf(this._sketchMotion);
    const next = nextTabIndex(index, ev.key, codes.length);
    if (next === index) return;
    ev.preventDefault();
    this._sketchMotion = codes[next];
    this._focusChecked(".motion");
  }

  private _onFlatFamilyKey(ev: KeyboardEvent): void {
    const families = FLAT_CATALOGUE.map((family) => family.family);
    const index = families.indexOf(this._flatFamily);
    const next = nextTabIndex(index, ev.key, families.length);
    if (next === index) return;
    ev.preventDefault();
    this._selectFlatFamily(families[next]);
    this._focusChecked(".family");
  }

  private _onFlatVariantKey(ev: KeyboardEvent): void {
    const variants = flatFamilyByCode(this._flatFamily).variants.map(
      (variant) => variant.variant,
    );
    const index = variants.indexOf(this._flatVariant);
    const next = nextTabIndex(index, ev.key, variants.length);
    if (next === index) return;
    ev.preventDefault();
    this._flatVariant = variants[next];
    this._focusChecked(".variant");
  }

  // --- live per-segment read-back -----------------------------------------

  private _segmentColors(): RGB[] | null {
    const entity = this._config?.entity;
    if (!entity || !this.hass) return null;
    const state = this.hass.states[entity];
    if (!state) return null;
    return coerceSegmentColors(state.attributes?.segment_colors);
  }

  private _supportedStudioKinds(): StudioKind[] {
    const entity = this._config?.entity;
    const raw = entity
      ? this.hass?.states[entity]?.attributes?.custom_effect_kinds
      : undefined;
    return supportedStudioKinds(raw);
  }

  private _availableKindDescriptors(): (typeof STUDIO_KINDS)[number][] {
    const supported = new Set(this._supportedStudioKinds());
    return STUDIO_KINDS.filter((kind) => kind.available && supported.has(kind.id));
  }

  private _isStudioKindSupported(kind: StudioKind): boolean {
    return this._supportedStudioKinds().includes(kind);
  }

  private _ensureSupportedStudioKind(): void {
    if (this._isStudioKindSupported(this._studioKind)) return;
    const [fallback] = this._supportedStudioKinds();
    if (fallback === undefined) return;
    this._editingId = null;
    this._editingOriginalName = null;
    this._editingOriginalContent = null;
    this._loadedContent = null;
    this._studioKind = fallback;
    this._draftBaseline = this._draftSignature();
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
    if (ev.pointerType === "touch") {
      this._touchStart = {
        x: ev.clientX,
        y: ev.clientY,
        cell: this._cellFromClientX(ev.clientX),
      };
      window.addEventListener("pointerup", this._onTouchUp);
      window.addEventListener("pointercancel", this._onTouchCancel);
      return;
    }
    ev.preventDefault();
    this._dragging = true;
    this._dragAnchor = this._cellFromClientX(ev.clientX);
    this._cursor = this._dragAnchor;
    this._selection = new Set([this._dragAnchor]);
    this.renderRoot.querySelector<HTMLElement>(".strip")?.focus();
    window.addEventListener("pointermove", this._onMove);
    window.addEventListener("pointerup", this._onUp);
    window.addEventListener("pointercancel", this._onUp);
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
    window.removeEventListener("pointercancel", this._onUp);
  };

  private readonly _onTouchUp = (ev: PointerEvent): void => {
    const start = this._touchStart;
    this._clearTouchGesture();
    if (
      start === null ||
      Math.hypot(ev.clientX - start.x, ev.clientY - start.y) > 10
    ) {
      return;
    }
    this._cursor = start.cell;
    this._selection = toggleSegment(this._selection, start.cell);
  };

  private readonly _onTouchCancel = (): void => {
    this._clearTouchGesture();
  };

  private _clearTouchGesture(): void {
    this._touchStart = null;
    window.removeEventListener("pointerup", this._onTouchUp);
    window.removeEventListener("pointercancel", this._onTouchCancel);
  }

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
      if (this._tab === "studio") this._paintActiveDraft();
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

  private _paintSketch(): void {
    if (this._selection.size === 0) return;
    const next = [...this._sketchColors];
    for (const seg of this._selection) next[seg - 1] = this._paintColor;
    this._sketchColors = next;
  }

  private _paintActiveDraft(): void {
    if (this._studioKind === "sketch") this._paintSketch();
    else this._paintStatic();
  }

  private _setUnchangedStatic(): void {
    if (this._selection.size === 0) return;
    const next = [...this._staticColors];
    for (const seg of this._selection) next[seg - 1] = null;
    this._staticColors = next;
  }

  private _clearSketchSelection(): void {
    if (this._selection.size === 0) return;
    const next = [...this._sketchColors];
    for (const seg of this._selection) next[seg - 1] = null;
    this._sketchColors = next;
  }

  private _resetStatic(): void {
    this._staticColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._staticBrightness = null;
    this._selection = clearSelection();
    this._finishDraftReset();
  }

  private _resetSketch(): void {
    this._sketchColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._sketchMotion = 0x09;
    this._sketchSpeed = 51;
    this._sketchBrightness = 100;
    this._sketchBackground = "#000000";
    this._selection = clearSelection();
    this._finishDraftReset();
  }

  private _selectFlatFamily(family: number): void {
    const entry = flatFamilyByCode(family);
    if (this._flatPalette.length > entry.palette_max) {
      this._feedback = {
        kind: "error",
        text: `${entry.label} accepts up to ${entry.palette_max} colours. Remove some first.`,
      };
      return;
    }
    this._flatFamily = family;
    this._flatVariant = entry.variants[0].variant;
    this._feedback = null;
  }

  private _setFlatPaletteColour(index: number, value: string): void {
    const next = [...this._flatPalette];
    next[index] = value;
    this._flatPalette = next;
  }

  private _addFlatPaletteColour(): void {
    const max = flatFamilyByCode(this._flatFamily).palette_max;
    if (this._flatPalette.length >= max) return;
    this._flatPalette = [...this._flatPalette, DEFAULT_PAINT];
  }

  private _removeFlatPaletteColour(index: number): void {
    this._flatPalette = this._flatPalette.filter((_colour, current) => current !== index);
  }

  private _moveFlatPaletteColour(index: number, delta: -1 | 1): void {
    const target = index + delta;
    if (target < 0 || target >= this._flatPalette.length) return;
    const next = [...this._flatPalette];
    [next[index], next[target]] = [next[target], next[index]];
    this._flatPalette = next;
  }

  private _resetFlat(): void {
    this._flatFamily = FLAT_CATALOGUE[0].family;
    this._flatVariant = FLAT_CATALOGUE[0].variants[0].variant;
    this._flatSpeed = 50;
    this._flatPalette = [...DEFAULT_STOPS];
    this._finishDraftReset();
  }

  private _setComboFamily(index: number, family: number): void {
    const entry = flatFamilyByCode(family);
    this._comboEffects = this._comboEffects.map((step, current) =>
      current === index
        ? { family, variant: entry.variants[0].variant }
        : step,
    );
  }

  private _setComboVariant(index: number, variant: number): void {
    const step = this._comboEffects[index];
    flatVariantLabel(step.family, variant);
    this._comboEffects = this._comboEffects.map((entry, current) =>
      current === index ? { ...entry, variant } : entry,
    );
  }

  private _addComboStep(): void {
    if (this._comboEffects.length >= 4) return;
    const family = FLAT_CATALOGUE[0];
    this._comboEffects = [
      ...this._comboEffects,
      { family: family.family, variant: family.variants[0].variant },
    ];
  }

  private _removeComboStep(index: number): void {
    this._comboEffects = this._comboEffects.filter(
      (_step, current) => current !== index,
    );
  }

  private _moveComboStep(index: number, delta: -1 | 1): void {
    const target = index + delta;
    if (target < 0 || target >= this._comboEffects.length) return;
    const next = [...this._comboEffects];
    [next[index], next[target]] = [next[target], next[index]];
    this._comboEffects = next;
  }

  private _setComboPaletteColour(index: number, value: string): void {
    const next = [...this._comboPalette];
    next[index] = value;
    this._comboPalette = next;
  }

  private _addComboPaletteColour(): void {
    if (this._comboPalette.length >= 8) return;
    this._comboPalette = [...this._comboPalette, DEFAULT_PAINT];
  }

  private _removeComboPaletteColour(index: number): void {
    this._comboPalette = this._comboPalette.filter(
      (_colour, current) => current !== index,
    );
  }

  private _moveComboPaletteColour(index: number, delta: -1 | 1): void {
    const target = index + delta;
    if (target < 0 || target >= this._comboPalette.length) return;
    const next = [...this._comboPalette];
    [next[index], next[target]] = [next[target], next[index]];
    this._comboPalette = next;
  }

  private _resetCombo(): void {
    const family = FLAT_CATALOGUE[0];
    this._comboEffects = [
      { family: family.family, variant: family.variants[0].variant },
    ];
    this._comboVariant = 0;
    this._comboSpeed = 50;
    this._comboPalette = [...DEFAULT_STOPS];
    this._finishDraftReset();
  }

  private _finishDraftReset(): void {
    if (this._editingId === null) {
      this._draftBaseline = this._draftSignature();
    }
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

  private _moveStop(i: number, delta: -1 | 1): void {
    const target = i + delta;
    const stops = this._activeStops();
    if (target < 0 || target >= stops.length) return;
    const next = [...stops];
    [next[i], next[target]] = [next[target], next[i]];
    this._setActiveStops(next);
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

  private _currentStudioContent(): EffectContentDict {
    if (this._studioKind === "static") {
      return buildSegmentContent(
        this._staticColors.map((c) => (c === null ? null : hexToRgb(c))),
        this._staticBrightness,
      );
    }
    if (this._studioKind === "gradient") {
      return buildVibrantContent(this._studioStops.map(hexToRgb));
    }
    if (this._studioKind === "sketch") {
      return buildSketchContent(
        this._sketchColors.map((color) =>
          color === null ? null : hexToRgb(color),
        ),
        this._sketchMotion,
        this._sketchSpeed,
        this._sketchBrightness,
        hexToRgb(this._sketchBackground),
      );
    }
    if (this._studioKind === "flat") {
      return buildFlatContent(
        this._flatFamily,
        this._flatVariant,
        this._flatSpeed,
        this._flatPalette.map(hexToRgb),
      );
    }
    if (this._studioKind === "combo") {
      return buildComboContent(
        this._comboEffects.map(
          (step) => [step.family, step.variant] as const,
        ),
        this._comboSpeed,
        this._comboPalette.map(hexToRgb),
        this._comboVariant,
      );
    }
    throw new Error(`The ${this._studioKind} editor is not available yet.`);
  }

  private _currentContentSignature(): string | null {
    try {
      return JSON.stringify(this._currentStudioContent());
    } catch {
      return null;
    }
  }

  private _targetModel(): string | null {
    const entity = this._config?.entity;
    if (!entity || !this.hass) return null;
    const deviceId = this.hass.entities?.[entity]?.device_id;
    if (!deviceId) return null;
    return this.hass.devices?.[deviceId]?.model ?? null;
  }

  private _knownEffectNames(effects: readonly CustomEffectEntry[]): string[] {
    const entity = this._config?.entity;
    const raw = entity ? this.hass?.states[entity]?.attributes?.effect_list : undefined;
    const listed = Array.isArray(raw)
      ? raw.filter((name): name is string => typeof name === "string")
      : [];
    return [...listed, ...effects.map((effect) => effect.name)];
  }

  private _loadDraft(
    name: string,
    content: EffectContentDict,
    editingId: string | null,
  ): void {
    this._editingId = editingId;
    this._loadedContent = content;
    this._studioName = name;
    this._studioKind = studioKindForContent(content);
    this._selection = clearSelection();
    this._cursor = 1;
    if (content.kind === "segments") {
      this._staticColors = Array.from(
        { length: SEGMENT_COUNT },
        (_unused, index) => {
          const colour = content.colors[index];
          return colour === undefined || colour === null ? null : rgbToHex(colour);
        },
      );
      this._staticBrightness =
        content.brightness === null
          ? null
          : Array.from(
              { length: SEGMENT_COUNT },
              (_unused, index) => content.brightness?.[index] ?? null,
            );
    } else if (content.kind === "vibrant") {
      this._studioStops = content.stops.map(rgbToHex);
    } else if (content.kind === "sketch") {
      this._sketchColors = Array.from(
        { length: SEGMENT_COUNT },
        (_unused, index) => {
          const colour = content.colors[index];
          return colour === undefined || colour === null ? null : rgbToHex(colour);
        },
      );
      this._sketchMotion = content.motion;
      this._sketchSpeed = content.speed;
      this._sketchBrightness = content.brightness;
      this._sketchBackground = rgbToHex(content.background);
    } else if (content.kind === "flat") {
      flatFamilyByCode(content.family);
      this._flatFamily = content.family;
      this._flatVariant = content.variant;
      this._flatSpeed = content.speed;
      this._flatPalette = content.palette.map(rgbToHex);
    } else if (content.kind === "combo") {
      for (const [family, variant] of content.effects) {
        flatVariantLabel(family, variant);
      }
      this._comboEffects = content.effects.map(([family, variant]) => ({
        family,
        variant,
      }));
      this._comboVariant = content.variant;
      this._comboSpeed = content.speed;
      this._comboPalette = content.palette.map(rgbToHex);
    }
    this._tab = "studio";
    this._pendingDraft = null;
    this._editingOriginalName = editingId === null ? null : name.trim();
    this._editingOriginalContent =
      editingId === null ? null : JSON.stringify(content);
    this._draftBaseline =
      editingId === null ? "" : this._draftSignature();
  }

  private _resetStudioDraft(): void {
    this._editingId = null;
    this._editingOriginalName = null;
    this._editingOriginalContent = null;
    this._loadedContent = null;
    this._studioName = "";
    this._staticColors = Array.from({ length: SEGMENT_COUNT }, () => null);
    this._staticBrightness = null;
    this._studioStops = [...DEFAULT_STOPS];
    this._resetSketch();
    this._resetFlat();
    this._resetCombo();
    this._selection = clearSelection();
    this._cursor = 1;
    this._pendingDraft = null;
    this._draftBaseline = this._draftSignature();
  }

  private _cancelEdit(): void {
    this._resetStudioDraft();
    this._feedback = { kind: "info", text: "Edit cancelled." };
  }

  private _offerDraft(
    name: string,
    content: EffectContentDict,
    editingId: string | null,
    feedback: string,
    clearImport = false,
  ): void {
    const kind = studioKindForContent(content);
    if (!this._isStudioKindSupported(kind)) {
      this._feedback = {
        kind: "error",
        text: `This light does not support ${STUDIO_KINDS.find((entry) => entry.id === kind)?.label ?? kind} effects.`,
      };
      return;
    }
    if (this._hasUnsavedDraft()) {
      this._pendingDraft = {
        name,
        content,
        editingId,
        feedback,
        clearImport,
      };
      void this.updateComplete.then(() => {
        this.renderRoot
          .querySelector<HTMLButtonElement>(".keep-draft")
          ?.focus();
      });
      return;
    }
    this._loadDraft(name, content, editingId);
    if (clearImport) this._importText = "";
    this._feedback = { kind: "info", text: feedback };
  }

  private _confirmDraftReplacement(): void {
    const pending = this._pendingDraft;
    if (pending === null) return;
    this._loadDraft(pending.name, pending.content, pending.editingId);
    if (pending.clearImport) this._importText = "";
    this._feedback = { kind: "info", text: pending.feedback };
  }

  private _keepDraft(): void {
    this._pendingDraft = null;
    this._feedback = { kind: "info", text: "Kept the existing Studio draft." };
  }

  /** Studio tab: save a new typed effect or update the loaded stable ID. */
  private async _saveStudio(): Promise<void> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) return;
    if (!this._isStudioKindSupported(this._studioKind)) {
      this._feedback = { kind: "error", text: "This effect type is not supported by this light." };
      return;
    }
    const name = this._studioName.trim();
    try {
      const content = this._currentStudioContent();
      const editingId = this._editingId;
      if (editingId === null) {
        await this.hass.callService(
          "ha_govee_led_ble",
          "save_effect",
          { name, content },
          { entity_id: entity },
        );
        this._feedback = { kind: "info", text: `Saved "${name}".` };
      } else {
        const update: Record<string, unknown> = { id: editingId };
        if (
          this._editingOriginalName === null ||
          name !== this._editingOriginalName
        ) {
          update.name = name;
        }
        if (
          this._editingOriginalContent === null ||
          JSON.stringify(content) !== this._editingOriginalContent
        ) {
          update.content = content;
        }
        if (Object.keys(update).length === 1) {
          this._feedback = { kind: "info", text: "No changes to update." };
          return;
        }
        await this.hass.callService(
          "ha_govee_led_ble",
          "update_effect",
          update,
          { entity_id: entity },
        );
        this._feedback = { kind: "info", text: `Updated "${name}".` };
      }
      this._resetStudioDraft();
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private async _readEffect<T>(
    effect: CustomEffectEntry,
    action: string,
    parse: (value: unknown, entityId: string) => T,
  ): Promise<T> {
    const entity = this._config?.entity;
    if (!this.hass || !entity) throw new Error("The light is unavailable.");
    this._busyKey = `${action}:${effect.id}`;
    try {
      const result = await this.hass.callService<unknown>(
        "ha_govee_led_ble",
        "export_effect",
        { id: effect.id },
        { entity_id: entity },
        true,
        true,
      );
      return parse(result.response, entity);
    } finally {
      this._busyKey = null;
    }
  }

  private async _editEffect(effect: CustomEffectEntry): Promise<void> {
    this._feedback = null;
    try {
      const exported = await this._readEffect(
        effect,
        "edit",
        parseEntityExportResponse,
      );
      this._offerDraft(
        exported.name,
        exported.content,
        exported.id,
        `Editing "${exported.name}".`,
      );
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private async _duplicateEffect(
    effect: CustomEffectEntry,
    existing: readonly CustomEffectEntry[],
  ): Promise<void> {
    this._feedback = null;
    try {
      const exported = await this._readEffect(
        effect,
        "duplicate",
        parseEntityExportResponse,
      );
      const name = suggestDuplicateName(
        exported.name,
        this._knownEffectNames(existing),
      );
      this._offerDraft(
        name,
        exported.content,
        null,
        `Loaded "${name}" as a new draft. Review it, then save.`,
      );
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private async _exportEffect(effect: CustomEffectEntry): Promise<void> {
    this._feedback = null;
    try {
      const exported = await this._readEffect(
        effect,
        "export",
        parseEntityRawExportResponse,
      );
      const exchange = buildEffectExchangeDocument(exported);
      const blob = new Blob([`${JSON.stringify(exchange, null, 2)}\n`], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = createDownloadAnchor(effectFileName(exported.name), url);
      window.document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      this._feedback = { kind: "info", text: `Exported "${exported.name}".` };
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err) };
    }
  }

  private _chooseImportFile(): void {
    this.renderRoot.querySelector<HTMLInputElement>(".import-file")?.click();
  }

  private async _loadImportFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    try {
      this._importText = await file.text();
      this._feedback = { kind: "info", text: `Loaded ${file.name}. Review the JSON, then import it.` };
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err, "Could not read that file.") };
    }
  }

  private _reviewImport(effects: readonly CustomEffectEntry[]): void {
    const segmentCount = this._segmentColors()?.length ?? SEGMENT_COUNT;
    try {
      const parsed = parseEffectExchangeJson(this._importText, {
        model: this._targetModel(),
        segmentCount,
      });
      const name = resolveImportName(
        parsed.effect.name,
        this._knownEffectNames(effects),
      );
      this._offerDraft(
        name,
        parsed.effect.content,
        null,
        name === parsed.effect.name
          ? `Imported "${name}" as a draft. Review it, then save.`
          : `Imported as "${name}" because that name already exists. Review it, then save.`,
        true,
      );
    } catch (err) {
      this._feedback = { kind: "error", text: errorMessage(err, "Could not import that effect.") };
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
      if (
        this._editingId === effect.id &&
        this._editingOriginalName !== null &&
        this._studioName.trim() === this._editingOriginalName
      ) {
        const contentUnchanged =
          this._currentContentSignature() === this._editingOriginalContent;
        this._studioName = to;
        this._editingOriginalName = to;
        if (contentUnchanged) this._draftBaseline = this._draftSignature();
      }
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
      if (this._editingId === effect.id) {
        this._editingId = null;
        this._editingOriginalName = null;
        this._editingOriginalContent = null;
        this._draftBaseline = "";
        this._feedback = {
          kind: "info",
          text: `Deleted "${effect.name}". Its Studio draft was kept as a new effect.`,
        };
      } else {
        this._feedback = { kind: "info", text: `Deleted "${effect.name}".` };
      }
      if (this._pendingDraft?.editingId === effect.id) {
        this._pendingDraft = {
          ...this._pendingDraft,
          editingId: null,
          feedback: `Loaded "${effect.name}" as a new draft because the saved effect was deleted.`,
        };
      }
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

  private _drawNowPreview(): void {
    const canvas = this.renderRoot?.querySelector<HTMLCanvasElement>("canvas.preview");
    if (canvas) this._draw(canvas);
  }

  private _draw(canvas: HTMLCanvasElement): void {
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
    const gap = 3;
    const cellW = (cssW - gap * (n - 1)) / n;
    for (let i = 0; i < n; i++) {
      const rgb = sampleStops(stops, i / (n - 1));
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
        ${this._pendingDraft
          ? html`
              <div class="draft-confirm" role="alertdialog" aria-label="Replace Studio draft">
                <span>Replace your unsaved Studio draft with "${this._pendingDraft.name}"?</span>
                <div class="row">
                  <button class="btn keep-draft" @click=${this._keepDraft}>Keep draft</button>
                  <button class="btn primary" @click=${this._confirmDraftReplacement}>
                    Replace draft
                  </button>
                </div>
              </div>
            `
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

  private _renderStrip(
    colours: (string | null)[],
    nullClass: "off" | "unchanged" | "background",
    nullColour: string | null = null,
  ): unknown {
    const cellId = (segment: number) =>
      `segment-cell-${this._tab}-${this._studioKind}-${segment}`;
    const cells = [];
    for (let seg = 1; seg <= SEGMENT_COUNT; seg++) {
      const colour = colours[seg - 1] ?? null;
      const selected = this._selection.has(seg);
      const cursor = seg === this._cursor;
      const stateWord = colour
        ? "painted"
        : nullClass === "off"
          ? "off"
          : nullClass === "background"
            ? "background"
            : "unchanged";
      const style = colour
        ? `background:${colour}`
        : nullClass === "background" && nullColour !== null
          ? `--cell-background:${nullColour}`
          : "";
      cells.push(html`
        <div
          id=${cellId(seg)}
          class="cell ${selected ? "sel" : ""} ${cursor ? "cursor" : ""} ${colour
            ? ""
            : nullClass}"
          style=${style}
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
          aria-activedescendant=${cellId(this._cursor)}
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
                ?disabled=${i === 0}
                @click=${() => this._moveStop(i, -1)}
                aria-label=${`Move stop ${i + 1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${i === n - 1}
                @click=${() => this._moveStop(i, 1)}
                aria-label=${`Move stop ${i + 1} right`}
              >
                →
              </button>
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
    const availableKinds = this._availableKindDescriptors();
    return html`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${availableKinds.map(
              (k) => html`
                <button
                  class="kind ${this._studioKind === k.id ? "active" : ""}"
                  role="radio"
                  aria-checked=${this._studioKind === k.id ? "true" : "false"}
                  tabindex=${this._studioKind === k.id ? "0" : "-1"}
                  ?disabled=${this._editingId !== null && this._studioKind !== k.id}
                  @click=${() => this._selectKind(k.id)}
                >
                  ${k.label}
                </button>
              `,
            )}
          </div>
          ${SOON_KINDS.length > 0
            ? html`
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
              `
            : nothing}
        </section>
        ${this._studioKind === "static"
          ? this._renderStaticEditor()
          : this._studioKind === "gradient"
            ? this._renderGradientAuthor()
            : this._studioKind === "sketch"
              ? this._renderSketchAuthor()
              : this._studioKind === "flat"
                ? this._renderFlatAuthor()
                : this._studioKind === "combo"
                  ? this._renderComboAuthor()
                  : this._renderPendingAuthor()}
      </div>
    `;
  }

  private _renderStaticEditor(): unknown {
    const painted = this._staticColors.filter((c) => c !== null).length;
    const hasContent = segmentDraftHasContent(
      this._staticColors.map((c) => (c === null ? null : hexToRgb(c))),
      this._staticBrightness,
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

  private _renderSketchAuthor(): unknown {
    const painted = this._sketchColors.filter((color) => color !== null).length;
    const content = buildSketchContent(
      this._sketchColors.map((color) =>
        color === null ? null : hexToRgb(color),
      ),
      this._sketchMotion,
      this._sketchSpeed,
      this._sketchBrightness,
      hexToRgb(this._sketchBackground),
    );
    const preview = sketchPreviewColors(content).map(rgbToHex);
    return html`
      <section>
        <div class="row heading">
          <span class="label">Sketch foreground</span>
          <span class="hint">${painted} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._sketchColors, "background", this._sketchBackground)}
        <div class="row controls">
          <label class="colour-control">
            <span>Foreground</span>
            <input
              type="color"
              aria-label="Sketch foreground colour"
              .value=${this._paintColor}
              @input=${(e: Event) =>
                (this._paintColor = (e.target as HTMLInputElement).value)}
            />
          </label>
          <label class="colour-control">
            <span>Background</span>
            <input
              type="color"
              aria-label="Sketch background colour"
              .value=${this._sketchBackground}
              @input=${(e: Event) =>
                (this._sketchBackground = (e.target as HTMLInputElement).value)}
            />
          </label>
          <button class="btn primary" @click=${this._paintSketch}>Paint selected</button>
          <button class="btn" @click=${this._clearSketchSelection}>Use background</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetSketch}>Reset</button>
        </div>
        <p class="help">
          Hatched cells use the background; solid cells are the animated foreground palette.
        </p>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Motion</span>
        </div>
        <div
          class="motion-grid"
          role="radiogroup"
          aria-label="Sketch motion"
          @keydown=${this._onMotionKey}
        >
          ${SKETCH_MOTIONS.map(
            (motion) => html`
              <button
                class="motion ${this._sketchMotion === motion.code ? "active" : ""}"
                role="radio"
                aria-checked=${this._sketchMotion === motion.code ? "true" : "false"}
                tabindex=${this._sketchMotion === motion.code ? "0" : "-1"}
                @click=${() => (this._sketchMotion = motion.code)}
              >
                ${motion.label}
              </button>
            `,
          )}
        </div>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchSpeed)}
            aria-label=${`Sketch speed, ${this._sketchSpeed} percent`}
            @input=${(e: Event) =>
              (this._sketchSpeed = Number((e.target as HTMLInputElement).value))}
          />
          <output>${this._sketchSpeed}%</output>
        </label>
        <label class="range-row">
          <span>Brightness</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchBrightness)}
            aria-label=${`Sketch brightness, ${this._sketchBrightness} percent`}
            @input=${(e: Event) =>
              (this._sketchBrightness = Number((e.target as HTMLInputElement).value))}
          />
          <output>${this._sketchBrightness}%</output>
        </label>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Representative preview</span>
          <span class="preview-badge">Approximate · animated on device</span>
        </div>
        ${this._renderPreviewStrip(preview)}
        ${this._renderStudioSave(true, "")}
      </section>
    `;
  }

  private _renderPaletteEditor(
    palette: readonly string[],
    max: number,
    label: string,
    setColour: (index: number, value: string) => void,
    addColour: () => void,
    removeColour: (index: number) => void,
    moveColour: (index: number, delta: -1 | 1) => void,
  ): unknown {
    return html`
      <div class="row heading">
        <span class="label">${label}</span>
        <span class="hint">${palette.length} of ${max}</span>
      </div>
      <div class="palette-editor">
        ${palette.map(
          (colour, index) => html`
            <div class="palette-chip">
              <span class="palette-number">${index + 1}</span>
              <input
                type="color"
                aria-label=${`${label} colour ${index + 1}`}
                .value=${colour}
                @input=${(e: Event) =>
                  setColour(index, (e.target as HTMLInputElement).value)}
              />
              <button
                class="btn tiny"
                ?disabled=${index === 0}
                @click=${() => moveColour(index, -1)}
                aria-label=${`Move colour ${index + 1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${index === palette.length - 1}
                @click=${() => moveColour(index, 1)}
                aria-label=${`Move colour ${index + 1} right`}
              >
                →
              </button>
              <button
                class="btn tiny danger"
                @click=${() => removeColour(index)}
                aria-label=${`Remove colour ${index + 1}`}
              >
                ×
              </button>
            </div>
          `,
        )}
        <button
          class="btn palette-add"
          ?disabled=${palette.length >= max}
          @click=${addColour}
        >
          Add colour
        </button>
      </div>
    `;
  }

  private _renderFlatAuthor(): unknown {
    const family = flatFamilyByCode(this._flatFamily);
    const preview =
      this._flatPalette.length === 0
        ? []
        : Array.from(
            { length: SEGMENT_COUNT },
            (_unused, index) => this._flatPalette[index % this._flatPalette.length],
          );
    return html`
      <section>
        <div class="row heading">
          <span class="label">Animation family</span>
          <span class="hint">Human-labelled catalogue</span>
        </div>
        <div
          class="family-grid"
          role="radiogroup"
          aria-label="Flat animation family"
          @keydown=${this._onFlatFamilyKey}
        >
          ${FLAT_CATALOGUE.map(
            (entry) => html`
              <button
                class="family ${entry.family === this._flatFamily ? "active" : ""}"
                role="radio"
                aria-checked=${entry.family === this._flatFamily ? "true" : "false"}
                tabindex=${entry.family === this._flatFamily ? "0" : "-1"}
                @click=${() => this._selectFlatFamily(entry.family)}
              >
                ${entry.label}
              </button>
            `,
          )}
        </div>
        <div class="row heading">
          <span class="label">Variant</span>
          <span class="hint">Up to ${family.palette_max} colours</span>
        </div>
        <div
          class="variant-grid"
          role="radiogroup"
          aria-label=${`${family.label} variant`}
          @keydown=${this._onFlatVariantKey}
        >
          ${family.variants.map(
            (variant) => html`
              <button
                class="variant ${variant.variant === this._flatVariant ? "active" : ""}"
                role="radio"
                aria-checked=${variant.variant === this._flatVariant ? "true" : "false"}
                tabindex=${variant.variant === this._flatVariant ? "0" : "-1"}
                @click=${() => (this._flatVariant = variant.variant)}
              >
                ${variant.label}
              </button>
            `,
          )}
        </div>
        <p class="help">${family.description}</p>
      </section>
      <section>
        ${this._renderPaletteEditor(
          this._flatPalette,
          family.palette_max,
          "Shared palette order",
          (index, value) => this._setFlatPaletteColour(index, value),
          () => this._addFlatPaletteColour(),
          (index) => this._removeFlatPaletteColour(index),
          (index, delta) => this._moveFlatPaletteColour(index, delta),
        )}
        ${preview.length > 0
          ? html`
              <div class="row heading">
                <span class="label">Representative preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(preview)}
            `
          : html`<p class="help">Add at least one colour to preview and save this effect.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>${family.control_label}</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._flatSpeed)}
            aria-label=${`${family.control_label}, ${this._flatSpeed} percent`}
            @input=${(e: Event) =>
              (this._flatSpeed = Number((e.target as HTMLInputElement).value))}
          />
          <output>${this._flatSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetFlat}>Reset Flat draft</button>
        ${this._renderStudioSave(
          this._flatPalette.length > 0,
          "Add at least one palette colour to save.",
        )}
      </section>
    `;
  }

  private _renderComboAuthor(): unknown {
    const preview =
      this._comboPalette.length === 0
        ? []
        : Array.from(
            { length: SEGMENT_COUNT },
            (_unused, index) => this._comboPalette[index % this._comboPalette.length],
          );
    return html`
      <section>
        <div class="row heading">
          <span class="label">Effect chain</span>
          <span class="hint">${this._comboEffects.length} of 4 steps</span>
        </div>
        ${this._comboEffects.length === 0
          ? html`<p class="help">Add at least one Flat effect to the chain.</p>`
          : html`
              <ol class="combo-chain">
                ${this._comboEffects.map((step, index) => {
                  const family = flatFamilyByCode(step.family);
                  return html`
                    <li class="combo-step">
                      <span class="combo-number">${index + 1}</span>
                      <label>
                        <span class="sr-only">Step ${index + 1} family</span>
                        <select
                          aria-label=${`Step ${index + 1} family`}
                          .value=${String(step.family)}
                          @change=${(e: Event) =>
                            this._setComboFamily(
                              index,
                              Number((e.target as HTMLSelectElement).value),
                            )}
                        >
                          ${FLAT_CATALOGUE.map(
                            (entry) => html`
                              <option value=${String(entry.family)}>${entry.label}</option>
                            `,
                          )}
                        </select>
                      </label>
                      <label>
                        <span class="sr-only">Step ${index + 1} variant</span>
                        <select
                          aria-label=${`Step ${index + 1} variant`}
                          .value=${String(step.variant)}
                          @change=${(e: Event) =>
                            this._setComboVariant(
                              index,
                              Number((e.target as HTMLSelectElement).value),
                            )}
                        >
                          ${family.variants.map(
                            (variant) => html`
                              <option value=${String(variant.variant)}>${variant.label}</option>
                            `,
                          )}
                        </select>
                      </label>
                      <div class="combo-actions">
                        <button
                          class="btn tiny"
                          ?disabled=${index === 0}
                          @click=${() => this._moveComboStep(index, -1)}
                          aria-label=${`Move step ${index + 1} up`}
                        >
                          ↑
                        </button>
                        <button
                          class="btn tiny"
                          ?disabled=${index === this._comboEffects.length - 1}
                          @click=${() => this._moveComboStep(index, 1)}
                          aria-label=${`Move step ${index + 1} down`}
                        >
                          ↓
                        </button>
                        <button
                          class="btn tiny danger"
                          @click=${() => this._removeComboStep(index)}
                          aria-label=${`Remove step ${index + 1}`}
                        >
                          ×
                        </button>
                      </div>
                    </li>
                  `;
                })}
              </ol>
            `}
        <button
          class="btn"
          ?disabled=${this._comboEffects.length >= 4}
          @click=${this._addComboStep}
        >
          Add step
        </button>
      </section>
      <section>
        ${this._renderPaletteEditor(
          this._comboPalette,
          8,
          "Shared palette order",
          (index, value) => this._setComboPaletteColour(index, value),
          () => this._addComboPaletteColour(),
          (index) => this._removeComboPaletteColour(index),
          (index, delta) => this._moveComboPaletteColour(index, delta),
        )}
        ${preview.length > 0
          ? html`
              <div class="row heading">
                <span class="label">Sequence preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(preview)}
            `
          : html`<p class="help">Add at least one shared palette colour.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._comboSpeed)}
            aria-label=${`Combo speed, ${this._comboSpeed} percent`}
            @input=${(e: Event) =>
              (this._comboSpeed = Number((e.target as HTMLInputElement).value))}
          />
          <output>${this._comboSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetCombo}>Reset Combo draft</button>
        ${this._renderStudioSave(
          this._comboEffects.length > 0 && this._comboPalette.length > 0,
          this._comboEffects.length === 0
            ? "Add at least one effect step to save."
            : "Add at least one shared palette colour to save.",
        )}
      </section>
    `;
  }

  private _renderPendingAuthor(): unknown {
    const label = STUDIO_KINDS.find((kind) => kind.id === this._studioKind)?.label ?? this._studioKind;
    const loaded = this._loadedContent?.kind === this._studioKind;
    return html`
      <section class="pending-author">
        <div class="row heading">
          <span class="label">${label}</span>
          <span class="hint">Editor coming next</span>
        </div>
        <p class="help">
          ${loaded
            ? `This ${label} effect is loaded safely, but this editor is not available in the current build.`
            : `The ${label} editor will be enabled in the next Studio phase.`}
        </p>
        ${this._editingId !== null
          ? html`<button class="btn" @click=${this._cancelEdit}>Cancel edit</button>`
          : nothing}
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
    const editing = this._editingId !== null;
    return html`
      ${editing
        ? html`<div class="edit-band" role="status">
            <span>Editing a saved effect. Update keeps its stable ID and effect kind.</span>
            <button class="btn" @click=${this._cancelEdit}>Cancel edit</button>
          </div>`
        : nothing}
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
          ${editing ? "Update effect" : "Save effect"}
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
    const quarantined = coerceCustomEffects(
      state.attributes?.quarantined_custom_effects,
    );
    const allEffects = [...effects, ...quarantined];
    const active =
      typeof state.attributes?.effect === "string" ? state.attributes.effect : null;
    return html`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${effects.length} available</span>
          </div>
          ${effects.length === 0
            ? html`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`
            : html`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${effects.map((effect) => this._renderEffectRow(effect, active, allEffects))}
                </ul>
              `}
        </section>
        ${quarantined.length === 0
          ? nothing
          : html`
              <section>
                <div class="row heading">
                  <span class="label">Unavailable on this model</span>
                  <span class="hint">${quarantined.length} preserved</span>
                </div>
                <p class="help">
                  These effects are kept for export or deletion, but cannot be applied or edited on
                  this light.
                </p>
                <ul class="effects" role="list">
                  ${quarantined.map((effect) => this._renderQuarantinedEffectRow(effect))}
                </ul>
              </section>
            `}
        <section>
          <details class="import-panel">
            <summary>Import effect JSON</summary>
            <div class="import-body">
              <textarea
                class="import-json"
                aria-label="Effect JSON"
                placeholder="Paste an exported Govee effect here"
                .value=${this._importText}
                @input=${(e: Event) =>
                  (this._importText = (e.target as HTMLTextAreaElement).value)}
              ></textarea>
              <input
                class="import-file"
                type="file"
                accept=".json,application/json"
                @change=${this._loadImportFile}
              />
              <div class="row controls">
                <button class="btn" @click=${this._chooseImportFile}>Load JSON file</button>
                <button
                  class="btn primary"
                  ?disabled=${this._importText.trim() === ""}
                  @click=${() => this._reviewImport(allEffects)}
                >
                  Review import
                </button>
                <button
                  class="btn"
                  ?disabled=${this._importText === ""}
                  @click=${() => (this._importText = "")}
                >
                  Clear
                </button>
              </div>
              <p class="help">
                Import opens an untrusted file as a Studio draft. Nothing is saved until you review it.
              </p>
            </div>
          </details>
        </section>
      </div>
    `;
  }

  private _renderEffectRow(
    effect: CustomEffectEntry,
    active: string | null,
    effects: readonly CustomEffectEntry[],
  ): unknown {
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
    const busy = this._busyKey?.endsWith(`:${effect.id}`) ?? false;
    return html`
      <li class="effect ${isActive ? "active" : ""}">
        <div class="effect-main">
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
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${busy}
            @click=${() => void this._editEffect(effect)}
            aria-label=${`Edit ${effect.name}`}
          >
            Edit
          </button>
          <button
            class="btn"
            ?disabled=${busy}
            @click=${() => void this._duplicateEffect(effect, effects)}
            aria-label=${`Duplicate ${effect.name}`}
          >
            Duplicate
          </button>
          <details class="effect-more">
            <summary class="btn">More</summary>
            <div class="more-actions">
              <button
                class="btn"
                ?disabled=${busy}
                @click=${() => void this._exportEffect(effect)}
                aria-label=${`Export ${effect.name}`}
              >
                ${busy ? "Working…" : "Export"}
              </button>
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
            </div>
          </details>
        </div>
      </li>
    `;
  }

  private _renderQuarantinedEffectRow(effect: CustomEffectEntry): unknown {
    if (this._deletingId === effect.id) {
      return html`
        <li class="effect quarantined">
          <span class="confirm-text">Delete "${effect.name}"?</span>
          <button class="btn confirm-cancel" @click=${this._cancelDelete}>Cancel</button>
          <button class="btn danger primary" @click=${() => this._deleteEffect(effect)}>
            Delete
          </button>
        </li>
      `;
    }
    const busy = this._busyKey?.endsWith(`:${effect.id}`) ?? false;
    return html`
      <li class="effect quarantined">
        <div class="effect-main">
          <span class="badge-unavailable">Unavailable</span>
          <span class="effect-label" title=${effect.name}>${effect.name}</span>
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${busy}
            @click=${() => void this._exportEffect(effect)}
            aria-label=${`Export ${effect.name}`}
          >
            ${busy ? "Working…" : "Export"}
          </button>
          <button
            class="btn danger"
            @click=${() => this._askDelete(effect)}
            aria-label=${`Delete ${effect.name}`}
          >
            Delete
          </button>
        </div>
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
