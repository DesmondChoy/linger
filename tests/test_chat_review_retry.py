"""End-to-end test pinning that a mismatched Provenance quote is retried, not declined."""

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

from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.services.memory import AccountContext, MemoryPolicyService

BRAILLE_QUESTION = (
    "Random thing I wondered about while photocopying parts today: how do blind "
    "musicians read music? Is there a braille form of notation, and how would a "
    "player manage it when both hands are busy on the instrument?"
)
DRAFT_REPLY = (
    "Short answer: yes, there is a braille form of notation, and blind musicians "
    "use a mix of approaches: reading by touch. It was standardised in the 1920s."
)
FIRST_SENTENCE = DRAFT_REPLY[: DRAFT_REPLY.index("touch.") + len("touch.")]
MISMATCHED_QUOTE = FIRST_SENTENCE[:-1] + ":"
HEDGED_REPLY = (
    "I can't cite a source for that here, so I won't state how braille music "
    "notation works. What drew you to the question while photocopying parts?"
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


def _retry_prompts(messages) -> list[RetryPromptPart]:
    return [
        part
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(part, RetryPromptPart)
    ]


def _candidate(info: AgentInfo, reply: str) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "reply": reply,
        "evidence_uses": [],
        "memory": NO_MEMORY,
    })])


def _provenance_review(info: AgentInfo, decision: str, **fields) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "findings": [],
        "response_decision": decision,
        "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
        **fields,
    })])


def _uncited_finding(quote: str) -> dict:
    return {
        "code": "uncited_web_claim",
        "applies_to": "response",
        "location": {
            "kind": "text_span",
            "source_field": "candidate.response",
            "path": "",
            "quote": quote,
        },
        "explanation": "The reply states a public fact without citing a source.",
    }


class ChatReviewRetryTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-review-retry-e2e"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("chat-review-retry-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_mismatched_finding_quote_is_retried_then_revised(self) -> None:
        provenance_calls = 0
        retry_contents: list[str] = []

        def muse(messages, info):
            envelope = _json_prompts(messages)[-1]
            if envelope["mode"] == "revision":
                return _candidate(info, HEDGED_REPLY)
            return _candidate(info, DRAFT_REPLY)

        def provenance(messages, info):
            nonlocal provenance_calls
            provenance_calls += 1
            payload = next(
                prompt for prompt in _json_prompts(messages)
                if "canonical_connection_evidence" in prompt
            )
            if payload["previous_response_review"] is not None:
                return _provenance_review(info, "pass", finding_resolutions=[{
                    "finding_index": 0,
                    "status": "resolved",
                    "explanation": "The reply no longer asserts the public fact.",
                }])
            retries = _retry_prompts(messages)
            if retries:
                retry_contents.extend(str(part.content) for part in retries)
                return _provenance_review(
                    info, "revise", findings=[_uncited_finding(FIRST_SENTENCE)],
                )
            return _provenance_review(
                info, "revise", findings=[_uncited_finding(MISMATCHED_QUOTE)],
            )

        with muse_chat_agent.override(model=FunctionModel(muse)):
            with provenance_agent.override(model=FunctionModel(provenance)):
                response = await chat_turn.run_chat_turn(
                    ChatRequest(session_id=self.session_id, message=BRAILLE_QUESTION),
                    self.service, self.account,
                )

        release = response.inspection.release
        self.assertEqual("muse_candidate", release.release_source)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual(3, provenance_calls)
        self.assertEqual(1, len(retry_contents))
        self.assertIn(MISMATCHED_QUOTE, retry_contents[0])
        self.assertIn("I can't cite a source for that here", response.reply)

    async def test_exhausted_quote_retries_end_as_a_model_safe_decline(self) -> None:
        provenance_calls = 0

        def muse(messages, info):
            return _candidate(info, DRAFT_REPLY)

        def provenance(messages, info):
            nonlocal provenance_calls
            provenance_calls += 1
            return _provenance_review(
                info, "revise", findings=[_uncited_finding(MISMATCHED_QUOTE)],
            )

        with muse_chat_agent.override(model=FunctionModel(muse)):
            with provenance_agent.override(model=FunctionModel(provenance)):
                response = await chat_turn.run_chat_turn(
                    ChatRequest(session_id=self.session_id, message=BRAILLE_QUESTION),
                    self.service, self.account,
                )

        release = response.inspection.release
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual("model", release.failure_type)
        self.assertTrue(release.failure_retryable)
        self.assertEqual(3, provenance_calls)


if __name__ == "__main__":
    unittest.main()
