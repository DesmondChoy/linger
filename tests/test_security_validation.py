"""Runtime checks for provider, storage, and transcript privacy boundaries."""

from __future__ import annotations

import json
import unittest

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from apps.backend.telemetry import run_agent_traced
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.muse.agent import build_muse_agent
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.sculptor.agent import build_sculptor_agent
from src.linger.agents.security import ProviderRequestPrivacyGuard
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.contracts.security_validation import (
    SecurityValidationBlocked,
    redact_storage_value,
)
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink


EMAIL = "alice.person@example.com"
CREDENTIAL = "sk-proj-1234567890123456789012345678901234567890"


def _capabilities(capability: object) -> list[object]:
    nested = getattr(capability, "capabilities", None)
    if nested is None:
        return [capability]
    return [item for child in nested for item in _capabilities(child)]


class ProviderRequestPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def test_every_role_agent_registers_the_provider_guard(self) -> None:
        agents = (
            build_muse_agent(TestModel()),
            build_librarian_agent(TestModel()),
            build_serendipity_agent(TestModel()),
            build_provenance_agent(TestModel()),
            build_sculptor_agent(TestModel()),
        )
        for agent in agents:
            with self.subTest(role=agent.name):
                self.assertTrue(
                    any(isinstance(cap, ProviderRequestPrivacyGuard)
                        for cap in _capabilities(agent.root_capability))
                )

    async def test_redacts_prompt_and_supplied_message_history_before_dispatch(self) -> None:
        dispatched: list[str] = []

        def respond(messages, _info):
            dispatched.append(json.dumps(messages, default=str))
            return ModelResponse(parts=[TextPart("ok")])

        agent = Agent(FunctionModel(respond), capabilities=[ProviderRequestPrivacyGuard()])
        await agent.run(
            f"Contact {EMAIL}",
            message_history=[ModelResponse(parts=[TextPart(f"Earlier {EMAIL}")])],
        )

        self.assertEqual(1, len(dispatched))
        self.assertNotIn(EMAIL, dispatched[0])
        self.assertIn("[EMAIL_", dispatched[0])

    async def test_blocks_credentials_before_calling_provider(self) -> None:
        calls = 0

        def respond(_messages, _info):
            nonlocal calls
            calls += 1
            return ModelResponse(parts=[TextPart("should not be called")])

        agent = Agent(FunctionModel(respond), capabilities=[ProviderRequestPrivacyGuard()])
        with self.assertRaises(SecurityValidationBlocked) as raised:
            await agent.run(f"Use this token: {CREDENTIAL}")

        self.assertEqual(0, calls)
        self.assertNotIn(CREDENTIAL, str(raised.exception))

    async def test_tool_follow_up_redacts_tool_result_before_next_dispatch(self) -> None:
        dispatched: list[str] = []

        def respond(messages, _info):
            dispatched.append(json.dumps(messages, default=str))
            if len(dispatched) == 1:
                return ModelResponse(parts=[ToolCallPart("lookup", {})])
            return ModelResponse(parts=[TextPart("done")])

        agent = Agent(FunctionModel(respond), capabilities=[ProviderRequestPrivacyGuard()])

        @agent.tool_plain
        def lookup() -> str:
            return f"Found contact {EMAIL}"

        await agent.run("Look it up")

        self.assertEqual(2, len(dispatched))
        self.assertNotIn(EMAIL, dispatched[1])
        self.assertIn("[EMAIL_", dispatched[1])

    async def test_output_repair_prompt_is_redacted_before_retry_dispatch(self) -> None:
        dispatched: list[str] = []

        def respond(messages, _info):
            dispatched.append(json.dumps(messages, default=str))
            return ModelResponse(parts=[TextPart("first" if len(dispatched) == 1 else "fixed")])

        agent = Agent(
            FunctionModel(respond),
            capabilities=[ProviderRequestPrivacyGuard()],
            retries=1,
        )

        @agent.output_validator
        def require_repair(_ctx, output: str) -> str:
            if output == "first":
                raise ModelRetry(f"Correct the contact address {EMAIL}")
            return output

        await agent.run("Repair this")

        self.assertEqual(2, len(dispatched))
        self.assertNotIn(EMAIL, dispatched[1])
        self.assertIn("[EMAIL_", dispatched[1])


class StorageAndTranscriptPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def test_storage_redacts_nested_text_and_blocks_credentials(self) -> None:
        stored = redact_storage_value({"note": [f"Contact {EMAIL}"]})
        self.assertNotIn(EMAIL, json.dumps(stored))
        self.assertIn("[EMAIL_", json.dumps(stored))
        with self.assertRaises(SecurityValidationBlocked) as raised:
            redact_storage_value({"note": CREDENTIAL})
        self.assertNotIn(CREDENTIAL, str(raised.exception))

    async def test_eval_transcript_redacts_prompt_history_and_generated_output(self) -> None:
        agent = Agent(
            FunctionModel(
                lambda _messages, _info: ModelResponse(parts=[TextPart(f"Contact {EMAIL}")])
            ),
            capabilities=[ProviderRequestPrivacyGuard()],
        )
        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            await run_agent_traced(
                agent,
                f"Contact {EMAIL}",
                span_name="test.security",
                role="Muse",
                stage="test",
                input_contract="TestInput.v1",
                output_contract="TestOutput.v1",
                prompt_template_id="test.security",
                prompt_digest="0" * 64,
                failure_code="test_security_failed",
                message_history=[],
            )

        exchange = recorder.exchanges[0]
        serialized = json.dumps(exchange.model_dump(mode="json"), default=str)
        self.assertNotIn(EMAIL, serialized)
        self.assertIn("[EMAIL_", serialized)


if __name__ == "__main__":
    unittest.main()
