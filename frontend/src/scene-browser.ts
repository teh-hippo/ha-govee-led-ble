import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import type { EffectStudioApi } from "./api";
import { effectOriginDescription } from "./effect-editor-model";
import type { SegmentedControlChange } from "./segmented-control";
import "./segmented-control";
import {
  nativeSceneActions,
  sceneBrowserCategories,
  sceneBrowserEntries,
  sceneHasParameterSurface,
  sceneKey,
  sceneSelectionKey,
  sameSceneDeviceIdentity,
  sceneSpeedOptions,
  type CategorySelection,
  type NativeSceneAction,
  type SceneBrowserViewState,
  type SceneInitialSelection,
  type ScenePreviewRequest,
} from "./scene-browser-model";
import { SceneBrowserWorkflow, type SceneEditSelection } from "./scene-browser-workflow";
import {
  studioActionStyles,
  studioBaseStyles,
  studioCardStyles,
  studioEditorStyles,
  studioFormStyles,
  studioSelectorStyles,
  studioVisuallyHiddenStyles,
  studioWorkspaceStyles,
} from "./studio-styles";
import type {
  DeviceCapabilities,
  LibraryItem,
  LibrarySnapshot,
  PreviewStatus,
  SceneSummary,
} from "./types";
import { scrollSelectedIntoView } from "./ui-utils";

export type { SceneInitialSelection, ScenePreviewRequest } from "./scene-browser-model";

export interface LibraryItemDeleteRequest {
  id: string;
  version: number;
  updated_at: string;
  name: string;
  discardsOpenEdits: boolean;
  returnFocus: HTMLElement;
}

function categorySelection(value: string): CategorySelection {
  if (value === "all" || value === "custom") {
    return value;
  }
  return Number(value);
}

export class GoveeSceneBrowser extends LitElement {
  @property({ attribute: false })
  public api?: EffectStudioApi;

  @property({ attribute: false })
  public device?: DeviceCapabilities;

  @property({ attribute: false })
  public library: LibrarySnapshot = { items: [] };

  @property({ type: Boolean })
  public isAdmin = false;

  @property({ type: Boolean })
  public autoSaveEnabled = false;

  @property({ type: Boolean })
  public autoSaveFailed = false;

  @property({ type: Boolean })
  public liveApplyEnabled = true;

  @property({ attribute: false })
  public savedSceneSelection?: LibraryItem;

  @property({ attribute: false })
  public initialSelection?: SceneInitialSelection;

  @property({ type: Boolean })
  public externalEditActive = false;

  @property({ type: Number })
  public editorTransitionEpoch = 0;

  @property({ attribute: false })
  public previewStatus?: PreviewStatus;

  @property({ type: Boolean })
  public stateUpdatesAvailable = true;

  @property({ attribute: false })
  public requestTransition?: (
    transition: () => void | Promise<void>,
    returnFocus: HTMLElement,
    save?: () => Promise<boolean>,
  ) => Promise<void>;

  @state()
  private viewState: SceneBrowserViewState;

  private readonly workflow: SceneBrowserWorkflow;
  private lastScrolledSelectionKey?: string;

  public constructor() {
    super();
    this.workflow = new SceneBrowserWorkflow({
      changed: (viewState) => {
        this.viewState = viewState;
      },
      initialSelectionFinished: (opened) => {
        this.emit(opened ? "scene-initial-selection-opened" : "scene-initial-selection-failed");
      },
      libraryItemSaved: (
        item,
        configEntryId,
        selectionIsCurrent,
        panelTransitionEpoch,
      ) => {
        this.emit("library-item-saved", {
          item,
          configEntryId,
          selectionIsCurrent,
          panelTransitionEpoch,
        });
      },
      error: (message, options) => {
        this.emit("studio-error", {
          message,
          ...options,
        });
      },
      workStateChanged: (dirty) => {
        this.emit("scene-work-state-changed", { dirty });
      },
    });
    this.viewState = this.workflow.state;
  }

  public savePendingWork(): Promise<boolean> {
    return this.workflow.savePendingWork(
      this.isAdmin,
      this.editorTransitionEpoch,
    );
  }

  public currentPreviewRequest(): ScenePreviewRequest | undefined {
    return this.workflow.previewRequest(
      this.isAdmin,
      this.autoSaveEnabled,
    );
  }

