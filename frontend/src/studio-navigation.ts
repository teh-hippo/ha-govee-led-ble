import type {
  DeviceCapabilities,
  EffectContent,
  EffectUserState,
  LibraryOrigin,
  LibrarySummary,
  ModelEffectCatalogue,
} from "./types";
import type { CustomEffectCategory } from "./effect-editor-model";

const PANEL_PATH = "/ha-govee-led-ble";
const DEVICE_ROUTE = `${PANEL_PATH}/editor`;
export type StudioSection = "video" | "scenes" | "custom";
export interface StudioNavigationItem {
  section: StudioSection;
  label: string;
  category?: CustomEffectCategory;
}
export type ActiveStudioContext =
  | { kind: "saved"; item: LibrarySummary }
  | { kind: "native-scene"; effect: string }
  | {
      kind: "native-profile";
      section: "video" | "custom";
      category?: "music";
      mode: string;
      label: string;
    }
  | {
      kind: "workspace";
      section: "video" | "custom";
      category?: CustomEffectCategory;
      content: EffectContent;
      origin: LibraryOrigin;
      label: string;
    }
  | { kind: "root" };

export function deviceIdFromEditorPath(pathname: string): string | undefined {
  const match = pathname.match(/^\/ha-govee-led-ble\/editor\/([^/]+)\/?$/);
  if (!match?.[1]) {
    return undefined;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return undefined;
  }
}

export function editorDevicePath(deviceId: string): string {
  return `${DEVICE_ROUTE}/${encodeURIComponent(deviceId)}`;
}

export function synchroniseDeviceSelect(
  select: Pick<HTMLSelectElement, "value">,
  selectedDeviceId: string | undefined,
): void {
  select.value = selectedDeviceId ?? "";
}

export function studioNavigationItems(
  scenesAvailable: boolean,
  videoAvailable: boolean,
  customCategories: readonly {
    category: CustomEffectCategory;
    label: string;
  }[],
): StudioNavigationItem[] {
  return [
    ...(videoAvailable
      ? [{ section: "video" as const, label: "Video" }]
      : []),
    ...(scenesAvailable
      ? [{ section: "scenes" as const, label: "Scenes" }]
      : []),
    ...customCategories.map(({ category, label }) => ({
      section: "custom" as const,
      category,
      label,
    })),
  ];
}

export function initialDeviceId(
  pathname: string,
  devices: readonly DeviceCapabilities[],
  rememberedDeviceId?: string | null,
): string | undefined {
  const linkedDeviceId = deviceIdFromEditorPath(pathname);
  if (linkedDeviceId !== undefined) {
    return linkedDeviceId;
  }
  if (
    rememberedDeviceId &&
    devices.some((device) => device.config_entry_id === rememberedDeviceId)
  ) {
    return rememberedDeviceId;
  }
  return devices[0]?.config_entry_id;
}

export function rememberedStudioSection(
  navigation: EffectUserState["navigation"],
  available: {
    scenes: boolean;
    custom: boolean;
    video: boolean;
  },
): StudioSection {
  const section = navigation.section;
  if (section === "video" && available.video) {
    return section;
  }
  if (section === "scenes" && available.scenes) {
    return section;
  }
  if (section === "custom" && available.custom) {
    return section;
  }
  return available.custom ? "custom" : available.video ? "video" : "scenes";
}

export function activeStudioContext(
  device: DeviceCapabilities | undefined,
  items: readonly LibrarySummary[],
  itemAvailable: (item: LibrarySummary) => boolean,
  catalogue: ModelEffectCatalogue | undefined,
): ActiveStudioContext {
  const active = device?.active_state;
  const hint = active?.active_effect;
  const observedSignature = active ? activeStateSignature(active) : undefined;
  const workspace = device?.active_workspace;
  const workspaceLocation =
    workspace &&
    workspace.config_entry_id === device.config_entry_id &&
    workspace.model === device.model
      ? workspaceStudioLocation(workspace.content)
      : undefined;
  if (workspace && workspaceLocation) {
    return {
      kind: "workspace",
      ...workspaceLocation,
      content: workspace.content,
      origin: workspace.origin,
      label: workspace.selector_label,
    };
  }
  if (
    hint?.source_kind === "saved_effect" &&
    hint.item_id &&
    (hint.confidence !== "unknown" ||
      observedSignature === hint.observable_signature)
  ) {
    const item = items.find(
      (candidate) =>
        candidate.id === hint.item_id &&
        candidate.version === hint.item_version &&
        candidate.content_hash === hint.content_hash &&
        itemAvailable(candidate),
    );
    if (item) {
      return { kind: "saved", item };
    }
  }
  if (hint) {
    return { kind: "root" };
  }
  const nativeMode = active?.native_mode;
  if (!nativeMode) {
    return { kind: "root" };
  }
  if (
    active.mode === "scene" &&
    active.effect === nativeMode
  ) {
    return { kind: "native-scene", effect: nativeMode };
  }
  if (active.mode === "video") {
    const mode = catalogue?.video_modes.find(
      (candidate) => candidate.id === nativeMode,
    );
    return mode
      ? {
          kind: "native-profile",
          section: "video",
          mode: mode.id,
          label: mode.label,
        }
      : { kind: "root" };
  }
  if (active.mode === "music") {
    const mode = catalogue?.music_modes.find(
      (candidate) => candidate.id === nativeMode,
    );
    return mode
      ? {
          kind: "native-profile",
          section: "custom",
          category: "music",
          mode: mode.id,
          label: mode.label,
        }
      : { kind: "root" };
  }
  return { kind: "root" };
}

function activeStateSignature(
  active: NonNullable<DeviceCapabilities["active_state"]>,
): string | undefined {
  if (active.mode === "custom" && active.diy_code !== null) {
    return `custom:${active.diy_code}`;
  }
  if (active.mode === "scene" && active.effect) {
    return `scene:${active.effect}`;
  }
  if (
    (active.mode === "music" || active.mode === "video") &&
    active.native_mode
  ) {
    return `${active.mode}:${active.native_mode}`;
  }
  return undefined;
}

function workspaceStudioLocation(
  content: EffectContent,
): Pick<
  Extract<ActiveStudioContext, { kind: "workspace" }>,
  "section" | "category"
> | undefined {
  if (content.kind === "video_profile") {
    return { section: "video" };
  }
  if (content.kind === "music_profile") {
    return { section: "custom", category: "music" };
  }
  if (
    content.kind === "h617a_painted" ||
    content.kind === "h617a_single" ||
    content.kind === "palette_diy"
  ) {
    return { section: "custom", category: "single-layer" };
  }
  if (content.kind === "h617a_multi") {
    return { section: "custom", category: "multi-layer" };
  }
  if (content.kind === "advanced" || content.kind === "workshop") {
    return { section: "custom", category: "advanced" };
  }
  return undefined;
}
