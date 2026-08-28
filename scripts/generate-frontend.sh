#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

output="${1:-custom_components/ha_govee_led_ble/frontend}"
expected_node="$(cat .node-version)"
actual_node="$(node --version)"
if [[ "$actual_node" != "v$expected_node" ]]; then
  echo "Node.js $expected_node is required; found $actual_node" >&2
  exit 1
fi

stage="$PWD/.build/frontend-stage-${BASHPID}"
trap 'rm -rf "$stage"' EXIT
rm -rf "$stage"
mkdir -p "$stage" "$output"

FRONTEND_OUT_DIR="$stage" npm --prefix frontend run build

mapfile -t expected < <(python3 - "$stage/manifest.json" <<'PY'
import json
import re
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest.get("bootstrap") != "effect-studio-bootstrap.js":
    raise SystemExit("frontend manifest contains an invalid bootstrap filename")
chunks = manifest.get("chunks")
if not isinstance(chunks, list) or not all(
    isinstance(chunk, str)
    and re.fullmatch(r"effect-studio-[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]+\.js", chunk)
    for chunk in chunks
):
    raise SystemExit("frontend manifest contains invalid chunk filenames")
if len(chunks) != len(set(chunks)):
    raise SystemExit("frontend manifest contains duplicate chunk filenames")
for filename in sorted(["effect-studio-bootstrap.js", *chunks, "manifest.json"]):
    print(filename)
PY
)

[[ -f "$stage/effect-studio-bootstrap.js" ]] || {
  echo "frontend bootstrap effect-studio-bootstrap.js was not generated" >&2
  exit 1
}

mapfile -t generated < <(
  find "$stage" -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort
)
if ! diff -u <(printf '%s\n' "${expected[@]}") <(printf '%s\n' "${generated[@]}"); then
  echo "frontend build output does not match its manifest" >&2
  exit 1
fi

if [[ -f "$output/manifest.json" ]]; then
  mapfile -t previous_chunks < <(python3 - "$output/manifest.json" <<'PY'
import json
import re
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for chunk in manifest.get("chunks", []):
    if isinstance(chunk, str) and re.fullmatch(
        r"effect-studio-[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]+\.js",
        chunk,
    ):
        print(chunk)
PY
)
  for filename in "${previous_chunks[@]}"; do
    rm -f "$output/$filename"
  done
fi

for filename in "${expected[@]}"; do
  temporary="$output/.$filename.new-${BASHPID}"
  install -m 0644 "$stage/$filename" "$temporary"
  mv -f "$temporary" "$output/$filename"
done
