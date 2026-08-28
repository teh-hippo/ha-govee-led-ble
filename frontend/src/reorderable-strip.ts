import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import {
  reorderableStripKeyboardAction,
  reorderableStripModel,
  reorderableStripPointerIntent,
  type ReorderableStripItem,
  type ReorderableStripItemRole,
} from "./reorderable-strip-model";
import {
  anchoredPopoverLayout,
  rectIntersectsViewport,
  type ViewportBounds,
} from "./info-control-model";
import { studioBaseStyles } from "./studio-styles";

export type { ReorderableStripItem } from "./reorderable-strip-model";

export class GoveeReorderableStrip extends LitElement {
  @property({ attribute: false })
  public items: ReorderableStripItem[] = [];

  @property({ attribute: false })
  public activeIndex?: number;

  @property()
  public ariaLabel = "Items";

  @property()
  public itemRole: ReorderableStripItemRole = "button";

  @property()
  public addLabel = "Add item";

  @property({ type: Boolean })
  public addDisabled = false;

  @property({ type: Boolean })
  public addHidden = false;

  @property({ type: Boolean })
  public reorderDisabled = false;

  @property({ type: Boolean })
  public separateActions = false;

  @property({ type: Boolean })
  public popoverDismissDisabled = false;

  private draggedIndex?: number;
  private pointerId?: number;
  private pointerIndex?: number;
  private pointerTarget?: HTMLElement;
  private pointerX = 0;
  private pointerY = 0;
  private pointerMoved = false;
  private pointerTapCancelled = false;
  private suppressClick = false;
  private popoverTracking = false;
  private positionFrame?: number;

