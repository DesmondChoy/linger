#!/usr/bin/env bash
set -euo pipefail

: "${CANDIDATE_SHA:?}" "${CI_RUN_ID:?}" "${GITHUB_REPOSITORY:?}" "${EVALUATED_IMAGE_ID:?}" "${PUBLICATION_ROUTE:?}"
jq -e --arg sha "$CANDIDATE_SHA" --arg image "$EVALUATED_IMAGE_ID" --arg route "$PUBLICATION_ROUTE" \
  '.candidate_sha == $sha and .image_id == $image and .publication.route == $route and .live_evaluations_enabled == true' \
  release-evidence/publication.json > /dev/null
repository="ghcr.io/$(printf '%s' "$GITHUB_REPOSITORY" | tr '[:upper:]' '[:lower:]')"
reference="$repository:release-$CANDIDATE_SHA-$CI_RUN_ID"
for arch in amd64 arm64; do
  directory="candidates/linger-candidate-$CANDIDATE_SHA-$arch"
  python3 .github/scripts/release_candidate.py verify --sha "$CANDIDATE_SHA" \
    --arch "$arch" --directory "$directory" > "release-evidence/$arch.json"
  image_id=$(jq -r .image_id "release-evidence/$arch.json")
  if [ "$arch" = amd64 ] && [ "$image_id" != "$EVALUATED_IMAGE_ID" ]; then
    echo 'Published image differs from behavioral evaluation image' >&2
    exit 1
  fi
  docker tag "$image_id" "$reference-$arch"
done

printf '%s' "$GH_TOKEN" | docker login ghcr.io --username "$GITHUB_ACTOR" --password-stdin
trap 'docker logout ghcr.io' EXIT
docker push "$reference-amd64"
docker push "$reference-arm64"
docker manifest create "$reference" "$reference-amd64" "$reference-arm64"
digest=$(docker manifest push "$reference")
if [[ ! "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo 'Registry did not return an immutable manifest digest' >&2
  exit 1
fi
export RELEASE_IMAGE="$repository@$digest"
python3 - <<'PY'
import json
import os
from pathlib import Path
record = {key.lower(): os.environ[key] for key in (
    "CANDIDATE_SHA", "CI_RUN_ID", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RELEASE_IMAGE",
)}
record["platforms"] = {arch: json.loads(Path(f"release-evidence/{arch}.json").read_text()) for arch in ("amd64", "arm64")}
record["authorization"] = json.loads(Path("release-evidence/publication.json").read_text())
Path("release-evidence/approved-release.json").write_text(json.dumps(record, indent=2) + "\n")
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
    output.write(f"Published image: `{record['release_image']}`\n\nDeploy this digest with `LINGER_IMAGE`.\n")
PY
