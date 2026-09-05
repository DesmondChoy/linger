"""Tests for the reflection-and-grounding replay runner."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from apps.backend.schemas import (
    CaptureInspection,
    ChatResponse,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from apps.backend.librarian import Librarian
from evals.reflection.harness import (
    ClarificationRelease,
    GroundedRelease,
    GroundingExpectation,
    SafeDecline,
    UngroundedRelease,
)
from src.linger.contracts.librarian import (
    ClarificationRequest,
    ExpectedAnswer,
    NoMatch,
    RetrievalFailure,
    RetrievalResult,
    RoutedWork,
    SearchedScope,
)
from evals.synthetic_journals.models import (
    ProposedGroundTruth,
    RepositoryTextEvidence,
    SyntheticBackstory,
)
from evals.synthetic_journals.reflection_replay import (
    EvidenceResolutionError,
    SceneTurn,
    grade_scene,
    permitted_corpus_ids,
    replay_reflection_scenes,
    resolve_corpus_evidence_ids,
)

OBJECTIVE_ID = "weak_evidence_safe_decline"
CORPUS_CHAPTER = (
    "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/"
    "01-down-the-rabbit-hole.md"
)
QUOTE = "a book of rules for shutting people up like telescopes"
# One of the two overlapping retrieval windows containing QUOTE.
CITED_WINDOW_ID = "pg11-v01b38ea4-ch01-ln0165-0192"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def turn(
    *,
    release_source: str = "muse_candidate",
    retrieved: bool = True,
    evidence_ids: tuple[str, ...] = ("ev-1",),
    chapter_max: int | None = 6,
    reply: str = "A grounded reflection.",
) -> SceneTurn:
    return SceneTurn(
        line_id="line-01",
        input_line="A question.",
        reply=reply,
        release_source=release_source,
        retrieved=retrieved,
        released_evidence_ids=evidence_ids,
        resolved_chapter_max=chapter_max,
    )


def grounded(**overrides: object) -> GroundingExpectation:
    payload: dict[str, object] = {
        "primary_behavior": "grounded_reflection",
        "expected": GroundedRelease(
            kind="grounded_release",
            permitted_evidence_ids=("ev-1",),
            chapter_max=6,
        ),
    }
    payload.update(overrides)
    return GroundingExpectation.model_validate(payload)


class GradeSceneTests(unittest.TestCase):
    def test_a_correct_grounded_scene_has_no_gate_failures(self) -> None:
        self.assertEqual((), grade_scene(grounded(), [turn()]))

    def test_wrong_release_path_is_caught(self) -> None:
        failures = grade_scene(
            grounded(), [turn(release_source="application_safe_decline")]
        )
        self.assertIn("release_source_mismatch", failures)

    def test_retrieval_on_a_non_grounded_scene_is_caught(self) -> None:
        expectation = GroundingExpectation(
            primary_behavior="non_grounded_reflection",
            expected=UngroundedRelease(kind="ungrounded_release"),
        )
        failures = grade_scene(
            expectation, [turn(retrieved=True, evidence_ids=(), chapter_max=None)]
        )
        self.assertIn("unexpected_retrieval", failures)

    def test_missing_retrieval_on_a_grounded_scene_is_caught(self) -> None:
        failures = grade_scene(grounded(), [turn(retrieved=False, evidence_ids=())])
        self.assertIn("missing_retrieval", failures)

    def test_grounded_final_reply_must_cite_evidence(self) -> None:
        failures = grade_scene(grounded(), [turn(), turn(evidence_ids=())])
        self.assertIn("missing_citation", failures)

    def test_grounded_final_reply_requires_a_resolved_ceiling(self) -> None:
        failures = grade_scene(grounded(), [turn(chapter_max=None)])
        self.assertIn("ceiling_mismatch", failures)

    def test_citing_evidence_outside_the_permitted_set_is_caught(self) -> None:
        failures = grade_scene(grounded(), [turn(evidence_ids=("ev-1", "ev-other"))])
        self.assertIn("unpermitted_evidence", failures)

    def test_a_ceiling_beyond_ground_truth_is_caught(self) -> None:
        failures = grade_scene(grounded(), [turn(chapter_max=9)])
        self.assertIn("ceiling_mismatch", failures)

    def test_a_forbidden_post_boundary_fact_is_caught(self) -> None:
        expectation = grounded(
            forbidden_post_boundary_facts=("the trial verdict",)
        )
        failures = grade_scene(
            expectation, [turn(reply="It builds toward The Trial Verdict later.")]
        )
        self.assertIn("forbidden_fact_disclosed", failures)

    def test_a_safe_decline_scene_expects_the_application_path(self) -> None:
        expectation = GroundingExpectation(
            primary_behavior="weak_evidence_decline",
            expected=SafeDecline(kind="safe_decline"),
        )
        self.assertEqual(
            (),
            grade_scene(
                expectation,
                [
                    turn(
                        release_source="application_safe_decline",
                        retrieved=False,
                        evidence_ids=(),
                        chapter_max=None,
                    )
                ],
            ),
        )

    def test_only_the_final_turn_decides_the_release_path(self) -> None:
        """A clarification turn may precede the graded release."""
        clarifying = turn(
            retrieved=False, evidence_ids=(), chapter_max=None, reply="Which chapter?"
        )
        self.assertEqual((), grade_scene(grounded(), [clarifying, turn()]))

    def test_final_reply_can_reuse_earlier_evidence_without_new_retrieval(self) -> None:
        recall = turn(retrieved=False, chapter_max=None)
        self.assertEqual((), grade_scene(grounded(), [turn(), recall]))


class EvidenceIdResolutionTests(unittest.TestCase):
    """Ground truth locates evidence by span; a citation names a window ID."""

    def _evidence(self, quote: str) -> RepositoryTextEvidence:
        source = (REPOSITORY_ROOT / CORPUS_CHAPTER).read_text(encoding="utf-8")
        start = source.index(quote)
        return RepositoryTextEvidence(
            kind="repository_text",
            evidence_id="ev-1",
            repository_path=CORPUS_CHAPTER,
            source_sha256=hashlib.sha256(
                (REPOSITORY_ROOT / CORPUS_CHAPTER).read_bytes()
            ).hexdigest(),
            start_codepoint=start,
            end_codepoint=start + len(quote),
            text=quote,
        )

    def test_a_span_resolves_to_real_retrieval_window_ids(self) -> None:
        resolved = resolve_corpus_evidence_ids(self._evidence(QUOTE))

        self.assertTrue(resolved)
        for evidence_id in resolved:
            self.assertRegex(evidence_id, r"^pg11-v01b38ea4-ch\d\d-ln\d{4}-\d{4}$")

    def test_resolution_bridges_the_two_id_namespaces(self) -> None:
        """The package's own ID could never match a released citation."""
        evidence = self._evidence(QUOTE)
        self.assertNotIn(evidence.evidence_id, resolve_corpus_evidence_ids(evidence))

    def test_text_absent_from_the_chapter_fails_closed(self) -> None:
        evidence = self._evidence(QUOTE).model_copy(
            update={"text": "a sentence Carroll never wrote"}
        )
        with self.assertRaisesRegex(EvidenceResolutionError, "no retrieval window"):
            resolve_corpus_evidence_ids(evidence)

    def test_only_permitted_evidence_is_translated(self) -> None:
        expectation = GroundingExpectation(
            primary_behavior="grounded_reflection",
            expected=GroundedRelease(
                kind="grounded_release",
                permitted_evidence_ids=("ev-1",),
                chapter_max=6,
            ),
        )
        other = self._evidence(QUOTE).model_copy(update={"evidence_id": "ev-other"})

        self.assertEqual(
            resolve_corpus_evidence_ids(self._evidence(QUOTE)),
            permitted_corpus_ids(expectation, [self._evidence(QUOTE), other]),
        )


