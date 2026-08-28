import { LitElement, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";

import type {
  CustomEffectBrowserCategoryRequest,
  CustomEffectBrowserEntryRequest,
} from "./custom-effect-browser";
import {
  advancedEditorContent,
  effectOriginDescription,
  isAdvancedEditableContent,
  isCustomEffectContent,
} from "./effect-editor-model";
import type { EditorActionDescriptor } from "./editor-state";
import { customEffectCategories } from "./custom-effect-workflow";
import type { LivePreviewInteraction } from "./live-preview-controller";
import type { MusicModeChange } from "./music-profile-editor";
import { PanelController } from "./panel-controller";
import { PanelEditorController } from "./panel-editor-controller";
import { PanelModalController } from "./panel-modal-controller";
import { PanelModel, type DeleteCandidate } from "./panel-model";
import { PanelPreviewController } from "./panel-preview-controller";
import { effectStudioPanelStyles } from "./panel-styles";
import { rememberRecentColour } from "./recent-colours";
import type {
  GoveeSceneBrowser,
  LibraryItemDeleteRequest,
  ScenePreviewRequest,
} from "./scene-browser";
import type { SceneEditSelection } from "./scene-browser-workflow";
import type { SliderControlChange } from "./slider-control";
import {
  synchroniseDeviceSelect,
  studioNavigationItems,
  type StudioNavigationItem,
} from "./studio-navigation";
import type {
  AdvancedContent,
  CustomEffectContent,
  HomeAssistant,
  LibraryItem,
  LibrarySummary,
  MusicProfileContent,
  OpaqueContent,
  PaintedContent,
  PaletteDiyEffectContent,
  PanelConfig,
  RGB,
  VideoProfileContent,
} from "./types";
import {
  brightnessFillPercentage,
  classifyLightEntityState,
  compareLabels,
  hassPanelRenderChanged,
  integrationSettingsPath,
  lightControlEntityId,
  lightControlPresentation,
  moreInfoDetail,
  scrollSelectedIntoView,
  showHomeAssistantHeader,
  studioToolbarLayoutState,
} from "./ui-utils";

const componentLoaders = {
  shell: () =>
    Promise.all([
      import("./custom-effect-browser"),
      import("./info-control"),
    ]),
  scenes: () => import("./scene-browser"),
  video: () => import("./video-profile-editor"),
  music: () => import("./music-profile-editor"),
  advanced: () => import("./advanced-effect-editor"),
  painted: () =>
    Promise.all([
      import("./painted-segment-editor"),
      import("./single-colour-field"),
      import("./slider-control"),
    ]),
  custom: () => import("./custom-effect-editor"),
} as const;

type ComponentGroup = keyof typeof componentLoaders;

export class GoveeLedEffectStudio extends LitElement {
  @property({ attribute: false })
  public hass?: HomeAssistant;

  @property({ attribute: false })
  public panel?: PanelConfig;

  @property({ type: Boolean })
  public narrow = false;

  @state()
  private modelRevision = 0;

  private readonly model = new PanelModel(() => {
    this.loadComponentsForCurrentView();
    this.syncUnloadProtection();
    this.modelRevision += 1;
  });
  private readonly preview = new PanelPreviewController(this.model);
  private readonly modal = new PanelModalController(this.model, {
    updateComplete: () => this.updateComplete,
    root: () => this.shadowRoot,
    canMutate: () => this.controller?.api !== undefined,
  });
  private readonly editor: PanelEditorController;
  private readonly controller: PanelController;
  private readonly requestedComponentGroups = new Set<ComponentGroup>();
  private visibleVideoSelection?: string;
  private unloadListenerRegistered = false;
  private redispatchingNavigation = false;

  public constructor() {
    super();
    this.editor = new PanelEditorController(
      this.model,
      this.preview,
      this.modal,
      {
        apiReady: () => this.controller?.api !== undefined,
        selectItem: (itemId) => void this.controller.selectItem(itemId),
        editorTransitionStarted: () =>
          this.controller?.cancelPendingAutoSave(),
        contentCommitted: (interaction) =>
          this.controller?.contentCommitted(interaction),
        selectCatalogueTemplate: (templateId, label, owner) =>
          void this.controller?.selectCatalogueTemplate(
            templateId,
            label,
            owner,
          ),
      },
    );
    this.controller = new PanelController(
      this.model,
      this.editor,
      this.preview,
      this.modal,
      {
        connected: () => this.isConnected,
        pathname: () => window.location.pathname,
        replacePath: (path) => {
          window.history.replaceState(window.history.state, "", path);
        },
        saveSceneWork: () =>
          this.shadowRoot
            ?.querySelector<GoveeSceneBrowser>("govee-scene-browser")
            ?.savePendingWork() ?? Promise.resolve(false),
      },
    );
  }

  private get section() { return this.model.section; }
  private get catalogueSourceLabel() { return this.model.catalogueSourceLabel; }
  private get editorSource() { return this.model.editorSource; }
  private get currentItem() { return this.model.currentItem; }
  private get content() { return this.model.content; }
  private get isAdmin() { return this.hass?.user?.is_admin === true; }
  private get editorReadOnly() { return this.model.editorReadOnly; }
  private get editorDisabled() {
    return this.editorReadOnly || this.model.saving;
  }
  private get canMutate() {
    return this.isAdmin && !this.model.stateUpdatesUnavailable;
  }

  public connectedCallback(): void {
    super.connectedCallback();
    this.addEventListener("keydown", this.keyDown);
    window.addEventListener("click", this.navigationClick, true);
    this.syncUnloadProtection();
    this.loadComponentsForCurrentView();
    this.model.syncAdmin(this.hass);
    if (this.hass && !this.controller.api) {
      void this.controller.load(this.hass, this.isAdmin);
    }
  }

  public disconnectedCallback(): void {
    this.removeEventListener("keydown", this.keyDown);
    window.removeEventListener("click", this.navigationClick, true);
    this.setUnloadListener(false);
    this.modal.releaseScrollLock();
    super.disconnectedCallback();
    this.editor.beginTransition();
    this.controller.disconnect();
  }

  protected shouldUpdate(changed: Map<PropertyKey, unknown>): boolean {
    if (changed.size !== 1 || !changed.has("hass")) {
      return true;
    }
    return hassPanelRenderChanged(
      this.hass,
      changed.get("hass") as HomeAssistant | undefined,
      lightControlEntityId(this.model.selectedDevice),
    );
  }

  protected updated(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("hass")) {
      this.model.syncAdmin(this.hass);
    }
    if (changed.has("hass") && this.hass && !this.controller.api) {
      void this.controller.load(this.hass, this.isAdmin);
    }
    if (changed.has("modelRevision")) {
      this.modal.syncScrollLock();
      this.syncSingleEffectSelects();
      this.syncVideoSelectionVisibility();
    }
  }

  private loadComponentsForCurrentView(): void {
    this.requestComponentGroup("shell");
    if (this.model.section === "scenes") {
      this.requestComponentGroup("scenes");
    }
    if (this.model.section === "video") {
      this.requestComponentGroup("video");
    }
    if (!this.model.editorOwnedByActiveView) {
      return;
    }
    switch (this.model.content.kind) {
      case "advanced":
      case "scene_layered":
      case "workshop":
        this.requestComponentGroup("advanced");
        break;
      case "h617a_painted":
        this.requestComponentGroup("painted");
        break;
      case "h617a_single":
      case "h617a_multi":
      case "palette_diy":
        this.requestComponentGroup("custom");
        break;
      case "music_profile":
        this.requestComponentGroup("music");
        break;
      case "video_profile":
        this.requestComponentGroup("video");
        break;
    }
  }

  private requestComponentGroup(group: ComponentGroup): void {
    if (this.requestedComponentGroups.has(group)) {
      return;
    }
    this.requestedComponentGroups.add(group);
    void componentLoaders[group]().catch((error: unknown) => {
      console.error(`Effect Studio could not load the ${group} controls.`, error);
      this.modal.showError(
        "Effect Studio could not load all controls. Reload the page to try again.",
        {
          title: "Controls unavailable",
          key: `component-load:${group}`,
        },
      );
    });
  }

  protected render() {
    if (this.model.loading) {
      return html`
        ${this.renderHomeAssistantHeader()}
        <div class="centred" role="status">Loading effect studio...</div>
      `;
    }
    if (this.model.error) {
      return html`
        ${this.renderHomeAssistantHeader()}
        ${this.renderFatalError()}
      `;
    }

    return html`
      <div class="panel-content" ?inert=${this.modal.open}>
        ${this.renderHomeAssistantHeader()}
        <h1 class="visually-hidden">Effect Studio</h1>

        ${this.renderStudioToolbar()}

        ${this.model.selectedDevice
          ? this.model.selectedDevice.effect_categories.length
            ? this.renderStudio()
            : this.renderNoEffectCategories()
          : this.renderMissingDevice()}
      </div>
      ${this.model.saveNameDialogOpen ? this.renderSaveNameDialog() : nothing}
      ${this.model.deleteCandidate ? this.renderDeleteConfirmation() : nothing}
      ${this.model.pendingTransitionDialog
        ? this.renderPendingTransitionDialog()
        : nothing}
      ${this.model.modalState?.kind === "overwrite"
        ? this.renderOverwriteDialog()
        : nothing}
      ${this.model.modalState?.kind === "error"
        ? this.renderErrorDialog()
        : nothing}
    `;
  }

  private renderHomeAssistantHeader() {
    if (
      !showHomeAssistantHeader(
        this.narrow,
        this.hass?.dockedSidebar,
        this.hass?.kioskMode,
      )
    ) {
      return nothing;
    }
    return html`
      <header class="home-assistant-header">
        <button
          class="home-assistant-menu"
          type="button"
          aria-label="Open Home Assistant navigation"
          @click=${this.toggleHomeAssistantMenu}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"></path>
          </svg>
        </button>
        <span>Govee Effect Studio</span>
      </header>
    `;
  }

  private toggleHomeAssistantMenu(): void {
    this.dispatchEvent(
      new CustomEvent("hass-toggle-menu", {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private renderStudio() {
    return html`
      <main
        class="studio ${this.section}-mode"
      >
        <nav class="primary-nav" aria-label="Create">
          ${studioNavigationItems(
            this.model.scenesAvailable,
            this.model.videoAvailable,
            this.model.customEffectsAvailable
              ? customEffectCategories(this.model.customEffectListContext).filter(
                  ({ category }) =>
                    this.model.customEffectCategoryAvailable(category),
                )
              : [],
          ).map((item) => this.navButton(item))}
        </nav>

        <govee-scene-browser
          ?hidden=${this.section !== "scenes"}
          .externalEditActive=${this.model.sceneEditorOpen}
          .editorTransitionEpoch=${this.model.editorTransitionEpoch}
          .api=${this.controller.api}
          .device=${this.model.selectedDevice}
          .library=${this.model.library}
          .previewStatus=${this.model.previewStatus}
          .stateUpdatesAvailable=${!this.model.stateUpdatesUnavailable}
          .isAdmin=${this.canMutate}
          .autoSaveEnabled=${this.model.autoSaveEnabled}
          .autoSaveFailed=${this.model.autoSaveFailed}
          .liveApplyEnabled=${this.model.liveApplyEnabled}
          .savedSceneSelection=${this.model.savedSceneSelection}
          .initialSelection=${this.model.sceneInitialSelection}
          .requestTransition=${(
            transition: () => void | Promise<void>,
            returnFocus: HTMLElement,
            save?: () => Promise<boolean>,
          ) =>
            this.controller.selectScene(
              transition,
              returnFocus,
              save,
            )}
          @library-item-saved=${this.sceneLibraryItemSaved}
          @library-item-delete-requested=${this.sceneLibraryItemDeleteRequested}
          @scene-edit-selected=${this.sceneTemplateSelected}
          @scene-preview-requested=${(
            event: CustomEvent<ScenePreviewRequest>,
          ) => this.preview.scheduleScene(event.detail)}
          @scene-external-edit-cancelled=${this.cancelSceneEdit}
          @scene-initial-selection-opened=${this.sceneInitialSelectionOpened}
          @scene-initial-selection-failed=${this.sceneInitialSelectionFailed}
          @studio-error=${(
            event: CustomEvent<{
              message: string;
              title?: string;
              key?: string;
            }>,
          ) =>
            this.modal.showError(event.detail.message, event.detail)}
          @scene-work-state-changed=${(
            event: CustomEvent<{ dirty: boolean }>,
          ) =>
            this.model.patch({
              sceneWorkDirty: this.model.sceneEditorOpen
                ? false
                : event.detail.dirty,
            })}
        ></govee-scene-browser>
        ${this.section === "scenes" && this.model.sceneEditorOpen
          ? html`
              <section class="editor-surface editor">
                ${this.renderAdvancedEditor()}
              </section>
            `
          : nothing}
        ${this.section === "video" ? this.renderVideo() : nothing}
        ${this.section === "custom" ? this.renderCustomEffects() : nothing}
      </main>
    `;
  }

  private renderMissingDevice() {
    const linked = this.model.selectedDeviceId !== undefined;
    return html`
      <main class="empty-state">
        <h2>${linked ? "This Govee light is unavailable" : "No Govee lights are available"}</h2>
        <p>
          ${linked
            ? "Choose another light or wait for this config entry to load."
            : "Add or enable a supported Govee Bluetooth light to use Effect Studio."}
        </p>
        <a href=${this.panel?.config?.configuration_path ?? "/config/integrations"}>
          Open integration configuration
        </a>
      </main>
    `;
  }

  private renderNoEffectCategories() {
    return html`
      <main class="empty-state">
        <h2>No Effect Studio categories are enabled</h2>
        <p>Enable one or more categories in this light's integration settings.</p>
        ${this.model.selectedDevice
          ? this.renderIntegrationSettings(
              this.model.selectedDevice.display_name,
              this.model.selectedDevice.config_entry_id,
            )
          : nothing}
      </main>
    `;
  }

  private renderStudioToolbar() {
    const device = this.model.selectedDevice;
    const lightEntityId = lightControlEntityId(device);
    const layout = studioToolbarLayoutState(
      this.model.showDeviceSelector,
      this.isAdmin,
      device !== undefined,
      lightEntityId,
    );
    if (!layout.visible) {
      return nothing;
    }
    return html`
      <div class="studio-toolbar">
        <div class="studio-toolbar-device">
          ${layout.deviceSelector ? this.renderDeviceSelector() : nothing}
        </div>
        <div class="studio-toolbar-controls">
          ${layout.modeControls ? this.renderLiveApplyControl() : nothing}
          ${layout.modeControls ? this.renderAutoSaveControl() : nothing}
          ${layout.lightControl && device && lightEntityId
            ? this.renderLightControl(device.display_name, lightEntityId)
            : nothing}
          ${layout.settings && device
            ? this.renderIntegrationSettings(
                device.display_name,
                device.config_entry_id,
              )
            : nothing}
        </div>
      </div>
    `;
  }

  private renderLightControl(displayName: string, entityId: string) {
    const entity = this.hass?.states?.[entityId];
    const state = classifyLightEntityState(this.hass?.states, entityId);
    const presentation = lightControlPresentation(
      displayName,
      state,
      entity?.attributes?.brightness,
    );
    const fillPercentage = brightnessFillPercentage(
      presentation.brightnessLevel ?? 0,
    );
    return html`
      <button
        class="toolbar-control light-control-button native-light-control ${presentation.className}"
        type="button"
        aria-label=${presentation.accessibleName}
        title=${presentation.accessibleName}
        style=${`--native-light-fill: ${fillPercentage}%`}
        @click=${() => this.showLightControls(entityId)}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path
            class="native-light-brightness-ring"
            fill-rule="evenodd"
            d="M20 15.31 23.31 12 20 8.69V4h-4.69L12 .69 8.69 4H4v4.69L.69 12 4 15.31V20h4.69L12 23.31 15.31 20H20v-4.69ZM12 6a6 6 0 1 0 0 12 6 6 0 1 0 0-12Z"
          ></path>
        </svg>
      </button>
    `;
  }

  private showLightControls(entityId: string): void {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: moreInfoDetail(entityId),
      }),
    );
  }

  private renderIntegrationSettings(
    displayName: string,
    configEntryId: string,
  ) {
    const configurationPath =
      this.panel?.config?.configuration_path ??
      "/config/integrations/integration/ha_govee_led_ble";
    return html`
      <a
        class="toolbar-control light-control-button"
        href=${integrationSettingsPath(configurationPath, configEntryId)}
        aria-label=${`Configure visible effects for ${displayName}`}
        title=${`Configure visible effects for ${displayName}`}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path
            d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.07-.94l2.03-1.58-1.92-3.32-2.39.96a7.2 7.2 0 0 0-1.62-.94L14.87 3h-3.84l-.36 3.18c-.59.24-1.13.56-1.62.94l-2.39-.96-1.92 3.32 2.03 1.58c-.05.31-.08.64-.08.94s.03.63.08.94l-2.03 1.58 1.92 3.32 2.39-.96c.49.38 1.03.7 1.62.94l.36 3.18h3.84l.36-3.18c.59-.24 1.13-.56 1.62-.94l2.39.96 1.92-3.32-2.02-1.58M13 15.5A3.5 3.5 0 1 1 13 8a3.5 3.5 0 0 1 0 7.5"
          ></path>
        </svg>
      </a>
    `;
  }

  private renderDeviceSelector() {
    if (!this.model.showDeviceSelector) {
      return nothing;
    }
    const selectedUnavailable =
      this.model.selectedDeviceId !== undefined && this.model.selectedDevice === undefined;
    return html`
      <label class="device-selector">
        <select
          aria-label="Light"
          .value=${this.model.selectedDeviceId ?? ""}
          @change=${(event: Event) => {
            const select = event.currentTarget as HTMLSelectElement;
            void this.controller
              .deviceChanged(select.value, select)
              .finally(() =>
                synchroniseDeviceSelect(
                  select,
                  this.model.selectedDeviceId,
                ),
              );
          }}
        >
          ${selectedUnavailable
            ? html`
                <option
                  value=${this.model.selectedDeviceId!}
                  .selected=${true}
                >
                  Unavailable light
                </option>
              `
            : nothing}
          ${[...this.model.devices]
            .sort((left, right) =>
              compareLabels(left.display_name, right.display_name),
            )
            .map(
              (device) => html`
                <option
                  value=${device.config_entry_id}
                  .selected=${device.config_entry_id ===
                  this.model.selectedDeviceId}
                >
                  ${device.display_name} (${device.model})
                </option>
              `,
            )}
        </select>
      </label>
    `;
  }

  private renderLiveApplyControl() {
    const phase = this.model.previewStatus?.phase;
    const pending =
      this.model.previewProgressVisible &&
      (phase === "queued" || phase === "writing");
    const status = pending ? "Applying changes" : undefined;
    return html`
      <div class="live-apply-control">
        <span
          class="live-apply-status ${pending
            ? "pending"
            : "idle"}"
          title=${status ?? nothing}
          aria-hidden="true"
        ></span>
        <button
          class="toolbar-control toolbar-mode-button"
          type="button"
          aria-pressed=${this.model.liveApplyEnabled}
          ?disabled=${this.model.stateUpdatesUnavailable}
          title="Apply committed changes automatically"
          @click=${() =>
            void this.controller.toggleLive(this.currentScenePreviewRequest())}
        >
          Live
        </button>
        ${status
          ? html`<span class="visually-hidden" role="status"
              >${status}</span
            >`
          : nothing}
      </div>
    `;
  }

  private renderAutoSaveControl() {
    return html`
      <button
        class="toolbar-control toolbar-mode-button ${this.model.autoSaveInProgress
          ? "pending"
          : ""}"
        type="button"
        aria-pressed=${this.model.autoSaveEnabled}
        aria-busy=${this.model.autoSaveInProgress}
        ?disabled=${this.model.stateUpdatesUnavailable}
        aria-label="Auto Save"
        title=${this.model.autoSaveInProgress
          ? "Saving committed changes automatically"
          : "Save committed changes automatically"}
        @click=${() =>
          this.controller.toggleAutoSave(this.currentScenePreviewRequest())}
      >
        <ha-icon
          class="toolbar-mode-icon"
          icon="mdi:content-save"
          aria-hidden="true"
        ></ha-icon>
      </button>
      ${this.model.autoSaveInProgress
        ? html`<span class="visually-hidden" role="status"
            >Saving changes automatically</span
          >`
        : nothing}
    `;
  }

  private renderFatalError() {
    return html`
      <main class="fatal">
        <h1>Effect Studio is unavailable</h1>
        <p role="alert">${this.model.error}</p>
        <p>Existing light controls are unaffected.</p>
        <a href=${this.panel?.config?.configuration_path ?? "/config/integrations"}>
          Open integration configuration
        </a>
      </main>
    `;
  }

  private navButton(item: StudioNavigationItem) {
    const selected =
      this.section === item.section &&
      (item.section !== "custom" ||
        item.category === this.model.customEffectCategory);
    return html`
      <button
        class="selector ${selected ? "selected" : ""}"
        type="button"
        aria-current=${selected ? "page" : nothing}
        @click=${(event: Event) =>
          void this.controller.selectSection(
            item.section,
            item.category,
            event.currentTarget as HTMLElement,
          )}
      >
        ${item.label}
      </button>
    `;
  }

  private renderCustomEffects() {
    const hasEditor =
      this.model.editorOwnedByActiveView &&
      (this.model.name !== "" || this.currentItem !== undefined);
    return html`
      <govee-custom-effect-browser
        .context=${this.model.customEffectListContext}
        .category=${this.model.customEffectCategory}
        .currentItemId=${this.currentItem?.id}
        .templateSelection=${this.model.templateSelection}
        .newSelected=${this.model.newCustomEffectSelected}
        .isAdmin=${this.canMutate}
        @custom-entry-requested=${(
          event: CustomEvent<CustomEffectBrowserEntryRequest>,
        ) =>
          void this.controller.selectCustomEffectEntry(
            event.detail.entry,
            event.detail.returnFocus,
          )}
        @custom-new-requested=${(
          event: CustomEvent<CustomEffectBrowserCategoryRequest>,
        ) =>
          void this.controller.newCustomEffect(
            event.detail.category,
            event.detail.returnFocus,
          )}
      ></govee-custom-effect-browser>

      ${hasEditor
        ? html`
            <section class="editor-surface editor">
              ${this.renderCurrentCustomEditor()}
            </section>
          `
        : nothing}
    `;
  }

  private renderCurrentCustomEditor() {
    if (isCustomEffectContent(this.content)) {
      return this.content.kind === "h617a_painted"
        ? this.renderPaintedEditor()
        : this.renderPaletteEffectEditor();
    }
    if (this.content.kind === "palette_diy") {
      return this.renderPaletteEffectEditor();
    }
    if (this.content.kind === "music_profile") {
      return this.renderMusicProfileEditor();
    }
    if (isAdvancedEditableContent(this.content)) {
      return this.renderAdvancedEditor();
    }
    return this.content.kind === "opaque"
      ? this.renderOpaqueEditor(this.content)
      : nothing;
  }

  private renderVideo() {
    const catalogue = this.model.modelCatalogue;
    if (!catalogue || !this.model.videoAvailable) {
      return nothing;
    }
    const saved = this.model.library.items
      .filter(
        (item) =>
          item.kind === "video_profile" && this.libraryItemAvailable(item),
      )
      .sort((left, right) => compareLabels(left.name, right.name));
    return html`
      <aside class="sidebar item-sidebar library" aria-label="Video profiles">
        ${catalogue.video_modes.map((mode) =>
          this.videoListButton(
            `template:video:${mode.id}`,
            mode.label,
            (returnFocus) =>
              void this.controller.selectVideoTemplate(
                mode.id,
                mode.label,
                returnFocus,
              ),
          ),
        )}
        ${saved.map((item) =>
          this.videoListButton(
            `saved:${item.id}`,
            item.name,
            (returnFocus) =>
              void this.controller.selectItemFromList(item.id, returnFocus),
            item,
          ),
        )}
      </aside>
      ${this.model.editorOwnedByActiveView &&
      this.content.kind === "video_profile"
        ? html`
            <section class="editor-surface editor">
              ${this.renderVideoProfileEditor()}
            </section>
          `
        : nothing}
    `;
  }

  private syncVideoSelectionVisibility(): void {
    if (this.section !== "video") {
      this.visibleVideoSelection = undefined;
      return;
    }
    const selection = this.currentItem
      ? `saved:${this.currentItem.id}`
      : this.model.templateSelection;
    if (!selection || selection === this.visibleVideoSelection) {
      return;
    }
    if (
      scrollSelectedIntoView(
        this.shadowRoot?.querySelector(
          '.item-sidebar[aria-label="Video profiles"]',
        ) ?? null,
      )
    ) {
      this.visibleVideoSelection = selection;
    }
  }

  private videoListButton(
    key: string,
    label: string,
    select: (returnFocus: HTMLElement) => void,
    item?: LibrarySummary,
  ) {
    const selected = item
      ? this.currentItem?.id === item.id
      : !this.currentItem && this.model.templateSelection === key;
    return html`
      <button
        class="selector item ${selected ? "selected" : ""}"
        type="button"
        ?disabled=${!item && !this.canMutate}
        @click=${(event: Event) =>
          select(event.currentTarget as HTMLElement)}
      >
        <span>${label}</span>
      </button>
    `;
  }

  private renderVideoProfileEditor() {
    if (this.content.kind !== "video_profile") {
      return nothing;
    }
    return html`
      ${this.renderProfileHeading()}
      <govee-video-profile-editor
        .content=${this.content}
        .disabled=${this.editorDisabled}
        @content-changed=${(
          event: CustomEvent<{
            content: VideoProfileContent;
            interaction?: LivePreviewInteraction;
          }>,
        ) => {
          this.editor.videoContentChanged(
            event.detail.content,
            event.detail.interaction,
          );
        }}
      ></govee-video-profile-editor>
    `;
  }

  private renderMusicProfileEditor() {
    if (this.content.kind !== "music_profile") {
      return nothing;
    }
    return html`
      ${this.renderProfileHeading()}
      <govee-music-profile-editor
        .content=${this.content}
        .catalogue=${this.model.modelCatalogue}
        .disabled=${this.editorDisabled}
        .modeSelectionEnabled=${this.model.showReactiveEffectSelector}
        @mode-changed=${(event: CustomEvent<MusicModeChange>) =>
          this.editor.musicModeChanged(event.detail.mode)}
        @content-changed=${(
          event: CustomEvent<{
            content: MusicProfileContent;
            interaction?: LivePreviewInteraction;
          }>,
        ) => {
          this.editor.musicContentChanged(
            event.detail.content,
            event.detail.interaction,
          );
        }}
      ></govee-music-profile-editor>
    `;
  }

  private renderProfileHeading() {
    return this.renderEditorHeading();
  }

  private libraryItemAvailable(item: LibrarySummary): boolean {
    return this.model.libraryItemAvailable(item);
  }

  private customEffectKindAvailable(kind: string): boolean {
    return this.model.customEffectKindAvailable(kind);
  }

  private renderDeleteConfirmation() {
    const candidate = this.model.deleteCandidate!;
    const discardsOpenEdits =
      candidate.discardsOpenEdits === true ||
      (this.currentItem?.id === candidate.id && this.model.dirty);
    return html`
      <div class="dialog-backdrop" @click=${this.cancelDelete}>
        <section
          class="dialog-card delete-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-effect-title"
          tabindex="-1"
          @click=${(event: Event) => event.stopPropagation()}
          @keydown=${this.deleteDialogKeyDown}
        >
          <h2 id="delete-effect-title">Delete effect?</h2>
          <p>
            <strong>${candidate.name}</strong> will be permanently removed
            from the shared Effect Studio library. This cannot be undone.
          </p>
          ${discardsOpenEdits
            ? html`<p>Unsaved changes in the open effect will be discarded.</p>`
            : nothing}
          <div class="dialog-actions">
            <button
              class="secondary"
              type="button"
              @click=${this.cancelDelete}
            >
              Cancel
            </button>
            <button
              class="danger delete-action"
              type="button"
              @click=${() => void this.controller.confirmDelete()}
            >
              Delete effect
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderSaveNameDialog() {
    return html`
      <div class="dialog-backdrop" @click=${this.cancelSaveName}>
        <form
          class="dialog-card save-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="save-effect-title"
          tabindex="-1"
          @click=${(event: Event) => event.stopPropagation()}
          @keydown=${this.saveNameDialogKeyDown}
          @submit=${(event: SubmitEvent) => {
            event.preventDefault();
            void this.modal.confirmNamedSave(
              (name) => this.controller.saveAs(name),
            );
          }}
        >
          <h2 id="save-effect-title">Save Effect As</h2>
          <label class="field">
            <span>Name</span>
            <input
              aria-label="Name"
              maxlength="128"
              autocomplete="off"
              .value=${this.model.saveNameValue}
              ?disabled=${this.model.modalState?.kind === "save-name" &&
              this.model.modalState.busy}
              @input=${(event: Event) => {
                this.modal.saveNameChanged(
                  (event.target as HTMLInputElement).value,
                );
              }}
            />
          </label>
          <div class="dialog-actions">
            <button
              class="secondary"
              type="button"
              ?disabled=${this.model.modalState?.kind === "save-name" &&
              this.model.modalState.busy}
              @click=${this.cancelSaveName}
            >
              Cancel
            </button>
            <button
              class="primary"
              type="submit"
              ?disabled=${this.model.modalState?.kind === "save-name" &&
              this.model.modalState.busy}
            >
              ${this.model.modalState?.kind === "save-name" &&
              this.model.modalState.busy
                ? "Saving..."
                : "Save As"}
            </button>
          </div>
        </form>
      </div>
    `;
  }

  private renderPendingTransitionDialog() {
    const dialog = this.model.pendingTransitionDialog!;
    return html`
      <div
        class="dialog-backdrop"
        @click=${() => this.controller.cancelPendingTransition()}
      >
        <section
          class="dialog-card transition-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pending-transition-title"
          tabindex="-1"
          @click=${(event: Event) => event.stopPropagation()}
          @keydown=${(event: KeyboardEvent) =>
            this.modal.dialogKeyDown(event, () =>
              this.controller.cancelPendingTransition(),
            )}
        >
          <h2 id="pending-transition-title">Save changes?</h2>
          <p>
            This effect has unsaved changes.  Save them before leaving,
            discard the local draft, or cancel to keep editing.
          </p>
          ${dialog.requiresName
            ? html`
                <label class="field">
                  <span>Name</span>
                  <input
                    aria-label="Name"
                    maxlength="128"
                    autocomplete="off"
                    .value=${dialog.saveName}
                    ?disabled=${dialog.busy}
                    @input=${(event: Event) =>
                      this.modal.updateTransitionName(
                        (event.target as HTMLInputElement).value,
                      )}
                  />
                </label>
              `
            : nothing}
          <div class="dialog-actions">
            <button
              class="secondary"
              type="button"
              ?disabled=${dialog.busy}
              @click=${() => this.controller.cancelPendingTransition()}
            >
              Cancel
            </button>
            <button
              class="secondary"
              type="button"
              ?disabled=${dialog.busy}
              @click=${() =>
                void this.controller.declinePendingTransition()}
            >
              Discard
            </button>
            <button
              class="primary"
              type="button"
              ?disabled=${dialog.busy}
              @click=${() => void this.controller.savePendingTransition()}
            >
              ${dialog.primaryLabel}
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderOverwriteDialog() {
    const dialog = this.model.modalState;
    if (dialog?.kind !== "overwrite") {
      return nothing;
    }
    return html`
      <div class="dialog-backdrop" @click=${() => this.modal.cancelOverwrite()}>
        <section
          class="dialog-card overwrite-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="overwrite-effect-title"
          aria-describedby="overwrite-effect-description"
          tabindex="-1"
          @click=${(event: Event) => event.stopPropagation()}
          @keydown=${(event: KeyboardEvent) =>
            this.modal.dialogKeyDown(event, () =>
              this.modal.cancelOverwrite(),
            )}
        >
          <h2 id="overwrite-effect-title">Effect already exists</h2>
          <p id="overwrite-effect-description">
            An effect named <strong>${dialog.effectName}</strong> already
            exists. Overwrite it with this effect?
          </p>
          <div class="dialog-actions">
            <button
              class="secondary"
              type="button"
              @click=${() => this.modal.cancelOverwrite()}
            >
              Cancel
            </button>
            <button
              class="danger delete-action"
              type="button"
              @click=${() => this.modal.confirmOverwrite()}
            >
              Overwrite
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderErrorDialog() {
    const dialog = this.model.modalState;
    if (dialog?.kind !== "error") {
      return nothing;
    }
    return html`
      <div class="dialog-backdrop" @click=${() => this.modal.closeError()}>
        <section
          class="dialog-card error-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="effect-error-title"
          aria-describedby="effect-error-description"
          tabindex="-1"
          @click=${(event: Event) => event.stopPropagation()}
          @keydown=${(event: KeyboardEvent) =>
            this.modal.dialogKeyDown(event, () =>
              this.modal.closeError(),
            )}
        >
          <h2 id="effect-error-title">${dialog.title}</h2>
          <p id="effect-error-description">${dialog.message}</p>
          <div class="dialog-actions">
            <button
              class="secondary"
              type="button"
              @click=${() => this.modal.closeError()}
            >
              Close
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderAdvancedEditor() {
    if (!isAdvancedEditableContent(this.content)) {
      return nothing;
    }
    return html`
      ${this.renderEditorHeading()}

      <govee-advanced-effect-editor
        .content=${advancedEditorContent(this.content)}
        .disabled=${this.editorDisabled}
        .segmentCount=${this.model.selectedDevice?.segment_count ?? 15}
        @content-changed=${(
          event: CustomEvent<{
            content: AdvancedContent;
            interaction?: LivePreviewInteraction;
          }>,
        ) => {
          this.editor.advancedContentChanged(
            event.detail.content,
            event.detail.interaction,
            this.currentScenePreviewRequest(),
          );
        }}
      ></govee-advanced-effect-editor>
    `;
  }

  private renderOpaqueEditor(content: OpaqueContent) {
    return html`
      ${this.renderEditorHeading({
        save: false,
        title: html`<div class="mobile-redundant-heading">
          <h2>${this.model.name}</h2>
        </div>`,
      })}
      <p class="read-only-copy">
        This effect definition can be inspected, but this editor cannot change,
        save or preview it.
      </p>
      <section class="card opaque-content">
        <h3 class="section-title">Source kind</h3>
        <p><code>${content.source_kind}</code></p>
        <h3 class="section-title">Preserved content</h3>
        <pre aria-label="Preserved opaque content">${JSON.stringify(
          content.body,
          null,
          2,
        )}</pre>
      </section>
    `;
  }

  private renderPaintedEditor() {
    if (this.content.kind !== "h617a_painted") {
      return nothing;
    }
    return html`
      ${this.renderEditorHeading()}

      ${this.renderSingleEffectSelector()}

      <govee-painted-segment-editor
        .segments=${this.content.segments}
        .disabled=${this.editorDisabled}
        @segment-selected=${(
          event: CustomEvent<{
            index: number;
            interaction: LivePreviewInteraction;
          }>,
        ) => {
          const changed = this.editor.setSegmentColour(
            event.detail.index,
            event.detail.interaction,
          );
          if (changed && !this.model.paintBrushOff) {
            rememberRecentColour(this.model.paintColour);
          }
        }}
      ></govee-painted-segment-editor>

      <div class="controls">
        <section class="card">
          <govee-single-colour-field
            label="Paint colour"
            .colour=${this.model.paintColour}
            .disabled=${this.editorDisabled}
            .selectionActive=${!this.model.paintBrushOff}
            .rememberOnCommit=${false}
            @colour-changing=${(event: CustomEvent<{ colour: RGB }>) =>
              this.editor.paintColourChanged(event.detail.colour)}
            @colour-changed=${(event: CustomEvent<{ colour: RGB }>) =>
              this.editor.paintColourChanged(event.detail.colour)}
          ></govee-single-colour-field>
          <div class="paint-actions">
            <button
              class="paint-off ${this.model.paintBrushOff ? "active" : ""}"
              type="button"
              ?disabled=${this.editorDisabled}
              aria-pressed=${this.model.paintBrushOff}
              @click=${() => this.editor.selectPaintOff()}
            >
              <span class="paint-off-swatch" aria-hidden="true"></span>
              Off
            </button>
          </div>
        </section>

        <section class="card">
          <div class="parameter-stack">
            ${this.renderPaintedVariationField()}
            ${this.sliderField("Speed", "speed", this.content.speed)}
            ${this.sliderField(
              "Brightness",
              "brightness",
              this.content.brightness,
            )}
          </div>
        </section>
      </div>
    `;
  }

  private renderPaletteEffectEditor() {
    if (
      this.content.kind !== "h617a_single" &&
      this.content.kind !== "h617a_multi" &&
      this.content.kind !== "palette_diy"
    ) {
      return nothing;
    }
    const content = this.content;
    return html`
      ${this.renderEditorHeading()}



      ${this.renderSingleEffectSelector()}

      <govee-custom-effect-editor
        .content=${content}
        .catalogue=${this.model.modelCatalogue}
        .disabled=${this.editorDisabled}
        @content-changed=${(
          event: CustomEvent<{
            content:
              | CustomEffectContent
              | PaletteDiyEffectContent;
            interaction?: LivePreviewInteraction;
          }>,
        ) => {
          this.editor.customContentChanged(
            event.detail.content,
            event.detail.interaction,
          );
        }}
      ></govee-custom-effect-editor>
    `;
  }

  private renderSingleEffectSelector() {
    if (
      !this.model.customCatalogue ||
      !this.model.showSingleEffectSelector ||
      (this.content.kind !== "h617a_painted" &&
        this.content.kind !== "h617a_single" &&
        this.content.kind !== "palette_diy")
    ) {
      return nothing;
    }
    const family = this.selectedSingleEffectFamily;
    const effectFamilies =
      this.currentItem?.content.kind === "h617a_painted"
        ? []
        : this.model.modelCatalogue?.effects.filter(
            (effect) => effect.category === "single_layer",
          ) ?? [];
    const familyAvailable = effectFamilies.some(
      (effect) => effect.family === family?.family,
    );
    const selectedEffect =
      this.content.kind === "h617a_painted"
        ? "paint"
        : family && familyAvailable
          ? family.id
          : `unknown:${this.content.family}`;
    const includePaint =
      this.customEffectKindAvailable("h617a_painted") &&
      this.currentItem?.content.kind !== "h617a_single";
    return html`
      <section class="card single-effect-settings">
        <label class="field">
          <span>Effect</span>
          <select
            aria-label="Effect"
            .value=${selectedEffect}
            ?disabled=${this.editorDisabled}
            @change=${(event: Event) =>
              this.editor.selectSingleEffect(
                (event.target as HTMLSelectElement).value,
              )}
          >
            ${(this.content.kind === "h617a_single" ||
              this.content.kind === "palette_diy") && !familyAvailable
              ? html`
                  <option value=${selectedEffect}>
                    Unknown effect ${this.content.family}
                  </option>
                `
              : nothing}
            ${includePaint
              ? html`
                  <option
                    value="paint"
                    ?selected=${selectedEffect === "paint"}
                  >
                    Paint
                  </option>
                `
              : nothing}
            ${effectFamilies.map(
              (effect) => html`
                <option
                  value=${effect.id}
                  ?selected=${selectedEffect === effect.id}
                >
                  ${effect.label}
                </option>
              `,
            )}
          </select>
        </label>
      </section>
    `;
  }

  private renderPaintedVariationField() {
    if (!this.model.customCatalogue || this.content.kind !== "h617a_painted") {
      return nothing;
    }
    const content = this.content;
    const variations = this.model.customCatalogue.painted_effects;
    const knownVariation = variations.some(
      (variation) => variation.id === content.effect,
    );
    if (knownVariation && variations.length <= 1) {
      return nothing;
    }
    return html`
      <label class="field">
        <span class="parameter-label">Variation</span>
        <select
          aria-label="Variation"
          .value=${content.effect}
          ?disabled=${this.editorDisabled}
          @change=${(event: Event) =>
            this.editor.updatePaintedContent(
              {
                effect: (event.target as HTMLSelectElement)
                  .value as PaintedContent["effect"],
              },
              "committed",
            )}
        >
          ${knownVariation
            ? nothing
            : html`
                <option value=${content.effect}>
                  Unknown variation ${content.effect}
                </option>
              `}
          ${variations.map(
            (variation) => html`
              <option
                value=${variation.id}
                ?selected=${variation.id === content.effect}
              >
                ${variation.label}
              </option>
            `,
          )}
        </select>
      </label>
    `;
  }

  private renderEffectName() {
    const origin = this.currentItem
      ? effectOriginDescription(this.currentItem.origin)
      : undefined;
    const marker =
      this.model.dirty && this.editorSource.kind !== "catalogue"
        ? html`<span class="dirty-marker" aria-label="Unsaved changes">*</span>`
        : nothing;
    if (
      this.editorSource.kind === "catalogue" ||
      (this.editorSource.kind === "scene" &&
        this.editorSource.itemId === undefined)
    ) {
      return html`
        <div class="editor-title mobile-redundant-heading">
          <h2>
            ${this.editorSource.kind === "catalogue"
              ? this.editorSource.label
              : this.model.name}
          </h2>
          ${origin ? html`<small class="origin-name">${origin}</small>` : nothing}
        </div>
      `;
    }
    return html`
      <div class="editor-title mobile-editable-heading">
        <span class="mobile-name-label">Name</span>
        <div class="editable-title">
          <input
            class="editor-name"
            aria-label="Effect name"
            maxlength="128"
            .value=${this.model.name}
            ?disabled=${this.editorDisabled}
            @input=${(event: Event) =>
              this.model.patch({
                name: (event.target as HTMLInputElement).value,
              })}
            @change=${() =>
              this.controller.contentCommitted("committed")}
          />
          ${marker}
        </div>
        ${origin ? html`<small class="origin-name">${origin}</small>` : nothing}
      </div>
    `;
  }

  private renderEditorHeading(
    options: { save?: boolean; title?: unknown } = {},
  ) {
    return html`
      <div class="editor-heading">
        <div class="editor-heading-title">
          ${options.title ?? this.renderEffectName()}
        </div>
        <div class="actions">
          ${this.model.editorActions
            .filter(
              (action) =>
                action.visible &&
                (options.save !== false ||
                  (action.id !== "save" && action.id !== "saveAs")),
            )
            .map((action) => this.renderEditorAction(action))}
        </div>
      </div>
    `;
  }

  private renderEditorAction(action: EditorActionDescriptor) {
    switch (action.id) {
      case "apply":
        return html`
          <button
            class="${this.editorActionClass(action)} apply-action"
            type="button"
            ?disabled=${!action.enabled}
            @click=${() => void this.controller.applyCurrentDraft()}
          >
            ${this.model.applying ? "Applying..." : action.label}
          </button>
        `;
      case "saveAs": {
        const sourceName =
          this.model.name.trim() || this.catalogueSourceLabel || "Effect";
        return html`
          <button
            class=${this.editorActionClass(action)}
            type="button"
            ?disabled=${!action.enabled}
            @click=${(event: Event) =>
              this.modal.requestSaveAs(
                event.currentTarget as HTMLElement,
                `${sourceName} copy`,
              )}
          >
            ${action.label}
          </button>
        `;
      }
      case "reset":
        return html`
          <button
            class=${this.editorActionClass(action)}
            type="button"
            ?disabled=${!action.enabled}
            @click=${() => this.editor.resetContent()}
          >
            ${action.label}
          </button>
        `;
      case "cancel":
        return html`
          <button
            class=${this.editorActionClass(action)}
            type="button"
            ?disabled=${!action.enabled}
            @click=${this.cancelSceneEdit}
          >
            ${action.label}
          </button>
        `;
      case "delete":
        return this.renderEditorDeleteButton(action);
      case "save":
        return html`
          <button
            class=${this.editorActionClass(action)}
            type="button"
            ?disabled=${!action.enabled}
            @click=${() =>
              this.modal.requestSave(
                () => void this.controller.save(),
              )}
          >
            ${this.model.saving ? "Saving..." : action.label}
          </button>
        `;
    }
  }

  private editorActionClass(action: EditorActionDescriptor): string {
    return action.style === "delete"
      ? "danger delete-action"
      : action.style;
  }

  private keyDown = (event: KeyboardEvent): void => {
    if (
      event.defaultPrevented ||
      event.repeat ||
      event.isComposing ||
      event.key.toLocaleLowerCase() !== "s" ||
      (!event.ctrlKey && !event.metaKey) ||
      this.modal.open
    ) {
      return;
    }
    if (event.shiftKey) {
      if (this.section === "scenes" && !this.model.sceneEditorOpen) {
        return;
      }
      if (
        !this.model.editorAction("saveAs")?.enabled
      ) {
        return;
      }
      event.preventDefault();
      const sourceName =
        this.model.name.trim() || this.catalogueSourceLabel || "Effect";
      this.modal.requestSaveAs(this, `${sourceName} copy`);
      return;
    }
    if (this.section === "scenes") {
      if (this.model.sceneEditorOpen) {
        if (
          !this.model.canSaveCurrentDraft ||
          this.model.saving ||
          this.model.deletingCurrentItem
        ) {
          return;
        }
        event.preventDefault();
        this.controller.cancelPendingAutoSave();
        this.modal.requestSave(() => void this.controller.save());
        return;
      }
      const sceneBrowser =
        this.shadowRoot?.querySelector<GoveeSceneBrowser>(
          "govee-scene-browser",
        );
      if (sceneBrowser?.invokeSaveShortcut?.()) {
        event.preventDefault();
      }
      return;
    }
    if (
      !this.model.editorAction("save")?.enabled
    ) {
      return;
    }
    event.preventDefault();
    this.controller.cancelPendingAutoSave();
    this.modal.requestSave(() => void this.controller.save());
  };

  private get selectedSingleEffectFamily() {
    return this.model.selectedSingleEffectFamily;
  }

  private syncSingleEffectSelects(): void {
    if (
      this.content.kind !== "h617a_painted" &&
      this.content.kind !== "h617a_single" &&
      this.content.kind !== "palette_diy"
    ) {
      return;
    }
    const effect = this.shadowRoot?.querySelector<HTMLSelectElement>(
      'select[aria-label="Effect"]',
    );
    if (effect) {
      effect.value =
        this.content.kind === "h617a_painted"
          ? "paint"
          : this.selectedSingleEffectFamily?.id ??
            `unknown:${this.content.family}`;
    }
    if (this.content.kind === "h617a_painted") {
      const variation = this.shadowRoot?.querySelector<HTMLSelectElement>(
        'select[aria-label="Variation"]',
      );
      if (variation) {
        variation.value = this.content.effect;
      }
    }
  }

  private sliderField(
    label: string,
    key: "speed" | "brightness",
    value: number,
  ) {
    return html`
      <govee-slider-control
        .label=${label}
        .value=${value}
        .minimum=${0}
        .maximum=${100}
        .disabled=${this.editorDisabled}
        @value-changed=${(event: CustomEvent<SliderControlChange>) =>
          this.editor.updatePaintedContent(
            { [key]: event.detail.value },
            event.detail.interaction,
          )}
      ></govee-slider-control>
    `;
  }

  private sceneInitialSelectionOpened = (): void => {
    this.controller.sceneInitialSelectionOpened();
  };

  private sceneInitialSelectionFailed = (): void => {
    this.controller.sceneInitialSelectionFailed();
  };

  private sceneLibraryItemSaved(
    event: CustomEvent<{
      item: LibraryItem;
      configEntryId: string;
      selectionIsCurrent: boolean;
      panelTransitionEpoch: number;
    }>,
  ): void {
    void this.controller.sceneItemSaved(
      event.detail.item,
      event.detail.configEntryId,
      event.detail.selectionIsCurrent,
      event.detail.panelTransitionEpoch,
    );
  }

  private sceneTemplateSelected(
    event: CustomEvent<SceneEditSelection>,
  ): void {
    void this.controller.openSceneEditor(
      event.detail,
      this.eventReturnFocus(event),
    );
  }

  private eventReturnFocus(event: Event): HTMLElement | undefined {
    return event
      .composedPath()
      .find((candidate): candidate is HTMLElement =>
        candidate instanceof HTMLElement &&
        (candidate.matches("button, select, input") || candidate === this),
      );
  }

  private navigationClick = (event: MouseEvent): void => {
    if (
      this.redispatchingNavigation ||
      !this.controller.unloadProtectionRequired ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    const anchor = event
      .composedPath()
      .find(
        (candidate): candidate is HTMLAnchorElement =>
          candidate instanceof HTMLAnchorElement &&
          candidate.href !== "" &&
          candidate.target !== "_blank" &&
          !candidate.hasAttribute("download"),
      );
    if (!anchor || anchor.href === window.location.href) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    void this.controller.requestTransition(
      () => {
        this.redispatchingNavigation = true;
        try {
          anchor.click();
        } finally {
          this.redispatchingNavigation = false;
        }
      },
      anchor,
    );
  };

  private beforeUnload = (event: BeforeUnloadEvent): void => {
    event.preventDefault();
    event.returnValue = "";
  };

  private syncUnloadProtection(): void {
    this.setUnloadListener(
      this.isConnected && this.controller?.unloadProtectionRequired === true,
    );
  }

  private setUnloadListener(enabled: boolean): void {
    if (enabled === this.unloadListenerRegistered) {
      return;
    }
    this.unloadListenerRegistered = enabled;
    if (enabled) {
      window.addEventListener("beforeunload", this.beforeUnload);
    } else {
      window.removeEventListener("beforeunload", this.beforeUnload);
    }
  }

  private sceneLibraryItemDeleteRequested(
    event: CustomEvent<LibraryItemDeleteRequest>,
  ): void {
    const { returnFocus, ...candidate } = event.detail;
    this.requestDelete(candidate, returnFocus);
  }

  private cancelSceneEdit(): void {
    this.editor.cancelSceneEdit();
    void this.updateComplete.then(() =>
      this.shadowRoot
        ?.querySelector<GoveeSceneBrowser>("govee-scene-browser")
        ?.refreshSelectedDefault?.(),
    );
  }

  private renderEditorDeleteButton(action: EditorActionDescriptor) {
    if (
      !this.isAdmin ||
      !this.currentItem ||
      !this.model.editorAction("delete")?.visible
    ) {
      return nothing;
    }
    return html`
      <button
        class=${this.editorActionClass(action)}
        type="button"
        ?disabled=${!action.enabled}
        @click=${(event: Event) =>
          this.requestDelete(
            {
              id: this.currentItem!.id,
              version: this.currentItem!.version,
              updated_at: this.currentItem!.updated_at,
              name: this.currentItem!.name,
            },
            event.currentTarget as HTMLElement,
          )}
      >
        ${this.model.deletingCurrentItem ? "Deleting..." : "Delete"}
      </button>
    `;
  }

  private requestDelete(
    candidate: DeleteCandidate,
    returnFocus: HTMLElement,
  ): void {
    this.modal.requestDelete(candidate, returnFocus);
  }

  private cancelDelete(): void {
    this.modal.cancelDelete();
  }

  private deleteDialogKeyDown(event: KeyboardEvent): void {
    this.modal.dialogKeyDown(event, () => this.cancelDelete());
  }

  private cancelSaveName(): void {
    this.modal.cancelSaveName();
  }

  private saveNameDialogKeyDown(event: KeyboardEvent): void {
    this.modal.dialogKeyDown(event, () => this.cancelSaveName());
  }

  private currentScenePreviewRequest(): ScenePreviewRequest | undefined {
    return this.shadowRoot
      ?.querySelector<GoveeSceneBrowser>("govee-scene-browser")
      ?.currentPreviewRequest?.();
  }

  static styles = effectStudioPanelStyles;
}

declare global {
  interface HTMLElementTagNameMap {
    "ha-govee-led-ble-editor": GoveeLedEffectStudio;
  }
}

if (!customElements.get("ha-govee-led-ble-editor")) {
  customElements.define("ha-govee-led-ble-editor", GoveeLedEffectStudio);
}
