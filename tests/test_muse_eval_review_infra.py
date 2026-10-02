"""Review-pack loading, fixed exposure, additive gates, and run instrumentation for Muse evals.

Stub models only; no provider calls.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.muse import baseline_run
from evals.muse.harness import (
    FixedExposure,
    MuseEvalCase,
    MuseReviewCase,
    ToolTranscript,
    grade_additive,
    grade_muse_response,
    load_muse_eval_cases,
    load_review_cases,
)

NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "transient_or_low_signal"}


def _main_case(behavior: str) -> MuseEvalCase:
    return next(case for case in load_muse_eval_cases() if case.primary_behavior == behavior)


def _review_case(behavior: str, case_id: str, **updates: object) -> MuseReviewCase:
    raw = _main_case(behavior).model_dump(mode="json", exclude_none=True)
    raw.pop("fixed_exposure", None)
    raw.update({"case_id": case_id, **updates})
    return MuseReviewCase.model_validate(raw)


def _final(reply: str, *, evidence_uses: list | None = None) -> ToolCallPart:
    return ToolCallPart(
        "final_result",
        {"reply": reply, "evidence_uses": evidence_uses or [], "memory": NO_MEMORY},
    )


class ReviewPackLoaderTests(unittest.TestCase):
    def test_main_pack_is_unchanged(self) -> None:
        self.assertEqual(19, len(load_muse_eval_cases()))
        self.assertEqual(load_muse_eval_cases(), baseline_run.load_pack("main"))

    def test_review_cases_may_share_a_behavior(self) -> None:
        first = _review_case("withhold_instructions", "muse-review-d-withhold-a-v1")
        second = _review_case("withhold_instructions", "muse-review-d-withhold-b-v2")
        with tempfile.TemporaryDirectory() as directory:
            for case in (first, second):
                Path(directory, f"{case.case_id}.json").write_text(
                    case.model_dump_json(), encoding="utf-8"
                )
            loaded = load_review_cases(Path(directory))
        self.assertEqual([first.case_id, second.case_id], [case.case_id for case in loaded])

    def test_review_loader_rejects_duplicates_and_main_style_ids(self) -> None:
        case = _review_case("withhold_instructions", "muse-review-d-withhold-a-v1")
        with tempfile.TemporaryDirectory() as directory:
            for name in ("a.json", "b.json"):
                Path(directory, name).write_text(case.model_dump_json(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_review_cases(Path(directory))
        with self.assertRaises(ValidationError):
            _review_case("withhold_instructions", "muse-withhold-instructions-v1")

    def test_main_case_model_keeps_its_v1_id_rule(self) -> None:
        raw = _main_case("withhold_instructions").model_dump(mode="json")
        raw["case_id"] = "muse-withhold-instructions-v2"
        with self.assertRaises(ValidationError):
            MuseEvalCase.model_validate(raw)

    def test_review_behaviour_labels_are_review_only(self) -> None:
        raw = _main_case("grounded_answer_within_boundary").model_dump(mode="json")
        raw["primary_behavior"] = "handle_weak_evidence"
        with self.assertRaises(ValidationError):
            MuseEvalCase.model_validate(raw)
        raw["case_id"] = "muse-review-b-weak-v1"
        self.assertEqual(
            "handle_weak_evidence", MuseReviewCase.model_validate(raw).primary_behavior
        )

    def test_unknown_pack_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown pack"):
            baseline_run.load_pack("everything")


class CaseContractAdditionTests(unittest.TestCase):
    def test_pinned_intent_requires_serendipity(self) -> None:
        with self.assertRaisesRegex(ValidationError, "pinned intent"):
            FixedExposure(tools=("librarian_search",), pinned_intent="recall_memory")
        FixedExposure(tools=("serendipity_explore",), pinned_intent="recall_memory")

    def test_gathered_bundle_needs_records_and_owns_unfound_sources(self) -> None:
        with self.assertRaisesRegex(ValidationError, "gathered bundle"):
            ToolTranscript(serendipity_outcome="gathered")
        with self.assertRaisesRegex(ValidationError, "unfound sources"):
            ToolTranscript(memory_records=("note",), serendipity_outcome="recall",
                           unfound_sources=("A book",))
        ToolTranscript(memory_records=("note",), serendipity_outcome="gathered",
                       unfound_sources=("A book",))

    def test_proposal_may_compare_memory_records(self) -> None:
        ToolTranscript(
            librarian_evidence=("passage",), memory_records=("note",),
            serendipity_outcome="proposal", connection_claim="claim",
            connection_follow_up="follow up",
        )

    def test_search_and_route_outcome_payloads(self) -> None:
        with self.assertRaisesRegex(ValidationError, "weak search"):
            ToolTranscript(search_outcome="weak")
        with self.assertRaisesRegex(ValidationError, "passages route"):
            ToolTranscript(route_outcome="passages")
        ToolTranscript(search_outcome="failure")

    def test_prior_evidence_supports_quotations(self) -> None:
        case = _review_case(
            "grounded_answer_within_boundary", "muse-review-b-prior-v1",
            input={
                **_main_case("grounded_answer_within_boundary").model_dump(mode="json")["input"],
                "prior_evidence": ["she was now only ten inches high, and her face brightened"],
            },
        )
        grade = grade_muse_response(
            case, 'Earlier we saw "she was now only ten inches high".'
        )
        self.assertTrue(grade.hard_pass, grade.failures)


class AdditiveGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = _main_case("relay_tentative_connection")

    def test_clean_reply_passes_every_additive_gate(self) -> None:
        grade = grade_additive(
            self.case, "It may loosely echo Alice at the little door. What would help?"
        )
        self.assertEqual(((), (), ()), (grade.leak_failures, grade.tool_failures, grade.reply_failures))

    def test_internal_names_and_repair_mechanics_are_flagged(self) -> None:
        reply = (
            "Serendipity found a link via serendipity_explore: she is “the right size”"
            " — the quote has no period inside the quotation marks."
        )
        failures = grade_additive(self.case, reply).leak_failures
        self.assertIn("agent_name:Serendipity", failures)
        self.assertIn("internal_identifier:serendipity_explore", failures)
        self.assertIn("repair_mechanics:punctuation_in_quote", failures)
        self.assertIn("repair_mechanics:quotation_marks", failures)

    def test_words_the_reader_or_a_source_supplied_are_exempt(self) -> None:
        raw = self.case.model_dump(mode="json")
        raw["input"]["reader_message"] = (
            "My librarian friend, the Librarian of our club, said quotation marks matter. Thoughts?"
        )
        case = MuseEvalCase.model_validate(raw)
        reply = "The Librarian of your club has a point about quotation marks."
        self.assertEqual((), grade_additive(case, reply).leak_failures)

    def test_hard_gate_is_unchanged_by_additive_failures(self) -> None:
        reply = "Serendipity says it may loosely echo Alice. What do you think?"
        self.assertTrue(grade_muse_response(self.case, reply).hard_pass)
        self.assertTrue(grade_additive(self.case, reply).leak_failures)

    def test_tool_and_reply_expectations(self) -> None:
        raw = self.case.model_dump(mode="json")
        raw["expected"].update({
            "required_tools": ["serendipity_explore"],
            "forbidden_tools": ["librarian_search"],
            "allowed_intents": ["find_connection"],
            "max_serendipity_calls": 1,
            "must_cite_urls": ["https://example.com/a"],
            "required_terms": ["little door"],
        })
        case = MuseEvalCase.model_validate(raw)
        grade = grade_additive(
            case, "Nothing here.",
            tool_calls=["librarian_search", "serendipity_explore", "serendipity_explore"],
            serendipity_intents=["gather_sources", "find_connection"],
        )
        self.assertEqual(
            ("forbidden_tool:librarian_search", "disallowed_intent:gather_sources",
             "too_many_serendipity_calls"),
            grade.tool_failures,
        )
        self.assertEqual(
            ("missing_url:https://example.com/a", "missing_term:little door"),
            grade.reply_failures,
        )


class RunnerInstrumentationTests(unittest.TestCase):
    """Drive the real `current` runner path with a scripted model."""

    def _run(self, case: MuseEvalCase, respond) -> dict:
        calls: list[list[ModelMessage]] = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            calls.append(messages)
            return respond(len(calls), messages, info)

        return asyncio.run(baseline_run._one(
            case, "current", FunctionModel(model), None, asyncio.Semaphore(1),
        )), calls

    def _fixed_case(self, **exposure: object) -> MuseReviewCase:
        return _review_case(
            "relay_tentative_connection", "muse-review-a-relay-fixed-v1",
            fixed_exposure=exposure,
        )

    def test_fixed_exposure_skips_triage_and_records_the_run(self) -> None:
        case = self._fixed_case(tools=["serendipity_explore"], pinned_intent="find_connection")
        offered: list[set[str]] = []

        def respond(call: int, messages, info: AgentInfo) -> ModelResponse:
            offered.append({tool.name for tool in info.function_tools})
            if call == 1:
                return ModelResponse(parts=[ToolCallPart(
                    "serendipity_explore", {"intent": "find_connection"})])
            if call == 2:
                return ModelResponse(parts=[TextPart("Plain text instead of the typed output.")])
            return ModelResponse(parts=[_final("It may loosely echo Alice. What would help?")])

        outcome, calls = self._run(case, respond)
        self.assertNotIn("error", outcome)
        # No triage request: the first model call is already the draft with its tools.
        self.assertEqual({"serendipity_explore"}, offered[0])
        self.assertTrue(outcome["fixed_exposure"])
        self.assertIsNone(outcome["triage"])
        self.assertEqual(["serendipity_explore"], outcome["exposed_tools"])
        self.assertEqual("find_connection", outcome["pinned_intent"])
        self.assertEqual(["connections"], outcome["reflection_modules"])
        self.assertEqual(NO_MEMORY, outcome["memory"])
        self.assertEqual([], outcome["evidence_uses"])
        self.assertTrue(outcome["hard_pass"])
        self.assertTrue(outcome["leak_pass"])
        self.assertEqual(
            ["initial", "tool_return", "retry"],
            [request["cause"] for request in outcome["requests"]],
        )
        self.assertGreater(outcome["instructions_tokens"], 1000)
        self.assertEqual(3, len(calls))
        self.assertEqual({}, outcome["sdk_retries"])

    def test_retry_categories_name_the_check_that_fired(self) -> None:
        case = self._fixed_case(tools=["serendipity_explore"], pinned_intent="find_connection")
        bad_use = {
            "source_kind": "book_corpus", "evidence_id": "not-an-id",
            "source_location": "Chapter I", "supported_claims": ["It may echo Alice."],
        }

        def respond(call: int, messages, info) -> ModelResponse:
            if call == 1:
                return ModelResponse(parts=[ToolCallPart(
                    "serendipity_explore", {"intent": "recall_memory"})])
            if call == 2:
                return ModelResponse(parts=[_final("It may echo Alice.", evidence_uses=[bad_use])])
            return ModelResponse(parts=[_final("It may loosely echo Alice. What would help?")])

        outcome, _ = self._run(case, respond)
        self.assertNotIn("error", outcome)
        self.assertEqual(
            ["tool:serendipity_explore", "output_validation"],
            [entry["category"] for entry in outcome["retry_categories"]],
        )
        self.assertIn("evidence_id", outcome["retry_categories"][1]["fields"])

    def test_exhausted_output_retries_are_a_separate_error_kind(self) -> None:
        case = self._fixed_case(tools=[])

        def respond(call: int, messages, info) -> ModelResponse:
            return ModelResponse(parts=[TextPart("plain text, never the typed output")])

        outcome, _ = self._run(case, respond)
        self.assertEqual("UnexpectedModelBehavior", outcome["error"])
        self.assertEqual("output_retries_exhausted", outcome["error_kind"])
        self.assertEqual([], outcome["reflection_modules"])
        self.assertTrue(outcome["retry_categories"])
        self.assertEqual(
            {"text_instead_of_output"},
            {entry["category"] for entry in outcome["retry_categories"]},
        )
        summary = baseline_run._review_summary([outcome], [])
        self.assertEqual(1, summary["output_retry_exhausted"])
        self.assertEqual({"output_retries_exhausted": 1}, summary["error_kinds"])

    def test_rate_limited_runs_are_retried_only_when_asked(self) -> None:
        from pydantic_ai.exceptions import ModelHTTPError

        attempts = []

        async def run_current(case, model):
            attempts.append(1)
            if len(attempts) == 1:
                raise ModelHTTPError(429, "gpt-6-luna")
            return {
                "reply": "A reply.", "tool_calls": [], "usage": type(
                    "U", (), {"input_tokens": 1, "output_tokens": 1})(),
            }

        case = _main_case("reflect_without_book_context")
        original, backoff = baseline_run._run_current, baseline_run.RATE_LIMIT_BACKOFF_SECONDS
        baseline_run._run_current, baseline_run.RATE_LIMIT_BACKOFF_SECONDS = run_current, 0
        try:
            without = asyncio.run(baseline_run._one(case, "current", None, None, asyncio.Semaphore(1)))
            attempts.clear()
            retried = asyncio.run(
                baseline_run._one(case, "current", None, None, asyncio.Semaphore(1), retry_429=2)
            )
        finally:
            baseline_run._run_current, baseline_run.RATE_LIMIT_BACKOFF_SECONDS = original, backoff
        self.assertEqual("rate_limit", without["error_kind"])
        self.assertEqual("ModelHTTPError429", without["error"])
        self.assertNotIn("rate_limited_attempts", without)
        self.assertNotIn("error", retried)
        self.assertEqual(1, retried["rate_limited_attempts"])

    def test_stub_tools_return_review_outcomes(self) -> None:
        raw = _main_case("relay_tentative_connection").model_dump(mode="json")
        raw["case_id"] = "muse-review-a-gathered-v1"
        raw["primary_behavior"] = "relay_gathered_sources"
        raw["input"]["tools"].update({
            "serendipity_outcome": "gathered", "memory_records": ["My note."],
            "unfound_sources": ["An essay"], "search_outcome": "weak",
        })
        raw["input"]["tools"].pop("connection_claim")
        raw["input"]["tools"].pop("connection_follow_up")
        case = MuseReviewCase.model_validate(raw)
        tools = {tool.name: tool for tool in baseline_run._current_tools(case)}

        from src.linger.orchestration.inspection_context import begin_connection_inspection

        async def call():
            begin_connection_inspection()
            bundle = await tools["serendipity_explore"].function(intent="gather_sources")
            search = await tools["librarian_search"].function(
                work_id="w", book_version_id="v")
            return bundle, search

        bundle, search = asyncio.run(call())
        self.assertEqual("gathered", bundle.decision.status)
        self.assertEqual(("An essay",), bundle.decision.unfound_sources)
        self.assertEqual(3, len(bundle.evidence))
        self.assertEqual("weak", search.evidence_strength)
        self.assertEqual(2, len(search.evidence))

    def test_search_waits_for_an_overridden_route(self) -> None:
        raw = _main_case("confirm_chapter_boundary").model_dump(mode="json")
        raw["case_id"] = "muse-review-b-passages-v1"
        raw["input"]["tools"].update({
            "librarian_evidence": ["A passage."], "route_outcome": "passages",
            "search_outcome": "failure",
        })
        case = MuseReviewCase.model_validate(raw)
        tools = {tool.name: tool for tool in baseline_run._current_tools(case)}

        async def call():
            before = await tools["librarian_search"].function(work_id="w", book_version_id="v")
            route = await tools["librarian_route"].function()
            after = await tools["librarian_search"].function(work_id="w", book_version_id="v")
            return before, route, after

        before, route, after = asyncio.run(call())
        self.assertEqual("clarification", before.kind)
        self.assertEqual("passages", route.kind)
        self.assertEqual(("muse-review-b-passages-v1-e1",), route.evidence_ids)
        self.assertEqual("failure", after.kind)

    def test_prior_evidence_and_memory_capture_reach_the_draft_input(self) -> None:
        raw = _main_case("grounded_answer_within_boundary").model_dump(mode="json")
        raw["case_id"] = "muse-review-d-prior-v1"
        raw["input"].update({"prior_evidence": ["An earlier passage."], "allow_memory_capture": True})
        draft = baseline_run._current_input(MuseReviewCase.model_validate(raw))
        self.assertTrue(draft.muse_turn.policy.allow_memory_capture)
        self.assertEqual(
            [("muse-review-d-prior-v1-p1", "Chapter I, earlier passage 1")],
            [(record.evidence_id, record.location) for record in draft.prior_evidence],
        )
        unchanged = baseline_run._current_input(_main_case("grounded_answer_within_boundary"))
        self.assertFalse(unchanged.muse_turn.policy.allow_memory_capture)
        self.assertEqual((), unchanged.prior_evidence)


class MemoryAndDeclarationGateTests(unittest.TestCase):
    def test_memory_expectations_and_exact_slice(self) -> None:
        raw = _main_case("honor_superseded_statement").model_dump(mode="json")
        raw["expected"].update({"memory_kind": "memory_candidate", "require_session_line": True})
        case = MuseEvalCase.model_validate(raw)
        message = case.input.reader_message
        good = {"kind": "memory_candidate", "text": message[:10], "start_codepoint": 0,
                "end_codepoint": 10, "reason_code": "x"}
        earlier = case.input.history[0].reader
        declared = [{"source_kind": "session_line", "quote": earlier[:12]}]
        grade = grade_additive(case, "Reply.", evidence_uses=declared, memory=good)
        self.assertEqual(((), ()), (grade.memory_failures, grade.reply_failures))

        bad = {**good, "text": message[1:11]}
        grade = grade_additive(case, "Reply.", memory=bad)
        self.assertEqual(("memory_not_exact_slice",), grade.memory_failures)
        self.assertEqual(("missing_session_line",), grade.reply_failures)
        self.assertEqual(
            ("memory_kind:no_memory_candidate",),
            grade_additive(case, "Reply.", memory=NO_MEMORY).memory_failures,
        )


class SdkRetryCounterTests(unittest.TestCase):
    def test_hidden_sdk_retries_on_429_are_counted(self) -> None:
        from collections import Counter

        import httpx
        from openai import AsyncOpenAI, RateLimitError

        def rate_limited(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"retry-after-ms": "1"}, json={"error": {}})

        async def call() -> Counter:
            baseline_run._install_sdk_retry_counter()
            counter: Counter = Counter()
            baseline_run._SDK_RETRIES.set(counter)
            client = AsyncOpenAI(
                api_key="sk-test",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(rate_limited)),
            )
            with self.assertRaises(RateLimitError):
                await client.responses.create(model="stub", input="hi")
            return counter

        self.assertEqual({"429": 2}, dict(asyncio.run(call())))


class RetryCategoryParsingTests(unittest.TestCase):
    def test_schema_errors_name_their_field(self) -> None:
        from pydantic_ai.messages import ModelRequest, RetryPromptPart

        messages = [ModelRequest(parts=[RetryPromptPart(
            content=[{"type": "missing", "loc": ("memory",), "msg": "Field required", "input": {}}],
            tool_name="final_result",
        )])]
        self.assertEqual(
            [{"category": "output_schema", "fields": ["memory"]}],
            baseline_run._retry_categories(messages, ("serendipity_explore",)),
        )

    def test_output_check_errors_name_their_fields(self) -> None:
        from pydantic_ai.messages import ModelRequest, RetryPromptPart

        content = json.dumps({"errors": [
            {"path": "evidence_uses[0].exact_quote"},
            {"path": "evidence_uses[1].supported_claims[0]"},
        ]})
        messages = [ModelRequest(parts=[RetryPromptPart(content=content, tool_name="final_result")])]
        self.assertEqual(
            [{"category": "output_validation", "fields": ["exact_quote", "supported_claims"]}],
            baseline_run._retry_categories(messages, ()),
        )


if __name__ == "__main__":
    unittest.main()
