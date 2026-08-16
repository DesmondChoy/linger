"""End-to-end tests from trusted boundary through selected retrieval and judgment."""

import re
import unittest
from unittest.mock import AsyncMock

import numpy as np

from apps.backend.hybrid_librarian import HybridLibrarian
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.contracts.librarian import ClarificationRequest, RetrievalFailure, RetrievalResult
from src.linger.contracts.reading import ReadingBoundary
from src.linger.contracts.turn import ConfirmedReading
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from src.linger.orchestration.grounding import build_request, grounding_evidence
from src.linger.orchestration.turn_context import reset_confirmed_reading, set_confirmed_reading


WORDS = re.compile(r"[a-z]+")


class ConstantEmbedding:
    def passage_embed(self, documents: list[str]):
        return iter(np.ones((len(documents), 2)))

    def query_embed(self, query: str):
        return iter((np.ones(2),))


class TermReranker:
    def rerank(self, query: str, documents: list[str]):
        terms = set(WORDS.findall(query.casefold()))
        return [10.0 if terms & set(WORDS.findall(text.casefold())) else -10.0 for text in documents]


class FailingEmbedding(ConstantEmbedding):
    def passage_embed(self, documents: list[str]):
        raise RuntimeError("embedding unavailable")


class LibrarianEndToEndTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.token = set_confirmed_reading(
            ConfirmedReading(work_id=WORK_ID, chapter_max=5)
        )
        self.librarian = HybridLibrarian(
            embedding_model=ConstantEmbedding(), reranker=TermReranker()
        )

    def tearDown(self) -> None:
        reset_confirmed_reading(self.token)

    def request(self, query: str, boundary: ReadingBoundary | None):
        return build_request(query, WORK_ID, BOOK_VERSION_ID, boundary)

    async def test_completed_boundary_returns_judged_exact_evidence(self) -> None:
        judge = AsyncMock()

        async def sufficient(_query, evidence):
            return EvidenceStrengthDecision(
                evidence_strength="sufficient",
                strength_reason="The passage directly answers the question.",
                relevant_evidence_ids=(evidence[0].evidence_id,),
            )

        judge.side_effect = sufficient
        response = await grounding_evidence(
            self.request(
                "Why can Alice not explain herself to the Caterpillar?",
                ReadingBoundary(chapter_number=5, chapter_state="completed"),
            ),
            librarian=self.librarian,
            strength_judge=judge,
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("sufficient", response.evidence_strength)
        self.assertEqual(1, len(response.evidence))
        record = response.evidence[0]
        start, end = record.source_lines
        source = BOOK.default_source.read_text(encoding="utf-8").splitlines()
        self.assertEqual("\n".join(source[start - 1 : end]), record.text)

    async def test_started_boundary_excludes_current_chapter_from_judge(self) -> None:
        async def weak(_query, evidence):
            return EvidenceStrengthDecision(
                evidence_strength="weak",
                strength_reason="Only earlier context is available.",
                relevant_evidence_ids=(evidence[0].evidence_id,),
                limitations=("Chapter 5 is not eligible until completed.",),
            )

        response = await grounding_evidence(
            self.request(
                "What does the Caterpillar say?",
                ReadingBoundary(chapter_number=5, chapter_state="started"),
            ),
            librarian=self.librarian,
            strength_judge=weak,
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("weak", response.evidence_strength)
        self.assertTrue(all(record.chapter_number <= 4 for record in response.evidence))

    async def test_ambiguous_boundary_clarifies_before_selected_retrieval(self) -> None:
        response = await grounding_evidence(
            self.request("What happens next?", None), librarian=self.librarian
        )
        self.assertIsInstance(response, ClarificationRequest)

    async def test_irrelevant_retrieval_matches_are_judged_as_none(self) -> None:
        judge = AsyncMock(
            return_value=EvidenceStrengthDecision(
                evidence_strength="none",
                strength_reason="The matching name does not support the requested event.",
                relevant_evidence_ids=(),
            )
        )
        response = await grounding_evidence(
            self.request(
                "Where does Alice repair a spaceship?",
                ReadingBoundary(chapter_number=5, chapter_state="completed"),
            ),
            librarian=self.librarian,
            strength_judge=judge,
        )
        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("none", response.evidence_strength)
        self.assertEqual((), response.evidence)
        judge.assert_awaited_once()

    async def test_retrieval_failure_degrades_to_typed_failure(self) -> None:
        failing = HybridLibrarian(
            embedding_model=FailingEmbedding(), reranker=TermReranker()
        )
        response = await grounding_evidence(
            self.request(
                "Caterpillar",
                ReadingBoundary(chapter_number=5, chapter_state="completed"),
            ),
            librarian=failing,
        )
        self.assertIsInstance(response, RetrievalFailure)
        self.assertEqual("retrieval_unavailable", response.error_code)


if __name__ == "__main__":
    unittest.main()
