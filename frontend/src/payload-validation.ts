import type { CapabilityState } from "./types";

const MAX_JSON_DEPTH = 16;
const MAX_JSON_NODES = 4096;
export const MAX_JSON_COLLECTION_ITEMS = 1024;
const MAX_JSON_STRING_LENGTH = 16_384;

export const MAX_SAFE_REVISION = Number.MAX_SAFE_INTEGER;

export function boundedString(
  value: unknown,
  name: string,
  maximum: number,
): string {
  const text = stringValue(value, name);
  if (text.length === 0 || text.length > maximum) {
    invalid(`${name} must contain 1 to ${maximum} characters`);
  }
  return text;
}

export function boundedStringAllowEmpty(
  value: unknown,
  name: string,
  maximum: number,
): string {
  const text = stringValue(value, name);
  if (text.length > maximum) {
    invalid(`${name} must not exceed ${maximum} characters`);
  }
  return text;
}

export function hexString(value: unknown, name: string): string {
  const text = stringValue(value, name);
  if (text.length % 2 !== 0 || !/^[0-9a-f]*$/i.test(text)) {
    invalid(`${name} must be hexadecimal`);
  }
  return text;
}

export function stringValue(value: unknown, name: string): string {
  if (typeof value !== "string") {
    invalid(`${name} must be a string`);
  }
  return value;
}

export function booleanValue(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") {
    invalid(`${name} must be a boolean`);
  }
  return value;
}

export function capabilityValue(
  value: unknown,
  name: string,
): CapabilityState {
  if (
    value !== "supported" &&
    value !== "unsupported" &&
    value !== "evidence_gap"
  ) {
    invalid(`${name} is invalid`);
  }
  return value;
}

export function integerValue(
  value: unknown,
  name: string,
  minimum: number,
  maximum = MAX_SAFE_REVISION,
): number {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    invalid(`${name} must be an integer from ${minimum} to ${maximum}`);
  }
  return value;
}

export function exactInteger(
  value: unknown,
  expected: number,
  name: string,
): number {
  const actual = integerValue(value, name, 1);
  if (actual !== expected) {
    invalid(`${name} is incompatible with this editor`);
  }
  return actual;
}

export function nullableInteger(
  value: unknown,
  name: string,
  minimum: number,
  maximum: number,
): number | null {
  return value === null
    ? null
    : integerValue(value, name, minimum, maximum);
}

export function byteValue(value: unknown, name: string): number {
  return integerValue(value, name, 0, 255);
}

export function enumString<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  name: string,
): Values[number] {
  const text = stringValue(value, name);
  if (!values.includes(text)) {
    invalid(`${name} is invalid`);
  }
  return text;
}

export function objectValue(
  value: unknown,
  name: string,
): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    invalid(`${name} must be an object`);
  }
  return value as Record<string, unknown>;
}

export function arrayValue(
  value: unknown,
  name: string,
  maximum: number,
): unknown[] {
  if (!Array.isArray(value)) {
    invalid(`${name} must be an array`);
  }
  if (value.length > maximum) {
    invalid(`${name} must not exceed ${maximum} items`);
  }
  return value;
}

export function requireUnique<Item>(
  items: Item[],
  key: (item: Item) => string,
  name: string,
): void {
  const keys = items.map(key);
  if (new Set(keys).size !== keys.length) {
    invalid(`${name} must be unique`);
  }
}

export function assertBoundedJson(
  value: unknown,
  name: string,
  maximumBytes: number,
  maximumNodes = MAX_JSON_NODES,
): void {
  let nodes = 0;
  const visit = (item: unknown, path: string, depth: number): void => {
    nodes += 1;
    if (nodes > maximumNodes) {
      invalid(`${name} must not exceed ${maximumNodes} JSON values`);
    }
    if (depth > MAX_JSON_DEPTH) {
      invalid(`${name} must not exceed ${MAX_JSON_DEPTH} nested levels`);
    }
    if (item === null || typeof item === "boolean") {
      return;
    }
    if (typeof item === "number") {
      if (
        !Number.isFinite(item) ||
        (Number.isInteger(item) && !Number.isSafeInteger(item))
      ) {
        invalid(`${path} must be a finite JSON number`);
      }
      return;
    }
    if (typeof item === "string") {
      if (item.length > MAX_JSON_STRING_LENGTH) {
        invalid(
          `${path} must not exceed ${MAX_JSON_STRING_LENGTH} characters`,
        );
      }
      return;
    }
    if (Array.isArray(item)) {
      if (item.length > MAX_JSON_COLLECTION_ITEMS) {
        invalid(`${path} must not exceed ${MAX_JSON_COLLECTION_ITEMS} items`);
      }
      item.forEach((nested, index) =>
        visit(nested, `${path}[${index}]`, depth + 1),
      );
      return;
    }
    if (typeof item === "object" && item !== null) {
      const entries = Object.entries(item);
      if (entries.length > MAX_JSON_COLLECTION_ITEMS) {
        invalid(`${path} must not exceed ${MAX_JSON_COLLECTION_ITEMS} fields`);
      }
      entries.forEach(([key, nested]) => {
        if (key.length > MAX_JSON_STRING_LENGTH) {
          invalid(`${path} contains an oversized key`);
        }
        visit(nested, `${path}.${key}`, depth + 1);
      });
      return;
    }
    invalid(`${path} contains a non-JSON value`);
  };
  visit(value, name, 0);
  const encoded = JSON.stringify(value);
  if (encoded === undefined) {
    invalid(`${name} must contain JSON values`);
  }
  if (new TextEncoder().encode(encoded).byteLength > maximumBytes) {
    invalid(`${name} must not exceed ${maximumBytes} bytes`);
  }
}

export function invalid(message: string): never {
  throw new Error(`Malformed Effect Studio server payload: ${message}.`);
}
