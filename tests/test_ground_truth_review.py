"""Tests for independent Ground truth adoption and the local review handoff."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from evals.synthetic_journals.adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
)
from evals.synthetic_journals.models import (
    AdoptedProposalDecision,
    GroundTruthAdoption,
    HumanGroundTruthReviewer,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / ".agents"
    / "skills"
    / "review-synthetic-ground-truth"
    / "scripts"
    / "ground_truth_reviewer.py"
)
SPEC = importlib.util.spec_from_file_location("ground_truth_reviewer", SCRIPT)
assert SPEC and SPEC.loader
reviewer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reviewer
SPEC.loader.exec_module(reviewer)

CAPTURE_PACKAGE = (
    ROOT
    / "synthetic-journal-evaluation"
    / "packages"
    / "2026-08-23T182725+0800"
)
def _copy_package(source: Path, destination: Path) -> None:
    destination.mkdir()
    for name in ("backstory.json", "ground-truth.json", "pre-generation-report.md"):
        shutil.copyfile(source / name, destination / name)


def _write_curation_package(destination: Path) -> None:
    """Build a compact package from the maintained Sculptor baseline cases."""

    case_paths = sorted((ROOT / "evals" / "sculptor" / "cases").glob("*.json"))
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in case_paths]
    backstory_id = "backstory-ground-truth-review-test"
    person_id = "person-ground-truth-review-test"
    account_id = "eval-account-sculptor"
    props: list[dict[str, object]] = []
    scenes: list[dict[str, object]] = []
    proposals: list[dict[str, object]] = []

    for order, case in enumerate(cases, start=1):
        scene_id = f"scene-{case['primary_behavior']}"
        memories = case["input"]["memories"]
        prop_ids = [memory["memory_id"] for memory in memories]
        scenes.append(
            {
                "scene_id": scene_id,
                "backstory_id": backstory_id,
                "objective_ids": ["bounded_memory_curation"],
                "order": order,
                "fresh_session": True,
                "prop_ids": prop_ids,
                "line_ids": [],
                "offline_input_ids": [],
            }
        )
        for memory in memories:
            props.append(
                {
                    "prop_id": memory["memory_id"],
                    "backstory_id": backstory_id,
                    "person_id": person_id,
                    "evaluation_account_id": account_id,
                    "source_text": memory["text"],
                    "lifecycle": [{"scene_id": scene_id, "state": "active"}],
                }
            )
        proposals.append(
            {
                "proposal_id": f"proposal-{case['primary_behavior']}",
                "scene_id": scene_id,
                "objective_id": "bounded_memory_curation",
                "expected_outcomes": ["Return the expected typed curation response."],
                "prohibited_outcomes": ["Do not mutate original memories."],
                "exact_spans": [
                    {
                        "source_kind": "prop",
                        "source_id": memory["memory_id"],
                        "start_codepoint": 0,
                        "end_codepoint": len(memory["text"]),
                        "text": memory["text"],
                    }
                    for memory in memories
                ],
                "evidence": [
                    {
                        "kind": "prop",
                        "evidence_id": f"evidence-{memory['memory_id']}",
                        "prop_id": memory["memory_id"],
                    }
                    for memory in memories
                ],
                "curation": {
                    "primary_behavior": case["primary_behavior"],
                    "expected": case["expected"],
                },
            }
        )

    backstory = {
        "objective_ids": ["bounded_memory_curation"],
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": backstory_id,
            "person_id": person_id,
            "evaluation_account_id": account_id,
            "context": "Test-only curation review package.",
        },
        "props": props,
        "scenes": scenes,
        "lines": [],
        "offline_inputs": [],
    }
    backstory_bytes = (json.dumps(backstory, indent=2) + "\n").encode()
    ground_truth = {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }

    destination.mkdir()
    (destination / "backstory.json").write_bytes(backstory_bytes)
    (destination / "ground-truth.json").write_text(
        json.dumps(ground_truth, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "pre-generation-report.md").write_text(
        "# Pre-generation report\n\nTest-only review fixture.\n",
        encoding="utf-8",
    )


def _state(package: Path, ui: Path) -> reviewer.ReviewState:
    return reviewer.create_review_state(
        argparse.Namespace(
            backstory=package / "backstory.json",
            ground_truth=package / "ground-truth.json",
            adoption=None,
            reviewer_id="independent.developer@example.com",
            ui=ui,
            timeout=30,
        )
    )


def _start_server(
    state: reviewer.ReviewState,
) -> tuple[reviewer.ReviewServer, threading.Thread, str]:
    server = reviewer.ReviewServer(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _post(base_url: str, token: str, body: dict[str, object]) -> dict[str, object]:
    request = Request(
        f"{base_url}/api/decision",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Review-Token": token,
        },
        method="POST",
    )
    with urlopen(request) as response:
        return json.load(response)


@pytest.fixture
def built_ui(tmp_path: Path) -> Path:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("review", encoding="utf-8")
    return ui


def test_review_payload_joins_lines_props_and_typed_ground_truth(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    capture = tmp_path / "capture"
    curation = tmp_path / "curation"
    _copy_package(CAPTURE_PACKAGE, capture)
    _write_curation_package(curation)

    capture_payload = _state(capture, built_ui).payload
    curation_payload = _state(curation, built_ui).payload

    assert len(capture_payload["rows"]) == 11
    assert capture_payload["rows"][0]["inputs"][0]["kind"] == "Line"
    assert capture_payload["rows"][0]["inputs"][0]["text"].startswith(
        "I put the rice on"
    )
    assert capture_payload["replay"]["supported"] is True
    assert "provider-backed" in capture_payload["replay"]["note"]
    assert "billable model calls" in capture_payload["replay"]["note"]
    assert len(curation_payload["rows"]) == 5
    assert {item["kind"] for item in curation_payload["rows"][0]["inputs"]} == {
        "Prop"
    }
    assert curation_payload["rows"][0]["curation"] is not None
    assert curation_payload["report"]["text"].startswith("# Pre-generation report")


def test_make_changes_returns_to_agent_without_writing_adoption(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _copy_package(CAPTURE_PACKAGE, package)
    state = _state(package, built_ui)
    server, thread, base_url = _start_server(state)
    first_id = state.proposal_ids[0]
    try:
        response = _post(
            base_url,
            state.token,
            {
                "action": "make_changes",
                "reviewedProposalIds": [],
                "flaggedProposalIds": [first_id],
            },
        )
        assert response == {"status": "make_changes"}
        thread.join(timeout=2)
        assert state.result is not None
        assert state.result["decision"] == "make_changes"
        assert state.result["flagged_proposal_ids"] == [first_id]
        assert not state.adoption_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_confirm_requires_every_row_and_writes_exact_adoption(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _write_curation_package(package)
    state = _state(package, built_ui)
    server, thread, base_url = _start_server(state)
    try:
        with pytest.raises(HTTPError) as partial:
            _post(
                base_url,
                state.token,
                {
                    "action": "confirm",
                    "reviewedProposalIds": list(state.proposal_ids[:-1]),
                    "flaggedProposalIds": [],
                },
            )
        assert partial.value.code == 422
        assert state.result is None

        response = _post(
            base_url,
            state.token,
            {
                "action": "confirm",
                "reviewedProposalIds": list(state.proposal_ids),
                "flaggedProposalIds": [],
            },
        )
        assert response == {"status": "confirm"}
        thread.join(timeout=2)
        assert state.result is not None
        assert state.result["decision"] == "confirm"
        assert state.result["replay_supported"] is True
        assert state.adoption_path.is_file()
        _, ground_truth, adoption = validate_ground_truth_adoption_files(
            package / "backstory.json",
            package / "ground-truth.json",
            state.adoption_path,
        )
        assert adoption.ground_truth_status == "adopted"
        assert adoption.reviewer.reviewer_id == "independent.developer@example.com"
        assert len(adoption.decisions) == len(ground_truth.proposals)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_confirm_rejects_files_changed_while_review_is_open(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _copy_package(CAPTURE_PACKAGE, package)
    state = _state(package, built_ui)
    server, thread, base_url = _start_server(state)
    ground_truth_path = package / "ground-truth.json"
    original = ground_truth_path.read_text(encoding="utf-8")
    ground_truth_path.write_text(original + "\n", encoding="utf-8")
    try:
        with pytest.raises(HTTPError) as stale:
            _post(
                base_url,
                state.token,
                {
                    "action": "confirm",
                    "reviewedProposalIds": list(state.proposal_ids),
                    "flaggedProposalIds": [],
                },
            )
        assert stale.value.code == 422
        assert not state.adoption_path.exists()
        assert state.result is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_make_changes_rejects_approved_and_flagged_overlap(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _copy_package(CAPTURE_PACKAGE, package)
    state = _state(package, built_ui)
    server, thread, base_url = _start_server(state)
    first_id = state.proposal_ids[0]
    try:
        with pytest.raises(HTTPError) as overlap:
            _post(
                base_url,
                state.token,
                {
                    "action": "make_changes",
                    "reviewedProposalIds": [first_id],
                    "flaggedProposalIds": [first_id],
                },
            )
        assert overlap.value.code == 422
        assert state.result is None
        assert not state.adoption_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_adoption_rejects_stale_or_partial_decisions(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _copy_package(CAPTURE_PACKAGE, package)
    state = _state(package, built_ui)
    ground_truth = json.loads(
        (package / "ground-truth.json").read_text(encoding="utf-8")
    )
    adoption = reviewer.build_ground_truth_adoption(
        reviewer.validate_package_files(
            package / "backstory.json",
            package / "ground-truth.json",
        )[1],
        (package / "ground-truth.json").read_bytes(),
        reviewer_id="independent.developer@example.com",
    )
    partial = adoption.model_copy(update={"decisions": adoption.decisions[:-1]})
    state.adoption_path.write_text(partial.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(GroundTruthAdoptionError, match="every proposal"):
        validate_ground_truth_adoption_files(
            package / "backstory.json",
            package / "ground-truth.json",
            state.adoption_path,
        )

    state.adoption_path.unlink()
    ground_truth["proposals"][0]["expected_outcomes"].append("Changed proposal")
    (package / "ground-truth.json").write_text(
        json.dumps(ground_truth, indent=2) + "\n",
        encoding="utf-8",
    )
    state.adoption_path.write_text(adoption.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(GroundTruthAdoptionError, match="exact file bytes"):
        validate_ground_truth_adoption_files(
            package / "backstory.json",
            package / "ground-truth.json",
            state.adoption_path,
        )


def test_review_server_rejects_unauthorized_package_reads(
    tmp_path: Path,
    built_ui: Path,
) -> None:
    package = tmp_path / "package"
    _copy_package(CAPTURE_PACKAGE, package)
    state = _state(package, built_ui)
    server, thread, base_url = _start_server(state)
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base_url}/api/review")
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_ground_truth_adoption_model_rejects_naive_review_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        GroundTruthAdoption(
            backstory_sha256="0" * 64,
            proposed_ground_truth_sha256="1" * 64,
            reviewer=HumanGroundTruthReviewer(
                reviewer_id="developer@example.com"
            ),
            reviewed_at=datetime(2026, 8, 26),
            decisions=(
                AdoptedProposalDecision(
                    proposal_id="proposal",
                    scene_id="scene",
                    objective_id="objective",
                ),
            ),
            adopted_ground_truth_identity="2" * 64,
        )
