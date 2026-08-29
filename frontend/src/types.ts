export type RGB = [number, number, number];
export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;

export interface JsonObject {
  [key: string]: JsonValue;
}

export type CapabilityState = "supported" | "unsupported" | "evidence_gap";
export type ModelSku = "H617A" | "H617E" | "H6199";
export type ObservationConfidence =
  | "exact_session"
  | "activation_match"
  | "settings_match"
  | "mode_match"
  | "write_completed"
  | "unknown";
export type ReleaseWorkflowId =
  | "native_scenes"
  | "edited_palette_scenes"
  | "layered_scenes"
  | "painted"
  | "single"
  | "multi"
  | "native_music"
  | "video"
  | "palette_diy"
  | "advanced"
  | "workshop";
type ReleaseWorkflowApplication =
  | "studio"
  | "home_assistant"
  | "planned";

export interface EditorApiInfo {
  api_version: number;
  effect_schema_version: number;
  compiler_version: number;
  limits: {
    effect_name: number;
    effect_document_bytes: number;
    devices: number;
    library_items: number;
    deployment_records: number;
    scene_catalogue_entries: number;
  };
}

export interface DeviceCapabilities {
  config_entry_id: string;
  light_entity_id: string | null;
  model: string;
  display_name: string;
  segment_count: number;
  custom_effects: {
    painted: CapabilityState;
    single: CapabilityState;
    multi: CapabilityState;
    palette_diy: CapabilityState;
    advanced: CapabilityState;
    workshop: CapabilityState;
  };
  profiles: {
    music: CapabilityState;
    video: CapabilityState;
  };
  readback: string;
  effect_categories: string[];
  preview_health: PreviewHealthStatus;
  active_state: ObservedEffectState | null;
  active_workspace?: ActiveEffectWorkspace | null;
}

export interface EffectUserState {
  owner_id: string;
  recent_colours: RGB[];
  selected_config_entry_id: string | null;
  navigation: JsonObject;
}

export interface ActiveEffectHint {
  source_kind: "saved_effect" | "snapshot" | "deleted_effect";
  selector_label: string;
  content_hash: string;
  origin: {
    kind: string;
    source_id: string | null;
  };
  observable_signature: string;
  confidence: ObservationConfidence;
  item_id: string | null;
  item_version: number | null;
}

export interface ObservedEffectState {
  config_entry_id: string;
  mode: string;
  observed_at: string;
  confidence: ObservationConfidence;
  diy_code: number | null;
  effect: string | null;
  native_mode: string | null;
  matched_operation_id: string | null;
  active_effect: ActiveEffectHint | null;
}

export interface ActiveEffectWorkspace {
  config_entry_id: string;
  model: string;
  selector_label: string;
  content: EffectContent;
  content_hash: string;
  origin: LibraryOrigin;
  observable_signature: string;
  updated_at: string;
  generation: number;
  confidence: ObservationConfidence;
}

export interface PaintedContent {
  kind: "h617a_painted";
  effect:
    | "cycle"
    | "clockwise"
    | "counter_clockwise"
    | "twinkle"
    | "gradient"
    | "breathe";
  speed: number;
  brightness: number;
  segments: (RGB | null)[];
}

export interface SingleContent {
  kind: "h617a_single";
  family: number;
  variant: number;
  speed: number;
  palette: RGB[];
}

export interface EffectPair {
  family: number;
  variant: number;
}

export interface MultiContent {
  kind: "h617a_multi";
  effects: EffectPair[];
  speed: number;
  palette: RGB[];
}

export interface PaletteDiyEffectContent {
  kind: "palette_diy";
  model: ModelSku;
  family: number;
  variant: number;
  speed: number;
  palette: RGB[];
}

export interface MusicProfileContent {
  kind: "music_profile";
  model: ModelSku;
  mode: string;
  sensitivity: number;
  colour: RGB | null;
  calm: boolean | null;
  parameters: JsonObject;
}

