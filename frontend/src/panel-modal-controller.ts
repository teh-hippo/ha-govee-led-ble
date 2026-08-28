import {
  PanelModel,
  type DeleteCandidate,
  type PanelModalState,
} from "./panel-model";

interface PanelModalHost {
  updateComplete(): Promise<unknown>;
  root(): ShadowRoot | null;
  canMutate(): boolean;
}

export class PanelModalController {
  private deleteReturnFocus?: HTMLElement;
  private saveNameReturnFocus?: HTMLElement;
  private overwriteReturnFocus?: HTMLElement;
  private errorReturnFocus?: HTMLElement;
  private scrollLock?: { bodyOverflow: string; documentOverflow: string };
  private transitionDialogTeardown?: () => void;
  private overwriteResolution?: (confirmed: boolean) => void;

  public constructor(
    private readonly model: PanelModel,
    private readonly host: PanelModalHost,
  ) {
    this.model.setErrorHandler((message, options) =>
      this.showError(message, options),
    );
  }

  public get open(): boolean {
    return this.model.modalState !== undefined;
  }

  public get deleteCandidate(): DeleteCandidate | undefined {
    return this.model.deleteCandidate;
  }

  public closeForEditorTransition(): void {
    const modal = this.model.modalState;
    const preserveStandaloneError =
      modal?.kind === "error" && modal.resume === undefined;
    if (
      modal?.kind === "pending-transition" ||
      (modal?.kind === "error" &&
        modal.resume?.kind === "pending-transition")
    ) {
      this.transitionDialogTeardown?.();
    }
    this.saveNameReturnFocus = undefined;
    if (!preserveStandaloneError) {
      this.errorReturnFocus = undefined;
    }
    this.overwriteReturnFocus = undefined;
    this.overwriteResolution?.(false);
    this.overwriteResolution = undefined;
    this.model.modalState = preserveStandaloneError ? modal : undefined;
    this.model.saveNameError = undefined;
    this.model.patch({});
  }

  public setTransitionDialogTeardown(callback: () => void): void {
    this.transitionDialogTeardown = callback;
  }

  public requestTransition(
    primaryLabel: "Save" | "Save As",
    saveName: string,
    requiresName: boolean,
    returnFocus?: HTMLElement,
  ): void {
    if (this.open) {
      return;
    }
    this.saveNameReturnFocus = returnFocus;
    this.model.patch({
      modalState: {
        kind: "pending-transition",
        primaryLabel,
        saveName,
        requiresName,
        busy: false,
      },
    });
    void this.host.updateComplete().then(() => {
      const selector =
        primaryLabel === "Save As"
          ? ".transition-dialog input"
          : ".transition-dialog .secondary";
      this.host.root()?.querySelector<HTMLElement>(selector)?.focus();
    });
  }

  public updateTransitionName(saveName: string): void {
    const dialog = this.model.modalState;
    if (dialog?.kind === "pending-transition") {
      this.model.patch({
        modalState: {
          ...dialog,
          saveName,
          error: undefined,
        },
      });
    }
  }

  public updateTransition(
    change: Partial<
      Extract<NonNullable<PanelModel["modalState"]>, { kind: "pending-transition" }>
    >,
  ): void {
    const dialog = this.model.modalState;
    if (dialog?.kind === "pending-transition") {
      this.model.patch({
        modalState: { ...dialog, ...change },
      });
    } else if (
      dialog?.kind === "error" &&
      dialog.resume?.kind === "pending-transition"
    ) {
      this.model.patch({
        modalState: {
          ...dialog,
          resume: { ...dialog.resume, ...change },
        },
      });
    }
  }

  public closeTransition(restoreFocus: boolean): void {
    const returnFocus = this.saveNameReturnFocus;
    this.saveNameReturnFocus = undefined;
    if (this.model.modalState?.kind === "pending-transition") {
      this.model.patch({ modalState: undefined });
    } else if (
      this.model.modalState?.kind === "error" &&
      this.model.modalState.resume?.kind === "pending-transition"
    ) {
      const { resume: _resume, ...error } = this.model.modalState;
      this.model.patch({ modalState: error });
    }
    if (restoreFocus) {
      this.restoreFocus(returnFocus);
    }
  }

  public requestDelete(candidate: DeleteCandidate, returnFocus: HTMLElement): void {
    if (!this.host.canMutate() || !this.model.isAdmin || this.model.deletingItemId !== undefined || this.model.saving) return;
    this.deleteReturnFocus = returnFocus;
    this.model.patch({
      modalState: { kind: "delete", candidate: { ...candidate } },
      notice: undefined,
    });
    void this.host.updateComplete().then(() => {
      this.host.root()?.querySelector<HTMLButtonElement>(".delete-dialog .secondary")?.focus();
    });
  }

