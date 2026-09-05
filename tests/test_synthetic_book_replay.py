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
from evals.synthetic_journals.book_contract import compile_book_replay_plan
from evals.synthetic_journals.book_replay import (
    BOOK_OBJECTIVE_IDS,
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
from src.linger.contracts.librarian import BoundarySupportLocation
from src.linger.evaluation_transcript import active_evaluation_transcript_sink
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import AccountContext, MemoryPolicyService

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_ID = "pg11-v01b38ea4-ch05-ln0964-0964"
QUOTE = "“Who are _you?_” said the Caterpillar."
CLARIFICATION = (
    "What is the latest chapter or scene in Alice's Adventures in Wonderland "
    "that you have completed?"
)


def _documents(
    objective_ids=BOOK_OBJECTIVE_IDS,
) -> tuple[dict[str, object], dict[str, object]]:
    from tests.test_synthetic_book_contract import _documents as canonical_documents

    content, truth = canonical_documents(objective_ids=objective_ids)
    encoded = json.dumps({"content": content, "truth": truth})
    encoded = encoded.replace("scene-infer", "scene-infer-ground")
    encoded = encoded.replace("line-infer", "line-infer-ground")
    encoded = encoded.replace(
        "Why does Alice struggle to explain who she is?",
        "Why does Alice struggle to explain who she is, and can you quote the passage?",
    )
    documents = json.loads(encoded)
    content, truth = documents["content"], documents["truth"]
    line = content["lines"][0]["text"]
    truth["book_scene_facts"][0]["basis_spans"][1].update(
        text=line, end_codepoint=len(line)
    )
    truth["backstory_sha256"] = hashlib.sha256(_json_bytes(content)).hexdigest()
    return content, truth


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _models(
    objective_ids=BOOK_OBJECTIVE_IDS,
) -> tuple[SyntheticBackstory, ProposedGroundTruth, bytes]:
    content, ground_truth = _documents(objective_ids)
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


def _corpus_record():
    from apps.backend.librarian import Librarian

    return Librarian().fetch_by_id(SUPPORT_ID).model_dump(mode="json")


def _record_boundary(output: BoundaryInferenceDecision) -> None:
    sink = active_evaluation_transcript_sink()
    assert sink is not None
    boundary_input = {
        "current_line": "synthetic current line",
        "relevant_memories": [],
        "full_work_candidates": [_corpus_record()],
    }
    from src.linger.evaluation_transcript import bind_evaluation_correlation_id

    with bind_evaluation_correlation_id("route-synthetic"):
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
    supporting_memory_ids: tuple[str, ...] = (),
) -> ChatResponse:
    if kind == "infer":
        _record_boundary(
            BoundaryInferenceDecision(
                outcome="candidate",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_number=5,
                confidence=0.92,
                authorization_basis="memory_supported",
                supporting_memory_ids=supporting_memory_ids,
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
            boundary_authorization_basis="memory_supported",
            boundary_confidence=0.92,
            boundary_supporting_memory_ids=supporting_memory_ids,
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
        grounding = [
            _route_call(ceiling=5),
            _grounding_call(request.message, searched_max=searched_max),
        ]
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
        grounding = [_route_clarification_call()]
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


def _route_call(*, ceiling: int = 5) -> dict[str, object]:
    """The `librarian_route` outcome a routed turn exposes to Inspect."""
    return {
        "tool_name": "librarian_route",
        "request": {},
        "outcome": "success",
        "response": {
            "kind": "routed",
            "request_id": "route-synthetic",
            "work_id": "pg11",
            "book_version_id": "pg11-v01b38ea4",
            "title": "Alice's Adventures in Wonderland",
            "routing_confidence": 0.7,
            "max_chapter_inclusive": ceiling,
            "boundary_confidence": 0.92,
            "selection_basis": "distinctive_cue",
        },
    }


def _route_clarification_call() -> dict[str, object]:
    """The `librarian_route` outcome when inference cannot set a ceiling."""
    return {
        "tool_name": "librarian_route",
        "request": {},
        "outcome": "success",
        "response": {
            "kind": "clarification",
            "request_id": "route-synthetic",
            "clarification_id": "clarify-synthetic",
            "reason_code": "insufficient_context",
            "question": CLARIFICATION,
            "expected_answer": {"type": "free_text"},
        },
    }


def _grounding_call(query: str, *, searched_max: int = 5) -> dict[str, object]:
    return {
        "tool_name": "librarian_search",
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
            "evidence": [_corpus_record()],
            "limitations": [],
        },
    }


def test_package_validator_requires_typed_book_ground_truth() -> None:
    content, ground_truth = _documents()
    backstory_bytes = _json_bytes(content)
    proposal = ground_truth["proposals"][0]  # type: ignore[index]
    proposal.pop("book_expectation")
    backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="typed book_expectation"):
        ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth))


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
            else "clarify" if "Alice's conversation" in request.message else "personal"
        )
        return _response(
            request,
            kind=kind,
            supporting_memory_ids=tuple(
                record.memory_id for record in service.list_active(account)
            ),
        )

    result = asyncio.run(
        replay_book_scenes(
            compile_book_replay_plan(backstory, ground_truth),
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
            else "clarify" if "Alice's conversation" in request.message else "personal"
        )
        return _response(
            request,
            kind=kind,
            searched_max=6 if kind == "infer" else 5,
            supporting_memory_ids=tuple(
                record.memory_id for record in _service.list_active(_account)
            ),
        )

    result = asyncio.run(
        replay_book_scenes(
            compile_book_replay_plan(backstory, ground_truth),
            adoption=adoption,
            ground_truth_bytes=ground_truth_bytes,
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
        scene.ground_truth_result == "passes_hard_gates" for scene in result.scenes[1:]
    )


def test_book_replay_rejects_wrong_scene_topology() -> None:
    backstory, ground_truth, _ = _models()
    invalid = backstory.model_copy(update={"scenes": backstory.scenes[:2]})

    with pytest.raises(ValueError):
        compile_book_replay_plan(invalid, ground_truth)


def test_production_chat_path_receives_props_but_not_ground_truth() -> None:
    backstory, ground_truth, _ = _models()
    from apps.backend import chat_turn

    async def reflection(prompt, *_args, **_kwargs):
        from src.linger.orchestration.turn_context import active_memories

        supporting_memory_ids = tuple(record.memory_id for record in active_memories())
        payload = json.loads(prompt)
        line = payload["muse_turn"]["user_message"]
        serialized = json.dumps(payload)
        assert "expected_outcomes" not in serialized
        assert "safe_ceiling_chapter" not in serialized
        if "quote" in line:
            # `librarian_route` records the inference exchange and reports the
            # routed ceiling. Both are how the boundary reaches the runner now
            # that inference runs inside Muse's own turn.
            _record_boundary(
                BoundaryInferenceDecision(
                    outcome="candidate",
                    work_id="pg11",
                    book_version_id="pg11-v01b38ea4",
                    chapter_number=5,
                    confidence=0.92,
                    authorization_basis="memory_supported",
                    supporting_memory_ids=supporting_memory_ids,
                    supporting_evidence_ids=(SUPPORT_ID,),
                )
            )
            return ReflectionRelease(
                reply=f"The passage says {QUOTE} That uncertainty can echo change.",
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                librarian_grounding_calls=(
                    _route_call(ceiling=5),
                    _grounding_call(line),
                ),
                evidence_ids=(SUPPORT_ID,),
            )
        if "Alice's conversation" in line:
            _record_boundary(
                BoundaryInferenceDecision(
                    outcome="uncertain",
                    confidence=0.4,
                    reason_code="insufficient_context",
                )
            )
            return ReflectionRelease(
                reply=CLARIFICATION,
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                librarian_grounding_calls=(_route_clarification_call(),),
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
                return_value=EmotionalBoundaryAssessment(decision="continue_reflection")
            ),
        ),
        patch.object(chat_turn, "reflection_reply", side_effect=reflection),
    ):
        result = asyncio.run(
            replay_book_scenes(
                compile_book_replay_plan(backstory, ground_truth),
                chat_handler=chat_turn.run_chat_turn,
            )
        )

    # Boundary inference itself runs inside Muse's own turn, which stubbing
    # `reflection_reply` bypasses — `test_boundary_observability.py` covers it
    # against the real routed path. What this test pins is that the production
    # chat hand-off carries Props but no Ground truth, and that the runner
    # grades the routed boundary that hand-off reports.
    assert all(
        scene.ground_truth_result == "matches_proposal" for scene in result.scenes
    )
    assert [scene.boundary_decision for scene in result.scenes] == [
        "infer",
        "clarify",
        "not_applicable",
    ]
    assert result.scenes[0].boundary_handoff_content_free is True
    assert result.scenes[1].boundary_handoff_content_free is True