  public refreshSelectedDefault(): void {
    void this.workflow.refreshSelectedDefault();
  }

  public invokeSaveShortcut(): boolean {
    if (!this.isAdmin) {
      return false;
    }
    if (this.workflow.sceneDefaultDirty) {
      void this.workflow.setCurrentDefault(true);
      return true;
    }
    if (this.viewState.saving) {
      return false;
    }
    if (
      this.viewState.selectedItem &&
      this.workflow.sceneDirty &&
      this.viewState.content?.kind !== "scene_layered"
    ) {
      void this.workflow.save(true, this.editorTransitionEpoch);
      return true;
    }
    return false;
  }

  protected willUpdate(changed: Map<PropertyKey, unknown>): void {
    const previousDevice = changed.get("device") as
      | DeviceCapabilities
      | undefined;
    const deviceIdentityChanged =
      changed.has("device") &&
      !sameSceneDeviceIdentity(previousDevice, this.device);
    if (deviceIdentityChanged || changed.has("api")) {
      this.workflow.configure(this.api, this.device);
    }
    if (changed.has("initialSelection")) {
      this.workflow.setInitialSelection(this.initialSelection);
    }
    if (changed.has("savedSceneSelection") && this.savedSceneSelection) {
      this.workflow.synchroniseSavedSelection(this.savedSceneSelection);
    }
    if (changed.has("library")) {
      this.workflow.setLibrary(this.library);
    }
    if (changed.has("stateUpdatesAvailable")) {
      this.workflow.setStateUpdatesAvailable(
        this.stateUpdatesAvailable,
      );
    }
  }

  protected updated(changed: Map<PropertyKey, unknown>): void {
    const previousDevice = changed.get("device") as
      | DeviceCapabilities
      | undefined;
    const deviceIdentityChanged =
      changed.has("device") &&
      !sameSceneDeviceIdentity(previousDevice, this.device);
    if ((deviceIdentityChanged || changed.has("api")) && this.api && this.device) {
      void this.workflow.loadCatalogue();
    }
    if (changed.has("initialSelection") && this.viewState.catalogue && this.initialSelection) {
      void this.workflow.openInitialSelection();
    }
    if (changed.has("previewStatus")) {
      this.workflow.previewStatusChanged(this.previewStatus);
    }
    const selectedKey = sceneSelectionKey(this.viewState);
    if (!selectedKey) {
      this.lastScrolledSelectionKey = undefined;
      return;
    }
    const previousViewState = changed.get("viewState") as
      | SceneBrowserViewState
      | undefined;
    if (
      (selectedKey !== this.lastScrolledSelectionKey ||
        (changed.has("initialSelection") && this.initialSelection) ||
        changed.has("library") ||
        previousViewState?.category !== this.viewState.category ||
        previousViewState?.catalogue !== this.viewState.catalogue) &&
      scrollSelectedIntoView(
        this.shadowRoot?.querySelector(".scene-list") ?? null,
      )
    ) {
      this.lastScrolledSelectionKey = selectedKey;
    }
  }

  protected render() {
    const state = this.viewState;
    if (!this.device) {
      return html`
        <section class="empty">
          <h2>No loaded device</h2>
          <p>Load a Govee light before browsing its native scenes.</p>
        </section>
      `;
    }
    if (state.loading) {
      return html`<div class="status" role="status">Loading scenes...</div>`;
    }
    if (state.error || !state.catalogue) {
      return html`
        <section class="empty">
          <h2>Scenes are unavailable</h2>
          <p>The scene catalogue could not be loaded.</p>
        </section>
      `;
    }
    return html`
      <aside class="sidebar item-sidebar scenes" aria-label="Scenes">
        <div class="scene-category-panel">
          <div class="field scene-category">
            <select
              aria-label="Scene category"
              @change=${(event: Event) => {
                const select = event.target as HTMLSelectElement;
                this.requestSceneTransition(
                  () => {
                    this.dismissExternalEdit();
                    this.workflow.setCategory(
                      categorySelection(select.value),
                    );
                  },
                  select,
                );
              }}
            >
              ${this.sortedCategories.map(
                (category) => html`
                  <option
                    value=${String(category.id)}
                    .selected=${this.viewState.category === category.id}
                  >
                    ${category.label}
                  </option>
                `,
              )}
            </select>
          </div>
        </div>
        <div class="scene-list">
          ${this.filteredSceneEntries.map((entry) =>
            entry.kind === "custom"
              ? this.sceneButton(`custom:${entry.item.id}`, entry.label, () => this.selectCustom(entry.item, true))
              : this.sceneButton(sceneKey(entry.scene), entry.label, () => this.selectBuiltin(entry.scene, true)),
          )}
        </div>
      </aside>

      ${this.externalEditActive || (!state.selectedScene || !state.content)
        ? nothing
        : html`
            <section class="editor-surface detail">
              ${state.selectedScene && state.content ? this.renderDetail() : nothing}
            </section>
          `}
    `;
  }

