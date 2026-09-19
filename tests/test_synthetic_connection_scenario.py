"""Connection scenarios bind source setup independently of proposed judgments."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.complete_curation_ground_truth import complete_curation_ground_truth
from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_scenario import ScenarioValidationError, validate_scenario
from tests.test_synthetic_curation_replay import _curation_documents

CROSS = "cross_source_tentative_connection"
WEAK = "weak_evidence_safe_decline"
CURATION = "bounded_memory_curation"
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
    validate_scenario(backstory, ground_truth, backstory_bytes=raw, run_configurations={}, repository_root=root)
    return compile_connection_replay_plan(backstory, ground_truth, repository_root=root)


def connection_curation_documents(repository_root: Path) -> tuple[dict, dict]:
    """Compose existing contract fixtures under one account without writing data."""
    content, labels = connection_documents(repository_root)
    curation, curation_labels, _ = _curation_documents()
    content["objective_ids"] = [CURATION, CROSS]
    content["scenes"] = content["scenes"][:2]
    content["lines"] = content["lines"][:2]
    for scene in content["scenes"]:
        scene["objective_ids"] = [CROSS]
        scene["order"] += len(curation["scenes"])
    for prop in curation["props"]:
        for field in ("backstory_id", "person_id", "evaluation_account_id"):
            prop[field] = content["backstory"][field]
    for scene in curation["scenes"]:
        scene["backstory_id"] = content["backstory"]["backstory_id"]
    content["props"] = [*curation["props"], *content["props"]]
    content["scenes"] = [*curation["scenes"], *content["scenes"]]
    labels["proposals"] = [
        *curation_labels["proposals"],
        *(proposal for proposal in labels["proposals"] if proposal["objective_id"] == CROSS),
    ]
    raw = json.dumps(content, sort_keys=True).encode()
    labels["backstory_sha256"] = hashlib.sha256(raw).hexdigest()
    return content, labels


@pytest.mark.parametrize("reverse_objectives", [False, True])
def test_connection_curation_compiles_original_scenario_and_only_connection_scenes(reverse_objectives):
    root = Path(__file__).resolve().parents[1]
    content, labels = connection_curation_documents(root)
    if reverse_objectives:
        content["objective_ids"].reverse()
    raw = json.dumps(content, sort_keys=True).encode()
    labels["backstory_sha256"] = hashlib.sha256(raw).hexdigest()
    backstory = SyntheticBackstory.model_validate_json(raw)
    ground_truth = ProposedGroundTruth.model_validate_json(json.dumps(labels))

    validate_scenario(backstory, ground_truth, backstory_bytes=raw, run_configurations={}, repository_root=root)
    plan = compile_connection_replay_plan(backstory, ground_truth, repository_root=root)

    assert plan.backstory is backstory
    assert plan.ground_truth is ground_truth
    assert plan.objective_ids == {CURATION, CROSS}
    assert len(plan.backstory.scenes) == len(plan.ground_truth.proposals) == 7
    assert plan.ground_truth.backstory_sha256 == hashlib.sha256(raw).hexdigest()
    assert [scene.scene.scene_id for scene in plan.scenes] == ["s1", "s2"]
    assert [scene.scene.order for scene in plan.scenes] == [6, 7]
    assert {prop.evaluation_account_id for prop in plan.backstory.props} == {"account"}


def test_connection_curation_completion_preserves_both_objectives_and_candidate_labels():
    root = Path(__file__).resolve().parents[1]
    content, labels = connection_curation_documents(root)
    for proposal in labels["proposals"]:
        action = proposal.get("curation", {}).get("expected", {}).get("action", {})
        action.pop("max_summary_words", None)
        action.pop("semantic_review", None)
    raw = json.dumps(content, sort_keys=True).encode()
    completed = json.loads(complete_curation_ground_truth(
        raw, json.dumps(labels).encode(), run_configurations={}, repository_root=root,
    ))
    plan = validate_documents(content, completed, root)
    assert len(plan.backstory.scenes) == len(plan.ground_truth.proposals) == 7
    for proposal in completed["proposals"]:
        action = proposal.get("curation", {}).get("expected", {}).get("action", {})
        action.pop("max_summary_words", None)
        action.pop("semantic_review", None)
    assert completed == labels


@pytest.mark.parametrize("mutation,message", [
    ("curation_behavior", "exactly one Scene for each accepted Sculptor behavior"),
    ("curation_evidence", "must cite every Scene Prop exactly once"),
    ("connection_evidence", "unavailable to Scene"),
    ("missing_curation_label", "proposal coverage must exactly match Scene Objectives"),
    ("extra_objective", "or exactly connection with bounded curation"),
    ("shared_scene", "Scenes must select exactly one Objective"),
])
def test_connection_curation_preserves_validation_boundaries(mutation, message):
    root = Path(__file__).resolve().parents[1]
    content, labels = connection_curation_documents(root)
    if mutation == "curation_behavior":
        labels["proposals"][0]["curation"]["primary_behavior"] = "paraphrased_duplicate"
    elif mutation == "curation_evidence":
        labels["proposals"][0]["evidence"].pop()
    elif mutation == "connection_evidence":
        labels["proposals"][-1]["evidence"][-1]["source_id"] = "unavailable"
    elif mutation == "missing_curation_label":
        labels["proposals"].pop(0)
    elif mutation == "extra_objective":
        content["objective_ids"].append(WEAK)
        content["scenes"][-1]["objective_ids"].append(WEAK)
        _, connection_labels = connection_documents(root)
        labels["proposals"].append(connection_labels["proposals"][2])
    elif mutation == "shared_scene":
        content["scenes"][-1]["objective_ids"].append(CURATION)
    with pytest.raises(ScenarioValidationError, match=message):
        validate_documents(content, labels, root)


@pytest.fixture
def connection_scenario():
    root = Path(__file__).resolve().parents[1]
    content, labels = connection_documents(root)
    return root, content, labels


def test_mixed_scenario_compiles_one_account_and_independent_sources(connection_scenario):
    root, content, labels = connection_scenario
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
def test_connection_source_and_label_failures_are_rejected(connection_scenario, mutation, message):
    root, content, labels = connection_scenario
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
    with pytest.raises((ScenarioValidationError, ValidationError), match=message):
        validate_documents(content, labels, root)


def test_insufficient_evidence_is_visible_without_becoming_required_citation(connection_scenario):
    root, content, labels = connection_scenario
    plan = validate_documents(content, labels, root)
    weak = plan.scenes[1].proposals[1]
    assert len(weak.evidence) == 3
    assert weak.connection.required_evidence_ids == ()
    assert set(weak.connection.acceptable_responses) == {"qualified", "declined", "request_better_evidence"}


def test_unavailable_scene_source_cannot_be_borrowed_from_another_scene(connection_scenario):
    root, content, labels = connection_scenario
    content["source_setups"][1]["public_sources"] = []
    with pytest.raises(ScenarioValidationError, match="unavailable to Scene s2"):
        validate_documents(content, labels, root)


def test_shared_scene_proposals_must_allow_a_common_response(connection_scenario):
    root, content, labels = connection_scenario
    labels["proposals"][1]["connection"]["acceptable_responses"] = ["qualified"]
    labels["proposals"][2]["connection"]["acceptable_responses"] = ["declined"]
    with pytest.raises(ScenarioValidationError, match="no jointly acceptable response"):
        validate_documents(content, labels, root)


def test_source_setup_changes_cannot_be_hidden_in_scene_pairing(connection_scenario):
    root, content, labels = connection_scenario
    del labels["proposals"][2]["pairing"]["difference_fields"][2]
    with pytest.raises(ScenarioValidationError, match="undeclared paired differences"):
        validate_documents(content, labels, root)
