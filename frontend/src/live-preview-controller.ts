import type { PreviewStatus } from "./types";

export type LivePreviewInteraction = "changing" | "committed";

export interface LivePreviewRequest {
  fingerprint: string;
  persistDefault?: boolean;
}

const SLOW_PREVIEW_DISPLAY_DELAY_MS = 500;

interface LivePreviewProgressOptions {
  changed: (visible: boolean) => void;
  now?: () => number;
  setTimer?: (callback: () => void, delay: number) => number;
  clearTimer?: (timer: number) => void;
}

export class LivePreviewProgressController {
  private readonly changed: (visible: boolean) => void;
  private readonly now: () => number;
  private readonly setTimer: (callback: () => void, delay: number) => number;
  private readonly clearTimer: (timer: number) => void;
  private starts = new Map<number, number>();
  private configEntryId?: string;
  private pendingSequence?: number;
  private displayTimer?: number;
  private visible = false;

  public constructor(options: LivePreviewProgressOptions) {
    this.changed = options.changed;
    this.now = options.now ?? (() => performance.now());
    this.setTimer =
      options.setTimer ??
      ((callback, delay) => window.setTimeout(callback, delay));
    this.clearTimer =
      options.clearTimer ?? ((timer) => window.clearTimeout(timer));
  }

  public accept(status: PreviewStatus): void {
    if (
      this.configEntryId !== undefined &&
      status.config_entry_id !== this.configEntryId
    ) {
      this.reset();
    }
    this.configEntryId = status.config_entry_id;
    if (status.phase === "queued") {
      for (const sequence of this.starts.keys()) {
        if (sequence < status.sequence) {
          this.starts.delete(sequence);
        }
      }
      this.starts.set(status.sequence, this.now());
      this.startPending(status.sequence);
      return;
    }
    if (status.phase === "writing") {
      this.startPending(status.sequence);
      return;
    }
    if (status.phase === "written") {
      this.starts.delete(status.sequence);
    }
    this.clearPending(status.sequence);
  }

  public clear(): void {
    if (this.pendingSequence !== undefined) {
      this.starts.delete(this.pendingSequence);
    }
    this.pendingSequence = undefined;
    this.clearDisplayTimer();
    this.setVisible(false);
  }

  public reset(): void {
    this.clear();
    this.configEntryId = undefined;
    this.starts = new Map();
  }

  private startPending(sequence: number): void {
    if (this.pendingSequence === sequence) {
      return;
    }
    this.pendingSequence = sequence;
    this.clearDisplayTimer();
    this.setVisible(false);
    this.displayTimer = this.setTimer(() => {
      this.displayTimer = undefined;
      if (this.pendingSequence === sequence) {
        this.setVisible(true);
      }
    }, SLOW_PREVIEW_DISPLAY_DELAY_MS);
  }

  private clearPending(sequence: number): void {
    if (this.pendingSequence !== sequence) {
      return;
    }
    this.clear();
  }

  private clearDisplayTimer(): void {
    if (this.displayTimer !== undefined) {
      this.clearTimer(this.displayTimer);
      this.displayTimer = undefined;
    }
  }

  private setVisible(visible: boolean): void {
    if (this.visible === visible) {
      return;
    }
    this.visible = visible;
    this.changed(visible);
  }
}
