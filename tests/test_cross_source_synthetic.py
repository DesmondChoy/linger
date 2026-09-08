from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from apps.backend.schemas import (
    CaptureInspection,
    ChatResponse,
    ConnectionDeclineInspection,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from evals.serendipity.objective_replay import (
    ObservedWebQuery,
    _package_cases,
    grade_cross_source_response,
    replay_cross_source_scenes,
)
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_package import (
    PackageValidationError,
    validate_package,
)


OBJECTIVE = "cross_source_tentative_connection"


def _documents() -> tuple[SyntheticBackstory, ProposedGroundTruth, bytes]:
    book_path = Path(
        "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/"
        "05-advice-from-a-caterpillar.md"
    )
    book_bytes = book_path.read_bytes()
    book_text = book_bytes.decode("utf-8")
    book_quote = "Who are _you?_"
    book_start = book_text.index(book_quote)
    backstory_document = {
        "objective_ids": [OBJECTIVE],
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-cross-source",
            "person_id": "person-cross-source",
            "evaluation_account_id": "account-cross-source",
            "context": "A reader relates Alice's uncertainty to a prior transition.",
        },
        "props": [
            {
                "prop_id": "prop-transition",
                "backstory_id": "backstory-cross-source",
                "person_id": "person-cross-source",
                "evaluation_account_id": "account-cross-source",
                "source_text": "Changing teams made familiar work feel strangely uncertain.",
                "lifecycle": [
                    {"scene_id": "supported", "state": "active"},
                    {"scene_id": "decline", "state": "active"},
                ],
            }
        ],
        "scenes": [
            {
                "scene_id": "supported",
                "backstory_id": "backstory-cross-source",
                "objective_ids": [OBJECTIVE],
                "order": 1,
                "fresh_session": True,
                "prop_ids": ["prop-transition"],
                "line_ids": ["line-supported"],
                "offline_input_ids": ["public-supported"],
            },
            {
                "scene_id": "decline",
                "backstory_id": "backstory-cross-source",
                "objective_ids": [OBJECTIVE],
                "order": 2,
                "fresh_session": True,
                "prop_ids": ["prop-transition"],
                "line_ids": ["line-decline"],
                "offline_input_ids": ["public-decline"],
            },
        ],
        "lines": [
            {
                "line_id": "line-supported",
                "scene_id": "supported",
                "order": 1,
                "text": "Connect Alice's uncertainty here with my earlier transition and an outside source.",
            },
            {
                "line_id": "line-decline",
                "scene_id": "decline",
                "order": 1,
                "text": "Can that same idea prove why every transition changes identity?",
            },
        ],
        "offline_inputs": [
            {
                "offline_input_id": "public-supported",
                "scene_id": "supported",
                "order": 1,
                "kind": "public_evidence",
                "text": "A public essay discusses uncertainty during transitions.",
                "prop_ids": [],
            },
            {
                "offline_input_id": "public-decline",
                "scene_id": "decline",
                "order": 1,
                "kind": "public_evidence",
                "text": "The comparison source does not establish a universal causal claim.",
                "prop_ids": [],
            },
        ],
    }
    backstory_bytes = json.dumps(
        backstory_document, ensure_ascii=False, sort_keys=True
    ).encode()
    prop_text = backstory_document["props"][0]["source_text"]
    private_wording = "Changing teams"
    private_span = {
        "source_kind": "prop",
        "source_id": "prop-transition",
        "start_codepoint": prop_text.index(private_wording),
        "end_codepoint": prop_text.index(private_wording) + len(private_wording),
        "text": private_wording,
    }
    proposals = []
    for scene_id, decision, public_id in (
        ("supported", "proposal", "public-supported"),
        ("decline", "decline", "public-decline"),
    ):
        evidence = [
            {
                "kind": "prop",
                "evidence_id": f"memory-{scene_id}",
                "prop_id": "prop-transition",
            },
            {
                "kind": "repository_text",
                "evidence_id": f"book-{scene_id}",
                "repository_path": str(book_path),
                "source_sha256": hashlib.sha256(book_bytes).hexdigest(),
                "start_codepoint": book_start,
                "end_codepoint": book_start + len(book_quote),
                "text": book_quote,
            },
            {
                "kind": "offline_input",
                "evidence_id": f"web-{scene_id}",
                "offline_input_id": public_id,
            },
        ]
        required_ids = (
            [f"memory-{scene_id}", f"book-{scene_id}", f"web-{scene_id}"]
            if decision == "proposal"
            else []
        )
        proposals.append(
            {
                "proposal_id": f"proposal-{scene_id}",
                "scene_id": scene_id,
                "objective_id": OBJECTIVE,
                "expected_outcomes": ["The decision follows the supplied support."],
                "prohibited_outcomes": ["Private wording appears in a public query."],
                "evidence": evidence,
                "connection": {
                    "expected_decision": decision,
                    "required_source_kinds": (
                        ["memory", "book_corpus", "web"] if decision == "proposal" else []
                    ),
                    "required_evidence_ids": required_ids,
                    "public_claims": [],
                    "forbidden_web_query_spans": [private_span],
                    "require_tentative": True,
                },
                "pairing": {
                    "paired_scene_id": "decline" if scene_id == "supported" else "supported",
                    "match_fields": ["backstory_id", "fresh_session", "prop_ids", "line_count"],
                    "difference_fields": ["line_text", "offline_input_content"],
                },
            }
        )
    ground_truth_document = {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }
    return (
        SyntheticBackstory.model_validate_json(backstory_bytes),
        ProposedGroundTruth.model_validate_json(
            json.dumps(ground_truth_document, ensure_ascii=False, sort_keys=True)
        ),
        backstory_bytes,
    )


