"""Vulture whitelist: names that look unused but are intentionally kept.

Checked by `make check` so new dead code fails the build. An entry here is a decision, not a default: add one only
with a reason, in the matching group. Because vulture matches by name, an entry also hides any other unused symbol
with the same name, so prefer deleting the code over whitelisting it.
"""

# --- Home Assistant hooks ---
# Home Assistant calls these by name (config flow, setup/unload hooks, entity properties and attrs, entity services
# registered by string in light_services, store migration). Nothing in this repo references them directly.

_.assumed_state  # light.py
_.async_apply_custom_effect  # light.py
async_get_config_entry_diagnostics  # diagnostics.py
_.async_get_options_flow  # config_flow.py
async_migrate_entry  # __init__.py
_._async_migrate_func  # effect_store.py
async_remove_entry  # __init__.py
_.async_select_option  # select.py
_.async_set_segment_color  # light_services.py
_.async_set_segment_color_temp  # light_services.py
async_setup  # __init__.py
_._async_setup  # coordinator.py
async_setup_entry  # __init__.py, light.py, select.py, sensor.py, switch.py
_.async_step_bluetooth  # config_flow.py
_.async_step_init  # config_flow.py
_.async_step_reconfigure  # config_flow.py
_.async_step_user  # config_flow.py
_.async_turn_off  # light.py, switch.py
_.async_turn_on  # light.py, switch.py
async_unload_entry  # __init__.py
_._async_update_data  # coordinator.py
_._attr_device_info  # light.py, select.py, sensor.py, switch.py
_._attr_entity_category  # switch.py
_._attr_entity_registry_visible_default  # switch.py
_._attr_options  # select.py
_._attr_translation_key  # select.py, switch.py
_._attr_unique_id  # light.py, select.py, sensor.py, switch.py
CONFIG_SCHEMA  # __init__.py
_.current_option  # select.py
_.extra_restore_state_data  # light.py
_.extra_state_attributes  # light.py
GoveeConfigFlow  # config_flow.py
_.native_value  # sensor.py
PARALLEL_UPDATES  # light.py, select.py, sensor.py, switch.py
_.supported_features  # light.py
VERSION  # config_flow.py

# --- Enum members ---
# Enum members. Enums are built from wire or stored values, so a member that is never named in code is still
# vocabulary the decoder can return.

BRIGHTEST_DARKEST  # layered_scene.py
BRIGHTEST_DARKEST_BRIGHTEST  # layered_scene.py
CANONICAL_ENCODER_ONLY  # effect_contracts.py
CAPTURED_FIXTURE  # effect_domain.py
CONTINUOUS  # layered_scene.py
DARKEST_BRIGHTEST  # layered_scene.py
DARKEST_BRIGHTEST_DARKEST  # layered_scene.py
FRONTEND_APPLY  # effect_diagnostics.py
HIDDEN  # effect_contracts.py
IMPORTED  # effect_domain.py
OPAQUE  # effect_contracts.py
RANDOM  # layered_scene.py
RAW_PRESERVATION  # effect_contracts.py
SEGMENT  # layered_scene.py
STRUCTURAL_DEFINITION_ONLY  # effect_contracts.py
STRUCTURAL_PARSER_ONLY  # effect_contracts.py

# --- Decoded wire-format fields ---
# Fields decoded from device frames. They are populated by the parser and kept so a captured frame round-trips
# losslessly, even where no feature reads the value yet.

_.a3_type  # layered_scene_decoder.py
_.applied_area  # layered_scene_decoder.py
_.area_count  # dreamview.py
_.area_values  # dreamview.py
_.brightness_order  # layered_scene_decoder.py
_.brightness_scope_end  # layered_scene_decoder.py
_.brightness_scope_start  # layered_scene_decoder.py
_.brightness_speed  # layered_scene_decoder.py
_.data_length  # h60a6_effects.py
_.direction_distribution  # layered_scene_decoder.py
_.discriminator  # dreamview.py
_.identity_kind  # dreamview.py
_.layer_flags  # layered_scene_decoder.py
_.len_body  # protocol_core.py
_.module  # dreamview.py
_.name_len  # dreamview.py
_.num_blocks  # layered_scene_decoder.py
_.num_brightness_blocks  # layered_scene_decoder.py
_.num_layers  # layered_scene_decoder.py
_.num_members  # dreamview.py
_.num_records  # layered_scene_decoder.py
_.num_steps  # palette_scene_decoder.py
_.off_maximum  # protocol_music_params.py
_.packed  # layered_scene_decoder.py
_.payload_length  # h60a6_effects.py
_.piece_count_max  # protocol_music_params.py
_.piece_count_min  # protocol_music_params.py
_.piece_len  # protocol_music_params.py
_.piece_length  # protocol_music_params.py
_.piece_num  # protocol_music_params.py
_.point_count  # h60a6_effects.py
_.reserved  # protocol_h6199.py
_.reversed_mac  # dreamview.py
_.unknown_tail  # protocol_h6199.py, protocol_transforms.py

# --- Protocol adapter field writes ---
# Kaitai field writes in generated_protocol_adapter.py. Assigning the field fills the wire frame; nothing reads it back.

_.a3_type  # generated_protocol_adapter.py
_.bottom_percent  # generated_protocol_adapter.py
_.dynamic  # generated_protocol_adapter.py
_.left_percent  # generated_protocol_adapter.py
_.manual  # generated_protocol_adapter.py
_.relative_brightness_percent  # generated_protocol_adapter.py
_.rhythm_response  # generated_protocol_adapter.py
_.right_percent  # generated_protocol_adapter.py
_.sound_type  # generated_protocol_adapter.py
_.strip_left_percent  # generated_protocol_adapter.py
_.strip_right_percent  # generated_protocol_adapter.py
_.top_percent  # generated_protocol_adapter.py
_.unknown_tail  # generated_protocol_adapter.py
_.zeros  # generated_protocol_adapter.py

# --- Keyword-only dataclass fields ---
# Dataclass fields that are only passed by keyword and serialised.

source_reference  # effect_catalogue.py

# --- Phase 2: to be analysed or removed ---
# TODO(#463): NOT intentional. Test-only hooks, test data living in production modules, and unconfirmed hits.
# Each one should be removed or tested through a real seam; do not add new entries here.

ALL_SEGMENTS  # light_commands.py
_.async_apply_saved_effect  # effect_application.py
_.async_flush  # effect_active_workspace.py, effect_identity.py, effect_user_state.py
_.async_reconcile  # effect_runtime.py
_.async_wait_idle  # effect_preview.py
_._control_lock  # coordinator.py
h6102_outbound_transform  # generated_protocol_adapter.py
MUSIC_MODE_SLUGS  # const.py
_.open_session  # effect_preview.py
parse_scene_body_param  # generated_protocol_adapter.py
parse_scene_type1_body_param  # generated_protocol_adapter.py
parse_status  # generated_protocol_adapter.py
SCENES  # scenes.py
WHITE_BALANCE_RESET  # h6199_calibration.py
WORKSHOP_PROTOCOL_FIXTURES  # effect_catalogue.py
