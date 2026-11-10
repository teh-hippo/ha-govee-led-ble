#!/usr/bin/env bash
set -euo pipefail

tag="$1"
target_sha="$2"
prerelease="$3"
notes="$4"
shift 4

[[ "$target_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$prerelease" == true || "$prerelease" == false ]]
[[ -s "$notes" && "$#" -gt 0 ]]

error_file="$(mktemp)"
trap 'rm -f "$error_file"' EXIT

if object="$(gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/$tag" 2> "$error_file")"; then
  while [[ "$(jq -r '.object.type' <<< "$object")" == tag ]]; do
    object_sha="$(jq -r '.object.sha' <<< "$object")"
    object="$(gh api "repos/$GITHUB_REPOSITORY/git/tags/$object_sha")"
  done
  if [[ "$(jq -r '.object.type' <<< "$object")" != commit ||
        "$(jq -r '.object.sha' <<< "$object")" != "$target_sha" ]]; then
    echo "Existing tag does not identify the requested commit; refusing to replace it." >&2
    exit 1
  fi
else
  if ! grep -q 'HTTP 404' "$error_file"; then
    cat "$error_file" >&2
    exit 1
  fi
  gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs" \
    -f "ref=refs/tags/$tag" -f "sha=$target_sha"
fi

latest=true
if [[ "$prerelease" == true ]]; then
  latest=false
fi
gh release create "$tag" "$@" \
  --repo "$GITHUB_REPOSITORY" \
  --verify-tag \
  --target "$target_sha" \
  --title "$tag" \
  --notes-file "$notes" \
  --prerelease="$prerelease" \
  --latest="$latest"
