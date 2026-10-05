"""Replay of issue #93: a revision retry may not bring back the sentences the review flagged."""

import json
import unittest

from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend.contracts import ContextResolution, MuseDraftInput, MuseTurn, TurnPolicy
from provenance_fixtures import review_with_audits
from src.linger.agents.muse.agent import build_muse_agent
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.inspection_context import begin_connection_inspection, reset_connection_inspection
from src.linger.orchestration.reflection import reflection_reply
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence

NECK = "Alice’s neck has grown so long that her head rises above the trees."
EGGS = "The Pigeon has guarded her eggs from serpents for three weeks, so she attacks Alice on sight."
HABIT = "Pigeons in the story always distrust strangers."
ASK = "What do you make of Alice’s answer?"
MERGED = f"{NECK[:-1]}, so the Pigeon attacks her on sight."
REPAIR = "The Pigeon says she has guarded her eggs from serpents for three weeks."
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def record(evidence_id: str, lines: tuple[int, int], text: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id, work_id="pg11", book_version_id="pg11-v01b38ea4",
        chapter_id="pg11-v01b38ea4-ch05", chapter_number=5,
        location=f"Chapter 5 — Advice from a Caterpillar, source lines {lines[0]}-{lines[1]}",
        source_sha256="a" * 64, source_lines=lines, text=text,
    )


NECK_RECORD = record("pg11-v01b38ea4-ch05-ln0100-0101", (100, 101),
                     "her neck had grown so long that her head rose high above the trees")
PIGEON_RECORD = record("pg11-v01b38ea4-ch05-ln0110-0112", (110, 112),
                       "“I’ve been guarding my eggs from the serpents these three weeks,” said the Pigeon.")


def book_use(evidence: EvidenceRecord, *claims: str) -> dict:
    return {"source_kind": "book_corpus", "evidence_id": evidence.evidence_id,
            "source_location": evidence.location, "supported_claims": list(claims)}


def muse_output(info: AgentInfo, reply: str, *uses: dict) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "reply": reply, "evidence_uses": list(uses), "memory": NO_MEMORY,
    })])


DRAFT = (f"{NECK} {EGGS} {HABIT} {ASK}", book_use(NECK_RECORD, NECK), book_use(PIGEON_RECORD, EGGS))
REVISION_ATTEMPTS = (
    (f"{MERGED} {ASK}", book_use(NECK_RECORD, MERGED), book_use(PIGEON_RECORD, MERGED)),
    DRAFT,
    (f"{NECK} {REPAIR} {ASK}", book_use(NECK_RECORD, NECK), book_use(PIGEON_RECORD, REPAIR)),
)


def user_prompts(messages) -> list[dict]:
    return [json.loads(part.content) for message in messages for part in message.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)]


def retry_errors(messages) -> list[list[dict]]:
    return [json.loads(part.content)["errors"] for message in messages for part in message.parts
            if isinstance(part, RetryPromptPart)]


def finding(quote: str) -> dict:
    return {
        "code": "unsupported_claim", "applies_to": "response",
        "location": {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": quote},
        "explanation": "The passage does not establish this.",
    }


class RevisionRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._evidence = set_turn_evidence((NECK_RECORD, PIGEON_RECORD))
        self._connection = begin_connection_inspection()

    async def asyncTearDown(self) -> None:
        reset_connection_inspection(self._connection)
        reset_turn_evidence(self._evidence)

    async def test_restored_flagged_sentences_are_retried_until_a_narrow_repair(self) -> None:
        retries_seen: list[list[dict]] = []

        def muse(messages, info):
            if user_prompts(messages)[-1]["mode"] == "draft":
                return muse_output(info, *DRAFT)
            retries_seen[:] = retry_errors(messages)
            return muse_output(info, *REVISION_ATTEMPTS[len(retries_seen)])

        def provenance(messages, info):
            payload = next(prompt for prompt in user_prompts(messages) if "candidate" in prompt)
            if payload["previous_response_review"] is None:
                fields = {"response_decision": "revise", "findings": [finding(EGGS), finding(HABIT)]}
            else:
                fields = {"response_decision": "pass", "finding_resolutions": [
                    {"finding_index": index, "status": "resolved", "explanation": "The claim is gone."}
                    for index in (0, 1)
                ]}
            review = review_with_audits(payload, {
                "findings": [], "emotional_boundary_decision": "not_required",
                "capture_decision": "no_candidate", **fields,
            }).model_dump(mode="json")
            # The flagged mapped claim stays unsupported, so a review of it cannot pass.
            claims = {group["group_index"]: group["claim"] for group in payload["claim_support_groups"]}
            for audit in review["claim_audit"]:
                audit["supported"] = claims[audit["group_index"]] != EGGS
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, review)])

        prompt = MuseDraftInput(
            mode="draft",
            muse_turn=MuseTurn(
                turn_id="issue-93", user_message="Why does the Pigeon call Alice a serpent?",
                reading_context=None, policy=TurnPolicy(allow_retrieval=False, allow_connection=False),
            ),
            context_resolution=ContextResolution(status="unknown", explanation="Test context."),
        ).model_dump_json()
        release = await reflection_reply(
            prompt, [],
            muse=build_muse_agent(FunctionModel(muse)),
            provenance=build_provenance_agent(FunctionModel(provenance)),
            previously_released_evidence_ids=frozenset({NECK_RECORD.evidence_id, PIGEON_RECORD.evidence_id}),
        )

        self.assertEqual([NECK], [error.get("draft_sentence") for error in retries_seen[0]])
        self.assertEqual(2, len(retries_seen), "the restored draft was accepted")
        self.assertEqual({EGGS, HABIT}, {error.get("draft_sentence") for error in retries_seen[1]})
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual(REVISION_ATTEMPTS[2][0], release.reply)
        self.assertIn(NECK, release.reply)
        self.assertIn(REPAIR, release.reply)
        self.assertNotIn(EGGS, release.reply)
        self.assertNotIn(HABIT, release.reply)


if __name__ == "__main__":
    unittest.main()
