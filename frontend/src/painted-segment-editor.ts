import { LitElement, css, html } from "lit";
import { property } from "lit/decorators.js";

import {
  studioBaseStyles,
  studioCardStyles,
} from "./studio-styles";
import type { LivePreviewInteraction } from "./live-preview-controller";
import type { PaintedSegmentDraft } from "./effect-editor-model";
import { rgbToHex } from "./ui-utils";

export class GoveePaintedSegmentEditor extends LitElement {
  @property({ attribute: false })
  public segments: PaintedSegmentDraft[] = [];

  @property({ type: Boolean })
  public disabled = false;

  private paintingPointerId?: number;
  private paintingPointerTarget?: HTMLElement;
  private lastPaintedSegment?: number;

  protected render() {
    return html`
      <section class="card" aria-labelledby="painted-segments-heading">
        <h3 class="section-title" id="painted-segments-heading">
          Painted segments
        </h3>
        <div class="segments">
          ${this.segments.map(
            (colour, index) => {
              const off = colour === null;
              const rendered = off ? "#000000" : rgbToHex(colour);
              return html`
              <button
                type="button"
                data-segment=${index}
                class=${off ? "off" : ""}
                style="--segment-colour: ${rendered}"
                aria-label=${off
                  ? `Segment ${index + 1}, off`
                  : `Segment ${index + 1}, ${rendered}`}
                ?disabled=${this.disabled}
                @pointerdown=${(event: PointerEvent) =>
                  this.pointerStarted(index, event)}
                @pointermove=${this.pointerMoved}
                @pointerup=${this.pointerCompleted}
                @pointercancel=${this.pointerCancelled}
                @click=${(event: MouseEvent) =>
                  this.segmentClicked(index, event)}
              ></button>
            `;
            },
          )}
        </div>
      </section>
    `;
  }

  private pointerStarted(index: number, event: PointerEvent): void {
    if (
      this.disabled ||
      !event.isPrimary ||
      this.paintingPointerId !== undefined ||
      (event.button !== 0 && event.pointerType !== "touch")
    ) {
      return;
    }
    event.preventDefault();
    const target = event.currentTarget as HTMLElement;
    this.paintingPointerId = event.pointerId;
    this.paintingPointerTarget = target;
    this.lastPaintedSegment = index;
    target.setPointerCapture(event.pointerId);
    this.selectSegment(index, "changing");
  }

  private pointerMoved(event: PointerEvent): void {
    if (event.pointerId !== this.paintingPointerId || !this.shadowRoot) {
      return;
    }
    const target = this.shadowRoot
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>("[data-segment]");
    const index = Number(target?.dataset.segment);
    if (
      Number.isInteger(index) &&
      index !== this.lastPaintedSegment
    ) {
      this.lastPaintedSegment = index;
      this.selectSegment(index, "changing");
    }
  }

  private pointerCompleted(event: PointerEvent): void {
    if (event.pointerId !== this.paintingPointerId) {
      return;
    }
    const index = this.lastPaintedSegment;
    this.finishPointer(event);
    if (index !== undefined) {
      this.selectSegment(index, "committed");
    }
  }

  private pointerCancelled(event: PointerEvent): void {
    if (event.pointerId !== this.paintingPointerId) {
      return;
    }
    const index = this.lastPaintedSegment;
    this.finishPointer(event);
    if (index !== undefined) {
      this.selectSegment(index, "committed");
    }
  }

  private finishPointer(event: PointerEvent): void {
    if (this.paintingPointerTarget?.hasPointerCapture(event.pointerId)) {
      this.paintingPointerTarget.releasePointerCapture(event.pointerId);
    }
    this.paintingPointerId = undefined;
    this.paintingPointerTarget = undefined;
    this.lastPaintedSegment = undefined;
  }

  private segmentClicked(index: number, event: MouseEvent): void {
    if (!this.disabled && event.detail === 0) {
      this.selectSegment(index, "committed");
    }
  }

  private selectSegment(
    index: number,
    interaction: LivePreviewInteraction,
  ): void {
    this.dispatchEvent(
      new CustomEvent<{
        index: number;
        interaction: LivePreviewInteraction;
      }>("segment-selected", {
        detail: { index, interaction },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [studioBaseStyles, studioCardStyles, css`
    :host {
      display: block;
    }

    .segments {
      display: grid;
      grid-template-columns: repeat(15, minmax(0, 1fr));
      gap: var(--studio-micro-gap);
      touch-action: none;
    }

    button {
      min-width: 0;
      min-height: var(--studio-paint-segment-height);
      padding: 0;
      border: var(--studio-border-width) solid
        color-mix(in srgb, var(--segment-colour) 70%, #000);
      border-radius: var(--studio-swatch-radius);
      background: var(--segment-colour);
      cursor: crosshair;
    }

    button:focus-visible {
      outline: var(--studio-focus-width) solid var(--studio-blue);
      outline-offset: var(--studio-focus-offset);
    }

    button.off {
      border-color: color-mix(in srgb, #000 70%, var(--studio-border));
      box-shadow: inset 0 0 0 var(--studio-border-width)
        rgb(255 255 255 / 12%);
    }

    /* Three rows of five segments preserve paint targets on phones. */
    @media (max-width: 600px) {
      .segments {
        grid-template-columns: repeat(5, minmax(0, 1fr));
      }
    }
  `];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-painted-segment-editor": GoveePaintedSegmentEditor;
  }
}

if (!customElements.get("govee-painted-segment-editor")) {
  customElements.define(
    "govee-painted-segment-editor",
    GoveePaintedSegmentEditor,
  );
}
