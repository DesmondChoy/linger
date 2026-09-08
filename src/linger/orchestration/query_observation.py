"""Evaluation-only record of the public-web queries Serendipity attempts.

Production never starts an observer, so `TurnInspection` keeps carrying no
query text and the released reply exposes no diagnostic content. The synthetic
replay opts in for one Scene at a time, which lets a grader compare the exact
outbound queries against the private wording a package declared off limits.
That check stays outside the running system: adopted Ground truth never reaches
the runtime, and the runtime never learns which wording a package forbade.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal

WebQueryVerdict = Literal["issued", "blocked"]


@dataclass(frozen=True)
class WebQueryObservation:
    """One attempted public-web query and the privacy gate's verdict on it."""

    query: str
    verdict: WebQueryVerdict


_observations: ContextVar[list[WebQueryObservation] | None] = ContextVar(
    "web_query_observations",
    default=None,
)


def begin_web_query_observation() -> Token[list[WebQueryObservation] | None]:
    """Start collecting outbound queries for one evaluated request."""
    return _observations.set([])


def record_web_query(query: str, verdict: WebQueryVerdict) -> None:
    """Record one attempted query when an evaluation is collecting them."""
    observed = _observations.get()
    if observed is not None:
        observed.append(WebQueryObservation(query=query, verdict=verdict))


def web_query_observations() -> tuple[WebQueryObservation, ...]:
    """Return the queries attempted in the current observed request."""
    observed = _observations.get()
    return tuple(observed) if observed is not None else ()


def reset_web_query_observation(
    token: Token[list[WebQueryObservation] | None],
) -> None:
    """Stop collecting and restore the previous observation state."""
    _observations.reset(token)
