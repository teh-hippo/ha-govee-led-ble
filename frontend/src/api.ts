import type {
  CustomEffectCatalogue,
  CatalogueTemplateContent,
  CatalogueTemplateDefaultDetail,
  DeviceCapabilities,
  EditorApiInfo,
  EffectContent,
  EffectUserState,
  HomeAssistant,
  LibraryItem,
  LibraryMutationResult,
  LibraryNameStatus,
  LibrarySnapshot,
  PreviewStatus,
  PreviewSnapshotProvenance,
  SceneCatalogue,
  SceneDetail,
  SceneSummary,
} from "./types";
import {
  editableLayerLabels,
} from "./effect-editor-model";
import { errorCode } from "./ui-utils";
import {
  decodeCustomCatalogue,
  decodeCatalogueTemplateDefaultDetail,
  decodeDevices,
  decodeEditorApiInfo,
  decodeEffectUserState,
  decodeLibraryItem,
  decodeLibrarySnapshot,
  decodePreviewStatus,
  decodeSceneCatalogue,
  decodeSceneDetail,
  effectContentToWire,
} from "./validation";

const PREFIX = "ha_govee_led_ble/editor";

export class EffectStudioApi {
  private librarySnapshotHandler?: (
    snapshot: LibrarySnapshot,
  ) => boolean | void | Promise<boolean | void>;
  private overwriteConfirmation?: (effectName: string) => Promise<boolean>;

  public constructor(private readonly hass: HomeAssistant) {}

  public setLibrarySnapshotHandler(
    handler: (
      snapshot: LibrarySnapshot,
    ) => boolean | void | Promise<boolean | void>,
  ): void {
    this.librarySnapshotHandler = handler;
  }

  public setOverwriteConfirmation(
    confirm: (effectName: string) => Promise<boolean>,
  ): void {
    this.overwriteConfirmation = confirm;
  }

  public async info(): Promise<EditorApiInfo> {
    return decodeEditorApiInfo(await this.call("info"));
  }

  public async devices(): Promise<DeviceCapabilities[]> {
    const result = await this.call("devices");
    return decodeDevices(resultField(result, "devices"));
  }

  public async device(configEntryId: string): Promise<DeviceCapabilities> {
    const result = await this.call("device", {
      config_entry_id: configEntryId,
    });
    const devices = decodeDevices([resultField(result, "device")]);
    return devices[0];
  }

  public subscribeDevice(
    configEntryId: string,
    callback: (device: DeviceCapabilities) => void,
    onError?: (error: Error) => void,
  ): Promise<() => void> {
    return this.hass.connection.subscribeMessage(
      (payload) => {
        try {
          callback(decodeDevices([resultField(payload, "device")])[0]);
        } catch (error) {
          onError?.(asError(error));
        }
      },
      {
        type: `${PREFIX}/device/subscribe`,
        config_entry_id: configEntryId,
      },
    );
  }

  public async customCatalogue(): Promise<CustomEffectCatalogue> {
    const result = await this.call("custom/catalogue");
    return decodeCustomCatalogue(resultField(result, "catalogue"));
  }

  public async library(): Promise<LibrarySnapshot> {
    return decodeLibrarySnapshot(await this.call("library/list"));
  }

  public async userState(): Promise<EffectUserState> {
    const result = await this.call("user_state/get");
    return decodeEffectUserState(resultField(result, "user_state"));
  }

  public async updateUserState(
    selectedConfigEntryId: string | undefined,
    navigation: EffectUserState["navigation"],
  ): Promise<EffectUserState> {
    const result = await this.call("user_state/update", {
      ...(selectedConfigEntryId
        ? { selected_config_entry_id: selectedConfigEntryId }
        : {}),
      navigation,
    });
    return decodeEffectUserState(resultField(result, "user_state"));
  }

  public async item(itemId: string): Promise<LibraryItem> {
    const result = await this.call("library/get", {
      item_id: itemId,
    });
    return decodeLibraryItem(resultField(result, "item"));
  }

