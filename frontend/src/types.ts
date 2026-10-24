export type RGB = [number, number, number];
export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;

export interface JsonObject {
  [key: string]: JsonValue;
}

export type CapabilityState = "supported" | "unsupported" | "evidence_gap";
export type SupportQuality = "experimental" | "supported";
export type ModelSku = string;
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
  integration_version?: string | null;
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
  physical_ic_count?: number | null;
  catalogue?: ModelEffectCatalogue;
  music_settings?: Record<string, MusicSettings>;
  retained_music_edit?: RetainedMusicEdit | null;
  config_entry_id: string;
  light_entity_id: string | null;
  model: string;
  support_quality: SupportQuality;
  confirmation_issue?: number | null;
  hw_version?: string | null;
  fw_version?: string | null;
  subordinate_20_version?: string | null;
  subordinate_21_version?: string | null;
  display_name: string;
  segment_count: number;
  static_composition?: boolean;
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
  video_control_states?: Partial<Record<VideoProfileSetting, CapabilityState>>;
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
  background?: RGB;
  addressing?: "segments" | "physical_ic";
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

export interface H6179SingleDiyContent {
  kind: "h6179_single_diy";
  model: ModelSku;
  family: number;
  variant: number;
  speed: number;
  palette: RGB[];
}

export interface H6179MixedDiyContent {
  kind: "h6179_mixed_diy";
  model: ModelSku;
  components: EffectPair[];
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

export interface NativeDiyLayer {
  type: "diy";
  kind: number;
  speed: number;
  palette: RGB[];
  parameters: string;
  parameter: number;
  flag: number;
  points: number[];
  direction: number;
  angle: number;
  opaque: string;
}

export interface NativePaintLayer {
  type: "paint";
  groups: { colour: RGB; indices: number[] }[];
  action: number;
  speed: number;
  brightness: number;
  priority: number;
  duration: number;
  opaque: string;
  data_opaque: string;
  trailing: string;
}

export interface NativeOpaqueLayer {
  type: "opaque";
  kind: number;
  data: string;
}

export interface NativeEffectContent {
  kind: "native_effect";
  model: ModelSku;
  family: 797 | 798;
  layers: (NativeDiyLayer | NativePaintLayer | NativeOpaqueLayer)[];
  backgrounds: RGB[];
  background_flag: number;
  background: RGB;
  background_brightness: number;
  show_type: number;
  opaque: string;
  preset_id: number | null;
  template: CatalogueRef | null;
  speed_index: number | null;
}

export type NativeSceneContent = NativeEffectContent & { template: CatalogueRef };

export interface MusicProfileContent {
  kind: "music_profile";
  model: ModelSku;
  mode: string;
  sensitivity: number;
  colour: RGB | null;
  calm: boolean | null;
  parameters: JsonObject;
  palette?: RGB[];
}

export interface RelativeBrightness {
  left: number;
  top: number;
  right: number;
  bottom: number;
  strip_left?: number;
  strip_right?: number;
}

export interface VideoControls {
  saturation_min: number;
  white_balance: {
    representation: "position" | "scalar";
    minimum: number;
    maximum: number;
    default: number;
  };
  brightness_zones: (keyof RelativeBrightness)[];
}

export interface VideoProfileContent {
  kind: "video_profile";
  model: ModelSku;
  mode: string;
  full_screen: boolean | null;
  saturation: number | null;
  sound_effects: boolean | null;
  sound_effects_softness: number | null;
  white_balance_position: number | null;
  white_balance_value?: number;
  relative_brightness: RelativeBrightness | null;
  blank_screen: boolean | null;
  black_border?: boolean;
  blank_screen_detection?: number;
  blank_screen_low_brightness_duration_seconds?: number;
  blank_screen_same_tone_duration_seconds?: number;
}

export type VideoProfileSetting =
  | "capture_region"
  | "saturation"
  | "sound_effects"
  | "white_balance"
  | "relative_brightness"
  | "blank_screen"
  | "black_border";

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
  extensions?: number;
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
  native_diy?: number;
}

export interface NativeDiyTemplateContract {
  template_id: number;
  body_effect: number;
  upload_subtype: number;
  layer_count: number;
  palette_min: number;
  palette_max: number;
  rate_field: "selected_movement_speed" | "colour_brightness_speed";
  rate_min: number;
  rate_max: number;
  rate_default: number;
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
  | MultiContent
  | H6179SingleDiyContent
  | H6179MixedDiyContent;

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
  rate: "speed" | "sensitivity" | "none";
  palette_max?: number;
  rate_min: number;
  multi_rate_min?: number;
  rate_max: number;
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
  | AdvancedContent
  | PaletteDiyEffectContent
  | NativeEffectContent
  | MusicProfileContent
  | VideoProfileContent;

export interface CatalogueTemplate {
  id: string;
  label: string;
  category: "single-layer" | "music" | "video" | "advanced";
  content: CatalogueTemplateContent;
}

export interface ReleaseWorkflowCapability {
  id: ReleaseWorkflowId;
  label: string;
  content_kind: string;
  application: ReleaseWorkflowApplication;
}

export interface MusicParameterSpec {
  kind: "number" | "switch" | "select";
  default: number | boolean | string;
  min: number;
  max: number;
  options: string[];
}

export interface MusicSettings {
  available: boolean;
  style: boolean;
  calm_default: boolean;
  colour: boolean;
  evidence: string | null;
  palette_size: number;
  palette?: { min: number; max: number; default: RGB[] };
  parameters: Record<string, MusicParameterSpec>;
}

export interface RetainedMusicEdit {
  mode: string;
  revision: number;
  parameters: JsonObject;
  calm: boolean | null;
  settings: MusicSettings;
}

export interface ModelEffectCatalogue {
  native_actions?: EffectStudioModeOption[];
  painted_addressing?: "segments" | "physical_ic";
  painted_background?: RGB;
  physical_ic_count?: number | null;
  sku: ModelSku;
  painted_effects: PaintedEffectTemplate[];
  effects: PaletteDiyFamily[];
  music_modes: EffectStudioModeOption[];
  music_settings: Record<string, MusicSettings>;
  video_modes: EffectStudioModeOption[];
  video_settings: VideoProfileSetting[];
  video_controls?: VideoControls;
  templates?: CatalogueTemplate[];
  workshop_templates: WorkshopTemplate[];
  workflows: ReleaseWorkflowCapability[];
  native_diy_templates?: NativeDiyTemplateContract[];
  diy_slot_policy?: "fixed" | "approved_observed";
  advanced_create?: boolean;
  supports: {
    multi: CapabilityState;
    advanced: CapabilityState;
    workshop: CapabilityState;
  };
  limits: {
    palette_min: number;
    palette_max: number;
    multi_max: number;
    speed_min: number;
    speed_max: number;
    brightness_min: number;
    brightness_max: number;
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
  schema_version: 11;
  sku: ModelSku;
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
  inline_extra?: number;
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
  | NativeEffectContent
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
  selector_only: boolean;
  parameter_kind: SceneParameterKind;
  speed: {
    option_count: number;
    default_index: number;
    layer_speeds?: number[][];
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
  content: BuiltinSceneContent | PaletteSceneContent | LayeredSceneContent | NativeSceneContent;
  catalogue_content:
    | BuiltinSceneContent
    | PaletteSceneContent
    | LayeredSceneContent
    | NativeSceneContent;
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
