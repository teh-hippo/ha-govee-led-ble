import { LitElement, css, html } from "lit";

import {
  blankAdvancedContent,
  type GoveeAdvancedEffectEditor,
} from "../../../src/advanced-effect-editor";
import {
  blankLayer,
  withAppliedAreaSegments,
} from "../../../src/advanced-effect-model";
import type { GoveeAppliedAreaControl } from "../../../src/applied-area-control";
import type { GoveeColourPicker } from "../../../src/colour-picker";
import type { GoveeCustomEffectEditor } from "../../../src/custom-effect-editor";
import type { PaintedSegmentDraft } from "../../../src/effect-editor-model";
import type { GoveeInfoControl } from "../../../src/info-control";
import type { GoveePaletteEditor } from "../../../src/palette-editor";
import type { GoveePaintedSegmentEditor } from "../../../src/painted-segment-editor";
import { studioTokenStyles } from "../../../src/studio-styles";
import type {
  AdvancedContent,
  EffectLayer,
  ModelEffectCatalogue,
  MultiContent,
  PaletteDiyEffectContent,
  RGB,
} from "../../../src/types";
import { clonePalette } from "../../../src/ui-utils";
import "../../../src/advanced-effect-editor";
import "../../../src/applied-area-control";
import "../../../src/colour-picker";
import "../../../src/custom-effect-editor";
import "../../../src/info-control";
import "../../../src/palette-editor";
import "../../../src/painted-segment-editor";

const INITIAL_PALETTE: RGB[] = [
  [255, 0, 0],
  [0, 255, 0],
  [0, 0, 255],
];

const CATALOGUE: ModelEffectCatalogue = {
  sku: "H6199",
  painted_effects: [],
  effects: [
    {
      id: "flow",
      label: "Flow",
      family: 1,
      variations: [
        {
          id: "flow-base",
          label: "Base",
          variant: 0,
        },
      ],
      supports_multi: false,
      rate: "speed",
      category: "single_layer",
    },
    {
      id: "chase",
      label: "Chase",
      family: 2,
      variations: [
        {
          id: "chase-base",
          label: "Base",
          variant: 0,
        },
      ],
      supports_multi: true,
      rate: "speed",
      category: "single_layer",
    },
    {
      id: "twinkle",
      label: "Twinkle",
      family: 3,
      variations: [
        {
          id: "twinkle-base",
          label: "Base",
          variant: 0,
        },
      ],
      supports_multi: true,
      rate: "speed",
      category: "single_layer",
    },
    {
      id: "breathe",
      label: "Breathe",
      family: 4,
      variations: [
        {
          id: "breathe-base",
          label: "Base",
          variant: 0,
        },
      ],
      supports_multi: true,
      rate: "speed",
      category: "single_layer",
    },
  ],
  music_modes: [],
  video_modes: [],
  workshop_templates: [],
  workflows: [],
  supports: {
    multi: "supported",
    advanced: "supported",
    workshop: "unsupported",
  },
  limits: {
    palette_min: 1,
    palette_max: 8,
    multi_max: 5,
    music_sensitivity_min: 0,
    music_sensitivity_max: 100,
  },
  apply: {
    painted: "unsupported",
    single: "unsupported",
    multi: "supported",
    palette_diy: "supported",
    workshop: "unsupported",
  },
};

export class GoveePaletteBrowserFixture extends LitElement {
  private directPalette = clonePalette(INITIAL_PALETTE);
  private customContent: PaletteDiyEffectContent = {
    kind: "palette_diy",
    model: "H6199",
    family: 1,
    variant: 0,
    speed: 50,
    palette: clonePalette(INITIAL_PALETTE),
  };
  private advancedContent = blankAdvancedContent();
  private multiContent: MultiContent = {
    kind: "h617a_multi",
    effects: [
      { family: 2, variant: 0 },
      { family: 3, variant: 0 },
      { family: 4, variant: 0 },
    ],
    speed: 50,
    palette: clonePalette(INITIAL_PALETTE),
  };
  private paintedSegments: PaintedSegmentDraft[] = Array.from(
    { length: 15 },
    () => null,
  );
  private paintedEvents: Array<{
    index: number;
    interaction: string;
  }> = [];
  private areaLayer = withAppliedAreaSegments(blankLayer(), 2, 10, 15);
  private areaEvents: string[] = [];
  private colourEvents: Array<{
    colour: RGB;
    type: string;
  }> = [];