  private get sortedCategories(): { id: CategorySelection; label: string }[] {
    return sceneBrowserCategories(this.viewState.catalogue, this.workflow.compatibleCustomScenes);
  }

  private get filteredSceneEntries() {
    return sceneBrowserEntries(
      this.viewState,
      this.workflow.compatibleCustomScenes,
    );
  }

  private sceneButton(
    key: string,
    label: string,
    select: () => void | Promise<void>,
  ) {
    const selected = sceneSelectionKey(this.viewState) === key;
    return html`
      <button
        class="selector scene ${selected ? "selected" : ""}"
        type="button"
        aria-pressed=${selected}
        @click=${(event: Event) => {
          const transition = async () => {
            this.dismissExternalEdit();
            await select();
          };
          const returnFocus = event.currentTarget as HTMLElement;
          this.requestSceneTransition(transition, returnFocus);
        }}
      >
        <span>${label}</span>
      </button>
    `;
  }

  private requestSceneTransition(
    transition: () => void | Promise<void>,
    returnFocus: HTMLElement,
  ): void {
    if (this.requestTransition) {
      void this.requestTransition(
        transition,
        returnFocus,
        this.externalEditActive
          ? undefined
          : () =>
              this.workflow.savePendingWork(
                this.isAdmin,
                this.editorTransitionEpoch,
              ),
      ).finally(() => {
        if (returnFocus instanceof HTMLSelectElement) {
          returnFocus.value = String(this.viewState.category);
        }
      });
    } else {
      void transition();
    }
  }

  private renderDetail() {
    const state = this.viewState;
    const scene = state.selectedScene!;
    const speed = scene.speed;
    const speedIndex = state.speedIndex ?? speed?.default_index ?? 0;
    const custom = state.selectedItem !== undefined || state.editingCopy;
    const layered = state.content?.kind === "scene_layered";
    const nativeSelection = state.selectedItem === undefined && !state.editingCopy;
    const savingCopy = state.selectedItem === undefined && state.editingCopy;
    const saveDisabled = !state.name.trim() || (state.selectedItem !== undefined && !this.workflow.sceneDirty);
    return html`
      <header class="editor-heading">
        <div class="editor-title ${custom ? "mobile-editable-heading" : ""}">
          ${custom
            ? html`
                <span class="mobile-name-label">Name</span>
                <div class="editable-title">
                  <input
                    class="editor-name"
                    aria-label="Scene name"
                    maxlength="128"
                    .value=${state.name}
                    ?disabled=${!this.isAdmin || state.saving}
                    @input=${(event: Event) => {
                      this.workflow.setName((event.target as HTMLInputElement).value);
                    }}
                  />
                  ${this.workflow.sceneDirty
                    ? html`<span class="dirty-marker" aria-label="Unsaved changes">*</span>`
                    : nothing}
                </div>
              `
            : html`<div class="mobile-redundant-heading">
                <h2>${scene.display_name}</h2>
              </div>`}
          ${state.selectedItem
            ? html`<small class="origin-name">
                ${effectOriginDescription(state.selectedItem.origin, scene.display_name)}
              </small>`
            : nothing}
        </div>
        <div class="actions">
          ${!this.liveApplyEnabled
            ? html`
                <button
                  class="secondary apply-action"
                  type="button"
                  ?disabled=${!this.isAdmin ||
                  state.saving ||
                  state.applying ||
                  !this.workflow.hasCurrentSceneContent()}
                  @click=${() =>
                    void this.workflow.applyCurrent(this.isAdmin)}
                >
                  ${state.applying ? "Applying..." : "Apply"}
                </button>
              `
            : nothing}
          ${savingCopy
            ? html`
                <button
                  class="secondary"
                  type="button"
                  ?disabled=${state.saving}
                  @click=${this.cancelCopy}
                >
                  Cancel
                </button>
              `
            : nothing}
          ${nativeSelection
            ? nativeSceneActions(
                this.workflow.sceneCatalogueDirty,
                this.workflow.sceneDefaultDirty,
                this.autoSaveEnabled,
                this.autoSaveFailed || state.defaultSaveFailed,
                this.liveApplyEnabled,
                this.workflow.defaultWritePending,
              )
                .filter(
                  (action) =>
                    action.id !== "edit" || scene.scene_type === 2,
                )
                .map((action) => this.renderNativeAction(action))
            : html`
                ${state.selectedItem
                  ? html`
                      <button
                        class="danger delete-action"
                        type="button"
                        ?disabled=${!this.isAdmin || state.saving}
                        @click=${this.requestDelete}
                      >
                        Delete
                      </button>
                    `
                  : nothing}
                <button
                  class=${layered ? "secondary" : "primary"}
                  type="button"
                  ?disabled=${!this.isAdmin ||
                  state.saving ||
                  !this.workflow.hasCurrentSceneContent() ||
                  (!layered && saveDisabled)}
                  @click=${layered ? this.edit : this.save}
                >
                  ${state.saving
                    ? "Saving..."
                    : layered
                      ? "Edit"
                      : savingCopy
                        ? "Save As"
                        : "Save"}
                </button>
              `}
        </div>
      </header>

      ${sceneHasParameterSurface(scene) ? this.renderParameters(speed!, speedIndex) : nothing}
    `;
  }

