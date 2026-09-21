"""Turn triage gates the tools Muse is offered during a real chat turn."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {"LINGER_MODEL": "google:gemini-2.5-flash", "GOOGLE_API_KEY": "test-key"},
):
    from apps.backend import chat_turn, sessions
    from apps.backend.schemas import ChatRequest
    get_settings()

from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from provenance_fixtures import review_with_audits

from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.models import ConnectionDecline, ConnectionExplorationResult
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.triage import TurnNeeds
from src.linger.contracts.turn import ReleaseScope
from src.linger.corpus.alice import BOOK
from src.linger.services.memory import AccountContext, AutomaticMemoryCandidate, MemoryPolicyService

BOOK_TOOLS = ["librarian_route", "librarian_search"]
ALL_TOOLS = [*BOOK_TOOLS, "serendipity_explore"]
ALL_INTENTS = ["find_connection", "get_recommendation", "recall_memory"]
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}
NOTHING = TurnNeeds(book_content="no", memory="none")
RECALL = TurnNeeds(book_content="no", memory="own_earlier_reflections")
REPLY = "That sounds worth staying with."
FINDING = {
    "code": "unsupported_claim",
    "applies_to": "response",
    "location": {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": REPLY},
    "explanation": "The reply asserts something it cannot support.",
}


def _review(decision: str, findings=(), **fields):
    def respond(messages, info: AgentInfo) -> ModelResponse:
        payload = next(part.content for message in messages for part in message.parts
                       if isinstance(part, UserPromptPart))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, review_with_audits(payload, {
            "findings": list(findings),
            "response_decision": decision,
            "emotional_boundary_decision": "not_required",
            "capture_decision": "no_candidate",
            **fields,
        }).model_dump(mode="json"))])
    return respond


class Turns:
    """Drive real chat turns with a scripted Muse and a scripted triage result."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.service = MemoryPolicyService(tmp_path)
        self.account = AccountContext("tool-exposure-test")
        self.offered: list[dict[str, list[str] | None]] = []
        self.retries: list[str] = []
        self.returned: list[object] = []
        self.explored: list[str] = []
        self.triaged: list[str] = []
        self.boundary = "continue_reflection"

        async def boundary(*args, **kwargs):
            return EmotionalBoundaryAssessment(decision=self.boundary)

        async def explore(brief):
            self.explored.append(brief.intent)
            return ConnectionExplorationResult(decision=ConnectionDecline(
                reason="no_matching_memory", safe_next_step="Reply without a stored reflection.",
            ))

        monkeypatch.setattr(chat_turn, "assess_emotional_boundary", boundary)
        monkeypatch.setattr("src.linger.agents.muse.tools.connection_exploration", explore)

    def triage(self, needs: TurnNeeds | Exception, *, delay: float = 0) -> None:
        async def triage_turn(current_line, **_):
            self.triaged.append(current_line)
            await asyncio.sleep(delay)
            if isinstance(needs, Exception):
                raise needs
            return needs

        self.monkeypatch.setattr(chat_turn, "triage_turn", triage_turn)

    def muse(self, *calls: ToolCallPart):
        """Issue each scripted tool call once, then reply plainly."""
        script = list(calls)

        def respond(messages, info: AgentInfo) -> ModelResponse:
            tools = {tool.name: tool for tool in info.function_tools}
            explore = tools.get("serendipity_explore")
            self.offered.append({
                "tools": sorted(tools),
                "intents": (
                    explore.parameters_json_schema["properties"]["intent"]["enum"]
                    if explore else None
                ),
            })
            self.retries = [
                part.model_response() for message in messages for part in message.parts
                if isinstance(part, RetryPromptPart)
            ]
            self.returned = [
                part.content for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart)
            ]
            if script:
                return ModelResponse(parts=[script.pop(0)])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "reply": REPLY, "evidence_uses": [], "memory": NO_MEMORY,
            })])
        return respond

    def run(self, muse, *, session_id="tool-exposure", message="It rained today.",
            provenance=None, **kwargs):
        with muse_chat_agent.override(model=FunctionModel(muse)):
            with provenance_agent.override(model=FunctionModel(provenance or _review("pass"))):
                return asyncio.run(chat_turn.run_chat_turn(
                    ChatRequest(session_id=session_id, message=message),
                    self.service, self.account, **kwargs,
                ))


