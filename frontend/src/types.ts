/** Shared types for the govee-led-ble-card modules. */

export interface HassServiceTarget {
  entity_id?: string | string[];
  device_id?: string | string[];
  area_id?: string | string[];
}

export interface HassEntityState {
  state: string;
  attributes: Record<string, unknown>;
}

export interface HassServiceResponse<T> {
  response?: T;
}

export interface HassEntityRegistryEntry {
  device_id?: string | null;
}

export interface HassDeviceRegistryEntry {
  model?: string | null;
}

export interface HassLike {
  states: Record<string, HassEntityState>;
  entities?: Record<string, HassEntityRegistryEntry>;
  devices?: Record<string, HassDeviceRegistryEntry>;
  callService<T = unknown>(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
    target?: HassServiceTarget,
    notifyOnError?: boolean,
    returnResponse?: boolean,
  ): Promise<HassServiceResponse<T>>;
}

export interface GoveeLedBleCardConfig {
  type?: string;
  entity?: string;
}

export interface CustomCard {
  type: string;
  name: string;
  description?: string;
  preview?: boolean;
}

declare global {
  interface Window {
    customCards?: CustomCard[];
  }
}
