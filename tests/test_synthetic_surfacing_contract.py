"""Package admission and hard-grading tests for proactive memory surfacing."""

import hashlib

import pytest
from pydantic import ValidationError

from evals.sculptor.surfacing_harness import grade_surfacing_expectation
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.replay_support import replay_support_for
from evals.synthetic_journals.surfacing_contract import (
    SurfacingContractError,
    compile_surfacing_scenes,
)
from evals.synthetic_journals.validate_package import PackageValidationError, validate_package
from tests.surfacing_fixtures import json_bytes, make_surfacing_package, surfacing_documents


def _validate(backstory, truth):
    payload = json_bytes(backstory)
    truth["backstory_sha256"] = hashlib.sha256(payload).hexdigest()
    b = SyntheticBackstory.model_validate_json(payload)
    g = ProposedGroundTruth.model_validate_json(json_bytes(truth))
    validate_package(b, g, backstory_bytes=payload, run_configurations={})
    return compile_surfacing_scenes(b, g)


def test_compiler_uses_active_bank_without_answer_key_or_backstory():
    backstory, truth, _ = surfacing_documents()
    # Distractors are supplied independently of expected source labels.
    for state in backstory["props"][1]["lifecycle"]:
        state["state"] = "deleted"
    scenes = _validate(backstory, truth)
    assert [scene.order for scene in scenes] == list(range(1, 7))
    assert {m.memory_id for m in scenes[0].input.memories} == {"prop-intention"}
    assert "Generator-only" not in scenes[0].input.model_dump_json()
    assert "semantic_criteria" not in scenes[0].input.model_dump_json()
    normal = compile_surfacing_scenes(*make_surfacing_package())
    assert len(normal[0].input.memories) == 2
    assert "prop-noise" not in normal[0].expectation.allowed_source_ids


@pytest.mark.parametrize("mutation,match", [
    ("changed_context", "must match|differing only"),
    ("no_pair", "declared timely/deferred pair"),
    ("missing_case", "must cover"),
    ("no_history", "prior surfacing history"),
    ("inactive_source", "active input Props"),
    ("missing_evidence", "Prop evidence and exact spans"),
    ("past_expectation", "after now"),
    ("wrong_offline_kind", "surfacing context"),
    ("continued_scene", "fresh snapshots"),
])
def test_rejects_invalid_surfacing_design(mutation, match):
    b, g, _ = surfacing_documents()
    if mutation == "changed_context":
        b["offline_inputs"][1]["surfacing_context"]["current_context"] = "A different situation"
    elif mutation == "no_pair":
        del g["proposals"][1]["pairing"]
    elif mutation == "missing_case":
        g["proposals"][-1]["surfacing"].update(case_kind="unsupported", reason="insufficient_evidence")
    elif mutation == "no_history":
        b["offline_inputs"][3]["surfacing_context"]["history"] = []
    elif mutation == "inactive_source":
        b["props"][0]["lifecycle"][0]["state"] = "inactive"
    elif mutation == "missing_evidence":
        g["proposals"][0]["evidence"] = []
    elif mutation == "past_expectation":
        g["proposals"][0]["surfacing"]["reconsideration"]["at"] = "2026-09-05T08:00:00+08:00"
    elif mutation == "wrong_offline_kind":
        b["offline_inputs"][0]["kind"] = "other"
    elif mutation == "continued_scene":
        b["scenes"][0]["fresh_session"] = False
    with pytest.raises((PackageValidationError, ValidationError), match=match):
        _validate(b, g)


def test_compiler_rejects_cross_account_model_copy_bypass():
    b, g = make_surfacing_package()
    forged = b.props[0].model_copy(update={"evaluation_account_id": "someone-else"})
    with pytest.raises(SurfacingContractError, match="package graph"):
        compile_surfacing_scenes(b.model_copy(update={"props": (forged, *b.props[1:])}), g)


def test_grading_retains_semantic_review_after_hard_pass():
    scene = compile_surfacing_scenes(*make_surfacing_package())[1]
    response = {
        "decision": "surface_now", "source_memory_ids": ["prop-intention"],
        "suggestion": "Invented advice that needs independent review.",
        "rationale": "These source IDs alone cannot prove this prose.",
    }
    grade = grade_surfacing_expectation(scene.input, response, scene.expectation)
    assert grade.hard_failures == ()
    assert grade.decision_match and grade.semantic_review_required
    assert grade.semantic_criteria == scene.expectation.semantic_criteria


@pytest.mark.parametrize("sources,match", [
    (["prop-noise"], "missing_required_sources"),
    (["prop-intention", "prop-noise"], "disallowed_sources"),
    (["unknown"], "invalid_response"),
])
def test_grading_rejects_bad_provenance(sources, match):
    scene = compile_surfacing_scenes(*make_surfacing_package())[1]
    grade = grade_surfacing_expectation(scene.input, {
        "decision": "surface_now", "source_memory_ids": sources,
        "suggestion": "Collect the novel.", "rationale": "Collection is open.",
    }, scene.expectation)
    assert any(match in failure for failure in grade.hard_failures)
    assert grade.decision_match  # Label correctness does not prove source correctness.


def test_condition_meaning_is_not_exact_string_graded():
    scene = compile_surfacing_scenes(*make_surfacing_package())[0]
    expected = scene.expectation.model_dump()
    expected["reconsideration"] = {"kind": "condition", "condition": "The library opens collection."}
    expected = type(scene.expectation).model_validate(expected)
    grade = grade_surfacing_expectation(scene.input, {
        "decision": "defer", "source_memory_ids": ["prop-intention"],
        "suggestion": "Collect the novel.", "rationale": "It is too early.",
        "reconsideration": {"kind": "condition", "condition": "Unrelated condition requiring review."},
    }, expected)
    assert grade.hard_failures == ()
    assert grade.semantic_review_required


def test_surfacing_replay_support_is_standalone():
    support = replay_support_for(["proactive_memory_surfacing"])
    assert support.module == "evals.synthetic_journals.surfacing_replay"
    assert replay_support_for(["proactive_memory_surfacing", "bounded_memory_curation"]) is None
