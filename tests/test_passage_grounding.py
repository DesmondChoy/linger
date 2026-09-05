"""Exact session-supported grants cannot become chapter retrieval permission."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.contracts.librarian import (
    AccessScope,
    LibrarianRequest,
    PassageGrant,
    RetrievalFailure,
    RetrievalOptions,
    RetrievalResult,
)
from src.linger.contracts.reading import ReadingBoundary
from src.linger.orchestration import turn_context
from src.linger.orchestration.grounding import BookVersionOutOfScope, grounding_evidence


class PassageGroundingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        corpus = Librarian()
        self.record = corpus.fetch_by_id("pg11-v01b38ea4-ch05-ln0974-0975")
        assert self.record is not None
        self.grant = PassageGrant(
            records=(self.record,), supporting_statement_ids=("reader-1",)
        )
        self.reading_token = turn_context.set_confirmed_reading(None)
        self.routing_token = turn_context.set_routing_context()
        self.evidence_token = turn_context.set_turn_evidence(())
        turn_context.bind_passage_grant(self.grant)
        self.librarian = MagicMock(spec=Librarian)
        self.librarian.supports_revision.return_value = True
        self.librarian.fetch_by_id.return_value = self.record
        self.judge = AsyncMock(return_value=EvidenceStrengthDecision(
            evidence_strength="sufficient",
            strength_reason="The exact paragraph supplies Alice's wording.",
            relevant_evidence_ids=(self.record.evidence_id,),
            limitations=(),
        ))

    def tearDown(self) -> None:
        turn_context.reset_turn_evidence(self.evidence_token)
        turn_context.reset_routing_context(self.routing_token)
        turn_context.reset_confirmed_reading(self.reading_token)

    def request(self, **changes: object) -> LibrarianRequest:
        values = {
            "request_id": "passage-search",
            "query": "What does Alice actually say?",
            "work_id": self.record.work_id,
            "book_version_id": self.record.book_version_id,
            "reading_boundary": None,
            "access_scope": AccessScope(
                allowed_book_version_ids=(self.record.book_version_id, "another-version")
            ),
            "options": RetrievalOptions(),
            **changes,
        }
        return LibrarianRequest.model_validate(values)

    async def search(self, **changes: object):
        return await grounding_evidence(
            self.request(**changes), librarian=self.librarian, strength_judge=self.judge
        )

    async def test_private_grant_becomes_evidence_only_after_exact_grounding(self) -> None:
        self.assertEqual({}, dict(turn_context.turn_evidence()))

        response = await self.search()

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual(self.grant.scope, response.searched_scope)
        self.assertEqual((self.record,), response.evidence)
        self.librarian.fetch_by_id.assert_called_once_with(self.record.evidence_id)
        self.librarian.retrieve.assert_not_called()
        self.assertEqual({self.record.evidence_id: self.record}, dict(turn_context.turn_evidence()))
        self.assertIsNone(turn_context.confirmed_reading())

    async def test_query_and_declared_chapter_cannot_expand_the_passage(self) -> None:
        query = "Tell me everything in the last chapter."
        response = await self.search(
            query=query,
            reading_boundary=ReadingBoundary(chapter_number=12, chapter_state="completed"),
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual((self.record,), response.evidence)
        self.judge.assert_awaited_once_with(query, (self.record,))
        self.librarian.retrieve.assert_not_called()

    async def test_changed_or_missing_canonical_record_fails_without_registration(self) -> None:
        for fetched in (None, self.record.model_copy(update={"text": "changed text"})):
            with self.subTest(fetched=fetched):
                self.librarian.fetch_by_id.return_value = fetched
                response = await self.search()

                self.assertIsInstance(response, RetrievalFailure)
                self.assertEqual({}, dict(turn_context.turn_evidence()))
        self.judge.assert_not_awaited()
        self.librarian.retrieve.assert_not_called()

    async def test_wrong_work_or_revision_cannot_use_a_passage_grant(self) -> None:
        for changes in ({"work_id": "another-work"}, {"book_version_id": "another-version"}):
            with self.subTest(changes=changes):
                with self.assertRaises(BookVersionOutOfScope):
                    await self.search(**changes)
        self.librarian.fetch_by_id.assert_not_called()
        self.librarian.retrieve.assert_not_called()

    async def test_strength_selection_can_only_register_selected_granted_records(self) -> None:
        self.judge.return_value = EvidenceStrengthDecision(
            evidence_strength="none",
            strength_reason="The request is unrelated to the permitted passage.",
            relevant_evidence_ids=(),
            limitations=(),
        )

        response = await self.search()

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("no_evidence", response.outcome)
        self.assertEqual((), response.evidence)
        self.assertEqual({}, dict(turn_context.turn_evidence()))

    async def test_only_strength_selected_subset_of_grant_is_registered(self) -> None:
        other = Librarian().fetch_by_id("pg11-v01b38ea4-ch05-ln1179-1179")
        assert other is not None
        grant = PassageGrant(
            records=(self.record, other), supporting_statement_ids=("reader-1",)
        )
        turn_context.reset_routing_context(self.routing_token)
        self.routing_token = turn_context.set_routing_context()
        turn_context.bind_passage_grant(grant)
        records_by_id = {record.evidence_id: record for record in grant.records}
        self.librarian.fetch_by_id.side_effect = records_by_id.__getitem__

        response = await self.search()

        self.assertEqual((self.record,), response.evidence)
        self.judge.assert_awaited_once_with(self.request().query, grant.records)
        self.assertEqual({self.record.evidence_id}, set(turn_context.turn_evidence()))
        self.librarian.retrieve.assert_not_called()

    async def test_canonical_fetch_exception_returns_typed_failure(self) -> None:
        self.librarian.fetch_by_id.side_effect = RuntimeError("corpus unavailable")

        response = await self.search()

        self.assertIsInstance(response, RetrievalFailure)
        self.assertEqual("retrieval_unavailable", response.error_code)
        self.assertEqual({}, dict(turn_context.turn_evidence()))
        self.judge.assert_not_awaited()

    async def test_passage_telemetry_does_not_claim_chapter_permission(self) -> None:
        with patch("src.linger.orchestration.grounding.set_span_attrs") as attributes:
            await self.search()

        recorded = attributes.call_args.args[1]
        self.assertEqual("passages", recorded["scope.kind"])
        self.assertNotIn("scope.chapter_max", recorded)

    async def test_strength_judge_cannot_select_an_ungranted_id(self) -> None:
        self.judge.return_value = EvidenceStrengthDecision(
            evidence_strength="sufficient",
            strength_reason="An invented neighboring paragraph.",
            relevant_evidence_ids=("not-granted",),
            limitations=(),
        )

        response = await self.search()

        self.assertIsInstance(response, RetrievalFailure)
        self.assertEqual({}, dict(turn_context.turn_evidence()))
