import { css } from "lit";

export const studioTokenStyles = css`
  :host {
    --studio-blue: var(--primary-color, #03a9f4);
    --studio-blue-soft: color-mix(
      in srgb,
      var(--studio-blue) 13%,
      transparent
    );
    --studio-border: var(--divider-color, #d8dce2);
    --studio-border-width: 1px;
    --studio-strong-border-width: 2px;
    --studio-card: var(--card-background-color, #fff);
    --studio-muted: var(--secondary-text-color, #68707c);
    --studio-danger: var(--error-color, #db4437);
    --studio-spacing-xxs: 4px;
    --studio-spacing-xs: 6px;
    --studio-spacing-sm: 8px;
    --studio-spacing-md: 10px;
    --studio-spacing-lg: 12px;
    --studio-spacing-xl: 14px;
    --studio-spacing-2xl: 16px;
    --studio-spacing-3xl: 18px;
    --studio-spacing-4xl: 20px;
    --studio-spacing-5xl: 22px;
    --studio-spacing-6xl: 24px;
    --studio-spacing-7xl: 28px;
    --studio-touch-target-size: 44px;
    --studio-control-height: var(--studio-touch-target-size);
    --studio-compact-control-height: 36px;
    --studio-compact-action-size: var(--studio-control-height);
    --studio-app-header-height: 56px;
    --studio-icon-size: 20px;
    --studio-action-glyph-size: var(--studio-icon-size);
    --studio-info-control-size: var(--studio-spacing-6xl);
    --studio-info-control-font-size: var(--studio-caption-size);
    --studio-info-popover-width: 320px;
    --studio-checkbox-size: 20px;
    --studio-small-swatch-size: 16px;
    --studio-swatch-size: 32px;
    --studio-paint-segment-height: 48px;
    --studio-control-radius: 8px;
    --studio-button-radius: 9px;
    --studio-card-radius: 10px;
    --studio-dialog-radius: 12px;
    --studio-swatch-radius: 6px;
    --studio-pill-radius: 999px;
    --studio-round-radius: 50%;
    --studio-card-padding: var(--studio-spacing-4xl);
    --studio-section-gap: var(--studio-spacing-3xl);
    --studio-parameter-gap: var(--studio-spacing-3xl);
    --studio-section-title-gap: var(--studio-spacing-xl);
    --studio-field-margin: var(--studio-spacing-xl);
    --studio-heading-gap: var(--studio-spacing-4xl);
    --studio-editor-heading-gap: var(--studio-spacing-5xl);
    --studio-control-gap: var(--studio-spacing-md);
    --studio-action-gap: var(--studio-spacing-md);
    --studio-compact-gap: var(--studio-spacing-sm);
    --studio-tight-gap: var(--studio-spacing-xs);
    --studio-micro-gap: var(--studio-spacing-xxs);
    --studio-caption-size: 12px;
    --studio-parameter-label-size: 13px;
    --studio-font-weight-medium: 500;
    --studio-font-weight-semibold: 600;
    --studio-font-weight-emphasis: 650;
    --studio-font-weight-bold: 700;
    --studio-font-weight-alert: 800;
    --studio-parameter-label-weight: var(--studio-font-weight-semibold);
    --studio-label-line-height: 1.35;
    --studio-muted-line-height: 1.45;
    --studio-body-line-height: 1.5;
    --studio-reading-line-height: 1.55;
    --studio-icon-line-height: 1;
    --studio-subheading-size: 14px;
    --studio-section-title-size: 16px;
    --studio-section-title-weight: var(--studio-font-weight-semibold);
    --studio-heading-size: 20px;
    --studio-editor-heading-size: 24px;
    --studio-page-heading-size: 25px;
    --studio-action-padding: var(--studio-spacing-sm)
      var(--studio-spacing-2xl);
    --studio-field-padding: var(--studio-spacing-sm)
      var(--studio-spacing-md);
    --studio-option-padding: var(--studio-spacing-sm)
      var(--studio-spacing-lg);
    --studio-sidebar-padding: var(--studio-spacing-5xl)
      var(--studio-spacing-2xl);
    --studio-editor-padding: var(--studio-spacing-7xl);
    --studio-mobile-editor-bottom-padding: 32px;
    --studio-mobile-editor-padding: var(--studio-spacing-4xl)
      var(--studio-spacing-2xl)
      var(--studio-mobile-editor-bottom-padding);
    --studio-dialog-padding: var(--studio-spacing-6xl);
    --studio-dialog-viewport-gutter: 48px;
    --studio-message-block-padding: 48px;
    --studio-message-inline-padding: 24px;
    --studio-empty-state-block-padding: 56px;
    --studio-chrome-gutter: var(--studio-spacing-2xl);
    --studio-empty-state-max-width: 680px;
    --studio-editor-name-max-width: 460px;
    --studio-editor-action-width: 96px;
    --studio-navigation-width: clamp(168px, 14vw, 190px);
    --studio-list-width: clamp(210px, 18vw, 230px);
    --studio-stacked-navigation-width: clamp(152px, 16vw, 170px);
    --studio-stacked-list-max-height: 220px;
    --studio-mobile-list-max-height: 340px;
    --studio-transition-duration: 120ms;
    --studio-switch-track-height: 24px;
    --studio-switch-thumb-size: 18px;
    --studio-switch-thumb-inset: 3px;
    --studio-compact-switch-track-width: 48px;
    --studio-switch-track-off: color-mix(
      in srgb,
      var(--studio-muted) 42%,
      var(--studio-card)
    );
    --studio-switch-track-on: color-mix(
      in srgb,
      var(--studio-blue) 72%,
      var(--studio-card)
    );
    --studio-switch-thumb-off: color-mix(
      in srgb,
      var(--studio-muted) 72%,
      var(--studio-card)
    );
    --studio-switch-thumb-on: var(--text-primary-color, #fff);
    --studio-switch-transition-duration: 150ms;
    --studio-switch-transition-easing: cubic-bezier(0.31, 0.94, 0.34, 1);
    --studio-z-raised: 1;
    --studio-z-toolbar: 4;
    --studio-z-popover: 20;
    --studio-z-modal: 1000;
    --studio-disabled-opacity: 0.52;
    --studio-focus-width: 3px;
    --studio-focus-offset: 2px;
    --studio-popover-padding: 10px;
    --studio-popover-radius: 9px;
    --studio-popover-shadow: 0 8px 24px rgb(0 0 0 / 18%);
    --studio-mobile-gutter: 24px;
  }
`;

