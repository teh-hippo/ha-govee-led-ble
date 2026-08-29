import { describe, expect, test, vi } from "vitest";

import backendContracts from "../fixtures/backend-contracts.json";
import { EffectStudioApi } from "../../src/api";
import {
  decodeCustomCatalogue,
  decodeDevices,
  decodeEditorApiInfo,
  decodeEffectContent,
  decodeEffectUserState,
  decodeLibraryItem,
  decodeLibrarySnapshot,
  decodePreviewStatus,
  decodeSceneCatalogue,
  decodeSceneDetail,
  decodeSceneSummary,
  effectContentToWire,
  isCompatibleEditorInfo,
} from "../../src/validation";
import type { HomeAssistant } from "../../src/types";

type JsonObject = Record<string, unknown>;

const responses = backendContracts.responses;
const contentSamples: Record<string, unknown> = backendContracts.content_samples;
const knownContentFamilies = [
  "h617a_painted",
  "h617a_single",
  "h617a_multi",
  "palette_diy",
  "music_profile",
  "video_profile",
  "advanced",
  "workshop",
  "scene_builtin",
  "scene_palette",
  "scene_layered",
] as const;

function cloneObject(value: unknown): JsonObject {
  return structuredClone(value) as JsonObject;
}

function objectArray(value: unknown): JsonObject[] {
  return value as JsonObject[];
}

test("canonical backend responses decode through the production validators", () => {
  const info = decodeEditorApiInfo(responses.editor_info);
  expect(isCompatibleEditorInfo(info)).toBe(true);
  const devices = decodeDevices(responses.devices);
  expect(devices.map((device) => device.model)).toEqual([
    "H6125",
    "H617A",
    "H617E",
    "H6199",
  ]);
  expect(devices[0].light_entity_id).toBeNull();
  expect(devices[1].light_entity_id).toBe("light.h617a_main");
  expect(devices[1].active_state?.active_effect?.observable_signature).toBe(
    "custom:800",
  );
  expect(decodeCustomCatalogue(responses.custom_catalogue).models).toHaveProperty(
    "H6199",
  );
  expect(decodeLibrarySnapshot(responses.library_snapshot).items).toHaveLength(
    2,
  );
  expect(decodeLibraryItem(responses.library_item).content.kind).toBe(
    "h617a_painted",
  );
  expect(decodePreviewStatus(responses.preview_status).phase).toBe("confirmed");
  expect(
    decodeEffectUserState({
      owner_id: "user-a",
      recent_colours: [[1, 2, 3]],
      selected_config_entry_id: "entry-a",
      navigation: { section: "scenes" },
    }),
  ).toEqual({
    owner_id: "user-a",
    recent_colours: [[1, 2, 3]],
    selected_config_entry_id: "entry-a",
    navigation: { section: "scenes" },
  });

  for (const catalogue of Object.values(responses.scene_catalogues)) {
    const decoded = decodeSceneCatalogue(catalogue);
    expect(decoded.scenes.length).toBeGreaterThan(0);
    expect(decodeSceneSummary(decoded.scenes[0])).toEqual(decoded.scenes[0]);
  }
  for (const detail of Object.values(responses.scene_details)) {
    const decoded = decodeSceneDetail(detail);
    expect(decoded.scene.display_name).not.toBe("");
    expect(typeof decoded.has_default).toBe("boolean");
  }
});

test("snapshot previews pass catalogue provenance through the API boundary", async () => {
  const callWS = vi.fn().mockResolvedValue(undefined);
  const api = new EffectStudioApi({
    callWS,
    callService: vi.fn(),
    connection: {
      subscribeMessage: vi.fn(),
    },
  } as unknown as HomeAssistant);

  await api.previewSnapshot(
    "session-a",
    1,
    "entry-a",
    "Flow",
    decodeEffectContent(contentSamples.h617a_painted),
    false,
    {
      origin_kind: "catalogue_template",
      origin_id: "template:single:1:0",
    },
  );

  expect(callWS).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "ha_govee_led_ble/editor/preview/apply_snapshot",
      origin_kind: "catalogue_template",
      origin_id: "template:single:1:0",
    }),
  );
});