export interface RelativeBrightness {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface VideoProfileContent {
  kind: "video_profile";
  model: "H6199";
  mode: "movie" | "game";
  full_screen: boolean;
  saturation: number;
  sound_effects: boolean;
  sound_effects_softness: number;
  white_balance_position: number;
  relative_brightness: RelativeBrightness;
  blank_screen: boolean;
}

export type BrightnessOrder = 0 | 1 | 2 | 3;

export type SelectionType = 0 | 1 | 2 | 3;

interface AppliedArea {
  start_tenths: number;
  width_tenths: number;
}

interface Selection {
  type: number;
  param_1: number;
  param_2: number;
}

export interface BrightnessPattern {
  scope_high: number;
  scope_low: number;
  order: number;
  change_speed: number;
  brightest_retention: number;
  darkest_retention: number;
}

interface Distribution {
  method: number;
  backwards: boolean;
}

export interface Movement {
  enabled: boolean;
  enter_exit: boolean;
  direction: number;
  distance: number;
  speed: number;
  unknown_flags: number;
}

export interface EffectLayer {
  area: AppliedArea;
  selection: Selection;
  brightness_gradient: boolean;
  brightness_patterns: BrightnessPattern[];
  distribution: Distribution;
  colour_speed: number;
  colour_retention: number;
  palette: RGB[];
  selected_movement: Movement;
  overall_movement: Movement;
  priority: number;
  unknown_flags: number;
  excess: string;
}

export interface AdvancedContent {
  kind: "advanced";
  layers: EffectLayer[];
}

export interface WorkshopContent {
  kind: "workshop";
  model: ModelSku;
  template: string;
  effect: {
    layers: EffectLayer[];
  };
  raw_param: string;
  trailing_padding: number;
}

export type CustomEffectContent =
  | PaintedContent
  | SingleContent
  | MultiContent;

export interface PaintedEffectTemplate {
  id: PaintedContent["effect"];
  label: string;
}

interface PaletteDiyVariation {
  id: string;
  label: string;
  variant: number;
}

export interface PaletteDiyFamily {
  id: string;
  label: string;
  family: number;
  variations: PaletteDiyVariation[];
  supports_multi: boolean;
  rate: "speed" | "sensitivity";
  category: "single_layer";
}

export type DiyEffectFamily = PaletteDiyFamily;

export interface EffectStudioModeOption {
  id: string;
  label: string;
}

export interface WorkshopTemplate {
  id: string;
  label: string;
  content: WorkshopContent;
}

export type CatalogueTemplateContent =
  | CustomEffectContent
  | PaletteDiyEffectContent
  | MusicProfileContent
  | VideoProfileContent;

export interface CatalogueTemplate {
  id: string;
  label: string;
  category: "single-layer" | "music" | "video";
  content: CatalogueTemplateContent;
}

export interface ReleaseWorkflowCapability {
  id: ReleaseWorkflowId;
  label: string;
  content_kind: string;
  application: ReleaseWorkflowApplication;
}

export interface ModelEffectCatalogue {
  sku: ModelSku;
  painted_effects: PaintedEffectTemplate[];
  effects: PaletteDiyFamily[];
  music_modes: EffectStudioModeOption[];
  video_modes: EffectStudioModeOption[];
  templates?: CatalogueTemplate[];
  workshop_templates: WorkshopTemplate[];
  workflows: ReleaseWorkflowCapability[];
  supports: {
    multi: CapabilityState;
    advanced: CapabilityState;
    workshop: CapabilityState;
  };
  limits: {
    palette_min: number;
    palette_max: number;
    multi_max: number;
    music_sensitivity_min: number;
    music_sensitivity_max: number;
  };
  apply: {
    painted: CapabilityState;
    single: CapabilityState;
    multi: CapabilityState;
    palette_diy: CapabilityState;
    workshop: CapabilityState;
  };
}

export interface EffectStudioCatalogue extends ModelEffectCatalogue {
  schema_version: 8;
  sku: "H617A";
  models: Record<ModelSku, ModelEffectCatalogue>;
}

export type CustomEffectCatalogue = EffectStudioCatalogue;

interface CatalogueRef {
  sku: string;
  scene_id: number;
  effect_id: number;
  catalogue_schema_version: number;
}

export interface BuiltinSceneContent {
  kind: "scene_builtin";
  template: CatalogueRef;
  speed_index: number | null;
}

interface SceneStepContent {
  value: number;
  colour: RGB;
  inline_colour: RGB | null;
}

export interface PaletteSceneContent {
  kind: "scene_palette";
  template: CatalogueRef;
  layout: 0 | 1;
  brightness_flag: boolean;
  steps: SceneStepContent[];
  palette: RGB[];
  speed_index: number | null;
  config_flags?: number;
  trailing_padding?: number;
}

export interface LayeredSceneContent {
  kind: "scene_layered";
  template: CatalogueRef;
  effect: {
    layers: EffectLayer[];
  };
  speed_index: number | null;
  raw_param: string;
  trailing_padding?: number;
}

export type KnownEffectContent =
  | CustomEffectContent
  | PaletteDiyEffectContent
  | MusicProfileContent
  | VideoProfileContent
  | AdvancedContent
  | WorkshopContent
  | BuiltinSceneContent
  | PaletteSceneContent
  | LayeredSceneContent;

export interface OpaqueContent {
  kind: "opaque";
  source_kind: string;
  body: Record<string, unknown>;
}

export type EffectContent = KnownEffectContent | OpaqueContent;

export interface LibraryOrigin {
  kind: string;
  source_id: string | null;
}

export interface LibraryItem {
  schema_version: number;
  id: string;
  version: number;
  updated_at: string;
  name: string;
  content: EffectContent;
  content_hash: string;
  origin: LibraryOrigin;
  extensions: Record<string, unknown>;
  target_hint?: {
    model: string | null;
    segment_count: number | null;
  };
}

export interface LibrarySummary {
  id: string;
  version: number;
  updated_at: string;
  name: string;
  kind: string;
  content_hash: string;
  origin: LibraryOrigin;
  model?: ModelSku;
  template?: CatalogueRef;
}

export interface LibrarySnapshot {
  items: LibrarySummary[];
  generation?: number;
}

export interface LibraryMutationResult {
  item: LibraryItem;
  library: LibrarySnapshot;
}

export type LibraryNameStatus =
  | { kind: "available" | "reserved" | "same_item" }
  | { kind: "saved"; item: LibrarySummary };

export const PREVIEW_PHASES = [
  "queued",
  "writing",
  "written",
  "confirmed",
  "unconfirmed",
  "failed",
  "cancelled",
] as const;

type PreviewPhase = (typeof PREVIEW_PHASES)[number];

export interface PreviewStatus {
  session_id: string;
  sequence: number;
  config_entry_id: string;
  phase: PreviewPhase;
  content_kind: string;
  confidence: ObservationConfidence;
  error_code: string | null;
  error_message: string | null;
  write_disposition:
    | "not_started"
    | "may_have_started"
    | "completed"
    | "unknown";
  persist_default: boolean;
  scene_id: number | null;
  effect_id: number | null;
  default_action: "set" | "reset" | null;
}

export interface PreviewSnapshotProvenance {
  origin_kind: "catalogue_template";
  origin_id: string;
}

export interface PreviewHealthStatus {
  config_entry_id: string;
  revision: number;
  phase: "healthy" | "checking" | "degraded";
  incident_id: string | null;
  error_code: string | null;
  error_message: string | null;
  write_disposition:
    | "not_started"
    | "may_have_started"
    | "completed"
    | "unknown";
  checked_at: string;
}

interface SceneCategory {
  id: number;
  name: string;
}

type SceneParameterKind = "none" | "palette" | "layers" | "opaque";

export interface SceneSummary {
  scene_id: number;
  effect_id: number;
  category_id: number;
  category: string;
  name: string;
  variant: string;
  display_name: string;
  scene_type: number;
  parameter_kind: SceneParameterKind;
  speed: {
    option_count: number;
    default_index: number;
  } | null;
}

export interface SceneCatalogue {
  schema_version: number;
  sku: string;
  enabled: boolean;
  categories: SceneCategory[];
  scenes: SceneSummary[];
}

export interface SceneDetail {
  scene: SceneSummary;
  content: BuiltinSceneContent | PaletteSceneContent | LayeredSceneContent;
  catalogue_content:
    | BuiltinSceneContent
    | PaletteSceneContent
    | LayeredSceneContent;
  has_default: boolean;
}

export interface CatalogueTemplateDefaultDetail {
  template_id: string;
  content: CatalogueTemplateContent;
  catalogue_content: CatalogueTemplateContent;
  has_default: boolean;
}

export interface HomeAssistantEntityState {
  state: string;
  attributes?: Record<string, unknown>;
}

export interface HomeAssistant {
  callWS<T>(message: Record<string, unknown>): Promise<T>;
  callService(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
  ): Promise<unknown>;
  connection: {
    subscribeMessage<T>(
      callback: (event: T) => void,
      message: Record<string, unknown>,
    ): Promise<() => void>;
    addEventListener?(event: "ready", callback: () => void): void;
    removeEventListener?(event: "ready", callback: () => void): void;
  };
  user?: {
    is_admin: boolean;
  };
  states?: Record<string, HomeAssistantEntityState>;
  dockedSidebar?: "auto" | "docked" | "always_hidden";
  kioskMode?: boolean;
}

export interface PanelConfig {
  config?: {
    configuration_path?: string;
  };
}
