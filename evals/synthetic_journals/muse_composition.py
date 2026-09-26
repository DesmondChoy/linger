"""Experimental Muse authoring format; production release still uses MuseCandidate."""

from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_ai import ModelRetry, RunContext

from src.linger.agents.contracts import StrictModel
from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.models import MemoryNomination, MuseCandidate
from src.linger.orchestration.turn_context import turn_evidence


class SourceReference(StrictModel):
    source_kind: Literal["book_corpus", "memory", "web"]
    evidence_id: str = Field(min_length=1, max_length=2_000)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


class SessionReference(StrictModel):
    source_kind: Literal["session_line"]
    quote: str = Field(min_length=12, max_length=2_000)


CompositionReference = Annotated[SourceReference | SessionReference, Field(discriminator="source_kind")]


class MuseSegment(StrictModel):
    """One complete claim, source limit, or sentence of the writer's own reflection."""

    kind: Literal["supported", "limit", "reflection"]
    text: str = Field(min_length=1, max_length=20_000)
    sources: tuple[CompositionReference, ...] = ()
    paragraph_break: bool = False

    @model_validator(mode="after")
    def check_sources(self) -> Self:
        if self.kind == "reflection" and self.sources:
            raise ValueError("reflection must not claim source support")
        if self.kind != "reflection" and not self.sources:
            raise ValueError("supported claims and limits must name their source records")
        if self.kind == "limit" and any(
            ref.source_kind == "session_line" or ref.exact_quote is not None
            for ref in self.sources
        ):
            raise ValueError("a limit names source records, without session lines or quotations")
        return self


class MuseComposition(StrictModel):
    segments: tuple[MuseSegment, ...] = Field(min_length=1, max_length=40)
    memory: MemoryNomination


COMPOSITION_INSTRUCTIONS = """
For this controlled authoring experiment, return MuseComposition using the
provided output tool. This replaces only the instructions to write a separate
reply plus copied supported_claims/limit_claims. All source, scope, quotation,
memory and reader-request obligations remain in force.

Write the answer once as ordered segments. Each segment contains a complete
substantive source claim (kind supported), a statement of what named sources
do not establish (kind limit), or your own non-factual reflection (kind
reflection). Split a positive claim from its limit or personal application.
Name every contributing source in sources. The application joins segment text
with spaces (or a blank line when paragraph_break is true) and uses that exact
text as its claim mapping; do not return a separate reply or repeat its words
as claim annotations. Include visible book locations and public Markdown links
in the segment text. Copy any quotation exactly from the canonical excerpt
into both text and that source reference's exact_quote. Session references
copy the reader's earlier words into quote. A limit must name a record also
used for a positive source account elsewhere in this answer.
Do not hide source claims in reflection.
""".strip()


def compile_composition(composition: MuseComposition) -> MuseCandidate:
    """Derive exact spans and canonical locations without deciding claim support."""
    reply = ""
    declarations: dict[tuple[str, str, str | None], dict] = {}
    limits: dict[tuple[str, str], list[str]] = defaultdict(list)
    for segment in composition.segments:
        reply += ("\n\n" if segment.paragraph_break else " ") if reply else ""
        reply += segment.text
        for ref in segment.sources:
            identity = ref.quote if ref.source_kind == "session_line" else ref.evidence_id
            if segment.kind == "limit":
                limits[(ref.source_kind, identity)].append(segment.text)
                continue
            quote = ref.exact_quote if isinstance(ref, SourceReference) else None
            key = ref.source_kind, identity, quote
            if key not in declarations:
                use: dict = {"source_kind": ref.source_kind, "supported_claims": []}
                if ref.source_kind == "session_line":
                    use["quote"] = ref.quote
                else:
                    use.update(evidence_id=ref.evidence_id, exact_quote=quote)
                    if ref.source_kind == "book_corpus":
                        record = turn_evidence().get(ref.evidence_id)
                        if record is None:
                            raise ModelRetry("Copy an authorized book evidence_id from the supplied records.")
                        use["source_location"] = record.location
                declarations[key] = use
            if segment.text not in declarations[key]["supported_claims"]:
                declarations[key]["supported_claims"].append(segment.text)
    for (kind, identity), claims in limits.items():
        matching = [use for (k, i, _), use in declarations.items() if (k, i) == (kind, identity)]
        if not matching:
            raise ModelRetry("Each limited source must also have a supported source account in this answer.")
        matching[0]["limit_claims"] = list(dict.fromkeys(claims))
    return MuseCandidate(reply=reply, evidence_uses=tuple(declarations.values()), memory=composition.memory)


def compose_muse_output(ctx: RunContext[None], composition: MuseComposition) -> MuseCandidate:
    """Output functions must explicitly apply Muse's normal candidate checks."""
    return validate_muse_output(ctx, compile_composition(composition))
