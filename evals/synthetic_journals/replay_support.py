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
_CAPTURE_CURATION = ReplaySupport(
    name="capture and bounded curation",
    module="evals.synthetic_journals.capture_curation_replay",
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
_CONNECTION = ReplaySupport(
    name="connection and restraint",
    module="evals.synthetic_journals.connection_replay",
)
_CONNECTION_CURATION = ReplaySupport(
    name="bounded curation and cross-source connection",
    module="evals.synthetic_journals.connection_curation_replay",
)
_RETRIEVAL = ReplaySupport(
    name="longitudinal retrieval",
    module="evals.synthetic_journals.retrieval_replay",
)
_LINE_ATTACK = ReplaySupport(
    name="Line attacks: reply and memory capture",
    module="evals.synthetic_journals.line_attack_replay",
)

_MEMORY_LOOP = ReplaySupport(
    name="memory curation and recall loop",
    module="evals.synthetic_journals.memory_loop_replay",
)

MEMORY_LOOP_RUN_CONFIGURATION_ID = "memory-curation-recall-loop"

_SUPPORTED_REPLAYS = {
    frozenset({"cross_source_tentative_connection"}): _CONNECTION,
    frozenset({"weak_evidence_safe_decline"}): _CONNECTION,
    frozenset({"cross_source_tentative_connection", "weak_evidence_safe_decline"}): _CONNECTION,
    frozenset({"bounded_memory_curation", "cross_source_tentative_connection"}): _CONNECTION_CURATION,
    frozenset({"reviewed_automatic_memory_capture"}): _CAPTURE,
    frozenset({"sensitive_inference_and_capture_veto"}): _CAPTURE,
    frozenset({"bounded_memory_curation"}): _CURATION,
    frozenset({"reviewed_automatic_memory_capture", "bounded_memory_curation"}): _CAPTURE_CURATION,
    frozenset({"session_scoped_conversation_continuity"}): _CONTINUITY,
    frozenset({"longitudinal_memory_retrieval"}): _RETRIEVAL,
    frozenset({"longitudinal_memory_retrieval", "untrusted_content_injection_resistance"}): _RETRIEVAL,
    frozenset({"reviewed_automatic_memory_capture", "untrusted_content_injection_resistance"}): _LINE_ATTACK,
    frozenset(
        {"session_scoped_conversation_continuity", "longitudinal_memory_retrieval"}
    ): _RETRIEVAL,
    frozenset({"grounded_book_reflection"}): _BOOK,
    frozenset({"spoiler_boundary_clarification"}): _BOOK,
    frozenset(
        {"grounded_book_reflection", "spoiler_boundary_clarification"}
    ): _BOOK,
}


def replay_support_for(
    objective_ids: Iterable[str],
    run_configuration_ids: Iterable[str] = (),
) -> ReplaySupport | None:
    """Return the runner for one exact, order-independent selection.

    A Scenario that declares the memory-loop run configuration is an experiment
    over its Objective, so it selects that runner and no Objective default.
    """

    selection = frozenset(objective_ids)
    if MEMORY_LOOP_RUN_CONFIGURATION_ID in run_configuration_ids:
        return (
            _MEMORY_LOOP
            if selection == frozenset({"longitudinal_memory_retrieval"})
            else None
        )
    return _SUPPORTED_REPLAYS.get(selection)


__all__ = ["MEMORY_LOOP_RUN_CONFIGURATION_ID", "ReplaySupport", "replay_support_for"]
