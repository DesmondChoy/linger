"""Exercise real authenticated HTTP and SSE with two synthetic reader Lines."""

import json
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def request(path, *, body=None, token=None, stream=False, timeout=900):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=timeout) as response:
        if stream:
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                raise ValueError("Chat stream did not return an event stream.")
            return parse_sse(response.read().decode())
        return json.loads(response.read())


def parse_sse(body):
    frames = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        event, data = "message", []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            frames.append((event, json.loads("\n".join(data))))
    terminal = [(event, value) for event, value in frames if event in {"result", "error"}]
    if len(terminal) != 1 or terminal[0][0] != "result" or frames[-1] != terminal[0]:
        raise ValueError("Expected one final SSE result and no error events.")
    progress = [payload for event, payload in frames if event == "progress"]
    if not progress or [item["sequence"] for item in progress] != list(range(1, len(progress) + 1)):
        raise ValueError("Expected ordered progress before the final SSE result.")
    return {"frames": frames, "response": terminal[0][1]}


def validate_response(response, *, grounded):
    if not isinstance(response.get("reply"), str) or not response["reply"].strip():
        raise ValueError("The HTTP turn returned no reply.")
    release = response["inspection"]["release"]
    if release["failure_type"] is not None:
        raise ValueError("A failed agent or application stage cannot pass a live smoke check.")
    if response.get("memory_capture") is not None or release["capture"]["storage"] == "committed":
        raise ValueError("The live smoke unexpectedly captured memory.")
    if grounded:
        if release["release_source"] != "muse_candidate" or not release["released_evidence_ids"]:
            raise ValueError("Expected a grounded, released answer with cited book evidence.")
        if not any(source["kind"] == "book" for source in response["sources"]):
            raise ValueError("The grounded HTTP response has no reader-visible book source.")
    elif release["release_source"] not in {"application_clarification", "application_safe_decline"}:
        raise ValueError("The ambiguous reading boundary requires clarification or decline.")


def wait_until_ready():
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if request("/api/ready", timeout=min(5, deadline - time.monotonic()))["status"] == "ready":
                return
        except (URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError("The candidate did not become ready.")


def main():
    report = {"status": "failed", "turns": [], "semantic_review_required": True}
    try:
        wait_until_ready()
        username = "release-" + secrets.token_hex(6)
        token = request("/api/auth/signup", body={"username": username, "password": secrets.token_urlsafe(24)})["token"]
        backstory = json.loads(Path("/tmp/backstory.json").read_text())
        lines = {line["line_id"]: line["text"] for line in backstory["lines"]}
        for line_id, streamed in (("alice-race-line", False), ("alice-bottle-line", True)):
            entry = {"line_id": line_id, "streamed": streamed, "message": lines[line_id]}
            report["turns"].append(entry)
            response = request(
                "/api/chat/stream" if streamed else "/api/chat", token=token, stream=streamed,
                body={"session_id": "release-" + secrets.token_hex(8), "message": lines[line_id]},
            )
            entry["evidence"] = response
            validate_response(response["response"] if streamed else response, grounded=not streamed)
        from apps.backend.config import get_settings
        from src.linger.services.memory import AccountContext, MemoryPolicyService
        service = MemoryPolicyService(get_settings().linger_memory_dir)
        account = AccountContext("user:" + username)
        if service.capture_enabled(account) or service.list_active(account):
            raise ValueError("The live smoke changed its disabled memory policy or stored memory.")
        report["status"] = "passed"
    except HTTPError as error:
        report["error"] = f"HTTP request failed with status {error.code}."
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        Path("/tmp/http-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Live HTTP and SSE smoke: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
