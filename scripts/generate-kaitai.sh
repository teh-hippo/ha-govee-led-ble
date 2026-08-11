#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-runtime}"
kaitai="tools/ble/kaitai"

case "$mode" in
  runtime)
    output="${2:-custom_components/ha_govee_led_ble/generated_protocol}"
    specs=(
      command_write
      diy_type04
      h6199_command_write
      h6199_effect_upload
      h6199_status_query
      h6199_status_reply
      h6199_wifi_provision
      h6199_wifi_result
      music_body
      music_stream
      scene_body
      scene_type1_body
      status_query
      status_reply
    )
    package_args=(
      --python-package
      custom_components.ha_govee_led_ble.generated_protocol
    )
    ;;
  all)
    if [[ -z "${2:-}" ]]; then
      echo "all-schema generation requires an output directory" >&2
      exit 2
    fi
    output="$2"
    specs=()
    for spec in "$kaitai"/*.ksy; do
      specs+=("${spec##*/}")
    done
    package_args=()
    ;;
  *)
    echo "usage: $0 [runtime|all] [output-directory]" >&2
    exit 2
    ;;
esac

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$output"

inputs=()
for spec in "${specs[@]}"; do
  [[ "$spec" == *.ksy ]] || spec="$spec.ksy"
  inputs+=("$kaitai/$spec")
done

mise exec -- kaitai-struct-compiler \
  --target python \
  --read-write \
  --import-path "$kaitai" \
  --outdir "$stage" \
  "${package_args[@]}" \
  "${inputs[@]}"

if [[ "$mode" == runtime ]]; then
  : >"$stage/__init__.py"
fi

find "$output" -maxdepth 1 -type f -name '*.py' -delete
cp "$stage"/*.py "$output"/
