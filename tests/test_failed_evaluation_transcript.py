"""Failed synthetic runs preserve diagnostic messages without provider calls."""

import asyncio
import json
import unittest

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
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
        generic_with_status = RuntimeError("private application failure")
        generic_with_status.status_code = 503
        cases = (
            (ModelHTTPError(503, "private model name", "private provider response"), "provider_error", 503),
            (ModelHTTPError(399, "private model name", "private provider response"), "provider_error", None),
            (ModelHTTPError(600, "private model name", "private provider response"), "provider_error", None),
            (ModelAPIError("private model name", "private API failure"), "provider_error", None),
            (generic_with_status, "unknown_error", None),
            (asyncio.CancelledError("private cancellation reason"), "cancelled", None),
        )
        for error, category, status_code in cases:
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
                self.assertEqual(status_code, exchange.provider_status_code)
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

    async def test_provider_kind_uses_only_known_outer_and_immediate_cause_types(self):
        request = httpx.Request("POST", "https://private.invalid/private")

        def wrapped(cause):
            error = ModelAPIError("private model", "private exception")
            error.__cause__ = cause
            return error

        context_only = ModelAPIError("private model", "private exception")
        context_only.__context__ = APITimeoutError(request)
        generic_outer = RuntimeError("private exception")
        generic_outer.__cause__ = APITimeoutError(request)
        hidden_timeout = RuntimeError("private exception")
        hidden_timeout.__cause__ = APITimeoutError(request)
        cases = (
            (ModelHTTPError(503, "private model", "private body"), "http"),
            (wrapped(APITimeoutError(request)), "timeout"),
            (wrapped(APIConnectionError(request=request)), "connection"),
            (wrapped(APIStatusError("private", response=httpx.Response(302, request=request), body="private")), "http"),
            (wrapped(hidden_timeout), "other"),
            (context_only, "other"),
            (generic_outer, None),
        )
        for error, expected in cases:
            with self.subTest(kind=expected):
                def fail(_messages, _info):
                    raise error

                recorder = SceneTranscriptRecorder()
                with bind_evaluation_transcript_sink(recorder):
                    with self.assertRaises(type(error)):
                        await traced(Agent(FunctionModel(fail)), "synthetic question")
                exchange = recorder.exchanges[0]
                self.assertEqual(expected, exchange.provider_error_kind)
                self.assertNotIn("private", exchange.model_dump_json())

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
        saved.pop("provider_status_code", None)
        saved.pop("provider_error_kind", None)
        restored = AgentExchange.model_validate(saved)
        self.assertIsNone(restored.failure_category)
        self.assertIsNone(restored.provider_status_code)
        self.assertIsNone(restored.provider_error_kind)
        self.assertFalse(restored.model_messages_include_history)

        for invalid_status in (399, 600, "503", True, 503.0):
            with self.subTest(status_code=invalid_status):
                with self.assertRaises(ValidationError):
                    AgentExchange.model_validate({**saved, "provider_status_code": invalid_status})
        with self.assertRaises(ValidationError):
            AgentExchange.model_validate({**saved, "provider_error_kind": "private arbitrary class"})
