import { css } from "lit";

import {
  studioActionStyles,
  studioBaseStyles,
  studioCardStyles,
  studioEditorStyles,
  studioFormStyles,
  studioSelectorStyles,
  studioTokenStyles,
  studioVisuallyHiddenStyles,
  studioWorkspaceStyles,
} from "./studio-styles";

export const effectStudioPanelStyles = [
  studioTokenStyles,
  studioBaseStyles,
  studioCardStyles,
  studioActionStyles,
  studioSelectorStyles,
  studioFormStyles,
  studioEditorStyles,
  studioVisuallyHiddenStyles,
  studioWorkspaceStyles,
  css`
    :host {
      --studio-device-selector-max-width: 340px;
      --studio-device-selector-min-width: 180px;
      --studio-dialog-max-width: 440px;
      --studio-video-list-max-height: 150px;
      --studio-live-status-size: 18px;
      --studio-live-status-line-height: 16px;
      --studio-live-spin-duration: 700ms;
      --studio-live-reduced-motion-duration: 1400ms;
      --studio-light-on-ring-strength: 44%;
      --studio-light-on-hover-strength: 18%;
      --studio-light-off-foreground-strength: 72%;
      --studio-light-off-background-strength: 4%;
      --studio-dialog-shadow-offset: 18px;
      --studio-dialog-shadow-blur: 52px;
      display: flex;
      height: calc(100dvh - env(safe-area-inset-bottom, 0px));
      min-height: 0;
      overflow: hidden;
      flex-direction: column;
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      font-family: var(--paper-font-body1_-_font-family, sans-serif);
    }

    .panel-content {
      display: contents;
    }

    .centred,
    .fatal {
      max-width: var(--studio-empty-state-max-width);
      margin: 0 auto;
      padding: var(--studio-message-block-padding)
        var(--studio-message-inline-padding);
    }

    .fatal h1 {
      margin-top: 0;
    }

    .fatal a {
      color: var(--studio-blue);
      font-weight: var(--studio-font-weight-semibold);
    }

    h1,
    h2,
    h3,
    p {
      margin-top: 0;
    }

    h1 {
      margin-bottom: 0;
      font-size: var(--studio-page-heading-size);
      font-weight: var(--studio-font-weight-semibold);
    }

    h2 {
      margin-bottom: 0;
      font-size: var(--studio-heading-size);
      font-weight: var(--studio-font-weight-semibold);
    }

    h3 {
      margin-bottom: var(--studio-section-gap);
      font-size: var(--studio-section-title-size);
    }

    select {
      min-height: var(--studio-control-height);
      padding: var(--studio-option-padding);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-button-radius);
      color: var(--primary-text-color);
      background: var(--studio-card);
    }

    .home-assistant-header {
      display: flex;
      align-items: center;
      min-height: var(--studio-app-header-height);
      padding: 0 var(--studio-chrome-gutter);
      flex: 0 0 var(--studio-app-header-height);
      box-sizing: border-box;
      border-bottom: var(--app-header-border-bottom, none);
      color: var(--app-header-text-color, #fff);
      background: var(--app-header-background-color, var(--primary-color));
      font-size: var(--ha-font-size-l, 18px);
      font-weight: var(--ha-font-weight-normal, 400);
    }

    .home-assistant-menu {
      display: inline-grid;
      width: var(--studio-app-header-height);
      height: var(--studio-app-header-height);
      margin: 0 var(--studio-chrome-gutter) 0
        calc(0px - var(--studio-control-gap));
      padding: var(--studio-control-gap);
      border: 0;
      place-items: center;
      color: inherit;
      background: transparent;
      cursor: pointer;
    }

    .home-assistant-menu svg {
      width: var(--studio-icon-size);
      height: var(--studio-icon-size);
      fill: currentColor;
    }

    .home-assistant-menu:focus-visible {
      border-radius: var(--studio-round-radius);
      outline: var(--studio-strong-border-width) solid currentColor;
      outline-offset: calc(0px - var(--studio-micro-gap));
    }

    .studio-toolbar {
      position: sticky;
      z-index: var(--studio-z-toolbar);
      top: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--studio-action-gap);
      height: var(--studio-app-header-height);
      min-height: var(--studio-app-header-height);
      padding: var(--studio-tight-gap) var(--studio-section-gap);
      box-sizing: border-box;
      border-bottom: var(--studio-border-width) solid var(--studio-border);
      background: var(--primary-background-color, #fff);
      contain: style;
    }

    .device-selector {
      display: flex;
      align-items: center;
      gap: var(--studio-control-gap);
      min-width: 0;
      flex: 1 1 auto;
      color: var(--studio-muted);
      font-size: var(--studio-parameter-label-size);
      font-weight: var(--studio-font-weight-semibold);
    }

    .studio-toolbar-device {
      display: flex;
      min-width: 0;
      align-items: center;
      gap: var(--studio-micro-gap);
      flex: 1 1 auto;
    }

    .device-selector select {
      width: min(var(--studio-device-selector-max-width), 50vw);
      max-width: 100%;
      min-width: min(var(--studio-device-selector-min-width), 100%);
    }

    .live-apply-control {
      display: flex;
      align-items: center;
      gap: var(--studio-action-gap);
    }

    .toolbar-control {
      min-width: var(--studio-touch-target-size);
      height: var(--studio-touch-target-size);
      min-height: var(--studio-touch-target-size);
      box-sizing: border-box;
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-button-radius);
      color: var(--secondary-text-color);
      background: transparent;
    }

    .toolbar-mode-button {
      display: inline-grid;
      padding: var(--studio-micro-gap) var(--studio-control-gap);
      place-content: center;
      font: inherit;
      font-size: var(--studio-caption-size);
      font-weight: var(--studio-font-weight-semibold);
      line-height: var(--studio-label-line-height);
      cursor: pointer;
    }

    .toolbar-mode-button > span,
    .toolbar-mode-icon {
      display: block;
    }

    .toolbar-mode-icon {
      --mdc-icon-size: var(--studio-icon-size);
      display: inline-flex;
      width: var(--studio-icon-size);
      height: var(--studio-icon-size);
      align-items: center;
      justify-content: center;
      line-height: 0;
    }

    .toolbar-control:hover {
      color: var(--primary-text-color);
      background: color-mix(
        in srgb,
        var(--primary-text-color) 8%,
        transparent
      );
    }

    .toolbar-mode-button[aria-pressed="true"] {
      border-color: var(--studio-blue);
      color: var(--studio-blue);
      background: color-mix(in srgb, var(--studio-blue) 12%, transparent);
    }

    .toolbar-mode-button.pending {
      box-shadow: inset 0 0 0 var(--studio-border-width)
        var(--studio-blue);
    }

    .toolbar-control:focus-visible {
      outline: var(--studio-focus-width) solid var(--studio-blue);
      outline-offset: var(--studio-focus-offset);
    }

    .studio-toolbar-controls {
      display: flex;
      align-items: center;
      gap: var(--studio-micro-gap);
      flex: 0 0 auto;
      margin-inline-start: auto;
    }

    .light-control-button {
      display: inline-grid;
      width: var(--studio-touch-target-size);
      padding: var(--studio-compact-gap);
      place-items: center;
      cursor: pointer;
      text-decoration: none;
    }

    .light-control-button:focus-visible {
      color: var(--primary-text-color);
    }

    .light-control-button svg {
      width: var(--studio-icon-size);
      height: var(--studio-icon-size);
      fill: currentColor;
    }

    .native-light-brightness-ring {
      fill: currentColor;
    }

    .native-light-control.light-state-on {
      color: var(--studio-blue);
      background:
        linear-gradient(
          to top,
          color-mix(in srgb, var(--studio-blue) 38%, transparent)
            0 var(--native-light-fill),
          transparent var(--native-light-fill) 100%
        ),
        var(--studio-blue-soft);
      box-shadow: inset 0 0 0 var(--studio-border-width)
        color-mix(
          in srgb,
          var(--studio-blue) var(--studio-light-on-ring-strength),
          transparent
        );
    }

    .native-light-control.light-state-on:hover,
    .native-light-control.light-state-on:focus-visible {
      color: var(--studio-blue);
      background:
        linear-gradient(
          to top,
          color-mix(in srgb, var(--studio-blue) 48%, transparent)
            0 var(--native-light-fill),
          transparent var(--native-light-fill) 100%
        ),
        color-mix(
          in srgb,
          var(--studio-blue) var(--studio-light-on-hover-strength),
          transparent
        );
    }

    .native-light-control.light-state-off {
      color: color-mix(
        in srgb,
        var(--studio-muted) var(--studio-light-off-foreground-strength),
        transparent
      );
      background: color-mix(
        in srgb,
        var(--primary-text-color, #212121)
          var(--studio-light-off-background-strength),
        transparent
      );
    }

    .native-light-control.light-state-unavailable {
      color: var(--studio-muted);
      opacity: var(--studio-disabled-opacity);
    }

    .live-apply-status {
      position: relative;
      display: grid;
      width: var(--studio-live-status-size);
      height: var(--studio-live-status-size);
      flex: 0 0 var(--studio-live-status-size);
      place-items: center;
      border: var(--studio-strong-border-width) solid transparent;
      border-radius: var(--studio-round-radius);
    }

    .live-apply-status.idle {
      visibility: hidden;
    }

    .live-apply-status.pending {
      border-color: color-mix(
        in srgb,
        var(--studio-blue) 25%,
        transparent
      );
      border-top-color: var(--studio-blue);
      animation: live-apply-spin var(--studio-live-spin-duration) linear
        infinite;
    }

    .live-apply-status.warning {
      border-color: var(--error-color, #db4437);
    }

    .live-apply-status.warning::after {
      position: absolute;
      inset: calc(0px - var(--studio-border-width)) 0 0;
      color: var(--error-color, #db4437);
      content: "!";
      font-size: var(--studio-caption-size);
      font-weight: var(--studio-font-weight-alert);
      line-height: var(--studio-live-status-line-height);
      text-align: center;
    }

    @keyframes live-apply-spin {
      to {
        transform: rotate(360deg);
      }
    }

    .studio {
      display: grid;
      min-height: 0;
      overflow: hidden;
      flex: 1 1 auto;
      contain: style;
      grid-template-columns:
        var(--studio-navigation-width)
        var(--studio-list-width)
        minmax(0, 1fr);
    }

    .empty-state {
      max-width: var(--studio-empty-state-max-width);
      margin: 0 auto;
      padding: var(--studio-empty-state-block-padding)
        var(--studio-message-inline-padding);
    }

    .empty-state a {
      color: var(--studio-blue);
      font-weight: var(--studio-font-weight-semibold);
    }

    .studio.scenes-mode {
      grid-template-columns:
        var(--studio-navigation-width)
        var(--studio-list-width)
        minmax(0, 1fr);
    }

    .primary-nav {
      display: flex;
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
      scrollbar-gutter: stable;
      flex-direction: column;
      gap: var(--studio-tight-gap);
      padding: var(--studio-sidebar-padding);
      border-inline-end: var(--studio-border-width) solid var(--studio-border);
      background: var(--secondary-background-color, #f5f6f8);
      contain: layout paint style;
    }

    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: var(--studio-action-gap);
    }

    .mobile-name-label {
      display: none;
    }

    .actions > button {
      min-height: var(--studio-control-height);
    }

    .dialog-backdrop {
      position: fixed;
      z-index: var(--studio-z-modal);
      inset: 0;
      display: grid;
      place-items: center;
      overflow: auto;
      overscroll-behavior: contain;
      padding: var(--studio-dialog-padding);
      background: rgb(0 0 0 / 45%);
    }

    .dialog-card {
      width: min(var(--studio-dialog-max-width), 100%);
      max-height: calc(100vh - var(--studio-dialog-viewport-gutter));
      overflow: auto;
      padding: var(--studio-dialog-padding);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-dialog-radius);
      color: var(--primary-text-color);
      background: var(--studio-card);
      box-shadow: 0 var(--studio-dialog-shadow-offset)
        var(--studio-dialog-shadow-blur) rgb(0 0 0 / 28%);
    }

    .dialog-card p {
      margin-top: var(--studio-spacing-2xl);
      margin-bottom: 0;
      line-height: var(--studio-body-line-height);
    }

    .save-dialog .field,
    .transition-dialog .field {
      margin-top: var(--studio-spacing-4xl);
    }

    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--studio-action-gap);
      margin-top: var(--studio-dialog-padding);
    }

    .controls {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--studio-section-gap);
      margin-top: var(--studio-section-gap);
    }

    .single-effect-settings {
      margin-bottom: var(--studio-section-gap);
    }

    .single-effect-settings .field {
      margin-top: 0;
    }

    .opaque-content h3 {
      margin: 0 0 var(--studio-compact-gap);
    }

    .opaque-content h3:not(:first-child) {
      margin-top: var(--studio-spacing-4xl);
    }

    .opaque-content p {
      margin: 0;
    }

    .opaque-content pre {
      max-width: 100%;
      margin: 0;
      padding: var(--studio-spacing-2xl);
      overflow: auto;
      border-radius: var(--studio-control-radius);
      background: var(--secondary-background-color, #f1f1f1);
      color: var(--primary-text-color);
      font: var(--studio-caption-size) / var(--studio-body-line-height)
        ui-monospace, SFMono-Regular, Consolas, monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .paint-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--studio-control-gap);
      margin-top: var(--studio-field-margin);
    }

    .paint-off {
      display: inline-flex;
      align-items: center;
      gap: var(--studio-compact-gap);
      min-height: var(--studio-compact-control-height);
      padding: var(--studio-tight-gap) var(--studio-control-gap);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-button-radius);
      color: var(--primary-text-color);
      background: var(--studio-card);
      cursor: pointer;
    }

    .paint-off.active {
      border-color: color-mix(
        in srgb,
        var(--studio-blue) 58%,
        var(--studio-border)
      );
      box-shadow: inset 0 0 0 var(--studio-border-width)
        var(--studio-blue);
    }

    .paint-off-swatch {
      width: var(--studio-small-swatch-size);
      height: var(--studio-small-swatch-size);
      border: var(--studio-border-width) solid var(--studio-border);
      border-radius: var(--studio-round-radius);
      background: #000;
      box-shadow: inset 0 0 0 var(--studio-border-width)
        rgb(255 255 255 / 14%);
    }

    .read-only-copy {
      margin: 0 0 var(--studio-section-gap);
      line-height: var(--studio-muted-line-height);
    }

    .read-only-copy {
      color: var(--studio-muted);
    }

    /* Accommodates Home Assistant's docked sidebar on common 1024px and 1280px desktops. */
    @media (min-width: 901px) and (max-width: 1320px) {
      .studio.scenes-mode {
        flex-basis: 0;
        grid-template-rows: auto minmax(0, 1fr);
        grid-template-columns:
          var(--studio-stacked-navigation-width)
          minmax(0, 1fr);
      }

      .studio.custom-mode {
        flex-basis: 0;
        grid-template-rows: auto minmax(0, 1fr);
        grid-template-columns:
          var(--studio-stacked-navigation-width)
          minmax(0, 1fr);
      }

      .scenes-mode .primary-nav {
        grid-row: 1 / span 2;
      }

      .custom-mode .primary-nav {
        grid-row: 1 / span 2;
      }

      .scenes-mode > .editor {
        grid-row: 2;
        grid-column: 2;
      }

      .custom-mode > .editor {
        grid-row: 2;
        grid-column: 2;
      }

      .studio.video-mode {
        flex-basis: 0;
        grid-template-rows: auto minmax(0, 1fr);
        grid-template-columns:
          var(--studio-stacked-navigation-width)
          minmax(0, 1fr);
      }

      .video-mode .primary-nav {
        grid-row: 1 / span 2;
      }

      .video-mode .library {
        grid-row: 1;
        grid-column: 2;
        max-height: var(--studio-video-list-max-height);
        border-inline-end: 0;
        border-bottom: var(--studio-border-width) solid var(--studio-border);
      }

      .video-mode .editor {
        grid-row: 2;
        grid-column: 2;
      }
    }

    /* Switches from bounded panel grids to document-flow layout on narrow screens. */
    @media (max-width: 900px) {
      :host {
        height: auto;
        min-height: 100%;
        overflow: visible;
      }

      .studio {
        grid-template-columns:
          var(--studio-stacked-navigation-width)
          minmax(0, 1fr);
        min-height: 0;
        overflow: visible;
        flex: none;
      }

      .studio.scenes-mode,
      .studio.custom-mode {
        grid-template-columns:
          var(--studio-stacked-navigation-width)
          minmax(0, 1fr);
      }

      .custom-mode .library {
        grid-column: 2;
      }

      .video-mode .library {
        grid-column: 2;
      }

      .editor {
        grid-column: 2;
      }

      .controls {
        grid-template-columns: 1fr;
      }
    }

    /* Moves primary navigation into a horizontal row on phone and small tablet widths. */
    @media (max-width: 760px) {
      .studio {
        display: block;
      }

      .primary-nav {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        gap: var(--studio-tight-gap);
        overflow-x: auto;
        overscroll-behavior-x: contain;
        scrollbar-gutter: auto;
        padding: var(--studio-control-gap) var(--studio-chrome-gutter);
        border-inline-end: 0;
        border-bottom: var(--studio-border-width) solid var(--studio-border);
        scrollbar-width: none;
      }

      .primary-nav::-webkit-scrollbar {
        display: none;
      }

      .selector {
        width: auto;
        flex: 0 0 auto;
        text-align: center;
        white-space: nowrap;
      }

      .library {
        padding-block: var(--studio-section-gap);
      }

      .library .selector {
        text-align: start;
      }
    }

    /* Keeps device and entity controls on one phone row. */
    @media (max-width: 480px) {
      .studio-toolbar {
        height: var(--studio-app-header-height);
        min-height: var(--studio-app-header-height);
        align-items: center;
        flex-direction: row;
        gap: var(--studio-micro-gap);
        padding: var(--studio-tight-gap) var(--studio-compact-gap);
      }

      .device-selector {
        min-width: 0;
        flex: 1 1 auto;
      }

      .device-selector select {
        width: 100%;
        min-width: 0;
        min-height: var(--studio-control-height);
        padding-inline: var(--studio-compact-gap);
      }

      .studio-toolbar-controls {
        min-width: 0;
        flex: 0 0 auto;
        align-self: center;
      }

      .live-apply-control {
        gap: var(--studio-micro-gap);
      }

      .editor {
        display: flex;
        flex-direction: column;
      }

      .editor > .editor-heading {
        display: contents;
      }

      .editor > .editor-heading > .actions {
        order: 100;
        margin-top: var(--studio-section-gap);
      }

      .editor > .editor-heading > .editor-heading-title {
        order: -1;
      }

      .editor .mobile-editable-heading {
        margin-top: var(--studio-section-gap);
      }

      .editor .mobile-name-label {
        display: block;
        color: var(--studio-muted);
        font-size: var(--studio-parameter-label-size);
        font-weight: var(--studio-parameter-label-weight);
      }

      .mobile-redundant-heading {
        display: none;
      }

      .button-row {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
      }

      .button-row button:first-child {
        grid-column: 1 / -1;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      * {
        scroll-behavior: auto !important;
      }

      .live-apply-status.pending {
        animation-duration: var(--studio-live-reduced-motion-duration);
      }

    }
  `,
];