@pytest.fixture(scope="module")
def replay_observed():
    backstory, truth, _ = _models()
    plan = compile_book_replay_plan(backstory, truth)

    async def handler(request, service, account):
        kind = (
            "infer"
            if "quote" in request.message
            else "clarify" if "Alice's conversation" in request.message else "personal"
        )
        return _response(
            request,
            kind=kind,
            supporting_memory_ids=tuple(
                record.memory_id for record in service.list_active(account)
            ),
        )

    return plan, asyncio.run(replay_book_scenes(plan, chat_handler=handler))


@pytest.mark.parametrize(
    "objective_ids",
    [
        ("grounded_book_reflection",),
        ("spoiler_boundary_clarification",),
        tuple(reversed(BOOK_OBJECTIVE_IDS)),
    ],
)
def test_replay_each_supported_selection(objective_ids):
    from pydantic_ai.models.test import TestModel

    backstory, truth, _ = _models(objective_ids)
    plan = compile_book_replay_plan(backstory, truth)

    async def handler(request, service, account):
        kind = (
            "infer"
            if "quote" in request.message
            else "clarify" if "Alice's conversation" in request.message else "personal"
        )
        return _response(
            request,
            kind=kind,
            supporting_memory_ids=tuple(
                record.memory_id for record in service.list_active(account)
            ),
        )

    result = asyncio.run(
        replay_book_scenes(
            plan,
            chat_handler=handler,
            run_semantic_review=True,
            semantic_model=TestModel(
                custom_output_args={
                    "disclosed_evidence_ids": [],
                    "explanation": "No later fact disclosed.",
                }
            ),
        )
    )
    assert result.objective_ids == objective_ids
    assert {grade.proposal_id for scene in result.scenes for grade in scene.grades} == {
        proposal.proposal_id for proposal in truth.proposals
    }
    assert all(grade.hard_pass for scene in result.scenes for grade in scene.grades)
    assert all(
        review.status == "pass"
        for scene in result.scenes
        for review in scene.semantic_spoiler_results
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("work_id", "wrong-work"),
        ("book_version_id", "wrong-version"),
        ("chapter_id", "wrong-chapter"),
        ("chapter_number", 9),
        ("source_sha256", "f" * 64),
        ("source_lines", (1, 2)),
        ("location", "another occurrence"),
        ("text", "Extra text: " + QUOTE),
    ],
)
def test_equal_quote_with_wrong_source_fails(replay_observed, field, value):
    from evals.synthetic_journals.book_replay import _grade_proposal

    plan, run = replay_observed
    observed = run.scenes[0]
    call = observed.grounding_calls[0]
    wrong = call.evidence[0].model_copy(update={field: value})
    observed = observed.model_copy(
        update={"grounding_calls": (call.model_copy(update={"evidence": (wrong,)}),)}
    )
    proposal = next(
        item
        for item in plan.scenes[0].proposals
        if item.objective_id == "grounded_book_reflection"
    )
    grade = _grade_proposal(plan.scenes[0], proposal, observed)
    assert not grade.hard_pass
    assert "retrieval_used_unpermitted_evidence" in grade.failures


