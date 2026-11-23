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
    mapfile -d '' -t specs < <(find "$kaitai" -type f -name '*.ksy' -printf '%P\0' | LC_ALL=C sort -z)
    package_args=()
    ;;
  runtime-from)
    if [[ -z "${2:-}" || -z "${3:-}" ]]; then
      echo "runtime-from requires a generated source and output directory" >&2
      exit 2
    fi
    source_output="$2"
    output="$3"
    mapfile -t expected < <(sed -e '/^[[:space:]]*$/d' -e '/^[[:space:]]*#/d' "$outputs_file" | LC_ALL=C sort)
    ;;
  *)
    echo "usage: $0 [runtime|all|runtime-from|verify] [output-directory]" >&2
    exit 2
    ;;
esac

stage="$PWD/.build/kaitai-stage-${BASHPID}"
trap 'rm -rf "$stage"' EXIT
rm -rf "$stage"
mkdir -p "$stage"
mkdir -p "$output"

if [[ "$mode" == runtime-from ]]; then
  python3 - "$source_output" "$stage" "${expected[@]}" <<'PY'
import ast
import sys
from pathlib import Path

source = Path(sys.argv[1])
stage = Path(sys.argv[2])
expected = sys.argv[3:]
package = "custom_components.ha_govee_led_ble.generated_protocol"
modules = {path.stem for path in source.glob("*.py")}

for filename in expected:
    generated = stage / filename
    if filename == "__init__.py":
        generated.write_text("", encoding="utf-8")
        continue
    original = source / filename
    if not original.is_file():
        raise SystemExit(f"generated source is missing {filename}")
    source_text = original.read_text(encoding="utf-8")
    lines = source_text.splitlines(keepends=True)
    for node in reversed(ast.parse(source_text).body):
        if not isinstance(node, ast.Import) or not all(alias.name in modules for alias in node.names):
            continue
        replacement = sorted(
            f"from {package} import {alias.name}" + (f" as {alias.asname}" if alias.asname else "") + "\n"
            for alias in node.names
        )
        lines[node.lineno - 1 : node.end_lineno] = replacement
    generated.write_text("".join(lines), encoding="utf-8")
PY
else
  resolve_compiler

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

  # Peer-schema imports come from an unordered compiler collection.
  python3 - "$stage" <<'PY'
import ast
import sys
from pathlib import Path

paths = list(Path(sys.argv[1]).glob("*.py"))
modules = {path.stem for path in paths}
for path in paths:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    imports = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Import | ast.ImportFrom)
        and all(alias.name in modules for alias in node.names)
    ]
    blocks = sorted("".join(lines[node.lineno - 1 : node.end_lineno]) for node in imports)
    for node, block in reversed(list(zip(imports, blocks, strict=True))):
        lines[node.lineno - 1 : node.end_lineno] = block.splitlines(keepends=True)
    path.write_text("".join(lines), encoding="utf-8")
PY
fi

if [[ "$mode" == runtime ]]; then
  : >"$stage/__init__.py"
  mapfile -t expected < <(sed -e '/^[[:space:]]*$/d' -e '/^[[:space:]]*#/d' "$outputs_file" | LC_ALL=C sort)
  mapfile -t actual < <(find "$stage" -maxdepth 1 -type f -name '*.py' -printf '%f\n' | LC_ALL=C sort)
  if ! diff -u <(printf '%s\n' "${expected[@]}") <(printf '%s\n' "${actual[@]}"); then
    echo "runtime protocol output set differs from $outputs_file" >&2
    exit 1
  fi
elif [[ "$mode" == all ]]; then
  mapfile -t expected < <(find "$stage" -maxdepth 1 -type f -name '*.py' -printf '%f\n' | LC_ALL=C sort)
  if ((${#expected[@]} != ${#specs[@]})); then
    echo "all-schema generation produced ${#expected[@]} modules from ${#specs[@]} schemas; check duplicate meta.id values" >&2
    exit 1
  fi
fi

python3 - "$stage" "$output" "${expected[@]}" <<'PY'
import os
import shutil
import sys
from pathlib import Path

stage = Path(sys.argv[1])
output = Path(sys.argv[2])
for filename in sys.argv[3:]:
    temporary = output / f".{filename}.new-{os.getpid()}"
    try:
        with temporary.open("wb") as destination, (stage / filename).open("rb") as source:
            shutil.copyfileobj(source, destination)
        temporary.chmod(0o644)
        os.replace(temporary, output / filename)
    finally:
        temporary.unlink(missing_ok=True)
PY
