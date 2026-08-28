#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-runtime}"
kaitai="tools/ble/kaitai"
compiler_version="0.11"
roots_file="scripts/kaitai-runtime-roots.txt"
outputs_file="scripts/kaitai-runtime-outputs.txt"

compiler=()
resolve_compiler() {
  if [[ -n "${KAITAI_STRUCT_COMPILER:-}" ]]; then
    compiler=("$KAITAI_STRUCT_COMPILER")
  elif command -v kaitai-struct-compiler >/dev/null 2>&1; then
    compiler=(kaitai-struct-compiler)
  elif command -v mise >/dev/null 2>&1; then
    compiler=(mise exec "github:kaitai-io/kaitai_struct_compiler@$compiler_version" -- kaitai-struct-compiler)
  else
    echo "kaitai-struct-compiler $compiler_version is required; install it directly or run: mise install github:kaitai-io/kaitai_struct_compiler" >&2
    exit 1
  fi

  version="$("${compiler[@]}" --version 2>&1)"
  if [[ "$version" != "kaitai-struct-compiler $compiler_version" ]]; then
    echo "kaitai-struct-compiler $compiler_version is required; found: $version" >&2
    exit 1
  fi
}

if [[ "$mode" == verify ]]; then
  resolve_compiler
  printf '%s\n' "kaitai-struct-compiler $compiler_version"
  exit 0
fi

case "$mode" in
  runtime)
    output="${2:-custom_components/ha_govee_led_ble/generated_protocol}"
    mapfile -t specs < <(sed -e '/^[[:space:]]*$/d' -e '/^[[:space:]]*#/d' "$roots_file")
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
    echo "usage: $0 [runtime|all|verify] [output-directory]" >&2
    exit 2
    ;;
esac

resolve_compiler

stage="$PWD/.build/kaitai-stage-${BASHPID}"
trap 'rm -rf "$stage"' EXIT
rm -rf "$stage"
mkdir -p "$stage"
mkdir -p "$output"

inputs=()
for spec in "${specs[@]}"; do
  [[ "$spec" == *.ksy ]] || spec="$spec.ksy"
  inputs+=("$kaitai/$spec")
done

"${compiler[@]}" \
  --target python \
  --read-write \
  --import-path "$kaitai" \
  --outdir "$stage" \
  "${package_args[@]}" \
  "${inputs[@]}"

if [[ "$mode" == runtime ]]; then
  : >"$stage/__init__.py"
  mapfile -t expected < <(sed -e '/^[[:space:]]*$/d' -e '/^[[:space:]]*#/d' "$outputs_file" | LC_ALL=C sort)
  mapfile -t actual < <(find "$stage" -maxdepth 1 -type f -name '*.py' -printf '%f\n' | LC_ALL=C sort)
  if ! diff -u <(printf '%s\n' "${expected[@]}") <(printf '%s\n' "${actual[@]}"); then
    echo "runtime protocol output set differs from $outputs_file" >&2
    exit 1
  fi
else
  mapfile -t expected < <(find "$stage" -maxdepth 1 -type f -name '*.py' -printf '%f\n' | LC_ALL=C sort)
fi

for filename in "${expected[@]}"; do
  temporary="$output/.$filename.new-${BASHPID}"
  install -m 0644 "$stage/$filename" "$temporary"
  mv -f "$temporary" "$output/$filename"
done
