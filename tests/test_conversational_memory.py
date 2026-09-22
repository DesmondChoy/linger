"""Application triggers for the conversational memory path."""

import asyncio

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.linger.agents.sculptor.surfacing_models import (
    AtTime,
    Defer,
    DoNotSurface,
    SurfaceNow,
)
from src.linger.contracts.curation import CuratedMemory
from src.linger.orchestration.conversational_memory import (
    curate_after_capture,
    prepare_surfacing_handoff,
    select_relevant_memories,
)
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)


NOW = datetime(2026, 9, 21, 10, tzinfo=timezone.utc)


def _memory(memory_id: str, text: str) -> CuratedMemory:
    return CuratedMemory(
        memory_id=memory_id,
        kind="original",
        text=text,
        source_memory_ids=(memory_id,),
        created_at=NOW.isoformat(),
    )


def test_relevant_memory_selection_is_positive_overlap_ranked_and_bounded() -> None:
    memories = tuple(
        [_memory("best", "I prefer tea while reading tea essays.")]
        + [_memory(f"match-{index:02}", "Tea is my reading drink.") for index in range(12)]
        + [_memory("irrelevant", "I take the bus to work.")]
    )

    selected = select_relevant_memories(
        "What tea should I make while reading?", memories
    )

    assert len(selected) == 12
    assert selected[0].memory_id == "best"
    assert "irrelevant" not in {item.memory_id for item in selected}


def test_surface_now_becomes_a_typed_handoff_with_exact_sources() -> None:
    memory = _memory("memory-1", "I prefer mint tea while reading.")
    decide = AsyncMock(
        return_value=SurfaceNow(
            decision="surface_now",
            source_memory_ids=(memory.memory_id,),
            suggestion="Mint tea may suit this reading session.",
            rationale="The saved preference is relevant now.",
        )
    )

    handoff = asyncio.run(
        prepare_surfacing_handoff(
            account_scope="private-account",
            current_context="I am choosing tea for this reading session.",
            memories=(memory,),
            now=NOW,
            decide=decide,
        )
    )

    assert handoff is not None
    assert handoff.suggestion == "Mint tea may suit this reading session."
    assert handoff.sources[0].evidence_id == memory.memory_id
    assert handoff.sources[0].excerpt == memory.text
    request = decide.await_args.args[0]
    assert request.account_scope == "private-account"
    assert request.context.current_context == "I am choosing tea for this reading session."


@pytest.mark.parametrize(
    "decision",
    [
        Defer(
            decision="defer",
            source_memory_ids=("memory-1",),
            suggestion="Consider mint tea later.",
            rationale="It is not useful yet.",
            reconsideration=AtTime(kind="time", at=datetime(2026, 9, 22, tzinfo=timezone.utc)),
        ),
        DoNotSurface(
            decision="do_not_surface",
            source_memory_ids=("memory-1",),
            reason="irrelevant",
            rationale="The preference does not help now.",
        ),
    ],
)
def test_defer_and_silence_create_no_muse_handoff(decision: object) -> None:
    memory = _memory("memory-1", "I prefer mint tea while reading.")
    assert asyncio.run(
        prepare_surfacing_handoff(
            account_scope="account",
            current_context="Tea for reading",
            memories=(memory,),
            now=NOW,
            decide=AsyncMock(return_value=decision),
        )
    ) is None


def test_new_capture_triggers_curation_with_new_and_relevant_prior_original() -> None:
    with TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        account = AccountContext("account")
        service.set_capture_enabled(account, True)
        prior = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I prefer mint tea while reading.",
                source_event_id="prior",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        created = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I now prefer jasmine tea while reading.",
                source_event_id="new",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        loop = AsyncMock()
        loop.return_value = SimpleNamespace(
            status="no_change",
            proposal_digest=None,
        )

        outcome = asyncio.run(
            curate_after_capture(
                account,
                created,
                created=True,
                service=service,
                run_loop=loop,
            )
        )

        assert outcome.status == "no_change"
        assert outcome.memory_ids == (created.memory_id, prior.memory_id)
        loop.assert_awaited_once_with(
            account,
            (created.memory_id, prior.memory_id),
            service=service,
        )


def test_idempotent_capture_and_unrelated_prior_memory_do_not_run_curation() -> None:
    with TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        account = AccountContext("account")
        service.set_capture_enabled(account, True)
        service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I commute by bus.",
                source_event_id="prior",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        captured = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I prefer jasmine tea while reading.",
                source_event_id="new",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        loop = AsyncMock()

        replay = asyncio.run(
            curate_after_capture(
                account, captured, created=False, service=service, run_loop=loop
            )
        )
        unrelated = asyncio.run(
            curate_after_capture(
                account, captured, created=True, service=service, run_loop=loop
            )
        )

        assert replay.status == "not_triggered"
        assert unrelated.status == "no_relevant_prior_memory"
        loop.assert_not_awaited()