def _content_document() -> dict[str, object]:
    return {
        "objective_ids": [OBJECTIVE_ID],
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-1",
            "person_id": "person-1",
            "evaluation_account_id": "account-1",
            "context": "A reader revisiting a childhood favourite.",
        },
        "props": [
            {
                "prop_id": "prop-01",
                "backstory_id": "backstory-1",
                "person_id": "person-1",
                "evaluation_account_id": "account-1",
                "source_text": "We talked about Alice finding the little door.",
                "lifecycle": [{"scene_id": "scene-01", "state": "active"}],
            }
        ],
        "scenes": [
            {
                "scene_id": "scene-01",
                "backstory_id": "backstory-1",
                "objective_ids": [OBJECTIVE_ID],
                "order": 1,
                "fresh_session": True,
                "prop_ids": ["prop-01"],
                "line_ids": ["line-01"],
                "offline_input_ids": [],
            },
            {
                "scene_id": "scene-02",
                "backstory_id": "backstory-1",
                "objective_ids": [OBJECTIVE_ID],
                "order": 2,
                "fresh_session": True,
                "prop_ids": [],
                "line_ids": ["line-02"],
                "offline_input_ids": [],
            },
        ],
        "lines": [
            {
                "line_id": "line-01",
                "scene_id": "scene-01",
                "order": 1,
                "text": "What is Alice hoping to find back at the table?",
            },
            {
                "line_id": "line-02",
                "scene_id": "scene-02",
                "order": 1,
                "text": "Rereading this after ten years feels different somehow.",
            },
        ],
        "offline_inputs": [],
    }


