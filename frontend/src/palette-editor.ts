import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import type { GoveeColourPicker } from "./colour-picker";
import "./colour-picker";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { recentColour } from "./recent-colours";
import "./reorderable-strip";
import type {
  GoveeReorderableStrip,
  ReorderableStripItem,
} from "./reorderable-strip";
import { studioBaseStyles } from "./studio-styles";
import type { RGB } from "./types";
import {
  clonePalette,
  relocatedIndex,
  rgbToHex,
} from "./ui-utils";

export class GoveePaletteEditor extends LitElement {
  @property({ attribute: false })
  public palette: RGB[] = [];

  @property({ type: Number })
  public minColours = 1;

  @property({ type: Number })
  public maxColours = 8;

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Boolean })
  public persistentPicker = false;

  @property({ type: Number })
  public selectedIndex?: number;

  @property()
  public ariaLabel = "Colours";

  @property()
  public itemName = "colour";

  @state()
  private editingIndex?: number;

  @state()
  private colourInteractionActive = false;

  private readonly windowPointerDown = (event: PointerEvent): void => {
    if (
      this.editingIndex !== undefined &&
      !event.composedPath().includes(this) &&
      !this.colourInteractionActive
    ) {
      this.closePicker();
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
      changed.has("palette") &&
      this.editingIndex !== undefined &&
      this.editingIndex >= this.palette.length
    ) {
      this.closePicker();
    }
  }

  protected render() {
    const activeIndex = this.persistentPicker
      ? this.selectedIndex
      : this.editingIndex;
    const items: ReorderableStripItem[] = this.palette.map(
      (colour, index) => ({
        key: `${index}-${rgbToHex(colour)}`,
        label: `${capitalise(this.itemName)} ${index + 1}`,
        ariaLabel: this.itemAriaLabel(colour, index),
        colour: rgbToHex(colour),
        removeReady:
          !this.persistentPicker &&
          this.editingIndex === index &&
          this.palette.length > this.minColours,
        disabled: this.disabled,
      }),
    );
    return html`
      <govee-reorderable-strip
        .items=${items}
        .activeIndex=${activeIndex}
        .itemRole=${this.persistentPicker ? "tab" : "button"}
        .ariaLabel=${this.ariaLabel}
        .addLabel=${`Add ${this.itemName}`}
        .addDisabled=${this.disabled}
        .addHidden=${this.palette.length >= this.maxColours}
        .reorderDisabled=${this.disabled || this.persistentPicker}
        .popoverDismissDisabled=${this.colourInteractionActive}
        @item-selected=${(event: CustomEvent<{ index: number }>) =>
          this.swatchClicked(event.detail.index)}
        @items-reordered=${(
          event: CustomEvent<{ from: number; to: number }>,
        ) => this.reorder(event.detail.from, event.detail.to)}
        @item-added=${this.addColour}
        @item-popover-dismissed=${this.dismissPicker}
        @keydown=${this.paletteKeyPressed}
        @focusout=${this.paletteFocusOut}
      >
        ${this.persistentPicker || this.editingIndex === undefined
          ? nothing
          : html`
              <div
                slot="item-${this.editingIndex}"
                class="strip-popover colour-popover"
                role="dialog"
                aria-label="Edit colour"
              >
                ${this.renderPicker(
                  this.editingIndex,
                  this.palette[this.editingIndex],
                )}
              </div>
            `}
      </govee-reorderable-strip>
      ${this.persistentPicker && activeIndex !== undefined
        ? html`
            <div
              class="persistent-picker"
              role="group"
              aria-label="Edit ${this.itemName} ${activeIndex + 1}"
            >
              ${this.renderPicker(
                activeIndex,
                this.palette[activeIndex],
              )}
            </div>
          `
        : nothing}
    `;
  }

  private itemAriaLabel(colour: RGB, index: number): string {
    const name = `${capitalise(this.itemName)} ${index + 1}`;
    if (this.persistentPicker) {
      return `${name}, ${rgbToHex(colour)}${
        index === this.selectedIndex ? ", selected" : ""
      }`;
    }
    return this.editingIndex === index &&
      this.palette.length > this.minColours
      ? `Remove colour ${index + 1}`
      : `Edit colour ${index + 1}, ${rgbToHex(
          colour,
        )}. Drag to reorder or use arrow keys.`;
  }

  private renderPicker(index: number, colour: RGB) {
    return html`
      <govee-colour-picker
        .colour=${colour}
        .disabled=${this.disabled}
        @colour-changing=${(event: CustomEvent<{ colour: RGB }>) => {
          this.colourInteractionActive = true;
          this.updateColour(index, event.detail.colour, "changing");
        }}
        @colour-changed=${(event: CustomEvent<{ colour: RGB }>) =>
          this.commitColour(index, event.detail.colour)}
      ></govee-colour-picker>
    `;
  }

  private commitColour(index: number, colour: RGB): void {
    this.colourInteractionActive = false;
    this.updateColour(index, colour, "committed");
    if (this.persistentPicker) {
      return;
    }
    this.closePicker();
    this.focusSwatchAfterUpdate(index);
  }

  private updateColour(
    index: number,
    colour: RGB,
    interaction: LivePreviewInteraction,
  ): void {
    const palette = clonePalette(this.palette);
    palette[index] = [...colour];
    this.emitPalette(palette, interaction);
  }

  private addColour(): void {
    if (this.disabled || this.palette.length >= this.maxColours) {
      return;
    }
    const previous =
      this.palette[this.palette.length - 1] ??
      recentColour(this.palette.length);
    const palette = [...clonePalette(this.palette), [...previous] as RGB];
    const index = palette.length - 1;
    if (this.persistentPicker) {
      this.selectColour(index, palette[index]);
    } else {
      this.editingIndex = index;
      this.focusPickerAfterUpdate();
    }
    this.emitPalette(palette, "committed");
  }

  private removeColour(index: number): void {
    if (this.disabled || this.palette.length <= this.minColours) {
      return;
    }
    const palette = this.palette
      .filter((_colour, colourIndex) => colourIndex !== index)
      .map((colour) => [...colour] as RGB);
    const focusIndex = Math.min(index, palette.length - 1);
    this.closePicker();
    this.emitPalette(palette, "committed");
    this.focusSwatchAfterUpdate(focusIndex);
  }

  private reorder(from: number, to: number): void {
    if (this.disabled || from === to) {
      return;
    }
    const palette = clonePalette(this.palette);
    const [moving] = palette.splice(from, 1);
    palette.splice(to, 0, moving);
    this.editingIndex =
      this.editingIndex === from
        ? to
        : relocatedIndex(this.editingIndex, from, to);
    if (this.persistentPicker) {
      const selectedIndex = relocatedIndex(this.selectedIndex, from, to);
      if (selectedIndex !== undefined) {
        this.selectColour(selectedIndex, palette[selectedIndex]);
      }
    }
    this.emitPalette(palette, "committed");
  }

  private focusSwatchAfterUpdate(index: number): void {
    void this.updateComplete.then(() => {
      this.shadowRoot
        ?.querySelector<GoveeReorderableStrip>("govee-reorderable-strip")
        ?.focusItem(index);
    });
  }

  private paletteKeyPressed(event: KeyboardEvent): void {
    const index = this.editingIndex;
    if (event.key !== "Escape" || index === undefined) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    this.closePicker();
    this.focusSwatchAfterUpdate(index);
  }

  private paletteFocusOut(event: FocusEvent): void {
    const strip = event.currentTarget as HTMLElement;
    if (
      this.editingIndex !== undefined &&
      !(event.relatedTarget instanceof Node &&
        strip.contains(event.relatedTarget))
    ) {
      if (this.colourInteractionActive) {
        return;
      }
      this.closePicker();
    }
  }

  private readonly dismissPicker = (): void => {
    if (!this.colourInteractionActive) {
      this.closePicker();
    }
  };

  private closePicker(): void {
    this.colourInteractionActive = false;
    this.editingIndex = undefined;
  }

  private swatchClicked(index: number): void {
    if (this.persistentPicker) {
      this.selectColour(index, this.palette[index]);
      return;
    }
    if (
      this.editingIndex === index &&
      this.palette.length > this.minColours
    ) {
      this.removeColour(index);
      return;
    }
    if (this.editingIndex === index) {
      this.closePicker();
      return;
    }
    this.editingIndex = index;
    this.focusPickerAfterUpdate();
  }

  private focusPickerAfterUpdate(): void {
    void this.updateComplete.then(() => {
      requestAnimationFrame(() => {
        const picker =
          this.shadowRoot?.querySelector<GoveeColourPicker>(
            ".colour-popover govee-colour-picker",
          );
        picker?.shadowRoot
          ?.querySelector<HTMLElement>(
            "button:not(:disabled), input:not(:disabled)",
          )
          ?.focus();
      });
    });
  }

  private selectColour(index: number, colour: RGB): void {
    this.selectedIndex = index;
    this.dispatchEvent(
      new CustomEvent<{ index: number; colour: RGB }>("colour-selected", {
        detail: { index, colour: [...colour] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private emitPalette(
    palette: RGB[],
    interaction: LivePreviewInteraction,
  ): void {
    this.palette = palette;
    this.dispatchEvent(
      new CustomEvent<{
        palette: RGB[];
        interaction: LivePreviewInteraction;
      }>("palette-changed", {
        detail: { palette, interaction },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [studioBaseStyles, css`
    :host {
      display: block;
    }

    .persistent-picker {
      margin-top: var(--studio-section-gap);
      padding-top: var(--studio-section-gap);
      border-top: var(--studio-border-width) solid var(--studio-border);
    }
  `];
}

function capitalise(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-palette-editor": GoveePaletteEditor;
  }
}

if (!customElements.get("govee-palette-editor")) {
  customElements.define("govee-palette-editor", GoveePaletteEditor);
}
