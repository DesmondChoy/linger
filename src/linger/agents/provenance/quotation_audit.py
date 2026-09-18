"""Project quoted reply spans and check reviewer-selected quotation bindings.

Pairing punctuation is not a source-use judgment. Semantic review still owns
classification, attribution and completeness, including single-quoted passages,
blockquotes and narrator text outside the paired quotation marks.
"""

from collections.abc import Callable
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.muse.models import EvidenceUse


class QuotedResponseSpan(StrictModel):
    """Exact interior of a balanced double-quote pair, using Python offsets."""

    span_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str


class QuotationAudit(StrictModel):
    """Semantic classification of one application-projected quotation span."""

    span_index: int = Field(ge=0)
    classification: Literal[
        "source_quote", "current_reader_wording", "title",
        "proposed_wording", "scare_quote",
    ] = Field(description=(
        "Judge this quotation in the complete reply. A quotation of a book, selected "
        "memory, web source or earlier session statement is source_quote even inside "
        "a question or a mapped claim. Other labels do not excuse source attribution."
    ))
    declaration_index: int | None = Field(default=None, ge=0, description=(
        "For source_quote, identify its current evidence declaration even when that "
        "declaration's quote is invalid or incomplete. Use null only when no associated "
        "declaration exists; then report a finding overlapping the quoted response span, "
        "not only a finding on an evidence declaration. A claim mapping alone does not "
        "bind a quotation. "
        "Use null for all other classifications."
    ))

    @model_validator(mode="after")
    def source_reference_matches_classification(self) -> "QuotationAudit":
        if self.classification != "source_quote" and self.declaration_index is not None:
            raise ValueError("only source_quote may reference an evidence declaration")
        return self


def quoted_response_spans(response: str) -> tuple[QuotedResponseSpan, ...]:
    """Locate balanced curly/ASCII double quotes without normalizing their text."""
    curly_starts: list[int] = []
    ascii_start: int | None = None
    pairs: list[tuple[int, int]] = []
    for offset, character in enumerate(response):
        if character == '“':
            curly_starts.append(offset)
        elif character == '”':
            if curly_starts:
                pairs.append((curly_starts.pop() + 1, offset))
        elif character == '"':
            if ascii_start is None:
                ascii_start = offset
            else:
                pairs.append((ascii_start + 1, offset))
                ascii_start = None
    return tuple(
        QuotedResponseSpan(span_index=index, start=start, end=end, text=response[start:end])
        for index, (start, end) in enumerate(sorted(pairs))
    )


def quote_is_bound(
    span: QuotedResponseSpan,
    response: str,
    use: EvidenceUse,
    *,
    quote_valid: bool = False,
    verified_session_lines: tuple[str, ...] = (),
) -> bool:
    """Check one already authorized declaration at this exact reply occurrence.

    For book/memory/web declarations, the caller supplies canonical quote validity
    computed from the current named source. This function never selects a source.
    Earlier session quotations retain their existing verified-reader-text contract.
    """
    if not span.text.strip() or response[span.start:span.end] != span.text:
        return False
    if use.source_kind == "session_line":
        quote = use.quote
        if not any(quote in line for line in verified_session_lines):
            return False
    else:
        quote = use.exact_quote
        if not quote_valid or quote is None:
            return False
    start = response.find(quote)
    while start != -1:
        if start <= span.start and span.end <= start + len(quote):
            return True
        start = response.find(quote, start + 1)
    return False


def quotation_audit_errors(
    *,
    response: str,
    audits: tuple[QuotationAudit, ...],
    evidence_uses: tuple[EvidenceUse, ...],
    valid_quote_declarations: set[int],
    verified_session_lines: tuple[str, ...],
    current_line: str,
    finding_overlaps: Callable[[int, int], bool],
    finding_on_declaration: Callable[[int], bool] | None = None,
) -> list[dict[str, JsonValue]]:
    """Validate complete quotation review against current application inputs."""
    spans = quoted_response_spans(response)
    errors: list[dict[str, JsonValue]] = []
    indices = [audit.span_index for audit in audits]
    if len(indices) != len(spans) or set(indices) != set(range(len(spans))):
        errors.append({
            "path": "quotation_audit", "value": indices,
            "error": "quotation_audit must assess every quoted response span exactly once",
            "current_target": [span.model_dump(mode="json") for span in spans],
        })
    for index, audit in enumerate(audits):
        if not 0 <= audit.span_index < len(spans):
            continue
        span = spans[audit.span_index]
        if audit.classification == "current_reader_wording":
            if not span.text or span.text not in current_line:
                errors.append({
                    "path": f"quotation_audit[{index}].classification",
                    "value": audit.classification,
                    "error": "current_reader_wording must occur exactly in the current reader Line",
                    "current_target": span.model_dump(mode="json"),
                })
            continue
        if audit.classification != "source_quote":
            continue
        declaration = audit.declaration_index
        if declaration is not None and not 0 <= declaration < len(evidence_uses):
            errors.append({
                "path": f"quotation_audit[{index}].declaration_index",
                "value": declaration,
                "error": "Reference a current evidence declaration, or use null for an undeclared quotation",
                "current_target": span.model_dump(mode="json"),
            })
            continue
        bound = declaration is not None and quote_is_bound(
            span, response, evidence_uses[declaration],
            quote_valid=declaration in valid_quote_declarations,
            verified_session_lines=verified_session_lines,
        )
        declaration_finding = (
            declaration is not None
            and finding_on_declaration is not None
            and finding_on_declaration(declaration)
        )
        if not bound and not declaration_finding and not finding_overlaps(span.start, span.end):
            errors.append({
                "path": f"quotation_audit[{index}].declaration_index",
                "value": declaration,
                "error": (
                    "This source quotation is not fully covered at this reply occurrence "
                    "by its declared, canonically bound exact_quote or verified session quote. "
                    "Keep the existing declaration index even when its quote is invalid or incomplete; "
                    "report a current response finding on that declaration or overlapping this quotation. "
                    "Use null only when no associated declaration exists. With null, a finding on an "
                    "evidence declaration cannot cover this quotation: the finding must overlap its "
                    "current response span. Claim "
                    "mapping alone or a matching fragment elsewhere does not cover it."
                ),
                "current_target": span.model_dump(mode="json"),
            })
    return errors


def source_quote_interiors(
    spans: tuple[QuotedResponseSpan, ...],
    audits: tuple[QuotationAudit, ...],
) -> tuple[str, ...]:
    """Extract source-quote obligations from an already input-validated review.

    These strings are repair constraints, not source identities or authorization.
    They say nothing about whether narrator text or a requested quotation is complete.
    """
    by_index = {span.span_index: span.text for span in spans}
    return tuple(dict.fromkeys(
        by_index[audit.span_index]
        for audit in audits
        if audit.classification == "source_quote" and audit.span_index in by_index
    ))
