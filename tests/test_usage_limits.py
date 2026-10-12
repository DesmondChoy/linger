"""Explicit request and tool-call budgets on the chat-turn model runs."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from provenance_fixtures import review_with_audits
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend.contracts import ContextResolution, MuseDraftInput, MuseTurn, TurnPolicy
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BookRequestPlan,
    LibrarianBookRequestInput,
    LibrarianEventIdentificationInput,
)
from src.linger.agents.muse.agent import build_muse_agent
from src.linger.agents.muse.models import MuseCandidate, NoMemoryCandidate
from src.linger.agents.muse.skills import REFLECTION
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.serendipity.models import ConnectionDecline, ConnectionExplorationResult
from src.linger.orchestration import reflection as reflection_module
from src.linger.orchestration.boundary import (
    BOUNDARY_INFERENCE_REQUEST_LIMIT,
    EVENT_IDENTIFICATION_REQUEST_LIMIT,
    identify_reader_event,
    judge_spoiler_boundary,
)
from src.linger.orchestration.evidence_strength import (
    BOOK_REQUEST_REQUEST_LIMIT,
    EVIDENCE_ASSESSMENT_REQUEST_LIMIT,
    assess_book_evidence,
    plan_book_request,
)
from src.linger.orchestration.reflection import (
    MUSE_TOOL_CALL_LIMIT,
    reflection_reply,
)
from src.linger.orchestration.turn_context import (
    ToolExposure,
    reset_reader_message,
    reset_tool_exposure,
    set_reader_message,
    set_tool_exposure,
)

CUE = "Tell me something new."


def draft_input(message: str) -> str:
    return MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id="usage-limit-test",
            user_message=message,
            reading_context=None,
            policy=TurnPolicy(
                spoiler_ceiling=None,
                allow_retrieval=False,
                allow_connection=True,
                allow_memory_capture=False,
            ),
        ),
        context_resolution=ContextResolution(status="unknown", explanation="No reading context."),
    ).model_dump_json()


def candidate_payload(reply: str) -> dict:
    return MuseCandidate(
        reply=reply,
        memory=NoMemoryCandidate(kind="no_memory_candidate", reason_code="automatic_capture_disabled"),
    ).model_dump(mode="json")


def latest_input(messages) -> str:
    """The current call's own prompt, not an earlier one carried in history."""
    return next(
        part.content for message in reversed(messages) for part in reversed(message.parts)
        if isinstance(part, UserPromptPart)
    )


def declining_explore(counter: list[int]):
    """Stand in for the nested Serendipity run, recording each call."""

    async def explore(brief):
        counter.append(1)
        return ConnectionExplorationResult(decision=ConnectionDecline(
            reason="no_matching_memory", safe_next_step="Reply without a stored reflection.",
        ))

    return explore


def _pass_review(messages, info: AgentInfo) -> ModelResponse:
    payload = latest_input(messages)
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, review_with_audits(payload, {
        "findings": [],
        "response_decision": "pass",
        "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
    }).model_dump(mode="json"))])


def run_draft(muse, provenance, *, pinned_intent: str | None = None):
    message = set_reader_message(CUE)
    exposure = set_tool_exposure(
        ToolExposure(tools=frozenset(REFLECTION.tools), pinned_intent=pinned_intent)
    )
    try:
        return asyncio.run(reflection_reply(
            draft_input(CUE), [], muse=build_muse_agent(FunctionModel(muse)), provenance=provenance,
        ))
    finally:
        reset_tool_exposure(exposure)
        reset_reader_message(message)


def test_muse_draft_looping_past_the_tool_budget_ends_in_the_safe_decline(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        "src.linger.agents.muse.tools.connection_exploration", declining_explore(calls)
    )

    def respond(messages, info: AgentInfo) -> ModelResponse:
        # Never emits a final candidate: a model that keeps calling the same
        # tool forever rather than a bounded, legitimate turn.
        return ModelResponse(
            parts=[ToolCallPart("serendipity_explore", {"intent": "find_connection"})]
        )

    release = run_draft(respond, AsyncMock())

    assert release.release_source == "application_safe_decline"
    assert release.failure_stage == "muse_draft"
    assert release.failure_type == "model"
    assert len(calls) == MUSE_TOOL_CALL_LIMIT


def test_muse_request_budget_covers_a_repair_before_every_permitted_call(monkeypatch) -> None:
    """The worst legitimate shape: the pinned-intent check rejects a call before
    each of the permitted ones. A rejected call costs a request without spending
    tool-call budget, so a request limit sized only for successes would decline
    this turn instead of releasing it."""
    calls: list[int] = []
    monkeypatch.setattr(
        "src.linger.agents.muse.tools.connection_exploration", declining_explore(calls)
    )

    def respond(messages, info: AgentInfo) -> ModelResponse:
        if len(calls) >= MUSE_TOOL_CALL_LIMIT:
            return ModelResponse(parts=[ToolCallPart(
                info.output_tools[0].name, candidate_payload("A grounded thought."),
            )])
        rejected = sum(
            1 for message in messages for part in message.parts
            if part.__class__.__name__ == "RetryPromptPart"
        )
        intent = "find_connection" if rejected > len(calls) else "recall_memory"
        return ModelResponse(parts=[ToolCallPart("serendipity_explore", {"intent": intent})])

    release = run_draft(
        respond,
        build_provenance_agent(FunctionModel(_pass_review)),
        pinned_intent="find_connection",
    )

    assert release.release_source == "muse_candidate"
    assert len(calls) == MUSE_TOOL_CALL_LIMIT


