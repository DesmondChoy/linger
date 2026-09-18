"""Resolve authoring excerpts to exact records from an intact registered corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from apps.backend.hybrid_librarian import _windows
from apps.backend.librarian import Paragraph, _paragraphs, _record_from_paragraphs
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.corpus import registry
from src.linger.corpus.book import check_corpus
from src.linger.corpus.units import CorpusUnit, load_units, read_unit

from .models import CorpusTextEvidence


@dataclass(frozen=True)
class ResolvedCorpusSpan:
    authored: CorpusTextEvidence
    chapter_number: int
    accepted_runtime_records: tuple[EvidenceRecord, ...]


class BookEvidenceResolver:
    """Validate each immutable corpus once, then resolve exact source occurrences."""

    def __init__(self, repository_root: Path) -> None:
        self.root = repository_root.resolve()
        self._catalogs: dict[tuple[str, str], tuple[Path, dict]] = {}
        self._units: dict[tuple[str, str], tuple[CorpusUnit, ...]] = {}

    def catalog(self, work_id: str, version: str) -> tuple[Path, dict]:
        key = (work_id, version)
        if key in self._catalogs:
            return self._catalogs[key]
        registration = registry.CORPORA.get(work_id)
        if registration is None or registration.book.book_version_id != version:
            raise ValueError("unregistered work or corpus version")
        book = registration.book
        repo = Path(__file__).resolve().parents[2]
        directory = self.root / registration.root.resolve().relative_to(repo)
        source = self.root / book.source_path
        if not directory.resolve().is_relative_to(
            self.root
        ) or not source.resolve().is_relative_to(self.root):
            raise ValueError("corpus path escapes repository")
        errors = check_corpus(book, source=source, output=directory)
        if errors:
            raise ValueError("corpus integrity: " + "; ".join(errors))
        document = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
        self._catalogs[key] = (directory, document)
        return directory, document

    def _registered_units(
        self, work_id: str, version: str
    ) -> tuple[registry.CorpusRegistration, tuple[CorpusUnit, ...]]:
        directory, _ = self.catalog(work_id, version)
        registration = replace(registry.CORPORA[work_id], root=directory)
        key = (work_id, version)
        if key not in self._units:
            self._units[key] = load_units(registration)
        return registration, self._units[key]

    def max_chapter(self, work_id: str, version: str) -> int:
        """Return the literary chapter extent of the main narrative only."""
        _, units = self._registered_units(work_id, version)
        numbers = [
            unit.chapter_number for unit in units
            if unit.part_id == "main" and unit.chapter_number is not None
        ]
        if not numbers:
            raise ValueError("registered corpus has no numbered main-text chapters")
        return max(numbers)

    def resolve(
        self, work_id: str, version: str, evidence: CorpusTextEvidence
    ) -> ResolvedCorpusSpan:
        registration, units = self._registered_units(work_id, version)
        unit = next(
            (unit for unit in units if unit.chapter_id == evidence.chapter_id), None
        )
        if unit is None:
            raise ValueError("chapter_id is absent from the registered catalog")
        if unit.part_id != "main" or unit.chapter_number is None:
            raise ValueError("book evidence requires a numbered main-text chapter")
        metadata, body = read_unit(registration, unit)
        markdown = (registration.root / unit.path).read_text(encoding="utf-8")
        if markdown[evidence.start_codepoint : evidence.end_codepoint] != evidence.text:
            raise ValueError("exact chapter span does not equal evidence text")
        _, source_body = body.split("\n\n", maxsplit=1)
        body_offset = len(markdown) - len(source_body)
        if evidence.start_codepoint < body_offset:
            raise ValueError("evidence span must reference the source body")
        start_line = metadata.body_lines[0] + source_body[
            : evidence.start_codepoint - body_offset
        ].count("\n")
        end_line = metadata.body_lines[0] + source_body[
            : evidence.end_codepoint - body_offset - 1
        ].count("\n")
        paragraphs = _paragraphs(metadata, body)
        candidates = (
            *paragraphs,
            *(
                Paragraph(item.text, item.source_lines)
                for item in _windows(metadata, paragraphs)
            ),
        )
        records: dict[str, EvidenceRecord] = {}
        for item in candidates:
            start, end = item.source_lines
            if (
                not (start <= start_line <= end_line <= end)
                or evidence.text not in item.text
            ):
                continue
            record = _record_from_paragraphs(metadata, (item,))
            records[record.evidence_id] = record
        if not records:
            raise ValueError("source occurrence is in no retrievable evidence window")
        return ResolvedCorpusSpan(
            evidence, unit.chapter_number, tuple(records.values())
        )
