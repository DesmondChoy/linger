"""Contracts and agent wiring for tool-led Serendipity discovery."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import SecretStr, ValidationError
from pydantic_ai import ModelRetry, UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend.config import Settings
from apps.backend.contracts import BookScope, ConnectionBrief, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    ConnectionScope,
)
from src.linger.agents.serendipity.tools import (
    GuardedExaSearch,
    SearchTrace,
    SerendipityDependencies,
    search_librarian,
)
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection,
    connection_inspections,
    reset_connection_inspection,
)
from src.linger.orchestration.turn_context import (
    reset_reader_message,
    reset_confirmed_reading,
    set_reader_message,
    set_confirmed_reading,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.agents.muse.tools import serendipity_explore
    from src.linger.agents.serendipity.agent import (
        build_serendipity_agent,
        validate_serendipity_output,
    )
    from src.linger.orchestration.connection import (
        ExplorationResult,
        SERENDIPITY_TOOL_CALL_LIMIT,
        _agent_explorer,
        connection_exploration,
        web_reach_permitted,
    )


def task(
    *, allowed_sources: tuple[str, ...] = ("book_corpus",)
) -> ConnectionDiscoveryInput:
    return ConnectionDiscoveryInput(
        cue="Why does changing size make Alice unsure who she is?",
        intent="find_connection",
        presentation="ask_before_showing",
        scope=ConnectionScope(
            allowed_sources=allowed_sources,
            book_scopes=(
                BookScope(
                    work_id="pg11",
                    book_version_id="pg11-v1",
                    chapter_max=5,
                ),
            )
            if "book_corpus" in allowed_sources
            else (),
        ),
    )


def rubric(**updates: object) -> CandidateRubric:
    values: dict[str, object] = {
        "cue_fit": "direct",
        "reflective_value": "high",
        "safety": "clear",
        "disqualifiers": (),
    }
    values.update(updates)
    return CandidateRubric.model_validate(values)


def candidate(
    candidate_id: str,
    position: int,
    *,
    evidence_ids: tuple[str, ...] = ("chapter-4", "chapter-5"),
    candidate_rubric: CandidateRubric | None = None,
) -> ConnectionCandidate:
    return ConnectionCandidate(
        candidate_id=candidate_id,
        tentative_claim=(
            "Alice's changing body complicates her account of identity."
            if position == 1
            else "The Caterpillar's composure may make Alice's uncertainty feel judged."
        ),
        evidence_ids=evidence_ids,
        shared_structure="Physical change and uncertainty about identity recur.",
        meaningful_difference=(
            "One scene enacts change; the other demands an explanation of it."
        ),
        interpretation="The repetition may make identity feel unstable rather than fixed.",
        rubric=candidate_rubric
        or (
            rubric()
            if position == 1
            else rubric(cue_fit="partial", reflective_value="medium")
        ),
        comparison_note=(
            "This ranks higher because the textual bridge is direct."
            if position == 1
            else "This remains plausible but adds less reflective value."
        ),
    )


def proposal(**updates: object) -> ConnectionProposal:
    values: dict[str, object] = {
        "shortlist": (
            candidate("candidate-identity", 1),
            candidate("candidate-authority", 2, evidence_ids=("chapter-5",)),
        ),
        "selected_candidate_id": "candidate-identity",
        "uncertainty": "medium",
        "presentation": "ask_before_showing",
        "suggested_follow_up": "Does that repetition make the question feel harsher?",
        "policy_flags": (),
    }
    values.update(updates)
    return ConnectionProposal.model_validate(values)


class SerendipityContractTests(unittest.TestCase):
    def test_trusted_reader_cue_accepts_the_full_chat_boundary(self) -> None:
        cue = "x" * 8_000

        brief = ConnectionBrief(cue=cue)
        active_task = ConnectionDiscoveryInput.model_validate(
            {**task().model_dump(mode="python"), "cue": cue}
        )

        self.assertEqual(cue, brief.cue)
        self.assertEqual(cue, active_task.cue)

    def test_dynamic_input_grants_sources_but_contains_no_evidence(self) -> None:
        result = task(allowed_sources=("book_corpus", "web"))

        self.assertFalse(hasattr(result, "evidence"))
        self.assertEqual(("book_corpus", "web"), result.scope.allowed_sources)

    def test_book_grant_requires_a_bounded_book_scope(self) -> None:
        with self.assertRaisesRegex(ValidationError, "book-corpus access"):
            ConnectionScope(allowed_sources=("book_corpus",))

    def test_authorised_memory_cannot_be_granted_in_this_slice(self) -> None:
        with self.assertRaises(ValidationError):
            ConnectionScope(allowed_sources=("authorised_memory",))

    def test_proposal_exposes_the_rank_one_candidate_as_its_winner(self) -> None:
        result = proposal()

        self.assertEqual("candidate-identity", result.selected_candidate_id)
        self.assertEqual(
            ("chapter-4", "chapter-5"),
            result.selected_candidate.evidence_ids,
        )

    def test_proposal_requires_two_or_three_ordered_candidates(self) -> None:
        with self.assertRaises(ValidationError):
            proposal(shortlist=(candidate("candidate-only", 1),))
        with self.assertRaisesRegex(ValidationError, "rank-one"):
            proposal(
                shortlist=(
                    candidate("candidate-first", 1),
                    candidate("candidate-second", 2),
                ),
                selected_candidate_id="candidate-second",
            )

    def test_proposal_rejects_an_ineligible_shortlist_candidate(self) -> None:
        ineligible = rubric(
            cue_fit="weak",
            safety="ineligible",
            disqualifiers=("generic_only",),
        )
        with self.assertRaisesRegex(ValidationError, "only eligible"):
            proposal(
                shortlist=(
                    candidate("candidate-first", 1),
                    candidate(
                        "candidate-generic", 2, candidate_rubric=ineligible
                    ),
                ),
                selected_candidate_id="candidate-first",
            )

    def test_low_reflective_value_is_ineligible(self) -> None:
        with self.assertRaisesRegex(ValidationError, "only eligible"):
            proposal(
                shortlist=(
                    candidate("candidate-first", 1),
                    candidate(
                        "candidate-restatement",
                        2,
                        candidate_rubric=rubric(
                            cue_fit="partial",
                            reflective_value="low",
                        ),
                    ),
                ),
                selected_candidate_id="candidate-first",
            )

    def test_proposal_requires_a_clear_rank_one_winner(self) -> None:
        tied = rubric()
        with self.assertRaisesRegex(ValidationError, "clear rubric winner"):
            proposal(
                shortlist=(
                    candidate("candidate-first", 1, candidate_rubric=tied),
                    candidate("candidate-second", 2, candidate_rubric=tied),
                ),
                selected_candidate_id="candidate-first",
            )

    def test_rubric_values_are_ordinal_not_numeric_confidence(self) -> None:
        result = rubric()
        self.assertTrue(result.eligible)
        with self.assertRaises(ValidationError):
            rubric(cue_fit=0.91)

    def test_contracts_reject_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            proposal(storage_authorised=True)


class WebReachPolicyTests(unittest.TestCase):
    def test_web_reach_is_disabled_by_default_even_with_a_key(self) -> None:
        settings = Settings(
            linger_model="google:gemini-2.5-flash",
            exa_api_key=SecretStr("test-exa-key"),
        )

        with patch(
            "src.linger.orchestration.connection.get_settings",
            return_value=settings,
        ):
            self.assertFalse(web_reach_permitted())

    def test_web_reach_requires_toggle_and_nonblank_key(self) -> None:
        for key, expected in (
            (None, False),
            (SecretStr("   "), False),
            (SecretStr("test-exa-key"), True),
        ):
            with self.subTest(key_present=key is not None):
                settings = Settings(
                    linger_model="google:gemini-2.5-flash",
                    linger_web_search_enabled=True,
                    exa_api_key=key,
                )
                with patch(
                    "src.linger.orchestration.connection.get_settings",
                    return_value=settings,
                ):
                    self.assertEqual(expected, web_reach_permitted())


class SerendipityAgentTests(unittest.IsolatedAsyncioTestCase):
    def deps(
        self, active_task: ConnectionDiscoveryInput | None = None
    ) -> SerendipityDependencies:
        return SerendipityDependencies(
            task=active_task or task(),
            librarian=Librarian(),
        )

    async def test_agent_exposes_librarian_search_and_typed_outputs(self) -> None:
        expected = proposal()
        model = TestModel(custom_output_args=expected, seed=0)
        agent = build_serendipity_agent(model)
        active_task = task(allowed_sources=("book_corpus",))

        deps = self.deps(active_task)
        for evidence_id, chapter in (("chapter-4", 4), ("chapter-5", 5)):
            deps.evidence[evidence_id] = EvidenceItem(
                evidence_id=evidence_id,
                source_title="Alice's Adventures in Wonderland",
                work_id="pg11",
                book_version_id="pg11-v1",
                chapter_id=f"chapter-{chapter}",
                chapter=chapter,
                location=f"Chapter {chapter}",
                source_sha256="a" * 64,
                source_lines=(chapter, chapter),
                excerpt="Alice's changes make identity feel unstable.",
                relevance=1.0,
            )

        result = await agent.run(active_task.model_dump_json(), deps=deps)

        self.assertEqual(expected, result.output)
        parameters = model.last_model_request_parameters
        self.assertIsNotNone(parameters)
        assert parameters is not None
        self.assertEqual(
            ["search_librarian"],
            [tool.name for tool in parameters.function_tools],
        )
        self.assertEqual(2, len(parameters.output_tools))
        self.assertEqual("canonical", deps.evidence["chapter-4"].trust_level)

    async def test_agent_round_trips_a_first_class_decline(self) -> None:
        expected = ConnectionDecline(
            reason="generic_theme_match",
            safe_next_step="Describe the particular moment that stayed with you.",
        )
        model = TestModel(custom_output_args=expected, seed=1)
        agent = build_serendipity_agent(model)

        result = await agent.run(task().model_dump_json(), deps=self.deps())

        self.assertEqual(expected, result.output)

    async def test_exa_search_is_only_citable_after_get_page(self) -> None:
        url = "https://example.com/identity"

        class FakeExaClient:
            async def search(self, *_args, **_kwargs):
                return SimpleNamespace(
                    results=[
                        SimpleNamespace(
                            url=url,
                            title="Identity and change",
                            published_date=None,
                            author=None,
                            highlights=["A short search-result lead."],
                        )
                    ],
                    output=None,
                )

            async def get_contents(self, *_args, **_kwargs):
                return SimpleNamespace(
                    results=[
                        SimpleNamespace(
                            url=url,
                            title="Identity and change",
                            published_date=None,
                            author=None,
                            text="A complete public page about identity and change.",
                        )
                    ]
                )

        def respond(messages, info: AgentInfo) -> ModelResponse:
            returns = [
                part
                for message in messages
                for part in getattr(message, "parts", ())
                if isinstance(part, ToolReturnPart)
            ]
            if not any(part.tool_name == "web_search" for part in returns):
                return ModelResponse(
                    parts=[ToolCallPart("web_search", {"query": "identity change"})]
                )
            if not any(part.tool_name == "get_page" for part in returns):
                return ModelResponse(
                    parts=[ToolCallPart("get_page", {"url": url})]
                )
            output_tool = info.output_tools[0]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        output_tool.name,
                        proposal(
                            shortlist=(
                                candidate(
                                    "candidate-web-identity",
                                    1,
                                    evidence_ids=(url,),
                                ),
                                candidate(
                                    "candidate-web-authority",
                                    2,
                                    evidence_ids=(url,),
                                ),
                            ),
                            selected_candidate_id="candidate-web-identity",
                            policy_flags=("contains_web_claim",),
                        ).model_dump(mode="json"),
                    )
                ]
            )

        active_task = task(allowed_sources=("web",))
        deps = self.deps(active_task)
        agent = build_serendipity_agent(FunctionModel(respond))

        result = await agent.run(
            active_task.model_dump_json(),
            deps=deps,
            capabilities=[GuardedExaSearch(client=FakeExaClient())],
        )

        self.assertIsInstance(result.output, ConnectionProposal)
        self.assertEqual((url,), tuple(deps.evidence))
        self.assertEqual(("web", "web"), tuple(trace.source for trace in deps.searches))
        self.assertEqual(
            ("evidence_found", "evidence_found"),
            tuple(trace.outcome for trace in deps.searches),
        )
        self.assertEqual({url}, deps.web_leads)
        self.assertIn("complete public page", deps.evidence[url].excerpt)
        self.assertEqual("external", deps.evidence[url].trust_level)

    async def test_agent_explorer_enforces_a_small_tool_call_budget(self) -> None:
        exa_calls = 0

        class RepeatingExaClient:
            async def search(self, *_args, **_kwargs):
                nonlocal exa_calls
                exa_calls += 1
                return SimpleNamespace(results=[], output=None)

        def respond(_messages, _info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[ToolCallPart("web_search", {"query": "identity philosophy"})]
            )

        active_task = task(allowed_sources=("web",))
        agent = build_serendipity_agent(FunctionModel(respond))
        capability = GuardedExaSearch(client=RepeatingExaClient())
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch(
            "src.linger.orchestration.connection.serendipity_agent",
            agent,
        ), patch(
            "src.linger.orchestration.connection._web_capability",
            return_value=capability,
        ), patch(
            "apps.backend.telemetry.get_settings",
            return_value=settings,
        ):
            with self.assertRaises(UsageLimitExceeded):
                await _agent_explorer(active_task, librarian=Librarian())

        self.assertEqual(SERENDIPITY_TOOL_CALL_LIMIT, exa_calls)

    async def test_exa_rejects_private_cue_terms_and_shaped_personal_data(self) -> None:
        for cue, unsafe_query in (
            ("My affair with Jane", "Jane affair"),
            ("Li and I divorced", "Li divorce"),
            ("Will and I divorced", "Will divorce"),
            ("will and i divorced", "will divorce"),
            ("José and I divorced", "Jose\u0301 divorce"),
            ("will and i divorced", "ｗｉｌｌ divorce"),
            ("Find a public essay about loss", "reader@example.com grief essay"),
        ):
            with self.subTest(query=unsafe_query):
                search_calls = 0

                class FakeExaClient:
                    async def search(self, *_args, **_kwargs):
                        nonlocal search_calls
                        search_calls += 1
                        raise AssertionError("private query reached Exa")

                def respond(messages, info: AgentInfo) -> ModelResponse:
                    retried = any(
                        isinstance(part, RetryPromptPart)
                        for message in messages
                        for part in getattr(message, "parts", ())
                    )
                    if not retried:
                        return ModelResponse(
                            parts=[
                                ToolCallPart("web_search", {"query": unsafe_query})
                            ]
                        )
                    output_tool = info.output_tools[1]
                    return ModelResponse(
                        parts=[
                            ToolCallPart(
                                output_tool.name,
                                ConnectionDecline(
                                    reason="unsafe_evidence",
                                    safe_next_step="Try a more general public concept.",
                                ).model_dump(mode="json"),
                            )
                        ]
                    )

                active_task = task(allowed_sources=("web",)).model_copy(
                    update={"cue": cue}
                )
                deps = self.deps(active_task)
                agent = build_serendipity_agent(FunctionModel(respond))

                result = await agent.run(
                    active_task.model_dump_json(),
                    deps=deps,
                    capabilities=[GuardedExaSearch(client=FakeExaClient())],
                )

                self.assertIsInstance(result.output, ConnectionDecline)
                self.assertEqual(0, search_calls)

    def test_failed_librarian_search_records_a_content_free_handoff(self) -> None:
        class FailingLibrarian:
            def retrieve(self, _request):
                raise RuntimeError("private retrieval failure")

        active_task = task()
        deps = SerendipityDependencies(
            task=active_task,
            librarian=FailingLibrarian(),
        )

        result = search_librarian(
            SimpleNamespace(deps=deps),
            query="identity change",
        )

        self.assertEqual("retrieval_unavailable", result.outcome)
        self.assertEqual(1, len(deps.searches))
        self.assertEqual("book_corpus", deps.searches[0].source)
        self.assertEqual("retrieval_unavailable", deps.searches[0].outcome)

    async def test_failed_exa_search_records_a_content_free_handoff(self) -> None:
        class FailingExaClient:
            async def search(self, *_args, **_kwargs):
                raise RuntimeError("private Exa failure")

        def respond(_messages, _info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[ToolCallPart("web_search", {"query": "identity change"})]
            )

        active_task = task(allowed_sources=("web",))
        deps = self.deps(active_task)
        agent = build_serendipity_agent(FunctionModel(respond))

        with self.assertRaises(RuntimeError):
            await agent.run(
                active_task.model_dump_json(),
                deps=deps,
                capabilities=[GuardedExaSearch(client=FailingExaClient())],
            )

        self.assertEqual(1, len(deps.searches))
        self.assertEqual("web", deps.searches[0].source)
        self.assertEqual("retrieval_unavailable", deps.searches[0].outcome)

    def test_output_validator_retries_an_unopened_web_lead(self) -> None:
        url = "https://example.com/unopened-lead"
        active_task = task(allowed_sources=("web",))
        deps = self.deps(active_task)
        output = proposal(
            shortlist=(
                candidate("candidate-web-first", 1, evidence_ids=(url,)),
                candidate("candidate-web-second", 2, evidence_ids=(url,)),
            ),
            selected_candidate_id="candidate-web-first",
            policy_flags=("contains_web_claim",),
        )

        with self.assertRaisesRegex(ModelRetry, "get_page"):
            validate_serendipity_output(SimpleNamespace(deps=deps), output)

    async def test_get_page_rejects_a_url_not_returned_by_this_run(self) -> None:
        attempted_fetches = 0
        unapproved_url = "https://example.com/unapproved"

        class FakeExaClient:
            async def get_contents(self, *_args, **_kwargs):
                nonlocal attempted_fetches
                attempted_fetches += 1
                raise AssertionError("unapproved URL reached Exa")

        def respond(messages, info: AgentInfo) -> ModelResponse:
            retried = any(
                isinstance(part, RetryPromptPart)
                for message in messages
                for part in getattr(message, "parts", ())
            )
            if not retried:
                return ModelResponse(
                    parts=[ToolCallPart("get_page", {"url": unapproved_url})]
                )
            output_tool = info.output_tools[1]
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        output_tool.name,
                        ConnectionDecline(
                            reason="source_scope_violation",
                            safe_next_step="Search the public web first.",
                        ).model_dump(mode="json"),
                    )
                ]
            )

        active_task = task(allowed_sources=("web",))
        deps = self.deps(active_task)
        agent = build_serendipity_agent(FunctionModel(respond))

        result = await agent.run(
            active_task.model_dump_json(),
            deps=deps,
            capabilities=[GuardedExaSearch(client=FakeExaClient())],
        )

        self.assertIsInstance(result.output, ConnectionDecline)
        self.assertEqual(0, attempted_fetches)


class ConnectionSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_muse_cannot_replace_the_application_owned_reader_cue(self) -> None:
        expected = object()
        explorer = AsyncMock(return_value=expected)
        token = set_reader_message("My affair with Jane")
        try:
            with patch(
                "src.linger.agents.muse.tools.connection_exploration",
                explorer,
            ):
                result = await serendipity_explore()
        finally:
            reset_reader_message(token)

        self.assertIs(expected, result)
        brief = explorer.await_args.args[0]
        self.assertEqual("My affair with Jane", brief.cue)

    async def test_one_request_runs_discovery_once_and_rejects_a_new_intent(self) -> None:
        calls = 0

        async def explorer(_task: ConnectionDiscoveryInput) -> ExplorationResult:
            nonlocal calls
            calls += 1
            return ExplorationResult(
                response=ConnectionDecline(
                    reason="no_clear_winner",
                    safe_next_step="Try a more specific cue.",
                ),
                evidence=(),
                searches=(),
            )

        reading_token = set_confirmed_reading(
            ConfirmedReading(work_id="pg11", chapter_max=2)
        )
        inspection_token = begin_connection_inspection()
        try:
            with patch(
                "src.linger.orchestration.connection.web_reach_permitted",
                return_value=False,
            ):
                first = await connection_exploration(
                    ConnectionBrief(cue="identity"),
                    explorer=explorer,
                    librarian=Librarian(),
                )
                repeated = await connection_exploration(
                    ConnectionBrief(cue="identity"),
                    explorer=explorer,
                    librarian=Librarian(),
                )
                conflicting = await connection_exploration(
                    ConnectionBrief(cue="identity", intent="get_recommendation"),
                    explorer=explorer,
                    librarian=Librarian(),
                )
            inspections = connection_inspections()
        finally:
            reset_connection_inspection(inspection_token)
            reset_confirmed_reading(reading_token)

        self.assertEqual(1, calls)
        self.assertEqual(first, repeated)
        self.assertEqual("retrieval_unavailable", conflicting.decision.reason)
        self.assertEqual(1, len(inspections))

    async def test_no_source_grant_declines_without_running_an_explorer(self) -> None:
        explorer_called = False

        async def explorer(_task: ConnectionDiscoveryInput) -> ExplorationResult:
            nonlocal explorer_called
            explorer_called = True
            raise AssertionError("explorer received an empty source grant")

        with patch(
            "src.linger.orchestration.connection.web_reach_permitted",
            return_value=False,
        ):
            result = await connection_exploration(
                ConnectionBrief(cue="a reflective cue"),
                explorer=explorer,
                librarian=Librarian(),
            )

        self.assertFalse(explorer_called)
        self.assertEqual("no_permitted_evidence", result.decision.reason)

    async def test_failed_scope_validation_keeps_inspection_content_free(self) -> None:
        reading_token = set_confirmed_reading(
            ConfirmedReading(work_id="pg11", chapter_max=2)
        )
        inspection_token = begin_connection_inspection()
        try:
            async def explorer(
                active_task: ConnectionDiscoveryInput,
            ) -> ExplorationResult:
                scope = active_task.scope.book_scopes[0]
                evidence = EvidenceItem(
                    evidence_id="post-boundary",
                    source_title="Alice's Adventures in Wonderland",
                    work_id=scope.work_id,
                    book_version_id=scope.book_version_id,
                    chapter_id="chapter-3",
                    chapter=3,
                    location="Chapter 3",
                    source_sha256="a" * 64,
                    source_lines=(1, 1),
                    excerpt="POST-BOUNDARY SPOILER",
                    relevance=1.0,
                )
                return ExplorationResult(
                    response=ConnectionDecline(
                        reason="spoiler_boundary",
                        safe_next_step="Stay within the confirmed chapter.",
                    ),
                    evidence=(evidence,),
                    searches=(
                        SearchTrace(
                            source="book_corpus",
                            outcome="evidence_found",
                        ),
                    ),
                )

            with patch(
                "src.linger.orchestration.connection.web_reach_permitted",
                return_value=False,
            ):
                result = await connection_exploration(
                    ConnectionBrief(cue="identity"),
                    explorer=explorer,
                    librarian=Librarian(),
                )
            inspection = connection_inspections()[0]
        finally:
            reset_connection_inspection(inspection_token)
            reset_confirmed_reading(reading_token)

        self.assertEqual("retrieval_unavailable", result.decision.reason)
        self.assertEqual((), result.evidence)
        self.assertEqual(
            {
                "status": "decline",
                "reason": "retrieval_unavailable",
                "book_search_outcomes": ("evidence_found",),
                "failure_code": "connection_discovery_failed",
            },
            vars(inspection),
        )

    async def test_decline_discards_rejected_candidates_and_raw_evidence(self) -> None:
        reading_token = set_confirmed_reading(
            ConfirmedReading(work_id="pg11", chapter_max=2)
        )
        inspection_token = begin_connection_inspection()
        try:
            async def explorer(
                active_task: ConnectionDiscoveryInput,
            ) -> ExplorationResult:
                scope = active_task.scope.book_scopes[0]
                evidence = EvidenceItem(
                    evidence_id="chapter-2",
                    source_title="Alice's Adventures in Wonderland",
                    work_id=scope.work_id,
                    book_version_id=scope.book_version_id,
                    chapter_id="chapter-2",
                    chapter=2,
                    location="Chapter 2",
                    source_sha256="b" * 64,
                    source_lines=(1, 1),
                    excerpt="Raw evidence from a rejected connection.",
                    relevance=1.0,
                )
                return ExplorationResult(
                    response=ConnectionDecline(
                        reason="no_clear_winner",
                        safe_next_step="Repeat raw rejected evidence here.",
                    ),
                    evidence=(evidence,),
                    searches=(
                        SearchTrace(
                            source="book_corpus",
                            outcome="evidence_found",
                        ),
                    ),
                )

            with patch(
                "src.linger.orchestration.connection.web_reach_permitted",
                return_value=False,
            ):
                result = await connection_exploration(
                    ConnectionBrief(cue="identity"),
                    explorer=explorer,
                    librarian=Librarian(),
                )
            inspection = connection_inspections()[0]
        finally:
            reset_connection_inspection(inspection_token)
            reset_confirmed_reading(reading_token)

        self.assertEqual("no_clear_winner", result.decision.reason)
        self.assertNotIn("raw rejected evidence", result.decision.safe_next_step)
        self.assertEqual((), result.evidence)
        self.assertEqual(
            {
                "status": "decline",
                "reason": "no_clear_winner",
                "book_search_outcomes": ("evidence_found",),
                "failure_code": None,
            },
            vars(inspection),
        )


if __name__ == "__main__":
    unittest.main()
