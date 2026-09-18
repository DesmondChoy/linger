"""Tests for Librarian's typed set-level strength decision."""

import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from src.linger.agents.librarian.models import (
    BookEvidenceAssessment,
    BookRequestPart,
    BookRequestPlan,
    EvidenceStrengthDecision,
    RequestedBookSupport,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.evidence_strength import judge_evidence_strength


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

    def test_weak_requires_an_explicit_limitation(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceStrengthDecision(
                evidence_strength="weak",
                strength_reason="partial",
                relevant_evidence_ids=("e1",),
            )


if __name__ == "__main__":
    unittest.main()
