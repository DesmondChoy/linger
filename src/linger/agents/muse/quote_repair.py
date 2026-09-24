"""Optional literal source spans for presentation-only quotation repairs."""

import re
from difflib import SequenceMatcher
from itertools import islice
from typing import Iterator

from src.linger.agents.muse.models import EvidenceUse
from src.linger.agents.provenance.quotation_audit import QuotedResponseSpan, quoted_response_spans, quote_is_bound


def retained_quotation_errors(
    *,
    response: str,
    evidence_uses: tuple[EvidenceUse, ...],
    reviewed_quotes: tuple[str, ...],
    source_texts: dict[int, str],
    valid_quotes: set[int],
    verified_session_lines: tuple[str, ...],
) -> list[dict[str, object]]:
    """Explain unbound, previously reviewed quotations without classifying new ones."""
    errors = []
    for span in quoted_response_spans(response):
        if not retained_source_quote(span.text, reviewed_quotes):
            continue
        if any(quote_is_bound(
            span, response, use, quote_valid=index in valid_quotes,
            verified_session_lines=verified_session_lines,
        ) for index, use in enumerate(evidence_uses)):
            continue
        sources = []
        for index, text in source_texts.items():
            use = evidence_uses[index]
            if use.source_kind == "session_line" or not any(
                _claim_covers_quote(response, claim, span) for claim in use.supported_claims
            ):
                continue
            source = {
                "declaration_index": index,
                "source_kind": use.source_kind,
                "evidence_id": use.evidence_id,
                "canonical_source_text": text,
            }
            suggestion = canonical_quote_suggestion(span.text, text)
            if suggestion is not None:
                source["suggested_quote"] = suggestion
            sources.append(source)
        errors.append({
            "path": "evidence_uses", "value": span.text,
            "quoted_response_text": span.text,
            "response_start": span.start, "response_end": span.end,
            "current_declared_sources": sources,
            "error": (
                "The first review identified this retained text as a source quotation. "
                "Its complete current quoted occurrence needs a canonically matching "
                "exact_quote declaration, or a verified session_line quote for earlier "
                "reader wording. A supported_claim mapping alone does not bind a quote. "
                "The listed sources are only your current mappings of this occurrence, "
                "not approved source assignments. A suggested_quote is an optional literal "
                "span to inspect, not an automatic correction or proof of attribution. "
                "Preserve the reader's requested quotation and complete claim mappings. "
                "For an optional fragment, a supported unquoted paraphrase is allowed. "
                "Do not introduce another altered or undeclared source quotation during repair. "
                "The next review checks completeness and attribution."
            ),
        })
    return errors


def unbound_source_quotation_errors(
    *,
    response: str,
    evidence_uses: tuple[EvidenceUse, ...],
    source_texts: dict[int, str],
    valid_quotes: set[int],
    verified_session_lines: tuple[str, ...],
    skip_starts: set[int] = frozenset(),
) -> list[dict[str, object]]:
    """Flag quoted wording that literally matches a source mapped over it but is not declared."""
    errors = []
    for span in quoted_response_spans(response):
        if span.start in skip_starts or any(quote_is_bound(
            span, response, use, quote_valid=index in valid_quotes,
            verified_session_lines=verified_session_lines,
        ) for index, use in enumerate(evidence_uses)):
            continue
        mapped = [
            (index, use) for index, use in enumerate(evidence_uses)
            if use.source_kind != "session_line"
            and any(_claim_covers_quote(response, claim, span) for claim in use.supported_claims)
        ]
        if any(_same_wording(use.exact_quote, span.text) for _, use in mapped if use.exact_quote):
            # A declared quote for this wording is checked, or reclassified, elsewhere.
            continue
        sources = []
        for index, use in mapped:
            text = source_texts.get(index)
            if text is None:
                continue
            suggestion = canonical_quote_suggestion(span.text, text)
            if suggestion is not None and not _heading_text(suggestion, text):
                sources.append({
                    "declaration_index": index,
                    "source_kind": use.source_kind,
                    "evidence_id": use.evidence_id,
                    "suggested_quote": suggestion,
                })
        if sources:
            errors.append({
                "path": "evidence_uses", "value": span.text,
                "quoted_response_text": span.text,
                "response_start": span.start, "response_end": span.end,
                "matching_declared_sources": sources,
                "error": (
                    "This quoted wording matches the canonical text of a source you mapped over it, "
                    "so it reads as a source quotation, but no exact_quote declaration binds it. "
                    "Either copy the complete quoted span into an exact_quote declaration for that "
                    "source (add another declaration with the same evidence_id for a second "
                    "fragment), or rewrite it as an unquoted paraphrase."
                ),
            })
    return errors


def _same_wording(declared: str, quoted: str) -> bool:
    def core(text: str) -> str:
        return " ".join(text.split()).strip('"“”').rstrip(".,;:!?…").strip()

    left, right = core(declared), core(quoted)
    return bool(left and right) and (left in right or right in left)