@pytest.fixture
def turns(tmp_path, monkeypatch):
    yield Turns(tmp_path, monkeypatch)
    for session_id in ("tool-exposure", "tool-exposure-other"):
        sessions.clear(session_id)


def test_no_book_need_withholds_the_book_tools_and_blocks_a_call_to_them(turns) -> None:
    routed: list[str] = []
    turns.monkeypatch.setattr(
        "src.linger.agents.muse.tools.route_reader_message", lambda message: routed.append(message)
    )
    turns.triage(NOTHING)
    response = turns.run(turns.muse(ToolCallPart("librarian_route", {})))

    assert turns.offered[0] == {"tools": [], "intents": None}
    assert routed == [] and "librarian_route" in turns.retries[0]
    assert response.inspection.release.release_source == "muse_candidate"
    assert response.inspection.tool_exposure == {
        "triage": {"book_content": "no", "memory": "none"},
        "triage_failed": False, "tools": [], "pinned_intent": None,
    }


def test_pending_clarification_offers_book_tools_despite_triage(turns) -> None:
    sessions.set_pending_clarification("tool-exposure", sessions.PendingClarification(
        book_id=BOOK.work_id, book_title=BOOK.title, reason_code="missing_boundary",
    ))
    turns.triage(NOTHING)
    turns.run(turns.muse())
    assert turns.offered[0]["tools"] == BOOK_TOOLS


def test_confirmed_reading_offers_book_tools_despite_triage(turns) -> None:
    turns.triage(NOTHING)
    turns.run(turns.muse(), public_source_urls=(), initial_reading=ReleaseScope(
        work_id=BOOK.work_id, book_version_id=BOOK.book_version_id, chapter_max=5,
    ))
    assert turns.offered[0]["tools"] == BOOK_TOOLS


def test_recall_need_pins_the_intent_and_rejects_another(turns) -> None:
    turns.triage(RECALL)
    response = turns.run(turns.muse(
        ToolCallPart("serendipity_explore", {"intent": "find_connection"}),
        ToolCallPart("serendipity_explore", {"intent": "recall_memory"}),
    ))

    assert turns.offered[0] == {"tools": ["serendipity_explore"], "intents": ["recall_memory"]}
    assert "recall_memory" in turns.retries[0]
    assert turns.explored == ["recall_memory"]
    assert response.inspection.release.release_source == "muse_candidate"
    assert response.inspection.tool_exposure["pinned_intent"] == "recall_memory"


def test_a_tool_called_earlier_in_the_session_stays_offered_unpinned(turns) -> None:
    turns.triage(TurnNeeds(book_content="no", memory="unsure"))
    turns.run(turns.muse(ToolCallPart("serendipity_explore", {"intent": "find_connection"})))
    assert sessions.called_tools("tool-exposure") == {"serendipity_explore"}

    turns.triage(NOTHING)
    turns.offered.clear()
    turns.run(turns.muse())
    turns.run(turns.muse(), session_id="tool-exposure-other")
    assert turns.offered == [
        {"tools": ["serendipity_explore"], "intents": ALL_INTENTS},
        {"tools": [], "intents": None},
    ]

    sessions.clear("tool-exposure")
    assert sessions.called_tools("tool-exposure") == frozenset()


def test_a_declined_turn_does_not_widen_later_exposure(turns) -> None:
    turns.triage(TurnNeeds(book_content="no", memory="unsure"))
    response = turns.run(
        turns.muse(ToolCallPart("serendipity_explore", {"intent": "find_connection"})),
        provenance=_review("reject", findings=[FINDING]),
    )
    assert response.inspection.release.provenance_verdicts == ("reject",)
    assert sessions.called_tools("tool-exposure") == frozenset()