def test_inference_must_use_the_authorised_prop(replay_observed):
    from evals.synthetic_journals.book_replay import _grade_proposal

    plan, run = replay_observed
    observed = run.scenes[0].model_copy(
        update={"boundary_support_memory_ids": ("another-account-memory",)}
    )
    assert all(
        "boundary_memory_support_differs_from_authorised_props"
        in _grade_proposal(plan.scenes[0], proposal, observed).failures
        for proposal in plan.scenes[0].proposals
    )


@pytest.mark.parametrize("valid_question", [True, False])
def test_application_clarification_is_graded_against_the_route_question(replay_observed, valid_question):
    from evals.synthetic_journals.book_replay import _grade_proposal

    plan, run = replay_observed
    observation = run.scenes[1].model_copy(update={
        "release_source": "application_clarification",
        "reply": CLARIFICATION if valid_question else "An unrelated reply?",
    })
    for proposal in plan.scenes[1].proposals:
        grade = _grade_proposal(plan.scenes[1], proposal, observation)
        assert grade.hard_pass is valid_question
        if not valid_question:
            assert "response_not_released_from_allowed_source" in grade.failures


def test_reader_confirmed_scope_requires_matching_trusted_context(replay_observed):
    from evals.synthetic_journals.book_replay import _grade_proposal

    content, truth = _documents(("grounded_book_reflection",))
    truth["book_scene_facts"][0]["scope"] = {
        "kind": "reader_confirmed",
        "work_id": "pg11",
        "book_version_id": "pg11-v01b38ea4",
        "safe_ceiling_chapter": 5,
    }
    truth["book_scene_facts"][0]["basis_spans"] = []
    plan = compile_book_replay_plan(
        SyntheticBackstory.model_validate_json(json.dumps(content)),
        ProposedGroundTruth.model_validate_json(json.dumps(truth)),
    )
    observed = replay_observed[1].scenes[0]
    case = plan.scenes[0]
    assert (
        "reader_confirmed_scope_differs_from_ground_truth"
        in _grade_proposal(case, case.proposals[0], observed).failures
    )
    context = ContextResolution(
        status="confirmed",
        work_id="pg11",
        work_title="Alice's Adventures in Wonderland",
        book_version_id="pg11-v01b38ea4",
        chapter_max=5,
        boundary_source="reader_confirmed",
        boundary_authorization_basis="explicit_progress",
        explanation="The reader explicitly confirmed chapter five.",
    )
    assert _grade_proposal(
        case,
        case.proposals[0],
        observed.model_copy(update={"context_resolution": context}),
    ).hard_pass


