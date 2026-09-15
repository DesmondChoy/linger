"""Failed synthetic runs preserve diagnostic messages without provider calls."""

import asyncio
import json
import unittest

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from apps.backend.telemetry import run_agent_traced
from evals.synthetic_journals.transcript import AgentExchange, SceneTranscriptRecorder
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink


async def traced(agent, prompt, *, role="Muse", **kwargs):
    return await run_agent_traced(
        agent,
        prompt,
        span_name="test.failed-transcript",
        role=role,
        stage="test",
        input_contract="TestInput.v1",
        output_contract="TestOutput.v1",
        prompt_template_id="test.failed-transcript",
        prompt_digest="0" * 64,
        failure_code="test_agent_failed",
        **kwargs,
    )


def invalid_answer(_messages, _info):
    return ModelResponse(parts=[
        ThinkingPart("synthetic hidden reasoning"),
        ToolCallPart("final_result", {"response": "not an integer"}),
    ])


class FailedEvaluationTranscriptTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_output_retains_attempts_and_repair_messages(self):
        agent = Agent(FunctionModel(invalid_answer), output_type=int, retries=1)
        recorder = SceneTranscriptRecorder()
        history = [
            ModelRequest(parts=[UserPromptPart("earlier synthetic question")]),
            ModelResponse(parts=[ToolCallPart("earlier_lookup", {}, tool_call_id="old-call")]),
            ModelRequest(parts=[ToolReturnPart("earlier_lookup", "earlier evidence", tool_call_id="old-call")]),
            ModelResponse(parts=[TextPart("earlier synthetic answer")]),
        ]

        with bind_evaluation_transcript_sink(recorder):
            with self.assertRaises(UnexpectedModelBehavior):
                await traced(agent, "current synthetic question", message_history=history)

        exchange = recorder.exchanges[0]
        serialized = json.dumps(exchange.model_messages)
        self.assertIn("not an integer", serialized)
        self.assertIn("retry-prompt", serialized)
        self.assertIn("current synthetic question", serialized)
        self.assertIn("earlier synthetic question", serialized)
        self.assertIn("earlier_lookup", serialized)
        self.assertEqual((), exchange.tool_exchanges)
        self.assertNotIn("synthetic hidden reasoning", serialized)
        self.assertTrue(exchange.model_messages_include_history)
        self.assertEqual("model_response_error", exchange.failure_category)
        self.assertEqual("failure", exchange.status)
        self.assertEqual("test_agent_failed", exchange.failure_code)
        self.assertIsNone(exchange.output)
        self.assertIsNone(exchange.usage)

    async def test_nested_runs_keep_separate_messages_and_completed_tool_return(self):
        child = Agent(FunctionModel(
            lambda _messages, _info: ModelResponse(parts=[TextPart("child result")])
        ))
        calls = 0

        def parent_response(messages, info):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(parts=[ToolCallPart("lookup", {})])
            return invalid_answer(messages, info)

        parent = Agent(FunctionModel(parent_response), output_type=int, retries=1)

        @parent.tool_plain
        async def lookup() -> str:
            return (await traced(child, "child synthetic prompt", role="Librarian")).output

        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            with self.assertRaises(UnexpectedModelBehavior):
                await traced(parent, "parent synthetic prompt")

        outer, inner = recorder.exchanges
        self.assertEqual(("Muse", "Librarian"), (outer.role, inner.role))
        self.assertEqual(("failure", "success"), (outer.status, inner.status))
        self.assertIn("parent synthetic prompt", json.dumps(outer.model_messages))
        self.assertNotIn("child synthetic prompt", json.dumps(outer.model_messages))
        self.assertIn("child synthetic prompt", json.dumps(inner.model_messages))
        self.assertNotIn("parent synthetic prompt", json.dumps(inner.model_messages))
        self.assertEqual("lookup", outer.tool_exchanges[0].tool_name)
        self.assertEqual("child result", outer.tool_exchanges[0].result)
        self.assertFalse(inner.model_messages_include_history)
        self.assertIsNone(inner.failure_category)

    async def test_failed_nested_run_retains_both_attempted_conversations(self):
        child = Agent(FunctionModel(invalid_answer), output_type=int, retries=1)
        parent = Agent(FunctionModel(
            lambda _messages, _info: ModelResponse(parts=[ToolCallPart("lookup", {})])
        ))

        @parent.tool_plain
        async def lookup() -> int:
            return (await traced(child, "failed child prompt", role="Librarian")).output

        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            with self.assertRaises(UnexpectedModelBehavior):
                await traced(parent, "failed parent prompt")

        outer, inner = recorder.exchanges
        self.assertEqual(("failure", "failure"), (outer.status, inner.status))
        self.assertIn("lookup", json.dumps(outer.model_messages))
        self.assertNotIn("failed child prompt", json.dumps(outer.model_messages))
        self.assertIn("retry-prompt", json.dumps(inner.model_messages))
        self.assertNotIn("failed parent prompt", json.dumps(inner.model_messages))
        self.assertIsNone(outer.tool_exchanges[0].result)

    async def test_failure_category_never_copies_exception_details(self):
        cases = (
            (ModelHTTPError(503, "private model name", "private provider response"), "provider_error"),
            (RuntimeError("private application failure"), "unknown_error"),
            (asyncio.CancelledError("private cancellation reason"), "cancelled"),
        )
        for error, category in cases:
            with self.subTest(category=category):
                def fail(_messages, _info):
                    raise error

                agent = Agent(FunctionModel(fail))
                recorder = SceneTranscriptRecorder()
                with bind_evaluation_transcript_sink(recorder):
                    with self.assertRaises(type(error)):
                        await traced(agent, "synthetic question")

                exchange = recorder.exchanges[0]
                self.assertEqual(category, exchange.failure_category)
                self.assertIn("synthetic question", json.dumps(exchange.model_messages))
                self.assertNotIn("private", exchange.model_dump_json())

    async def test_usage_limit_retains_output_that_preceded_the_limit(self):
        from pydantic_ai.exceptions import UsageLimitExceeded

        agent = Agent(FunctionModel(invalid_answer), output_type=int, retries=2)
        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            with self.assertRaises(UsageLimitExceeded):
                await traced(agent, "synthetic question", usage_limits=UsageLimits(request_limit=1))

        exchange = recorder.exchanges[0]
        self.assertEqual("usage_limit", exchange.failure_category)
        self.assertIn("not an integer", json.dumps(exchange.model_messages))

    async def test_saved_exchange_without_diagnostic_fields_remains_readable(self):
        agent = Agent(FunctionModel(
            lambda _messages, _info: ModelResponse(parts=[TextPart("ok")])
        ))
        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            await traced(agent, "synthetic question")

        saved = recorder.exchanges[0].model_dump()
        saved.pop("failure_category", None)
        saved.pop("model_messages_include_history", None)
        restored = AgentExchange.model_validate(saved)
        self.assertIsNone(restored.failure_category)
        self.assertFalse(restored.model_messages_include_history)