def _heading_text(fragment: str, source: str) -> bool:
    """A quoted title matches the source's heading, not its prose."""
    start = source.find(fragment)
    line_start = source.rfind("\n", 0, start) + 1
    line_end = source.find("\n", start + len(fragment))
    line = source[line_start:line_end if line_end >= 0 else len(source)].strip()
    return line.startswith(("#", "Title:")) or line.rstrip(".") == fragment.strip().rstrip(".")


def _claim_covers_quote(response: str, claim: str, span: QuotedResponseSpan) -> bool:
    start = response.find(claim)
    while start >= 0:
        if start <= span.start and span.end <= start + len(claim):
            return True
        start = response.find(claim, start + 1)
    return False


def incomplete_declared_quote_edges(response: str, use: EvidenceUse) -> tuple[QuotedResponseSpan, ...]:
    """Find punctuation-only underdeclarations; the caller verifies the source first."""
    if use.source_kind == "session_line" or use.exact_quote is None:
        return ()
    quote = use.exact_quote
    spans = quoted_response_spans(response)
    if any(quote_is_bound(span, response, use, quote_valid=True) for span in spans):
        return ()
    start = response.find(quote)
    while start >= 0:
        if not any(span.start <= start and start + len(quote) <= span.end for span in spans):
            return ()
        start = response.find(quote, start + 1)
    return tuple(span for span in spans if retained_source_quote(span.text, (quote,)))


def retained_source_quote(current: str, previous: tuple[str, ...]) -> bool:
    """Carry a reviewed source-quote obligation through terminal punctuation edits."""
    if current in previous:
        return True

    def core(text: str) -> str:
        return text.strip().rstrip(".,;:!?…").rstrip()

    current_core = core(current)
    return bool(current_core) and any(current_core == core(text) for text in previous)


def _source_matches(proposed: str, source: str) -> Iterator[re.Match[str]]:
    literal = r"\s+".join(re.escape(part) for part in proposed.split())
    start = r"(?<![\w.,:/’'-])" if proposed[0].isdigit() else r"(?<![\w’'-])"
    end = r"(?![\w’'-]|[.,:/]\d)" if proposed[-1].isdigit() else r"(?![\w’'-])"
    # Lookahead also counts overlapping occurrences when checking ambiguity.
    return re.finditer(r"(?=(" + start + literal + end + r"))", source)


def canonical_quote_suggestion(proposed: str, source: str) -> str | None:
    """Find one exact source span without changing words or interior punctuation."""
    original = proposed.strip()
    unquoted = original.strip('"“”').strip()
    core = unquoted.rstrip(".,;:!?").rstrip('"“”').strip()
    if len(core) < 12 or len(re.findall(r"\w+", core)) < 3:
        return None

    matches = list(islice(_source_matches(core, source), 2))
    if len(matches) != 1:
        return None
    core_start, core_end = matches[0].span(1)
    for variant in dict.fromkeys((original, unquoted, core)):
        for match in _source_matches(variant, source):
            start, end = match.span(1)
            if start <= core_start and end >= core_end:
                suggestion = match.group(1)
                return suggestion if len(suggestion) <= 2000 else None
    return None


def quote_copy_feedback(response: str, declared: str, source: str) -> dict[str, object]:
    """Show one unambiguous copy mismatch; never repair or approve a quotation."""
    canonical = canonical_quote_suggestion(declared, source)
    if canonical is None:
        return {}
    matches = []
    for span in quoted_response_spans(response):
        if len(span.text) > 2000:
            continue
        # Strip line prefixes only to locate a diagnostic, never for validation.
        lookup = re.sub(r"(?m)^[ \t]*>+[ \t]?", "", span.text)
        suggested = canonical_quote_suggestion(span.text, source)
        if suggested is None:
            suggested = canonical_quote_suggestion(lookup, source)
        if suggested is not None and retained_source_quote(suggested, (canonical,)):
            matches.append((span, suggested))
    if len(matches) != 1:
        return {}
    span, suggested = matches[0]

    def differences(current: str) -> list[dict[str, object]]:
        return [
            {"current_start": a, "current_end": b,
             "current_text": current[a:b], "source_text": suggested[c:d]}
            for tag, a, b, c, d in SequenceMatcher(
                None, current, suggested, autojunk=False,
            ).get_opcodes() if tag != "equal"
        ]

    return {"reply_quote_repair": {
        "current_reply_quote": span.text,
        "response_start": span.start, "response_end": span.end,
        "suggested_quote": suggested,
        "reply_differences": differences(span.text),
        "declaration_differences": differences(declared),
        "instruction": (
            "Inspect this complete quoted occurrence and its literal differences. "
            "If this canonical span covers the requested quotation, copy suggested_quote "
            "unchanged into both the reply occurrence and exact_quote. Preserve its "
            "line breaks without inserting Markdown prefixes between lines. Then "
            "copy supported_claims from the final reply. These differences describe "
            "text only; they do not approve attribution or waive any evidence check."
        ),
    }}
