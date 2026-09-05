"""Session-supported passage permissions use canonical paragraphs, not chapters."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from apps.backend.contracts import EvidenceBundle, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.contracts.librarian import BoundaryPassages, BoundaryUncertain
from src.linger.contracts.session import ReaderStatement
from src.linger.orchestration.boundary import infer_spoiler_boundary, judge_spoiler_boundary

WORK = "pg11"
VERSION = "pg11-v01b38ea4"
WINDOW = f"{VERSION}-ch05-ln0960-1016"
ANCHOR = f"{VERSION}-ch05-ln0964-0964"
QUOTE = f"{VERSION}-ch05-ln0974-0975"
FIRST = (
    "Got up to the part with the caterpillar on the mushroom tonight. It keeps "
    "asking Alice who she is and she can't answer properly. I had to put the "
    "book down for a minute. Reading two chapters a night if I can stay awake."
)
SECOND = (
    "There's a bit where Alice tries to tell the caterpillar that she can't "
    "explain herself because she isn't herself at the moment. I've been turning "
    "it over all week but I know I'm mangling the actual wording. What does she "
    "actually say there?"
)
PRIOR = (ReaderStatement(statement_id="reader-1", text=FIRST),)


def decision(**changes):
    from src.linger.agents.librarian.models import PassageInferenceDecision

    values = dict(
        outcome="passages", work_id=WORK, book_version_id=VERSION, confidence=0.98,
        supporting_statement_ids=("reader-1",), supporting_evidence_ids=(ANCHOR,),
        passage_evidence_ids=(QUOTE,),
    )
    values.update(changes)
    return PassageInferenceDecision(**values)


class PassageInferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.librarian = Librarian()
        window = self.librarian.fetch_by_id(WINDOW)
        assert window is not None
        self.window = window
        item = EvidenceItem(
            **{key: value for key, value in window.model_dump().items()
               if key not in {"chapter_number", "text"}},
            chapter=window.chapter_number, excerpt=window.text,
            source_title="Alice's Adventures in Wonderland", relevance=0.95,
        )
        self.bundle = EvidenceBundle(items=[item], retrieval_note="private")

    async def infer(self, judge, *, prior=PRIOR):
        with patch.object(self.librarian, "retrieve", return_value=self.bundle) as retrieve:
            result = await infer_spoiler_boundary(
                SECOND, work_id=WORK, book_version_id=VERSION, memories=(),
                librarian=self.librarian, prior_reader_statements=prior, judge=judge,
            )
        self.assertEqual(1, retrieve.call_count)
        self.search_request = retrieve.call_args.args[0]
        return result

    async def test_alice_pair_grants_only_requested_canonical_paragraph(self) -> None:
        async def judge(line, memories, paragraphs, prior):
            self.assertEqual(SECOND, line)
            self.assertEqual((), memories)
            self.assertEqual(PRIOR, prior)
            self.assertNotIn(WINDOW, {record.evidence_id for record in paragraphs})
            self.assertTrue(all("\n\n" not in record.text for record in paragraphs))
            return decision()

        result = await self.infer(judge)
        self.assertIsInstance(result, BoundaryPassages)
        self.assertEqual((self.librarian.fetch_by_id(QUOTE),), result.grant.records)
        self.assertEqual(("reader-1",), result.grant.supporting_statement_ids)
        self.assertNotIn(ANCHOR, result.grant.scope.evidence_ids)
        self.assertIn(FIRST, self.search_request.query)

    async def test_unsupplied_support_and_parent_window_fail_closed(self) -> None:
        for changes in (
            {"supporting_statement_ids": ("assistant-1",)},
            {"supporting_statement_ids": ("reader-missing",)},
            {"supporting_evidence_ids": ("missing",)},
            {"supporting_evidence_ids": (WINDOW,)},
            {"passage_evidence_ids": (WINDOW,)},
            {"passage_evidence_ids": ("missing",)},
            {"work_id": "other-work"},
            {"book_version_id": "other-revision"},
        ):
            with self.subTest(changes=changes):
                async def judge(*_args):
                    return decision(**changes)

                result = await self.infer(judge)
                self.assertIsInstance(result, BoundaryUncertain)
                self.assertEqual("inference_unavailable", result.reason_code)

    async def test_low_confidence_is_not_a_passage_grant(self) -> None:
        result = await self.infer(AsyncMock(return_value=decision(confidence=0.6)))
        self.assertIsInstance(result, BoundaryUncertain)
        self.assertEqual("low_confidence", result.reason_code)

    async def test_no_history_cannot_authorize_passages(self) -> None:
        with patch.object(
            self.librarian, "candidate_paragraphs", side_effect=AssertionError("narrowed")
        ):
            result = await self.infer(AsyncMock(return_value=decision()), prior=())
        self.assertIsInstance(result, BoundaryUncertain)

    async def test_duplicate_or_empty_selections_fail_closed(self) -> None:
        for field, value in (
            ("supporting_statement_ids", "reader-1"),
            ("supporting_evidence_ids", ANCHOR),
            ("passage_evidence_ids", QUOTE),
        ):
            for ids in ((), (value, value)):
                with self.subTest(field=field, ids=ids):
                    invalid = decision().model_copy(update={field: ids})
                    result = await self.infer(AsyncMock(return_value=invalid))
                    self.assertIsInstance(result, BoundaryUncertain)

    async def test_duplicate_input_statement_ids_are_not_usable_support(self) -> None:
        result = await self.infer(AsyncMock(return_value=decision()), prior=PRIOR + PRIOR)
        self.assertIsInstance(result, BoundaryUncertain)

    def test_passage_decision_contract_rejects_chapter_and_memory_authority(self) -> None:
        for changes in (
            {"chapter_number": 5},
            {"supporting_memory_ids": ("memory-1",)},
            {"supporting_statement_ids": ()},
            {"supporting_statement_ids": ("reader-1", "reader-1")},
            {"passage_evidence_ids": (QUOTE,) * 6},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    decision(**changes)

    async def test_semantic_uncertainty_stays_clarification(self) -> None:
        for reason in ("conflicting_context", "insufficient_context", "low_confidence"):
            with self.subTest(reason=reason):
                result = await self.infer(AsyncMock(return_value=BoundaryInferenceDecision(
                    outcome="uncertain", confidence=0.5, reason_code=reason,
                )))
                self.assertIsInstance(result, BoundaryUncertain)
                self.assertEqual(reason, result.reason_code)

    async def test_canonical_candidate_mismatch_does_not_reach_judge(self) -> None:
        self.bundle.items[0] = self.bundle.items[0].model_copy(update={"excerpt": "forged"})
        judge = AsyncMock(return_value=decision())
        result = await self.infer(judge)
        self.assertIsInstance(result, BoundaryUncertain)
        judge.assert_not_awaited()

    async def test_long_history_bounds_search_but_keeps_original_judge_input(self) -> None:
        prior = (ReaderStatement(statement_id="reader-1", text=FIRST * 20),)
        judge = AsyncMock(return_value=decision())
        result = await self.infer(judge, prior=prior)
        self.assertIsInstance(result, BoundaryPassages)
        self.assertLessEqual(len(self.search_request.query), 2000)
        self.assertEqual(prior, judge.await_args.args[3])

    async def test_payload_separates_original_statements_from_memories(self) -> None:
        judge_result = SimpleNamespace(output=decision())
        with patch("src.linger.orchestration.boundary.run_agent_traced", new=AsyncMock(
            return_value=judge_result,
        )) as run:
            await judge_spoiler_boundary(SECOND, (), (self.window,), PRIOR)
        payload = json.loads(run.await_args.args[1])
        self.assertEqual([PRIOR[0].model_dump()], payload["prior_reader_statements"])
        self.assertEqual([], payload["relevant_memories"])
        self.assertEqual("LibrarianBoundaryInferenceInput.v2", run.await_args.kwargs["input_contract"])
        self.assertEqual("2", run.await_args.kwargs["prompt_version"])