def test_route_no_match_is_not_a_search():
    from evals.synthetic_journals.book_replay import (
        _grounding_observations,
        _route_outcome,
    )

    response = SimpleNamespace(
        inspection=SimpleNamespace(
            librarian_grounding=[
                {
                    "tool_name": "librarian_route",
                    "response": {"kind": "no_match", "request_id": "arbitrary"},
                }
            ]
        )
    )
    assert _grounding_observations(response) == ()
    assert _route_outcome(response)["kind"] == "no_match"


def test_passage_retrieval_records_exact_scope_without_a_chapter():
    from evals.synthetic_journals.book_replay import _grounding_observations
    from src.linger.contracts.librarian import PassageScope

    call = _grounding_call("Quote the Caterpillar's question.")
    call["response"]["searched_scope"] = PassageScope(
        work_id="pg11", book_version_id="pg11-v01b38ea4",
        evidence_ids=(SUPPORT_ID,),
    ).model_dump(mode="json")
    response = SimpleNamespace(inspection=SimpleNamespace(librarian_grounding=[call]))
    observation, = _grounding_observations(response)
    assert observation.searched_max_chapter is None
    assert observation.searched_passage_ids == (SUPPORT_ID,)
    assert observation.evidence[0].evidence_id == SUPPORT_ID


def test_passage_route_is_outside_existing_chapter_objectives(replay_observed):
    from evals.synthetic_journals.book_replay import (
        BookEvaluationOutput, _boundary_decision, _grade_proposal, _route_outcome,
    )
    from src.linger.contracts.librarian import RoutedPassages

    route = RoutedPassages(
        work_id="pg11", book_version_id="pg11-v01b38ea4",
        evidence_ids=(SUPPORT_ID,), request_id="route-passages",
        title="Alice's Adventures in Wonderland", routing_confidence=1,
        boundary_confidence=1, selection_basis="resolved_book_identity",
    )
    route_call = {
        "tool_name": "librarian_route", "response": route.model_dump(mode="json"),
    }
    response = SimpleNamespace(inspection=SimpleNamespace(librarian_grounding=[route_call]))
    observed_route = _route_outcome(response)
    assert observed_route == route.model_dump(mode="json")
    assert "max_chapter_inclusive" not in observed_route
    decision = _boundary_decision(observed_route)
    assert decision == "passages"
    for calls in (
        [route_call, _route_clarification_call()],
        [_route_clarification_call(), route_call],
    ):
        response.inspection.librarian_grounding = calls
        assert _route_outcome(response)["kind"] == "clarification"
    plan, run = replay_observed
    observation = run.scenes[0].model_copy(update={
        "boundary_decision": decision, "routed_ceiling": None,
        "routed_passage_ids": route.evidence_ids,
    })
    grades = tuple(
        _grade_proposal(plan.scenes[0], proposal, observation)
        for proposal in plan.scenes[0].proposals
    )
    for grade in grades:
        assert not grade.hard_pass
        assert grade.failures == ("passage_scope_outside_chapter_objective",)
    observation = observation.model_copy(update={
        "grades": grades, "ground_truth_result": "differs_from_proposal",
    })
    output = BookEvaluationOutput.model_validate(
        observation.model_dump(include=set(BookEvaluationOutput.model_fields))
    )
    assert output.boundary_decision == "passages"
    assert BookEvaluationOutput.model_validate_json(output.model_dump_json()) == output
    with patch(
        "evals.synthetic_journals.book_replay._replay_book_scene",
        new=AsyncMock(side_effect=(observation, *run.scenes[1:])),
    ):
        replayed = asyncio.run(replay_book_scenes(plan, chat_handler=AsyncMock()))
    assert replayed.scenes[0].boundary_decision == "passages"
    assert replayed.scenes[0].ground_truth_result == "differs_from_proposal"


