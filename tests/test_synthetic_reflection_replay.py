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
from evals.reflection.harness import (
    GroundedRelease,
    GroundingExpectation,
    SafeDecline,
    UngroundedRelease,
)
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.reflection_replay import (
    SceneTurn,
    grade_scene,
    replay_reflection_scenes,
)

OBJECTIVE_ID = "grounded_book_reflection"
CORPUS_CHAPTER = (
    "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/"
    "01-down-the-rabbit-hole.md"
)
QUOTE = "a book of rules for shutting people up like telescopes"
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
        clarifying = turn(retrieved=False, evidence_ids=(), reply="Which chapter?")
        self.assertEqual((), grade_scene(grounded(), [clarifying, turn()]))


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
) -> ChatResponse:
    return ChatResponse(
        reply=reply,
        inspection=TurnInspection(
            muse_turn={"turn_id": "turn-1"},
            context_resolution={"status": "confirmed", "chapter_max": chapter_max},
            traces=[],
            librarian_grounding=[{"request": {}}] if retrieved else [],
            prompt="",
            release=ReleaseInspection(
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=(),
                released_evidence_ids=evidence_ids,
                revision_count=0,
                failure_stage=None,
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
    async def test_replays_both_scenes_and_places_props(self) -> None:
        backstory, ground_truth = _package()
        seen_memory_counts: list[int] = []

        async def handler(request, service, account):
            seen_memory_counts.append(len(service.list_active(account)))
            grounded_scene = "hoping to find" in request.message
            return _response(
                reply="A reply.",
                evidence_ids=("ev-1",) if grounded_scene else (),
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
                evidence_ids=("ev-1",) if grounded_scene else (),
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
                evidence_ids=("ev-1",) if grounded_scene else (),
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
