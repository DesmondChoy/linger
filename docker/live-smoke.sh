#!/usr/bin/env bash
set -euo pipefail

image=${1:?Usage: bash docker/live-smoke.sh IMAGE}
: "${LINGER_MODEL:?Select the release model before making live calls}"
name="linger-live-smoke-$(date +%s)-$$"
mkdir -p release-evidence
cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    docker cp "$name:/tmp/http-smoke.json" release-evidence/http-smoke.json >/dev/null 2>&1 || true
    docker logs "$name" >&2 || true
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
docker run -d --name "$name" \
  --env LINGER_MODEL --env OPENAI_API_KEY --env ANTHROPIC_API_KEY --env GOOGLE_API_KEY \
  --env LOGFIRE_TOKEN --env LINGER_WEB_SEARCH_ENABLED=false \
  --tmpfs /var/lib/linger:uid=10001,gid=10001,mode=0700 "$image" >/dev/null
docker cp docker/live_smoke.py "$name:/tmp/linger-live-smoke.py"
docker cp synthetic-journal-evaluation/scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json "$name:/tmp/backstory.json"
docker exec "$name" python /tmp/linger-live-smoke.py
docker cp "$name:/tmp/http-smoke.json" release-evidence/http-smoke.json
python3 -c 'import json; assert json.load(open("release-evidence/http-smoke.json"))["status"] == "passed"'
