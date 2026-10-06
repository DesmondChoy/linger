import json
import os
from pathlib import Path
import subprocess

import pytest

from docker.live_smoke import parse_sse, validate_response
from docker import live_smoke


def frame(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def test_sse_requires_ordered_progress_and_one_final_success():
    progress = frame("progress", {"sequence": 1})
    assert parse_sse(progress + frame("result", {"reply": "Synthetic"}))["response"]["reply"] == "Synthetic"
    for body in (progress, frame("result", {}), progress + frame("error", {}),
                 progress + frame("result", {}) + frame("result", {}),
                 frame("progress", {"sequence": 2}) + frame("result", {}),
                 progress + frame("result", {}) + frame("progress", {"sequence": 2})):
        with pytest.raises(ValueError):
            parse_sse(body)


def test_model_failure_cannot_pass_as_an_expected_decline():
    response = {"reply": "Unable to answer.", "inspection": {"release": {
        "release_source": "application_safe_decline", "failure_type": "model",
    }}}
    with pytest.raises(ValueError, match="failed agent"):
        validate_response(response, grounded=False)


def test_grounded_http_smoke_requires_reader_visible_evidence_and_no_capture():
    response = {"reply": "Synthetic answer.", "memory_capture": None, "sources": [{"kind": "book"}], "inspection": {"release": {
        "failure_type": None, "release_source": "muse_candidate", "released_evidence_ids": ["evidence-1"],
        "capture": {"storage": "suppressed"},
    }}}
    validate_response(response, grounded=True)
    response["sources"] = []
    with pytest.raises(ValueError, match="reader-visible"):
        validate_response(response, grounded=True)
    response["inspection"]["release"]["capture"]["storage"] = "committed"
    with pytest.raises(ValueError, match="captured"):
        validate_response(response, grounded=True)


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
