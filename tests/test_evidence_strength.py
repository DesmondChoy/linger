"""Tests for Librarian's typed set-level strength decision."""

import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BookEvidenceAssessment,
    BookRequestPart,
    BookRequestPlan,
    EvidenceStrengthDecision,
    LibrarianBookRequestInput,
    LibrarianEvidenceStrengthInput,
    RequestedBookSupport,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.evidence_strength import (
    EVIDENCE_ASSESSMENT_REQUEST_LIMIT, assess_book_evidence, judge_evidence_strength,
)


class EvidenceStrengthDecisionTests(unittest.TestCase):
    def test_sufficient_and_weak_require_evidence(self) -> None:
        for strength in ("sufficient", "weak"):
            with self.subTest(strength=strength), self.assertRaises(ValidationError):
                EvidenceStrengthDecision(
                    evidence_strength=strength,
                    strength_reason="reason",
                    limitations=("partial",) if strength == "weak" else (),
                )

    def test_none_cannot_claim_relevant_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceStrengthDecision(
                evidence_strength="none",
                strength_reason="not useful",
                relevant_evidence_ids=("e1",),
            )


class EvidenceStrengthOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def evidence(self) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id="pg11-v01b38ea4-ch05-ln0964-0964",
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            chapter_id="pg11-v01b38ea4-ch05",
            chapter_number=5,
            location="Chapter 5, source line 964",
            source_sha256="01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
            source_lines=(964, 964),
            text="“Who are _you?_” said the Caterpillar.",
        )

    async def test_judge_receives_reader_query_before_plan_and_exact_evidence(self) -> None:
        query = "Who questions Alice's identity?"
        plan = BookRequestPlan(parts=(BookRequestPart(context_spans=(), purpose="answer", reader_spans=(query,)),))
        agent = AsyncMock()
        agent.run.side_effect = [SimpleNamespace(output=plan), SimpleNamespace(
            output=BookEvidenceAssessment(
                evidence_strength="sufficient",
                strength_reason="The passage directly supports the query.",
                relevant_evidence_ids=(self.evidence().evidence_id,),
                support=(RequestedBookSupport(
                    evidence_id=self.evidence().evidence_id, part_index=0,
                    necessary_support="The passage names the character asking the question.",
                ),),
            )
        )]
        module = ModuleType("src.linger.agents.librarian.agent")
        module.librarian_agent = agent

        with patch.dict(sys.modules, {module.__name__: module}):
            decision = await judge_evidence_strength(
                query, (self.evidence(),)
            )

        self.assertEqual("sufficient", decision.evidence_strength)
        self.assertEqual(2, agent.run.await_count)
        request_payload = json.loads(agent.run.await_args_list[0].args[0])
        self.assertEqual({"current_line": query, "prior_reader_statements": [], "search_target": "book_evidence"}, request_payload)
        payload = json.loads(agent.run.await_args_list[1].args[0])
        self.assertEqual({"original_request", "request", "evidence", "max_evidence_records"}, set(payload))
        self.assertEqual(request_payload, payload["original_request"])
        self.assertEqual(plan.model_dump(mode="json"), payload["request"])
        self.assertEqual(self.evidence().evidence_id, payload["evidence"][0]["evidence_id"])
        self.assertEqual(self.evidence().model_dump(mode="json"), payload["evidence"][0])

    async def test_judge_rejects_invented_evidence_ids(self) -> None:
        agent = AsyncMock()
        agent.run.side_effect = [SimpleNamespace(output=BookRequestPlan(parts=(
            BookRequestPart(context_spans=(), purpose="answer", reader_spans=("query",)),
        ))), SimpleNamespace(
            output=BookEvidenceAssessment(
                evidence_strength="sufficient",
                strength_reason="Invented support.",
                relevant_evidence_ids=("not-in-the-input",),
                support=(RequestedBookSupport(
                    evidence_id="not-in-the-input", part_index=0,
                    necessary_support="Claimed support from an unavailable passage.",
                ),),
            )
        )]
        module = ModuleType("src.linger.agents.librarian.agent")
        module.librarian_agent = agent

        with patch.dict(sys.modules, {module.__name__: module}):
            with self.assertRaisesRegex(ValueError, "unknown evidence ID"):
                await judge_evidence_strength("query", (self.evidence(),))
        self.assertEqual(2, agent.run.await_count)

    async def test_assessment_repairs_missing_support_and_invented_span_together(self) -> None:
        question = "Who questions Alice? What does Alice say?"
        plan = BookRequestPlan(parts=(BookRequestPart(
            context_spans=(), purpose="answer", reader_spans=("Who questions Alice?",),
        ),))
        questioner = self.evidence()
        answer = questioner.model_copy(update={"evidence_id": "alice-answer", "text": "Alice says she is confused."})
        attempts = []

        def model(messages, info):
            retries = [part.content for part in messages[-1].parts if isinstance(part, RetryPromptPart)]
            if attempts:
                feedback = json.loads(retries[0])
                self.assertTrue(any(error["path"] == "additional_parts[0].reader_spans[0]"
                                    for error in feedback["errors"]))
                self.assertTrue(any(error.get("missing_part_indices") == [1]
                                    for error in feedback["errors"]))
            repaired = bool(attempts)
            attempts.append(repaired)
            output = {
                "evidence_strength": "sufficient", "strength_reason": "Both requested answers are present.",
                "relevant_evidence_ids": [questioner.evidence_id, *([answer.evidence_id] if repaired else [])],
                "additional_parts": [{"context_spans": [], "purpose": "answer",
                                      "reader_spans": ["What does Alice say?" if repaired else "Who answers him?"]}],
                "support": [{"evidence_id": questioner.evidence_id, "part_index": 0,
                             "necessary_support": "The Caterpillar asks the question."}],
            }
            if repaired:
                output["support"].append({"evidence_id": answer.evidence_id, "part_index": 1,
                                          "necessary_support": "Alice answers that she is confused."})
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

        decision = await assess_book_evidence(
            plan, (questioner, answer), original_request=LibrarianBookRequestInput(current_line=question),
            agent=build_librarian_agent(FunctionModel(model)),
        )

        self.assertEqual([False, True], attempts)
        self.assertEqual("sufficient", decision.evidence_strength)
        self.assertEqual((questioner.evidence_id, answer.evidence_id), decision.relevant_evidence_ids)

    async def test_weak_assessment_can_leave_a_requested_part_unsupported(self) -> None:
        plan = BookRequestPlan(parts=tuple(BookRequestPart(
            context_spans=(), purpose="answer", reader_spans=(span,),
        ) for span in ("Who questions Alice?", "What does Alice say?")))
        output = BookEvidenceAssessment(
            evidence_strength="weak", strength_reason="Only the questioner is identified.",
            relevant_evidence_ids=(self.evidence().evidence_id,), limitations=("Alice's answer is absent.",),
            support=(RequestedBookSupport(evidence_id=self.evidence().evidence_id, part_index=0,
                                          necessary_support="The Caterpillar asks the question."),),
        )
        attempts = []

        def model(messages, info):
            attempts.append(messages)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

        result = await assess_book_evidence(
            plan, (self.evidence(),), original_request=LibrarianBookRequestInput(
                current_line="Who questions Alice? What does Alice say?",
            ), agent=build_librarian_agent(FunctionModel(model)),
        )
        self.assertEqual(1, len(attempts))
        self.assertEqual("weak", result.evidence_strength)
        self.assertEqual(output.limitations, result.limitations)
        self.assertEqual(output.relevant_evidence_ids, result.relevant_evidence_ids)

    async def test_unknown_requested_part_exhausts_only_the_existing_retry_budget(self) -> None:
        plan = BookRequestPlan(parts=(BookRequestPart(
            context_spans=(), purpose="answer", reader_spans=("Who questions Alice?",),
        ),))
        output = BookEvidenceAssessment(
            evidence_strength="sufficient", strength_reason="The questioner is identified.",
            relevant_evidence_ids=(self.evidence().evidence_id,),
            support=(RequestedBookSupport(evidence_id=self.evidence().evidence_id, part_index=9,
                                          necessary_support="The Caterpillar asks the question."),),
        )
        attempts = []

        def model(messages, info):
            if attempts:
                feedback = json.loads(next(part.content for part in messages[-1].parts
                                           if isinstance(part, RetryPromptPart)))
                self.assertTrue(any(error["path"] == "support[0].part_index" for error in feedback["errors"]))
                self.assertTrue(any(error.get("missing_part_indices") == [0] for error in feedback["errors"]))
            attempts.append(messages)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

        with self.assertRaises(UnexpectedModelBehavior):
            await assess_book_evidence(
                plan, (self.evidence(),), original_request=LibrarianBookRequestInput(current_line="Who questions Alice?"),
                agent=build_librarian_agent(FunctionModel(model)),
            )
        self.assertEqual(EVIDENCE_ASSESSMENT_REQUEST_LIMIT, len(attempts))

    async def test_numeric_string_part_indices_receive_typed_validation(self) -> None:
        plan = BookRequestPlan(parts=(BookRequestPart(
            context_spans=(), purpose="answer", reader_spans=("Who questions Alice?",),
        ),))
        for strength, initial_index, expected_attempts in (
            ("weak", "9", 2), ("weak", "0", 1),
            ("sufficient", "9", 2), ("sufficient", "0", 1),
        ):
            with self.subTest(strength=strength, initial_index=initial_index):
                attempts = []

                def model(messages, info):
                    if attempts:
                        feedback = json.loads(next(part.content for part in messages[-1].parts
                                                   if isinstance(part, RetryPromptPart)))
                        self.assertTrue(any(error["path"] == "support[0].part_index" and error["value"] == 9
                                            for error in feedback["errors"]))
                    part_index = 0 if attempts else initial_index
                    attempts.append(part_index)
                    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                        "evidence_strength": strength, "strength_reason": "The questioner is named, with little context.",
                        "limitations": ["Only the question is supplied."],
                        "relevant_evidence_ids": [self.evidence().evidence_id],
                        "support": [{"evidence_id": self.evidence().evidence_id, "part_index": part_index,
                                     "necessary_support": "The Caterpillar asks the question."}],
                    })])

                result = await assess_book_evidence(
                    plan, (self.evidence(),), original_request=LibrarianBookRequestInput(current_line="Who questions Alice?"),
                    agent=build_librarian_agent(FunctionModel(model)),
                )
                self.assertEqual(expected_attempts, len(attempts))
                self.assertEqual(strength, result.evidence_strength)
                self.assertEqual(("Only the question is supplied.",), result.limitations)

    async def test_application_and_captured_replay_recheck_domain_faults(self) -> None:
        from evals.synthetic_journals.captured_stage_tasks import _validate_application_result

        first = self.evidence()
        second = first.model_copy(update={"evidence_id": "alice-answer", "text": "Alice answers."})
        task = LibrarianEvidenceStrengthInput(
            original_request=LibrarianBookRequestInput(current_line="Who questions Alice? What does Alice say?"),
            request=BookRequestPlan(parts=(BookRequestPart(
                context_spans=(), purpose="answer", reader_spans=("Who questions Alice?",),
            ),)), evidence=(first, second), max_evidence_records=1,
        )
        valid = BookEvidenceAssessment(
            evidence_strength="sufficient", strength_reason="The questioner is identified.",
            relevant_evidence_ids=(first.evidence_id,), support=(RequestedBookSupport(
                evidence_id=first.evidence_id, part_index=0, necessary_support="The Caterpillar asks the question.",
            ),),
        )
        additions = (BookRequestPart(context_spans=(), purpose="answer", reader_spans=("What does Alice say?",)),)
        faults = {
            "span": valid.model_copy(update={"additional_parts": (
                additions[0].model_copy(update={"reader_spans": ("Invented question",)}),
            )}),
            "coverage": valid.model_copy(update={"additional_parts": additions}),
            "part": valid.model_copy(update={"support": (valid.support[0].model_copy(update={"part_index": 9}),)}),
            "unknown_id": valid.model_copy(update={"relevant_evidence_ids": ("unknown",), "support": (
                valid.support[0].model_copy(update={"evidence_id": "unknown"}),
            )}),
            "duplicate": valid.model_copy(update={"relevant_evidence_ids": (first.evidence_id, first.evidence_id)}),
            "budget": valid.model_copy(update={"relevant_evidence_ids": (first.evidence_id, second.evidence_id),
                                                "support": (valid.support[0], valid.support[0].model_copy(
                                                    update={"evidence_id": second.evidence_id},
                                                ))}),
        }
        for fault, output in faults.items():
            with self.subTest(fault=fault):
                agent = AsyncMock()
                agent.run.return_value = SimpleNamespace(output=output)
                with self.assertRaises(ValueError) as application_error:
                    await assess_book_evidence(
                        task.request, task.evidence, original_request=task.original_request,
                        max_evidence_records=task.max_evidence_records, agent=agent,
                    )
                with self.assertRaises(ValueError) as replay_error:
                    _validate_application_result(task, output)
                self.assertEqual(str(application_error.exception), str(replay_error.exception))
                self.assertTrue(json.loads(str(application_error.exception))["errors"])

    def test_weak_requires_an_explicit_limitation(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceStrengthDecision(
                evidence_strength="weak",
                strength_reason="partial",
                relevant_evidence_ids=("e1",),
            )


if __name__ == "__main__":
    unittest.main()