def test_passage_handoff_keeps_only_verified_identifiers(replay_observed):
    from evals.synthetic_journals.book_replay import _boundary_handoff_is_content_free
    from src.linger.agents.librarian.models import PassageInferenceDecision
    from src.linger.contracts.librarian import RoutedPassages

    decision = PassageInferenceDecision(
        outcome="passages", work_id="pg11", book_version_id="pg11-v01b38ea4",
        confidence=1, supporting_statement_ids=("reader-1",),
        supporting_evidence_ids=(SUPPORT_ID,), passage_evidence_ids=(SUPPORT_ID,),
    )
    route = RoutedPassages(
        request_id="route-synthetic", title="Alice's Adventures in Wonderland",
        work_id=decision.work_id, book_version_id=decision.book_version_id,
        routing_confidence=1, boundary_confidence=1,
        evidence_ids=decision.passage_evidence_ids,
        selection_basis="resolved_book_identity",
    ).model_dump(mode="json")
    exchange = replay_observed[1].scenes[0].agent_exchanges[0].model_copy(
        update={"output": decision.model_dump(mode="json")}
    )
    assert _boundary_handoff_is_content_free("passages", route, (exchange,))
    assert _boundary_handoff_is_content_free(
        "clarify", _route_clarification_call()["response"], (exchange,)
    )
    assert not _boundary_handoff_is_content_free(
        "passages", route | {"text": QUOTE}, (exchange,)
    )
    assert not _boundary_handoff_is_content_free(
        "passages", route | {"evidence_ids": ["different-paragraph"]}, (exchange,)
    )


def test_private_support_uses_only_the_correlated_exchange(replay_observed):
    from evals.synthetic_journals.book_replay import _boundary_support_observations

    _, run = replay_observed
    exchange = run.scenes[0].agent_exchanges[0]
    unrelated = exchange.model_copy(
        update={"correlation_id": "another-route", "output": {}}
    )
    assert (
        _boundary_support_observations(
            (unrelated, exchange),
            _route_call()["response"],
        )
        == run.scenes[0].boundary_support_evidence
    )
    forged = exchange.model_copy(
        update={
            "output": exchange.output
            | {
                "supporting_evidence_ids": [SUPPORT_ID, "unknown-source"],
            }
        }
    )
    assert _boundary_support_observations((forged,), _route_call()["response"]) == ()


@pytest.mark.parametrize("reverse", [False, True])
def test_replay_clarification_precedes_routed_work(reverse):
    from evals.synthetic_journals.book_replay import _route_outcome

    calls = [_route_call(), _route_clarification_call()]
    if reverse:
        calls.reverse()
    response = SimpleNamespace(inspection=SimpleNamespace(librarian_grounding=calls))
    assert _route_outcome(response)["kind"] == "clarification"


def test_stale_adoption_fails_before_chat(replay_observed):
    plan, _ = replay_observed
    encoded = plan.ground_truth.model_dump_json().encode()
    adoption = build_ground_truth_adoption(
        plan.ground_truth, encoded, reviewer_id="test-reviewer"
    )
    handler = AsyncMock()
    with pytest.raises(ValueError, match="exact file bytes"):
        asyncio.run(
            replay_book_scenes(
                plan,
                adoption=adoption,
                ground_truth_bytes=encoded + b"\n",
                chat_handler=handler,
            )
        )
    handler.assert_not_called()


def test_semantic_spoiler_result_is_separate_and_contains_paraphrase(replay_observed):
    from pydantic_ai.models.test import TestModel
    from evals.synthetic_journals.book_semantics import review_spoiler_semantics

    plan, run = replay_observed
    scene = plan.scenes[0]
    proposal = next(
        item
        for item in scene.proposals
        if item.objective_id == "spoiler_boundary_clarification"
    )
    model = TestModel(
        custom_output_args={
            "disclosed_evidence_ids": ["later"],
            "explanation": "The reply paraphrases the forbidden execution order.",
        }
    )
    result = asyncio.run(
        review_spoiler_semantics(
            scene,
            proposal,
            "The monarch demands that she be executed.",
            model=model,
        )
    )
    assert result.status == "fail"
    assert result.proposal_id == proposal.proposal_id
    assert result.independence == "non_independent_model_judge"
    assert all(grade.hard_pass for grade in run.scenes[0].grades)
    assert all(
        result.status == "not_run" for result in run.scenes[0].semantic_spoiler_results
    )