  private renderNativeAction(action: NativeSceneAction) {
    const click =
      action.id === "save-default"
        ? () => void this.workflow.setCurrentDefault(this.isAdmin)
        : action.id === "reset-default"
          ? this.resetToCatalogue
          : action.id === "save-as"
            ? this.edit
            : this.edit;
    return html`
      <button
        class=${action.style}
        type="button"
        ?disabled=${!this.isAdmin ||
        this.viewState.saving ||
        !this.workflow.hasCurrentSceneContent() ||
        action.disabled === true}
        @click=${click}
      >
        ${action.label}
      </button>
    `;
  }

  private renderParameters(speed: NonNullable<SceneSummary["speed"]>, speedIndex: number) {
    return html`
      <div class="card scene-parameters">
        <div class="parameter-list">
          <govee-segmented-control
            .label=${"Speed"}
            .value=${speedIndex}
            .options=${sceneSpeedOptions(speed.option_count, speed.default_index)}
            .disabled=${!this.isAdmin || this.viewState.saving}
            @value-changed=${(event: CustomEvent<SegmentedControlChange<number>>) => {
              this.workflow.setSpeedIndex(event.detail.value);
              if (this.autoSaveEnabled) {
                if (this.liveApplyEnabled) {
                  this.dispatchPreview();
                } else {
                  void this.workflow.setCurrentDefault(this.isAdmin);
                }
              } else {
                this.dispatchPreview();
              }
            }}
          ></govee-segmented-control>
        </div>
      </div>
    `;
  }

  private async selectBuiltin(scene: SceneSummary, preview = false): Promise<void> {
    if ((await this.workflow.selectBuiltin(scene)) && preview) {
      this.dispatchPreview();
    }
  }

  private async selectCustom(summary: Parameters<SceneBrowserWorkflow["selectCustom"]>[0], preview = false): Promise<void> {
    if ((await this.workflow.selectCustom(summary)) && preview) {
      this.dispatchPreview();
    }
  }

  private edit(): void {
    const detail = this.workflow.edit(this.isAdmin);
    if (detail) {
      this.emit<SceneEditSelection>("scene-edit-selected", detail);
    }
  }

  private cancelCopy(): void {
    void this.workflow.cancelCopy();
  }

  private save(): void {
    void this.workflow.save(this.isAdmin, this.editorTransitionEpoch);
  }

  private resetToCatalogue(): void {
    void this.workflow.resetToCatalogue(this.isAdmin).then(() => {
      if (this.autoSaveEnabled && !this.liveApplyEnabled) {
        void this.workflow.setCurrentDefault(this.isAdmin);
      } else {
        this.dispatchPreview();
      }
    });
  }

