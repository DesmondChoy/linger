"""Exercise real authenticated HTTP and SSE with two synthetic reader Lines."""

import json
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"
BACKSTORY_PATH = Path("/tmp/backstory.json")
REPORT_PATH = Path("/tmp/http-smoke.json")


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
    from apps.backend.librarian import Librarian
    from apps.backend.schemas import ChatResponse

    observed = ChatResponse.model_validate(response)
    if not observed.reply.strip():
        raise ValueError("The HTTP turn returned no reply.")
    release = observed.inspection.release
    if release is None or "released_evidence_ids" not in response["inspection"]["release"]:
        raise ValueError("The HTTP turn omitted its release observations.")
    if observed.memory_capture is not None or release.capture.storage == "committed":
        raise ValueError("The live smoke unexpectedly captured memory.")
    evidence_ids = release.released_evidence_ids
    if len(evidence_ids) != len(set(evidence_ids)) or any(not identity.strip() for identity in evidence_ids):
        raise ValueError("The HTTP turn has malformed released evidence identities.")
    if release.release_source == "muse_candidate":
        if (release.failure_type is not None or release.security_block_category is not None
                or not release.provenance_verdicts or release.provenance_verdicts[-1] != "pass"):
            raise ValueError("The HTTP turn released a Muse answer without successful approval.")
        if not grounded and evidence_ids:
            raise ValueError("The ambiguous HTTP turn released book evidence without a confirmed reading boundary.")
        librarian = Librarian()
        for identity in evidence_ids:
            record = librarian.fetch_by_id(identity)
            if record is None:
                raise ValueError("The HTTP turn released an invalid book evidence identity.")
            if grounded and (record.work_id != "pg11" or record.part_id != "main"
                             or record.chapter_number is None or record.chapter_number > 3):
                raise ValueError("The grounded HTTP turn released evidence beyond its authorized book scope.")
        if any(source.kind != "book" for source in observed.sources):
            raise ValueError("The live smoke released a source outside its empty-memory, web-disabled setup.")
        if observed.sources and not evidence_ids:
            raise ValueError("The HTTP turn reported sources without released evidence identities.")
    elif evidence_ids or observed.sources:
        raise ValueError("An application-authored response cannot release source evidence.")
    findings = []
    if release.failure_type is not None:
        findings.append(f"runtime_{release.failure_type}_failure:{release.failure_stage}")
    if grounded:
        if release.release_source != "muse_candidate" or not evidence_ids:
            findings.append("expected_grounded_book_answer_missing")
        if not any(source.kind == "book" for source in observed.sources):
            findings.append("reader_visible_book_source_missing")
    elif release.release_source not in {"application_clarification", "application_safe_decline"}:
        findings.append("expected_boundary_clarification_missing")
    return findings


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
    report = {"status": "failed", "turns": [], "task_findings": [], "semantic_review_required": True}
    try:
        wait_until_ready()
        username = "release-" + secrets.token_hex(6)
        signed_in = request("/api/auth/signup", body={"username": username, "password": secrets.token_urlsafe(24)})
        token = signed_in["token"]
        from apps.backend.config import get_settings
        from src.linger.services.memory import AccountContext, MemoryPolicyService
        service = MemoryPolicyService(get_settings().linger_memory_dir, capture_enabled_by_default=True)
        account = AccountContext("user:" + signed_in["username"])
        service.set_capture_enabled(account, False)
        if service.capture_enabled(account) or service.list_active(account):
            raise ValueError("The live smoke requires disabled capture and empty memory before chat.")
        backstory = json.loads(BACKSTORY_PATH.read_text())
        lines = {line["line_id"]: line["text"] for line in backstory["lines"]}
        for line_id, streamed in (("alice-race-line", False), ("alice-bottle-line", True)):
            entry = {"line_id": line_id, "streamed": streamed, "message": lines[line_id]}
            report["turns"].append(entry)
            response = request(
                "/api/chat/stream" if streamed else "/api/chat", token=token, stream=streamed,
                body={"session_id": "release-" + secrets.token_hex(8), "message": lines[line_id]},
            )
            entry["evidence"] = response
            findings = validate_response(response["response"] if streamed else response, grounded=not streamed)
            entry["task_findings"] = findings
            report["task_findings"].extend({"line_id": line_id, "detail": finding} for finding in findings)
        if service.capture_enabled(account) or service.list_active(account):
            raise ValueError("The live smoke changed its disabled memory policy or stored memory.")
        report["status"] = "passed"
    except HTTPError as error:
        report["error"] = f"HTTP request failed with status {error.code}."
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Live HTTP and SSE smoke: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
