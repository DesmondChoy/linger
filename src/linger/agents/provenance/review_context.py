"""Request-scoped binding of the candidate-review input for Provenance's validator."""

from __future__ import annotations

import contextvars

from src.linger.agents.provenance.models import ProvenanceInput

_review_input: contextvars.ContextVar[ProvenanceInput | None] = contextvars.ContextVar(
    "provenance_review_input", default=None
)


def set_review_input(value: ProvenanceInput) -> contextvars.Token:
    """Bind the application-validated review input for the current run."""
    return _review_input.set(value)


def review_input() -> ProvenanceInput | None:
    return _review_input.get()


def reset_review_input(token: contextvars.Token) -> None:
    _review_input.reset(token)
