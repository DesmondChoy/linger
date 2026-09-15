"""Optional literal source spans for presentation-only quotation repairs."""

import re
from itertools import islice
from typing import Iterator


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
