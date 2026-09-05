"""One turn's session-supported route cannot acquire broader authority later."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from apps.backend.librarian import Librarian
from src.linger.agents.muse.tools import librarian_route
from src.linger.contracts.librarian import (
    AccessScope,
    BoundaryCandidate,
    BoundaryPassages,
    BoundarySupportLocation,
    BoundaryUncertain,
    ClarificationRequest,
    LibrarianRequest,
    PassageGrant,
    RetrievalOptions,
    RoutedPassages,
)
from src.linger.contracts.reading import ReadingBoundary
from src.linger.contracts.session import ReaderStatement
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration import turn_context
from src.linger.orchestration.grounding import grounding_evidence


class PassageRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.librarian = Librarian()
        self.record = self.librarian.fetch_by_id("pg11-v01b38ea4-ch05-ln0974-0975")
        assert self.record is not None
        self.grant = PassageGrant(
            records=(self.record,), supporting_statement_ids=("reader-1",)
        )
        self.boundary = BoundaryPassages(grant=self.grant, confidence=0.98)
        self.message = "What does Alice say to the Caterpillar in Alice's Adventures in Wonderland?"
        self.prior = (ReaderStatement(
            statement_id="reader-1", text="I reached Alice's conversation with the Caterpillar."
        ),)
        self.reading_token = turn_context.set_confirmed_reading(None)
        self.reader_token = turn_context.set_reader_message(self.message)
        self.statements_token = turn_context.set_reader_statements(self.prior)
        self.memories_token = turn_context.set_active_memories(())
        self.routing_token = turn_context.set_routing_context()
        self.evidence_token = turn_context.set_turn_evidence(())

    def tearDown(self) -> None:
        turn_context.reset_turn_evidence(self.evidence_token)
        turn_context.reset_routing_context(self.routing_token)
        turn_context.reset_active_memories(self.memories_token)
        turn_context.reset_reader_statements(self.statements_token)
        turn_context.reset_reader_message(self.reader_token)
        turn_context.reset_confirmed_reading(self.reading_token)

    def request(self) -> LibrarianRequest:
        return LibrarianRequest(
            request_id="ground-after-route", query="What are her exact words?",
            work_id=self.record.work_id, book_version_id=self.record.book_version_id,
            reading_boundary=ReadingBoundary(chapter_number=12, chapter_state="completed"),
            access_scope=AccessScope(allowed_book_version_ids=(self.record.book_version_id,)),
            options=RetrievalOptions(),
        )

    async def test_concurrent_argument_free_routes_share_one_inference(self) -> None:
        inference_entered = asyncio.Event()
        finish_inference = asyncio.Event()
        second_started = asyncio.Event()

        async def infer(*_args, **_kwargs):
            inference_entered.set()
            await finish_inference.wait()
            return self.boundary

        async def second_call():
            second_started.set()
            return await librarian_route()

        with patch("src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(
            side_effect=infer,
        )) as inference:
            first = asyncio.create_task(librarian_route())
            await asyncio.wait_for(inference_entered.wait(), timeout=1)
            second = asyncio.create_task(second_call())
            await asyncio.wait_for(second_started.wait(), timeout=1)
            self.assertEqual(1, inference.await_count)
            self.assertFalse(second.done())
            finish_inference.set()
            results = await asyncio.gather(first, second)

        inference.assert_awaited_once()
        self.assertEqual(self.message, inference.await_args.args[0])
        self.assertEqual(self.prior, inference.await_args.kwargs["prior_reader_statements"])
        self.assertIs(results[0], results[1])
        self.assertIsInstance(results[0], RoutedPassages)
        self.assertEqual(self.grant, turn_context.passage_grant())
        self.assertIsNone(turn_context.confirmed_reading())

    async def test_repeated_route_cannot_replace_passages_with_a_chapter_grant(self) -> None:
        later = BoundaryCandidate(
            kind="candidate", work_id=self.record.work_id,
            book_version_id=self.record.book_version_id, max_chapter_inclusive=12,
            confidence=0.99, authorization_basis="memory_supported",
            supporting_memory_ids=("memory-later",),
            supporting_locations=(BoundarySupportLocation(
                evidence_id="private-later-evidence", chapter_number=12, location="Chapter 12",
            ),),
        )
        with patch("src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(
            side_effect=(self.boundary, later),
        )) as inference:
            first = await librarian_route()
            again = await librarian_route()

        inference.assert_awaited_once()
        self.assertIs(first, again)
        self.assertEqual(self.grant.scope.evidence_ids, again.evidence_ids)
        self.assertIsNone(turn_context.confirmed_reading())

    async def test_cached_clarification_blocks_grounding_with_confirmed_chapter(self) -> None:
        turn_context.bind_confirmed_reading(ConfirmedReading(work_id=self.record.work_id, chapter_max=12))
        uncertain = BoundaryUncertain(
            kind="uncertain", work_id=self.record.work_id,
            book_version_id=self.record.book_version_id, reason_code="conflicting_context",
            clarification_question="Have you read this passage, or are you asking about a later scene?",
        )
        judge = AsyncMock()
        with (
            patch("src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(
                return_value=uncertain,
            )),
            patch.object(self.librarian, "retrieve", side_effect=AssertionError("retrieved")) as retrieve,
            patch.object(self.librarian, "fetch_by_id", side_effect=AssertionError("fetched")) as fetch,
        ):
            route = await librarian_route()
            response = await grounding_evidence(
                self.request(), librarian=self.librarian, strength_judge=judge,
            )

        self.assertIsInstance(route, ClarificationRequest)
        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual(route.question, response.question)
        self.assertEqual("ground-after-route", response.request_id)
        retrieve.assert_not_called()
        fetch.assert_not_called()
        judge.assert_not_awaited()
        self.assertEqual({}, dict(turn_context.turn_evidence()))

    async def test_passage_above_explicit_chapter_clarifies_without_binding_grant(self) -> None:
        reading = ConfirmedReading(work_id=self.record.work_id, chapter_max=3)
        turn_context.bind_confirmed_reading(reading)
        with patch("src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(
            return_value=self.boundary,
        )):
            response = await librarian_route()

        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual("conflicting_context", response.reason_code)
        self.assertIsNone(turn_context.passage_grant())
        self.assertEqual(reading, turn_context.confirmed_reading())

    def test_nested_turn_context_is_isolated_and_reset_restores_outer_snapshot(self) -> None:
        turn_context.bind_passage_grant(self.grant)
        outer = turn_context.routing_context()
        routing_token = turn_context.set_routing_context()
        statements_token = turn_context.set_reader_statements(())
        reader_token = turn_context.set_reader_message("An unrelated reader's turn")
        try:
            self.assertIsNot(outer, turn_context.routing_context())
            self.assertIsNone(turn_context.passage_grant())
            self.assertIsNone(turn_context.routing_context().response)
            self.assertEqual((), turn_context.reader_statements())
            self.assertNotEqual(self.message, turn_context.reader_message())
        finally:
            turn_context.reset_reader_message(reader_token)
            turn_context.reset_reader_statements(statements_token)
            turn_context.reset_routing_context(routing_token)

        self.assertIs(outer, turn_context.routing_context())
        self.assertEqual(self.grant, turn_context.passage_grant())
        self.assertEqual(self.prior, turn_context.reader_statements())
        self.assertEqual(self.message, turn_context.reader_message())