  private dispatchPreview(): void {
    const detail = this.currentPreviewRequest();
    if (detail) {
      this.emit<ScenePreviewRequest>("scene-preview-requested", detail);
    }
  }

  private dismissExternalEdit(): void {
    if (this.externalEditActive) {
      this.emit("scene-external-edit-cancelled");
    }
  }

  private requestDelete(event: Event): void {
    const item = this.viewState.selectedItem;
    if (!item || !this.isAdmin) {
      return;
    }
    const returnFocus = event.currentTarget as HTMLElement;
    this.emit<LibraryItemDeleteRequest>("library-item-delete-requested", {
      id: item.id,
      version: item.version,
      updated_at: item.updated_at,
      name: item.name,
      discardsOpenEdits: this.workflow.sceneDirty,
      returnFocus,
    });
    returnFocus.blur();
  }

  private emit<T>(name: string, detail?: T): void {
    this.dispatchEvent(
      new CustomEvent<T>(name, {
        ...(detail === undefined ? {} : { detail }),
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    studioBaseStyles,
    studioCardStyles,
    studioActionStyles,
    studioSelectorStyles,
    studioEditorStyles,
    studioFormStyles,
    studioVisuallyHiddenStyles,
    studioWorkspaceStyles,
    css`
      :host {
        display: contents;
      }
      :host([hidden]) { display: none !important; }
      h2, p { margin-top: 0; }
      h2 { margin-bottom: 0; font-size: var(--studio-heading-size); }
      .empty {
        max-width: var(--studio-empty-state-max-width);
        padding: var(--studio-editor-padding);
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-card-radius);
        background: var(--studio-card);
        line-height: var(--studio-reading-line-height);
      }
      .scene-parameters { margin-top: var(--studio-section-gap); }
      .scenes {
        display: grid;
        min-height: 0;
        overflow: hidden;
        padding: 0;
        grid-template-rows: auto minmax(0, 1fr);
      }
      .scene-category-panel {
        padding: var(--studio-sidebar-padding);
        border-bottom: var(--studio-border-width) solid var(--studio-border);
        background: var(--primary-background-color);
      }
      .scene-category {
        gap: 0;
        margin: 0;
      }
      .scene-list {
        min-height: 0;
        overflow-y: auto;
        padding: var(--studio-sidebar-padding);
        background: var(--primary-background-color);
      }
      .parameter-list { display: grid; gap: var(--studio-spacing-lg); }
      .empty p {
        margin-bottom: 0;
        color: var(--studio-muted);
        line-height: var(--studio-body-line-height);
      }
      .status {
        grid-column: 2 / -1;
        padding: var(--studio-message-block-padding)
          var(--studio-editor-padding);
      }
      .mobile-name-label {
        display: none;
      }
      /* Places scenes above detail beside HA's docked sidebar. */
      @media (min-width: 901px) and (max-width: 1320px) {
        .item-sidebar {
          grid-row: 1;
          grid-column: 2;
          max-height: var(--studio-stacked-list-max-height);
          border-inline-end: 0;
          border-bottom: var(--studio-border-width) solid var(--studio-border);
        }
        .editor-surface {
          grid-row: 2;
          grid-column: 2;
        }
      }
      /* The panel owns document-flow placement below this width. */
      @media (max-width: 900px) { :host { display: block; } }
      @media (max-width: 600px) {
        .detail {
          display: flex;
          flex-direction: column;
        }
        .editor-heading {
          display: contents;
        }
        .editor-heading .actions {
          order: 100;
          margin-top: var(--studio-section-gap);
        }
        .editor-heading .mobile-editable-heading {
          order: 99;
          margin-top: var(--studio-section-gap);
        }
        .mobile-name-label {
          display: block;
          color: var(--studio-muted);
          font-size: var(--studio-parameter-label-size);
          font-weight: var(--studio-parameter-label-weight);
        }
        .mobile-redundant-heading {
          display: none;
        }
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-scene-browser": GoveeSceneBrowser;
  }
}

if (!customElements.get("govee-scene-browser")) {
  customElements.define("govee-scene-browser", GoveeSceneBrowser);
}
