import { css } from "../vendor/lit.js";

/** Styles for the main segment-painter card. */
export const cardStyles = css`
    ha-card {
      overflow: hidden;
    }
    .body {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 16px;
    }
    .notice {
      padding: 16px;
      color: var(--secondary-text-color);
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .heading {
      justify-content: space-between;
    }
    .label {
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .hint {
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Painter strip */
    .strip {
      display: grid;
      gap: 3px;
      padding: 4px;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--divider-color);
      touch-action: pan-x pan-y;
      user-select: none;
      outline: none;
    }
    .strip:focus-visible {
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .cell {
      position: relative;
      aspect-ratio: 1 / 1.6;
      border-radius: 6px;
      background: var(--card-background-color);
      cursor: pointer;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      transition: transform 0.05s ease;
    }
    .cell.off {
      background: var(--card-background-color);
      border: 1px dashed var(--secondary-text-color);
      opacity: 0.5;
    }
    .cell .cell-num {
      font-size: 9px;
      line-height: 1.2;
      font-weight: 600;
      padding: 1px 4px;
      margin-bottom: 2px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.4);
      color: #fff;
      pointer-events: none;
    }
    .cell.off .cell-num,
    .cell.unchanged .cell-num {
      background: var(--card-background-color);
      color: var(--secondary-text-color);
    }
    .cell.sel {
      outline: 3px solid var(--primary-color);
      outline-offset: -1px;
      transform: translateY(-2px);
    }
    .cell.cursor::after {
      content: "";
      position: absolute;
      inset: -3px;
      border-radius: 8px;
      border: 2px dashed var(--primary-text-color);
      pointer-events: none;
    }
    /* Gradient */
    .gradient-bar {
      position: relative;
      height: 34px;
      border-radius: 17px;
      border: 1px solid var(--divider-color);
    }
    .handle {
      position: absolute;
      top: 50%;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      border: 2px solid var(--card-background-color);
      box-shadow: 0 0 0 1px var(--divider-color);
      cursor: grab;
      touch-action: none;
    }
    .handle.dragging {
      cursor: grabbing;
      transform: translate(-50%, -50%) scale(1.25);
    }
    .stops {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .stop {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
    }
    /* Presets */
    .presets {
      gap: 8px;
    }
    .preset {
      display: inline-flex;
      flex-direction: column;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      cursor: pointer;
      font: inherit;
    }
    .preset:hover {
      border-color: var(--primary-color);
    }
    .preset .swatch {
      width: 64px;
      height: 22px;
      border-radius: 6px;
      border: 1px solid var(--divider-color);
    }
    .preset .preset-name {
      font-size: 0.8em;
      text-align: center;
      color: var(--secondary-text-color);
    }
    /* Preview */
    canvas.preview {
      width: 100%;
      height: 44px;
      display: block;
      border-radius: 8px;
      background: var(--card-background-color);
    }
    /* Controls */
    .btn {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .btn:hover {
      border-color: var(--primary-color);
    }
    .btn.primary {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .btn.tiny {
      border-radius: 50%;
      width: 26px;
      height: 26px;
      padding: 0;
      line-height: 1;
    }
    .btn[disabled] {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .btn.primary[disabled] {
      opacity: 1;
      background: var(--disabled-color, var(--divider-color));
      color: var(--disabled-text-color, var(--secondary-text-color));
      border-color: var(--divider-color);
      cursor: not-allowed;
    }
    input[type="color"] {
      width: 42px;
      height: 30px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color);
      padding: 2px;
      cursor: pointer;
    }
    input[type="text"] {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 10px;
      font: inherit;
    }
    input[type="text"]:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    textarea {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 10px;
      font: 0.85em/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
      resize: vertical;
    }
    textarea:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .effect-name {
      flex: 1 1 12ch;
      min-width: 12ch;
    }
    .edit-band {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid var(--primary-color);
      border-radius: 8px;
      color: var(--primary-text-color);
      background: var(--secondary-background-color);
      font-size: 0.85em;
    }
    .pending-author {
      padding: 12px;
      border: 1px dashed var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .import-panel {
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      overflow: hidden;
    }
    .import-panel summary {
      padding: 10px 12px;
      color: var(--primary-text-color);
      font-weight: 600;
      cursor: pointer;
    }
    .import-panel[open] summary {
      border-bottom: 1px solid var(--divider-color);
    }
    .import-body {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 12px;
    }
    .import-json {
      min-height: 130px;
    }
    .import-file {
      display: none;
    }
    /* Custom effects */
    .help {
      margin: 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .feedback {
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.9em;
      border: 1px solid var(--divider-color);
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
    }
    .feedback.error {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .feedback.info {
      border-color: var(--success-color, var(--primary-color));
    }
    .draft-confirm {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--warning-color, #f9a825);
      border-radius: 8px;
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      font-size: 0.9em;
    }
    .effects {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .effect {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .effect-main {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1 1 220px;
      min-width: 0;
    }
    .effect-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 6px;
      flex: 1 1 auto;
      flex-wrap: wrap;
    }
    .effect-more summary {
      list-style: none;
    }
    .effect-more summary::-webkit-details-marker {
      display: none;
    }
    .effect-more[open] {
      flex-basis: 100%;
    }
    .more-actions {
      display: flex;
      justify-content: flex-end;
      gap: 6px;
      margin-top: 6px;
      flex-wrap: wrap;
    }
    .effect-label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    /* Studio shell: header, status band, tabs */
    .card-head {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px 16px 0;
    }
    .title {
      font-size: 1.15em;
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .status {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--secondary-text-color);
      font-size: 0.9em;
      min-width: 0;
    }
    .status .current {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    .tabs {
      display: flex;
      gap: 4px;
      background: var(--divider-color);
      border-radius: 22px;
      padding: 4px;
    }
    .tab {
      flex: 1 1 0;
      border: none;
      background: transparent;
      color: var(--secondary-text-color);
      border-radius: 18px;
      padding: 8px 12px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .tab:hover {
      color: var(--primary-text-color);
    }
    .tab.active {
      background: var(--card-background-color);
      color: var(--primary-text-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
    }
    .tab:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: kind pill picker */
    .kinds {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .kind {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .kind:hover {
      border-color: var(--primary-color);
    }
    .kind.active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .kind.soon,
    .kind:disabled {
      opacity: 1;
      border-style: dashed;
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
      cursor: default;
    }
    .kind.soon:hover,
    .kind:disabled:hover {
      border-color: var(--divider-color);
    }
    .kind .soon-tag {
      font-size: 0.7em;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      background: var(--divider-color);
      color: var(--secondary-text-color);
      border-radius: 8px;
      padding: 1px 6px;
      margin-left: 6px;
    }
    .kind:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: unchanged (leave-as-is) segment cells */
    .cell.unchanged {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          var(--divider-color) 5px,
          var(--divider-color) 6px
        ),
        var(--card-background-color);
      border: 1px solid var(--divider-color);
    }
    .cell.background {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          rgba(255, 255, 255, 0.24) 5px,
          rgba(255, 255, 255, 0.24) 6px
        ),
        var(--cell-background);
      border: 1px solid var(--divider-color);
    }
    .colour-control {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .motion-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .motion {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      padding: 9px 10px;
      font: inherit;
      cursor: pointer;
    }
    .motion:hover {
      border-color: var(--primary-color);
    }
    .motion.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .motion:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .range-row {
      display: grid;
      grid-template-columns: minmax(80px, auto) minmax(120px, 1fr) 4ch;
      align-items: center;
      gap: 10px;
      color: var(--primary-text-color);
    }
    .range-row input[type="range"] {
      width: 100%;
      accent-color: var(--primary-color);
    }
    .range-row output {
      text-align: right;
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
    }
    .preview-badge {
      color: var(--secondary-text-color);
      font-size: 0.78em;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      padding: 2px 7px;
    }
    .family-grid,
    .variant-grid {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
    }
    .family,
    .variant {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 7px 12px;
      font: inherit;
      cursor: pointer;
    }
    .family:hover,
    .variant:hover {
      border-color: var(--primary-color);
    }
    .family.active,
    .variant.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .family:focus-visible,
    .variant:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .palette-editor {
      display: flex;
      align-items: stretch;
      gap: 8px;
      flex-wrap: wrap;
    }
    .palette-chip {
      display: grid;
      grid-template-columns: auto auto auto;
      align-items: center;
      gap: 4px;
      padding: 5px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .palette-chip input[type="color"] {
      grid-column: 1 / -1;
      width: 100%;
    }
    .palette-number {
      color: var(--secondary-text-color);
      font-size: 0.8em;
      font-variant-numeric: tabular-nums;
    }
    .palette-chip .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .palette-add {
      min-height: 76px;
      border-style: dashed;
    }
    .combo-chain {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .combo-step {
      display: grid;
      grid-template-columns: auto minmax(100px, 1fr) minmax(120px, 1fr);
      align-items: center;
      gap: 8px;
      padding: 8px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .combo-number {
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .combo-step select {
      width: 100%;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 9px;
      font: inherit;
    }
    .combo-step select:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .combo-actions {
      display: flex;
      gap: 4px;
      grid-column: 2 / -1;
      justify-content: flex-end;
    }
    .combo-actions .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    /* Studio: "coming next" caption row of disabled kinds */
    .kinds-soon {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Scope band: does this workspace touch the strip? */
    .scope-band {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.85em;
      font-weight: 600;
      background: var(--secondary-background-color);
    }
    .scope-band.live {
      border-left: 3px solid var(--primary-color);
      color: var(--primary-text-color);
    }
    .scope-band.draft {
      border-left: 3px solid var(--secondary-text-color);
      color: var(--secondary-text-color);
    }
    .scope-band .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      flex: 0 0 auto;
    }
    .scope-band.live .dot {
      background: var(--primary-color);
    }
    .scope-band.draft .dot {
      border: 2px solid var(--secondary-text-color);
    }
    /* Horizontal scroll guard for the 15-cell strip on narrow cards */
    .strip-scroll {
      position: relative;
      overflow-x: auto;
    }
    .strip-scroll .strip {
      min-width: 336px;
    }
    .strip-scroll::after {
      content: "›";
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 34px;
      pointer-events: none;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      padding-right: 3px;
      box-sizing: border-box;
      color: var(--primary-color);
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(
        to left,
        var(--card-background-color) 35%,
        transparent
      );
      opacity: 0;
      transition: opacity 0.15s ease;
    }
    .strip-scroll.clipped::after {
      opacity: 1;
    }
    /* Non-interactive resolved preview strip */
    .strip.preview-strip {
      pointer-events: none;
    }
    /* Gradient track padding so end handles never clip */
    .gradient-track {
      padding: 0 12px;
    }
    /* Library: active row + inline delete confirm */
    .effect .badge-active {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      font-weight: 600;
      background: transparent;
      color: var(--primary-color);
      border: 1px solid var(--primary-color);
      cursor: default;
    }
    .effect.active {
      border-left: 3px solid var(--primary-color);
      padding-left: 8px;
      border-radius: 4px;
    }
    .effect .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .effect .btn.danger.primary {
      background: var(--error-color);
      color: var(--text-primary-color, #fff);
    }
    .effect .confirm-text {
      flex: 1 1 auto;
      min-width: 0;
      color: var(--primary-text-color);
      font-size: 0.9em;
    }
    @media (max-width: 360px) {
      .cell .cell-num {
        display: none;
      }
      .motion-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .range-row {
        grid-template-columns: 1fr 4ch;
      }
      .range-row > span {
        grid-column: 1 / -1;
      }
    }
`;
