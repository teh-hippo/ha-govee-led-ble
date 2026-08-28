import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import {
  adjustAppliedAreaLeftEdge,
  adjustAppliedAreaRightEdge,
  appliedAreaEffectiveWidth,
  layerAppliedAreaSegments,
  moveAppliedArea,
  withAppliedAreaSegments,
} from "./advanced-effect-model";
import type { LivePreviewInteraction } from "./live-preview-controller";
import { studioActionStyles, studioBaseStyles } from "./studio-styles";
import type { EffectLayer } from "./types";
import { rgbToHex } from "./ui-utils";

const DEFAULT_SEGMENT_COUNT = 15;
type AppliedAreaControl = "left" | "move" | "right";

interface AppliedAreaDrag {
  control: AppliedAreaControl;
  pointerId: number;
  pointerStart: number;
  start: number;
  end: number;
  track: HTMLElement;
}

export interface AppliedAreaChange {
  layer: EffectLayer;
  interaction: LivePreviewInteraction;
}

export class GoveeAppliedAreaControl extends LitElement {
  @property({ attribute: false })
  public layer?: EffectLayer;

  @property({ type: Boolean })
  public disabled = false;

  @property({ type: Number })
  public segmentCount = DEFAULT_SEGMENT_COUNT;

  @state()
  private activeControl?: AppliedAreaControl;

  private drag?: AppliedAreaDrag;

  public disconnectedCallback(): void {
    this.drag = undefined;
    this.activeControl = undefined;
    super.disconnectedCallback();
  }

