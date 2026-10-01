#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo 'Usage: bash docker/smoke.sh IMAGE [PREVIOUS_IMAGE]' >&2
  exit 2
fi
image=$1
previous_image=${2:-$image}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
name="linger-offline-smoke-$(date +%s)-$$"
volume="$name-state"
cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then docker logs "$name" >&2 || true; fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
docker volume create "$volume" >/dev/null
start() {
  docker run -d --name "$name" --network none \
    --env LINGER_MODEL=openai:gpt-6-luna \
    --env OPENAI_API_KEY=offline-smoke-placeholder \
    --env LINGER_WEB_SEARCH_ENABLED=false \
    --env LOGFIRE_SEND_TO_LOGFIRE=false \
    --mount "type=volume,src=$volume,dst=/var/lib/linger" "$1" >/dev/null
}
check() {
  docker exec -i "$name" python - "$1" < "$script_dir/smoke_client.py"
}
start "$image"
check seed
docker restart "$name" >/dev/null
check verify
# Replace the container, retaining the same state volume. Supply a previous
# approved image to exercise actual version rollback instead of recreation.
docker rm -f "$name" >/dev/null
start "$previous_image"
check verify
echo 'Offline deployment smoke passed: UI, readiness, auth, isolation, persisted state, restart and image replacement.'
