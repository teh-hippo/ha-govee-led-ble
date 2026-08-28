import { css } from "lit";

import {
  studioActionStyles,
  studioBaseStyles,
  studioCardStyles,
  studioFormStyles,
  studioVisuallyHiddenStyles,
} from "./studio-styles";

export const advancedEffectEditorStyles = [
  studioBaseStyles,
  studioCardStyles,
  studioActionStyles,
  studioFormStyles,
  studioVisuallyHiddenStyles,
  css`
    :host {
      display: block;
    }

    p {
      margin-top: 0;
    }

    .layer-card {
      margin-bottom: var(--studio-section-gap);
    }

    .selected-record-panel {
      padding-top: var(--studio-section-gap);
      border-top: var(--studio-border-width) solid var(--studio-border);
    }

    .layer-strip,
    .pattern-strip {
      --strip-label-min-width: var(--studio-compact-action-size);
    }

    .layer-card > .section-title {
      margin-bottom: var(--studio-section-title-gap);
    }

    .card-heading,
    .section-heading,
    .subsection-heading {
      display: flex;
      align-items: center;
      gap: var(--studio-compact-gap);
    }

    .section-heading {
      margin-bottom: var(--studio-section-title-gap);
    }

    .section-heading .section-title {
      margin: 0;
    }

    .subsection-heading h4 {
      margin: 0;
      font-size: var(--studio-subheading-size);
      font-weight: var(--studio-font-weight-semibold);
    }

    .add-button {
      flex: 0 0 auto;
      padding: var(--studio-spacing-sm) var(--studio-spacing-xl);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-control-radius);
      color: var(--studio-blue);
      background: var(--studio-card);
      font-weight: var(--studio-font-weight-semibold);
      border-style: dashed;
      cursor: pointer;
    }

    .muted {
      color: var(--studio-muted);
      font-size: var(--studio-parameter-label-size);
      line-height: var(--studio-muted-line-height);
    }

    .empty-state .add-button {
      margin-top: var(--studio-spacing-lg);
    }

    .control-grid {
      column-width: 500px;
      column-gap: var(--studio-section-gap);
      column-fill: balance;
    }

    .control-grid > .card {
      display: inline-block;
      width: 100%;
      margin: 0 0 var(--studio-section-gap);
      break-inside: avoid;
      break-inside: avoid-column;
    }

    .fill-pattern-controls {
      margin-top: var(--studio-section-gap);
      padding-top: var(--studio-section-gap);
      border-top: var(--studio-border-width) solid var(--studio-border);
    }

    .parameter-grid {
      display: grid;
      grid-template-columns: repeat(
        auto-fit,
        minmax(min(100%, 220px), 1fr)
      );
      gap: var(--studio-parameter-gap) var(--studio-section-gap);
    }

    .parameter-grid > .field {
      margin-top: 0;
    }

    .patterns-section {
      display: grid;
      gap: var(--studio-parameter-gap);
    }

    .brightness-fields {
      padding-top: var(--studio-parameter-gap);
      border-top: var(--studio-border-width) solid var(--studio-border);
    }

    .compact-action-icon {
      --mdc-icon-size: var(--studio-icon-size);
      display: inline-flex;
      width: var(--studio-icon-size);
      height: var(--studio-icon-size);
      align-items: center;
      justify-content: center;
      line-height: 0;
    }

    .card-heading {
      justify-content: space-between;
      margin-bottom: var(--studio-section-title-gap);
    }

    .card-heading .section-heading {
      margin-bottom: 0;
    }

    .field-label-with-help {
      display: inline-flex;
      align-items: center;
      gap: var(--studio-compact-gap);
      justify-self: start;
    }

    /* Advanced cards become single-column when controls no longer fit. */
    @media (max-width: 760px) {
      .add-button {
        width: 100%;
      }
    }

    /* Recovers phone-width card space without reducing control hit targets. */
    @media (max-width: 480px) {
      .card {
        padding: var(--studio-spacing-2xl);
      }

      .secondary {
        min-width: 0;
      }
    }
  `,
];
