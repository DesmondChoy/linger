"""Muse, the conversational agent behind the chat endpoint.

Instructions plus two tools: `librarian_search`, which lets Muse ground its
replies in the confirmed book's actual text, and `serendipity_explore`, which
lets Muse propose tentative, evidence-backed connections.
"""

from pydantic_ai import ModelRetry, RunContext, Tool

from src.linger.agents.build import build_agent
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.prompt import INSTRUCTIONS
from src.linger.agents.muse.tools import librarian_search, serendipity_explore
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.turn_context import turn_evidence


muse_chat_agent = build_agent(
    INSTRUCTIONS,
    name="Muse",
    output_type=MuseCandidate,
    tools=[Tool(librarian_search), Tool(serendipity_explore, sequential=True)],
    retries={"tools": 1, "output": 3},
)


def validate_exact_quote_declarations(output: MuseCandidate) -> MuseCandidate:
    """Reject quote metadata that does not describe visible reply text."""
    if any(
        evidence.exact_quote is not None
        and evidence.exact_quote not in output.reply
        for evidence in output.evidence_uses
    ):
        raise ModelRetry(
            "Each exact_quote must occur character for character in reply. "
            "Rewrite that wording as an unquoted paraphrase and set exact_quote "
            "to null. Do not attempt an approximate quotation."
        )
    return output


def _available_evidence() -> dict[str, EvidenceRecord]:
    """Snapshot the application-owned evidence shared across this turn."""
    return dict(turn_evidence())


@muse_chat_agent.output_validator
def validate_muse_output(
    _ctx: RunContext[None], output: MuseCandidate
) -> MuseCandidate:
    """Retry citation-copy errors while the model can still repair its output."""
    validate_exact_quote_declarations(output)
    available = _available_evidence()
    for declared in output.evidence_uses:
        record = available.get(declared.evidence_id)
        if record is None:
            raise ModelRetry(
                "Every evidence_id must exactly match book evidence authorised "
                "for this turn."
            )
        if declared.source_location != record.location:
            raise ModelRetry(
                "Each source_location must be copied character for character "
                "from the matching Librarian evidence record."
            )
        if (
            declared.exact_quote is not None
            and declared.exact_quote not in record.text
        ):
            raise ModelRetry(
                "Each exact_quote must also occur character for character in "
                "the matching Librarian evidence text. Rewrite that wording "
                "as an unquoted paraphrase and set exact_quote to null. Do not "
                "attempt an approximate quotation."
            )
    return output
