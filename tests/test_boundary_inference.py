"""Two-phase Librarian spoiler-boundary inference tests."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.backend.contracts import EvidenceBundle, EvidenceItem
from apps.backend.librarian import Librarian, RegisteredCorpusScope, WorkRouteCandidate
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.contracts.librarian import BoundaryCandidate, BoundaryUncertain
from src.linger.orchestration.boundary import infer_spoiler_boundary
from src.linger.services.memory import (
    AccountContext, AutomaticMemoryCandidate, MemoryPolicyService, MemoryRecord,
)

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

    def work_candidates(self, text: str, allowed_versions: tuple[str, ...]):
        if VERSION_ID in allowed_versions and any(
            cue in text.casefold() for cue in ("alice", "caterpillar", "identity")
        ):
            return (
                WorkRouteCandidate(
                    scope=self.registered_scope(WORK_ID, VERSION_ID),
                    strength="strong",
                    reasons=("test_signal",),
                ),
            )
        return ()

    def fetch_by_id(self, evidence_id: str):
        if evidence_id in {
            self.chapter_five.evidence_id,
            self.chapter_eight.evidence_id,
        }:
            return SimpleNamespace(
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
            )
        return None

    def retrieve(self, request):
        self.requests.append(request)
        return EvidenceBundle(
            items=[self.chapter_five, self.chapter_eight],
            retrieval_note="private full-work search",
        )


class BoundaryInferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_separate_searches_preserve_current_and_memory_anchors(self) -> None:
        librarian = FakeLibrarian()
        line = "Current event question"
        stored = memory("memory-anchor", "Alice and the Caterpillar")
        received = []

        def retrieve(request):
            records = [librarian.chapter_five] if request.query == stored.text else [librarian.chapter_eight]
            return EvidenceBundle(items=records, retrieval_note="private")

        async def judge(_line, memories, evidence, _statements):
            received.append((memories, evidence))
            return BoundaryInferenceDecision(outcome="uncertain", confidence=0.2,
                                             reason_code="conflicting_context")

        with patch.object(librarian, "retrieve", side_effect=retrieve) as search:
            result = await infer_spoiler_boundary(
                line, work_id=WORK_ID, book_version_id=VERSION_ID,
                memories=(stored,), librarian=librarian, judge=judge,
            )
        self.assertEqual([line, stored.text], [call.args[0].query for call in search.call_args_list])
        self.assertEqual((stored,), received[0][0])
        self.assertEqual([8, 5], [record.chapter_number for record in received[0][1]])
        self.assertEqual("conflicting_context", result.reason_code)

    async def test_memory_only_hits_do_not_authorize_current_position(self) -> None:
        librarian = FakeLibrarian()
        line = "An ambiguous current event"
        stored = memory("memory-anchor", "Alice and the Caterpillar")
        judge = AsyncMock(return_value=BoundaryInferenceDecision(
            outcome="uncertain", confidence=0.2, reason_code="conflicting_context",
        ))

        def retrieve(request):
            return EvidenceBundle(
                items=[] if request.query == line else [librarian.chapter_five],
                retrieval_note="private",
            )

        with patch.object(librarian, "retrieve", side_effect=retrieve):
            result = await infer_spoiler_boundary(
                line, work_id=WORK_ID, book_version_id=VERSION_ID,
                memories=(stored,), librarian=librarian, judge=judge,
            )
        judge.assert_not_called()
        self.assertEqual("insufficient_context", result.reason_code)
        self.assertIsNone(result.candidate_chapter)

    async def test_separate_candidates_are_deduplicated_and_bounded_fairly(self) -> None:
        librarian = FakeLibrarian()
        line = "Current event"
        stored = memory("memory-anchor", "Alice and the Caterpillar")
        current = [item(chapter, f"event {chapter}") for chapter in range(1, 11)]
        previous = [item(12, "Memory anchor"), *current]
        received = []

        async def judge(_line, _memories, evidence, _statements):
            received.extend(evidence)
            return BoundaryInferenceDecision(outcome="uncertain", confidence=0.2,
                                             reason_code="conflicting_context")

        def retrieve(request):
            return EvidenceBundle(items=previous if request.query == stored.text else current,
                                  retrieval_note="private")

        with patch.object(librarian, "retrieve", side_effect=retrieve):
            await infer_spoiler_boundary(
                line, work_id=WORK_ID, book_version_id=VERSION_ID,
                memories=(stored,), librarian=librarian, judge=judge,
            )
        self.assertEqual(10, len(received))
        self.assertEqual(10, len({record.evidence_id for record in received}))
        self.assertEqual([1, 12], [record.chapter_number for record in received[:2]])

    async def test_adopted_prop_reaches_private_judge_from_saved_memory(self) -> None:
        package = Path(__file__).resolve().parents[1] / (
            "synthetic-journal-evaluation/packages/2026-09-03T200134+0800/backstory.json"
        )
        backstory = json.loads(package.read_text())
        prop = backstory["props"][0]
        with tempfile.TemporaryDirectory() as root:
            service = MemoryPolicyService(Path(root))
            account = AccountContext("synthetic-memory-regression")
            service.set_capture_enabled(account, True)
            saved = service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=prop["source_text"], source_event_id=prop["prop_id"],
                    review_allows_capture=True, contains_sensitive_content=False,
                ),
            ).record
            service.set_capture_enabled(account, False)
            self.assertEqual([], service.list_for_retrieval(AccountContext("other-account")))
            memories = tuple(service.list_for_retrieval(account))
            self.assertEqual([saved.memory_id], [m.memory_id for m in memories])
            self.assertEqual(prop["source_text"], memories[0].text)
            self.assertEqual((), memories[0].evidence_ids)

            for line in backstory["lines"][:2]:
                with self.subTest(scene=line["scene_id"]):
                    received = []

                    async def judge(current_line, selected, evidence, statements):
                        received.append((current_line, selected, evidence, statements))
                        return BoundaryInferenceDecision(
                            outcome="uncertain", confidence=0.2,
                            reason_code="insufficient_context",
                        )

                    result = await infer_spoiler_boundary(
                        line["text"], work_id=WORK_ID, book_version_id=VERSION_ID,
                        memories=memories, librarian=Librarian(), judge=judge,
                    )
                    self.assertEqual(1, len(received))
                    self.assertEqual(line["text"], received[0][0])
                    self.assertEqual(memories, received[0][1])
                    self.assertTrue(received[0][2])
                    self.assertEqual((), received[0][3])
                    self.assertIsInstance(result, BoundaryUncertain)
                    self.assertIsNone(result.candidate_chapter)
            self.assertEqual([saved], service.list_active(account))
            self.assertFalse(service.capture_enabled(account))

    async def test_failed_or_inconsistent_memory_search_fails_closed(self) -> None:
        librarian = FakeLibrarian()
        stored = memory("memory-anchor", "Alice and the Caterpillar")
        current = EvidenceBundle(items=[librarian.chapter_five], retrieval_note="private")
        inconsistent = EvidenceBundle(items=[librarian.chapter_five.model_copy(
            update={"excerpt": "Different text for the same evidence ID"},
        )], retrieval_note="private")
        for memory_result in (RuntimeError("search unavailable"), inconsistent):
            with self.subTest(result=type(memory_result).__name__):
                judge = AsyncMock()
                with patch.object(librarian, "retrieve", side_effect=[current, memory_result]):
                    result = await infer_spoiler_boundary(
                        "Current event", work_id=WORK_ID, book_version_id=VERSION_ID,
                        memories=(stored,), librarian=librarian, judge=judge,
                    )
                judge.assert_not_called()
                self.assertEqual("inference_unavailable", result.reason_code)

    async def test_caterpillar_memory_infers_chapter_five_without_exposing_text(self) -> None:
        librarian = FakeLibrarian()
        stored = memory(
            "memory-1",
            "The Caterpillar's questions made me think about how uncertain I am about my identity.",
            (librarian.chapter_five.evidence_id,),
        )

        async def judge(current_line, memories, evidence, prior_reader_statements):
            self.assertEqual((), prior_reader_statements)
            self.assertEqual((stored,), memories)
            self.assertEqual({5, 8}, {record.chapter_number for record in evidence})
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.93,
                authorization_basis="memory_supported",
                supporting_memory_ids=(stored.memory_id,),
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
        self.assertEqual("memory_supported", result.authorization_basis)
        self.assertEqual((stored.memory_id,), result.supporting_memory_ids)
        self.assertEqual(12, librarian.requests[0].book_scopes[0].chapter_max)
        serialized = result.model_dump_json()
        self.assertNotIn("Caterpillar asks Alice", serialized)
        self.assertNotIn(PRIVATE_LATER_TEXT, serialized)
        self.assertIn("Chapter 5", serialized)

    async def test_low_confidence_memory_candidate_requires_clarification(self) -> None:
        librarian = FakeLibrarian()
        stored = memory(
            "memory-low",
            "The Caterpillar made me think about identity.",
            (librarian.chapter_five.evidence_id,),
        )

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.61,
                authorization_basis="memory_supported",
                supporting_memory_ids=(stored.memory_id,),
                supporting_evidence_ids=(librarian.chapter_five.evidence_id,),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(stored,),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("low_confidence", result.reason_code)
        self.assertEqual(5, result.candidate_chapter)
        self.assertEqual(0.61, result.confidence)
        self.assertEqual("memory_supported", result.authorization_basis)
        self.assertEqual((stored.memory_id,), result.supporting_memory_ids)
        self.assertTrue(result.supporting_locations)
        self.assertIn("completed Chapter 5", result.clarification_question)

    async def test_line_only_candidate_never_authorizes_a_ceiling(self) -> None:
        librarian = FakeLibrarian()

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.99,
                authorization_basis="line_only",
                supporting_evidence_ids=(librarian.chapter_five.evidence_id,),
            )

        result = await infer_spoiler_boundary(
            "Why does the Caterpillar ask Alice who she is?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("progress_unverified", result.reason_code)
        self.assertEqual("line_only", result.authorization_basis)
        self.assertEqual(5, result.candidate_chapter)

    async def test_unrelated_memories_are_not_sent_to_the_judge(self) -> None:
        librarian = FakeLibrarian()
        unrelated = memory("memory-2", "I need to repair the spaceship tomorrow.")

        async def judge(_line, memories, _evidence, _prior_reader_statements):
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
            (librarian.chapter_five.evidence_id,),
        )
        later_memory = memory(
            "memory-4",
            "Alice in the garden reminded me of a later disagreement.",
            (librarian.chapter_eight.evidence_id,),
        )

        async def judge(_line, memories, _evidence, _prior_reader_statements):
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
                authorization_basis="line_only",
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
                authorization_basis="line_only",
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

    async def test_unknown_supporting_memory_id_fails_closed(self) -> None:
        librarian = FakeLibrarian()
        stored = memory(
            "memory-known",
            "The Caterpillar made me think about identity.",
            (librarian.chapter_five.evidence_id,),
        )

        async def judge(*_args):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_number=5,
                confidence=0.95,
                authorization_basis="memory_supported",
                supporting_memory_ids=("memory-invented",),
                supporting_evidence_ids=(librarian.chapter_five.evidence_id,),
            )

        result = await infer_spoiler_boundary(
            "Why does Alice feel uncertain?",
            work_id=WORK_ID,
            book_version_id=VERSION_ID,
            memories=(stored,),
            librarian=librarian,  # type: ignore[arg-type]
            judge=judge,
        )

        self.assertIsInstance(result, BoundaryUncertain)
        assert isinstance(result, BoundaryUncertain)
        self.assertEqual("inference_unavailable", result.reason_code)


if __name__ == "__main__":
    unittest.main()