  public async createItem(
    name: string,
    content: EffectContent,
    guard?: () => boolean,
  ): Promise<LibraryItem> {
    const data = {
      name,
      content: effectContentToWire(content),
      ...(editableLayerLabels(content)
        ? { layer_labels: editableLayerLabels(content) }
        : {}),
    };
    try {
      return await this.libraryMutation("library/create", data);
    } catch (error) {
      return this.resolveNameCollision(
        error,
        name,
        content,
        undefined,
        guard,
      );
    }
  }

  public async updateItem(
    item: LibraryItem,
    name: string,
    content: EffectContent,
    guard?: () => boolean,
  ): Promise<LibraryItem> {
    const data = {
      item_id: item.id,
      name,
      content: effectContentToWire(content),
      ...(editableLayerLabels(content)
        ? { layer_labels: editableLayerLabels(content) }
        : {}),
      expected_version: item.version,
      expected_updated_at: item.updated_at,
    };
    try {
      return await this.libraryMutation("library/update", data);
    } catch (error) {
      return this.resolveNameCollision(
        error,
        name,
        content,
        item.id,
        guard,
      );
    }
  }

  public async deleteItem(item: Pick<LibraryItem, "id" | "version" | "updated_at">): Promise<void> {
    const result = await this.call("library/delete", {
      item_id: item.id,
      expected_version: item.version,
      expected_updated_at: item.updated_at,
    });
    const accepted = await this.acceptLibrarySnapshot(
      decodeLibrarySnapshot(resultField(result, "library")),
    );
    if (accepted === false) {
      throw new StaleLibraryMutationError();
    }
  }

  public async nameStatus(
    name: string,
    excludingItemId?: string,
  ): Promise<LibraryNameStatus> {
    const result = await this.call("library/name_status", {
      name,
      ...(excludingItemId ? { excluding_item_id: excludingItemId } : {}),
    });
    const status = resultField(result, "status");
    if (typeof status !== "object" || status === null || Array.isArray(status)) {
      throw new Error("Malformed Effect Studio server payload: name status must be an object.");
    }
    const raw = status as Record<string, unknown>;
    if (
      raw.kind !== "available" &&
      raw.kind !== "reserved" &&
      raw.kind !== "same_item" &&
      raw.kind !== "saved"
    ) {
      throw new Error("Malformed Effect Studio server payload: name status kind is invalid.");
    }
    if (raw.kind !== "saved") {
      return { kind: raw.kind };
    }
    const snapshot = decodeLibrarySnapshot({
      generation: 0,
      items: [raw.item],
    });
    return { kind: "saved", item: snapshot.items[0] };
  }

  public async applySavedEffect(
    configEntryId: string,
    item: Pick<LibraryItem, "id" | "version">,
  ): Promise<void> {
    await this.call("apply", {
      config_entry_id: configEntryId,
      item_id: item.id,
      expected_version: item.version,
      updated_at: new Date().toISOString(),
    });
  }

  public async applySnapshot(
    configEntryId: string,
    name: string,
    content: EffectContent,
    provenance?: PreviewSnapshotProvenance,
  ): Promise<void> {
    await this.call("apply_snapshot", {
      config_entry_id: configEntryId,
      name,
      content: effectContentToWire(content),
      updated_at: new Date().toISOString(),
      ...(provenance ?? {}),
    });
  }

  public async applyScene(
    configEntryId: string,
    scene: SceneSummary,
    speedIndex: number | null,
  ): Promise<void> {
    await this.call("scene/apply", {
      config_entry_id: configEntryId,
      scene_id: scene.scene_id,
      effect_id: scene.effect_id,
      ...(speedIndex === null ? {} : { speed_index: speedIndex }),
    });
  }

  public async closePreviewSession(sessionId: string): Promise<void> {
    await this.call("preview/session/close", {
      session_id: sessionId,
    });
  }

