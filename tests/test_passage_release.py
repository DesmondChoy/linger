"""Passage permission survives release review without becoming chapter access."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic_ai.messages import ToolReturnPart

from apps.backend.contracts import ConnectionBrief
from apps.backend.librarian import Librarian
from src.linger.contracts.librarian import PassageGrant, RetrievalResult, RoutedPassages, SearchedScope
from src.linger.contracts.turn import ReleaseScope
from src.linger.orchestration.connection import _build_task
from src.linger.orchestration import turn_context
from tests.test_reflection import candidate, reflection_reply, result, review, route_clarification


class PassageReleaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.corpus = Librarian()
        self.record = self.corpus.fetch_by_id("pg11-v01b38ea4-ch05-ln0974-0975")
        self.neighbor = self.corpus.fetch_by_id("pg11-v01b38ea4-ch05-ln0977-0977")
        self.enclosing = self.corpus.fetch_by_id("pg11-v01b38ea4-ch05-ln0974-0977")
        assert self.record and self.neighbor and self.enclosing
        self.grant = PassageGrant(records=(self.record,), supporting_statement_ids=("reader-1",))
        self.route = RoutedPassages(
            **self.grant.scope.model_dump(), request_id="route-passages",
            title="Alice's Adventures in Wonderland", routing_confidence=0.99,
            boundary_confidence=0.99, selection_basis="resolved_book_identity",
        )
        self.reading_token = turn_context.set_confirmed_reading(None)
        self.routing_token = turn_context.set_routing_context()
        self.evidence_token = turn_context.set_turn_evidence(())
        turn_context.bind_passage_grant(self.grant)
        self.context = {
            "reading_context": None,
            "policy_constraints": {
                "spoiler_ceiling": None, "allow_retrieval": False,
                "allow_connection": False, "allow_memory_capture": False,
            },
        }

    def tearDown(self) -> None:
        turn_context.reset_turn_evidence(self.evidence_token)
        turn_context.reset_routing_context(self.routing_token)
        turn_context.reset_confirmed_reading(self.reading_token)

    def route_tool(self):
        return ToolReturnPart("librarian_route", self.route.model_dump(mode="json"))

    def search_tool(self, *, record=None, searched_scope=None):
        response = RetrievalResult(
            kind="result", request_id="search-passages", outcome="evidence_found",
            evidence_strength="sufficient", strength_reason="The exact wording is present.",
            searched_scope=searched_scope or self.grant.scope,
            evidence=(record or self.record,),
        )
        return ToolReturnPart("librarian_search", response.model_dump(mode="json"))

    def quoted_candidate(self, record=None):
        record = record or self.record
        return candidate(
            record.text, evidence_id=record.evidence_id, location=record.location,
            exact_quote=record.text,
        )

    async def release(self, muse, provenance, **kwargs):
        return await reflection_reply(
            "What does Alice actually say?", [], muse=muse, provenance=provenance,
            review_context=kwargs.pop("review_context", self.context), **kwargs,
        )

    async def test_exact_passage_releases_with_passage_only_provenance_context(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        muse.run.return_value = result(self.quoted_candidate(), self.route_tool(), self.search_tool())
        provenance.run.return_value = result(review("pass"))

        released = await self.release(muse, provenance)

        self.assertEqual("muse_candidate", released.release_source)
        self.assertEqual((self.record.evidence_id,), released.evidence_ids)
        context = json.loads(provenance.run.await_args.args[0])["context"]
        self.assertEqual(self.grant.scope.model_dump(mode="json"), context["passage_scope"])
        self.assertIsNone(context["reading_context"])
        self.assertIsNone(context["policy"]["spoiler_ceiling"])
        self.assertTrue(context["policy"]["allow_retrieval"])
        self.assertFalse(context["policy"]["allow_connection"])

    async def test_revision_keeps_the_draft_passage_permission(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        muse.run.side_effect = [
            result(self.quoted_candidate(), self.route_tool(), self.search_tool()),
            result(self.quoted_candidate()),
        ]
        provenance.run.side_effect = [result(review("revise")), result(review("pass"))]

        released = await self.release(muse, provenance)

        self.assertEqual("muse_candidate", released.release_source)
        self.assertEqual(1, released.revision_count)
        for call in provenance.run.await_args_list:
            context = json.loads(call.args[0])["context"]
            self.assertEqual(self.grant.scope.model_dump(mode="json"), context["passage_scope"])
            self.assertIsNone(context["reading_context"])

    async def test_revision_cannot_add_a_neighbor_to_the_passage_permission(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        calls = 0

        async def draft_then_invalid_revision(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return result(self.quoted_candidate(), self.route_tool(), self.search_tool())
            turn_context.add_turn_evidence((self.neighbor,))
            return result(self.quoted_candidate(self.neighbor), self.search_tool(record=self.neighbor))

        muse.run.side_effect = draft_then_invalid_revision
        provenance.run.side_effect = [result(review("revise")), result(review("pass"))]

        released = await self.release(muse, provenance)

        self.assertEqual("application_safe_decline", released.release_source)
        self.assertEqual("deterministic_validation", released.failure_stage)
        self.assertEqual(1, released.revision_count)

    async def test_neighbor_and_enclosing_window_rejected_even_if_registered(self) -> None:
        for record in (self.neighbor, self.enclosing):
            with self.subTest(record=record.evidence_id):
                token = turn_context.set_turn_evidence((record,))
                try:
                    muse, provenance = AsyncMock(), AsyncMock()
                    muse.run.return_value = result(
                        self.quoted_candidate(record), self.route_tool(), self.search_tool(record=record),
                    )
                    provenance.run.return_value = result(review("pass"))
                    released = await self.release(muse, provenance)
                    self.assertEqual("application_safe_decline", released.release_source)
                    self.assertEqual("deterministic_validation", released.failure_stage)
                finally:
                    turn_context.reset_turn_evidence(token)

    async def test_returned_wrong_revision_or_forged_text_rejected_against_canonical_ledger(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        for change in ({"book_version_id": "wrong-revision"}, {"text": "Alice reveals a later event."}):
            with self.subTest(change=change):
                muse, provenance = AsyncMock(), AsyncMock()
                muse.run.return_value = result(
                    self.quoted_candidate(), self.route_tool(),
                    self.search_tool(record=self.record.model_copy(update=change)),
                )
                provenance.run.return_value = result(review("pass"))
                released = await self.release(muse, provenance)
                self.assertEqual("application_safe_decline", released.release_source)
                self.assertEqual("deterministic_validation", released.failure_stage)

    async def test_chapter_search_scope_cannot_replace_a_passage_scope(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        muse.run.return_value = result(
            self.quoted_candidate(), self.route_tool(), self.search_tool(searched_scope=SearchedScope(
                work_id=self.record.work_id, book_version_id=self.record.book_version_id,
                max_chapter_inclusive=5,
            )),
        )
        provenance.run.return_value = result(review("pass"))

        released = await self.release(muse, provenance)

        self.assertEqual("application_safe_decline", released.release_source)
        self.assertEqual("deterministic_validation", released.failure_stage)

    async def test_previous_exact_evidence_reuses_no_new_passage_or_chapter_grant(self) -> None:
        turn_context.reset_routing_context(self.routing_token)
        self.routing_token = turn_context.set_routing_context()
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        muse.run.return_value = result(self.quoted_candidate())
        provenance.run.return_value = result(review("pass"))

        released = await self.release(
            muse, provenance, previously_released_evidence_ids=frozenset({self.record.evidence_id}),
        )

        self.assertEqual("muse_candidate", released.release_source)
        context = json.loads(provenance.run.await_args.args[0])["context"]
        self.assertIsNone(context["passage_scope"])
        self.assertIsNone(context["reading_context"])

    async def test_clarification_outranks_passage_route_in_both_orders(self) -> None:
        question = "What is the last scene you finished?"
        routes = (self.route_tool(), route_clarification(question))
        for ordered in (routes, tuple(reversed(routes))):
            with self.subTest(first=ordered[0].content["kind"]):
                muse, provenance = AsyncMock(), AsyncMock()
                muse.run.return_value = result("Muse's alternative question", *ordered)
                provenance.run.return_value = result(review("pass"))
                released = await self.release(muse, provenance)
                self.assertEqual("application_clarification", released.release_source)
                self.assertEqual(question, released.reply)
                self.assertEqual((), released.evidence_ids)
                context = json.loads(provenance.run.await_args.args[0])["context"]
                self.assertIsNone(context["passage_scope"])
                self.assertIsNone(context["reading_context"])

    async def test_explicit_lower_chapter_scope_outranks_passage_route(self) -> None:
        turn_context.add_turn_evidence((self.record,))
        muse, provenance = AsyncMock(), AsyncMock()
        muse.run.return_value = result(self.quoted_candidate(), self.route_tool(), self.search_tool())
        provenance.run.return_value = result(review("pass"))
        scope = ReleaseScope(work_id=self.record.work_id, book_version_id=self.record.book_version_id, chapter_max=3)
        context = {
            "reading_context": {"work_id": self.record.work_id, "chapter_max": 3, "boundary_source": "reader_confirmed"},
            "policy_constraints": {**self.context["policy_constraints"], "spoiler_ceiling": 3, "allow_retrieval": True},
        }

        released = await self.release(muse, provenance, release_scope=scope, review_context=context)

        self.assertEqual("application_safe_decline", released.release_source)
        self.assertEqual("deterministic_validation", released.failure_stage)
        reviewed = json.loads(provenance.run.await_args.args[0])["context"]
        self.assertIsNone(reviewed["passage_scope"])
        self.assertEqual(3, reviewed["reading_context"]["chapter_max"])

    def test_passage_grant_does_not_enable_serendipity_book_scope(self) -> None:
        with patch("src.linger.orchestration.connection.web_reach_permitted", return_value=False):
            task = _build_task(ConnectionBrief(cue="Alice's identity"), librarian=self.corpus)

        self.assertEqual((), task.scope.book_scopes)
        self.assertNotIn("book_corpus", task.scope.allowed_sources)
        self.assertIsNone(turn_context.confirmed_reading())