  public cancelDelete(): void {
    const returnFocus = this.deleteReturnFocus;
    this.deleteReturnFocus = undefined;
    if (this.model.modalState?.kind === "delete") {
      this.model.patch({ modalState: undefined });
    }
    this.restoreFocus(returnFocus);
  }

  public takeDeleteCandidate(): DeleteCandidate | undefined {
    const candidate = this.model.deleteCandidate;
    this.deleteReturnFocus = undefined;
    if (this.model.modalState?.kind === "delete") {
      this.model.patch({ modalState: undefined });
    }
    return candidate;
  }

  public requestSave(save: () => void): void {
    if (!this.model.isAdmin || !this.model.canSaveCurrentDraft || this.model.saving || this.model.deletingCurrentItem) return;
    save();
  }

  public requestSaveAs(
    returnFocus: HTMLElement,
    suggestedName: string,
  ): void {
    if (
      !this.host.canMutate() ||
      !this.model.isAdmin ||
      this.model.saving ||
      this.model.deletingCurrentItem
    ) {
      return;
    }
    this.requestNamedSave(returnFocus, suggestedName);
  }

  private requestNamedSave(
    returnFocus: HTMLElement,
    value: string,
  ): void {
    this.saveNameReturnFocus = returnFocus;
    this.model.patch({
      saveNameValue: value,
      saveNameError: undefined,
      modalState: { kind: "save-name", busy: false },
    });
    void this.host.updateComplete().then(() => {
      const input = this.host.root()?.querySelector<HTMLInputElement>(".save-dialog input");
      input?.focus();
      input?.select();
    });
  }

  public saveNameChanged(saveNameValue: string): void {
    this.model.patch({ saveNameValue, saveNameError: undefined });
  }

  public cancelSaveName(): void {
    if (
      this.model.modalState?.kind === "save-name" &&
      this.model.modalState.busy
    ) {
      return;
    }
    const returnFocus = this.saveNameReturnFocus;
    this.saveNameReturnFocus = undefined;
    if (this.model.modalState?.kind === "save-name") {
      this.model.patch({
        modalState: undefined,
        saveNameError: undefined,
      });
    }
    this.restoreFocus(returnFocus);
  }

  public async confirmNamedSave(
    save: (name: string) => Promise<boolean>,
  ): Promise<void> {
    const name = this.model.saveNameValue.trim();
    if (!name) {
      this.showError("Enter an effect name.", {
        title: "Effect name required",
        key: `save-name-required:${this.model.saveNameValue}`,
      });
      return;
    }
    this.model.patch({
      modalState: { kind: "save-name", busy: true },
      saveNameError: undefined,
    });
    const saved = await save(name);
    if (saved) {
      this.saveNameReturnFocus = undefined;
      if (this.model.modalState?.kind === "save-name") {
        this.model.patch({ modalState: undefined });
      } else if (
        this.model.modalState?.kind === "error" &&
        this.model.modalState.resume?.kind === "save-name"
      ) {
        const { resume: _resume, ...error } = this.model.modalState;
        this.model.patch({ modalState: error });
      }
    } else {
      this.updateSaveNameBusy(false);
    }
  }

  public showError(
    message: string,
    options: {
      title?: string;
      key?: string;
      resumeWorkflow?: boolean;
    } = {},
  ): void {
    const key = options.key ?? `error:${message}`;
    const current = this.model.modalState;
    if (current?.kind === "error" && current.key === key) {
      return;
    }
    if (options.resumeWorkflow === false) {
      this.overwriteResolution?.(false);
      this.overwriteResolution = undefined;
      this.saveNameReturnFocus = undefined;
      this.overwriteReturnFocus = undefined;
    }
    const resume =
      options.resumeWorkflow === false
        ? undefined
        : current?.kind === "error"
          ? current.resume
          : current
            ? current
            : undefined;
    const active = this.host.root()?.activeElement;
    this.errorReturnFocus = htmlElement(active) ?? this.errorReturnFocus;
    this.model.patch({
      modalState: {
        kind: "error",
        title: options.title ?? "Effect Studio error",
        message,
        key,
        ...(resume ? { resume } : {}),
      },
    });
    void this.host.updateComplete().then(() => {
      this.host.root()
        ?.querySelector<HTMLButtonElement>(".error-dialog .secondary")
        ?.focus();
    });
  }

  public closeError(): void {
    const dialog = this.model.modalState;
    if (dialog?.kind !== "error") {
      return;
    }
    const resume = dialog.resume;
    this.model.patch({ modalState: resume });
    if (resume) {
      void this.host.updateComplete().then(() =>
        this.focusModal(resume),
      );
      return;
    }
    const returnFocus = this.errorReturnFocus;
    this.errorReturnFocus = undefined;
    this.restoreFocus(returnFocus);
  }

