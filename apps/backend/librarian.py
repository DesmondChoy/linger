"""Spoiler-bounded retrieval from immutable, checked-in book corpora."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.linger.corpus.alice import BOOK
from src.linger.corpus.book import BookCorpus, ChapterFrontMatter, parse_chapter_markdown

from src.linger.services.memory import AccountContext, MemoryPolicyService

from .contracts import (
    EvidenceBundle,
    EvidenceItem,
    LibrarianRequest,
    MemoryEvidenceItem,
)


TOKEN = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
STOP_WORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and",
    "are", "as", "at", "be", "because", "been", "before", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had", "has",
    "have", "he", "her", "hers", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "she",
    "so", "that", "the", "their", "them", "then", "there", "they", "this",
    "to", "too", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your",
}


class CorpusScopeError(ValueError):
    """Raised before chapter text is opened when a corpus scope is invalid."""


@dataclass(frozen=True)
class CorpusRegistration:
    book: BookCorpus
    root: Path


CORPORA = {
    BOOK.work_id: CorpusRegistration(book=BOOK, root=BOOK.default_output),
}


@dataclass(frozen=True)
class Paragraph:
    text: str
    source_lines: tuple[int, int]


def _terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN.findall(text)
        if len(token) > 1 and token.casefold() not in STOP_WORDS
    }


def _normalise(text: str) -> str:
    return " ".join(token.casefold() for token in TOKEN.findall(text))


def _paragraphs(metadata: ChapterFrontMatter, markdown_body: str) -> tuple[Paragraph, ...]:
    """Return exact source paragraphs and their inclusive Gutenberg line ranges."""
    try:
        _, source_body = markdown_body.split("\n\n", maxsplit=1)
    except ValueError as exc:
        raise CorpusScopeError(f"{metadata.chapter_id} is missing its Markdown heading") from exc

    lines = source_body.splitlines()
    paragraphs: list[Paragraph] = []
    start: int | None = None
    for index in range(len(lines) + 1):
        line = lines[index] if index < len(lines) else ""
        if line and start is None:
            start = index
        if not line and start is not None:
            end = index - 1
            source_start = metadata.body_lines[0] + start
            source_end = metadata.body_lines[0] + end
            paragraphs.append(
                Paragraph(
                    text="\n".join(lines[start:index]),
                    source_lines=(source_start, source_end),
                )
            )
            start = None
    return tuple(paragraphs)


def _score(query_terms: set[str], paragraph: str) -> float:
    """Return a bounded lexical score; zero means no textual anchor exists."""
    if not query_terms:
        return 0.0
    overlap = len(query_terms & _terms(paragraph))
    if overlap == 0:
        return 0.0
    # One real textual anchor clears the 0.5 baseline. More matched terms raise
    # confidence, while later strategy benchmarks can replace this scorer.
    return min(1.0, 0.5 + 0.5 * overlap / min(len(query_terms), 4))


def _load_catalog(registration: CorpusRegistration) -> dict[str, object]:
    catalog = json.loads((registration.root / "catalog.json").read_text(encoding="utf-8"))
    book = registration.book
    if catalog.get("work_id") != book.work_id or catalog.get("book_version_id") != book.book_version_id:
        raise CorpusScopeError("catalog identity does not match its registered corpus")
    return catalog


class Librarian:
    """Retrieve authorised internal evidence from books and reader memories."""

    def has_corpus(self, work_id: str) -> bool:
        return work_id in CORPORA

    def supports_revision(self, work_id: str, book_version_id: str) -> bool:
        registration = CORPORA.get(work_id)
        return registration is not None and registration.book.book_version_id == book_version_id

    def version_for(self, work_id: str) -> str | None:
        registration = CORPORA.get(work_id)
        return registration.book.book_version_id if registration else None

    def retrieve_memories(
        self,
        query: str,
        *,
        memory_service: MemoryPolicyService,
        account: AccountContext,
        max_results: int = 5,
    ) -> tuple[MemoryEvidenceItem, ...]:
        """Search only active memories resolved inside the trusted account.

        Account identity and the service handle are application-owned inputs;
        neither is accepted from an agent or tool argument. An exact duplicate
        of the current cue is excluded because it cannot form a second side of
        a useful connection.
        """
        query_terms = _terms(query)
        normalised_query = _normalise(query)
        candidates = [
            record
            for record in memory_service.list_active(account)
            if _normalise(record.text) != normalised_query
        ]
        ranked = sorted(
            candidates,
            key=lambda record: (
                len(query_terms & _terms(record.text)),
                record.updated_at,
                record.memory_id,
            ),
            reverse=True,
        )[:max_results]
        denominator = max(len(query_terms), 1)
        return tuple(
            MemoryEvidenceItem(
                evidence_id=record.memory_id,
                excerpt=record.text,
                capture_type=record.capture_type,
                recorded_at=record.updated_at,
                relevance=min(1.0, len(query_terms & _terms(record.text)) / denominator),
            )
            for record in ranked
        )

    def retrieve(self, request: LibrarianRequest) -> EvidenceBundle:
        """Search eligible chapter bodies without opening a forbidden chapter."""
        query_terms = _terms(request.query)
        selected: list[EvidenceItem] = []

        for scope in request.book_scopes:
            registration = CORPORA.get(scope.work_id)
            if registration is None or registration.book.book_version_id != scope.book_version_id:
                raise CorpusScopeError(
                    f"unregistered corpus revision: {scope.work_id}/{scope.book_version_id}"
                )

            catalog = _load_catalog(registration)
            chapters = catalog.get("chapters")
            if not isinstance(chapters, list):
                raise CorpusScopeError("catalog chapters must be a list")

            # The metadata-only catalogue is filtered first. A chapter above the
            # trusted ceiling is never opened and therefore cannot leak text.
            eligible = [
                chapter
                for chapter in chapters
                if isinstance(chapter, dict)
                and isinstance(chapter.get("chapter_number"), int)
                and chapter["chapter_number"] <= scope.chapter_max
            ]
            for chapter in eligible:
                relative_path = chapter.get("path")
                if not isinstance(relative_path, str):
                    raise CorpusScopeError("catalog chapter path is invalid")
                metadata, markdown_body = parse_chapter_markdown(
                    (registration.root / relative_path).read_text(encoding="utf-8")
                )
                if (
                    metadata.work_id != scope.work_id
                    or metadata.book_version_id != scope.book_version_id
                    or metadata.chapter_number != chapter["chapter_number"]
                ):
                    raise CorpusScopeError("chapter identity does not match its search scope")

                for paragraph in _paragraphs(metadata, markdown_body):
                    relevance = _score(query_terms, paragraph.text)
                    if relevance < request.retrieval_score_threshold:
                        continue
                    start, end = paragraph.source_lines
                    selected.append(
                        EvidenceItem(
                            evidence_id=f"{metadata.chapter_id}-ln{start:04d}-{end:04d}",
                            work_id=metadata.work_id,
                            book_version_id=metadata.book_version_id,
                            chapter_id=metadata.chapter_id,
                            source_title=registration.book.title,
                            location=(
                                f"Chapter {metadata.chapter_number} — {metadata.title}, "
                                f"source lines {start}-{end}"
                            ),
                            chapter=metadata.chapter_number,
                            source_sha256=metadata.source_sha256,
                            source_lines=paragraph.source_lines,
                            excerpt=paragraph.text,
                            relevance=relevance,
                        )
                    )

        selected.sort(key=lambda item: (-item.relevance, item.chapter, item.source_lines[0]))
        diversified: list[EvidenceItem] = []
        per_chapter: dict[int, int] = {}
        for item in selected:
            if per_chapter.get(item.chapter, 0) >= 2:
                continue
            diversified.append(item)
            per_chapter[item.chapter] = per_chapter.get(item.chapter, 0) + 1
            if len(diversified) == request.max_results:
                break
        return EvidenceBundle(
            items=diversified,
            retrieval_note="Only exact text inside the reader-confirmed corpus revision and chapter boundary was searched.",
        )
