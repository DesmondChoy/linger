"""Pre-ingested, spoiler-aware reference corpora for default library books.

The reader UI never calls this module. It is queried only after chat has
explicitly established a book title and reading boundary.
"""

import re

from .contracts import EvidenceBundle, EvidenceItem, LibrarianRequest


def evidence(evidence_id: str, title: str, location: str, chapter: int, excerpt: str, relevance: float) -> EvidenceItem:
    return EvidenceItem(evidence_id=evidence_id, source_title=title, location=location, chapter=chapter, excerpt=excerpt, relevance=relevance)


ALICE_EVIDENCE = (
    evidence("alice-ch2-identity", "Alice's Adventures in Wonderland", "Chapter 2 — The Pool of Tears", 2, "How queer everything is to-day!", 0.92),
    evidence("alice-ch3-rules", "Alice's Adventures in Wonderland", "Chapter 3 — A Caucus-Race and a Long Tale", 3, "Everybody has won, and all must have prizes.", 0.82),
    evidence("alice-ch4-change", "Alice's Adventures in Wonderland", "Chapter 4 — The Rabbit Sends in a Little Bill", 4, "One wasn't always growing larger and smaller.", 0.96),
    evidence("alice-ch5-identity", "Alice's Adventures in Wonderland", "Chapter 5 — Advice from a Caterpillar", 5, "Who are YOU? said the Caterpillar.", 0.99),
    evidence("alice-ch5-reason", "Alice's Adventures in Wonderland", "Chapter 5 — Advice from a Caterpillar", 5, "I can't explain myself, because I am not myself.", 0.99),
)

ANIMAL_FARM_EVIDENCE = (
    evidence("animal-ch1-comrades", "Animal Farm", "Chapter I", 1, "All men are enemies. All animals are comrades.", 0.94),
    evidence("animal-ch2-equality", "Animal Farm", "Chapter II", 2, "All animals are equal.", 0.99),
    evidence("animal-ch3-milk", "Animal Farm", "Chapter III", 3, "The milk and apples should be reserved for the pigs alone.", 0.97),
    evidence("animal-ch4-battle", "Animal Farm", "Chapter IV", 4, "Snowball was wounded by Jones's gun.", 0.7),
    evidence("animal-ch5-dogs", "Animal Farm", "Chapter V", 5, "Nine enormous dogs wearing brass-studded collars came bounding into the barn.", 0.9),
)

CORPORA = {
    "alice-s-adventures-in-wonderland": ALICE_EVIDENCE,
    "alice-adventures-in-wonderland": ALICE_EVIDENCE,
    "alice-wonderland": ALICE_EVIDENCE,
    "animal-farm": ANIMAL_FARM_EVIDENCE,
}


class Librarian:
    """Retrieve excerpts only from a registered corpus and confirmed range."""

    def has_corpus(self, book_id: str) -> bool:
        return book_id in CORPORA

    def retrieve(self, request: LibrarianRequest) -> EvidenceBundle:
        """Retrieve book excerpts within each request-scoped boundary."""
        words = set(re.findall(r"[a-z]+", request.query.lower()))
        selected: list[EvidenceItem] = []
        for scope in request.book_scopes:
            corpus = CORPORA.get(scope.book_id, ())
            allowed = [item for item in corpus if item.chapter is not None and item.chapter <= scope.chapter_max]
            matches = [
                item for item in allowed
                if words & set(re.findall(r"[a-z]+", f"{item.excerpt} {item.location}".lower()))
            ]
            # A narrow corpus can still support a thematic connection when the
            # reader's wording differs from the source's wording.
            selected.extend((matches[:3] if matches else allowed[-3:]))

        return EvidenceBundle(
            items=selected,
            retrieval_note="Only the reader-confirmed, request-scoped book boundary was searched.",
        )
