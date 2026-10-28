import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from docker.live_smoke import parse_sse, validate_response
from docker import live_smoke
from src.linger.services.memory import AccountContext, MemoryPolicyService, ScenarioProp


def frame(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def chat_response(*, source="muse_candidate", failure_type=None):
    candidate = source == "muse_candidate"
    return {
        "reply": "Synthetic answer." if candidate else "Unable to answer.",
        "memory_capture": None,
        "sources": [{"kind": "book", "label": "Alice's Adventures in Wonderland"}] if candidate else [],
        "trace": {"trace_id": "1" * 32},
        "inspection": {
            "muse_turn": {}, "context_resolution": {}, "traces": [], "prompt": "",
            "release": {
                "release_source": source, "provenance_verdicts": ["pass"] if candidate else [],
                "finding_codes": [], "revision_count": 0,
                "released_evidence_ids": ["pg11-v01b38ea4-ch03-ln0553-0587"] if candidate else [],
                "failure_stage": "muse_draft" if failure_type else None,
                "failure_type": failure_type, "failure_retryable": True if failure_type else None,
                "capture": {
                    "nomination": "unavailable", "provenance_decision": None,
                    "binding": "not_applicable", "storage": "suppressed", "reason_code": None,
                },
            },
        },
    }


def test_sse_requires_ordered_progress_and_one_final_success():
    progress = frame("progress", {"sequence": 1})
    assert parse_sse(progress + frame("result", {"reply": "Synthetic"}))["response"]["reply"] == "Synthetic"
    for body in (progress, frame("result", {}), progress + frame("error", {}),
                 progress + frame("result", {}) + frame("result", {}),
                 frame("progress", {"sequence": 2}) + frame("result", {}),
                 progress + frame("result", {}) + frame("progress", {"sequence": 2})):
        with pytest.raises(ValueError):
            parse_sse(body)


@pytest.mark.parametrize("failure_type", ["model", "application", "validation"])
@pytest.mark.parametrize("grounded", [False, True])
def test_completed_safe_failure_is_recorded_as_a_task_finding(failure_type, grounded):
    response = chat_response(source="application_safe_decline", failure_type=failure_type)
    findings = validate_response(response, grounded=grounded)

    assert f"runtime_{failure_type}_failure:muse_draft" in findings
    assert ("expected_grounded_book_answer_missing" in findings) == grounded


def test_missing_reader_source_is_a_task_finding_while_capture_blocks():
    response = chat_response()
    assert validate_response(response, grounded=True) == []
    response["sources"] = []
    assert validate_response(response, grounded=True) == ["reader_visible_book_source_missing"]
    response["inspection"]["release"]["capture"]["storage"] = "committed"
    with pytest.raises(ValueError, match="captured"):
        validate_response(response, grounded=True)


def test_intent_mismatch_and_missing_grounding_are_task_findings():
    response = chat_response()
    response["inspection"]["release"]["released_evidence_ids"] = []
    response["sources"] = []
    assert validate_response(response, grounded=True) == [
        "expected_grounded_book_answer_missing", "reader_visible_book_source_missing",
    ]
    assert validate_response(response, grounded=False) == ["expected_boundary_clarification_missing"]


def test_ambiguous_fresh_turn_cannot_release_even_canonical_book_evidence():
    response = chat_response()
    with pytest.raises(ValueError, match="without a confirmed reading boundary"):
        validate_response(response, grounded=False)


@pytest.mark.parametrize("mutation", [
    "missing_release", "null_release", "missing_capture", "missing_citation_observation",
    "missing_trace", "unknown_failure", "inconsistent_failure", "empty_reply",
])
def test_smoke_rejects_missing_or_invalid_required_http_observations(mutation):
    response = chat_response(source="application_safe_decline", failure_type="model")
    release = response["inspection"]["release"]
    if mutation == "missing_release":
        del response["inspection"]["release"]
    elif mutation == "null_release":
        response["inspection"]["release"] = None
    elif mutation == "missing_capture":
        del release["capture"]
    elif mutation == "missing_citation_observation":
        del release["released_evidence_ids"]
    elif mutation == "missing_trace":
        del response["trace"]
    elif mutation == "unknown_failure":
        release["failure_type"] = "unknown"
    elif mutation == "inconsistent_failure":
        release["failure_stage"] = None
    elif mutation == "empty_reply":
        response["reply"] = " "

    with pytest.raises(ValueError):
        validate_response(response, grounded=True)


@pytest.mark.parametrize("mutation", [
    "missing_approval", "rejected_approval", "failed_candidate", "guarded_candidate",
    "unknown_evidence", "empty_evidence", "duplicate_evidence", "later_chapter",
    "application_evidence", "application_sources", "unbound_sources", "foreign_sources",
])
def test_smoke_keeps_actual_release_authority_and_evidence_violations_blocking(mutation):
    response = chat_response()
    release = response["inspection"]["release"]
    if mutation == "missing_approval":
        release["provenance_verdicts"] = []
    elif mutation == "rejected_approval":
        release["provenance_verdicts"] = ["reject"]
    elif mutation == "failed_candidate":
        release.update(failure_type="model", failure_stage="muse_draft", failure_retryable=True)
    elif mutation == "guarded_candidate":
        release["security_block_category"] = "prompt_injection"
    elif mutation == "unknown_evidence":
        release["released_evidence_ids"] = ["invented-evidence"]
    elif mutation == "empty_evidence":
        release["released_evidence_ids"] = [""]
    elif mutation == "duplicate_evidence":
        release["released_evidence_ids"] *= 2
    elif mutation == "later_chapter":
        release["released_evidence_ids"] = ["pg11-v01b38ea4-ch04-ln0820-0851"]
    elif mutation == "application_evidence":
        release["release_source"] = "application_safe_decline"
    elif mutation == "application_sources":
        release["release_source"] = "application_clarification"
        release["released_evidence_ids"] = []
    elif mutation == "unbound_sources":
        release["released_evidence_ids"] = []
    elif mutation == "foreign_sources":
        response["sources"] = [{"kind": "memory", "label": "Another account's memory"}]

    with pytest.raises(ValueError):
        validate_response(response, grounded=True)


def prepare_main(monkeypatch, tmp_path):
    backstory = tmp_path / "backstory.json"
    backstory.write_text(json.dumps({"lines": [
        {"line_id": "alice-race-line", "text": "Synthetic grounded request."},
        {"line_id": "alice-bottle-line", "text": "Synthetic ambiguous boundary."},
    ]}))
    report = tmp_path / "http-smoke.json"
    monkeypatch.setattr(live_smoke, "BACKSTORY_PATH", backstory)
    monkeypatch.setattr(live_smoke, "REPORT_PATH", report)
    monkeypatch.setattr(live_smoke, "wait_until_ready", lambda: None)
    monkeypatch.setattr("apps.backend.config.get_settings", lambda: SimpleNamespace(linger_memory_dir=tmp_path / "memories"))
    return report


def test_completed_http_and_streamed_task_failures_keep_saved_evidence(monkeypatch, tmp_path):
    report_path = prepare_main(monkeypatch, tmp_path)
    monkeypatch.setattr(live_smoke.secrets, "token_hex", lambda _: "ABCDEF")
    api_memory = MemoryPolicyService(tmp_path / "memories", capture_enabled_by_default=True)
    accounts = []
    ungrounded_answer = chat_response()
    ungrounded_answer["inspection"]["release"]["released_evidence_ids"] = []
    ungrounded_answer["sources"] = []
    responses = iter((chat_response(source="application_safe_decline", failure_type="model"), ungrounded_answer))
    paths = []

    def request(path, **kwargs):
        paths.append(path)
        if path == "/api/auth/signup":
            username = kwargs["body"]["username"].lower()
            account = AccountContext("user:" + username)
            accounts.append(account)
            assert api_memory.capture_enabled(account)
            return {"username": username, "token": "synthetic-token"}
        assert kwargs["token"] == "synthetic-token"
        assert not api_memory.capture_enabled(accounts[0])
        assert api_memory.list_active(accounts[0]) == []
        response = next(responses)
        if kwargs["stream"]:
            return parse_sse(frame("progress", {"sequence": 1}) + frame("result", response))
        return response

    monkeypatch.setattr(live_smoke, "request", request)
    assert live_smoke.main() == 0
    report = json.loads(report_path.read_text())
    assert report["status"] == "passed"
    assert paths == ["/api/auth/signup", "/api/chat", "/api/chat/stream"]
    assert len(report["turns"]) == 2
    assert not api_memory.capture_enabled(accounts[0])
    assert all(turn["task_findings"] and turn["evidence"] for turn in report["turns"])
    assert {item["detail"] for item in report["task_findings"]} >= {
        "runtime_model_failure:muse_draft", "expected_grounded_book_answer_missing",
        "expected_boundary_clarification_missing",
    }


@pytest.mark.parametrize("problem", ["capture_still_enabled", "existing_memory"])
def test_invalid_memory_setup_stops_before_chat(monkeypatch, tmp_path, problem):
    report_path = prepare_main(monkeypatch, tmp_path)
    api_memory = MemoryPolicyService(tmp_path / "memories", capture_enabled_by_default=True)
    if problem == "capture_still_enabled":
        monkeypatch.setattr(MemoryPolicyService, "set_capture_enabled", lambda *args: None)
    accounts, paths = [], []

    def request(path, **kwargs):
        paths.append(path)
        assert path == "/api/auth/signup"
        username = kwargs["body"]["username"]
        account = AccountContext("user:" + username)
        accounts.append(account)
        if problem == "existing_memory":
            api_memory.load_scenario_props(account, "smoke", [ScenarioProp("existing", "Existing synthetic memory.", None)])
        return {"username": username, "token": "synthetic-token"}

    monkeypatch.setattr(live_smoke, "request", request)
    assert live_smoke.main() == 1
    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert "before chat" in report["error"]
    assert paths == ["/api/auth/signup"]
    if problem == "existing_memory":
        assert len(api_memory.list_active(accounts[0])) == 1


@pytest.mark.parametrize("change", ["policy_deleted", "capture_reenabled", "stored_memory"])
def test_smoke_detects_policy_or_storage_changes_after_chat(monkeypatch, tmp_path, change):
    report_path = prepare_main(monkeypatch, tmp_path)
    api_memory = MemoryPolicyService(tmp_path / "memories", capture_enabled_by_default=True)
    accounts = []

    def request(path, **kwargs):
        if path == "/api/auth/signup":
            username = kwargs["body"]["username"]
            accounts.append(AccountContext("user:" + username))
            return {"username": username, "token": "synthetic-token"}
        account = accounts[0]
        assert not api_memory.capture_enabled(account)
        response = chat_response() if path == "/api/chat" else chat_response(source="application_clarification")
        if kwargs["stream"]:
            if change == "policy_deleted":
                policy, = (tmp_path / "memories").rglob("policy.json")
                policy.unlink()
            elif change == "capture_reenabled":
                api_memory.set_capture_enabled(account, True)
            else:
                api_memory.load_scenario_props(account, "smoke", [ScenarioProp("unexpected", "Unexpected synthetic memory.", None)])
            return parse_sse(frame("progress", {"sequence": 1}) + frame("result", response))
        return response

    monkeypatch.setattr(live_smoke, "request", request)
    assert live_smoke.main() == 1
    report = json.loads(report_path.read_text())
    assert len(report["turns"]) == 2
    assert report["status"] == "failed"
    assert "changed its disabled memory policy or stored memory" in report["error"]
    if change == "stored_memory":
        assert len(api_memory.list_active(accounts[0])) == 1


def test_http_authentication_error_keeps_smoke_failed_and_records_error(monkeypatch, tmp_path):
    report_path = prepare_main(monkeypatch, tmp_path)

    def request(*args, **kwargs):
        raise HTTPError("http://synthetic/api/auth/signup", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(live_smoke, "request", request)
    assert live_smoke.main() == 1
    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert report["error"] == "HTTP request failed with status 401."


def test_non_ready_response_still_obeys_readiness_deadline(monkeypatch):
    ticks = iter((0, 1, 1, 181))
    monkeypatch.setattr(live_smoke.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(live_smoke.time, "sleep", lambda _: None)
    timeouts = []
    monkeypatch.setattr(live_smoke, "request", lambda path, *, timeout: timeouts.append(timeout) or {"status": "starting"})
    with pytest.raises(RuntimeError, match="did not become ready"):
        live_smoke.wait_until_ready()
    assert timeouts == [5]


@pytest.mark.parametrize("report_status", ["passed", "missing", "failed"])
def test_live_smoke_requires_saved_passing_evidence(tmp_path, report_status):
    fake_docker = tmp_path / "docker"
    fake_docker.write_text("""#!/usr/bin/env bash
if [[ "$1" == cp && "$2" == *:/tmp/http-smoke.json ]]; then
  if [[ "$REPORT_STATUS" == missing ]]; then exit 1; fi
  printf '{"status":"%s"}\\n' "$REPORT_STATUS" > "$3"
fi
""")
    fake_docker.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "docker/live-smoke.sh"
    result = subprocess.run(
        ["bash", str(script), "synthetic-image"], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "LINGER_MODEL": "test:model", "REPORT_STATUS": report_status},
    )
    assert (result.returncode == 0) == (report_status == "passed")