  public connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("resize", this.viewportResized, {
      passive: true,
    });
    window.visualViewport?.addEventListener(
      "resize",
      this.viewportResized,
      { passive: true },
    );
    window.visualViewport?.addEventListener(
      "scroll",
      this.viewportResized,
      { passive: true },
    );
  }

  public disconnectedCallback(): void {
    this.stopPopoverTracking();
    window.removeEventListener("resize", this.viewportResized);
    window.visualViewport?.removeEventListener(
      "resize",
      this.viewportResized,
    );
    window.visualViewport?.removeEventListener(
      "scroll",
      this.viewportResized,
    );
    super.disconnectedCallback();
  }

  protected updated(): void {
    if (this.popoverElement) {
      this.startPopoverTracking();
      this.schedulePopoverPosition();
    } else {
      this.stopPopoverTracking();
    }
  }

  protected render() {
    const model = reorderableStripModel(
      this.itemRole,
      this.addLabel,
      this.addDisabled,
      this.addHidden,
    );
    const tablist = model.listRole === "tablist";
    return html`
      <div class="strip ${this.separateActions ? "separate-actions" : ""}">
        <div class="strip-items">
          ${tablist
            ? html`
                <div
                  class="item-list"
                  role="tablist"
                  aria-label=${this.ariaLabel}
                >
                  ${this.items.map((item, index) =>
                    this.renderItemButton(item, index, true),
                  )}
                </div>
              `
            : html`
                <ul class="item-list" aria-label=${this.ariaLabel}>
                  ${this.items.map(
                    (item, index) => html`
                      <li class="item-container">
                        ${this.renderItemButton(item, index, false)}
                        <slot name="item-${index}"></slot>
                      </li>
                    `,
                  )}
                </ul>
              `}
          ${model.addAction
            ? html`
                <button
                  class="compact-action add"
                  type="button"
                  title=${model.addAction.label}
                  aria-label=${model.addAction.label}
                  ?disabled=${model.addAction.disabled}
                  @click=${this.addClicked}
                >
                  <span aria-hidden="true">+</span>
                </button>
              `
            : nothing}
        </div>
        <div class="strip-actions">
          <slot name="actions"></slot>
        </div>
      </div>
    `;
  }

  private renderItemButton(
    item: ReorderableStripItem,
    index: number,
    tab: boolean,
  ) {
    return html`
      <button
        id=${item.id ?? nothing}
        class="item item-wrapper ${item.colour ? "colour" : "label"} ${index ===
        this.activeIndex
          ? "selected"
          : ""} ${item.removeReady ? "remove-ready" : ""}"
        type="button"
        role=${tab ? "tab" : nothing}
        aria-label=${item.ariaLabel}
        aria-description=${item.ariaDescription ?? nothing}
        aria-selected=${tab
          ? String(index === this.activeIndex)
          : nothing}
        aria-controls=${item.ariaControls ?? nothing}
        tabindex=${tab
          ? index === this.activeIndex
            ? "0"
            : "-1"
          : nothing}
        data-item-index=${index}
        draggable=${this.reorderDisabled ? "false" : "true"}
        style=${item.colour
          ? `--item-colour: ${item.colour}`
          : nothing}
        ?disabled=${item.disabled}
        @click=${(event: MouseEvent) => this.itemClicked(index, event)}
        @keydown=${(event: KeyboardEvent) =>
          this.keyPressed(index, event)}
        @dragstart=${(event: DragEvent) =>
          this.dragStarted(index, event)}
        @dragover=${(event: DragEvent) => {
          if (!this.reorderDisabled) {
            event.preventDefault();
          }
        }}
        @drop=${(event: DragEvent) => this.dropped(index, event)}
        @pointerdown=${(event: PointerEvent) =>
          this.pointerStarted(index, event)}
        @pointermove=${this.pointerMovedOver}
        @pointerup=${this.pointerCompleted}
        @pointercancel=${this.pointerCancelled}
      >
        ${item.colour ? nothing : item.label}
      </button>
    `;
  }

  public focusItem(index: number): void {
    void this.updateComplete.then(() => {
      this.shadowRoot
        ?.querySelectorAll<HTMLButtonElement>(".item")
        [index]?.focus();
    });
  }

  private startPopoverTracking(): void {
    if (this.popoverTracking) {
      return;
    }
    window.addEventListener("scroll", this.viewportScrolled, {
      capture: true,
      passive: true,
    });
    this.popoverTracking = true;
  }

  private stopPopoverTracking(): void {
    if (this.positionFrame !== undefined) {
      cancelAnimationFrame(this.positionFrame);
      this.positionFrame = undefined;
    }
    if (!this.popoverTracking) {
      return;
    }
    window.removeEventListener("scroll", this.viewportScrolled, true);
    this.popoverTracking = false;
  }

  private readonly viewportResized = (): void => {
    this.schedulePopoverPosition();
  };

  private readonly viewportScrolled = (): void => {
    if (!this.mobilePopover || !this.activeItem) {
      return;
    }
    if (!rectIntersectsViewport(
      this.activeItem.getBoundingClientRect(),
      this.viewportBounds(),
    )) {
      if (!this.popoverDismissDisabled) {
        this.dispatchEvent(
          new CustomEvent("item-popover-dismissed", {
            bubbles: true,
            composed: true,
          }),
        );
      }
      return;
    }
    this.schedulePopoverPosition();
  };

  private schedulePopoverPosition(): void {
    if (this.positionFrame !== undefined) {
      cancelAnimationFrame(this.positionFrame);
    }
    this.positionFrame = requestAnimationFrame(() => {
      this.positionFrame = undefined;
      this.positionPopover();
    });
  }

  private positionPopover(): void {
    const popover = this.popoverElement;
    const trigger = this.activeItem;
    if (!popover || !trigger) {
      return;
    }
    if (!this.mobilePopover) {
      this.resetPopoverPosition(popover);
      return;
    }

    popover.classList.remove("mobile-positioned");
    popover.style.left = "0";
    popover.style.top = "0";
    popover.style.maxHeight = "none";
    const rect = popover.getBoundingClientRect();
    const naturalHeight =
      popover.scrollHeight + popover.offsetHeight - popover.clientHeight;
    const layout = anchoredPopoverLayout(
      trigger.getBoundingClientRect(),
      {
        width: rect.width,
        height: Math.max(rect.height, naturalHeight),
      },
      this.viewportBounds(),
      8,
      12,
    );
    popover.style.left = `${layout.left}px`;
    popover.style.top = `${layout.top}px`;
    popover.style.maxHeight = `${layout.maxHeight}px`;
    popover.classList.add("mobile-positioned");
  }

  private resetPopoverPosition(popover: HTMLElement): void {
    popover.classList.remove("mobile-positioned");
    popover.style.removeProperty("left");
    popover.style.removeProperty("top");
    popover.style.removeProperty("max-height");
  }

  private viewportBounds(): ViewportBounds {
    const viewport = window.visualViewport;
    return {
      left: viewport?.offsetLeft ?? 0,
      top: viewport?.offsetTop ?? 0,
      width: viewport?.width ?? window.innerWidth,
      height: viewport?.height ?? window.innerHeight,
    };
  }

  private get mobilePopover(): boolean {
    return window.matchMedia("(max-width: 600px)").matches;
  }

  private get activeItem(): HTMLButtonElement | undefined {
    if (this.activeIndex === undefined) {
      return undefined;
    }
    return this.shadowRoot
      ?.querySelectorAll<HTMLButtonElement>(".item")
      [this.activeIndex];
  }

  private get popoverElement(): HTMLElement | null {
    return this.querySelector<HTMLElement>(".strip-popover");
  }

  private itemClicked(index: number, event: MouseEvent): void {
    if (this.suppressClick && event.detail !== 0) {
      this.suppressClick = false;
      return;
    }
    this.suppressClick = false;
    this.selectItem(index);
  }

  private selectItem(index: number): void {
    this.dispatchEvent(
      new CustomEvent<{ index: number }>("item-selected", {
        detail: { index },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private addClicked(): void {
    this.dispatchEvent(
      new CustomEvent("item-added", {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private dragStarted(index: number, event: DragEvent): void {
    if (this.reorderDisabled) {
      return;
    }
    this.draggedIndex = index;
    event.dataTransfer?.setData("text/plain", String(index));
  }

  private dropped(index: number, event: DragEvent): void {
    event.preventDefault();
    if (this.draggedIndex === undefined) {
      return;
    }
    this.reorder(this.draggedIndex, index);
    this.draggedIndex = undefined;
  }

  private keyPressed(index: number, event: KeyboardEvent): void {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }
    event.preventDefault();
    const action = reorderableStripKeyboardAction(
      index,
      event.key,
      this.items.length,
      this.reorderDisabled,
      this.itemRole,
    );
    if (!action) {
      return;
    }
    if (action.kind === "select") {
      this.selectItem(action.index);
      this.focusItem(action.focusIndex);
      return;
    }
    this.reorder(action.from, action.to, true);
  }

  private pointerStarted(index: number, event: PointerEvent): void {
    if (!event.isPrimary || this.pointerId !== undefined) {
      return;
    }
    this.suppressClick = false;
    const target = event.currentTarget as HTMLButtonElement;
    target.draggable =
      event.pointerType === "mouse" && !this.reorderDisabled;
    if (
      event.pointerType === "mouse" ||
      (event.target as HTMLElement).closest(".strip-popover")
    ) {
      return;
    }
    this.pointerId = event.pointerId;
    this.pointerIndex = index;
    this.pointerTarget = target;
    this.pointerX = event.clientX;
    this.pointerY = event.clientY;
    this.pointerMoved = false;
    this.pointerTapCancelled = false;
  }

  private pointerMovedOver(event: PointerEvent): void {
    if (
      event.pointerId !== this.pointerId ||
      this.pointerIndex === undefined
    ) {
      return;
    }
    const deltaX = event.clientX - this.pointerX;
    const deltaY = event.clientY - this.pointerY;
    if (!this.pointerMoved && !this.pointerTapCancelled) {
      const intent = reorderableStripPointerIntent(
        deltaX,
        deltaY,
        this.reorderDisabled,
      );
      if (intent === "pending") {
        return;
      }
      if (intent === "cancel") {
        this.pointerTapCancelled = true;
        return;
      }
      this.pointerMoved = true;
      this.pointerTarget?.setPointerCapture(event.pointerId);
    }
    if (this.pointerTapCancelled) {
      return;
    }
    event.preventDefault();
    const target = this.shadowRoot
      ?.elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>("[data-item-index]");
    const targetIndex = Number(target?.dataset.itemIndex);
    if (
      !Number.isInteger(targetIndex) ||
      targetIndex === this.pointerIndex
    ) {
      return;
    }
    this.reorder(this.pointerIndex, targetIndex);
    this.pointerIndex = targetIndex;
  }

  private pointerCompleted(event: PointerEvent): void {
    if (event.pointerId !== this.pointerId) {
      return;
    }
    const index = this.pointerIndex;
    const activate =
      index !== undefined &&
      !this.pointerMoved &&
      !this.pointerTapCancelled;
    this.finishPointer(event);
    this.suppressClick = true;
    if (activate) {
      this.selectItem(index);
    }
  }

  private pointerCancelled(event: PointerEvent): void {
    if (event.pointerId !== this.pointerId) {
      return;
    }
    this.finishPointer(event);
    this.suppressClick = true;
  }

  private finishPointer(event: PointerEvent): void {
    const target = this.pointerTarget;
    if (target?.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
    this.pointerId = undefined;
    this.pointerIndex = undefined;
    this.pointerTarget = undefined;
    this.pointerMoved = false;
    this.pointerTapCancelled = false;
  }

  private reorder(from: number, to: number, restoreFocus = false): void {
    if (this.reorderDisabled || from === to) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<{ from: number; to: number }>("items-reordered", {
        detail: { from, to },
        bubbles: true,
        composed: true,
      }),
    );
    if (restoreFocus) {
      this.focusItem(to);
    }
  }

  static styles = [studioBaseStyles, css`
    :host {
      --strip-label-min-width: 76px;
      --strip-popover-default-width: 280px;
      --strip-remove-icon-size: 26px;
      display: block;
    }

    .strip {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: var(--studio-control-gap);
    }

    .strip-items,
    .item-list {
      display: flex;
      flex-wrap: wrap;
      gap: var(--studio-control-gap);
    }

    .strip-items {
      align-items: flex-start;
    }

    .item-list {
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .strip-actions {
      display: flex;
      flex: 0 0 auto;
      gap: var(--studio-control-gap);
    }

    .strip.separate-actions .strip-actions {
      margin-inline-start: var(--studio-compact-gap);
      padding-inline-start: var(--studio-control-gap);
      border-inline-start: var(--studio-border-width) solid
        var(--studio-border);
    }

    .item-container,
    .item-wrapper {
      position: relative;
    }

    .item-wrapper {
      touch-action: pan-y;
    }

    .item-wrapper[draggable="true"] {
      cursor: grab;
    }

    .item {
      height: var(--studio-control-height);
      padding: 0;
      border-radius: var(--studio-control-radius);
      cursor: pointer;
    }

    .compact-action,
    ::slotted(.compact-action) {
      width: var(--studio-compact-action-size);
      height: var(--studio-compact-action-size);
      min-height: var(--studio-compact-action-size);
      padding: 0;
      border-radius: var(--studio-control-radius);
      cursor: pointer;
    }

    .item {
      border: var(--studio-border-width) solid rgb(0 0 0 / 14%);
    }

    .item.colour {
      width: var(--studio-control-height);
    }

    .item.colour {
      background: var(--item-colour);
    }

    .item.label {
      min-width: var(--strip-label-min-width);
      padding: 0 var(--studio-spacing-xl);
      color: var(--primary-text-color);
      background: var(--studio-card);
      font-weight: var(--studio-font-weight-semibold);
    }

    .item.label.selected {
      color: var(--studio-blue);
      border-color: var(--studio-blue);
      background: var(--studio-blue-soft);
    }

    .item.remove-ready {
      position: relative;
      outline: var(--studio-strong-border-width) solid
        rgb(255 255 255 / 95%);
      outline-offset: calc(0px - var(--studio-micro-gap));
    }

    .item.remove-ready::after {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      color: #fff;
      font-size: var(--strip-remove-icon-size);
      font-weight: var(--studio-font-weight-medium);
      text-shadow: 0 var(--studio-border-width) var(--studio-micro-gap)
        rgb(0 0 0 / 80%);
      content: "×";
      pointer-events: none;
    }

    .compact-action,
    ::slotted(.compact-action) {
      display: grid;
      place-items: center;
      border: var(--studio-border-width) solid var(--studio-border);
      background: var(--studio-card);
      font-size: var(--studio-action-glyph-size);
      font-weight: var(--studio-font-weight-semibold);
      line-height: 0;
    }

    .compact-action > span {
      display: inline-grid;
      width: var(--studio-icon-size);
      height: var(--studio-icon-size);
      place-items: center;
      line-height: 0;
    }

    .add {
      color: var(--studio-blue);
    }

    ::slotted(.compact-action) {
      color: var(--primary-text-color);
    }

    ::slotted(.compact-action.danger-action) {
      border-color: var(--studio-danger);
      color: var(--text-primary-color, #fff);
      background: var(--studio-danger);
      font-size: var(--strip-remove-icon-size);
      font-weight: var(--studio-font-weight-medium);
      line-height: var(--studio-icon-line-height);
    }

    ::slotted(.compact-action.danger-action:hover),
    ::slotted(.compact-action.danger-action:focus-visible) {
      border-color: var(--studio-danger);
      background: color-mix(in srgb, var(--studio-danger) 84%, #000);
    }

    .item:focus-visible,
    .compact-action:focus-visible,
    ::slotted(.compact-action:focus-visible) {
      outline: var(--studio-focus-width) solid var(--studio-blue);
      outline-offset: var(--studio-focus-offset);
    }

    ::slotted(.strip-popover) {
      position: absolute;
      z-index: var(--studio-z-popover);
      top: calc(var(--studio-control-height) + var(--studio-compact-gap));
      left: 0;
      width: min(
        var(--strip-popover-width, var(--strip-popover-default-width)),
        calc(100vw - var(--studio-dialog-viewport-gutter))
      );
      padding: var(--studio-popover-padding);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-popover-radius);
      background: var(--studio-card);
      box-shadow: var(--studio-popover-shadow);
    }

    /* Promotes popovers to viewport overlays on phones to avoid clipping. */
    @media (max-width: 600px) {
      .strip.separate-actions {
        flex-direction: column;
      }

      .strip.separate-actions .strip-actions {
        margin-block-start: var(--studio-compact-gap);
        margin-inline-start: 0;
        padding-block-start: var(--studio-control-gap);
        padding-inline-start: 0;
        border-block-start: var(--studio-border-width) solid
          var(--studio-border);
        border-inline-start: 0;
      }

      ::slotted(.strip-popover) {
        position: fixed;
        top: 0;
        right: auto;
        left: 0;
        width: min(
          var(--strip-popover-width, var(--strip-popover-default-width)),
          calc(100vw - var(--studio-dialog-viewport-gutter))
        );
        overflow: auto;
        visibility: hidden;
        transform: none;
      }

      ::slotted(.strip-popover.mobile-positioned) {
        visibility: visible;
      }
    }
  `];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-reorderable-strip": GoveeReorderableStrip;
  }
}

if (!customElements.get("govee-reorderable-strip")) {
  customElements.define(
    "govee-reorderable-strip",
    GoveeReorderableStrip,
  );
}