  public async previewSnapshot(
    sessionId: string,
    sequence: number,
    configEntryId: string,
    name: string,
    content: EffectContent,
    persistDefault = false,
    provenance?: PreviewSnapshotProvenance,
  ): Promise<void> {
    await this.call("preview/apply_snapshot", {
      session_id: sessionId,
      sequence,
      config_entry_id: configEntryId,
      name,
      content: effectContentToWire(content),
      updated_at: new Date().toISOString(),
      persist_default: persistDefault,
      ...(provenance ?? {}),
    });
  }

  public async previewScene(
    sessionId: string,
    sequence: number,
    configEntryId: string,
    scene: SceneSummary,
    speedIndex: number | null,
    persistDefault = false,
  ): Promise<void> {
    await this.call("preview/apply_scene", {
      session_id: sessionId,
      sequence,
      config_entry_id: configEntryId,
      scene_id: scene.scene_id,
      effect_id: scene.effect_id,
      ...(speedIndex === null ? {} : { speed_index: speedIndex }),
      updated_at: new Date().toISOString(),
      persist_default: persistDefault,
    });
  }

  public async cancelPreview(
    sessionId: string,
    configEntryId?: string,
  ): Promise<void> {
    await this.call("preview/cancel", {
      session_id: sessionId,
      ...(configEntryId ? { config_entry_id: configEntryId } : {}),
    });
  }

  public async sceneCatalogue(
    configEntryId: string,
  ): Promise<SceneCatalogue> {
    const result = await this.call(
      "scene/catalogue/list",
      {
        config_entry_id: configEntryId,
      },
    );
    return decodeSceneCatalogue(resultField(result, "catalogue"));
  }

  public sceneDetail(
    configEntryId: string,
    sceneId: number,
    effectId: number,
  ): Promise<SceneDetail> {
    return this.call("scene/catalogue/get", {
      config_entry_id: configEntryId,
      scene_id: sceneId,
      effect_id: effectId,
    }).then(decodeSceneDetail);
  }

  public resetScene(
    configEntryId: string,
    scene: SceneSummary,
  ): Promise<SceneDetail> {
    return this.call("scene/reset", {
      config_entry_id: configEntryId,
      scene_id: scene.scene_id,
      effect_id: scene.effect_id,
    }).then(decodeSceneDetail);
  }

  public setSceneDefault(
    configEntryId: string,
    content: SceneDetail["content"],
  ): Promise<SceneDetail> {
    return this.call("scene/default/set", {
      config_entry_id: configEntryId,
      scene_id: content.template.scene_id,
      effect_id: content.template.effect_id,
      content: effectContentToWire(content),
      updated_at: new Date().toISOString(),
    }).then(decodeSceneDetail);
  }

  public templateDefault(
    configEntryId: string,
    templateId: string,
  ): Promise<CatalogueTemplateDefaultDetail> {
    return this.call("template/default/get", {
      config_entry_id: configEntryId,
      template_id: templateId,
    }).then(decodeCatalogueTemplateDefaultDetail);
  }

  public setTemplateDefault(
    configEntryId: string,
    templateId: string,
    content: CatalogueTemplateContent,
  ): Promise<CatalogueTemplateDefaultDetail> {
    return this.call("template/default/set", {
      config_entry_id: configEntryId,
      template_id: templateId,
      content: effectContentToWire(content),
      updated_at: new Date().toISOString(),
    }).then(decodeCatalogueTemplateDefaultDetail);
  }

  public resetTemplateDefault(
    configEntryId: string,
    templateId: string,
  ): Promise<CatalogueTemplateDefaultDetail> {
    return this.call("template/default/reset", {
      config_entry_id: configEntryId,
      template_id: templateId,
    }).then(decodeCatalogueTemplateDefaultDetail);
  }

  public subscribeLibrary(
    callback: (snapshot: LibrarySnapshot) => void,
    onError?: (error: Error) => void,
  ): Promise<() => void> {
    return this.hass.connection.subscribeMessage(
      (snapshot) => {
        try {
          callback(decodeLibrarySnapshot(snapshot));
        } catch (error) {
          onError?.(asError(error));
        }
      },
      {
        type: `${PREFIX}/library/subscribe`,
      },
    );
  }