  protected render() {
    const layer = this.layer;
    if (!layer) {
      return nothing;
    }
    const effectiveWidth = appliedAreaEffectiveWidth(
      layer.area.width_tenths,
    );
    const areaIsEditable =
      layer.area.start_tenths >= 0 &&
      layer.area.start_tenths <= 9 &&
      effectiveWidth >= 1 &&
      effectiveWidth <= 10 - layer.area.start_tenths;
    const segmentCount = this.validSegmentCount;
    const segmentColour = rgbToHex(layer.palette[0] ?? [47, 111, 237]);
    const visibleSegments = layerAppliedAreaSegments(layer, segmentCount);
    const visualStart = (visibleSegments.start / segmentCount) * 100;
    const visualEnd = (visibleSegments.end / segmentCount) * 100;
    return html`
      <div class="area-control">
        <div
          class="area-range"
          style="--area-segment-count: ${segmentCount}; --area-colour: ${segmentColour};"
          aria-label="Applied area"
        >
          <div class="area-segments" aria-hidden="true">
            ${Array.from(
              { length: segmentCount },
              (_, index) => html`
                <span
                  class=${areaIsEditable &&
                  index >= visibleSegments.start &&
                  index < visibleSegments.end
                    ? "covered"
                    : ""}
                ></span>
              `,
            )}
          </div>
          ${areaIsEditable
            ? html`
                <div
                  class="area-window"
                  style="left: ${visualStart}%; width: ${visualEnd -
                  visualStart}%;"
                >
                  ${this.renderSlider(
                    "move",
                    "Move applied area",
                    visibleSegments.start,
                    0,
                    segmentCount - visibleSegments.length,
                    `Segments ${visibleSegments.start + 1} to ${visibleSegments.end}`,
                    visibleSegments.start + 1,
                  )}
                  ${this.renderSlider(
                    "left",
                    "Applied area left edge",
                    visibleSegments.start,
                    0,
                    visibleSegments.end - 1,
                    `Segment ${visibleSegments.start + 1}`,
                    visibleSegments.start + 1,
                  )}
                  ${this.renderSlider(
                    "right",
                    "Applied area right edge",
                    visibleSegments.end,
                    visibleSegments.start + 1,
                    segmentCount,
                    `Segment ${visibleSegments.end}`,
                    visibleSegments.end,
                  )}
                </div>
              `
            : nothing}
        </div>
      </div>
      ${!areaIsEditable
        ? html`
            <p class="muted">
              This loaded layer uses an applied area that is not editable here.
              It remains preserved until replaced.
            </p>
            <button
              class="secondary"
              type="button"
              ?disabled=${this.disabled}
              @click=${this.setFullStrip}
            >
              Set full strip
            </button>
          `
        : nothing}
    `;
  }

  private renderSlider(
    control: AppliedAreaControl,
    label: string,
    value: number,
    minimum: number,
    maximum: number,
    valueText: string,
    displayValue: number,
  ) {
    return html`
      <div
        class=${control === "move"
          ? "area-move"
          : `area-handle area-handle-${control}`}
        role="slider"
        tabindex=${this.disabled ? -1 : 0}
        aria-label=${label}
        aria-orientation="horizontal"
        aria-valuemin=${minimum}
        aria-valuemax=${maximum}
        aria-valuenow=${value}
        aria-valuetext=${valueText}
        aria-disabled=${this.disabled ? "true" : "false"}
        @keydown=${(event: KeyboardEvent) => this.keyPressed(event, control)}
        @pointerdown=${(event: PointerEvent) =>
          this.startDrag(event, control)}
        @pointermove=${this.pointerMoved}
        @pointerup=${this.finishDrag}
        @pointercancel=${this.finishDrag}
      >
        ${control !== "move" && this.activeControl === control
          ? html`<span class="area-drag-value" aria-hidden="true"
              >${displayValue}</span
            >`
          : nothing}
      </div>
    `;
  }

  private keyPressed(
    event: KeyboardEvent,
    control: AppliedAreaControl,
  ): void {
    const { start, end } = this.renderedSegments(
      event.currentTarget as HTMLElement,
    );
    const direction =
      event.key === "ArrowLeft" || event.key === "ArrowDown"
        ? -1
        : event.key === "ArrowRight" || event.key === "ArrowUp"
          ? 1
          : undefined;
    let next: number;
    if (event.key === "Home") {
      next = control === "right" ? start + 1 : 0;
    } else if (event.key === "End") {
      next =
        control === "left"
          ? end - 1
          : control === "right"
            ? this.validSegmentCount
            : this.validSegmentCount - (end - start);
    } else if (direction !== undefined) {
      next = (control === "right" ? end : start) + direction;
    } else {
      return;
    }
    event.preventDefault();
    this.applyControl(control, start, end, next, "committed");
  }

  private startDrag(
    event: PointerEvent,
    control: AppliedAreaControl,
  ): void {
    if (this.disabled || (event.button !== 0 && event.pointerType !== "touch")) {
      return;
    }
    const target = event.currentTarget as HTMLElement;
    const track = target.closest<HTMLElement>(".area-range");
    if (!track) {
      return;
    }
    const { start, end } = this.renderedSegments(target);
    target.focus();
    event.preventDefault();
    event.stopPropagation();
    target.setPointerCapture(event.pointerId);
    this.activeControl = control;
    this.drag = {
      control,
      pointerId: event.pointerId,
      pointerStart: event.clientX,
      start,
      end,
      track,
    };
  }

  private readonly pointerMoved = (event: PointerEvent): void => {
    const drag = this.drag;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    event.preventDefault();
    const bounds = drag.track.getBoundingClientRect();
    const next =
      drag.control === "move"
        ? drag.start +
          Math.round(
            ((event.clientX - drag.pointerStart) / bounds.width) *
              this.validSegmentCount,
          )
        : Math.round(
            ((event.clientX - bounds.left) / bounds.width) *
              this.validSegmentCount,
          );
    this.applyControl(drag.control, drag.start, drag.end, next, "changing");
  };

  private readonly finishDrag = (event: PointerEvent): void => {
    const drag = this.drag;
    if (drag?.pointerId !== event.pointerId) {
      return;
    }
    const target = event.currentTarget as HTMLElement;
    if (target.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
    const segments = this.layer
      ? layerAppliedAreaSegments(this.layer, this.validSegmentCount)
      : undefined;
    const changed =
      segments !== undefined &&
      (segments.start !== drag.start || segments.end !== drag.end);
    this.drag = undefined;
    this.activeControl = undefined;
    if (changed) {
      this.emitAreaChange("committed");
    }
  };

  private applyControl(
    control: AppliedAreaControl,
    start: number,
    end: number,
    next: number,
    interaction: LivePreviewInteraction,
  ): void {
    const area =
      control === "left"
        ? adjustAppliedAreaLeftEdge(end, next, this.validSegmentCount)
        : control === "right"
          ? adjustAppliedAreaRightEdge(start, next, this.validSegmentCount)
          : moveAppliedArea(start, end, next, this.validSegmentCount);
    this.setArea(area.start, area.end, interaction);
  }

  private setArea(
    start: number,
    end: number,
    interaction: LivePreviewInteraction,
  ): void {
    if (!this.layer || this.disabled) {
      return;
    }
    this.layer = withAppliedAreaSegments(
      this.layer,
      start,
      end,
      this.validSegmentCount,
    );
    this.emitAreaChange(interaction);
  }

  private emitAreaChange(interaction: LivePreviewInteraction): void {
    if (!this.layer || this.disabled) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<AppliedAreaChange>("area-changed", {
        detail: { layer: this.layer, interaction },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private readonly setFullStrip = (): void => {
    if (!this.layer || this.disabled) {
      return;
    }
    this.setArea(0, this.validSegmentCount, "committed");
  };

  private renderedSegments(origin: HTMLElement): {
    start: number;
    end: number;
  } {
    const areaWindow = origin.closest(".area-window");
    const left = Number(
      areaWindow
        ?.querySelector<HTMLElement>(".area-handle-left")
        ?.getAttribute("aria-valuenow"),
    );
    const right = Number(
      areaWindow
        ?.querySelector<HTMLElement>(".area-handle-right")
        ?.getAttribute("aria-valuenow"),
    );
    if (
      Number.isInteger(left) &&
      Number.isInteger(right) &&
      left >= 0 &&
      right > left &&
      right <= this.validSegmentCount
    ) {
      return { start: left, end: right };
    }
    const segments = layerAppliedAreaSegments(
      this.layer!,
      this.validSegmentCount,
    );
    return { start: segments.start, end: segments.end };
  }

  private get validSegmentCount(): number {
    return Number.isInteger(this.segmentCount) && this.segmentCount > 0
      ? this.segmentCount
      : DEFAULT_SEGMENT_COUNT;
  }

  static styles = [
    studioBaseStyles,
    studioActionStyles,
    css`
      :host {
        --area-control-horizontal-padding: var(--studio-spacing-5xl);
        --area-control-mobile-padding: var(--studio-spacing-3xl);
        --area-track-height: 64px;
        --area-segment-gap: var(--studio-spacing-xxs);
        --area-segment-radius: var(--studio-swatch-radius);
        --area-move-indicator-width: var(--studio-spacing-2xl);
        --area-move-indicator-height: var(--studio-spacing-md);
        --area-move-indicator-radius: 5px;
        --area-move-dot-size: 1.5px;
        --area-move-dot-fade-size: 1.8px;
        --area-move-dot-period: var(--studio-spacing-xs);
        --area-handle-hit-width: var(--studio-touch-target-size);
        --area-handle-hit-height: 56px;
        --area-handle-grip-width: var(--studio-compact-gap);
        --area-handle-grip-height: var(--studio-spacing-6xl);
        --area-handle-body-width: var(--studio-spacing-5xl);
        --area-handle-body-height: 44px;
        --area-handle-body-radius: 10px;
        --area-tooltip-gap: 7px;
        --area-tooltip-min-width: var(--studio-spacing-7xl);
        --area-z-move-target: 1;
        --area-z-window: 2;
        --area-z-handle: 3;
        --area-z-tooltip: 5;
        --area-z-handle-background: -1;
        display: block;
      }

      .area-control {
        margin-bottom: var(--studio-spacing-2xl);
        padding: var(--studio-micro-gap)
          var(--area-control-horizontal-padding) 0;
      }

      .area-range {
        position: relative;
        min-height: var(--area-track-height);
        touch-action: pan-y;
      }

      .area-segments {
        display: grid;
        grid-template-columns: repeat(
          var(--area-segment-count),
          minmax(0, 1fr)
        );
        gap: var(--area-segment-gap);
        min-height: var(--area-track-height);
        pointer-events: none;
      }

      .area-segments span {
        min-width: 0;
        min-height: var(--area-track-height);
        border: var(--studio-border-width) solid
          color-mix(in srgb, var(--area-colour) 35%, var(--studio-border));
        border-radius: var(--area-segment-radius);
        background: color-mix(
          in srgb,
          var(--area-colour) 14%,
          var(--studio-card)
        );
      }

      .area-segments span.covered {
        border-color: color-mix(
          in srgb,
          var(--area-colour) 42%,
          var(--studio-border)
        );
        background: color-mix(
          in srgb,
          var(--area-colour) 24%,
          var(--studio-card)
        );
      }

      .area-window {
        position: absolute;
        z-index: var(--area-z-window);
        top: 0;
        bottom: 0;
        min-width: var(--studio-border-width);
        border-block: var(--studio-strong-border-width) solid
          color-mix(in srgb, var(--area-colour) 48%, var(--studio-border));
        background: color-mix(in srgb, var(--area-colour) 5%, transparent);
      }

      .area-move {
        position: absolute;
        inset: 0;
        z-index: var(--area-z-move-target);
        min-width: var(--area-handle-hit-width);
        cursor: grab;
      }

      .area-move::after {
        position: absolute;
        top: 50%;
        left: 50%;
        width: var(--area-move-indicator-width);
        height: var(--area-move-indicator-height);
        border-radius: var(--area-move-indicator-radius);
        background-image: radial-gradient(
          circle,
          color-mix(in srgb, var(--area-colour) 52%, #000)
            var(--area-move-dot-size),
          transparent var(--area-move-dot-fade-size)
        );
        background-position: 0 0;
        background-size:
          var(--area-move-dot-period)
          var(--area-move-dot-period);
        content: "";
        opacity: 0.72;
        transform: translate(-50%, -50%);
      }

      .area-move:active {
        cursor: grabbing;
      }

      .area-handle {
        position: absolute;
        z-index: var(--area-z-handle);
        top: 50%;
        width: var(--area-handle-hit-width);
        min-height: var(--area-handle-hit-height);
        border: 0;
        background: transparent;
        cursor: ew-resize;
        transform: translateY(-50%);
      }

      .area-handle::before {
        position: absolute;
        top: 50%;
        left: 50%;
        width: var(--area-handle-grip-width);
        height: var(--area-handle-grip-height);
        border-inline: var(--studio-strong-border-width) solid
          color-mix(in srgb, var(--area-colour) 72%, #000);
        content: "";
        transform: translate(-50%, -50%);
      }

      .area-handle::after {
        position: absolute;
        z-index: var(--area-z-handle-background);
        top: 50%;
        left: 50%;
        width: var(--area-handle-body-width);
        height: var(--area-handle-body-height);
        border: var(--studio-strong-border-width) solid
          color-mix(in srgb, var(--area-colour) 78%, #000);
        border-radius: var(--area-handle-body-radius);
        background: var(--studio-card);
        box-shadow: 0 var(--studio-strong-border-width)
          var(--studio-compact-gap) rgb(0 0 0 / 18%);
        content: "";
        transform: translate(-50%, -50%);
      }

      .area-handle-left {
        left: 0;
        transform: translate(-50%, -50%);
      }

      .area-handle-right {
        right: 0;
        transform: translate(50%, -50%);
      }

      .area-move:focus-visible,
      .area-handle:focus-visible {
        outline: var(--studio-focus-width) solid var(--studio-blue);
        outline-offset: var(--studio-focus-offset);
      }

      .area-move[aria-disabled="true"],
      .area-handle[aria-disabled="true"] {
        cursor: default;
        opacity: var(--studio-disabled-opacity);
      }

      .area-drag-value {
        position: absolute;
        z-index: var(--area-z-tooltip);
        bottom: calc(100% + var(--area-tooltip-gap));
        left: 50%;
        min-width: var(--area-tooltip-min-width);
        padding: var(--studio-micro-gap) var(--area-tooltip-gap);
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-control-radius);
        color: var(--primary-text-color);
        background: var(--studio-card);
        box-shadow: var(--studio-popover-shadow);
        font-size: var(--studio-caption-size);
        font-weight: var(--studio-font-weight-emphasis);
        font-variant-numeric: tabular-nums;
        line-height: var(--studio-icon-line-height);
        text-align: center;
        transform: translateX(-50%);
      }

      .muted {
        color: var(--studio-muted);
        font-size: var(--studio-parameter-label-size);
        line-height: var(--studio-muted-line-height);
      }

      /* Narrows side padding while retaining full handle hit targets. */
      @media (max-width: 760px) {
        .area-control {
          padding-inline: var(--area-control-mobile-padding);
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-applied-area-control": GoveeAppliedAreaControl;
  }
}

if (!customElements.get("govee-applied-area-control")) {
  customElements.define(
    "govee-applied-area-control",
    GoveeAppliedAreaControl,
  );
}
