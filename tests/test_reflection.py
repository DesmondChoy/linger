"""Tests for the mandatory Muse-to-Provenance release gate."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
from pydantic_ai.messages import ToolReturnPart

from apps.backend.contracts import (
    ContextResolution,
    EvidenceItem,
    MuseDraftInput,
    MuseRevisionReview,
    MuseTurn,
    TurnPolicy,
)
from src.linger.agents.muse.models import (
    EvidenceUse,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionExplorationResult,
    ConnectionProposal,
    WebConnectionEvidence,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.turn import ReleaseScope
from src.linger.orchestration.reflection import (
    SAFE_DECLINE,
    reflection_reply as production_reflection_reply,
)
from src.linger.orchestration.turn_context import (
    add_turn_evidence,
    reset_turn_evidence,
    set_turn_evidence,
)

EVIDENCE_ID = "pg11-v01b38ea4-ch02-ln0010-0011"
LOCATION = "Chapter 2 — The Pool of Tears, source lines 10-11"
QUOTE = "Who are you?"
RELEASE_SCOPE = ReleaseScope(
    work_id="pg11",
    book_version_id="pg11-v01b38ea4",
    chapter_max=3,
)


def muse_input(message: str) -> str:
    return MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id="test-turn",
            user_message=message,
            reading_context=None,
            policy=TurnPolicy(
                spoiler_ceiling=None,
                allow_retrieval=False,
                allow_connection=False,
                allow_memory_capture=False,
            ),
        ),
        context_resolution=ContextResolution(
            status="unknown",
            explanation="No reading context.",
        ),
    ).model_dump_json()


async def reflection_reply(message: str, *args, **kwargs):
    """Keep tests concise while exercising the strict production envelope."""
    prompt = message if message.lstrip().startswith("{") else muse_input(message)
    kwargs.setdefault("capture_source_text", message)
    return await production_reflection_reply(prompt, *args, **kwargs)


def candidate(
    reply: str,
    *,
    evidence_id: str | None = None,
    location: str = LOCATION,
    exact_quote: str | None = None,
) -> MuseCandidate:
    uses = ()
    if evidence_id is not None:
        uses = (
            EvidenceUse(
                source_kind="book_corpus",
                evidence_id=evidence_id,
                source_location=location,
                exact_quote=exact_quote,
            ),
        )
    return MuseCandidate(
        reply=reply,
        evidence_uses=uses,
        memory=NoMemoryCandidate(
            kind="no_memory_candidate",
            reason_code="transient_or_low_signal",
        ),
    )


def result(output: object, *tool_returns: ToolReturnPart) -> SimpleNamespace:
    if isinstance(output, str):
        output = candidate(output)
    messages = [SimpleNamespace(parts=list(tool_returns))]
    return SimpleNamespace(output=output, new_messages=lambda: messages)


def evidence_record(
    *,
    evidence_id: str = EVIDENCE_ID,
    work_id: str = "pg11",
    book_version_id: str = "pg11-v01b38ea4",
    chapter_number: int = 2,
    location: str = LOCATION,
    text: str = f'Alice asked, "{QUOTE}" before answering.',
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "work_id": work_id,
        "book_version_id": book_version_id,
        "chapter_id": "pg11-v01b38ea4-ch02",
        "chapter_number": chapter_number,
        "location": location,
        "source_sha256": "a" * 64,
        "source_lines": [10, 11],
        "text": text,
    }


def retrieval_result(
    *,
    evidence: list[dict[str, object]] | None = None,
    work_id: str = "pg11",
    book_version_id: str = "pg11-v01b38ea4",
    chapter_max: int = 3,
    strength: str = "sufficient",
) -> dict[str, object]:
    records = [evidence_record()] if evidence is None else evidence
    return {
        "kind": "result",
        "request_id": "libreq-test",
        "outcome": "evidence_found" if records else "no_evidence",
        "evidence_strength": strength if records else "none",
        "strength_reason": "The returned text answers the question." if records else "No support found.",
        "searched_scope": {
            "work_id": work_id,
            "book_version_id": book_version_id,
            "max_chapter_inclusive": chapter_max,
        },
        "evidence": records,
        "limitations": [],
    }


def canonical_record(**updates: object) -> EvidenceRecord:
    return EvidenceRecord.model_validate(evidence_record(**updates))


def connection_result(*, web: bool = False) -> ConnectionExplorationResult:
    evidence_id = "https://example.com/source" if web else EVIDENCE_ID
    shortlist = (
        ConnectionCandidate(
            candidate_id="candidate-identity",
            tentative_claim="Alice's question of identity echoes the reader's cue.",
            evidence_ids=(evidence_id,),
            shared_structure="Both moments make identity uncertain.",
            meaningful_difference=(
                "The scene asks directly while the cue reflects backward."
            ),
            interpretation="The repetition may make identity feel unstable.",
            rubric=CandidateRubric(
                cue_fit="direct",
                reflective_value="high",
                safety="clear",
            ),
            comparison_note="This is the closest supported bridge.",
        ),
        ConnectionCandidate(
            candidate_id="candidate-authority",
            tentative_claim="The exchange also makes authority feel unsettled.",
            evidence_ids=(evidence_id,),
            shared_structure="Both moments involve an uncertain answer.",
            meaningful_difference=(
                "This reading emphasizes authority rather than identity."
            ),
            interpretation="The question may also shift who controls the exchange.",
            rubric=CandidateRubric(
                cue_fit="partial",
                reflective_value="medium",
                safety="clear",
            ),
            comparison_note="This is plausible but less direct.",
        ),
    )
    proposal = ConnectionProposal(
        shortlist=shortlist,
        selected_candidate_id="candidate-identity",
        uncertainty="medium",
        presentation="ask_before_showing",
        suggested_follow_up="Does that echo change how the question feels?",
        policy_flags=("contains_web_claim",) if web else (),
    )
    evidence = (
        (
            WebConnectionEvidence(
                evidence_id=evidence_id,
                title="An external source",
                excerpt="A public-web connection.",
            ),
        )
        if web
        else (
            EvidenceItem(
                evidence_id=EVIDENCE_ID,
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_id="pg11-v01b38ea4-ch02",
                source_title="Alice's Adventures in Wonderland",
                location=LOCATION,
                chapter=2,
                source_sha256="a" * 64,
                source_lines=(10, 11),
                excerpt=f'Alice asked, "{QUOTE}" before answering.',
                relevance=1.0,
            ),
        )
    )
    return ConnectionExplorationResult(decision=proposal, evidence=evidence)


def review(
    decision: str,
    *,
    capture: str = "no_candidate",
    finding: str = "",
) -> ProvenanceReview:
    """Build a review, supplying the finding a non-pass decision requires."""
    findings = []
    if decision != "pass":
        findings.append(
            RiskFinding(
                code="unsupported_claim",
                applies_to="response",
                location={
                    "kind": "structural",
                    "source_field": "candidate.response",
                    "path": "",
                },
                explanation=finding or "The evidence does not support this.",
            )
        )
    if capture == "reject_capture":
        findings.append(
            RiskFinding(
                code="unsupported_claim",
                applies_to="capture",
                location={
                    "kind": "structural",
                    "source_field": "candidate.memory",
                    "path": "",
                },
                explanation="The memory nomination is not safe to capture.",
            )
        )
    return ProvenanceReview(
        findings=tuple(findings),
        response_decision=decision,
        emotional_boundary_decision="not_required",
        capture_decision=capture,
    )


class ReflectionReplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._evidence_token = set_turn_evidence(())

    async def asyncTearDown(self) -> None:
        reset_turn_evidence(self._evidence_token)

    @staticmethod
    def register_evidence(**updates: object) -> EvidenceRecord:
        record = canonical_record(**updates)
        add_turn_evidence((record,))
        return record

    async def test_rejects_undiscriminated_muse_input_before_model_invocation(self) -> None:
        muse = AsyncMock()
        provenance = AsyncMock()

        release = await production_reflection_reply(
            json.dumps({"muse_turn": {"user_message": "Hello"}}),
            [],
            muse=muse,
            provenance=provenance,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("muse_draft", release.failure_stage)
        muse.run.assert_not_awaited()
        provenance.run.assert_not_awaited()

    async def test_rejects_unknown_nested_muse_authority_before_model_invocation(
        self,
    ) -> None:
        muse = AsyncMock()
        provenance = AsyncMock()
        payload = json.loads(muse_input("Hello"))
        payload["muse_turn"]["policy"]["unexpected_grant"] = True

        release = await production_reflection_reply(
            json.dumps(payload),
            [],
            muse=muse,
            provenance=provenance,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("muse_draft", release.failure_stage)
        muse.run.assert_not_awaited()
        provenance.run.assert_not_awaited()

    def test_revision_contract_rejects_capture_findings(self) -> None:
        with self.assertRaises(ValidationError):
            MuseRevisionReview(
                findings=(
                    RiskFinding(
                        code="unsupported_claim",
                        applies_to="capture",
                        location={
                            "kind": "structural",
                            "source_field": "candidate.memory",
                            "path": "",
                        },
                        explanation="Capture-only fault.",
                    ),
                )
            )

    async def test_releases_only_after_pass(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Approved reply")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            review_context={
                "policy_constraints": {
                    "spoiler_ceiling": 3,
                    "allow_retrieval": True,
                    "allow_connection": False,
                    "allow_memory_capture": False,
                },
                "reading_context": None,
            },
        )

        self.assertEqual("Approved reply", release.reply)
        self.assertEqual("muse_candidate", release.release_source)
        self.assertEqual(("pass",), release.provenance_verdicts)
        provenance.run.assert_awaited_once()
        review_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual(3, review_payload["context"]["policy"]["spoiler_ceiling"])
        self.assertIsNone(review_payload["context"]["reading_context"])
        self.assertEqual([], review_payload["candidate"]["evidence_uses"])
        self.assertNotIn("cited_evidence", review_payload)
        self.assertNotIn("connection_proposal", review_payload)

    async def test_provenance_receives_untrusted_tool_outcomes_once(self) -> None:
        self.register_evidence()
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate(
                f'The text asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            ToolReturnPart(
                "librarian_search",
                retrieval_result(),
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        review_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual(
            "librarian_search",
            review_payload["untrusted_tool_outcomes"][0]["tool_name"],
        )
        self.assertEqual(
            EVIDENCE_ID,
            review_payload["candidate"]["evidence_uses"][0]["evidence_id"],
        )
        self.assertEqual(
            EVIDENCE_ID,
            review_payload["canonical_book_evidence"][0]["evidence_id"],
        )

    async def test_direct_librarian_grounding_is_exposed_for_inspection(self) -> None:
        from pydantic_ai.messages import ToolCallPart

        self.register_evidence()
        call = ToolCallPart(
            "librarian_search",
            {"query": "the pool of tears", "work_id": "pg11"},
            "call-1",
        )
        tool_return = ToolReturnPart("librarian_search", retrieval_result(), "call-1")
        muse = AsyncMock()
        muse.run.return_value = SimpleNamespace(
            output=candidate(
                f'The text asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            new_messages=lambda: [SimpleNamespace(parts=[call, tool_return])],
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(1, len(release.librarian_grounding_calls))
        grounding_call = release.librarian_grounding_calls[0]
        self.assertEqual(
            "the pool of tears", grounding_call["request"]["query"]
        )
        self.assertEqual("success", grounding_call["outcome"])
        self.assertEqual(
            "evidence_found", grounding_call["response"]["outcome"]
        )

    async def test_web_serendipity_proposal_fails_closed_after_semantic_pass(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            "A web-backed connection that is not yet a releasable citation.",
            ToolReturnPart(
                "serendipity_explore",
                connection_result(web=True),
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Find me an outside connection",
            [],
            muse=muse,
            provenance=provenance,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_book_serendipity_proposal_can_authorize_release(self) -> None:
        self.register_evidence()
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate(
                "The identity question echoes the reader's cue.",
                evidence_id=EVIDENCE_ID,
            ),
            ToolReturnPart("serendipity_explore", connection_result()),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Find a connection",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual("muse_candidate", release.release_source)
        self.assertEqual((EVIDENCE_ID,), release.evidence_ids)

    async def test_serendipity_decline_can_be_relayed_after_semantic_pass(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            "I could not support a connection from the permitted sources.",
            ToolReturnPart(
                "serendipity_explore",
                {
                    "decision": {
                        "status": "decline",
                        "reason": "insufficient_evidence",
                        "safe_next_step": "Try a more specific cue.",
                    },
                    "evidence": [],
                },
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Find a connection",
            [],
            muse=muse,
            provenance=provenance,
        )

        self.assertEqual(
            "I could not support a connection from the permitted sources.",
            release.reply,
        )
        self.assertEqual("muse_candidate", release.release_source)

    async def test_every_librarian_branch_reaches_provenance_unchanged(self) -> None:
        branches = (
            {
                "kind": "clarification",
                "request_id": "libreq-clarify",
                "clarification_id": "clarify-test",
                "reason_code": "current_chapter_state_ambiguous",
                "question": "Have you completed Chapter 5?",
                "expected_answer": {
                    "type": "one_of",
                    "values": ["completed", "started"],
                },
            },
            retrieval_result(),
            retrieval_result(strength="weak"),
            retrieval_result(evidence=[]),
            {
                "kind": "failure",
                "request_id": "libreq-failure",
                "error_code": "retrieval_unavailable",
                "retryable": True,
            },
        )

        for branch in branches:
            with self.subTest(branch=branch):
                if branch.get("kind") == "result":
                    add_turn_evidence(
                        EvidenceRecord.model_validate(record)
                        for record in branch["evidence"]
                    )
                muse = AsyncMock()
                muse.run.return_value = result(
                    "Candidate handled the Librarian response.",
                    ToolReturnPart("librarian_search", branch),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(
                    review("pass")
                )

                await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                review_payload = json.loads(provenance.run.await_args.args[0])
                self.assertEqual(
                    branch,
                    review_payload["untrusted_tool_outcomes"][0]["content"],
                )

    async def test_allows_one_reviewed_revision(self) -> None:
        muse = AsyncMock()
        draft = result("Draft")
        muse.run.side_effect = [draft, result("Revised reply")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Qualify the claim.")),
            result(review("pass")),
        ]

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual("Revised reply", release.reply)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual(1, release.revision_count)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)
        revision_payload = json.loads(muse.run.await_args_list[1].args[0])
        self.assertEqual("revision", revision_payload["mode"])
        finding = revision_payload["review"]["findings"][0]
        self.assertEqual("Qualify the claim.", finding["explanation"])
        self.assertEqual("response", finding["applies_to"])
        self.assertEqual("candidate.response", finding["location"]["source_field"])
        self.assertEqual(
            draft.new_messages(),
            muse.run.await_args_list[1].kwargs["message_history"],
        )
        self.assertEqual((("unsupported_claim",), ()), release.review_finding_codes)
        self.assertFalse(hasattr(release, "critiques"))

    async def test_revision_guidance_excludes_capture_findings(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Revised reply")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", capture="reject_capture")),
            result(review("pass")),
        ]

        await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        revision_payload = json.loads(muse.run.await_args_list[1].args[0])
        findings = revision_payload["review"]["findings"]
        self.assertEqual(1, len(findings))
        self.assertEqual("response", findings[0]["applies_to"])

    async def test_valid_book_quote_passes_deterministic_validation(self) -> None:
        self.register_evidence()
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate(
                f'Alice asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            ToolReturnPart("librarian_search", retrieval_result()),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual("muse_candidate", release.release_source)
        self.assertIsNone(release.failure_stage)

    async def test_unresolved_or_non_librarian_evidence_fails_closed(self) -> None:
        self.register_evidence()
        cases = (
            (ToolReturnPart("librarian_search", retrieval_result()), "unknown-evidence"),
            (
                ToolReturnPart(
                    "serendipity_explore",
                    {
                        "status": "proposal",
                        "tentative_claim": "A connection",
                        "evidence_ids": [EVIDENCE_ID],
                        "interpretation": "Tentative",
                        "uncertainty": "medium",
                        "suggested_follow_up": "What do you think?",
                    },
                ),
                EVIDENCE_ID,
            ),
        )
        for tool_return, evidence_id in cases:
            with self.subTest(tool=tool_return.tool_name):
                muse = AsyncMock()
                muse.run.return_value = result(
                    candidate("A supported thought.", evidence_id=evidence_id),
                    tool_return,
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_quote_and_location_mismatches_fail_closed(self) -> None:
        self.register_evidence()
        cases = (
            candidate(
                f'Alice asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                location="Chapter 99",
                exact_quote=QUOTE,
            ),
            candidate(
                'Alice asks, "Invented words"',
                evidence_id=EVIDENCE_ID,
                exact_quote="Invented words",
            ),
            candidate(
                "Alice asks a question.",
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
        )
        for invalid_candidate in cases:
            with self.subTest(candidate=invalid_candidate):
                muse = AsyncMock()
                muse.run.return_value = result(
                    invalid_candidate,
                    ToolReturnPart("librarian_search", retrieval_result()),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_work_revision_and_spoiler_mismatches_fail_closed(self) -> None:
        self.register_evidence()
        scopes = (
            RELEASE_SCOPE.model_copy(update={"work_id": "animal-farm"}),
            RELEASE_SCOPE.model_copy(update={"book_version_id": "pg11-other"}),
            RELEASE_SCOPE.model_copy(update={"chapter_max": 1}),
        )
        for scope in scopes:
            with self.subTest(scope=scope):
                muse = AsyncMock()
                muse.run.return_value = result(
                    candidate("A supported thought.", evidence_id=EVIDENCE_ID),
                    ToolReturnPart("librarian_search", retrieval_result()),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello", [], muse=muse, provenance=provenance, release_scope=scope
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_unsupported_candidate_source_fails_closed_before_review(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            {
                "reply": "Unsupported citation.",
                "evidence_uses": [
                    {
                        "source_kind": "web",
                        "evidence_id": "web-1",
                        "source_location": "https://example.com",
                        "exact_quote": None,
                    }
                ],
            }
        )
        provenance = AsyncMock()

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("muse_draft", release.failure_stage)
        provenance.run.assert_not_awaited()

    async def test_malformed_librarian_result_fails_closed_after_review(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            "Uncited reply.",
            ToolReturnPart(
                "librarian_search",
                {"kind": "result", "evidence": "not-a-valid-result"},
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_passed_revision_still_requires_deterministic_validation(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [
            result("Draft"),
            result(candidate("Still unsupported.", evidence_id="unknown-evidence")),
        ]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Add support.")),
            result(review("pass")),
        ]

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_evidence_from_message_history_cannot_authorize_release(self) -> None:
        historical = [
            SimpleNamespace(
                parts=[ToolReturnPart("librarian_search", retrieval_result())]
            )
        ]
        current = [SimpleNamespace(parts=[])]
        muse = AsyncMock()
        muse.run.return_value = SimpleNamespace(
            output=candidate("A supported thought.", evidence_id=EVIDENCE_ID),
            all_messages=lambda: historical + current,
            new_messages=lambda: current,
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_exact_previously_released_evidence_can_authorize_later_turn(self) -> None:
        self.register_evidence()
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate("That same passage still fits.", evidence_id=EVIDENCE_ID)
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "What about that passage?",
            [],
            muse=muse,
            provenance=provenance,
            previously_released_evidence_ids=frozenset({EVIDENCE_ID}),
        )

        self.assertEqual("muse_candidate", release.release_source)
        self.assertEqual((EVIDENCE_ID,), release.evidence_ids)

    async def test_reject_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unsafe draft")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("reject"))

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual(("reject",), release.provenance_verdicts)
        self.assertEqual(1, muse.run.await_count)

    async def test_failed_review_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unreviewed draft")
        provenance = AsyncMock()
        provenance.run.side_effect = RuntimeError("provider failed")

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual((), release.provenance_verdicts)

    async def test_second_revision_request_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Still unsafe")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Try again.")),
            result(review("revise", finding="Still unsafe.")),
        ]

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual(("revise", "revise"), release.provenance_verdicts)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)
