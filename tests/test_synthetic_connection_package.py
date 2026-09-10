"""Connection packages bind source setup independently of proposed judgments."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_package import PackageValidationError, validate_package

CROSS = "cross_source_tentative_connection"
WEAK = "weak_evidence_safe_decline"
CHAPTER = "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/01-down-the-rabbit-hole.md"


def connection_documents(repository_root: Path) -> tuple[dict, dict]:
    """A minimal executable contract fixture, never a generated evaluation dataset."""
    public_text = "The source describes a literary image; it does not establish causation."
    snapshot = {
        "source_id": "source-public", "url": "https://example.org/literature",
        "title": "Literary image", "text": public_text,
        "source_sha256": hashlib.sha256(public_text.encode()).hexdigest(),
        "retrieved_at": "2026-09-07T10:00:00+00:00",
    }
    content = {
        "objective_ids": [CROSS, WEAK],
        "backstory": {
            "backstory_id": "story", "person_id": "person",
            "evaluation_account_id": "account", "context": "Contract fixture.",
        },
        "props": [{
            "prop_id": "memory", "backstory_id": "story", "person_id": "person",
            "evaluation_account_id": "account", "source_text": "I remembered an unusual image.",
            "lifecycle": [{"scene_id": f"s{index}", "state": "active"} for index in (1, 2)],
        }],
        "scenes": [{
            "scene_id": f"s{index}", "backstory_id": "story", "objective_ids": objectives,
            "order": index, "fresh_session": True,
            "prop_ids": ["memory"] if index < 3 else [], "line_ids": [f"l{index}"],
        } for index, objectives in enumerate(([CROSS], [CROSS, WEAK], [WEAK]), 1)],
        "lines": [{
            "line_id": f"l{index}", "scene_id": f"s{index}", "order": 1, "text": text,
        } for index, text in enumerate((
            "Could my earlier image relate to this passage and the public account?",
            "Does that connection establish why I felt that way?",
            "I am thinking about how differently rereading feels.",
        ), 1)],
        "source_setups": [{
            "scene_id": f"s{index}",
            "book_scope": {
                "kind": "reader_confirmed", "work_id": "pg11",
                "book_version_id": "pg11-v01b38ea4", "safe_ceiling_chapter": 1,
            },
            "public_sources": [deepcopy(snapshot)],
        } for index in (1, 2)],
    }
    chapter_bytes = (repository_root / CHAPTER).read_bytes()
    chapter_text = chapter_bytes.decode()
    quote = "a book of rules for shutting people up like telescopes"
    start = chapter_text.index(quote)
    proposals = []
    for scene_id, objective, decision in (("s1", CROSS, "proposal"), ("s2", CROSS, "restraint"), ("s2", WEAK, "restraint"), ("s3", WEAK, "not_requested")):
        prefix = f"{scene_id}-{objective}"
        evidence = [] if decision == "not_requested" else [
            {"kind": "prop", "evidence_id": f"{prefix}-memory", "prop_id": "memory"},
            {
                "kind": "repository_text", "evidence_id": f"{prefix}-book",
                "repository_path": CHAPTER, "source_sha256": hashlib.sha256(chapter_bytes).hexdigest(),
                "start_codepoint": start, "end_codepoint": start + len(quote), "text": quote,
            },
            {
                "kind": "public_source", "evidence_id": f"{prefix}-public", "source_id": "source-public",
                "start_codepoint": 0, "end_codepoint": len(public_text), "text": public_text,
            },
        ]
        available = [item["evidence_id"] for item in evidence]
        paired_id = "s2" if scene_id in {"s1", "s3"} else ("s1" if objective == CROSS else "s3")
        same_props = objective == CROSS
        proposals.append({
            "proposal_id": prefix, "scene_id": scene_id, "objective_id": objective,
            "expected_outcomes": ["Reviewed connection behavior."],
            "prohibited_outcomes": ["Invented support or certainty."], "evidence": evidence,
            "prop_relevance": [] if scene_id == "s3" else [{"prop_id": "memory", "relevance": "relevant"}],
            "pairing": {
                "paired_scene_id": paired_id,
                "match_fields": ["backstory_id", "fresh_session", "line_count"] + (["prop_ids", "source_setup"] if same_props else []),
                "difference_fields": ["line_text"] + ([] if same_props else ["prop_ids", "source_setup"]),
            },
            "connection": {
                "decision": decision,
                "permitted_evidence_ids": available,
                "required_evidence_ids": available if decision == "proposal" else [],
                "acceptable_responses": {
                    "proposal": ["tentative_connection"],
                    "restraint": ["qualified", "declined", "request_better_evidence"],
                    "not_requested": ["personal_reflection"],
                }[decision],
                "required_public_claims": ["The public account describes a literary image."] if decision == "proposal" else [],
            },
        })
    raw = json.dumps(content, sort_keys=True).encode()
    return content, {
        "backstory_sha256": hashlib.sha256(raw).hexdigest(),
        "ground_truth_status": "proposed", "proposals": proposals,
    }


def validate_documents(content: dict, labels: dict, root: Path):
    raw = json.dumps(content, sort_keys=True).encode()
    labels = labels | {"backstory_sha256": hashlib.sha256(raw).hexdigest()}
    backstory = SyntheticBackstory.model_validate_json(raw)
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(labels))
    validate_package(backstory, ground_truth, backstory_bytes=raw, run_configurations={}, repository_root=root)
    return compile_connection_replay_plan(backstory, ground_truth, repository_root=root)


@pytest.fixture
def connection_package():
    root = Path(__file__).resolve().parents[1]
    content, labels = connection_documents(root)
    return root, content, labels


def test_mixed_package_compiles_one_account_and_independent_sources(connection_package):
    root, content, labels = connection_package
    plan = validate_documents(content, labels, root)
    assert len(plan.scenes) == 3
    assert len(plan.ground_truth.proposals) == 4
    assert {prop.evaluation_account_id for scene in plan.scenes for prop in scene.props} == {"account"}
    assert plan.scenes[0].props == plan.scenes[1].props
    assert plan.scenes[2].props == ()
    assert len(plan.scenes[0].evidence_by_id) == 1
    assert plan.scenes[0].source_setup.public_sources[0].source_id == "source-public"
    assert '"connection":' not in plan.backstory.model_dump_json()


@pytest.mark.parametrize("mutation, message", [
    ("public_hash", "source_sha256"),
    ("public_source", "unavailable to Scene"),
    ("public_span", "exact text span"),
    ("book_scope", "book scope"),
    ("prop_missing", "every available Prop"),
    ("prop_unknown", "unknown or unavailable Props"),
    ("untyped", "typed connection"),
    ("empty_weak_sources", "inspectable insufficient evidence"),
])
def test_connection_source_and_label_failures_are_rejected(connection_package, mutation, message):
    root, content, labels = connection_package
    if mutation == "public_hash":
        content["source_setups"][0]["public_sources"][0]["text"] += " Altered."
    elif mutation == "public_source":
        labels["proposals"][0]["evidence"][2]["source_id"] = "not-supplied"
    elif mutation == "public_span":
        labels["proposals"][0]["evidence"][2]["end_codepoint"] += 1
    elif mutation == "book_scope":
        del content["source_setups"][0]["book_scope"]
    elif mutation == "prop_missing":
        labels["proposals"][1]["prop_relevance"] = []
    elif mutation == "prop_unknown":
        labels["proposals"][2]["prop_relevance"] = [{"prop_id": "unknown", "relevance": "distractor"}]
    elif mutation == "untyped":
        del labels["proposals"][0]["connection"]
    elif mutation == "empty_weak_sources":
        labels["proposals"][1]["evidence"] = []
        labels["proposals"][1]["connection"]["permitted_evidence_ids"] = []
    with pytest.raises((PackageValidationError, ValidationError), match=message):
        validate_documents(content, labels, root)


def test_insufficient_evidence_is_visible_without_becoming_required_citation(connection_package):
    root, content, labels = connection_package
    plan = validate_documents(content, labels, root)
    weak = plan.scenes[1].proposals[1]
    assert len(weak.evidence) == 3
    assert weak.connection.required_evidence_ids == ()
    assert set(weak.connection.acceptable_responses) == {"qualified", "declined", "request_better_evidence"}


def test_unavailable_scene_source_cannot_be_borrowed_from_another_scene(connection_package):
    root, content, labels = connection_package
    content["source_setups"][1]["public_sources"] = []
    with pytest.raises(PackageValidationError, match="unavailable to Scene s2"):
        validate_documents(content, labels, root)


def test_shared_scene_proposals_must_allow_a_common_response(connection_package):
    root, content, labels = connection_package
    labels["proposals"][1]["connection"]["acceptable_responses"] = ["qualified"]
    labels["proposals"][2]["connection"]["acceptable_responses"] = ["declined"]
    with pytest.raises(PackageValidationError, match="no jointly acceptable response"):
        validate_documents(content, labels, root)


def test_source_setup_changes_cannot_be_hidden_in_scene_pairing(connection_package):
    root, content, labels = connection_package
    del labels["proposals"][2]["pairing"]["difference_fields"][2]
    with pytest.raises(PackageValidationError, match="undeclared paired differences"):
        validate_documents(content, labels, root)
