"""Read canonical units using their literary locations, preserving stable IDs."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from src.linger.corpus.book import (
    CorpusBuildError, UnitLocation, WORD, parse_chapter_markdown, sha256,
)

if TYPE_CHECKING:
    from src.linger.corpus.registry import CorpusRegistration


@dataclass(frozen=True)
class CorpusUnit:
    work_id: str
    book_version_id: str
    chapter_id: str
    chapter_number: int | None
    part_id: str
    part_title: str
    kind: str
    order: int
    title: str
    label: str
    path: str
    routing_description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    retrieval_cues: tuple[str, ...]
    word_count: int
    source_path: str
    source_sha256: str
    recipient: str | None = None
    date: str | None = None
    body_sha256: str = ""
    source_lines: tuple[int, int] | None = None
    body_lines: tuple[int, int] | None = None


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise CorpusBuildError("invalid canonical unit path")
    if root.is_symlink() or any((root / Path(*path.parts[:n])).is_symlink()
                                for n in range(1, len(path.parts) + 1)):
        raise CorpusBuildError("canonical corpus paths must not be symbolic links")
    return root / path


def load_units(registration: CorpusRegistration) -> tuple[CorpusUnit, ...]:
    """Load routing metadata only; never open a canonical body to infer locations."""
    book = registration.book
    catalog = json.loads(_safe_path(registration.root, "catalog.json").read_text(encoding="utf-8"))
    expected = {
        "schema_version": 2 if book.unit_kind == "section" else 1,
        "work_id": book.work_id,
        "book_version_id": book.book_version_id,
        "source_sha256": book.source_sha256,
        "source_path": book.source_path,
        "title": book.title,
        "author": book.author,
    }
    if not isinstance(catalog, dict) or any(catalog.get(k) != v for k, v in expected.items()):
        raise CorpusBuildError("catalog identity differs from registered corpus")
    kind = book.unit_kind
    rows = catalog.get(f"{kind}s")
    if not isinstance(rows, list) or not rows or catalog.get(f"{kind}_count") != len(rows):
        raise CorpusBuildError("catalog unit count is invalid")
    if kind == "section" and len(book.unit_locations) != len(rows):
        raise CorpusBuildError("section corpus needs reviewed literary locations for every unit")
    width = max(2, len(str(len(rows))))
    units = []
    for order, row in enumerate(rows, 1):
        identity = f"{book.book_version_id}-{'sec' if kind == 'section' else 'ch'}{order:0{width}d}"
        if not isinstance(row, dict) or row.get(f"{kind}_id") != identity or row.get(f"{kind}_number") != order:
            raise CorpusBuildError("catalog unit identity or order is invalid")
        for key in ("title", "routing_description", "path"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise CorpusBuildError(f"catalog unit has invalid {key}")
        for key in ("characters", "locations", "retrieval_cues"):
            if not isinstance(row.get(key), list) or any(not isinstance(value, str) for value in row[key]):
                raise CorpusBuildError(f"catalog unit has invalid {key}")
        if not row["retrieval_cues"] or type(row.get("word_count")) is not int or row["word_count"] <= 0:
            raise CorpusBuildError("catalog unit has invalid routing metadata")
        path = _safe_path(registration.root, row["path"])
        relative = path.relative_to(registration.root)
        if len(relative.parts) != 2 or relative.parts[0] != f"{kind}s" or not relative.name.startswith(f"{order:0{width}d}-") or relative.suffix != ".md":
            raise CorpusBuildError("catalog path differs from canonical unit order")
        location = (book.unit_locations[order - 1] if kind == "section" else
                    UnitLocation("chapter", "main", "Main text", f"Chapter {order}", order))
        if not location.label or not location.part_id or not location.kind:
            raise CorpusBuildError("literary location is incomplete")
        if (location.kind == "chapter") != (location.chapter_number is not None):
            raise CorpusBuildError("only chapters may have chapter numbers")
        if location.chapter_number is not None and location.chapter_number < 1:
            raise CorpusBuildError("chapter numbers must be positive")
        units.append(CorpusUnit(
            work_id=book.work_id, book_version_id=book.book_version_id,
            chapter_id=identity, chapter_number=location.chapter_number,
            part_id=location.part_id, part_title=location.part_title,
            kind=location.kind, order=order, title=row["title"], label=location.label,
            path=row["path"], routing_description=row["routing_description"],
            characters=tuple(row["characters"]), locations=tuple(row["locations"]),
            retrieval_cues=tuple(row["retrieval_cues"]), word_count=row["word_count"],
            source_path=book.source_path, source_sha256=book.source_sha256,
            recipient=location.recipient, date=location.date,
        ))
    chapter_locations = [(unit.part_id, unit.chapter_number) for unit in units if unit.kind == "chapter"]
    if len(set(chapter_locations)) != len(chapter_locations):
        raise CorpusBuildError("duplicate chapter number within a book part")
    return tuple(units)


def read_unit(registration: CorpusRegistration, unit: CorpusUnit) -> tuple[CorpusUnit, str]:
    """Open a selected unit, validate its canonical metadata and body, and retain its heading."""
    if (unit.work_id, unit.book_version_id) != (registration.book.work_id, registration.book.book_version_id):
        raise CorpusBuildError("unit is outside the registered corpus")
    metadata, markdown = parse_chapter_markdown(
        _safe_path(registration.root, unit.path).read_text(encoding="utf-8"),
        unit_kind=registration.book.unit_kind,
    )
    for field in ("work_id", "book_version_id", "chapter_id", "title", "routing_description",
                  "characters", "locations", "retrieval_cues", "word_count", "source_path", "source_sha256"):
        if getattr(metadata, field) != getattr(unit, field):
            raise CorpusBuildError(f"canonical unit differs from catalog: {field}")
    if metadata.chapter_number != unit.order:
        raise CorpusBuildError("canonical unit order differs from catalog")
    if not markdown.startswith("# ") or "\n\n" not in markdown:
        raise CorpusBuildError("canonical unit is missing its Markdown heading")
    _, body = markdown.split("\n\n", 1)
    if sha256(body) != metadata.body_sha256 or len(WORD.findall(body)) != metadata.word_count:
        raise CorpusBuildError("canonical unit body checksum or word count differs")
    source_start, source_end = metadata.source_lines
    body_start, body_end = metadata.body_lines
    if not (1 <= source_start <= body_start <= body_end <= source_end) or len(body.splitlines()) != body_end - body_start + 1:
        raise CorpusBuildError("canonical unit source ranges are invalid")
    return replace(unit, body_sha256=metadata.body_sha256, source_lines=metadata.source_lines,
                   body_lines=metadata.body_lines), markdown