test("saved-name collisions confirm a guarded overwrite and accept its generation", async () => {
  const original = cloneObject(responses.library_item);
  const target = {
    id: "target",
    version: 4,
    updated_at: "2026-08-27T00:00:00Z",
    name: "Existing",
    kind: "h617a_painted",
    content_hash: "4".repeat(64),
    origin: { kind: "authored", source_id: null },
  };
  const overwritten = {
    ...original,
    id: target.id,
    version: 5,
    updated_at: "2026-08-27T00:00:01Z",
    name: target.name,
  };
  const callWS = vi.fn(async (message: Record<string, unknown>) => {
    if (message.type === "ha_govee_led_ble/editor/library/create") {
      throw { code: "name_conflict", message: "name conflict" };
    }
    if (message.type === "ha_govee_led_ble/editor/library/name_status") {
      return { status: { kind: "saved", item: target } };
    }
    if (message.type === "ha_govee_led_ble/editor/library/overwrite") {
      return {
        item: overwritten,
        library: { generation: 8, items: [target] },
      };
    }
    throw new Error(`Unexpected command ${String(message.type)}`);
  });
  const api = new EffectStudioApi({
    callWS,
    callService: vi.fn(),
    connection: { subscribeMessage: vi.fn() },
  } as unknown as HomeAssistant);
  const confirm = vi.fn().mockResolvedValue(true);
  const accept = vi.fn().mockReturnValue(true);
  api.setOverwriteConfirmation(confirm);
  api.setLibrarySnapshotHandler(accept);

  const result = await api.createItem(
    "Existing",
    decodeEffectContent(contentSamples.h617a_painted),
  );

  expect(confirm).toHaveBeenCalledWith("Existing");
  expect(result).toMatchObject({ id: "target", version: 5 });
  expect(accept).toHaveBeenCalledWith(
    expect.objectContaining({ generation: 8 }),
  );
  expect(callWS).toHaveBeenLastCalledWith(
    expect.objectContaining({
      type: "ha_govee_led_ble/editor/library/overwrite",
      target_item_id: "target",
      expected_version: 4,
      expected_updated_at: "2026-08-27T00:00:00Z",
    }),
  );
});

test("reserved names surface a direct unavailable-name error", async () => {
  const api = new EffectStudioApi({
    callWS: vi.fn().mockRejectedValue({
      code: "reserved_name",
      message: "reserved",
    }),
    callService: vi.fn(),
    connection: { subscribeMessage: vi.fn() },
  } as unknown as HomeAssistant);

  await expect(
    api.createItem(
      "Mysterious",
      decodeEffectContent(contentSamples.h617a_painted),
    ),
  ).rejects.toThrow('An effect named "Mysterious" already exists.');
});

test("abandoned collision classification cannot issue an overwrite", async () => {
  let active = true;
  const target = {
    id: "target",
    version: 4,
    updated_at: "2026-08-27T00:00:00Z",
    name: "Existing",
    kind: "h617a_painted",
    content_hash: "4".repeat(64),
    origin: { kind: "authored", source_id: null },
  };
  const callWS = vi.fn(async (message: Record<string, unknown>) => {
    if (message.type === "ha_govee_led_ble/editor/library/create") {
      throw { code: "name_conflict", message: "name conflict" };
    }
    if (message.type === "ha_govee_led_ble/editor/library/name_status") {
      active = false;
      return { status: { kind: "saved", item: target } };
    }
    throw new Error(`Unexpected command ${String(message.type)}`);
  });
  const api = new EffectStudioApi({
    callWS,
    callService: vi.fn(),
    connection: { subscribeMessage: vi.fn() },
  } as unknown as HomeAssistant);
  const confirm = vi.fn().mockResolvedValue(true);
  api.setOverwriteConfirmation(confirm);

  await expect(
    api.createItem(
      "Existing",
      decodeEffectContent(contentSamples.h617a_painted),
      () => active,
    ),
  ).rejects.toMatchObject({ code: "save_cancelled" });

  expect(confirm).not.toHaveBeenCalled();
  expect(
    callWS.mock.calls.some(
      ([message]) =>
        message.type === "ha_govee_led_ble/editor/library/overwrite",
    ),
  ).toBe(false);
});

test.each(knownContentFamilies)(
  "canonical %s content decodes and preserves its wire form",
  (family) => {
    const payload = contentSamples[family];
    const decoded = decodeEffectContent(payload);
    expect(decoded.kind).toBe(family);
    expect(effectContentToWire(decoded)).toEqual(payload);
  },
);

test("unknown content remains opaque and preserves its wire form", () => {
  const payload = contentSamples.future_wave;
  const decoded = decodeEffectContent(payload);
  expect(decoded).toMatchObject({
    kind: "opaque",
    source_kind: "future_wave",
  });
  expect(effectContentToWire(decoded)).toEqual(payload);
});