  public subscribePreview(
    sessionId: string,
    callback: (status: PreviewStatus) => void,
    onError?: (error: Error) => void,
  ): Promise<() => void> {
    return this.hass.connection.subscribeMessage(
      (status) => {
        try {
          callback(decodePreviewStatus(status));
        } catch (error) {
          onError?.(asError(error));
        }
      },
      {
        type: `${PREFIX}/preview/subscribe`,
        session_id: sessionId,
      },
    );
  }

  public onConnectionReady(callback: () => void): () => void {
    const connection = this.hass.connection;
    if (!connection.addEventListener || !connection.removeEventListener) {
      return () => undefined;
    }
    connection.addEventListener("ready", callback);
    return () => connection.removeEventListener?.("ready", callback);
  }

  private call<T>(
    command: string,
    data: Record<string, unknown> = {},
  ): Promise<T> {
    return this.hass.callWS<T>({
      type: `${PREFIX}/${command}`,
      ...data,
    });
  }

  private async libraryMutation(
    command: string,
    data: Record<string, unknown>,
  ): Promise<LibraryItem> {
    const result = await this.call(command, data);
    const mutation = decodeLibraryMutation(result);
    const accepted = await this.acceptLibrarySnapshot(mutation.library);
    if (accepted === false) {
      throw new StaleLibraryMutationError();
    }
    return mutation.item;
  }

  private async resolveNameCollision(
    error: unknown,
    name: string,
    content: EffectContent,
    excludingItemId?: string,
    guard?: () => boolean,
  ): Promise<LibraryItem> {
    const code = errorCode(error);
    if (code === "reserved_name") {
      throw new EffectNameUnavailableError(name);
    }
    if (code !== "name_conflict") {
      throw error;
    }
    if (guard && !guard()) {
      throw new EffectSaveCancelledError();
    }
    const status = await this.nameStatus(name, excludingItemId);
    if (guard && !guard()) {
      throw new EffectSaveCancelledError();
    }
    if (status.kind === "reserved") {
      throw new EffectNameUnavailableError(name);
    }
    if (status.kind !== "saved") {
      throw error;
    }
    if (
      !this.overwriteConfirmation ||
      !(await this.overwriteConfirmation(status.item.name))
    ) {
      throw new EffectSaveCancelledError();
    }
    if (guard && !guard()) {
      throw new EffectSaveCancelledError();
    }
    return this.libraryMutation("library/overwrite", {
      target_item_id: status.item.id,
      expected_version: status.item.version,
      expected_updated_at: status.item.updated_at,
      name,
      content: effectContentToWire(content),
      ...(editableLayerLabels(content)
        ? { layer_labels: editableLayerLabels(content) }
        : {}),
    });
  }

  private acceptLibrarySnapshot(
    snapshot: LibrarySnapshot,
  ): boolean | void | Promise<boolean | void> {
    return this.librarySnapshotHandler?.(snapshot);
  }
}

export class EffectSaveCancelledError extends Error {
  public readonly code = "save_cancelled";

  public constructor() {
    super("The save was cancelled.");
  }
}

export class EffectNameUnavailableError extends Error {
  public readonly code = "reserved_name";

  public constructor(name: string) {
    super(`An effect named ${JSON.stringify(name)} already exists.`);
  }
}

class StaleLibraryMutationError extends Error {
  public readonly code = "conflict";

  public constructor() {
    super("The effect library changed before the save response arrived.");
  }
}

function decodeLibraryMutation(value: unknown): LibraryMutationResult {
  return {
    item: decodeLibraryItem(resultField(value, "item")),
    library: decodeLibrarySnapshot(resultField(value, "library")),
  };
}

function resultField(value: unknown, field: string): unknown {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Malformed Effect Studio server payload: response must be an object.");
  }
  if (!(field in value)) {
    throw new Error(`Malformed Effect Studio server payload: response is missing ${field}.`);
  }
  return (value as Record<string, unknown>)[field];
}


function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error("Malformed Effect Studio server payload.");
}
