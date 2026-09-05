"""Spoiler-bounded retrieval from immutable, checked-in book corpora."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.linger.corpus import registry
from src.linger.corpus.book import ChapterFrontMatter, parse_chapter_markdown
from src.linger.corpus.registry import BookClarification, CorpusRegistration, ResolvedBook
from src.linger.contracts.librarian import EvidenceRecord, SelectionBasis

from .contracts import EvidenceBundle, EvidenceItem, LibrarianRequest


TOKEN = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
EVIDENCE_ID = re.compile(
    r"^(?P<chapter_id>[a-z0-9]+(?:-[a-z0-9]+)*-ch\d+)-ln"
    r"(?P<start>\d+)-(?P<end>\d+)$"
)
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
# Single-word catalog cues that are also common English words: matching one
# of these must not bear routing confidence, unlike a distinctive name like
# "dormouse" that happens to also be one word.
GENERIC_CUE_WORDS = {
    "baby", "cook", "crab", "duck", "eggs", "five", "garden", "kitchen",
    "mouse", "seven", "wood",
}


class CorpusScopeError(ValueError):
    """Raised before chapter text is opened when a corpus scope is invalid."""


@dataclass(frozen=True)
class Paragraph:
    text: str
    source_lines: tuple[int, int]


@dataclass(frozen=True)
class RegisteredCorpusScope:
    """Metadata-only identity and extent of one immutable registered work."""

    work_id: str
    book_version_id: str
    title: str
    max_chapter: int


# Below this, a matched catalog word explains too little of the message to
# justify routing (e.g. one incidental word inside unrelated reflection).
ROUTING_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class RoutingDecision:
    """A routed work, the confidence the evidence supports, and how it was selected."""

    scope: RegisteredCorpusScope
    confidence: float
    basis: SelectionBasis


@dataclass(frozen=True)
class WorkRouteCandidate:
    """Metadata-only possible work; weak matches never select a work alone."""

    scope: RegisteredCorpusScope
    strength: Literal["strong", "weak"]
    reasons: tuple[str, ...]


def _terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in TOKEN.findall(text)
        if len(token) > 1 and token.casefold() not in STOP_WORDS
    }


def _phrase_tokens(text: str) -> tuple[str, ...]:
    normalized = text.casefold().replace("’s", "").replace("'s", "")
    return tuple(re.findall(r"[^\W_]+", normalized, re.UNICODE))


def _contains_phrase(text_tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _phrase_tokens(phrase)
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    width = len(phrase_tokens)
    return any(
        text_tokens[index : index + width] == phrase_tokens
        for index in range(len(text_tokens) - width + 1)
    )


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


def _record_from_paragraphs(
    metadata: ChapterFrontMatter, paragraphs: tuple[Paragraph, ...]
) -> EvidenceRecord:
    start, end = paragraphs[0].source_lines[0], paragraphs[-1].source_lines[1]
    return EvidenceRecord(
        evidence_id=f"{metadata.chapter_id}-ln{start:04d}-{end:04d}",
        work_id=metadata.work_id,
        book_version_id=metadata.book_version_id,
        chapter_id=metadata.chapter_id,
        chapter_number=metadata.chapter_number,
        location=(
            f"Chapter {metadata.chapter_number} — {metadata.title}, "
            f"source lines {start}-{end}"
        ),
        source_sha256=metadata.source_sha256,
        source_lines=(start, end),
        text="\n\n".join(paragraph.text for paragraph in paragraphs),
    )


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


def _normalize(text: str) -> str:
    """Casefold and unify apostrophe variants so cue matching is quote-agnostic."""
    return text.casefold().replace("’", "'").replace("‘", "'").replace("ʼ", "'")


@lru_cache(maxsize=None)
def _catalog_cues(
    registration: CorpusRegistration,
) -> tuple[frozenset[str], re.Pattern[str]]:
    """Precompute contextual cues; reviewed identities use the shared resolver."""
    catalog = _load_catalog(registration)
    chapters = catalog.get("chapters")
    assert isinstance(chapters, list)
    catalog_markers: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        for field in ("characters", "locations", "retrieval_cues"):
            values = chapter.get(field)
            if isinstance(values, list):
                catalog_markers.update(
                    _normalize(value)
                    for value in values
                    if isinstance(value, str) and len(value.strip()) >= 4
                )
        # routing_description is free prose written for humans, not a
        # catalog cue — counting its incidental words (e.g. "while",
        # "much") as evidence would let unrelated reflection accrue
        # confidence from common vocabulary alone.
    alternation = "|".join(re.escape(marker) for marker in sorted(catalog_markers, key=len, reverse=True))
    pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)" if alternation else r"(?!)")
    return frozenset(catalog_markers), pattern


class Librarian:
    """Retrieve exact passages only from a registered revision and chapter range."""

    def has_corpus(self, work_id: str) -> bool:
        return work_id in registry.CORPORA

    def supports_revision(self, work_id: str, book_version_id: str) -> bool:
        registration = registry.CORPORA.get(work_id)
        return registration is not None and registration.book.book_version_id == book_version_id

    def version_for(self, work_id: str) -> str | None:
        registration = registry.CORPORA.get(work_id)
        return registration.book.book_version_id if registration else None

    def registered_scope(
        self,
        work_id: str,
        book_version_id: str,
    ) -> RegisteredCorpusScope | None:
        """Return trusted metadata without opening any canonical chapter body."""
        registration = registry.CORPORA.get(work_id)
        if registration is None or registration.book.book_version_id != book_version_id:
            return None
        catalog = _load_catalog(registration)
        chapters = catalog.get("chapters")
        if not isinstance(chapters, list):
            raise CorpusScopeError("catalog chapters must be a list")
        numbers = [
            chapter.get("chapter_number")
            for chapter in chapters
            if isinstance(chapter, dict)
        ]
        if not numbers or any(not isinstance(number, int) for number in numbers):
            raise CorpusScopeError("catalog chapter numbers are invalid")
        return RegisteredCorpusScope(
            work_id=work_id,
            book_version_id=book_version_id,
            title=registration.book.title,
            max_chapter=max(numbers),
        )

    def work_candidates(
        self,
        text: str,
        allowed_book_version_ids: tuple[str, ...],
    ) -> tuple[WorkRouteCandidate, ...]:
        """Generate metadata-only candidates without granting a work selection."""
        identity = registry.resolve_book_identity(text, allowed_book_version_ids)
        if identity is not None:
            registrations = (
                (identity.registration,) if isinstance(identity, ResolvedBook)
                else identity.candidates
            )
            candidates = []
            for item in registrations:
                scope = self.registered_scope(item.book.work_id, item.book.book_version_id)
                assert scope is not None
                resolved = isinstance(identity, ResolvedBook)
                candidates.append(WorkRouteCandidate(
                    scope=scope,
                    strength="strong" if resolved else "weak",
                    reasons=("resolved_book_identity" if resolved else "unresolved_book_identity",),
                ))
            return tuple(candidates)
        text_tokens = _phrase_tokens(text)
        query_terms = _terms(text)
        allowed = set(allowed_book_version_ids)
        ranked: list[tuple[int, WorkRouteCandidate]] = []
        for registration in registry.CORPORA.values():
            book = registration.book
            if book.book_version_id not in allowed:
                continue
            scope = self.registered_scope(book.work_id, book.book_version_id)
            assert scope is not None
            catalog = _load_catalog(registration)
            chapters = catalog.get("chapters")
            assert isinstance(chapters, list)

            strong_reasons: set[str] = set()
            weak_reasons: set[str] = set()
            routing_terms: set[str] = set()
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                for field in ("characters", "locations", "retrieval_cues"):
                    values = chapter.get(field)
                    if isinstance(values, list):
                        for value in values:
                            if not isinstance(value, str) or len(value.strip()) < 4:
                                continue
                            routing_terms.update(_terms(value))
                            if not _contains_phrase(text_tokens, value):
                                continue
                            if len(_phrase_tokens(value)) >= 2:
                                strong_reasons.add("distinctive_catalog_phrase")
                            else:
                                weak_reasons.add("single_catalog_term")
                description = chapter.get("routing_description")
                if isinstance(description, str):
                    routing_terms.update(_terms(description))

            overlap = len(query_terms & routing_terms)
            if overlap >= 3:
                strong_reasons.add("catalog_context_agreement")
            elif overlap:
                weak_reasons.add("catalog_context_overlap")

            reasons = strong_reasons or weak_reasons
            if not reasons:
                continue
            strength: Literal["strong", "weak"] = (
                "strong" if strong_reasons else "weak"
            )
            ranked.append(
                (
                    (100 if strength == "strong" else 0) + overlap,
                    WorkRouteCandidate(
                        scope=scope,
                        strength=strength,
                        reasons=tuple(sorted(reasons)),
                    ),
                )
            )

        ranked.sort(key=lambda item: (-item[0], item[1].scope.work_id))
        return tuple(candidate for _, candidate in ranked)

    def route_work(
        self,
        text: str,
        allowed_book_version_ids: tuple[str, ...],
    ) -> RoutingDecision | BookClarification | None:
        """Route explicit literary cues using metadata only, never chapter text."""
        if not allowed_book_version_ids:
            return None
        identity = registry.resolve_book_identity(text, allowed_book_version_ids)
        if isinstance(identity, BookClarification):
            return identity
        if isinstance(identity, ResolvedBook):
            book = identity.registration.book
            scope = self.registered_scope(book.work_id, book.book_version_id)
            assert scope is not None
            return RoutingDecision(scope=scope, confidence=1.0, basis="resolved_book_identity")
        lowered = _normalize(text)
        allowed = set(allowed_book_version_ids)
        ranked: list[tuple[RegisteredCorpusScope, float, int]] = []
        for registration in registry.CORPORA.values():
            book = registration.book
            if book.book_version_id not in allowed:
                continue
            scope = self.registered_scope(book.work_id, book.book_version_id)
            assert scope is not None
            catalog_markers, pattern = _catalog_cues(registration)

            all_matches = {match.group(0) for match in pattern.finditer(lowered)}
            matched_markers = all_matches & catalog_markers
            # Keep only maximal matches: drop a matched cue that is itself a
            # substring of another matched cue (e.g. "garden" inside "rose
            # garden") so nested catalog entries don't double-count.
            matched_markers = {
                marker
                for marker in matched_markers
                if not any(
                    marker != other and marker in other for other in matched_markers
                )
            }
            if not matched_markers:
                continue
            counted_cues = {
                marker for marker in matched_markers
                if " " in marker or marker not in GENERIC_CUE_WORDS
            }
            distinct_cues = len(counted_cues)
            confidence = min(1.0, 0.3 + 0.2 * distinct_cues)
            if confidence >= ROUTING_CONFIDENCE_THRESHOLD:
                ranked.append((scope, confidence, distinct_cues))

        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[1], -item[2], item[0].work_id))
        if len(ranked) > 1:
            return BookClarification(tuple(
                registry.CORPORA[item[0].work_id] for item in ranked
            ))
        scope, confidence, _ = ranked[0]
        return RoutingDecision(scope=scope, confidence=confidence, basis="distinctive_cue")

    def _resolve_evidence_paragraphs(
        self, evidence_id: str
    ) -> tuple[ChapterFrontMatter, tuple[Paragraph, ...]] | None:
        """Resolve an exact canonical window without extending its boundaries."""
        match = EVIDENCE_ID.fullmatch(evidence_id)
        if match is None:
            return None

        chapter_id = match.group("chapter_id")
        start = int(match.group("start"))
        end = int(match.group("end"))
        if (
            start < 1
            or end < start
            or evidence_id != f"{chapter_id}-ln{start:04d}-{end:04d}"
        ):
            return None

        matches: list[tuple[CorpusRegistration, dict[str, object]]] = []
        for registration in registry.CORPORA.values():
            catalog = _load_catalog(registration)
            chapters = catalog.get("chapters")
            if not isinstance(chapters, list):
                raise CorpusScopeError("catalog chapters must be a list")
            matches.extend(
                (registration, chapter)
                for chapter in chapters
                if isinstance(chapter, dict) and chapter.get("chapter_id") == chapter_id
            )

        if not matches:
            return None
        if len(matches) != 1:
            raise CorpusScopeError("evidence chapter identifier is ambiguous")

        registration, chapter = matches[0]
        relative_path = chapter.get("path")
        chapter_number = chapter.get("chapter_number")
        if not isinstance(relative_path, str) or not isinstance(chapter_number, int):
            raise CorpusScopeError("catalog chapter metadata is invalid")

        metadata, markdown_body = parse_chapter_markdown(
            (registration.root / relative_path).read_text(encoding="utf-8")
        )
        if (
            metadata.work_id != registration.book.work_id
            or metadata.book_version_id != registration.book.book_version_id
            or metadata.chapter_id != chapter_id
            or metadata.chapter_number != chapter_number
            or metadata.source_sha256 != registration.book.source_sha256
        ):
            raise CorpusScopeError("chapter identity does not match its registered corpus")

        paragraphs = _paragraphs(metadata, markdown_body)
        first = next(
            (
                index
                for index, paragraph in enumerate(paragraphs)
                if paragraph.source_lines[0] == start
            ),
            None,
        )
        if first is None:
            return None

        selected: list[Paragraph] = []
        for paragraph in paragraphs[first:]:
            selected.append(paragraph)
            paragraph_end = paragraph.source_lines[1]
            if paragraph_end == end:
                break
            if paragraph_end > end:
                return None
        if not selected or selected[-1].source_lines[1] != end:
            return None

        return metadata, tuple(selected)

    def fetch_by_id(self, evidence_id: str) -> EvidenceRecord | None:
        """Resolve one released handle without running retrieval again."""
        resolved = self._resolve_evidence_paragraphs(evidence_id)
        return None if resolved is None else _record_from_paragraphs(*resolved)

    def candidate_paragraphs(
        self, candidates: tuple[EvidenceRecord, ...]
    ) -> tuple[EvidenceRecord, ...]:
        """Narrow verified private windows to canonical paragraphs, never neighbors."""
        records: dict[str, EvidenceRecord] = {}
        for candidate in candidates:
            resolved = self._resolve_evidence_paragraphs(candidate.evidence_id)
            if resolved is None or _record_from_paragraphs(*resolved) != candidate:
                raise CorpusScopeError("candidate does not match its canonical evidence")
            metadata, paragraphs = resolved
            for paragraph in paragraphs:
                record = _record_from_paragraphs(metadata, (paragraph,))
                records.setdefault(record.evidence_id, record)
        return tuple(records.values())

    def retrieve(self, request: LibrarianRequest) -> EvidenceBundle:
        """Search eligible chapter bodies without opening a forbidden chapter."""
        query_terms = _terms(request.query)
        selected: list[EvidenceItem] = []

        for scope in request.book_scopes:
            registration = registry.CORPORA.get(scope.work_id)
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
            retrieval_note=(
                "The complete immutable work was searched privately for boundary inference; "
                "candidate passage text is not a disclosure grant."
                if request.purpose == "boundary_inference"
                else "Only exact text inside the validated corpus revision and chapter boundary was searched."
            ),
        )
