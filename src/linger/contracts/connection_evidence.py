"""Frozen source records shared by discovery and independent release review."""

import re
from typing import Annotated, Literal

from pydantic import Field

from src.linger.agents.contracts import StrictModel

# Untrusted-page delimiters (OWASP LLM01); no attribute, since evidence_id already carries the URL and a page could break out of one.
_UNTRUSTED_WEB_PAGE_OPEN = "<untrusted_web_page>\n"
_UNTRUSTED_WEB_PAGE_CLOSE = "\n</untrusted_web_page>"
# Case- and whitespace-insensitive, so a page can't smuggle a look-alike delimiter past the wrapper.
_UNTRUSTED_TAG_PATTERN = re.compile(r"(?i)<(\s*/?\s*)untrusted_web_page")
_UNTRUSTED_TAG_MIN_MATCH_LEN = len("<untrusted_web_page")
# Worst-case escaping growth: one inserted backslash per minimal-length match in an 8000-char excerpt.
_UNTRUSTED_WEB_PAGE_MAX_OVERHEAD = (
    len(_UNTRUSTED_WEB_PAGE_OPEN)
    + len(_UNTRUSTED_WEB_PAGE_CLOSE)
    + 8_000 // _UNTRUSTED_TAG_MIN_MATCH_LEN
)


def wrap_untrusted_web_excerpt(excerpt: str) -> str:
    """Wrap web page text in untrusted-page delimiters, escaping any look-alike tag."""
    safe_excerpt = _UNTRUSTED_TAG_PATTERN.sub(r"<\\\1untrusted_web_page", excerpt)
    return f"{_UNTRUSTED_WEB_PAGE_OPEN}{safe_excerpt}{_UNTRUSTED_WEB_PAGE_CLOSE}"


class WebConnectionEvidence(StrictModel):
    """One retrievable public-web record returned by Exa."""

    source_kind: Literal["web"] = "web"
    evidence_id: str = Field(min_length=1, max_length=2_000)
    title: str = Field(min_length=1, max_length=500)
    # Sized for a full-length raw excerpt plus Muse's untrusted-page wrapper.
    excerpt: str = Field(min_length=1, max_length=8_000 + _UNTRUSTED_WEB_PAGE_MAX_OVERHEAD)
    trust_level: Literal["external"] = "external"


class MemoryConnectionEvidence(StrictModel):
    """One active record authorized by the account-scoped memory service."""

    source_kind: Literal["memory"] = "memory"
    evidence_id: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=8_000)
    trust_level: Literal["account_scoped"] = "account_scoped"



ConnectionSourceEvidence = Annotated[
    MemoryConnectionEvidence | WebConnectionEvidence,
    Field(discriminator="source_kind"),
]