describe("focused response mutations", () => {
  test("device entity references tolerate old payloads and reject non-light IDs", () => {
    const oldPayload = structuredClone(responses.devices) as JsonObject[];
    delete oldPayload[0].light_entity_id;
    expect(decodeDevices(oldPayload)[0].light_entity_id).toBeNull();

    const invalid = structuredClone(responses.devices) as JsonObject[];
    invalid[0].light_entity_id = "switch.cupboard";
    expect(() => decodeDevices(invalid)).toThrow(
      "devices[0].light_entity_id must identify a light entity",
    );
  });

  test("devices accept an optional active workspace without requiring it", () => {
    const payload = structuredClone(responses.devices) as JsonObject[];
    payload[0].active_workspace = {
      config_entry_id: payload[0].config_entry_id,
      model: payload[0].model,
      selector_label: "Flow",
      content: contentSamples.h617a_painted,
      content_hash: "a".repeat(64),
      origin: { kind: "catalogue_template", source_id: "template:single:1:0" },
      observable_signature: "custom:800",
      updated_at: "2026-08-25T00:00:00Z",
      generation: 1,
      confidence: "write_completed",
    };

    const devices = decodeDevices(payload);

    expect(devices[0].active_workspace).toMatchObject({
      selector_label: "Flow",
      content: { kind: "h617a_painted" },
      origin: {
        kind: "catalogue_template",
        source_id: "template:single:1:0",
      },
    });
    expect(devices[1].active_workspace).toBeUndefined();
  });

  test("API version drift is incompatible without making the payload malformed", () => {
    const payload = cloneObject(responses.editor_info);
    payload.api_version = 999;
    expect(isCompatibleEditorInfo(decodeEditorApiInfo(payload))).toBe(false);
  });

  test("unknown library models remain optional compatibility hints", () => {
    const payload = cloneObject(responses.library_snapshot);
    objectArray(payload.items)[0].model = "future-model";
    expect(decodeLibrarySnapshot(payload).items[0]).not.toHaveProperty("model");
  });

  test("library snapshots reject duplicate IDs and malformed item collections", () => {
    const duplicate = cloneObject(responses.library_snapshot);
    const items = objectArray(duplicate.items);
    items[1].id = items[0].id;
    expect(() => decodeLibrarySnapshot(duplicate)).toThrow(
      "library item IDs must be unique",
    );

    const malformed = cloneObject(responses.library_snapshot);
    malformed.items = {};
    expect(() => decodeLibrarySnapshot(malformed)).toThrow(
      "library items must be an array",
    );
  });

  test("scene details reject non-scene content", () => {
    const payload = cloneObject(responses.scene_details.scene_builtin);
    payload.content = contentSamples.h617a_painted;
    expect(() => decodeSceneDetail(payload)).toThrow(
      "scene detail content is unsupported",
    );
  });
});

describe("focused effect-content mutations", () => {
  test("palette scenes reject invalid layouts, flags, colours, and padding", () => {
    const mutations: Array<(payload: JsonObject) => void> = [
      (payload) => {
        payload.layout = 2;
      },
      (payload) => {
        objectArray(payload.steps)[0].inline_colour = [1, 2, 3];
      },
      (payload) => {
        payload.config_flags = 1;
      },
      (payload) => {
        payload.trailing_padding = 0xff * 17 + 1;
      },
      (payload) => {
        objectArray(payload.steps)[0].colour = [1, 2];
      },
    ];

    for (const mutate of mutations) {
      const payload = cloneObject(contentSamples.scene_palette);
      mutate(payload);
      expect(() => decodeEffectContent(payload)).toThrow(
        "Malformed Effect Studio server payload",
      );
    }
  });

  test("layer and movement reserved bits round-trip while explicit bits are rejected", () => {
    const reserved = cloneObject(contentSamples.advanced);
    const reservedLayer = objectArray(reserved.layers)[0];
    reservedLayer.unknown_flags = 0xfd;
    (reservedLayer.selected_movement as JsonObject).unknown_flags = 0xe8;
    (reservedLayer.overall_movement as JsonObject).unknown_flags = 0xe8;
    const decoded = decodeEffectContent(reserved);
    expect(decodeEffectContent(effectContentToWire(decoded))).toEqual(decoded);

    const invalidLayer = cloneObject(contentSamples.scene_layered);
    const layeredEffect = invalidLayer.effect as JsonObject;
    objectArray(layeredEffect.layers)[0].unknown_flags = 0x02;
    expect(() => decodeEffectContent(invalidLayer)).toThrow(
      "must only set reserved bits",
    );

    const invalidMovement = cloneObject(contentSamples.advanced);
    const advancedLayer = objectArray(invalidMovement.layers)[0];
    (advancedLayer.selected_movement as JsonObject).unknown_flags = 0x01;
    expect(() => decodeEffectContent(invalidMovement)).toThrow(
      "must only set reserved bits",
    );
  });

  test("layered scene padding remains bounded", () => {
    const payload = cloneObject(contentSamples.scene_layered);
    payload.trailing_padding = 0xff * 17 + 1;
    expect(() => decodeEffectContent(payload)).toThrow(
      "layered scene trailing padding must be an integer",
    );
  });
});
