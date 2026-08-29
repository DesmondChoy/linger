"""Two-phase Librarian spoiler-boundary inference tests."""

import unittest

from apps.backend.contracts import EvidenceBundle, EvidenceItem
from apps.backend.librarian import RegisteredCorpusScope, RoutingDecision
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.contracts.librarian import BoundaryCandidate, BoundaryUncertain
from src.linger.orchestration.boundary import infer_spoiler_boundary
from src.linger.services.memory import MemoryRecord

WORK_ID = "pg11"
VERSION_ID = "pg11-v01b38ea4"
SOURCE_HASH = "a" * 64
PRIVATE_LATER_TEXT = "PRIVATE_LATER_CHAPTER_TEXT_MUST_NOT_ESCAPE"


def item(chapter: int, text: str) -> EvidenceItem:
    start = chapter * 100
    return EvidenceItem(
        evidence_id=f"{VERSION_ID}-ch{chapter:02d}-ln{start:04d}-{start + 1:04d}",
        work_id=WORK_ID,
        book_version_id=VERSION_ID,
        chapter_id=f"{VERSION_ID}-ch{chapter:02d}",
        source_title="Alice's Adventures in Wonderland",
        location=f"Chapter {chapter}, source lines {start}-{start + 1}",
        chapter=chapter,
        source_sha256=SOURCE_HASH,
        source_lines=(start, start + 1),
        excerpt=text,
        relevance=0.9,
    )


def memory(memory_id: str, text: str, evidence_ids: tuple[str, ...] = ()) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        account_key="account-key",
        text=text,
        capture_type="automatic",
        source_event_id=f"event-{memory_id}",
        idempotency_key=f"key-{memory_id}",
        evidence_ids=evidence_ids,
        created_at="2026-08-28T00:00:00+00:00",
        updated_at="2026-08-28T00:00:00+00:00",
    )


class FakeLibrarian:
    def __init__(self) -> None:
        self.requests = []
        self.chapter_five = item(5, "The Caterpillar asks Alice who she is.")
        self.chapter_eight = item(8, PRIVATE_LATER_TEXT)

    def registered_scope(self, work_id: str, version_id: str):
        if (work_id, version_id) != (WORK_ID, VERSION_ID):
            return None
        return RegisteredCorpusScope(
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            title="Alice's Adventures in Wonderland",
            max_chapter=12,
        )

    def route_work(self, text: str, allowed_versions: tuple[str, ...]):
        if VERSION_ID in allowed_versions and any(
            cue in text.casefold() for cue in ("alice", "caterpillar", "identity")
        ):
            return RoutingDecision(
                scope=self.registered_scope(WORK_ID, VERSION_ID), confidence=1.0
            )
        return None

    def fetch_by_id(self, evidence_id: str):
        return None

    def retrieve(self, request):
        self.requests.append(request)
        return EvidenceBundle(
            items=[self.chapter_five, self.chapter_eight],
            retrieval_note="private full-work search",
        )


class BoundaryInferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_caterpillar_memory_infers_chapter_five_without_exposing_text(self) -> None:
        librarian = FakeLibrarian()
        stored = memory(
            "memory-1",
            "The Caterpillar's questions made me think about how uncertain I am about my identity.",
        )

        async def judge(current_line, memories, evidence):
            self.assertEqual((stored,), memories)
            self.assertEqual({5, 8}, {record.chapter_number for record in evidence})
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.93,
                supporting_evidence_ids=(librarian.chapter_five.evidence_id,),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice keep struggling to explain who she is?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(stored,),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryCandidate)
        assert isinstance(result, BoundaryCandidate)
        self.assertEqual(5, result.max_chapter_inclusive)
        self.assertEqual(12, librarian.requests[0].book_scopes[0].chapter_max)
        serialized = result.model_dump_json()
        self.assertNotIn("Caterpillar asks Alice", serialized)
        self.assertNotIn(PRIVATE_LATER_TEXT, serialized)
        self.assertIn("Chapter 5", serialized)

    async def test_low_confidence_candidate_requires_clarification_with_support(self) -> None:
        librarian = FakeLibrarian()

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.61,
                supporting_evidence_ids=(librarian.chapter_five.evidence_id,),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("low_confidence", result.reason_code)
        self.assertEqual(5, result.candidate_chapter)
        self.assertEqual(0.61, result.confidence)
        self.assertTrue(result.supporting_locations)
        self.assertIn("completed Chapter 5", result.clarification_question)

    async def test_unrelated_memories_are_not_sent_to_the_judge(self) -> None:
        librarian = FakeLibrarian()
        unrelated = memory("memory-2", "I need to repair the spaceship tomorrow.")

        async def judge(_line, memories, _evidence):
            self.assertEqual((), memories)
            return BoundaryInferenceDecision(
                outcome="uncertain",
                confidence=0.2,
                reason_code="insufficient_context",
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(unrelated,),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("insufficient_context", result.reason_code)

    async def test_conflicting_book_memories_require_clarification(self) -> None:
        librarian = FakeLibrarian()
        chapter_five_memory = memory(
            "memory-3",
            "The Caterpillar made Alice's uncertainty about identity feel familiar.",
        )
        later_memory = memory(
            "memory-4",
            "Alice in the garden reminded me of a later disagreement.",
        )

        async def judge(_line, memories, _evidence):
            self.assertEqual(
                (chapter_five_memory, later_memory),
                memories,
            )
            return BoundaryInferenceDecision(
                outcome="uncertain",
                confidence=0.45,
                reason_code="conflicting_context",
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(chapter_five_memory, later_memory),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("conflicting_context", result.reason_code)
        self.assertIsNone(result.candidate_chapter)

    async def test_unknown_support_id_fails_closed(self) -> None:
        librarian = FakeLibrarian()

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.95,
                supporting_evidence_ids=("invented-evidence",),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("inference_unavailable", result.reason_code)

    async def test_duplicate_support_id_fails_closed(self) -> None:
        librarian = FakeLibrarian()

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.95,
                supporting_evidence_ids=(
                    librarian.chapter_five.evidence_id,
                    librarian.chapter_five.evidence_id,
                ),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("inference_unavailable", result.reason_code)


if __name__ == "__main__":
    unittest.main()