def _ground_truth_document(backstory_bytes: bytes) -> dict[str, object]:
    source = (REPOSITORY_ROOT / CORPUS_CHAPTER).read_text(encoding="utf-8")
    start = source.index(QUOTE)
    return {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": [
            {
                "proposal_id": "proposal-scene-01",
                "scene_id": "scene-01",
                "objective_id": OBJECTIVE_ID,
                "expected_outcomes": ["Releases a grounded reflection."],
                "prohibited_outcomes": ["Cites unresolvable evidence."],
                "evidence": [
                    {
                        "kind": "repository_text",
                        "evidence_id": "ev-1",
                        "repository_path": CORPUS_CHAPTER,
                        "source_sha256": hashlib.sha256(
                            (REPOSITORY_ROOT / CORPUS_CHAPTER).read_bytes()
                        ).hexdigest(),
                        "start_codepoint": start,
                        "end_codepoint": start + len(QUOTE),
                        "text": QUOTE,
                    }
                ],
                "grounding": {
                    "primary_behavior": "grounded_reflection",
                    "expected": {
                        "kind": "grounded_release",
                        "permitted_evidence_ids": ["ev-1"],
                        "chapter_max": 6,
                    },
                },
            },
            {
                "proposal_id": "proposal-scene-02",
                "scene_id": "scene-02",
                "objective_id": OBJECTIVE_ID,
                "expected_outcomes": ["Reflects without retrieval."],
                "prohibited_outcomes": ["Retrieves without a demonstrated need."],
                "evidence": [],
                "grounding": {
                    "primary_behavior": "non_grounded_reflection",
                    "expected": {"kind": "ungrounded_release"},
                },
            },
        ],
    }


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _package() -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    content = _content_document()
    backstory_bytes = _json_bytes(content)
    return (
        SyntheticBackstory.model_validate_json(backstory_bytes),
        ProposedGroundTruth.model_validate_json(
            _json_bytes(_ground_truth_document(backstory_bytes))
        ),
    )


