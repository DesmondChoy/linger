"""Bounded source-local context for a rejected private excerpt; never a repair."""
from difflib import SequenceMatcher
import re


def literal_source_context(excerpt: str, source: str | None) -> str | None:
    """Return original source characters around a unique shared word sequence."""
    if not source or len(excerpt) > 800 or len(source) > 24000:
        return None
    attempted = excerpt.split()
    positions = list(re.finditer(r'\S+', source))
    if not attempted or len(positions) > 2048:
        return None
    words = [match.group() for match in positions]
    match = SequenceMatcher(None, attempted, words, autojunk=False).find_longest_match()
    if match.size < 3:
        return None
    anchor = words[match.b:match.b + match.size]
    if sum(words[i:i + match.size] == anchor for i in range(len(words) - match.size + 1)) != 1:
        return None
    start = positions[max(0, match.b - match.a - 3)].start()
    end = positions[min(len(positions) - 1, match.b + len(attempted) - match.a + 2)].end()
    return source[start:end] if end - start <= 1200 else None