@pytest.mark.parametrize("failure", ("error", "timeout"))
def test_failed_triage_offers_every_tool_and_still_releases(turns, failure) -> None:
    if failure == "timeout":
        turns.monkeypatch.setattr(chat_turn, "TRIAGE_TIMEOUT_SECONDS", 0.01)
        turns.triage(NOTHING, delay=5)
    else:
        turns.triage(RuntimeError("provider down"))
    response = turns.run(turns.muse())

    assert turns.offered[0] == {"tools": ALL_TOOLS, "intents": ALL_INTENTS}
    assert response.inspection.release.release_source == "muse_candidate"
    assert response.inspection.tool_exposure["triage_failed"] is True
    assert [t["status"] for t in response.inspection.traces if t["agent"] == "Router"] == [
        "complete", "failed",
    ]


def test_emotional_boundary_stops_the_turn_before_triage(turns) -> None:
    turns.boundary = "apply_boundary"
    turns.triage(NOTHING)
    response = turns.run(turns.muse())

    assert response.inspection.release.release_source == "application_emotional_boundary"
    assert turns.triaged == [] and turns.offered == []
    assert response.inspection.tool_exposure is None


def test_revision_reuses_the_draft_exposure_after_one_triage(turns) -> None:
    reviews = iter((
        _review("revise", [FINDING]),
        _review("pass", finding_resolutions=[
            {"finding_index": 0, "status": "resolved", "explanation": "The claim is gone."},
        ]),
    ))

    def provenance(messages, info: AgentInfo) -> ModelResponse:
        return next(reviews)(messages, info)

    turns.triage(RECALL)
    response = turns.run(turns.muse(), provenance=provenance)

    assert response.inspection.release.provenance_verdicts == ("revise", "pass")
    assert turns.triaged == ["It rained today."]
    assert turns.offered == [
        {"tools": ["serendipity_explore"], "intents": ["recall_memory"]}
    ] * 2


def test_no_connection_grant_still_blocks_an_offered_exploration(turns, monkeypatch) -> None:
    from src.linger.orchestration.connection import connection_exploration

    def serendipity(messages, info):
        raise AssertionError("Serendipity must not run without a permitted source")

    monkeypatch.setattr("src.linger.agents.muse.tools.connection_exploration", connection_exploration)
    monkeypatch.setattr("src.linger.orchestration.connection.web_reach_permitted", lambda: False)
    monkeypatch.setattr(chat_turn, "web_reach_permitted", lambda: False)
    returned: list[object] = []
    script = turns.muse(ToolCallPart("serendipity_explore", {"intent": "recall_memory"}))

    def muse(messages, info: AgentInfo) -> ModelResponse:
        returned.extend(
            part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        return script(messages, info)

    turns.triage(RECALL)
    with serendipity_agent.override(model=FunctionModel(serendipity)):
        response = turns.run(muse)

    assert response.inspection.muse_turn["policy"]["allow_connection"] is False
    exploration = ConnectionExplorationResult.model_validate(returned[-1])
    assert exploration.decision.reason == "no_permitted_evidence"
    assert response.inspection.release.release_source == "muse_candidate"


def test_stored_memories_do_not_change_what_triage_exposes(turns) -> None:
    turns.service.set_capture_enabled(turns.account, True)
    turns.service.save_automatic(turns.account, AutomaticMemoryCandidate(
        text="My favourite tea is peppermint.", source_event_id="fixture",
        review_allows_capture=True, contains_sensitive_content=False,
    ))
    turns.service.set_capture_enabled(turns.account, False)
    turns.triage(NOTHING)
    response = turns.run(turns.muse())
    assert response.inspection.muse_turn["policy"]["allow_connection"] is True
    assert turns.offered[0]["tools"] == []