def test_muse_revision_looping_past_the_tool_budget_ends_in_the_safe_decline(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        "src.linger.agents.muse.tools.connection_exploration", declining_explore(calls)
    )

    def review_respond(messages, info: AgentInfo) -> ModelResponse:
        # The draft always earns exactly one "revise" verdict; the revision
        # itself never completes, so Provenance is never asked again.
        payload = latest_input(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, review_with_audits(payload, {
            "findings": [{
                "code": "unsupported_claim",
                "applies_to": "response",
                "location": {
                    "kind": "structural", "source_field": "candidate.response", "path": "",
                },
                "explanation": "Remove the unsupported response claim.",
            }],
            "response_decision": "revise",
            "emotional_boundary_decision": "not_required",
            "capture_decision": "no_candidate",
        }).model_dump(mode="json"))])

    def muse_respond(messages, info: AgentInfo) -> ModelResponse:
        mode = json.loads(latest_input(messages))["mode"]
        if mode == "draft":
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, candidate_payload("Initial candidate"))]
            )
        # The revision keeps looping through the same tool rather than
        # producing a bounded, legitimate revised candidate.
        return ModelResponse(
            parts=[ToolCallPart("serendipity_explore", {"intent": "find_connection"})]
        )

    release = run_draft(muse_respond, build_provenance_agent(FunctionModel(review_respond)))

    assert release.release_source == "application_safe_decline"
    assert release.failure_stage == "muse_revision"
    assert release.failure_type == "model"
    assert len(calls) == MUSE_TOOL_CALL_LIMIT


def test_provenance_review_exceeding_its_request_budget_ends_in_the_safe_decline(monkeypatch) -> None:
    monkeypatch.setattr(reflection_module, "PROVENANCE_REVIEW_REQUEST_LIMIT", 0)

    def muse_respond(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, candidate_payload("A grounded thought."))]
        )

    # A budget of zero must block this request before the model ever answers;
    # if it did not, this otherwise-valid "pass" would release the candidate
    # instead of declining.
    release = run_draft(muse_respond, build_provenance_agent(FunctionModel(_pass_review)))

    assert release.release_source == "application_safe_decline"
    assert release.failure_stage == "provenance_review"
    assert release.failure_type == "model"


def test_nested_serendipity_agent_run_does_not_share_the_drafts_budget(monkeypatch) -> None:
    """Each `serendipity_explore` call starts its own fresh `Agent.run`, so a
    heavy nested run (many of its own requests) cannot starve or double-count
    against the parent Muse draft's own tool-call budget."""
    calls: list[int] = []

    async def explore(brief):
        calls.append(1)
        inner = Agent(FunctionModel(lambda _m, _i: ModelResponse(parts=[TextPart("done")])))
        for _ in range(5):
            await inner.run("go")
        return ConnectionExplorationResult(decision=ConnectionDecline(
            reason="no_matching_memory", safe_next_step="Reply without a stored reflection.",
        ))

    monkeypatch.setattr("src.linger.agents.muse.tools.connection_exploration", explore)

    def respond(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart("serendipity_explore", {"intent": "find_connection"})]
        )

    release = run_draft(respond, AsyncMock())

    assert release.release_source == "application_safe_decline"
    assert release.failure_stage == "muse_draft"
    assert len(calls) == MUSE_TOOL_CALL_LIMIT


BOOK_REQUEST_INPUT = LibrarianBookRequestInput(current_line=CUE, prior_reader_statements=())
LIBRARIAN_RUNS = {
    "boundary_inference": (
        BOUNDARY_INFERENCE_REQUEST_LIMIT,
        lambda agent: judge_spoiler_boundary(CUE, (), (), (), agent=agent),
    ),
    "event_identification": (
        EVENT_IDENTIFICATION_REQUEST_LIMIT,
        lambda agent: identify_reader_event(
            LibrarianEventIdentificationInput(
                current_line=CUE, prior_reader_statements=(), full_work_candidates=(),
            ),
            agent=agent,
        ),
    ),
    "book_request": (
        BOOK_REQUEST_REQUEST_LIMIT,
        lambda agent: plan_book_request(CUE, agent=agent),
    ),
    "evidence_assessment": (
        EVIDENCE_ASSESSMENT_REQUEST_LIMIT,
        lambda agent: assess_book_evidence(
            BookRequestPlan(parts=()), (), original_request=BOOK_REQUEST_INPUT, agent=agent,
        ),
    ),
}


@pytest.mark.parametrize("stage", sorted(LIBRARIAN_RUNS))
def test_librarian_reply_path_runs_stop_at_their_own_request_budget(stage) -> None:
    """A model answering a no-tool run with calls to tools it was never given
    earns a fresh retry prompt each time; without an explicit budget the run
    would keep going to PydanticAI's default of fifty requests."""
    limit, call = LIBRARIAN_RUNS[stage]
    requests: list[int] = []

    def ghost_tools(messages, info: AgentInfo) -> ModelResponse:
        requests.append(1)
        return ModelResponse(parts=[ToolCallPart(f"ghost_{len(requests)}", {})])

    with pytest.raises(UsageLimitExceeded):
        asyncio.run(call(build_librarian_agent(FunctionModel(ghost_tools))))
    assert len(requests) == limit
