"""Contracts and agent wiring for tool-led Serendipity discovery."""

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    BookEvidenceScope,
    BookConnectionEvidence,
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    ConnectionScope,
)
from src.linger.agents.serendipity.tools import (
    GuardedExaSearch,
    SerendipityDependencies,
    _query_copies_private_memory,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.agents.serendipity.agent import (
        build_serendipity_agent,
        validate_serendipity_output,
    )


def task(
    *, allowed_sources: tuple[str, ...] = ("book_corpus",)
) -> ConnectionDiscoveryInput:
    return ConnectionDiscoveryInput(
        request_id="serendipity-test-request",
        cue="Why does changing size make Alice unsure who she is?",
        intent="find_connection",
        presentation="ask_before_showing",
        scope=ConnectionScope(
            allowed_sources=allowed_sources,
            book_scopes=(
                BookEvidenceScope(
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
    rank: int,
    *,
    evidence_ids: tuple[str, ...] = ("chapter-4", "chapter-5"),
    candidate_rubric: CandidateRubric | None = None,
) -> ConnectionCandidate:
    return ConnectionCandidate(
        candidate_id=candidate_id,
        rank=rank,
        tentative_claim=(
            "Alice's changing body complicates her account of identity."
            if rank == 1
            else "The Caterpillar's composure may make Alice's uncertainty feel judged."
        ),
        evidence_ids=evidence_ids,
        shared_structure="Physical change and uncertainty about identity recur.",
        meaningful_difference=(
            "One scene enacts change; the other demands an explanation of it."
        ),
        interpretation="The repetition may make identity feel unstable rather than fixed.",
        rubric=candidate_rubric or rubric(),
        comparison_note=(
            "This ranks higher because the textual bridge is direct."
            if rank == 1
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
    def test_dynamic_input_grants_sources_but_contains_no_evidence(self) -> None:
        result = task(
            allowed_sources=("authorised_memory", "book_corpus", "web")
        )

        self.assertFalse(hasattr(result, "evidence"))
        self.assertEqual(
            ("authorised_memory", "book_corpus", "web"),
            result.scope.allowed_sources,
        )

    def test_book_grant_requires_a_bounded_book_scope(self) -> None:
        with self.assertRaisesRegex(ValidationError, "book-corpus access"):
            ConnectionScope(allowed_sources=("book_corpus",))

    def test_memory_grant_does_not_require_a_book_scope(self) -> None:
        result = task(allowed_sources=("authorised_memory",))
        self.assertEqual((), result.scope.book_scopes)

    def test_proposal_exposes_the_rank_one_candidate_as_its_winner(self) -> None:
        result = proposal()

        self.assertEqual("candidate-identity", result.selected_candidate_id)
        self.assertEqual(
            ("chapter-4", "chapter-5"),
            result.selected_candidate.evidence_ids,
        )

    def test_proposal_requires_two_or_three_ranked_candidates(self) -> None:
        with self.assertRaises(ValidationError):
            proposal(shortlist=(candidate("candidate-only", 1),))
        with self.assertRaisesRegex(ValidationError, "contiguous"):
            proposal(
                shortlist=(
                    candidate("candidate-first", 1),
                    candidate("candidate-third", 3),
                ),
                selected_candidate_id="candidate-first",
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

    def test_rubric_values_are_ordinal_not_numeric_confidence(self) -> None:
        result = rubric()
        self.assertTrue(result.eligible)
        with self.assertRaises(ValidationError):
            rubric(cue_fit=0.91)

    def test_contracts_reject_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            proposal(storage_authorised=True)


class SerendipityAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def deps(
        self, active_task: ConnectionDiscoveryInput | None = None
    ) -> SerendipityDependencies:
        return SerendipityDependencies(
            task=active_task or task(),
            librarian=Librarian(),
            memory_service=MemoryPolicyService(self.directory.name),
            account=AccountContext("serendipity-test"),
        )

    async def test_agent_exposes_librarian_search_and_typed_outputs(self) -> None:
        expected = proposal()
        model = TestModel(custom_output_args=expected, seed=0)
        agent = build_serendipity_agent(model)
        active_task = task(
            allowed_sources=("authorised_memory", "book_corpus")
        )

        deps = self.deps(active_task)
        for evidence_id, chapter in (("chapter-4", 4), ("chapter-5", 5)):
            deps.evidence[evidence_id] = BookConnectionEvidence(
                evidence_id=evidence_id,
                source_title="Alice's Adventures in Wonderland",
                work_id="pg11",
                book_version_id="pg11-v1",
                chapter=chapter,
                location=f"Chapter {chapter}",
                source_sha256="a" * 64,
                source_lines=(chapter, chapter),
                excerpt="Alice's changes make identity feel unstable.",
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
            ("web_search", "get_page"),
            tuple(trace.tool for trace in deps.searches),
        )
        self.assertEqual("identity change", deps.searches[0].request["query"])
        self.assertEqual(url, deps.searches[1].request["url"])
        self.assertIn("complete public page", deps.evidence[url].excerpt)

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

    def test_private_memory_wording_is_not_safe_for_an_exa_query(self) -> None:
        active_task = task(allowed_sources=("web",))
        deps = self.deps(active_task)
        deps.memory_service.save_explicit(
            deps.account,
            text="I hide unfinished work when I fear disappointing my team.",
            source_event_id="private-memory-test",
        )

        self.assertTrue(
            _query_copies_private_memory(
                "music about how I hide unfinished work when I fear disappointing my team",
                deps,
            )
        )


if __name__ == "__main__":
    unittest.main()
