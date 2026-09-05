"""Pin the boundary facts that `spoiler_boundary_clarification` grades.

Grading compares the ceiling Librarian inferred against event-derived Ground
truth, so that ceiling and its provenance must survive the trip out of
inference and into `TurnInspection`. Boundary inference runs mid-turn inside
the `librarian_route` tool, so these drive the real chat route and read what
actually reaches Inspect rather than constructing a `ContextResolution` by
hand — a hand-built one would pass while the production handoff was broken.

The no-leak contract is the load-bearing one: a ceiling is located by evidence
ID, chapter number, and location string, never by post-boundary story text.
`test_boundary_inference.py` covers inference itself; these cover the handoff.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import chat_turn, main, sessions
    from apps.backend.schemas import ChatRequest

    get_settings()

from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)
from tests.test_librarian_route_e2e import (
    BOOK_REQUEST_MESSAGE,
    _muse_routes_then_relays_clarification,
    _muse_routes_then_searches,
    _plain_reply_model,
    _provenance_pass,
    _sufficient_strength,
)

WORK_ID = "pg11"
VERSION_ID = "pg11-v01b38ea4"
CEILING = 5

# Stands in for story text past the ceiling. It must never reach Inspect.
PRIVATE_LATER_TEXT = "PRIVATE_LATER_CHAPTER_TEXT_MUST_NOT_ESCAPE"


async def _confident_ceiling_judge(_line, memories, evidence, _statements):
    """Authorize exactly `CEILING`, citing only support at or below it."""
    within = [record for record in evidence if record.chapter_number <= CEILING]
    return BoundaryInferenceDecision(
        outcome="candidate",
        work_id=WORK_ID,
        book_version_id=VERSION_ID,
        chapter_number=CEILING,
        confidence=0.93,
        authorization_basis="memory_supported",
        supporting_memory_ids=[memory.memory_id for memory in memories],
        supporting_evidence_ids=[record.evidence_id for record in within],
    )


async def _uncertain_judge(_line, _memories, _evidence, _statements):
    return BoundaryInferenceDecision(
        outcome="uncertain",
        confidence=0.4,
        reason_code="insufficient_context",
    )


class BoundaryObservabilityTests(unittest.IsolatedAsyncioTestCase):
    session_id = "boundary-observability-test"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("boundary-observability-account")
        # `authorization_basis="memory_supported"` needs a backing memory.
        self.service.set_capture_enabled(self.account, True)
        self.service.save_automatic(
            self.account,
            AutomaticMemoryCandidate(
                text="Alice and the Caterpillar made me think about identity.",
                source_event_id="event-boundary-observability",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        self._emotional_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self._emotional_patcher.start()
        self.addCleanup(self._emotional_patcher.stop)
        self.addCleanup(sessions.clear, self.session_id)

    async def _routed_turn(self, judge, *, muse_model=None):
        """Run one real routed turn through the production chat boundary."""
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)
        captured: list = []
        muse_model = muse_model or _muse_routes_then_searches(captured)
        with (
            patch(
                "src.linger.orchestration.boundary.judge_spoiler_boundary",
                side_effect=judge,
            ),
            # Without this the bounded search fails closed on
            # `evidence_judgement_unavailable` and never exercises the ceiling.
            patch(
                "src.linger.orchestration.grounding.judge_evidence_strength",
                side_effect=_sufficient_strength,
            ),
        ):
            with muse_chat_agent.override(model=FunctionModel(muse_model)):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    return await main.chat(request, self.service, self.account)

    def _route_outcome(self, response):
        """Return the `librarian_route` outcome Inspect exposes for this turn."""
        for call in response.inspection.librarian_grounding:
            outcome = call.get("response")
            if isinstance(outcome, dict) and outcome.get("kind") in {
                "routed",
                "clarification",
            }:
                return outcome
        return None

    async def test_inferred_ceiling_and_its_confidence_reach_inspection(self) -> None:
        """The graded ceiling must be readable from the turn's inspection."""
        response = await self._routed_turn(_confident_ceiling_judge)

        routed = self._route_outcome(response)
        self.assertIsNotNone(routed)
        self.assertEqual("routed", routed["kind"])
        self.assertEqual(WORK_ID, routed["work_id"])
        self.assertEqual(VERSION_ID, routed["book_version_id"])
        self.assertEqual(CEILING, routed["max_chapter_inclusive"])
        self.assertIsInstance(routed["boundary_confidence"], float)
        self.assertEqual("distinctive_cue", routed["selection_basis"])

    async def test_routed_ceiling_governs_the_evidence_actually_searched(self) -> None:
        """A ceiling nobody enforces is not observability, it is decoration."""
        response = await self._routed_turn(_confident_ceiling_judge)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        searched = [
            call
            for call in response.inspection.librarian_grounding
            if isinstance(call.get("response"), dict)
            and (call["response"].get("evidence") is not None)
        ]
        self.assertTrue(searched, "the routed turn performed no bounded search")
        for call in searched:
            for record in call["response"]["evidence"]:
                self.assertLessEqual(record["chapter_number"], CEILING)

    async def test_unresolved_boundary_asks_instead_of_granting_a_ceiling(self) -> None:
        """Uncertain inference must clarify, never quietly authorize a ceiling."""
        response = await self._routed_turn(
            _uncertain_judge,
            muse_model=_muse_routes_then_relays_clarification(),
        )

        routed = self._route_outcome(response)
        self.assertIsNotNone(routed)
        self.assertEqual("clarification", routed["kind"])
        self.assertNotIn("max_chapter_inclusive", routed)
        self.assertTrue(routed["question"])

    async def test_inspection_never_carries_post_boundary_story_text(self) -> None:
        """Locating a ceiling must not become a channel for later-chapter text.

        Boundary inference searches the complete work privately, so the judge
        legitimately sees chapters past the ceiling it goes on to authorize.
        For this query the real corpus happens to return only Chapter 5
        candidates, which would make the assertion vacuous — so a Chapter 8
        record carrying a sentinel is injected to create a genuine leak path.
        """
        saw_post_boundary = False

        async def leak_probe_judge(line, memories, evidence, statements):
            nonlocal saw_post_boundary
            later = EvidenceRecord(
                evidence_id=f"{VERSION_ID}-ch08-ln0800-0801",
                work_id=WORK_ID,
                book_version_id=VERSION_ID,
                chapter_id=f"{VERSION_ID}-ch08",
                chapter_number=8,
                location="Chapter 8, source lines 800-801",
                source_sha256="a" * 64,
                source_lines=(800, 801),
                text=PRIVATE_LATER_TEXT,
            )
            saw_post_boundary = True
            # The ceiling stays at CEILING: the later record is context the
            # judge reads, never support it may cite.
            return await _confident_ceiling_judge(
                line, memories, (*evidence, later), statements
            )

        response = await self._routed_turn(leak_probe_judge)

        self.assertTrue(saw_post_boundary, "the judge was never consulted")
        self.assertNotIn(PRIVATE_LATER_TEXT, response.inspection.model_dump_json())

    async def test_a_non_book_line_grants_no_boundary_at_all(self) -> None:
        """No boundary must be distinguishable from an inferred ceiling."""
        request = ChatRequest(
            session_id=self.session_id,
            message="My afternoon in the garden was calming.",
        )
        reply = "That sounds like a gentle way to spend the afternoon."

        with muse_chat_agent.override(model=FunctionModel(_plain_reply_model(reply))):
            with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                response = await main.chat(request, self.service, self.account)

        self.assertEqual([], response.inspection.librarian_grounding)
        self.assertIsNone(response.inspection.context_resolution["boundary_source"])
        self.assertIsNone(response.inspection.context_resolution["chapter_max"])


if __name__ == "__main__":
    unittest.main()