  public requestOverwrite(
    effectName: string,
  ): Promise<boolean> {
    const current = this.model.modalState;
    if (
      current?.kind === "delete" ||
      current?.kind === "error" ||
      current?.kind === "overwrite"
    ) {
      return Promise.resolve(false);
    }
    const active = this.host.root()?.activeElement;
    this.overwriteReturnFocus =
      htmlElement(active) ?? this.overwriteReturnFocus;
    this.model.patch({
      modalState: {
        kind: "overwrite",
        effectName,
        ...(current ? { resume: current } : {}),
      },
    });
    const confirmation = new Promise<boolean>((resolve) => {
      this.overwriteResolution = resolve;
    });
    void this.host.updateComplete().then(() => {
      this.host.root()
        ?.querySelector<HTMLButtonElement>(".overwrite-dialog .secondary")
        ?.focus();
    });
    return confirmation;
  }

  public cancelOverwrite(): void {
    if (this.model.modalState?.kind !== "overwrite") {
      return;
    }
    const returnFocus = this.overwriteReturnFocus;
    const resume = this.model.modalState.resume;
    this.overwriteReturnFocus = undefined;
    this.overwriteResolution?.(false);
    this.overwriteResolution = undefined;
    this.model.patch({ modalState: resume });
    if (resume) {
      void this.host.updateComplete().then(() =>
        this.focusModal(resume),
      );
      return;
    }
    this.restoreFocus(returnFocus);
  }

  public confirmOverwrite(): void {
    if (this.model.modalState?.kind !== "overwrite") {
      return;
    }
    const resume = this.model.modalState.resume;
    this.overwriteReturnFocus = undefined;
    this.overwriteResolution?.(true);
    this.overwriteResolution = undefined;
    this.model.patch({ modalState: resume });
  }

  public dialogKeyDown(event: KeyboardEvent, cancel: () => void): void {
    if (event.key === "Tab") this.trapDialogFocus(event);
    else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  }

  public focusActiveSectionIfNeeded(): void {
    void this.host.updateComplete().then(() => {
      if (!this.host.root()?.activeElement) {
        this.host.root()?.querySelector<HTMLButtonElement>('.primary-nav .selector[aria-current="page"]')?.focus();
      }
    });
  }

  public syncScrollLock(): void {
    if (!this.open) {
      this.releaseScrollLock();
      return;
    }
    if (this.scrollLock) return;
    this.scrollLock = {
      bodyOverflow: document.body.style.overflow,
      documentOverflow: document.documentElement.style.overflow,
    };
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
  }

  public releaseScrollLock(): void {
    if (!this.scrollLock) return;
    document.body.style.overflow = this.scrollLock.bodyOverflow;
    document.documentElement.style.overflow = this.scrollLock.documentOverflow;
    this.scrollLock = undefined;
  }

  private restoreFocus(element: HTMLElement | undefined): void {
    void this.host.updateComplete().then(() => {
      if (element?.isConnected) element.focus();
    });
  }

  private focusModal(modal: PanelModalState): void {
    const selector =
      modal.kind === "save-name"
        ? ".save-dialog input"
        : modal.kind === "pending-transition"
          ? ".transition-dialog .secondary"
          : modal.kind === "delete"
            ? ".delete-dialog .secondary"
            : modal.kind === "overwrite"
              ? ".overwrite-dialog .secondary"
              : ".error-dialog .secondary";
    this.host.root()?.querySelector<HTMLElement>(selector)?.focus();
  }

  private updateSaveNameBusy(busy: boolean): void {
    const modal = this.model.modalState;
    if (modal?.kind === "save-name") {
      this.model.patch({
        modalState: { ...modal, busy },
      });
    } else if (
      modal?.kind === "error" &&
      modal.resume?.kind === "save-name"
    ) {
      this.model.patch({
        modalState: {
          ...modal,
          resume: { ...modal.resume, busy },
        },
      });
    }
  }

  private trapDialogFocus(event: KeyboardEvent): void {
    const dialog = event.currentTarget as HTMLElement;
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    )).filter((element) => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    const root = dialog.getRootNode();
    const active = root instanceof ShadowRoot ? root.activeElement : document.activeElement;
    const activeIsFocusable = active instanceof HTMLElement && focusable.includes(active);
    if (event.shiftKey && (active === first || !activeIsFocusable)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !activeIsFocusable)) {
      event.preventDefault();
      first.focus();
    }
  }
}

function htmlElement(
  value: Element | null | undefined,
): HTMLElement | undefined {
  return typeof HTMLElement !== "undefined" && value instanceof HTMLElement
    ? value
    : undefined;
}
