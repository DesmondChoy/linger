"""Shared lifecycle for retrieval-neutral, chapter-based book corpora."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = 1
WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
CHAPTER_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CorpusBuildError(ValueError):
    """Raised when source or canonical artifacts violate the corpus contract."""


@dataclass(frozen=True)
class ParsedChapter:
    """One exact chapter extracted by a source-specific adapter."""

    number: int
    title: str
    slug: str
    markdown_heading: str
    routing_description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    retrieval_cues: tuple[str, ...]
    source_lines: tuple[int, int]
    body_lines: tuple[int, int]
    body: str


@dataclass(frozen=True)
class BookCorpus:
    """Immutable book identity plus its source-specific chapter extractor."""

    work_id: str
    book_version_id: str
    title: str
    author: str
    source_path: str
    source_sha256: str
    default_source: Path
    default_output: Path
    parse_source: Callable[[Path], tuple[ParsedChapter, ...]]
    unit_kind: Literal["chapter", "section"] = "chapter"

    def __post_init__(self) -> None:
        if self.unit_kind not in ("chapter", "section"):
            raise ValueError("unit_kind must be chapter or section")
        valid_work_id = re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", self.work_id
        )
        if not valid_work_id:
            raise ValueError("work_id must be a lowercase stable identifier")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("source_sha256 must be a full lowercase SHA-256")
        if not self.title.strip() or not self.author.strip() or not self.source_path:
            raise ValueError("title, author, and source_path must not be blank")
        expected_version_id = f"{self.work_id}-v{self.source_sha256[:8]}"
        if self.book_version_id != expected_version_id:
            raise ValueError(
                "book_version_id must combine work_id with the first eight "
                "characters of source_sha256"
            )
        if self.default_output.name != self.book_version_id:
            raise ValueError("default_output must end with book_version_id")


class ChapterFrontMatter(BaseModel):
    """Validated metadata stored beside one authoritative chapter body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    work_id: str
    book_version_id: str
    chapter_id: str
    chapter_number: int = Field(ge=1)
    title: str
    routing_description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    retrieval_cues: tuple[str, ...]
    word_count: int = Field(gt=0)
    source_path: str
    source_lines: tuple[int, int]
    body_lines: tuple[int, int]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SectionFrontMatter(ChapterFrontMatter):
    """Schema 2 names mixed literary divisions as sections on disk.

    The lifecycle uses the same ordinal and identity attributes internally;
    aliases keep chapter terminology out of section files and catalogs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)

    schema_version: Literal[2] = 2
    chapter_id: str = Field(alias="section_id")
    chapter_number: int = Field(ge=1, alias="section_number")


def sha256(value: bytes | str) -> str:
    """Return a lowercase SHA-256 digest for bytes or UTF-8 text."""
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _load_chapters(book: BookCorpus, source: Path) -> tuple[ParsedChapter, ...]:
    source_hash = sha256(source.read_bytes())
    if source_hash != book.source_sha256:
        raise CorpusBuildError(f"unexpected source SHA-256: {source_hash}")
    chapters = book.parse_source(source)
    if not chapters:
        raise CorpusBuildError("source adapter returned no chapters")
    numbers = [chapter.number for chapter in chapters]
    if numbers != list(range(1, len(chapters) + 1)):
        raise CorpusBuildError("chapters must be numbered consecutively from 1")
    slugs = [chapter.slug for chapter in chapters]
    if len(set(slugs)) != len(slugs) or any(
        not CHAPTER_SLUG.fullmatch(slug) for slug in slugs
    ):
        raise CorpusBuildError("chapter slugs must be unique lowercase slugs")
    previous_source_end = 0
    for chapter in chapters:
        if not chapter.title.strip() or not chapter.markdown_heading.strip():
            raise CorpusBuildError(f"chapter {chapter.number} has a blank heading")
        if (
            not chapter.body.endswith("\n")
            or chapter.body.endswith("\n\n")
            or not chapter.body.strip()
        ):
            raise CorpusBuildError(
                f"chapter {chapter.number} body must be non-empty with one terminal LF"
            )
        source_start, source_end = chapter.source_lines
        body_start, body_end = chapter.body_lines
        if source_start <= previous_source_end or source_start > source_end:
            raise CorpusBuildError(
                f"chapter {chapter.number} source range overlaps or is reversed"
            )
        if not (source_start <= body_start <= body_end <= source_end):
            raise CorpusBuildError(
                f"chapter {chapter.number} body range is outside its source range"
            )
        if not chapter.routing_description.strip() or not chapter.retrieval_cues:
            raise CorpusBuildError(
                f"chapter {chapter.number} requires routing metadata"
            )
        previous_source_end = source_end
    return chapters


def _chapter_number_width(chapters: Sequence[ParsedChapter]) -> int:
    return max(2, len(str(len(chapters))))


def chapter_path(
    chapter: ParsedChapter, number_width: int = 2, unit_kind: str = "chapter"
) -> Path:
    """Return the stable canonical path for one parsed chapter."""
    return Path(f"{unit_kind}s") / f"{chapter.number:0{number_width}d}-{chapter.slug}.md"


def chapter_metadata(
    book: BookCorpus, chapter: ParsedChapter, number_width: int = 2
) -> ChapterFrontMatter:
    """Build exact canonical front matter for one parsed chapter."""
    metadata = ChapterFrontMatter(
        work_id=book.work_id,
        book_version_id=book.book_version_id,
        chapter_id=f"{book.book_version_id}-ch{chapter.number:0{number_width}d}",
        chapter_number=chapter.number,
        title=chapter.title,
        routing_description=chapter.routing_description,
        characters=chapter.characters,
        locations=chapter.locations,
        retrieval_cues=chapter.retrieval_cues,
        word_count=len(WORD.findall(chapter.body)),
        source_path=book.source_path,
        source_lines=chapter.source_lines,
        body_lines=chapter.body_lines,
        source_sha256=book.source_sha256,
        body_sha256=sha256(chapter.body),
    )
    if book.unit_kind == "section":
        values = metadata.model_dump()
        values["schema_version"] = 2
        values.pop("chapter_id")
        values["section_id"] = f"{book.book_version_id}-sec{chapter.number:0{number_width}d}"
        values["section_number"] = values.pop("chapter_number")
        return SectionFrontMatter.model_validate(values)
    return metadata


def render_chapter(
    book: BookCorpus, chapter: ParsedChapter, number_width: int = 2
) -> tuple[ChapterFrontMatter, str]:
    """Render one exact chapter body with deterministic JSON front matter."""
    metadata = chapter_metadata(book, chapter, number_width)
    front_matter = json.dumps(
        metadata.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    markdown = (
        f"---\n{front_matter}\n---\n\n"
        f"# {chapter.markdown_heading}\n\n"
        f"{chapter.body}"
    )
    return metadata, markdown


def parse_chapter_markdown(
    markdown: str, *, unit_kind: Literal["chapter", "section"] = "chapter"
) -> tuple[ChapterFrontMatter, str]:
    """Read the expected schema; chapter runtime callers reject section files."""
    if not markdown.startswith("---\n"):
        raise CorpusBuildError("chapter is missing front matter")
    try:
        encoded, body = markdown[4:].split("\n---\n\n", maxsplit=1)
        model = SectionFrontMatter if unit_kind == "section" else ChapterFrontMatter
        metadata = model.model_validate_json(encoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CorpusBuildError("chapter front matter is invalid") from exc
    return metadata, body


def _catalog_chapter(
    metadata: ChapterFrontMatter, chapter: ParsedChapter, number_width: int,
    unit_kind: str,
) -> dict[str, Any]:
    return {
        f"{unit_kind}_id": metadata.chapter_id,
        f"{unit_kind}_number": metadata.chapter_number,
        "title": metadata.title,
        "routing_description": metadata.routing_description,
        "characters": list(metadata.characters),
        "locations": list(metadata.locations),
        "retrieval_cues": list(metadata.retrieval_cues),
        "word_count": metadata.word_count,
        "path": chapter_path(chapter, number_width, unit_kind).as_posix(),
    }


def render_catalog(
    book: BookCorpus,
    chapters: Sequence[ParsedChapter],
    metadata: Sequence[ChapterFrontMatter],
) -> str:
    """Project validated front matter into a metadata-only routing catalogue."""
    if len(chapters) != len(metadata):
        raise CorpusBuildError("chapter and metadata counts differ")
    number_width = _chapter_number_width(chapters)
    catalog = {
        "schema_version": 2 if book.unit_kind == "section" else SCHEMA_VERSION,
        "work_id": book.work_id,
        "book_version_id": book.book_version_id,
        "title": book.title,
        "author": book.author,
        "source_path": book.source_path,
        "source_sha256": book.source_sha256,
        f"{book.unit_kind}_count": len(metadata),
        f"{book.unit_kind}s": [
            _catalog_chapter(record, chapter, number_width, book.unit_kind)
            for chapter, record in zip(chapters, metadata, strict=True)
        ],
    }
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def render_initial_corpus(
    book: BookCorpus, source: Path | None = None
) -> dict[Path, str]:
    """Render initial canonical files from an immutable source exactly once."""
    chapters = _load_chapters(book, source or book.default_source)
    number_width = _chapter_number_width(chapters)
    artifacts: dict[Path, str] = {}
    metadata: list[ChapterFrontMatter] = []
    for chapter in chapters:
        front_matter, markdown = render_chapter(book, chapter, number_width)
        artifacts[chapter_path(chapter, number_width, book.unit_kind)] = markdown
        metadata.append(front_matter)
    artifacts[Path("catalog.json")] = render_catalog(book, chapters, metadata)
    return artifacts


def initialise_corpus(
    book: BookCorpus,
    source: Path | None = None,
    output: Path | None = None,
) -> None:
    """Create a corpus only inside an absent or completely empty destination."""
    destination_root = output or book.default_output
    artifacts = render_initial_corpus(book, source)
    if destination_root.is_symlink():
        raise CorpusBuildError(
            f"refusing symbolic-link corpus directory: {destination_root}"
        )
    if destination_root.exists() and any(destination_root.iterdir()):
        raise CorpusBuildError(
            f"refusing to overwrite non-empty corpus directory: {destination_root}"
        )
    for relative_path, content in artifacts.items():
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


def _artifact_errors(
    output: Path, expected_files: set[Path], unit_kind: str = "chapter"
) -> list[str]:
    errors: list[str] = []
    expected_directories = {Path(f"{unit_kind}s")}
    actual_files: set[Path] = set()
    actual_directories: set[Path] = set()
    if output.exists():
        for path in output.rglob("*"):
            relative = path.relative_to(output)
            if path.is_symlink():
                errors.append(f"unexpected symbolic link: {relative.as_posix()}")
            elif path.is_dir():
                actual_directories.add(relative)
            elif path.is_file():
                actual_files.add(relative)
            else:
                errors.append(f"unexpected artifact: {relative.as_posix()}")

    for path in sorted(expected_files - actual_files):
        if path == Path("catalog.json"):
            continue
        errors.append(f"missing {unit_kind} file: {path.as_posix()}")
    for path in sorted(actual_files - expected_files):
        errors.append(f"unexpected file: {path.as_posix()}")
    for path in sorted(actual_directories - expected_directories):
        errors.append(f"unexpected directory: {path.as_posix()}")
    if Path(f"{unit_kind}s") not in actual_directories:
        errors.append(f"missing {unit_kind} directory: {unit_kind}s")
    return errors


def _canonical_records(
    book: BookCorpus,
    source: Path,
    output: Path,
) -> tuple[tuple[ParsedChapter, ...], tuple[ChapterFrontMatter, ...], tuple[str, ...]]:
    """Validate canonical chapters once for both checking and catalogue builds."""
    chapters = _load_chapters(book, source)
    if output.is_symlink():
        return chapters, (), ("unexpected symbolic link: corpus directory",)
    number_width = _chapter_number_width(chapters)
    expected_chapter_paths = {
        chapter_path(chapter, number_width, book.unit_kind) for chapter in chapters
    }
    expected_files = expected_chapter_paths | {Path("catalog.json")}
    errors = _artifact_errors(output, expected_files, book.unit_kind)
    records: list[ChapterFrontMatter] = []

    for chapter in chapters:
        relative_path = chapter_path(chapter, number_width, book.unit_kind)
        path = output / relative_path
        if not path.is_file() or path.is_symlink():
            continue
        try:
            metadata, markdown_body = parse_chapter_markdown(
                path.read_text(encoding="utf-8"), unit_kind=book.unit_kind
            )
        except (CorpusBuildError, OSError, UnicodeError) as exc:
            errors.append(f"{relative_path.as_posix()}: {exc}")
            continue

        records.append(metadata)
        expected_metadata = chapter_metadata(book, chapter, number_width)
        structural_fields = (
            "schema_version",
            "work_id",
            "book_version_id",
            "chapter_id",
            "chapter_number",
            "title",
            "word_count",
            "source_path",
            "source_lines",
            "body_lines",
            "source_sha256",
            "body_sha256",
        )
        for field in structural_fields:
            if getattr(metadata, field) != getattr(expected_metadata, field):
                errors.append(f"{relative_path.as_posix()}: stale {field}")

        expected_body = f"# {chapter.markdown_heading}\n\n{chapter.body}"
        if markdown_body != expected_body:
            errors.append(f"{relative_path.as_posix()}: body differs from source")
        if not metadata.routing_description.strip():
            errors.append(f"{relative_path.as_posix()}: empty routing description")
        if not metadata.retrieval_cues:
            errors.append(f"{relative_path.as_posix()}: no retrieval cues")

    return chapters, tuple(records), tuple(errors)


def build_catalog(
    book: BookCorpus,
    source: Path | None = None,
    output: Path | None = None,
) -> None:
    """Rebuild the catalogue only after all canonical chapters validate."""
    source_path = source or book.default_source
    output_path = output or book.default_output
    chapters, records, errors = _canonical_records(book, source_path, output_path)
    chapter_errors = tuple(
        error for error in errors if error != "catalog.json is missing or stale"
    )
    if chapter_errors:
        raise CorpusBuildError(
            "cannot build catalog from invalid canonical corpus:\n- "
            + "\n- ".join(chapter_errors)
        )
    catalog = render_catalog(book, chapters, records)
    (output_path / "catalog.json").write_text(
        catalog, encoding="utf-8", newline="\n"
    )


def check_corpus(
    book: BookCorpus,
    source: Path | None = None,
    output: Path | None = None,
) -> tuple[str, ...]:
    """Return complete integrity errors without modifying corpus artifacts."""
    source_path = source or book.default_source
    output_path = output or book.default_output
    chapters, records, errors = _canonical_records(book, source_path, output_path)
    all_errors = list(errors)
    if len(records) == len(chapters):
        expected_catalog = render_catalog(book, chapters, records)
        catalog_path = output_path / "catalog.json"
        try:
            actual_catalog = (
                catalog_path.read_text(encoding="utf-8")
                if catalog_path.is_file() and not catalog_path.is_symlink()
                else None
            )
        except (OSError, UnicodeError):
            actual_catalog = None
        if actual_catalog != expected_catalog:
            all_errors.append("catalog.json is missing or stale")
    return tuple(all_errors)


def _load_book(adapter: str) -> BookCorpus:
    try:
        module: ModuleType = importlib.import_module(adapter)
        book = module.BOOK
    except (AttributeError, ImportError) as exc:
        raise CorpusBuildError(
            f"adapter {adapter!r} must import and expose BOOK"
        ) from exc
    required = (
        "work_id",
        "book_version_id",
        "title",
        "author",
        "source_path",
        "source_sha256",
        "default_source",
        "default_output",
        "parse_source",
    )
    if not all(hasattr(book, field) for field in required):
        raise CorpusBuildError(f"adapter {adapter!r} BOOK has the wrong shape")
    return cast(BookCorpus, book)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "adapter",
        help="Python module exposing a source-specific BookCorpus as BOOK",
    )
    parser.add_argument("command", choices=("init", "build-catalog", "check"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Initialize, rebuild, or verify any configured chapter-based book."""
    args = _parser().parse_args(argv)
    try:
        book = _load_book(args.adapter)
        if args.command == "init":
            initialise_corpus(book, args.source, args.output)
            chapter_count = len(
                _load_chapters(book, args.source or book.default_source)
            )
            print(
                f"Initialized {chapter_count} {book.unit_kind}s for "
                f"{book.book_version_id} in {args.output or book.default_output}"
            )
            return 0
        if args.command == "build-catalog":
            build_catalog(book, args.source, args.output)
            print(f"Built {(args.output or book.default_output) / 'catalog.json'}")
            return 0
        errors = check_corpus(book, args.source, args.output)
        if errors:
            print(f"Corpus check failed for {book.book_version_id}:")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"Corpus check passed for {book.book_version_id}")
        return 0
    except (CorpusBuildError, OSError) as exc:
        print(f"Corpus command failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
