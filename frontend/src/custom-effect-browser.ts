import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";

import {
  buildCustomEffectEntries,
  newEffectKindForCategory,
  type CustomEffectListContext,
  type CustomEffectListEntry,
} from "./custom-effect-list";
import type { CustomEffectCategory } from "./effect-editor-model";
import { customEffectCategoryLabel } from "./custom-effect-workflow";
import {
  studioBaseStyles,
  studioSelectorStyles,
  studioWorkspaceStyles,
} from "./studio-styles";
import { scrollSelectedIntoView } from "./ui-utils";

export interface CustomEffectBrowserEntryRequest {
  entry: CustomEffectListEntry;
  returnFocus: HTMLElement;
}

export interface CustomEffectBrowserCategoryRequest {
  category: CustomEffectCategory;
  returnFocus: HTMLElement;
}

export class GoveeCustomEffectBrowser extends LitElement {
  @property({ attribute: false })
  public context?: CustomEffectListContext;

  @property()
  public category: CustomEffectCategory = "single-layer";

  @property()
  public currentItemId?: string;

  @property()
  public templateSelection?: string;

  @property({ type: Boolean })
  public newSelected = false;

  @property({ type: Boolean })
  public isAdmin = false;

  private lastSelectionIdentity?: string;

  protected updated(changed: Map<PropertyKey, unknown>): void {
    const selectionIdentity = this.selectionIdentity;
    if (!selectionIdentity) {
      this.lastSelectionIdentity = undefined;
      return;
    }
    if (
      (selectionIdentity !== this.lastSelectionIdentity ||
        changed.has("category") ||
        changed.has("context")) &&
      scrollSelectedIntoView(
        this.shadowRoot?.querySelector(".item-sidebar") ?? null,
      )
    ) {
      this.lastSelectionIdentity = selectionIdentity;
    }
  }

  protected render() {
    const context = this.context;
    if (!context) {
      return nothing;
    }
    const entries = buildCustomEffectEntries(context, this.category);
    const canCreate =
      (this.category === "music" &&
        Boolean(context.catalogue?.music_modes.length)) ||
      newEffectKindForCategory(context, this.category) !== undefined;
    return html`
      <aside
        class="sidebar item-sidebar library"
        aria-label=${customEffectCategoryLabel(this.category)}
      >
        ${canCreate
          ? html`
              <button
                class="selector item new-effect-action ${this.newSelected
                  ? "selected"
                  : ""}"
                type="button"
                aria-pressed=${String(this.newSelected)}
                ?disabled=${!this.isAdmin}
                @click=${this.requestNew}
              >
                <span
                  ><span class="new-effect-icon" aria-hidden="true"></span
                  >New</span
                >
              </button>
            `
          : nothing}
        ${entries.map((entry) => this.entryButton(entry))}
      </aside>
    `;
  }

  private get selectionIdentity(): string | undefined {
    if (this.newSelected) {
      return "new";
    }
    if (this.currentItemId) {
      return `saved:${this.currentItemId}`;
    }
    return this.templateSelection;
  }

  private entryButton(entry: CustomEffectListEntry) {
    const selected =
      entry.kind === "saved"
        ? this.currentItemId === entry.item.id
        : this.currentItemId === undefined &&
          this.templateSelection === entry.key;
    return html`
      <button
        class="selector item ${selected ? "selected" : ""}"
        type="button"
        aria-pressed=${String(selected)}
        ?disabled=${entry.kind !== "saved" && !this.isAdmin}
        @click=${(event: Event) => {
          this.dispatchEvent(
            new CustomEvent<CustomEffectBrowserEntryRequest>(
              "custom-entry-requested",
              {
                detail: {
                  entry,
                  returnFocus: event.currentTarget as HTMLElement,
                },
                bubbles: true,
                composed: true,
              },
            ),
          );
        }}
      >
        <span>${entry.label}</span>
        ${entry.kind === "saved"
          ? html`
              <span
                class="user-effect-marker"
                title="User-created effect"
                aria-label="User-created effect"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8m0 2c-4.42 0-8 1.79-8 4v2h16v-2c0-2.21-3.58-4-8-4Z"></path>
                </svg>
              </span>
            `
          : nothing}
      </button>
    `;
  }

  private requestNew(event: Event): void {
    this.dispatchEvent(
      new CustomEvent<CustomEffectBrowserCategoryRequest>(
        "custom-new-requested",
        {
          detail: {
            category: this.category,
            returnFocus: event.currentTarget as HTMLElement,
          },
          bubbles: true,
          composed: true,
        },
      ),
    );
  }

  static styles = [
    studioBaseStyles,
    studioSelectorStyles,
    studioWorkspaceStyles,
    css`
      :host {
        --new-effect-stroke-width: 1.5px;
        display: contents;
      }

      .new-effect-action {
        color: var(--studio-blue);
      }

      .new-effect-icon {
        display: inline-block;
        width: var(--studio-spacing-lg);
        height: var(--studio-spacing-lg);
        margin-inline-end: var(--studio-compact-gap);
        background:
          linear-gradient(currentColor, currentColor) center /
            var(--studio-spacing-lg) var(--new-effect-stroke-width) no-repeat,
          linear-gradient(currentColor, currentColor) center /
            var(--new-effect-stroke-width) var(--studio-spacing-lg) no-repeat;
      }

      .item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--studio-compact-gap);
      }

      .user-effect-marker {
        display: inline-grid;
        width: var(--studio-icon-size);
        height: var(--studio-icon-size);
        flex: 0 0 var(--studio-icon-size);
        place-items: center;
        color: var(--studio-muted);
      }

      .user-effect-marker svg {
        width: var(--studio-small-swatch-size);
        height: var(--studio-small-swatch-size);
        fill: currentColor;
      }

      /* Places effects above the editor beside HA's docked sidebar. */
      @media (min-width: 901px) and (max-width: 1320px) {
        .library {
          grid-row: 1;
          grid-column: 2;
          max-height: var(--studio-stacked-list-max-height);
          border-inline-end: 0;
          border-bottom: var(--studio-border-width) solid var(--studio-border);
        }
      }

      /* The panel owns document-flow placement below this width. */
      @media (max-width: 900px) {
        :host {
          display: block;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-custom-effect-browser": GoveeCustomEffectBrowser;
  }
}

if (!customElements.get("govee-custom-effect-browser")) {
  customElements.define(
    "govee-custom-effect-browser",
    GoveeCustomEffectBrowser,
  );
}
