import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import {
  INFO_GLYPH,
  popoverPosition,
  rectIntersectsViewport,
  type ViewportBounds,
} from "./info-control-model";
import { studioBaseStyles } from "./studio-styles";

export class GoveeInfoControl extends LitElement {
  @property()
  public label = "More information";

  @property()
  public text = "";

  @property()
  public variant: "info" | "error" = "info";

  @state()
  private open = false;

  private intersectionObserver?: IntersectionObserver;
  private scrollTargets: EventTarget[] = [];
  private positionFrame?: number;

  public disconnectedCallback(): void {
    this.stopTracking();
    super.disconnectedCallback();
  }

  protected render() {
    const nativePopover = this.supportsNativePopover();
    return html`
      <button
        class="info-trigger"
        type="button"
        aria-label=${this.label}
        aria-controls="information"
        aria-expanded=${String(this.open)}
        title=${this.label}
        popovertarget=${nativePopover ? "information" : nothing}
        @click=${nativePopover ? nothing : this.toggleFallback}
      >
        ${this.variant === "error"
          ? html`
              <svg
                class="error"
                aria-hidden="true"
                viewBox="0 0 24 24"
                width="18"
                height="18"
              >
                <circle cx="12" cy="12" r="9"></circle>
                <path d="M12 7.5v6"></path>
                <circle class="info-dot" cx="12" cy="16.5" r="0.75"></circle>
              </svg>
            `
          : html`<span class="info-glyph" aria-hidden="true">${INFO_GLYPH}</span>`}
      </button>
      <div
        id="information"
        class="info-popover ${this.open ? "fallback-open" : ""}"
        popover=${nativePopover ? "auto" : nothing}
        role="note"
        aria-label=${this.label}
        ?hidden=${!nativePopover && !this.open}
        @toggle=${this.popoverToggled}
      >
        ${this.text}
        <slot name="actions"></slot>
      </div>
    `;
  }

  private supportsNativePopover(): boolean {
    return "showPopover" in HTMLElement.prototype;
  }

  private readonly toggleFallback = (): void => {
    this.open = !this.open;
    if (this.open) {
      void this.updateComplete.then(() => this.startTracking());
    } else {
      this.stopTracking();
    }
  };

  private readonly popoverToggled = (event: ToggleEvent): void => {
    this.open = event.newState === "open";
    if (this.open) {
      this.startTracking();
    } else {
      this.stopTracking();
    }
  };

  private startTracking(): void {
    this.stopTracking();
    const trigger = this.trigger;
    if (!trigger) {
      return;
    }
    this.scrollTargets = this.scrollAncestors(trigger);
    for (const target of this.scrollTargets) {
      target.addEventListener("scroll", this.viewportChanged, {
        passive: true,
      });
    }
    window.addEventListener("resize", this.viewportChanged, {
      passive: true,
    });
    window.visualViewport?.addEventListener(
      "resize",
      this.viewportChanged,
      { passive: true },
    );
    window.visualViewport?.addEventListener(
      "scroll",
      this.viewportChanged,
      { passive: true },
    );
    if ("IntersectionObserver" in window) {
      this.intersectionObserver = new IntersectionObserver(
        ([entry]) => {
          if (!entry?.isIntersecting) {
            this.closePopover();
          }
        },
        { threshold: 0 },
      );
      this.intersectionObserver.observe(trigger);
    }
    this.schedulePosition();
  }

  private stopTracking(): void {
    if (this.positionFrame !== undefined) {
      cancelAnimationFrame(this.positionFrame);
      this.positionFrame = undefined;
    }
    for (const target of this.scrollTargets) {
      target.removeEventListener("scroll", this.viewportChanged);
    }
    this.scrollTargets = [];
    window.removeEventListener("resize", this.viewportChanged);
    window.visualViewport?.removeEventListener(
      "resize",
      this.viewportChanged,
    );
    window.visualViewport?.removeEventListener(
      "scroll",
      this.viewportChanged,
    );
    this.intersectionObserver?.disconnect();
    this.intersectionObserver = undefined;
    this.popoverElement?.classList.remove("positioned");
  }

  private readonly viewportChanged = (): void => {
    const trigger = this.trigger;
    if (!trigger || !rectIntersectsViewport(
      trigger.getBoundingClientRect(),
      this.viewportBounds(),
    )) {
      this.closePopover();
      return;
    }
    this.schedulePosition();
  };

