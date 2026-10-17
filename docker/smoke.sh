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
root_owned_state() {
  docker run --rm -i --user 0 --network none --entrypoint python \
    --mount "type=volume,src=$volume,dst=/var/lib/linger" "$image" - <<'PY'
import os
from pathlib import Path

state = Path('/var/lib/linger')
marker = state / 'existing-root-state.txt'
if not marker.exists():
    marker.write_text('Existing Railway state must survive image migration.\n')
for directory, subdirectories, files in os.walk(state):
    for name in subdirectories + files:
        path = Path(directory) / name
        assert not path.is_symlink(), path
        os.chown(path, 0, 0)
    os.chown(directory, 0, 0)
os.chmod(state, 0o700)
os.chmod(marker, 0o600)
PY
}
start() {
  local user_options=()
  if [[ $1 == "$image" ]]; then user_options=(--user 0); fi
  docker run -d --name "$name" --network none \
    "${user_options[@]}" \
    --env LINGER_MODEL=openai:gpt-6-luna \
    --env OPENAI_API_KEY=offline-smoke-placeholder \
    --env LINGER_WEB_SEARCH_ENABLED=false \
    --env LOGFIRE_SEND_TO_LOGFIRE=false \
    --mount "type=volume,src=$volume,dst=/var/lib/linger" "$1" >/dev/null
}
check() {
  docker exec --user 10001 -i "$name" python - "$1" < "$script_dir/smoke_client.py"
  docker exec --user 10001 -i "$name" python - <<'PY'
import os
from pathlib import Path

assert os.geteuid() == 10001
status = Path('/proc/1/status').read_text().splitlines()
for field in ('Uid:', 'Gid:'):
    values = next(line for line in status if line.startswith(field)).split()[1:]
    assert values == ['10001'] * 4, (field, values)
state = Path('/var/lib/linger')
assert (state / 'existing-root-state.txt').read_text() == 'Existing Railway state must survive image migration.\n'
for directory, subdirectories, files in os.walk(state):
    assert Path(directory).stat().st_uid == 10001, directory
    for name in subdirectories + files:
        path = Path(directory) / name
        assert path.stat().st_uid == 10001, path
PY
}
root_owned_state
start "$image"
check seed
docker restart "$name" >/dev/null
check verify
# Exercise migration of populated SQLite and memory state from the old service.
docker rm -f "$name" >/dev/null
root_owned_state
start "$image"
check verify
if [[ $previous_image != "$image" ]]; then
  docker rm -f "$name" >/dev/null
  start "$previous_image"
  check verify
fi
echo 'Offline deployment smoke passed: UI, readiness, auth, isolation, root-volume migration, uid 10001, persisted state, restart and image replacement.'
