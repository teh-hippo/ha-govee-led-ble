/**
 * Minimal type surface for the vendored lit ESM bundle (`lit.js`).
 *
 * Only the exports the card actually uses are declared. The runtime bundle is
 * copied verbatim from the proven no-build vendored-lit pattern in
 * `ha-ux-lab/www/vendor/lit.js`; `bun build` inlines it so the Home Assistant
 * runtime needs no npm packages.
 */

export interface PropertyDeclaration {
  readonly attribute?: boolean | string;
  readonly state?: boolean;
  readonly reflect?: boolean;
  readonly type?: unknown;
}

export class CSSResult {
  readonly cssText: string;
  toString(): string;
}

export type CSSResultGroup = CSSResult | CSSResultArray;
interface CSSResultArray extends Array<CSSResultGroup> {}

export interface TemplateResult {
  readonly _$litType$: unknown;
}

export const nothing: unique symbol;
export const noChange: unique symbol;

export function html(strings: TemplateStringsArray, ...values: unknown[]): TemplateResult;
export function svg(strings: TemplateStringsArray, ...values: unknown[]): TemplateResult;
export function css(strings: TemplateStringsArray, ...values: unknown[]): CSSResult;
export function unsafeCSS(value: unknown): CSSResult;

export class LitElement extends HTMLElement {
  static properties?: Record<string, PropertyDeclaration>;
  static styles?: CSSResultGroup;
  static shadowRootOptions?: ShadowRootInit;
  readonly renderRoot: HTMLElement | ShadowRoot;
  readonly updateComplete: Promise<boolean>;
  protected createRenderRoot(): HTMLElement | ShadowRoot;
  protected render(): unknown;
  protected firstUpdated(changed: Map<PropertyKey, unknown>): void;
  protected updated(changed: Map<PropertyKey, unknown>): void;
  requestUpdate(name?: PropertyKey, oldValue?: unknown): void;
  connectedCallback(): void;
  disconnectedCallback(): void;
}