  private schedulePosition(): void {
    if (this.positionFrame !== undefined) {
      cancelAnimationFrame(this.positionFrame);
    }
    this.positionFrame = requestAnimationFrame(() => {
      this.positionFrame = undefined;
      this.positionPopover();
    });
  }

  private positionPopover(): void {
    const trigger = this.trigger;
    const popover = this.popoverElement;
    if (!trigger || !popover || !this.open) {
      return;
    }
    const position = popoverPosition(
      trigger.getBoundingClientRect(),
      popover.getBoundingClientRect(),
      this.viewportBounds(),
      8,
      12,
    );
    popover.style.left = `${position.left}px`;
    popover.style.top = `${position.top}px`;
    popover.classList.add("positioned");
  }

  private closePopover(): void {
    const popover = this.popoverElement;
    if (this.supportsNativePopover() && popover?.matches(":popover-open")) {
      popover.hidePopover();
      return;
    }
    if (this.open) {
      this.open = false;
      this.stopTracking();
    }
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

  private scrollAncestors(element: HTMLElement): EventTarget[] {
    const targets = new Set<EventTarget>();
    let current: Node | null = element;
    while (current) {
      if (current instanceof HTMLElement) {
        const style = getComputedStyle(current);
        if (/(auto|scroll|overlay)/.test(
          `${style.overflow}${style.overflowX}${style.overflowY}`,
        )) {
          targets.add(current);
        }
      }
      current =
        current.parentNode instanceof ShadowRoot
          ? current.parentNode.host
          : current.parentNode;
    }
    targets.add(window);
    return [...targets];
  }

  private get trigger(): HTMLButtonElement | null {
    return this.shadowRoot?.querySelector(".info-trigger") ?? null;
  }

  private get popoverElement(): HTMLDivElement | null {
    return this.shadowRoot?.querySelector(".info-popover") ?? null;
  }

  static styles = [
    studioBaseStyles,
    css`
      :host {
        display: inline-flex;
        flex: 0 0 auto;
      }

      .info-trigger {
        display: inline-grid;
        width: var(--studio-info-control-size);
        min-height: var(--studio-info-control-size);
        padding: 0;
        place-items: center;
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-round-radius);
        color: var(--studio-muted);
        background: var(--studio-card);
        font-size: var(--studio-info-control-font-size);
        font-weight: var(--studio-font-weight-semibold);
        line-height: var(--studio-icon-line-height);
        cursor: help;
      }

      .info-trigger:hover,
      .info-trigger:focus-visible {
        color: var(--studio-blue);
        border-color: var(--studio-blue);
      }

      .info-trigger:has(svg.error) {
        color: var(--error-color, #db4437);
        border-color: var(--error-color, #db4437);
      }

      .info-trigger:focus-visible {
        outline: var(--studio-focus-width) solid var(--studio-blue);
        outline-offset: var(--studio-focus-offset);
      }

      svg {
        display: block;
        fill: none;
        stroke: currentcolor;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-width: 1.75;
      }

      .info-glyph {
        display: block;
        line-height: 1;
      }

      .info-dot {
        fill: currentcolor;
        stroke: none;
      }

      .info-popover {
        position: fixed;
        inset: auto;
        width: min(
          var(--studio-info-popover-width),
          calc(100vw - var(--studio-dialog-viewport-gutter))
        );
        max-height: calc(100vh - var(--studio-dialog-viewport-gutter));
        margin: 0;
        padding: var(--studio-popover-padding);
        overflow: auto;
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-popover-radius);
        color: var(--primary-text-color);
        background: var(--studio-card);
        box-shadow: var(--studio-popover-shadow);
        font-size: var(--studio-parameter-label-size);
        line-height: var(--studio-muted-line-height);
        visibility: hidden;
      }

      .info-popover.positioned {
        visibility: visible;
      }

      .info-popover.fallback-open {
        z-index: var(--studio-z-popover);
      }

      ::slotted([slot="actions"]) {
        display: flex;
        flex-wrap: wrap;
        gap: var(--studio-action-gap);
        margin-top: var(--studio-control-gap);
      }

    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-info-control": GoveeInfoControl;
  }
}

if (!customElements.get("govee-info-control")) {
  customElements.define("govee-info-control", GoveeInfoControl);
}
