"""Shared sentence offsets for response review and revision."""

import re

_SENTENCE_BREAK = re.compile(r"(?<=[.?!])[\"'”’)\]*_]*(?=\s)|\n[ \t]*\n")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return sentence offsets without surrounding whitespace."""
    spans, start = [], 0
    for match in _SENTENCE_BREAK.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(text)))
    trimmed = []
    for start, end in spans:
        segment = text[start:end]
        if segment.strip():
            lead = len(segment) - len(segment.lstrip())
            trimmed.append((start + lead, start + len(segment.rstrip())))
    return trimmed
