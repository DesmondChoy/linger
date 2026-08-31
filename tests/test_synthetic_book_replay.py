"""Focused tests for grounded-reflection and spoiler-boundary replay."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend import sessions
from apps.backend.contracts import ContextResolution
from apps.backend.schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.book_replay import (
    BOOK_OBJECTIVE_IDS,
    _book_scene_cases,
    replay_book_scenes,
)
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_package import (
    PackageValidationError,
    load_run_configurations,
    validate_package,
)
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.librarian import (
    BoundaryCandidate,
    BoundarySupportLocation,
    BoundaryUncertain,
)
from src.linger.evaluation_transcript import active_evaluation_transcript_sink
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import AccountContext, MemoryPolicyService

ROOT = Path(__file__).resolve().parents[1]
CHAPTER_FIVE_PATH = Path(
    "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/"
    "05-advice-from-a-caterpillar.md"
)
CHAPTER_EIGHT_PATH = Path(
    "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/"
    "08-the-queens-croquet-ground.md"
)
SUPPORT_ID = "pg11-v01b38ea4-ch05-ln0974-0975"
FORBIDDEN_ID = "pg11-v01b38ea4-ch08-ln2010-2011"
QUOTE = "“Who are _you?_” said the Caterpillar."
FORBIDDEN = "Off with her head!"
CLARIFICATION = (
    "What is the latest chapter or scene in Alice's Adventures in Wonderland "
    "that you have completed?"
)


def _repository_evidence(
    path: Path,
    evidence_id: str,
    text: str,
) -> dict[str, object]:
    source = (ROOT / path).read_text(encoding="utf-8")
    start = source.index(text)
    return {
        "kind": "repository_text",
        "evidence_id": evidence_id,
        "repository_path": str(path),
        "source_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
        "start_codepoint": start,
        "end_codepoint": start + len(text),
        "text": text,
    }


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    prop_text = (
        "Alice and the Caterpillar's questions about identity stayed with me."
    )
    infer_line = (
        "Why does Alice struggle to explain who she is, and can you quote the passage?"
    )
    clarify_line = (
        "What should I make of what happens after Alice's conversation about identity?"
    )
    personal_line = (
        "I also struggle to explain who I am when my plans keep changing."
    )
    content: dict[str, object] = {
        "objective_ids": list(BOOK_OBJECTIVE_IDS),
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-book-01",
            "person_id": "person-book-01",
            "evaluation_account_id": "account-book-01",
            "context": "One reader connects a changing sense of identity to a novel.",
        },
        "props": [
            {
                "prop_id": "prop-event-memory",
                "backstory_id": "backstory-book-01",
                "person_id": "person-book-01",
                "evaluation_account_id": "account-book-01",
                "source_text": prop_text,
                "lifecycle": [
                    {"scene_id": "scene-infer-ground", "state": "active"},
                    {"scene_id": "scene-clarify", "state": "active"},
                ],
            }
        ],
        "scenes": [
            {
                "scene_id": "scene-infer-ground",
                "backstory_id": "backstory-book-01",
                "objective_ids": list(BOOK_OBJECTIVE_IDS),
                "order": 1,
                "fresh_session": True,
                "prop_ids": ["prop-event-memory"],
                "line_ids": ["line-infer-ground"],
                "offline_input_ids": [],
            },
            {
                "scene_id": "scene-clarify",
                "backstory_id": "backstory-book-01",
                "objective_ids": ["spoiler_boundary_clarification"],
                "order": 2,
                "fresh_session": True,
                "prop_ids": ["prop-event-memory"],
                "line_ids": ["line-clarify"],
                "offline_input_ids": [],
            },
            {
                "scene_id": "scene-personal",
                "backstory_id": "backstory-book-01",
                "objective_ids": ["grounded_book_reflection"],
                "order": 3,
                "fresh_session": True,
                "prop_ids": [],
                "line_ids": ["line-personal"],
                "offline_input_ids": [],
            },
        ],
        "lines": [
            {
                "line_id": "line-infer-ground",
                "scene_id": "scene-infer-ground",
                "order": 1,
                "text": infer_line,
            },
            {
                "line_id": "line-clarify",
                "scene_id": "scene-clarify",
                "order": 1,
                "text": clarify_line,
            },
            {
                "line_id": "line-personal",
                "scene_id": "scene-personal",
                "order": 1,
                "text": personal_line,
            },
        ],
        "offline_inputs": [],
    }
    backstory_bytes = _json_bytes(content)
    prop_span = {
        "source_kind": "prop",
        "source_id": "prop-event-memory",
        "start_codepoint": 0,
        "end_codepoint": len(prop_text),
        "text": prop_text,
    }
    infer_span = {
        "source_kind": "line",
        "source_id": "line-infer-ground",
        "start_codepoint": 0,
        "end_codepoint": len(infer_line),
        "text": infer_line,
    }
    clarify_span = {
        "source_kind": "line",
        "source_id": "line-clarify",
        "start_codepoint": 0,
        "end_codepoint": len(clarify_line),
        "text": clarify_line,
    }
    grounded_support_ref = "evidence-grounded-support"
    spoiler_support_ref = "evidence-spoiler-support"
    spoiler_forbidden_ref = "evidence-spoiler-forbidden"
    clarify_forbidden_ref = "evidence-clarify-forbidden"
    grounded_support = _repository_evidence(
        CHAPTER_FIVE_PATH,
        grounded_support_ref,
        QUOTE,
    )
    spoiler_support = _repository_evidence(
        CHAPTER_FIVE_PATH,
        spoiler_support_ref,
        QUOTE,
    )
    spoiler_forbidden = _repository_evidence(
        CHAPTER_EIGHT_PATH,
        spoiler_forbidden_ref,
        FORBIDDEN,
    )
    clarify_forbidden = _repository_evidence(
        CHAPTER_EIGHT_PATH,
        clarify_forbidden_ref,
        FORBIDDEN,
    )
    proposals = [
        {
            "proposal_id": "proposal-infer-grounded",
            "scene_id": "scene-infer-ground",
            "objective_id": "grounded_book_reflection",
            "expected_outcomes": ["Use exact permitted book evidence."],
            "prohibited_outcomes": ["Use evidence outside the permitted set."],
            "exact_spans": [],
            "evidence": [grounded_support],
            "pairing": {
                "paired_scene_id": "scene-personal",
                "match_fields": ["backstory_id", "fresh_session"],
                "difference_fields": ["prop_ids", "line_text"],
            },
            "grounded_book_reflection": {
                "retrieval": "required",
                "permitted_evidence_ids": [grounded_support_ref],
                "exact_quotation_evidence_ids": [grounded_support_ref],
            },
        },
        {
            "proposal_id": "proposal-infer-spoiler",
            "scene_id": "scene-infer-ground",
            "objective_id": "spoiler_boundary_clarification",
            "expected_outcomes": ["Infer Chapter 5 as the safe ceiling."],
            "prohibited_outcomes": ["Reveal a later event."],
            "exact_spans": [prop_span, infer_span],
            "evidence": [spoiler_support, spoiler_forbidden],
            "pairing": {
                "paired_scene_id": "scene-clarify",
                "match_fields": ["backstory_id", "fresh_session", "prop_ids"],
                "difference_fields": ["line_text"],
            },
            "spoiler_boundary": {
                "decision": "infer",
                "authorised_prop_ids": ["prop-event-memory"],
                "safe_ceiling_chapter": 5,
                "supporting_evidence_ids": [spoiler_support_ref],
                "forbidden_later_evidence_ids": [spoiler_forbidden_ref],
            },
        },
        {
            "proposal_id": "proposal-clarify-spoiler",
            "scene_id": "scene-clarify",
            "objective_id": "spoiler_boundary_clarification",
            "expected_outcomes": ["Ask for clarification without retrieval."],
            "prohibited_outcomes": ["Reveal a later event."],
            "exact_spans": [prop_span, clarify_span],
            "evidence": [clarify_forbidden],
            "pairing": {
                "paired_scene_id": "scene-infer-ground",
                "match_fields": ["backstory_id", "fresh_session", "prop_ids"],
                "difference_fields": ["line_text"],
            },
            "spoiler_boundary": {
                "decision": "clarify",
                "authorised_prop_ids": ["prop-event-memory"],
                "safe_ceiling_chapter": None,
                "supporting_evidence_ids": [],
                "forbidden_later_evidence_ids": [clarify_forbidden_ref],
            },
        },
        {
            "proposal_id": "proposal-personal-grounded",
            "scene_id": "scene-personal",
            "objective_id": "grounded_book_reflection",
            "expected_outcomes": ["Respond without book retrieval."],
            "prohibited_outcomes": ["Retrieve book evidence unnecessarily."],
            "exact_spans": [],
            "evidence": [],
            "pairing": {
                "paired_scene_id": "scene-infer-ground",
                "match_fields": ["backstory_id", "fresh_session"],
                "difference_fields": ["prop_ids", "line_text"],
            },
            "grounded_book_reflection": {
                "retrieval": "not_required",
                "permitted_evidence_ids": [],
                "exact_quotation_evidence_ids": [],
            },
        },
    ]
    ground_truth = {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }
    return content, ground_truth


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _models() -> tuple[SyntheticBackstory, ProposedGroundTruth, bytes]:
    content, ground_truth = _documents()
    backstory_bytes = _json_bytes(content)
    backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
    proposed = ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth))
    validate_package(
        backstory,
        proposed,
        backstory_bytes=backstory_bytes,
        run_configurations=load_run_configurations(
            ROOT / "synthetic-journal-evaluation" / "run-configurations"
        ),
    )
    return backstory, proposed, _json_bytes(ground_truth)


def _capture() -> CaptureInspection:
    return CaptureInspection(
        nomination="no_candidate",
        provenance_decision="no_candidate",
        binding="not_applicable",
        storage="not_applicable",
        reason_code="automatic_capture_disabled",
    )


def _record_boundary(output: BoundaryInferenceDecision) -> None:
    sink = active_evaluation_transcript_sink()
    assert sink is not None
    boundary_input = {
        "current_line": "synthetic current line",
        "relevant_memories": [],
        "full_work_candidates": [
            {
                "evidence_id": SUPPORT_ID,
                "work_id": "pg11",
                "book_version_id": "pg11-v01b38ea4",
                "chapter_id": "pg11-v01b38ea4-ch05",
                "chapter_number": 5,
                "location": "Chapter 5, source lines 974-975",
                "source_sha256": "0" * 64,
                "source_lines": [974, 975],
                "text": QUOTE,
            }
        ],
    }
    handle = sink.begin_agent_exchange(
        role="Librarian",
        stage="boundary_inference",
        input_origin="Application",
        output_receiver="Application",
        input_contract="LibrarianBoundaryInferenceInput.v1",
        output_contract=(
            "src.linger.agents.librarian.models.BoundaryInferenceDecision"
        ),
        prompt_template_id="librarian.boundary-inference",
        prompt_version="1",
        prompt_digest="0" * 64,
        input_prompt=json.dumps(boundary_input),
        message_history=(),
        trace_id="0" * 32,
        span_id="0" * 16,
    )
    sink.complete_agent_exchange(
        handle,
        result=SimpleNamespace(
            output=output,
            new_messages=lambda: (),
            usage=lambda: None,
        ),
        status="success",
        failure_code=None,
    )


def _response(
    request: ChatRequest,
    *,
    kind: str,
    searched_max: int = 5,
) -> ChatResponse:
    if kind == "infer":
        _record_boundary(
            BoundaryInferenceDecision(
                outcome="candidate",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_number=5,
                confidence=0.92,
                supporting_evidence_ids=(SUPPORT_ID,),
            )
        )
        context = ContextResolution(
            status="confirmed",
            work_id="pg11",
            work_title="Alice's Adventures in Wonderland",
            book_version_id="pg11-v01b38ea4",
            chapter_max=5,
            boundary_source="librarian_inferred",
            boundary_confidence=0.92,
            boundary_supporting_locations=(
                BoundarySupportLocation(
                    evidence_id=SUPPORT_ID,
                    chapter_number=5,
                    location="Chapter 5, source lines 974-975",
                ),
            ),
            explanation="A request-scoped ceiling was inferred.",
        )
        reply = f"The passage says {QUOTE} That uncertainty can echo change."
        grounding = [_grounding_call(request.message, searched_max=searched_max)]
        evidence_ids = (SUPPORT_ID,)
    elif kind == "clarify":
        _record_boundary(
            BoundaryInferenceDecision(
                outcome="uncertain",
                confidence=0.4,
                reason_code="insufficient_context",
            )
        )
        context = ContextResolution(
            status="inferred",
            work_id="pg11",
            work_title="Alice's Adventures in Wonderland",
            book_version_id="pg11-v01b38ea4",
            clarification_question=CLARIFICATION,
            explanation="The reading boundary remains uncertain.",
        )
        reply = CLARIFICATION
        grounding = []
        evidence_ids = ()
    else:
        context = ContextResolution(
            status="unknown",
            explanation="No book context was established.",
        )
        reply = "Changing plans can make identity feel unsettled without defining you."
        grounding = []
        evidence_ids = ()

    sessions.append_turn(
        request.session_id,
        request.message,
        reply,
        turn_id=request.turn_id or "missing-turn",
        release_source="muse_candidate",
        evidence_ids=evidence_ids,
    )
    return ChatResponse(
        reply=reply,
        inspection=TurnInspection(
            muse_turn={"turn_id": request.turn_id},
            context_resolution=context.model_dump(mode="json"),
            traces=[],
            librarian_grounding=grounding,
            prompt="synthetic",
            release=ReleaseInspection(
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=(),
                revision_count=0,
                failure_stage=None,
                capture=_capture(),
            ),
        ),
        trace=TraceReference(trace_id="0" * 32),
    )


def _grounding_call(query: str, *, searched_max: int = 5) -> dict[str, object]:
    return {
        "request": {"query": query},
        "outcome": "success",
        "response": {
            "kind": "result",
            "request_id": "request-grounding",
            "outcome": "evidence_found",
            "evidence_strength": "sufficient",
            "strength_reason": "The passage directly answers the question.",
            "searched_scope": {
                "work_id": "pg11",
                "book_version_id": "pg11-v01b38ea4",
                "max_chapter_inclusive": searched_max,
            },
            "evidence": [
                {
                    "evidence_id": SUPPORT_ID,
                    "work_id": "pg11",
                    "book_version_id": "pg11-v01b38ea4",
                    "chapter_id": "pg11-v01b38ea4-ch05",
                    "chapter_number": 5,
                    "location": "Chapter 5, source lines 974-975",
                    "source_sha256": "0" * 64,
                    "source_lines": [974, 975],
                    "text": QUOTE,
                }
            ],
            "limitations": [],
        },
    }


def test_package_validator_requires_typed_book_ground_truth() -> None:
    content, ground_truth = _documents()
    backstory_bytes = _json_bytes(content)
    proposal = ground_truth["proposals"][0]  # type: ignore[index]
    proposal.pop("grounded_book_reflection")
    backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
    proposed = ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth))

    with pytest.raises(PackageValidationError, match="lacks typed"):
        validate_package(
            backstory,
            proposed,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )


def test_book_replay_isolates_props_accounts_sessions_and_ground_truth() -> None:
    backstory, ground_truth, _ = _models()
    requests = []
    accounts = set()
    roots = set()
    prop_banks = []

    async def handler(request, service, account):
        requests.append(request)
        accounts.add(account.account_id)
        roots.add(service.root)
        assert not service.capture_enabled(account)
        prop_banks.append(tuple(record.text for record in service.list_active(account)))
        kind = (
            "infer"
            if "quote" in request.message
            else "clarify"
            if "Alice's conversation" in request.message
            else "personal"
        )
        return _response(request, kind=kind)

    result = asyncio.run(
        replay_book_scenes(
            backstory,
            ground_truth,
            chat_handler=handler,
        )
    )

    assert [scene.ground_truth_result for scene in result.scenes] == [
        "matches_proposal",
        "matches_proposal",
        "matches_proposal",
    ]
    assert len(accounts) == 1
    assert len(roots) == 3
    assert len({request.session_id for request in requests}) == 3
    assert len({request.turn_id for request in requests}) == 3
    assert [len(bank) for bank in prop_banks] == [1, 1, 0]
    assert all(not sessions.history(request.session_id) for request in requests)
    assert all(not root.exists() for root in roots)
    serialized_runtime = json.dumps(
        {
            "requests": [request.model_dump(mode="json") for request in requests],
            "props": prop_banks,
        }
    )
    assert backstory.backstory.context not in serialized_runtime
    assert "expected_outcomes" not in serialized_runtime
    assert "prohibited_outcomes" not in serialized_runtime
    assert "safe_ceiling_chapter" not in serialized_runtime


def test_book_replay_uses_adopted_identity_and_grades_ceiling_failure() -> None:
    backstory, ground_truth, ground_truth_bytes = _models()
    adoption = build_ground_truth_adoption(
        ground_truth,
        ground_truth_bytes,
        reviewer_id="independent-reviewer",
    )

    async def handler(request, _service, _account):
        kind = (
            "infer"
            if "quote" in request.message
            else "clarify"
            if "Alice's conversation" in request.message
            else "personal"
        )
        return _response(
            request,
            kind=kind,
            searched_max=6 if kind == "infer" else 5,
        )

    result = asyncio.run(
        replay_book_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            chat_handler=handler,
        )
    )

    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.ground_truth_status == "adopted"
    assert result.scenes[0].ground_truth_result == "fails_hard_gates"
    spoiler_grade = next(
        grade
        for grade in result.scenes[0].grades
        if grade.objective_id == "spoiler_boundary_clarification"
    )
    assert "retrieval_exceeded_safe_ceiling" in spoiler_grade.failures
    assert all(
        scene.ground_truth_result == "passes_hard_gates"
        for scene in result.scenes[1:]
    )


def test_book_replay_rejects_wrong_scene_topology() -> None:
    backstory, ground_truth, _ = _models()
    invalid = backstory.model_copy(update={"scenes": backstory.scenes[:2]})

    with pytest.raises(ValueError, match="exactly three Scenes"):
        _book_scene_cases(invalid, ground_truth)


def test_production_chat_path_receives_props_but_not_ground_truth() -> None:
    backstory, ground_truth, _ = _models()
    from apps.backend import chat_turn

    boundary_calls = 0

    async def infer_boundary(current_line, **kwargs):
        nonlocal boundary_calls
        boundary_calls += 1
        assert len(kwargs["memories"]) == 1
        if "quote" in current_line:
            _record_boundary(
                BoundaryInferenceDecision(
                    outcome="candidate",
                    work_id="pg11",
                    book_version_id="pg11-v01b38ea4",
                    chapter_number=5,
                    confidence=0.92,
                    supporting_evidence_ids=(SUPPORT_ID,),
                )
            )
            return BoundaryCandidate(
                kind="candidate",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                max_chapter_inclusive=5,
                confidence=0.92,
                supporting_locations=(
                    BoundarySupportLocation(
                        evidence_id=SUPPORT_ID,
                        chapter_number=5,
                        location="Chapter 5, source lines 974-975",
                    ),
                ),
            )
        _record_boundary(
            BoundaryInferenceDecision(
                outcome="uncertain",
                confidence=0.4,
                reason_code="insufficient_context",
            )
        )
        return BoundaryUncertain(
            kind="uncertain",
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            reason_code="insufficient_context",
            confidence=0.4,
            clarification_question=CLARIFICATION,
        )

    async def reflection(prompt, *_args, **_kwargs):
        payload = json.loads(prompt)
        line = payload["muse_turn"]["user_message"]
        serialized = json.dumps(payload)
        assert "expected_outcomes" not in serialized
        assert "safe_ceiling_chapter" not in serialized
        if "quote" in line:
            return ReflectionRelease(
                reply=f"The passage says {QUOTE} That uncertainty can echo change.",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                librarian_grounding_calls=(_grounding_call(line),),
                evidence_ids=(SUPPORT_ID,),
            )
        if "Alice's conversation" in line:
            return ReflectionRelease(
                reply=CLARIFICATION,
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
            )
        return ReflectionRelease(
            reply="Changing plans can make identity feel unsettled without defining you.",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        )

    with (
        patch.object(
            chat_turn,
            "assess_emotional_boundary",
            AsyncMock(
                return_value=EmotionalBoundaryAssessment(
                    decision="continue_reflection"
                )
            ),
        ),
        patch.object(chat_turn, "infer_spoiler_boundary", side_effect=infer_boundary),
        patch.object(chat_turn, "reflection_reply", side_effect=reflection),
    ):
        result = asyncio.run(
            replay_book_scenes(
                backstory,
                ground_truth,
                chat_handler=chat_turn.run_chat_turn,
            )
        )

    assert boundary_calls == 2
    assert all(
        scene.ground_truth_result == "matches_proposal" for scene in result.scenes
    )
    assert result.scenes[0].boundary_handoff_content_free is True
    assert result.scenes[1].boundary_handoff_content_free is True
