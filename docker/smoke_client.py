"""Run inside an isolated image with networking disabled; never invoke chat."""

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.backend.config import get_settings
from apps.backend.transcripts import TranscriptStore
from src.linger.services.memory import AccountContext, AutomaticMemoryCandidate, MemoryPolicyService

base = "http://127.0.0.1:8000"


def request(path, *, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        assert response.status == expected, (path, response.status, expected)
        payload = response.read().decode()
        return json.loads(payload) if "application/json" in response.headers.get("Content-Type", "") else payload


deadline = time.monotonic() + 180
while True:
    try:
        if request("/api/ready") == {"status": "ready"}:
            break
    except (URLError, TimeoutError, AssertionError):
        if time.monotonic() >= deadline:
            raise RuntimeError("Image did not become ready within 180 seconds") from None
        time.sleep(1)

assert request("/api/health")["status"] == "ok"
assert "<html" in request("/").lower()
assert request("/api/library")
request("/api/nonexistent", expected=404)
request("/.env", expected=404)
request("/api/history", expected=401)
request("/api/chat", body={"session_id": "unauthorized", "message": "Never call a model."}, expected=401)
for excluded in (".env", ".git", ".logfire", "evals", "synthetic-journal-evaluation", "memories"):
    assert not (Path("/app") / excluded).exists(), f"Private/development path included: {excluded}"

settings = get_settings()
memory = MemoryPolicyService(settings.linger_memory_dir)
transcripts = TranscriptStore(settings.linger_state_dir / "transcripts.sqlite3")
state = settings.linger_state_dir / "smoke.json"
credentials = {"username": "smoke-reader", "password": "synthetic-smoke-password"}
other_credentials = {"username": "smoke-other", "password": "synthetic-smoke-password"}
context = AccountContext("user:smoke-reader")
if sys.argv[1] == "seed":
    token = request("/api/auth/signup", body=credentials, expected=201)["token"]
    other_token = request("/api/auth/signup", body=other_credentials, expected=201)["token"]
    memory.set_capture_enabled(context, True)
    saved = memory.save_automatic(context, AutomaticMemoryCandidate(
        text="I enjoy reading about courage in novels.", source_event_id="deployment-smoke",
        review_allows_capture=True, contains_sensitive_content=False,
    ))
    transcripts.append_turn(context.account_id, "deployment-smoke", "turn-1", "A synthetic question.", "A synthetic released answer.")
    state.write_text(json.dumps({"token": token, "other_token": other_token, "memory_id": saved.record.memory_id}))

saved = json.loads(state.read_text())
assert request("/api/auth/me", token=saved["token"])["username"] == credentials["username"]
token = request("/api/auth/login", body=credentials)["token"]
history = request("/api/history", token=token)
assert len(history) == 1 and history[0]["session_id"] == "deployment-smoke"
assert history[0]["turns"][0]["assistant_message"] == "A synthetic released answer."
assert request("/api/history", token=saved["other_token"]) == []
records = memory.list_active(context)
assert len(records) == 1 and records[0].memory_id == saved["memory_id"]
assert records[0].text == "I enjoy reading about courage in novels."
assert memory.list_active(AccountContext("user:smoke-other")) == []
print(f"Offline image check passed: {sys.argv[1]}")
