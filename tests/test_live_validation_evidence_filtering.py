"""A mixed book/session-line candidate must not crash the live-validation helper."""

import os
import unittest
from unittest.mock import patch

with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from evals.librarian.live_validation import _book_corpus_evidence_uses

from src.linger.agents.muse.models import (
    BookEvidenceUse,
    MuseCandidate,
    NoMemoryCandidate,
    SessionLineUse,
)

EVIDENCE_ID = "pg11-v01b38ea4-ch02-ln0010-0011"


def mixed_candidate() -> MuseCandidate:
    return MuseCandidate(
        reply="A reply mixing book and session-line support.",
        evidence_uses=(
            BookEvidenceUse(
                source_kind="book_corpus",
                evidence_id=EVIDENCE_ID,
                source_location="Chapter 2 — The Pool of Tears, source lines 10-11",
                exact_quote=None,
            ),
            SessionLineUse(
                source_kind="session_line",
                quote="I lost my job last spring",
            ),
        ),
        memory=NoMemoryCandidate(
            kind="no_memory_candidate", reason_code="transient_or_low_signal"
        ),
    )


class BookCorpusEvidenceUsesTests(unittest.TestCase):
    def test_keeps_only_book_corpus_declarations(self) -> None:
        filtered = _book_corpus_evidence_uses(mixed_candidate())

        self.assertEqual(1, len(filtered))
        self.assertEqual(EVIDENCE_ID, filtered[0].evidence_id)

    def test_session_line_only_candidate_yields_no_crash_and_no_entries(self) -> None:
        candidate = MuseCandidate(
            reply="A reply supported only by the reader's own words.",
            evidence_uses=(
                SessionLineUse(
                    source_kind="session_line",
                    quote="I lost my job last spring",
                ),
            ),
            memory=NoMemoryCandidate(
                kind="no_memory_candidate", reason_code="transient_or_low_signal"
            ),
        )

        self.assertEqual([], _book_corpus_evidence_uses(candidate))


if __name__ == "__main__":
    unittest.main()
