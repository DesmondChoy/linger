"""Tests for the Pydantic AI Sculptor agent and curation boundary."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from evals.sculptor.harness import (
    SculptorEvalCase,
    grade_sculptor_response,
    load_sculptor_eval_cases,
)
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CuratableMemory,
    CurationProposal,
    DerivedSummary,
    DuplicateLink,
    NoCurationProposal,
    TopicGroup,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.agents.sculptor.agent import build_sculptor_agent
    from src.linger.orchestration.curation import (
        InvalidCurationProposal,
        propose_curation,
    )


def _batch(case: SculptorEvalCase) -> AccountScopedMemories:
    return AccountScopedMemories(
        account_scope=case.input.account_scope,
        memories=tuple(
            CuratableMemory(memory_id=memory.memory_id, text=memory.text)
            for memory in case.input.memories
        ),
    )


def _mocked_response(
    case: SculptorEvalCase,
) -> CurationProposal | NoCurationProposal:
    expected = case.expected
    if expected.kind == "no_curation_proposal":
        return NoCurationProposal(
            kind="no_curation_proposal",
            reason="The similar words describe unrelated people and contexts.",
        )

    action = expected.action
    if action.action == "link_duplicates":
        response_action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=action.source_memory_ids,
        )
    elif action.action == "update_derived_summary":
        response_action = DerivedSummary(
            action="update_derived_summary",
            source_memory_ids=action.source_memory_ids,
            summary=(
                "Walks after work, sometimes in rain and without headphones, "
                "can help the user feel calmer and mentally clearer."
            ),
        )
    else:
        response_action = TopicGroup(
            action="assign_topic_group",
            source_memory_ids=action.source_memory_ids,
            topic_label="Restorative transitions",
        )
    return CurationProposal(kind="curation_proposal", action=response_action)


class SculptorAgentTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_sculptor_eval_cases()

    async def test_pydantic_agent_covers_the_five_baseline_behaviors(self) -> None:
        for case in self.cases:
            with self.subTest(behavior=case.primary_behavior):
                mocked_response = _mocked_response(case)
                model = TestModel(
                    custom_output_args=mocked_response,
                    seed=1 if isinstance(mocked_response, NoCurationProposal) else 0,
                )
                agent = build_sculptor_agent(model)

                response = await propose_curation(_batch(case), agent=agent)

                grade = grade_sculptor_response(case, response)
                self.assertTrue(grade.hard_pass, grade.failures)
                request_parameters = model.last_model_request_parameters
                self.assertIsNotNone(request_parameters)
                assert request_parameters is not None
                self.assertEqual([], request_parameters.function_tools)
                self.assertEqual(2, len(request_parameters.output_tools))

    async def test_sends_only_memory_ids_and_text_to_the_model(self) -> None:
        case = self.cases[0]
        agent = AsyncMock()
        agent.run.return_value = SimpleNamespace(
            output=NoCurationProposal(
                kind="no_curation_proposal",
                reason="No supported curation action.",
            )
        )

        await propose_curation(_batch(case), agent=agent)

        payload = json.loads(agent.run.await_args.args[0])
        self.assertEqual({"memories"}, set(payload))
        self.assertTrue(payload["memories"])
        self.assertTrue(
            all(set(memory) == {"memory_id", "text"} for memory in payload["memories"])
        )
        self.assertNotIn(case.input.account_scope, agent.run.await_args.args[0])

    async def test_rejects_malformed_or_storage_mutating_output(self) -> None:
        case = self.cases[0]
        agent = AsyncMock()
        agent.run.return_value = SimpleNamespace(
            output={
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": [
                        case.input.memories[0].memory_id,
                        case.input.memories[1].memory_id,
                    ],
                    "deleted_memory_ids": [case.input.memories[1].memory_id],
                },
            }
        )

        with self.assertRaisesRegex(InvalidCurationProposal, "malformed output"):
            await propose_curation(_batch(case), agent=agent)

    async def test_rejects_sources_outside_the_account_scoped_batch(self) -> None:
        case = self.cases[0]
        agent = AsyncMock()
        agent.run.return_value = SimpleNamespace(
            output=CurationProposal(
                kind="curation_proposal",
                action=DuplicateLink(
                    action="link_duplicates",
                    source_memory_ids=(
                        case.input.memories[0].memory_id,
                        "memory-from-another-account",
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(InvalidCurationProposal, "unknown memories"):
            await propose_curation(_batch(case), agent=agent)

    def test_input_rejects_duplicate_memory_ids(self) -> None:
        with self.assertRaisesRegex(ValidationError, "memory IDs must be unique"):
            AccountScopedMemories(
                account_scope="account-a",
                memories=(
                    CuratableMemory(memory_id="memory-1", text="First"),
                    CuratableMemory(memory_id="memory-1", text="Second"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
