"""Reviewed book identities and deterministic resolution for every entry point.

Aliases identify a work; candidate aliases only suggest one for clarification.
Neither names nor catalogue metadata establish a reader's completed chapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.linger.corpus.alice import BOOK
from src.linger.corpus.book import WORD, BookCorpus


@dataclass(frozen=True)
class CorpusRegistration:
    book: BookCorpus
    root: Path
    aliases: tuple[str, ...] = ()
    candidate_aliases: tuple[str, ...] = ()


CORPORA = {
    BOOK.work_id: CorpusRegistration(
        book=BOOK,
        root=BOOK.default_output,
        aliases=("alice in wonderland",),
        candidate_aliases=("wonderland",),
    ),
}


def normalize_name(text: str) -> str:
    """Normalize case, quote variants, whitespace and surrounding punctuation."""
    text = text.casefold().replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    return " ".join(WORD.findall(text))


@dataclass(frozen=True)
class ResolvedBook:
    registration: CorpusRegistration


@dataclass(frozen=True)
class BookClarification:
    candidates: tuple[CorpusRegistration, ...] = ()

    @property
    def question(self) -> str:
        if len(self.candidates) > 1:
            choices = "; ".join(
                f'"{item.book.title}" by {item.book.author}'
                for item in self.candidates
            )
            return f"Which book do you mean: {choices}? Please give the title and author."
        return "Which book do you mean? Please give its full title and author."


@dataclass(frozen=True)
class _NameMatch:
    registration: CorpusRegistration
    start: int
    end: int
    canonical: bool


def _matches(text: str, name: str) -> tuple[re.Match[str], ...]:
    normalized = normalize_name(name)
    if not normalized:
        return ()
    return tuple(re.finditer(rf"(?<!\w){re.escape(normalized)}(?!\w)", text))


def resolve_book_identity(
    text: str,
    allowed_book_version_ids: tuple[str, ...],
    *,
    exact: bool = False,
) -> ResolvedBook | BookClarification | None:
    """Resolve reviewed names, preserving ambiguity instead of ranking it away.

    Exact mode accepts a reader's supplied title, optionally followed by its
    author. Free-text mode also finds names inside a book question. Longer
    names subsume shorter names inside them; a canonical name wins over an
    alias at the same location. Separate mentions remain separate identities.
    """
    normalized = normalize_name(text)
    matches: list[_NameMatch] = []
    hints: dict[str, CorpusRegistration] = {}
    for registration in CORPORA.values():
        book = registration.book
        for canonical, names in (
            (True, (book.title, book.work_id, book.work_id.replace("-", " "))),
            (False, registration.aliases),
        ):
            for name in names:
                if exact and normalized not in (
                    normalize_name(name),
                    normalize_name(f"{name} by {book.author}"),
                ):
                    continue
                matches.extend(
                    _NameMatch(registration, match.start(), match.end(), canonical)
                    for match in _matches(normalized, name)
                )
        if any(
            _matches(normalized, name)
            and (not exact or normalized == normalize_name(name))
            for name in registration.candidate_aliases
        ):
            hints[book.work_id] = registration

    matches = [
        match for match in matches
        if not any(
            other.start <= match.start and match.end <= other.end
            and (
                (other.start, other.end) != (match.start, match.end)
                or other.canonical and not match.canonical
            )
            for other in matches
        )
    ]
    candidates = {
        match.registration.book.work_id: match.registration for match in matches
    }
    if len(candidates) > 1 and len({(item.start, item.end) for item in matches}) == 1:
        by_author = {
            work_id: item for work_id, item in candidates.items()
            if _matches(normalized, item.book.author)
        }
        if len(by_author) == 1:
            candidates = by_author

    allowed = set(allowed_book_version_ids)
    if len(candidates) == 1:
        registration = next(iter(candidates.values()))
        if registration.book.book_version_id in allowed:
            return ResolvedBook(registration)
    if matches or hints:
        eligible = tuple(
            item for _, item in sorted((candidates or hints).items())
            if item.book.book_version_id in allowed
        )
        return BookClarification(eligible)
    return None


def registration_errors() -> tuple[str, ...]:
    """Check reviewed identities before enabling a new corpus revision.

    Shared candidate-only names are permitted because they cannot select a
    work. Authoritative aliases must not collide with another registered name.
    Runtime still checks ambiguity if an unchecked registration is supplied.
    """
    errors: list[str] = []
    names: dict[str, set[str]] = {}
    for work_id, registration in CORPORA.items():
        book = registration.book
        if work_id != book.work_id:
            errors.append(f"{work_id}: registry key does not match the work ID")
        if registration.root.name != book.book_version_id:
            errors.append(f"{work_id}: corpus directory does not match its revision")
        aliases = tuple(map(normalize_name, registration.aliases))
        hints = tuple(map(normalize_name, registration.candidate_aliases))
        if any(not name for name in (*aliases, *hints)):
            errors.append(f"{work_id}: aliases must not be blank")
        if len(set((*aliases, *hints))) != len((*aliases, *hints)):
            errors.append(f"{work_id}: duplicate or conflicting alias classification")
        for name in (book.title, book.work_id, book.work_id.replace("-", " "), *registration.aliases):
            names.setdefault(normalize_name(name), set()).add(work_id)
    for name, work_ids in sorted(names.items()):
        if len(work_ids) > 1:
            registrations = [CORPORA[work_id] for work_id in work_ids]
            shared_title = all(
                normalize_name(item.book.title) == name for item in registrations
            )
            distinct_authors = len({
                normalize_name(item.book.author) for item in registrations
            }) == len(registrations)
            if not (shared_title and distinct_authors):
                errors.append(f"Name collision {name!r}: {', '.join(sorted(work_ids))}")
    for work_id, registration in CORPORA.items():
        for alias in registration.aliases:
            for other_id, other in CORPORA.items():
                if other_id == work_id:
                    continue
                if (
                    _matches(normalize_name(other.book.title), alias)
                    or _matches(normalize_name(alias), other.book.title)
                ):
                    errors.append(
                        f"Alias overlap {alias!r}: {work_id} and title of {other_id}"
                    )
                if normalize_name(alias) in map(normalize_name, other.candidate_aliases):
                    errors.append(
                        f"Alias overlap {alias!r}: {work_id} and candidate alias of {other_id}"
                    )
    return tuple(errors)


def main() -> int:
    errors = registration_errors()
    for error in errors:
        print(error)
    if not errors:
        print(f"Book registry OK: {len(CORPORA)} registered work(s)")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
