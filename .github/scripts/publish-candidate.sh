#!/usr/bin/env bash
set -euo pipefail

: "${CANDIDATE_SHA:?}" "${CI_RUN_ID:?}" "${GITHUB_REPOSITORY:?}" "${EVALUATED_IMAGE_ID:?}" "${PUBLICATION_ROUTE:?}"
: "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}"
jq -e --arg sha "$CANDIDATE_SHA" --arg image "$EVALUATED_IMAGE_ID" --arg route "$PUBLICATION_ROUTE" \
  '.candidate_sha == $sha and .image_id == $image and .publication.route == $route and .live_evaluations_enabled == true' \
  release-evidence/publication.json > /dev/null

docker load --input release-image/image.tar.gz
python3 .github/scripts/release_candidate.py image --sha "$CANDIDATE_SHA" \
  --image-id "$EVALUATED_IMAGE_ID" > release-evidence/image.json
repository="ghcr.io/$(printf '%s' "$GITHUB_REPOSITORY" | tr '[:upper:]' '[:lower:]')"
reference="$repository:release-$CANDIDATE_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
docker tag "$EVALUATED_IMAGE_ID" "$reference"
printf '%s' "$GH_TOKEN" | docker login ghcr.io --username "$GITHUB_ACTOR" --password-stdin
trap 'docker logout ghcr.io' EXIT
docker push "$reference"
release_image=$(docker image inspect "$reference" --format '{{json .RepoDigests}}' | \
  jq -er --arg repository "$repository" \
    '[.[] | select(startswith($repository + "@sha256:"))] | unique | if length == 1 then .[0] else error("Expected one published digest") end')
if [[ ! "$release_image" =~ @sha256:[a-f0-9]{64}$ ]]; then
  echo 'Registry did not return an immutable image digest' >&2
  exit 1
fi
export RELEASE_IMAGE="$release_image"
python3 - <<'PYTHON'
import json
import os
from pathlib import Path
record = {key.lower(): os.environ[key] for key in (
    "CANDIDATE_SHA", "CI_RUN_ID", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RELEASE_IMAGE",
)}
record["image"] = json.loads(Path("release-evidence/image.json").read_text())
record["authorization"] = json.loads(Path("release-evidence/publication.json").read_text())
Path("release-evidence/approved-release.json").write_text(json.dumps(record, indent=2) + "\n")
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
    output.write(f"Published image: `{record['release_image']}`\n\nDeploy this digest with `LINGER_IMAGE`.\n")
PYTHON
