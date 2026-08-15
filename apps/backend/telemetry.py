"""OpenTelemetry tracing for the agent pipeline.

`docs/specification.md` §8.1 requires one correlated trace per request spanning
the Muse, Librarian, Serendipity and Provenance invocations, recording agent
role, duration, status, failures, validation outcomes, Provenance verdicts and
revision count.

The same section forbids logging raw personal memories, full user or assistant
messages, photographs, raw book or web excerpts, credentials, API keys, and
sensitive-inference content. Logfire captures prompts and completions **by
default**, so `configure_telemetry` turns that off explicitly, and every
contract object reaches a span through one of the `*_attrs` projections below.

Those projections are allowlists: they name the safe fields rather than
stripping unsafe ones, so a field added to a contract stays invisible to
telemetry until someone adds it here deliberately.
"""

from typing import Any, Mapping

import logfire

from src.linger.agents.provenance.models import ProvenanceReview

from .config import get_settings
from .contracts import (
    ConnectionBrief,
    ContextResolution,
    EvidenceBundle,
    LibrarianRequest,
    MuseTurn,
    ReadingContext,
    TurnPolicy,
)

SERVICE_NAME = "linger-backend"


def configure_telemetry() -> None:
    """Start tracing. Must run before the agent singletons are imported.

    Muse, Provenance and Sculptor are built at module import time, so
    `instrument_pydantic_ai` has to be in effect before those imports run or it
    never sees them.

    Without a token nothing leaves the machine: spans are created and dropped,
    so the trace path stays exercised in local development without requiring an
    account.

    The token is read through `Settings` rather than from the environment,
    because nothing in this project loads `.env` into `os.environ` — Pydantic
    Settings reads that file itself. Letting Logfire pick the variable up on its
    own would work only when the token is exported by hand.
    """
    token = get_settings().logfire_token
    logfire.configure(
        token=token.get_secret_value() if token else None,
        send_to_logfire="if-token-present",
        service_name=SERVICE_NAME,
        console=False,
        # Logfire introspects calling source to label f-strings; it cannot when
        # frames lack source (exec, .pyc) and warns each time.
        inspect_arguments=False,
    )
    # §8.1: no prompts, completions, tool arguments, or images in telemetry.
    # Both default to True, so omitting either would capture chat content.
    logfire.instrument_pydantic_ai(
        include_content=False,
        include_binary_content=False,
    )


def policy_attrs(policy: TurnPolicy) -> dict[str, Any]:
    """All four fields are operational flags, safe by construction."""
    return policy.model_dump(mode="json")


def turn_attrs(turn: MuseTurn) -> dict[str, Any]:
    """Turn shape without the message. Length alone distinguishes turns."""
    attrs: dict[str, Any] = {
        "turn_id": turn.turn_id,
        "user_message_length": len(turn.user_message),
        "policy": policy_attrs(turn.policy),
    }
    if turn.reading_context is not None:
        attrs["reading_context"] = reading_context_attrs(turn.reading_context)
    return attrs


def reading_context_attrs(context: ReadingContext) -> dict[str, Any]:
    return {
        "work_id": context.work_id,
        "chapter_max": context.chapter_max,
        "boundary_source": context.boundary_source,
    }


def resolution_attrs(resolution: ContextResolution) -> dict[str, Any]:
    """`explanation` is prose shown to the reader, so it stays out."""
    return {
        "status": resolution.status,
        "work_id": resolution.work_id,
        "chapter_max": resolution.chapter_max,
        "boundary_source": resolution.boundary_source,
    }


def brief_attrs(brief: ConnectionBrief) -> dict[str, Any]:
    """`cue` is reader-derived text, so only its length is recorded."""
    return {
        "book_id": brief.book_id,
        "chapter_max": brief.chapter_max,
        "intent": brief.intent,
        "allowed_sources": sorted(brief.allowed_sources),
        "cue_length": len(brief.cue),
    }


def librarian_request_attrs(request: LibrarianRequest) -> dict[str, Any]:
    """`query` is reader-derived text, so only its length is recorded."""
    return {
        "purpose": request.purpose,
        "query_length": len(request.query),
        "book_scopes": [
            {"book_id": scope.book_id, "chapter_max": scope.chapter_max}
            for scope in request.book_scopes
        ],
    }


def evidence_attrs(bundle: EvidenceBundle) -> dict[str, Any]:
    """Which passages matched and how well, never what they say.

    `EvidenceItem.excerpt` is a raw book excerpt, named directly in §8.1.
    `retrieval_note` is model-authored prose and is excluded for the same reason.
    """
    return {
        "item_count": len(bundle.items),
        "evidence_ids": [item.evidence_id for item in bundle.items],
        "chapters": [item.chapter for item in bundle.items],
        "relevance": [item.relevance for item in bundle.items],
        "source_kinds": sorted({item.source_kind for item in bundle.items}),
    }


def review_attrs(review: ProvenanceReview) -> dict[str, Any]:
    """Verdicts and risk codes only.

    `RiskFinding.quote` is a verbatim span of the candidate response and
    `explanation` is model prose about it, so neither is recorded.
    """
    return {
        "response_decision": review.response_decision,
        "capture_decision": review.capture_decision,
        "finding_codes": [finding.code for finding in review.findings],
        "finding_count": len(review.findings),
        "contains_sensitive_content": review.contains_sensitive_content,
    }


def review_context_attrs(context: Mapping[str, object]) -> dict[str, Any]:
    """Shape of the Provenance payload, without any of its content.

    The payload embeds evidence excerpts and tool results, so this reports only
    which keys were populated.
    """
    return {
        "keys_present": sorted(key for key, value in context.items() if value is not None),
    }