export const studioBaseStyles = css`
  * {
    box-sizing: border-box;
  }

  button,
  input,
  select {
    font: inherit;
  }

  button {
    min-height: var(--studio-control-height);
  }

  button:disabled,
  input:disabled,
  select:disabled {
    cursor: not-allowed;
    opacity: var(--studio-disabled-opacity);
  }
`;

export const studioCardStyles = css`
  .card {
    min-width: 0;
    padding: var(--studio-card-padding);
    border: var(--studio-border-width) solid var(--studio-border);
    border-radius: var(--studio-card-radius);
    background: var(--studio-card);
  }

  .section-title {
    margin: 0 0 var(--studio-section-title-gap);
    font-size: var(--studio-section-title-size);
    font-weight: var(--studio-section-title-weight);
    line-height: var(--studio-label-line-height);
  }
`;

export const studioActionStyles = css`
  .primary,
  .secondary,
  .danger {
    min-height: var(--studio-control-height);
    padding: var(--studio-action-padding);
    border-radius: var(--studio-button-radius);
    font-weight: var(--studio-font-weight-semibold);
    cursor: pointer;
  }

  .primary {
    border: var(--studio-border-width) solid var(--studio-blue);
    color: var(--text-primary-color, #fff);
    background: var(--studio-blue);
  }

  .secondary {
    border: var(--studio-border-width) solid var(--studio-border);
    color: var(--primary-text-color);
    background: var(--studio-card);
  }

  .danger {
    border: var(--studio-border-width) solid var(--studio-danger);
    color: var(--studio-danger);
    background: var(--studio-card);
  }

  .danger:hover,
  .danger:focus-visible {
    color: var(--text-primary-color, #fff);
    background: var(--studio-danger);
  }

  .danger.delete-action {
    color: var(--text-primary-color, #fff);
    background: var(--studio-danger);
  }

  .danger.delete-action:hover,
  .danger.delete-action:focus-visible {
    background: color-mix(in srgb, var(--studio-danger) 84%, #000);
  }

  .secondary.active {
    color: var(--studio-blue);
    border-color: var(--studio-blue);
    background: var(--studio-blue-soft);
  }
`;

export const studioSelectorStyles = css`
  .selector {
    width: 100%;
    min-height: var(--studio-control-height);
    padding: var(--studio-field-padding);
    border: 0;
    border-radius: var(--studio-control-radius);
    color: var(--primary-text-color);
    background: transparent;
    text-align: start;
    cursor: pointer;
  }

  .selector:hover {
    background: color-mix(
      in srgb,
      var(--primary-text-color) 6%,
      transparent
    );
  }

  .selector.selected {
    /* Selection uses colour and fill so labels keep the same width and row height. */
    color: var(--studio-blue);
    background: var(--studio-blue-soft);
  }
`;

