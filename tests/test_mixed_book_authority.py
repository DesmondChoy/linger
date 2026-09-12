"""No cross-part or preceding-unit permission can cross the release gates."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from apps.backend.contracts import BookScope, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.contracts.librarian import EvidenceRecord, SearchedScope
from src.linger.contracts.reading import ReadingBoundary, contains_scope, permits_scope
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration.grounding import build_request, _grounding_evidence
from src.linger.orchestration.reflection import _validate_record_scope, ReleaseValidationError
from src.linger.orchestration.turn_context import set_confirmed_reading, reset_confirmed_reading

VERSION = "pg2397-vb3cc1e13"


def record(unit="sec003", part="main", chapter=1):
    return EvidenceRecord(evidence_id=f"{VERSION}-{unit}-ln0001-0002", work_id="pg2397",
        book_version_id=VERSION, chapter_id=f"{VERSION}-{unit}", part_id=part,
        chapter_number=chapter, location="a canonical location", source_sha256="a" * 64,
        source_lines=(1, 2), text="canonical text")


def test_chapter_permission_excludes_other_parts_and_frontmatter():
    scope = ReleaseScope(work_id="pg2397", book_version_id=VERSION, chapter_max=3)
    _validate_record_scope(record(), scope, frozenset())
    for evidence in (record("sec133", "part-iii"), record("sec002", "frontmatter", None)):
        assert not permits_scope(scope, evidence)
        with pytest.raises(ReleaseValidationError):
            _validate_record_scope(evidence, scope, frozenset())
    assert not contains_scope(scope, SearchedScope(work_id="pg2397", book_version_id=VERSION,
        max_chapter_inclusive=1, part_id="part-iii"))


def test_letter_permission_never_grants_preceding_letters():
    scope = ReleaseScope(work_id="pg2397", book_version_id=VERSION,
        part_id="letters", unit_ids=(f"{VERSION}-sec032",))
    _validate_record_scope(record("sec032", "letters", None), scope, frozenset())
    with pytest.raises(ReleaseValidationError):
        _validate_record_scope(record("sec031", "letters", None), scope, frozenset())
    with pytest.raises(ValidationError):
        BookScope(work_id="pg2397", book_version_id=VERSION, chapter_max=1,
            unit_ids=(f"{VERSION}-sec032",))


def test_grounding_rejects_cross_part_before_retrieval():
    librarian = Librarian()
    token = set_confirmed_reading(ConfirmedReading(work_id="pg2397", chapter_max=3))
    try:
        request = build_request("How did this happen?", "pg2397", VERSION,
            ReadingBoundary(chapter_number=1, chapter_state="completed", part_id="part-iii"))
        with patch.object(librarian, "retrieve", side_effect=AssertionError("must not retrieve")):
            response = asyncio.run(_grounding_evidence(request, librarian=librarian, strength_judge=AsyncMock()))
        assert response.kind == "clarification"
    finally:
        reset_confirmed_reading(token)


def test_named_grounding_reads_only_exact_letter_and_connection_keeps_permission():
    from pathlib import Path
    from apps.backend.contracts import ConnectionBrief
    from src.linger.agents.librarian.models import EvidenceStrengthDecision
    from src.linger.orchestration.connection import _build_task, _evidence_is_in_scope
    from src.linger.orchestration.turn_context import set_turn_evidence, reset_turn_evidence

    librarian = Librarian()
    reading = ConfirmedReading(work_id="pg2397", part_id="letters", unit_ids=(f"{VERSION}-sec032",))
    token = set_confirmed_reading(reading)
    evidence_token = set_turn_evidence(())
    opened = []
    original = Path.read_text

    def recording_read(path, *args, **kwargs):
        if path.suffix == ".md":
            opened.append(path)
        return original(path, *args, **kwargs)

    async def strength(query, evidence):
        return EvidenceStrengthDecision(evidence_strength="sufficient", strength_reason="Matches the letter.",
            relevant_evidence_ids=tuple(item.evidence_id for item in evidence))

    try:
        request = build_request("Boston school", "pg2397", VERSION,
            ReadingBoundary(chapter_state="completed", part_id="letters", unit_ids=reading.unit_ids))
        request = request.model_copy(update={"options": request.options.model_copy(update={"retrieval_score_threshold": 0})})
        with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
            response = asyncio.run(_grounding_evidence(request, librarian=librarian, strength_judge=strength))
        assert response.kind == "result"
        assert response.evidence
        assert response.searched_scope.unit_ids == reading.unit_ids
        assert len(set(opened)) == 1
        assert "032-" in opened[0].name
        task = _build_task(ConnectionBrief(cue="Learning to communicate", intent="find_connection"), librarian=librarian)
        assert task.scope.book_scopes[0].unit_ids == reading.unit_ids
        for canonical in response.evidence:
            assert permits_scope(reading, canonical)
            item = EvidenceItem(evidence_id=canonical.evidence_id, work_id=canonical.work_id,
                book_version_id=canonical.book_version_id, chapter_id=canonical.chapter_id,
                chapter=canonical.chapter_number, part_id=canonical.part_id, source_title="The Story of My Life",
                location=canonical.location, source_sha256=canonical.source_sha256,
                source_lines=canonical.source_lines, excerpt=canonical.text, relevance=1)
            assert _evidence_is_in_scope(item, task)
            assert not _evidence_is_in_scope(item.model_copy(update={"chapter_id": f"{VERSION}-sec031"}), task)
    finally:
        reset_turn_evidence(evidence_token)
        reset_confirmed_reading(token)
