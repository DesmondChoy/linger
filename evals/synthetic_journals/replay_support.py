"""Canonical supported-replay lookup for synthetic evaluation selections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplaySupport:
    """One runner available for one exact Objective selection."""

    name: str
    module: str
    accepts_semantic_review: bool = False


_CAPTURE = ReplaySupport(
    name="capture",
    module="evals.synthetic_journals.replay",
)
_CURATION = ReplaySupport(
    name="bounded curation",
    module="evals.synthetic_journals.curation_replay",
)
_CONTINUITY = ReplaySupport(
    name="session continuity",
    module="evals.synthetic_journals.continuity_replay",
)
_BOOK = ReplaySupport(
    name="book reflection",
    module="evals.synthetic_journals.book_replay",
    accepts_semantic_review=True,
)

_SUPPORTED_REPLAYS = {
    frozenset({"proactive_memory_surfacing"}): ReplaySupport(
        name="proactive memory surfacing",
        module="evals.synthetic_journals.surfacing_replay",
    ),
    frozenset({"reviewed_automatic_memory_capture"}): _CAPTURE,
    frozenset({"bounded_memory_curation"}): _CURATION,
    frozenset({"session_scoped_conversation_continuity"}): _CONTINUITY,
    frozenset({"grounded_book_reflection"}): _BOOK,
    frozenset({"spoiler_boundary_clarification"}): _BOOK,
    frozenset(
        {"grounded_book_reflection", "spoiler_boundary_clarification"}
    ): _BOOK,
}


def replay_support_for(objective_ids: Iterable[str]) -> ReplaySupport | None:
    """Return the runner for one exact, order-independent selection."""

    return _SUPPORTED_REPLAYS.get(frozenset(objective_ids))


__all__ = ["ReplaySupport", "replay_support_for"]