export const studioFormStyles = css`
  .parameter-stack {
    display: grid;
    gap: var(--studio-parameter-gap);
  }

  .parameter-stack > .field,
  .parameter-stack > .range-field,
  .parameter-stack > .parameter-group,
  .parameter-stack > .check-field {
    margin-top: 0;
  }

  .parameter-group {
    display: grid;
    gap: var(--studio-control-gap);
  }

  .check-field {
    display: flex;
    align-items: center;
    gap: var(--studio-control-gap);
    min-height: var(--studio-control-height);
  }

  .check-field input[type="checkbox"] {
    width: var(--studio-checkbox-size);
    height: var(--studio-checkbox-size);
    margin: 0;
    accent-color: var(--studio-blue);
  }

  .parameter-label,
  .field > span:first-child,
  .range-field > span:first-child,
  .check-field > span:last-child {
    color: var(--studio-muted);
    font-size: var(--studio-parameter-label-size);
    font-weight: var(--studio-parameter-label-weight);
    line-height: var(--studio-label-line-height);
  }

  .parameter-options {
    display: flex;
    flex-wrap: wrap;
    gap: var(--studio-tight-gap);
  }

  .parameter-options button {
    min-width: 0;
    flex: 1;
    padding: var(--studio-option-padding);
    border: var(--studio-border-width) solid var(--studio-border);
    border-radius: var(--studio-control-radius);
    color: var(--primary-text-color);
    background: var(--studio-card);
    font-size: var(--studio-parameter-label-size);
    font-weight: var(--studio-parameter-label-weight);
    cursor: pointer;
  }

  .parameter-options button.selected,
  .parameter-options button[aria-pressed="true"] {
    color: var(--studio-blue);
    border-color: var(--studio-blue);
    background: var(--studio-blue-soft);
  }

  .field,
  .range-field {
    display: grid;
    align-items: center;
    gap: var(--studio-control-gap);
    margin-top: var(--studio-field-margin);
  }

  .field input,
  .field select {
    width: 100%;
    min-width: 0;
    min-height: var(--studio-control-height);
    padding: var(--studio-field-padding);
    border: var(--studio-border-width) solid var(--studio-border);
    border-radius: var(--studio-control-radius);
    color: var(--primary-text-color);
    background: var(--studio-card);
  }

  .range-field input[type="range"] {
    width: 100%;
    min-width: 0;
    min-height: var(--studio-control-height);
    margin: 0;
  }

`;

export const studioEditorStyles = css`
  .editor-heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--studio-heading-gap);
    margin-bottom: var(--studio-editor-heading-gap);
  }

  .editor-title {
    display: grid;
    min-width: 0;
    gap: var(--studio-tight-gap);
  }

  .editable-title {
    display: flex;
    align-items: center;
    gap: var(--studio-tight-gap);
    min-width: 0;
  }

  .dirty-marker {
    color: var(--studio-blue);
    font-size: var(--studio-heading-size);
    font-weight: var(--studio-font-weight-bold);
    line-height: var(--studio-icon-line-height);
  }

  .origin-name {
    color: var(--studio-muted);
    font-size: var(--studio-caption-size);
    line-height: var(--studio-label-line-height);
  }

  .editor-name {
    width: min(var(--studio-editor-name-max-width), 100%);
    min-height: var(--studio-control-height);
    padding: var(--studio-compact-gap) 0;
    border: 0;
    border-bottom: var(--studio-border-width) solid var(--studio-border);
    border-radius: 0;
    color: var(--primary-text-color);
    background: transparent;
    font-size: var(--studio-editor-heading-size);
    font-weight: var(--studio-font-weight-semibold);
  }

  .actions {
    display: flex;
    flex: 1;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--studio-action-gap);
  }

  .actions > .apply-action {
    margin-right: auto;
  }

  .actions > button {
    width: var(--studio-editor-action-width);
    min-width: var(--studio-editor-action-width);
    max-width: var(--studio-editor-action-width);
  }

  /* Gives editor actions full-row room on phone widths. */
  @media (max-width: 600px) {
    .editor-heading {
      align-items: stretch;
      flex-direction: column;
    }

    .actions {
      display: grid;
      grid-template-columns: repeat(
        auto-fit,
        minmax(var(--studio-editor-action-width), 1fr)
      );
    }

    .actions > button {
      width: auto;
      min-width: 0;
      max-width: none;
    }
  }
`;

export const studioVisuallyHiddenStyles = css`
  /* Standard one-pixel accessibility box keeps content available to assistive technology. */
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
  }
`;

export const studioWorkspaceStyles = css`
  .sidebar {
    overflow: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    padding: var(--studio-sidebar-padding);
    border-inline-end: var(--studio-border-width) solid var(--studio-border);
    contain: style;
  }

  .item-sidebar {
    background: var(--primary-background-color);
  }

  .editor-surface {
    min-width: 0;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    padding: var(--studio-editor-padding);
    background: var(--secondary-background-color, #f5f6f8);
    contain: style;
  }

  /* Matches the panel's narrow document-flow breakpoint. */
  @media (max-width: 900px) {
    .item-sidebar {
      max-height: var(--studio-mobile-list-max-height);
      border-inline-end: 0;
      border-bottom: var(--studio-border-width) solid var(--studio-border);
    }
  }

  /* Reduces editor gutters once primary navigation becomes horizontal. */
  @media (max-width: 760px) {
    .editor-surface {
      padding: var(--studio-mobile-editor-padding);
    }
  }
`;
