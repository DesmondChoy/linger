"""Contracts and the no-tool boundary for Sculptor surfacing decisions."""

import asyncio
import json
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.sculptor.models import CuratableMemory
from src.linger.agents.sculptor.surfacing_models import (
    SURFACING_DECISION_ADAPTER,
    AtTime,
    Defer,
    DoNotSurface,
    OnCondition,
    PriorSurfacing,
    SurfaceNow,
    SurfacingContext,
    SurfacingInput,
)
from src.linger.agents.sculptor.surfacing_prompt import PROMPT_FINGERPRINT
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.agents.sculptor.surfacing_agent import build_surfacing_agent
    from src.linger.orchestration.surfacing import (
        InvalidSurfacingProposal,
        propose_surfacing,
        validate_surfacing_decision,
    )


NOW = datetime(2026, 9, 10, 10, tzinfo=timezone(timedelta(hours=8)))


def test_package_import_and_injected_grading_do_not_initialize_a_model():
    source = textwrap.dedent(
        """
        from datetime import datetime, timezone
        from unittest.mock import patch

        with patch(
            "src.linger.agents.build.build_model",
            side_effect=AssertionError("unexpected model initialization"),
        ) as build_model:
            import evals.synthetic_journals.models
            from evals.sculptor.surfacing_harness import (
                SurfacingExpectation, grade_surfacing_expectation,
            )
            from src.linger.agents.sculptor.surfacing_models import (
                SurfacingContext, SurfacingInput,
            )

            request = SurfacingInput(
                account_scope="account",
                context=SurfacingContext(
                    now=datetime(2026, 9, 10, tzinfo=timezone.utc),
                    current_context="The reader has returned.",
                ),
                memories=(),
            )
            expected = SurfacingExpectation(
                case_kind="unsupported",
                decision="do_not_surface",
                reason="insufficient_evidence",
                semantic_criteria=("Do not invent supporting facts.",),
            )
            grade = grade_surfacing_expectation(
                request,
                {
                    "decision": "do_not_surface",
                    "source_memory_ids": (),
                    "reason": "insufficient_evidence",
                    "rationale": "No memories support a useful suggestion.",
                },
                expected,
            )
            assert not grade.hard_failures
            build_model.assert_not_called()
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _input() -> SurfacingInput:
    return SurfacingInput(
        account_scope="private-test-account",
        context=SurfacingContext(
            now=NOW,
            current_context="The reader has returned before tomorrow's book club.",
        ),
        memories=(
            CuratableMemory(
                memory_id="memory-1",
                text="I want to revisit my notes before book club on September 11.",
            ),
        ),
    )


def _suggestion() -> SurfaceNow:
    return SurfaceNow(
        decision="surface_now",
        source_memory_ids=("memory-1",),
        suggestion="Revisit your saved book-club notes before tomorrow's meeting.",
        rationale="The reader wanted to revisit these notes before that meeting.",
    )


def _defer() -> Defer:
    return Defer(
        decision="defer",
        source_memory_ids=("memory-1",),
        suggestion="Revisit the book-club notes.",
        rationale="The reader has deferred this until the evening.",
        reconsideration=AtTime(kind="time", at=NOW + timedelta(hours=8)),
    )


@pytest.mark.parametrize(
    ("response", "seed"),
    [
        (_suggestion(), 0),
        (_defer(), 1),
        (
            DoNotSurface(
                decision="do_not_surface",
                source_memory_ids=("memory-1",),
                reason="repetition",
                rationale="The same suggestion was already shown without a change.",
            ),
            2,
        ),
    ],
)
def test_typed_decisions_run_without_tools_and_keep_account_private(response, seed):
    model = TestModel(custom_output_args=response, seed=seed)
    recorder = SceneTranscriptRecorder()
    with bind_evaluation_transcript_sink(recorder):
        result = asyncio.run(
            propose_surfacing(_input(), agent=build_surfacing_agent(model))
        )

    assert result == response
    parameters = model.last_model_request_parameters
    assert parameters is not None
    assert parameters.function_tools == []
    assert len(parameters.output_tools) == 3
    assert len(recorder.exchanges) == 1
    exchange = recorder.exchanges[0]
    payload = json.loads(exchange.input_prompt)
    assert set(payload) == {"context", "memories"}
    assert set(payload["memories"][0]) == {"memory_id", "text"}
    assert payload["context"]["now"] == NOW.isoformat()
    assert "private-test-account" not in exchange.input_prompt
    assert exchange.role == "Sculptor"
    assert exchange.stage == "surfacing"
    assert exchange.input_origin == "Application"
    assert exchange.output_receiver == "Application"
    assert exchange.prompt_fingerprint == PROMPT_FINGERPRINT
    assert exchange.input_contract.endswith("surfacing_models.SurfacingInput")
    assert exchange.output_contract.endswith("surfacing_models.SurfacingDecision")
    assert exchange.status == "success"


def test_empty_memories_allow_silence_without_invented_sources():
    request = _input().model_copy(update={"memories": ()})
    response = DoNotSurface(
        decision="do_not_surface",
        reason="insufficient_evidence",
        rationale="No authorized memories support a suggestion.",
    )
    assert validate_surfacing_decision(request, response) == response
    with pytest.raises(InvalidSurfacingProposal, match="unknown memories"):
        validate_surfacing_decision(request, _suggestion())


def test_defer_accepts_an_observable_condition():
    response = _defer().model_copy(
        update={
            "reconsideration": OnCondition(
                kind="condition", condition="The reader confirms a new meeting date."
            )
        }
    )
    assert validate_surfacing_decision(_input(), response) == response


@pytest.mark.parametrize("decision", ["surface_now", "defer", "do_not_surface"])
def test_every_decision_rejects_unknown_sources(decision):
    response = {
        "surface_now": _suggestion(),
        "defer": _defer(),
        "do_not_surface": DoNotSurface(
            decision="do_not_surface", reason="irrelevant", rationale="Not relevant."
        ),
    }[decision].model_copy(update={"source_memory_ids": ("unavailable",)})
    with pytest.raises(InvalidSurfacingProposal, match="unknown memories"):
        validate_surfacing_decision(_input(), response)


@pytest.mark.parametrize("at", [NOW, NOW - timedelta(seconds=1)])
def test_defer_requires_a_strictly_future_time(at):
    response = _defer().model_copy(
        update={"reconsideration": AtTime(kind="time", at=at)}
    )
    with pytest.raises(InvalidSurfacingProposal, match="after now"):
        validate_surfacing_decision(_input(), response)


@pytest.mark.parametrize("changes", [{"suggestion": "  "}, {"delivered": True}])
def test_orchestration_rejects_invalid_model_output(changes):
    agent = AsyncMock()
    agent.run.return_value = SimpleNamespace(
        output={**_suggestion().model_dump(), **changes}
    )
    with pytest.raises(InvalidSurfacingProposal, match="malformed output"):
        asyncio.run(propose_surfacing(_input(), agent=agent))


def test_pure_checker_revalidates_preconstructed_model_instances():
    response = _suggestion().model_copy(update={"source_memory_ids": ()})
    with pytest.raises(InvalidSurfacingProposal, match="malformed output"):
        validate_surfacing_decision(_input(), response)


@pytest.mark.parametrize("decision", [_suggestion(), _defer()])
def test_suggestions_require_nonempty_unique_source_ids(decision):
    for source_ids in [(), ("memory-1", "memory-1"), (" ",)]:
        with pytest.raises(ValidationError):
            SURFACING_DECISION_ADAPTER.validate_python(
                {**decision.model_dump(), "source_memory_ids": source_ids}
            )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SurfacingContext(
            now=NOW.replace(tzinfo=None), current_context="Reading"
        ),
        lambda: SurfacingContext(now=NOW, current_context=" \n "),
        lambda: PriorSurfacing(
            surfacing_id="prior-1",
            suggestion="Read",
            outcome="surfaced",
            occurred_at=NOW.replace(tzinfo=None),
        ),
        lambda: PriorSurfacing(
            surfacing_id="prior-1",
            suggestion="Read",
            outcome="dismissed",
            occurred_at=NOW,
            suppress_until=(NOW + timedelta(days=1)).replace(tzinfo=None),
        ),
        lambda: AtTime(kind="time", at=NOW.replace(tzinfo=None)),
        lambda: OnCondition(kind="condition", condition=" "),
    ],
)
def test_context_feedback_and_reconsideration_reject_naive_times_or_blank_text(factory):
    with pytest.raises(ValidationError):
        factory()


def test_history_is_bounded_unique_and_never_in_the_future():
    prior = PriorSurfacing(
        surfacing_id="prior-1",
        suggestion="Read the notes.",
        outcome="surfaced",
        occurred_at=NOW - timedelta(hours=1),
    )
    with pytest.raises(ValidationError, match="unique"):
        SurfacingContext(now=NOW, current_context="Reading", history=(prior, prior))
    with pytest.raises(ValidationError, match="after now"):
        SurfacingContext(
            now=NOW,
            current_context="Reading",
            history=(
                prior.model_copy(update={"occurred_at": NOW + timedelta(seconds=1)}),
            ),
        )
    with pytest.raises(ValidationError):
        SurfacingContext(
            now=NOW,
            current_context="Reading",
            history=tuple(
                prior.model_copy(update={"surfacing_id": str(i)}) for i in range(21)
            ),
        )


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
def test_suppression_must_end_after_the_recorded_feedback(delta):
    with pytest.raises(ValidationError, match="after the prior surfacing"):
        PriorSurfacing(
            surfacing_id="prior-1",
            suggestion="Read",
            outcome="dismissed",
            occurred_at=NOW,
            suppress_until=NOW + delta,
        )


def test_input_enforces_memory_bound_and_unique_ids():
    request = _input()
    for memories in [
        request.memories * 2,
        tuple(CuratableMemory(memory_id=str(i), text="Memory") for i in range(13)),
        (CuratableMemory(memory_id="memory-1", text="  "),),
    ]:
        with pytest.raises(ValidationError):
            SurfacingInput(
                account_scope=request.account_scope,
                context=request.context,
                memories=memories,
            )


def test_failed_model_run_records_a_fixed_failure_code_without_exception_text():
    def fail(_messages, _info):
        raise RuntimeError("private model exception")

    recorder = SceneTranscriptRecorder()
    with bind_evaluation_transcript_sink(recorder):
        with pytest.raises(RuntimeError, match="private model exception"):
            asyncio.run(
                propose_surfacing(
                    _input(), agent=build_surfacing_agent(FunctionModel(fail))
                )
            )
    exchange = recorder.exchanges[0]
    assert exchange.status == "failure"
    assert exchange.failure_code == "sculptor_surfacing_model_failed"
    assert "private model exception" not in exchange.model_dump_json()