  protected render() {
    return html`
      <main>
        <button data-testid="outside" type="button">Outside control</button>

        <section data-testid="direct-context">
          <h1>Direct palette</h1>
          <govee-palette-editor
            .palette=${this.directPalette}
            .minColours=${1}
            .maxColours=${8}
            @palette-changed=${this.directPaletteChanged}
          ></govee-palette-editor>
        </section>

        <section data-testid="custom-context">
          <h1>Custom effect palette</h1>
          <govee-custom-effect-editor
            .content=${this.customContent}
            .catalogue=${CATALOGUE}
            @content-changed=${this.customContentChanged}
          ></govee-custom-effect-editor>
        </section>

        <section data-testid="advanced-context">
          <h1>Advanced layer palette</h1>
          <govee-advanced-effect-editor
            .content=${this.advancedContent}
            @content-changed=${this.advancedContentChanged}
          ></govee-advanced-effect-editor>
        </section>

        <section data-testid="multi-context">
          <h1>Multi-effect sequence</h1>
          <govee-custom-effect-editor
            .content=${this.multiContent}
            .catalogue=${CATALOGUE}
            @content-changed=${this.multiContentChanged}
          ></govee-custom-effect-editor>
          <output data-testid="multi-order"
            >${JSON.stringify(
              this.multiContent.effects.map((effect) => effect.family),
            )}</output
          >
        </section>

        <section data-testid="painted-context">
          <h1>Painted segments</h1>
          <govee-painted-segment-editor
            .segments=${this.paintedSegments}
            @segment-selected=${this.segmentSelected}
          ></govee-painted-segment-editor>
          <output data-testid="painted-events"
            >${JSON.stringify(this.paintedEvents)}</output
          >
        </section>

        <section data-testid="area-context">
          <h1>Applied area</h1>
          <govee-applied-area-control
            .layer=${this.areaLayer}
            .segmentCount=${15}
            @area-changed=${this.areaChanged}
          ></govee-applied-area-control>
          <output data-testid="area-events"
            >${JSON.stringify(this.areaEvents)}</output
          >
        </section>

        <section data-testid="colour-context">
          <h1>Native colour input</h1>
          <govee-colour-picker
            .colour=${[255, 255, 255] satisfies RGB}
            @colour-changing=${this.colourChanged}
            @colour-changed=${this.colourChanged}
          ></govee-colour-picker>
          <output data-testid="colour-events"
            >${JSON.stringify(this.colourEvents)}</output
          >
        </section>

        <section data-testid="info-context">
          <h1>Information popover</h1>
          <govee-info-control
            label="WebKit information"
            text="A positioned information popover."
          ></govee-info-control>
        </section>
      </main>
    `;
  }

  private readonly directPaletteChanged = (
    event: CustomEvent<{ palette: RGB[] }>,
  ): void => {
    this.directPalette = clonePalette(event.detail.palette);
    this.requestUpdate();
  };

  private readonly customContentChanged = (
    event: CustomEvent<{ content: PaletteDiyEffectContent }>,
  ): void => {
    this.customContent = {
      ...event.detail.content,
      palette: clonePalette(event.detail.content.palette),
    };
    this.requestUpdate();
  };

  private readonly advancedContentChanged = (
    event: CustomEvent<{ content: AdvancedContent }>,
  ): void => {
    this.advancedContent = event.detail.content;
    this.requestUpdate();
  };

  private readonly multiContentChanged = (
    event: CustomEvent<{ content: MultiContent }>,
  ): void => {
    this.multiContent = {
      ...event.detail.content,
      effects: event.detail.content.effects.map((effect) => ({ ...effect })),
      palette: clonePalette(event.detail.content.palette),
    };
    this.requestUpdate();
  };

  private readonly segmentSelected = (
    event: CustomEvent<{ index: number; interaction: string }>,
  ): void => {
    this.paintedEvents = [...this.paintedEvents, { ...event.detail }];
    if (event.detail.interaction === "changing") {
      this.paintedSegments = this.paintedSegments.map((segment, index) =>
        index === event.detail.index ? [12, 34, 56] : segment,
      );
    }
    this.requestUpdate();
  };

  private readonly areaChanged = (
    event: CustomEvent<{ layer: EffectLayer; interaction: string }>,
  ): void => {
    this.areaLayer = event.detail.layer;
    this.areaEvents = [...this.areaEvents, event.detail.interaction];
    this.requestUpdate();
  };

  private readonly colourChanged = (
    event: CustomEvent<{ colour: RGB }>,
  ): void => {
    this.colourEvents = [
      ...this.colourEvents,
      {
        colour: [...event.detail.colour],
        type: event.type,
      },
    ];
    this.requestUpdate();
  };

  static styles = [
    studioTokenStyles,
    css`
      :host {
        display: block;
        color: #202124;
        background: #f5f5f5;
        font-family: sans-serif;
      }

      main {
        display: grid;
        gap: var(--studio-section-gap);
        min-height: 1600px;
        padding: var(--studio-editor-padding);
      }

      section {
        min-width: 0;
        padding: var(--studio-card-padding);
        border: var(--studio-border-width) solid var(--studio-border);
        border-radius: var(--studio-card-radius);
        background: var(--studio-card);
      }

      h1 {
        margin: 0 0 var(--studio-section-gap);
        font-size: var(--studio-heading-size);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "govee-advanced-effect-editor": GoveeAdvancedEffectEditor;
    "govee-applied-area-control": GoveeAppliedAreaControl;
    "govee-colour-picker": GoveeColourPicker;
    "govee-custom-effect-editor": GoveeCustomEffectEditor;
    "govee-info-control": GoveeInfoControl;
    "govee-palette-browser-fixture": GoveePaletteBrowserFixture;
    "govee-palette-editor": GoveePaletteEditor;
    "govee-painted-segment-editor": GoveePaintedSegmentEditor;
  }
}

if (!customElements.get("govee-palette-browser-fixture")) {
  customElements.define(
    "govee-palette-browser-fixture",
    GoveePaletteBrowserFixture,
  );
}
