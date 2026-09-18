"""End-to-end tests pinning the session-line and connection-grant mechanics Muse guidance relies on."""

import json
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
    from apps.backend import chat_turn, sessions
    from apps.backend.schemas import ChatRequest
    get_settings()

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from provenance_fixtures import review_with_audits
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)


ASSEMBLY_LINE = "The farewell assembly is next Tuesday. Thursday is only the band's run-through in the hall."
ASSEMBLY_QUOTE = "The farewell assembly is next Tuesday."
DEADLINE_QUESTION = "I'd like the final draft finished two days before the assembly. Which day does that make my deadline?"
BRAILLE_QUESTION = (
    "Random thing I wondered about while photocopying parts today: how do blind "
    "musicians read music? Is there a braille form of notation, and how would a "
    "player manage it when both hands are busy on the instrument?"
)
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def _json_prompts(messages) -> list[dict]:
    return [
        json.loads(part.content)
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(getattr(part, "content", None), str)
        and part.content.lstrip().startswith("{")
    ]


def _candidate(info: AgentInfo, reply: str, evidence_uses: list[dict]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "reply": reply,
        "evidence_uses": evidence_uses,
        "memory": NO_MEMORY,
    })])


def _provenance_review(payload: dict, info: AgentInfo, decision: str, **fields) -> ModelResponse:
    coverage = [
        {"span_index": span["span_index"],
         "classification": "source_dependent" if decision == "revise" else "reader_reflection"}
        for span in payload["uncovered_response_spans"]
    ]
    review = review_with_audits(payload, {
        "findings": [],
        "response_decision": decision,
        "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
        "coverage_audit": coverage,
        **fields,
    })
    return ModelResponse(parts=[ToolCallPart(
        info.output_tools[0].name, review.model_dump(mode="json"),
    )])


class ChatSessionLineTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-session-lines-e2e"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("chat-session-lines-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_carried_forward_reader_fact_repairs_through_session_line_declaration(self) -> None:
        provenance_inputs = []

        def muse(messages, info):
            envelope = _json_prompts(messages)[-1]
            if envelope["mode"] == "revision":
                reply = "You said the assembly is next Tuesday, so two days before is the Sunday before it."
                return _candidate(info, reply, [{
                    "source_kind": "session_line",
                    "quote": ASSEMBLY_QUOTE,
                    "supported_claims": [reply],
                }])
            if envelope["muse_turn"]["user_message"] == ASSEMBLY_LINE:
                reply = "It sounds like the week has a clear shape now."
                return _candidate(info, reply, [{
                    "source_kind": "session_line",
                    "quote": ASSEMBLY_QUOTE,
                    "supported_claims": [reply],
                }])
            return _candidate(
                info,
                "Two days before next Tuesday (22 September 2026) is Sunday, 20 September 2026.",
                [],
            )

        def provenance(messages, info):
            payload = next(
                prompt for prompt in _json_prompts(messages)
                if "canonical_connection_evidence" in prompt
            )
            provenance_inputs.append(payload)
            if payload["previous_response_review"] is not None:
                return _provenance_review(payload, info, "pass", finding_resolutions=[{
                    "finding_index": 0,
                    "status": "resolved",
                    "explanation": "The day is now attributed to the reader and declared as a session line.",
                }])
            if payload["current_line"]["text"] == DEADLINE_QUESTION:
                return _provenance_review(payload, info, "revise", findings=[{
                    "code": "misattribution",
                    "applies_to": "response",
                    "location": {
                        "kind": "text_span", "source_field": "candidate.response", "path": "",
                        "quote": payload["candidate"]["response"],
                    },
                    "explanation": "The reply states the assembly day as fact without attributing it to the reader.",
                }])
            return _provenance_review(payload, info, "pass")

        with muse_chat_agent.override(model=FunctionModel(muse)):
            with provenance_agent.override(model=FunctionModel(provenance)):
                first = await chat_turn.run_chat_turn(
                    ChatRequest(session_id=self.session_id, message=ASSEMBLY_LINE),
                    self.service, self.account,
                )
                second = await chat_turn.run_chat_turn(
                    ChatRequest(session_id=self.session_id, message=DEADLINE_QUESTION),
                    self.service, self.account,
                )

        self.assertEqual("muse_candidate", first.inspection.release.release_source)
        self.assertEqual(("pass",), first.inspection.release.provenance_verdicts)
        self.assertEqual("muse_candidate", second.inspection.release.release_source)
        self.assertEqual(("revise", "pass"), second.inspection.release.provenance_verdicts)
        self.assertEqual(3, len(provenance_inputs))
        self.assertEqual([ASSEMBLY_QUOTE], provenance_inputs[0]["canonical_session_lines"])
        self.assertEqual([], provenance_inputs[1]["canonical_session_lines"])
        self.assertEqual([ASSEMBLY_QUOTE], provenance_inputs[2]["canonical_session_lines"])
        self.assertIn("You said the assembly is next Tuesday", second.reply)

    async def test_world_fact_question_releases_without_using_the_connection_grant(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        self.service.save_automatic(self.account, AutomaticMemoryCandidate(
            text="Reading about Helen Keller made me think about how I learn by touch.",
            source_event_id="fixture-keller",
            review_allows_capture=True,
            contains_sensitive_content=False,
        ))
        self.service.set_capture_enabled(self.account, False)
        provenance_inputs = []
        muse_calls = 0

        def muse(messages, info):
            nonlocal muse_calls
            muse_calls += 1
            return _candidate(
                info,
                "I can't cite a source for that here, so I won't state how braille music "
                "notation works. What drew you to the question while photocopying parts?",
                [],
            )

        def serendipity(messages, info):
            self.fail("serendipity_explore must not run for a general-knowledge question")

        def provenance(messages, info):
            payload = next(
                prompt for prompt in _json_prompts(messages)
                if "canonical_connection_evidence" in prompt
            )
            provenance_inputs.append(payload)
            return _provenance_review(payload, info, "pass")

        with muse_chat_agent.override(model=FunctionModel(muse)):
            with serendipity_agent.override(model=FunctionModel(serendipity)):
                with provenance_agent.override(model=FunctionModel(provenance)):
                    response = await chat_turn.run_chat_turn(
                        ChatRequest(session_id=self.session_id, message=BRAILLE_QUESTION),
                        self.service, self.account,
                    )

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(("pass",), response.inspection.release.provenance_verdicts)
        self.assertEqual(1, muse_calls)
        self.assertEqual(1, len(provenance_inputs))
        payload = provenance_inputs[0]
        self.assertTrue(payload["context"]["policy"]["allow_connection"])
        self.assertEqual([], payload["canonical_connection_evidence"])
        self.assertEqual([], payload["untrusted_tool_outcomes"])
        self.assertIn("I can't cite a source for that here", response.reply)


if __name__ == "__main__":
    unittest.main()