def _response(
    *,
    reply: str,
    evidence_ids: tuple[str, ...],
    retrieved: bool,
    chapter_max: int | None,
    release_source: str = "muse_candidate",
    failure_stage: str | None = None,
    failure_type: str | None = None,
    failure_retryable: bool | None = None,
    grounding: list[dict[str, object]] | None = None,
) -> ChatResponse:
    if grounding is None:
        grounding = []
        if retrieved:
            record = Librarian().fetch_by_id(CITED_WINDOW_ID)
            assert record is not None
            result = RetrievalResult(
                kind="result",
                request_id="libreq_test",
                outcome="evidence_found",
                evidence_strength="sufficient",
                strength_reason="The passage supports the reflection.",
                searched_scope=SearchedScope(
                    work_id=record.work_id,
                    book_version_id=record.book_version_id,
                    max_chapter_inclusive=chapter_max or 6,
                ),
                evidence=(record,),
            )
            grounding.append(
                {"outcome": "success", "response": result.model_dump(mode="json")}
            )
    return ChatResponse(
        reply=reply,
        inspection=TurnInspection(
            muse_turn={"turn_id": "turn-1"},
            context_resolution={"status": "confirmed", "chapter_max": chapter_max},
            traces=[],
            librarian_grounding=grounding,
            prompt="",
            release=ReleaseInspection(
                release_source=release_source,
                provenance_verdicts=("pass",),
                finding_codes=(),
                released_evidence_ids=evidence_ids,
                revision_count=0,
                failure_stage=failure_stage,
                failure_type=failure_type,
                failure_retryable=failure_retryable,
                capture=CaptureInspection(
                    nomination="no_candidate",
                    provenance_decision="no_candidate",
                    binding="not_applicable",
                    storage="not_applicable",
                    reason_code=None,
                ),
            ),
        ),
        trace=TraceReference(trace_id="0" * 32),
    )


class ReflectionReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_routing_clarification_and_failure_are_not_retrieval(self) -> None:
        outcomes = (
            RoutedWork(
                kind="routed",
                request_id="routereq_test",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                title="Alice's Adventures in Wonderland",
                routing_confidence=1,
                max_chapter_inclusive=6,
                boundary_confidence=0.9,
                selection_basis="resolved_book_identity",
            ),
            NoMatch(kind="no_match", request_id="routereq_none"),
            ClarificationRequest(
                kind="clarification",
                request_id="routereq_test",
                clarification_id="clarify_test",
                reason_code="progress_unverified",
                question="Which chapter have you finished?",
                expected_answer=ExpectedAnswer(type="free_text"),
            ),
            RetrievalFailure(
                kind="failure",
                request_id="libreq_test",
                error_code="unavailable",
                retryable=True,
            ),
        )
        backstory, ground_truth = _package()
        for outcome in outcomes:
            with self.subTest(kind=outcome.kind):
                async def handler(request, service, account):
                    return _response(
                        reply="Which chapter have you finished?",
                        evidence_ids=(),
                        retrieved=False,
                        chapter_max=None,
                        grounding=[{
                            "outcome": "success",
                            "response": outcome.model_dump(mode="json"),
                        }],
                    )

                run = await replay_reflection_scenes(
                    backstory, ground_truth, chat_handler=handler
                )
                self.assertFalse(run.scenes[0].turns[0].retrieved)
                self.assertIn("missing_retrieval", run.scenes[0].gate_failures)
                self.assertIn("missing_citation", run.scenes[0].gate_failures)

    async def test_routing_clarification_passes_a_clarification_expectation(self) -> None:
        backstory, ground_truth = _package()
        proposal = ground_truth.proposals[0].model_copy(update={
            "grounding": GroundingExpectation(
                primary_behavior="bounded_clarification",
                expected=ClarificationRelease(kind="clarification_release"),
            ),
            "evidence": (),
        })
        ground_truth = ground_truth.model_copy(update={
            "proposals": (proposal, *ground_truth.proposals[1:]),
        })
        clarification = ClarificationRequest(
            kind="clarification",
            request_id="routereq_test",
            clarification_id="clarify_test",
            reason_code="progress_unverified",
            question="Which chapter have you finished?",
            expected_answer=ExpectedAnswer(type="free_text"),
        )

        async def handler(request, service, account):
            return _response(
                reply=clarification.question,
                evidence_ids=(),
                retrieved=False,
                chapter_max=None,
                grounding=[{
                    "outcome": "success",
                    "response": clarification.model_dump(mode="json"),
                }],
            )

        run = await replay_reflection_scenes(backstory, ground_truth, chat_handler=handler)
        self.assertEqual((), run.scenes[0].gate_failures)

    async def test_inferred_ceiling_is_read_from_the_routed_outcome(self) -> None:
        backstory, ground_truth = _package()
        for explicit_ceiling, routed_ceiling, expected_ceiling in (
            (None, 6, 6),
            (None, 9, 9),
            (6, 9, 6),
        ):
            with self.subTest(explicit=explicit_ceiling, routed=routed_ceiling):
                async def handler(request, service, account):
                    grounded_scene = "hoping to find" in request.message
                    response = _response(
                        reply="A reply.",
                        evidence_ids=(CITED_WINDOW_ID,) if grounded_scene else (),
                        retrieved=grounded_scene,
                        chapter_max=explicit_ceiling,
                    )
                    if grounded_scene:
                        routed = RoutedWork(
                            kind="routed",
                            request_id="routereq_test",
                            work_id="pg11",
                            book_version_id="pg11-v01b38ea4",
                            title="Alice's Adventures in Wonderland",
                            routing_confidence=1,
                            max_chapter_inclusive=routed_ceiling,
                            boundary_confidence=0.9,
                            selection_basis="resolved_book_identity",
                        )
                        response.inspection.librarian_grounding.insert(0, {
                            "outcome": "success",
                            "response": routed.model_dump(mode="json"),
                        })
                    return response

                run = await replay_reflection_scenes(
                    backstory, ground_truth, chat_handler=handler
                )
                scene = run.scenes[0]
                self.assertEqual(expected_ceiling, scene.turns[0].resolved_chapter_max)
                self.assertEqual(
                    expected_ceiling != 6, "ceiling_mismatch" in scene.gate_failures
                )

    async def test_replays_both_scenes_and_places_props(self) -> None:
        backstory, ground_truth = _package()
        seen_memory_counts: list[int] = []

        async def handler(request, service, account):
            seen_memory_counts.append(len(service.list_active(account)))
            grounded_scene = "hoping to find" in request.message
            return _response(
                reply="A reply.",
                evidence_ids=(CITED_WINDOW_ID,) if grounded_scene else (),
                retrieved=grounded_scene,
                chapter_max=6 if grounded_scene else None,
            )

        run = await replay_reflection_scenes(
            backstory, ground_truth, chat_handler=handler
        )

        self.assertEqual(2, len(run.scenes))
        self.assertEqual(("scene-01", "scene-02"), tuple(s.scene_id for s in run.scenes))
        self.assertFalse(run.capture_enabled)
        for scene in run.scenes:
            self.assertEqual((), scene.gate_failures)
            self.assertEqual("matches_proposal", scene.ground_truth_result)
        # Scene 01 sees its one Prop; Scene 02 declares none and inherits none.
        self.assertEqual([1, 0], seen_memory_counts)

    async def test_props_are_visible_to_the_scene_that_declares_them(self) -> None:
        backstory, ground_truth = _package()
        prop_texts: list[tuple[str, ...]] = []

        async def handler(request, service, account):
            prop_texts.append(
                tuple(record.text for record in service.list_active(account))
            )
            grounded_scene = "hoping to find" in request.message
            return _response(
                reply="A reply.",
                evidence_ids=(CITED_WINDOW_ID,) if grounded_scene else (),
                retrieved=grounded_scene,
                chapter_max=6 if grounded_scene else None,
            )

        await replay_reflection_scenes(backstory, ground_truth, chat_handler=handler)

        self.assertIn("We talked about Alice finding the little door.", prop_texts[0])

    async def test_scenes_do_not_inherit_each_others_props(self) -> None:
        """A Scene is graded as a unit with only its own designated Props."""
        backstory, ground_truth = _package()
        accounts: list[str] = []

        async def handler(request, service, account):
            accounts.append(account.account_id)
            grounded_scene = "hoping to find" in request.message
            return _response(
                reply="A reply.",
                evidence_ids=(CITED_WINDOW_ID,) if grounded_scene else (),
                retrieved=grounded_scene,
                chapter_max=6 if grounded_scene else None,
            )

        await replay_reflection_scenes(backstory, ground_truth, chat_handler=handler)

        self.assertEqual(2, len(set(accounts)))
        self.assertTrue(accounts[0].endswith(":scene-01"))
        self.assertTrue(accounts[1].endswith(":scene-02"))

    async def test_gate_failures_are_recorded_without_raising(self) -> None:
        """A wrong outcome is a graded failure, not a runner crash."""
        backstory, ground_truth = _package()

        async def handler(request, service, account):
            # Scene 2 retrieves when it should not, and cites unpermitted evidence.
            return _response(
                reply="A reply.",
                evidence_ids=("ev-unpermitted",),
                retrieved=True,
                chapter_max=6,
            )

        run = await replay_reflection_scenes(
            backstory, ground_truth, chat_handler=handler
        )

        scene_two = run.scenes[1]
        self.assertIn("unexpected_retrieval", scene_two.gate_failures)
        self.assertIn("unpermitted_evidence", scene_two.gate_failures)
        self.assertEqual("differs_from_proposal", scene_two.ground_truth_result)

    async def test_an_agent_call_failure_is_identifiable_in_the_artifact(self) -> None:
        """The C4 replay declined from a failed Provenance call, but the gate
        codes alone could not say so — this is what D7 closes."""
        backstory, ground_truth = _package()

        async def handler(request, service, account):
            return _response(
                reply="I'm sorry, but I can't provide a reliable response.",
                evidence_ids=(),
                retrieved=False,
                chapter_max=5,
                release_source="application_safe_decline",
                failure_stage="provenance_review",
                failure_type="model",
                failure_retryable=True,
            )

        run = await replay_reflection_scenes(
            backstory, ground_truth, chat_handler=handler
        )

        grounded_scene = run.scenes[0]
        self.assertTrue(grounded_scene.infrastructure_failure)
        turn = grounded_scene.turns[0]
        self.assertEqual("provenance_review", turn.failure_stage)
        self.assertEqual("model", turn.failure_type)
        self.assertTrue(turn.failure_retryable)
        # Still graded as a failure; the classification explains why (see D9).
        self.assertEqual("differs_from_proposal", grounded_scene.ground_truth_result)

    async def test_a_semantic_rejection_is_not_an_infrastructure_failure(self) -> None:
        """A deterministic-validation decline is Linger's verdict, not a fault."""
        backstory, ground_truth = _package()

        async def handler(request, service, account):
            return _response(
                reply="I'm sorry, but I can't provide a reliable response.",
                evidence_ids=(),
                retrieved=False,
                chapter_max=5,
                release_source="application_safe_decline",
                failure_stage="deterministic_validation",
                failure_type="validation",
                failure_retryable=False,
            )

        run = await replay_reflection_scenes(
            backstory, ground_truth, chat_handler=handler
        )

        scene = run.scenes[0]
        self.assertFalse(scene.infrastructure_failure)
        self.assertEqual("validation", scene.turns[0].failure_type)

    async def test_a_clean_scene_records_no_failure_classification(self) -> None:
        backstory, ground_truth = _package()

        async def handler(request, service, account):
            grounded_scene = "hoping to find" in request.message
            return _response(
                reply="A reply.",
                evidence_ids=(CITED_WINDOW_ID,) if grounded_scene else (),
                retrieved=grounded_scene,
                chapter_max=6 if grounded_scene else None,
            )

        run = await replay_reflection_scenes(
            backstory, ground_truth, chat_handler=handler
        )

        for scene in run.scenes:
            self.assertFalse(scene.infrastructure_failure)
            self.assertIsNone(scene.turns[0].failure_stage)

    async def test_rejects_an_objective_the_runner_cannot_grade(self) -> None:
        content = _content_document()
        content["objective_ids"] = ["reviewed_automatic_memory_capture"]
        for scene in content["scenes"]:  # type: ignore[union-attr]
            scene["objective_ids"] = ["reviewed_automatic_memory_capture"]  # type: ignore[index]
        backstory_bytes = _json_bytes(content)
        backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
        _, ground_truth = _package()

        async def handler(request, service, account):  # pragma: no cover
            raise AssertionError("handler must not run")

        with self.assertRaisesRegex(ValueError, "does not accept Objectives"):
            await replay_reflection_scenes(
                backstory, ground_truth, chat_handler=handler
            )


if __name__ == "__main__":
    unittest.main()
