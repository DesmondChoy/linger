"""Executable Serendipity component evaluation contracts and hard gates."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_evals.reporting import ReportCaseFailure

from evals.serendipity.harness import (
    REQUIRED_BEHAVIORS,
    ExpectedDecline,
    ExpectedProposal,
    ExpectedRecall,
    RunObservation,
    SearchObservation,
    dataset_digest,
    grade_serendipity_run,
    load_serendipity_eval_cases,
)
from evals.serendipity.runner import (
    CaseExecutionErrorReport,
    _FixtureLibrarian,
    _fixture_book_judge,
    _ordered_results,
    run_case,
)
from evals.serendipity.objective_replay import (
    CrossSourceReplayCase,
    grade_cross_source_response,
)
from apps.backend.schemas import (
    CaptureInspection,
    ChatResponse,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDecline,
    ConnectionProposal,
    MemoryRecall,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian


def _proposal(case) -> ConnectionProposal:
    assert isinstance(case.expected, ExpectedProposal)
    evidence_ids = (
        case.expected.required_evidence_ids or case.expected.acceptable_evidence_ids
    )
    candidates = (
        ConnectionCandidate(
            candidate_id="candidate-supported",
            tentative_claim="The evidence supports one specific recurring structure.",
            evidence_ids=evidence_ids,
            shared_structure="Both moments put identity under pressure.",
            meaningful_difference="One enacts change while the other asks for an account of it.",
            interpretation="The later question may make earlier instability explicit.",
            rubric=CandidateRubric(
                cue_fit="direct",
                reflective_value="high",
                safety="clear",
            ),
            comparison_note="This candidate answers the exact cue most directly.",
        ),
        ConnectionCandidate(
            candidate_id="candidate-secondary",
            tentative_claim="The evidence also frames uncertainty as social pressure.",
            evidence_ids=(_secondary_evidence_id(case, evidence_ids),),
            shared_structure="Both moments involve uncertainty.",
            meaningful_difference="This bridge emphasizes audience rather than change.",
            interpretation="The question may feel unsettling because it demands certainty.",
            rubric=CandidateRubric(
                cue_fit="partial",
                reflective_value="medium",
                safety="clear",
            ),
            comparison_note="This remains plausible but requires another inference.",
        ),
    )
    has_web = any(
        item.source_kind == "web" and item.evidence_id in evidence_ids
        for item in case.tool_evidence
    )
    return ConnectionProposal(
        shortlist=candidates,
        selected_candidate_id="candidate-supported",
        uncertainty="medium",
        presentation=case.expected.presentation,
        suggested_follow_up="Does that distinction change how the scene feels?",
        policy_flags=("contains_web_claim",) if has_web else (),
    )


def _secondary_evidence_id(case, cited: tuple[str, ...]) -> str:
    """A record the winner does not cite, so the shortlist rests on distinct evidence.

    Never a record the case forbids: a case that requires an ineligible record
    to be excluded must not have it reintroduced by the fixture helper.
    """
    forbidden = set(getattr(case.expected, "forbidden_evidence_ids", ()))
    for item in case.tool_evidence:
        if item.evidence_id not in cited and item.evidence_id not in forbidden:
            return item.evidence_id
    return cited[-1]


def _observation(case, *, response=None) -> RunObservation:
    if response is None:
        if isinstance(case.expected, ExpectedProposal):
            response = _proposal(case)
        elif isinstance(case.expected, ExpectedRecall):
            response = MemoryRecall(
                evidence_ids=(
                    case.expected.required_evidence_ids
                    or case.expected.acceptable_evidence_ids
                ),
                relevance_note="The reader's own earlier statement on what the cue asks about.",
            )
        else:
            response = ConnectionDecline(
                reason=case.expected.allowed_reasons[0],
                safe_next_step="No connection cleared the current evidence checks.",
            )
    searches = tuple(
        SearchObservation(
            operation=operation,
            source=(
                "memory" if operation == "search_memories"
                else "book_corpus" if operation == "search_librarian"
                else "web"
            ),
            outcome="evidence_found",
        )
        for operation in case.expected_searches.required_operations
    )
    tools = ["search_librarian"]
    if "web" in case.input.scope.allowed_sources:
        tools.extend(("web_search", "get_page"))
    return RunObservation(
        response=response.model_dump(mode="json"),
        evidence=case.tool_evidence,
        searches=searches,
        available_tools=tuple(tools),
        model_requests=3,
        tool_calls=len(searches),
        latency_seconds=0.01,
    )


class SerendipityEvalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_serendipity_eval_cases()

    def test_current_cases_cover_every_required_behavior(self) -> None:
        self.assertTrue(self.cases)
        self.assertEqual(
            REQUIRED_BEHAVIORS,
            {case.primary_behavior for case in self.cases},
        )
        self.assertTrue(all(case.schema_version == 3 for case in self.cases))
        self.assertEqual(64, len(dataset_digest(self.cases)))

    def test_future_memory_case_is_not_in_current_baseline(self) -> None:
        self.assertTrue(
            Path("evals/serendipity/cases/future/authorised-memory-connection.json").is_file()
        )
        self.assertNotIn(
            "route_authorised_memory_connection",
            {case.primary_behavior for case in self.cases},
        )

    def test_baseline_contains_a_contrast_pair(self) -> None:
        groups: dict[str, int] = {}
        for case in self.cases:
            groups[case.contrast_group] = groups.get(case.contrast_group, 0) + 1
        self.assertGreaterEqual(groups["book-specificity"], 2)

    def test_hard_grader_accepts_known_good_local_decisions(self) -> None:
        for case in self.cases:
            with self.subTest(case_id=case.case_id):
                grade = grade_serendipity_run(case, _observation(case))
                self.assertTrue(grade.hard_pass, grade.failures)

    def test_hard_grader_uses_observed_searches_and_budgets(self) -> None:
        case = next(
            item
            for item in self.cases
            if item.primary_behavior == "route_book_relationship_to_librarian"
        )
        observation = _observation(case).model_copy(
            update={"searches": (), "tool_calls": 7, "model_requests": 9}
        )
        grade = grade_serendipity_run(case, observation)
        self.assertFalse(grade.hard_pass)
        self.assertIn("no_observed_search", grade.failures)
        self.assertIn("model_request_budget_exceeded", grade.failures)
        self.assertIn("tool_call_budget_exceeded", grade.failures)

    def test_loader_allows_multiple_cases_per_behavior(self) -> None:
        source = next(
            item
            for item in self.cases
            if item.primary_behavior == "decline_when_no_supported_bridge_exists"
        )
        with TemporaryDirectory() as directory:
            target = Path(directory)
            for index, case in enumerate(self.cases):
                (target / f"{index:02}.json").write_text(
                    case.model_dump_json(indent=2), encoding="utf-8"
                )
            successor = source.model_copy(
                update={"case_id": "serendipity-decline-bridge-successor-v3"}
            )
            (target / "99.json").write_text(
                successor.model_dump_json(indent=2), encoding="utf-8"
            )
            loaded = load_serendipity_eval_cases(target)
        self.assertEqual(len(self.cases) + 1, len(loaded))

    def _case(self, case_id: str):
        return next(item for item in self.cases if item.case_id == case_id)

    def test_winner_forbidden_evidence_fails_only_in_the_winner(self) -> None:
        case = self._case("serendipity-rank-clear-winner-v3")
        proposal = _proposal(case)
        winner, runner_up = proposal.shortlist
        in_winner = proposal.model_copy(
            update={
                "shortlist": (
                    winner.model_copy(
                        update={"evidence_ids": (*winner.evidence_ids, "rank-alice-ch4-puppy")}
                    ),
                    runner_up,
                )
            }
        )
        grade = grade_serendipity_run(case, _observation(case, response=in_winner))
        self.assertIn("winner_cites_forbidden_evidence:rank-alice-ch4-puppy", grade.failures)

        in_runner_up = proposal.model_copy(
            update={
                "shortlist": (
                    winner,
                    runner_up.model_copy(update={"evidence_ids": ("rank-alice-ch4-puppy",)}),
                )
            }
        )
        grade = grade_serendipity_run(case, _observation(case, response=in_runner_up))
        self.assertTrue(grade.hard_pass, grade.failures)

    def test_recall_padded_with_forbidden_record_fails(self) -> None:
        case = self._case("serendipity-recall-matching-memory-v3")
        padded = MemoryRecall(
            evidence_ids=("memory-morning-practice", "memory-weekend-walks"),
            relevance_note="The reader's own earlier statement on what the cue asks about.",
        )
        grade = grade_serendipity_run(case, _observation(case, response=padded))
        self.assertIn("recall_cites_forbidden_evidence:memory-weekend-walks", grade.failures)

    def test_decline_without_search_passes_only_when_no_search_is_required(self) -> None:
        not_granted = self._case("serendipity-requested-source-not-granted-v3")
        decline = ConnectionDecline(
            reason="source_scope_violation",
            safe_next_step="Web search is not available for this request.",
        )
        observation = _observation(not_granted, response=decline).model_copy(
            update={"searches": (), "tool_calls": 0}
        )
        grade = grade_serendipity_run(not_granted, observation)
        self.assertTrue(grade.hard_pass, grade.failures)

        needs_search = self._case("serendipity-decline-insufficient-bridge-v3")
        observation = _observation(needs_search).model_copy(update={"searches": (), "tool_calls": 0})
        self.assertIn("no_observed_search", grade_serendipity_run(needs_search, observation).failures)

    def test_unset_primary_operation_accepts_either_order(self) -> None:
        case = self._case("serendipity-granted-url-opened-directly-v3")
        observation = _observation(case)
        reversed_order = observation.model_copy(
            update={"searches": tuple(reversed(observation.searches))}
        )
        grade = grade_serendipity_run(case, reversed_order)
        self.assertTrue(grade.hard_pass, grade.failures)

    def test_every_case_declares_a_tier(self) -> None:
        tiers = {case.tier for case in self.cases}
        self.assertEqual({"regression", "capability"}, tiers)


class SerendipityFixtureRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_book_judge_honors_the_requested_selection_budget(self) -> None:
        case = load_serendipity_eval_cases()[0]
        self.assertEqual("serendipity-select-real-semantic-bridge-v3", case.case_id)
        self.assertEqual(2, len(case.tool_evidence))

        for limit in (1, 2, 5):
            with self.subTest(limit=limit):
                deps = SerendipityDependencies(
                    task=case.input,
                    librarian=_FixtureLibrarian(case.tool_evidence),
                    strength_judge=_fixture_book_judge(case),
                )

                result = await search_librarian(
                    SimpleNamespace(deps=deps), max_results_per_source=limit,
                )

                self.assertEqual("evidence_found", result.outcome)
                self.assertEqual(case.tool_evidence[:limit], result.evidence)
                self.assertEqual(
                    tuple(item.evidence_id for item in result.evidence),
                    result.judgement.relevant_evidence_ids,
                )
                self.assertEqual(
                    "weak" if limit == 1 else "sufficient",
                    result.judgement.evidence_strength,
                )
                self.assertEqual(limit == 1, bool(result.judgement.limitations))
                self.assertEqual("evidence_found", deps.searches[0].outcome)

    def test_suite_report_preserves_captured_case_execution_errors(self) -> None:
        case = load_serendipity_eval_cases()[0]
        failure = ReportCaseFailure(
            name=case.case_id,
            inputs=case,
            metadata=None,
            expected_output=None,
            error_message="ModelHTTPError: provider unavailable",
            error_stacktrace="synthetic traceback",
            trace_id="1" * 32,
        )

        ordered = _ordered_results((case,), (), (failure,))

        self.assertEqual(1, len(ordered))
        self.assertIsInstance(ordered[0], CaseExecutionErrorReport)
        self.assertEqual(case.case_id, ordered[0].case_id)
        self.assertEqual("ModelHTTPError: provider unavailable", ordered[0].error_message)

    async def test_runner_executes_production_agent_with_fixture_librarian(self) -> None:
        case = next(
            item
            for item in load_serendipity_eval_cases()
            if item.primary_behavior == "route_book_relationship_to_librarian"
        )
        expected = _proposal(case)

        def respond(messages, info: AgentInfo) -> ModelResponse:
            self.assertEqual(CONNECTION_DISCOVERY.effective_instructions, info.instructions)
            self.assertEqual(
                {"search_librarian", "web_search", "get_page"},
                {tool.name for tool in info.function_tools},
            )
            returns = [
                part
                for message in messages
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            ]
            if not returns:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_librarian",
                            {},
                        )
                    ]
                )
            output_tool = info.output_tools[0]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        output_tool.name,
                        expected.model_dump(mode="json", exclude={"status"}),
                    )
                ]
            )

        with patch(
            "src.linger.orchestration.book_evidence.plan_book_request",
            new=AsyncMock(side_effect=AssertionError("Fixture evaluation must not call a live judge")),
        ) as live_judge:
            report = await run_case(case, model=FunctionModel(respond))
        live_judge.assert_not_awaited()

        self.assertTrue(report.grade.hard_pass, report.grade.failures)
        self.assertEqual("search_librarian", report.observation.searches[0].operation)
        self.assertEqual(
            set(case.expected.required_evidence_ids),
            {item.evidence_id for item in report.observation.evidence},
        )

    async def test_runner_observes_web_search_then_opened_page(self) -> None:
        case = next(
            item
            for item in load_serendipity_eval_cases()
            if item.primary_behavior == "route_external_recommendation_to_web"
        )
        expected = _proposal(case)
        required_url = (
            case.expected.required_evidence_ids or case.expected.acceptable_evidence_ids
        )[0]
        # The shortlist compares two candidates on distinct records, so the run
        # opens every page it intends to cite, not only the required one.
        opened_urls = [required_url, _secondary_evidence_id(case, (required_url,))]

        def respond(messages, info: AgentInfo) -> ModelResponse:
            returns = [
                part
                for message in messages
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            ]
            if not returns:
                return ModelResponse(
                    parts=[ToolCallPart("web_search", {"query": "philosophy continuity selfhood"})]
                )
            if len(returns) <= len(opened_urls):
                return ModelResponse(
                    parts=[ToolCallPart("get_page", {"url": opened_urls[len(returns) - 1]})]
                )
            output_tool = info.output_tools[0]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        output_tool.name,
                        expected.model_dump(mode="json", exclude={"status"}),
                    )
                ]
            )

        report = await run_case(case, model=FunctionModel(respond))

        self.assertTrue(report.grade.hard_pass, report.grade.failures)
        self.assertEqual(
            ["web_search", "get_page", "get_page"],
            [search.operation for search in report.observation.searches],
        )
        self.assertEqual(
            set(opened_urls),
            {item.evidence_id for item in report.observation.evidence},
        )


class CrossSourceObjectiveStageTests(unittest.TestCase):
    def _case(self) -> CrossSourceReplayCase:
        return CrossSourceReplayCase(
            schema_version=1,
            case_id="cross-source-stage-test-v1",
            objective_id="cross_source_tentative_connection",
            messages=("Connect this chapter to an outside essay.",),
        )

    def _response(
        self,
        *,
        serendipity_status: str,
        librarian_status: str,
        release_source: str,
        failure_stage: str | None,
    ) -> ChatResponse:
        capture = CaptureInspection(
            nomination="no_candidate",
            provenance_decision="no_candidate",
            binding="not_applicable",
            storage="not_applicable",
            reason_code="not_applicable",
        )
        release = ReleaseInspection.model_validate(
            {
                "release_source": release_source,
                "provenance_verdicts": ["pass"],
                "finding_codes": [],
                "revision_count": 0,
                "failure_stage": failure_stage,
                # `failure_type` and `failure_retryable` are paired with a stage
                # by contract, so a staged failure must classify itself.
                "failure_type": "validation" if failure_stage else None,
                "failure_retryable": False if failure_stage else None,
                "capture": capture.model_dump(mode="json"),
            }
        )
        return ChatResponse(
            reply="A bounded synthetic response.",
            inspection=TurnInspection(
                muse_turn={},
                context_resolution={},
                traces=[
                    {"agent": "Serendipity", "status": serendipity_status, "detail": "test"},
                    {"agent": "Librarian", "status": librarian_status, "detail": "test"},
                ],
                prompt="{}",
                release=release,
            ),
            trace=TraceReference(
                trace_id="0" * 32,
            ),
        )

    def test_reports_deterministic_release_as_first_failure(self) -> None:
        response = self._response(
            serendipity_status="complete",
            librarian_status="declined",
            release_source="application_safe_decline",
            failure_stage="deterministic_validation",
        )
        from src.linger.evaluation_transcript import ConnectionEvaluationEvent
        report = grade_cross_source_response(self._case(), response, run_id="run", events=(
            ConnectionEvaluationEvent(kind="search", status="evidence_found", source="book_corpus"),
            ConnectionEvaluationEvent(kind="discovery", status="proposal"),
        ))

        self.assertEqual("deterministic_release", report.first_failure_stage)
        self.assertEqual(
            ["passed", "passed", "passed", "passed", "passed", "failed"],
            [stage.status for stage in report.stages],
        )
        self.assertFalse(report.hard_gate_pass)

    def test_stops_stage_claims_after_missing_invocation(self) -> None:
        response = self._response(
            serendipity_status="skipped",
            librarian_status="skipped",
            release_source="muse_candidate",
            failure_stage=None,
        )
        report = grade_cross_source_response(self._case(), response, run_id="run")

        self.assertEqual("invocation", report.first_failure_stage)
        self.assertEqual("failed", report.stages[0].status)
        self.assertTrue(all(stage.status == "not_reached" for stage in report.stages[1:]))

    def test_discovery_failure_after_search_is_a_selection_failure(self) -> None:
        from src.linger.evaluation_transcript import ConnectionEvaluationEvent
        response = self._response(serendipity_status="declined", librarian_status="declined", release_source="muse_candidate", failure_stage=None)
        report = grade_cross_source_response(self._case(), response, run_id="run", events=(
            ConnectionEvaluationEvent(kind="search", status="evidence_found", source="book_corpus"),
            ConnectionEvaluationEvent(kind="discovery", status="failed", failure_code="connection_discovery_failed"),
        ))
        self.assertEqual("passed", report.stages[1].status)
        self.assertEqual("serendipity_selection", report.first_failure_stage)

    def test_honest_decline_uses_raw_discovery_instead_of_api_status(self) -> None:
        from src.linger.evaluation_transcript import ConnectionEvaluationEvent
        case = self._case().model_copy(update={"expected_decision": "decline"})
        response = self._response(serendipity_status="declined", librarian_status="declined", release_source="muse_candidate", failure_stage=None)
        report = grade_cross_source_response(case, response, run_id="run", events=(
            ConnectionEvaluationEvent(kind="search", status="no_evidence", source="book_corpus"),
            ConnectionEvaluationEvent(kind="discovery", status="decline"),
        ))
        self.assertTrue(report.hard_gate_pass)
        self.assertTrue(report.semantic_review_required)


if __name__ == "__main__":
    unittest.main()