def test_cross_source_package_validates_and_builds_scene_cases() -> None:
    backstory, ground_truth, backstory_bytes = _documents()
    validate_package(
        backstory,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations={},
    )
    cases = _package_cases(backstory, ground_truth)
    assert [entry.case.expected_decision for entry in cases] == ["proposal", "decline"]
    assert all(entry.prop_ids == ("prop-transition",) for entry in cases)
    assert all(entry.semantic_review.require_tentative for entry in cases)


def _passing_response(*, declined: bool = False) -> ChatResponse:
    """A response whose fixed metadata clears every production stage."""
    capture = CaptureInspection(
        nomination="no_candidate",
        provenance_decision="no_candidate",
        binding="not_applicable",
        storage="not_applicable",
        reason_code="not_applicable",
    )
    return ChatResponse(
        reply="A tentative, cited synthetic connection.",
        inspection=TurnInspection(
            muse_turn={},
            context_resolution={},
            traces=[
                {"agent": "Serendipity", "status": "complete", "detail": "test"},
                {"agent": "Librarian", "status": "complete", "detail": "test"},
            ],
            connection_decline=(
                ConnectionDeclineInspection(reason="insufficient_evidence")
                if declined
                else None
            ),
            prompt="synthetic",
            release=ReleaseInspection(
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=(),
                revision_count=0,
                failure_stage=None,
                capture=capture,
            ),
        ),
        trace=TraceReference(trace_id="0" * 32),
    )


def _graded_stage(report, stage: str):
    return next(item for item in report.stages if item.stage == stage)


def test_cross_source_case_carries_forbidden_wording_and_review_items() -> None:
    backstory, ground_truth, _ = _documents()
    supported, decline = _package_cases(backstory, ground_truth)

    assert supported.case.forbidden_query_texts == ("Changing teams",)
    assert supported.semantic_review.require_tentative is True
    # Private wording is off limits in the decline Scene too, even though a
    # declining proposal requires no sources, evidence, or public claims.
    assert decline.case.forbidden_query_texts == ("Changing teams",)
    assert decline.case.expected_decision == "decline"


def test_issued_query_with_private_wording_fails_the_retrieval_stage() -> None:
    backstory, ground_truth, _ = _documents()
    supported, _ = _package_cases(backstory, ground_truth)

    report = grade_cross_source_response(
        supported.case,
        _passing_response(),
        run_id="0" * 32,
        web_queries=(
            ObservedWebQuery(
                query="Changing teams and uncertainty essays",
                verdict="issued",
            ),
        ),
    )

    assert report.objective_pass is False
    assert report.first_failure_stage == "retrieval"
    assert _graded_stage(report, "retrieval").reason_code == (
        "private_wording_in_public_query"
    )
    assert _graded_stage(report, "serendipity_selection").status == "not_reached"


def test_blocked_query_with_private_wording_is_the_gate_working() -> None:
    backstory, ground_truth, _ = _documents()
    supported, _ = _package_cases(backstory, ground_truth)

    report = grade_cross_source_response(
        supported.case,
        _passing_response(),
        run_id="0" * 32,
        web_queries=(
            ObservedWebQuery(
                query="Changing teams and uncertainty essays",
                verdict="blocked",
            ),
            ObservedWebQuery(query="uncertainty during transitions", verdict="issued"),
        ),
    )

    assert report.objective_pass is True
    assert report.first_failure_stage is None
    assert [item.verdict for item in report.web_queries] == ["blocked", "issued"]


def test_cross_source_package_requires_typed_connection_ground_truth() -> None:
    backstory, ground_truth, backstory_bytes = _documents()
    broken = ground_truth.model_copy(
        update={
            "proposals": (
                ground_truth.proposals[0].model_copy(update={"connection": None}),
                ground_truth.proposals[1],
            )
        }
    )
    with pytest.raises(PackageValidationError, match="lacks typed connection"):
        validate_package(
            backstory,
            broken,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )


def test_cross_source_replay_seeds_props_and_grades_adoption() -> None:
    backstory, ground_truth, _ = _documents()
    adoption = build_ground_truth_adoption(
        ground_truth,
        ground_truth.model_dump_json().encode(),
        reviewer_id="independent-reviewer",
    )
    observed_props: list[tuple[str, ...]] = []

    async def handler(request, service, account):
        observed_props.append(tuple(record.text for record in service.list_active(account)))
        return _passing_response(declined="prove" in request.message)

    report = asyncio.run(
        replay_cross_source_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            chat_handler=handler,
        )
    )

    assert report.ground_truth_status == "adopted"
    assert report.dataset_version == adoption.adopted_ground_truth_identity
    assert observed_props == [
        ("Changing teams made familiar work feel strangely uncertain.",),
        ("Changing teams made familiar work feel strangely uncertain.",),
    ]
    assert all(scene.ground_truth_result == "passes_hard_gates" for scene in report.scenes)
