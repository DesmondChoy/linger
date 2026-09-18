"""A compatible book passage is not proof of a uniquely identified stopping event."""

import pytest
from pydantic import ValidationError
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.agents.librarian.models import (
    BoundaryMemory,
    BoundaryUncertainDecision,
    LibrarianBoundaryInferenceInput,
    boundary_memory_assessment_errors,
)
from src.linger.contracts.librarian import EvidenceRecord
from tests.boundary_fixtures import quoted_support


def test_candidate_requires_reader_identification_beyond_compatible_memory():
    with pytest.raises(ValidationError, match="event_resolution"):
        BoundaryInferenceDecision(
            memory_assessments=(
                {
                    "memory_id": "remembered-return",
                    "status": "grounded_prior_knowledge",
                    "evidence_ids": ("return-eight",),
                    "reason": "One return matches the vague memory.",
                },
            ),
            outcome="candidate",
            work_id="book",
            book_version_id="book-v1",
            chapter_number=8,
            confidence=0.99,
            authorization_basis="memory_supported",
            supporting_memory_ids=("remembered-return",),
            supporting_evidence=({"evidence_id": "return-eight", "source_excerpt": "A return."},),
        )


def record(identity, chapter):
    return EvidenceRecord(
        evidence_id=identity,
        work_id="book",
        book_version_id="book-v1",
        chapter_id=f"chapter-{chapter}",
        chapter_number=chapter,
        location=f"Chapter {chapter}",
        source_sha256="a" * 64,
        source_lines=(chapter, chapter),
        text=f"Canonical event {identity}.",
    )


def identified_stop():
    return BoundaryInferenceDecision(
        memory_assessments=(
            {
                "memory_id": "earlier",
                "status": "grounded_prior_knowledge",
                "evidence_ids": ("earlier-event",),
                "reason": "The earlier memory matches its own event.",
            },
        ),
        outcome="candidate",
        work_id="book",
        book_version_id="book-v1",
        chapter_number=8,
        confidence=0.99,
        authorization_basis="memory_supported",
        supporting_memory_ids=("earlier",),
        supporting_evidence=quoted_support(request().full_work_candidates, ("earlier-event", "current-event")),
        event_resolution={
            "reader_event_spans": (
                "I stopped after the return following the valuation.",
            ),
            "occurrences": (
                {
                    "evidence_ids": ("current-event",),
                    "disposition": "selected",
                    "distinguishing_reader_spans": ("following the valuation",),
                    "explanation": "The named cause identifies this return.",
                },
                {
                    "evidence_ids": ("other-return",),
                    "disposition": "ruled_out",
                    "distinguishing_reader_spans": ("following the valuation",),
                    "explanation": "The alternative return follows imprisonment instead.",
                },
            ),
            "other_evidence_ids": ("earlier-event",),
        },
    )


def request():
    return LibrarianBoundaryInferenceInput(
        current_line="I stopped after the return following the valuation.",
        prior_reader_statements=(),
        relevant_memories=(
            BoundaryMemory(memory_id="earlier", text="I read the earlier event."),
        ),
        full_work_candidates=(
            record("earlier-event", 6),
            record("current-event", 8),
            record("other-return", 10),
        ),
    )


def test_distinct_current_stop_can_extend_earlier_memory_without_latest_alternative_grant():
    assert boundary_memory_assessment_errors(identified_stop(), request()) == []


def test_every_private_candidate_must_be_accounted_for_before_grant():
    decision = identified_stop()
    resolution = decision.event_resolution.model_copy(
        update={"occurrences": decision.event_resolution.occurrences[:1]}
    )
    errors = boundary_memory_assessment_errors(
        decision.model_copy(update={"event_resolution": resolution}), request()
    )
    assert any(
        error.get("missing_evidence_ids") == ["other-return"] for error in errors
    )


def test_corpus_or_memory_detail_cannot_be_fabricated_as_reader_identification():
    decision = identified_stop()
    chosen = decision.event_resolution.occurrences[0].model_copy(
        update={"distinguishing_reader_spans": ("I escaped imprisonment",)}
    )
    resolution = decision.event_resolution.model_copy(
        update={"occurrences": (chosen, decision.event_resolution.occurrences[1])}
    )
    errors = boundary_memory_assessment_errors(
        decision.model_copy(update={"event_resolution": resolution}), request()
    )
    assert any(error.get("span") == "I escaped imprisonment" for error in errors)


def test_two_compatible_occurrences_cannot_form_a_candidate():
    payload = identified_stop().model_dump()
    payload["event_resolution"]["occurrences"][1]["disposition"] = "selected"
    with pytest.raises(ValidationError, match="exactly one identified occurrence"):
        BoundaryInferenceDecision.model_validate(payload)


def test_current_event_not_older_memory_must_establish_ceiling():
    decision = identified_stop().model_copy(update={"chapter_number": 10})
    assert any(
        error["path"] == "chapter_number"
        for error in boundary_memory_assessment_errors(decision, request())
    )


def test_uncertain_shape_preserves_assessment_without_any_grant_fields():
    decision = BoundaryUncertainDecision(
        memory_assessments=identified_stop().memory_assessments,
        outcome="uncertain",
        confidence=0.28,
        reason_code="low_confidence",
    )
    assert boundary_memory_assessment_errors(decision, request()) == []
    assert set(decision.model_dump()) == {
        "memory_assessments",
        "outcome",
        "confidence",
        "reason_code",
    }
    assert not {
        "work_id",
        "chapter_number",
        "authorization_basis",
        "supporting_evidence",
    } & set(BoundaryUncertainDecision.model_json_schema()["properties"])
    with pytest.raises(ValidationError, match="Extra inputs"):
        BoundaryUncertainDecision.model_validate(
            {**decision.model_dump(), "authorization_basis": "memory_supported"}
        )
