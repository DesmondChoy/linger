"""Read-only Reader access to granted, registered canonical chapter corpora."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.linger.corpus import registry
from src.linger.corpus.book import parse_chapter_markdown, sha256
from src.linger.corpus.registry import CorpusRegistration

from .config import Settings, get_settings

router = APIRouter(prefix="/api/library")
LibrarySettings = Annotated[Settings, Depends(get_settings)]


class LibraryChapter(BaseModel):
    number: int
    title: str
    summary: str


class LibraryBook(BaseModel):
    work_id: str
    book_version_id: str
    title: str
    author: str
    chapters: list[LibraryChapter]


class ChapterText(BaseModel):
    text: str


class CatalogChapter(BaseModel):
    chapter_id: str
    chapter_number: int = Field(ge=1, strict=True)
    title: str
    routing_description: str
    path: str


class ChapterCatalog(BaseModel):
    schema_version: Literal[1]
    work_id: str
    book_version_id: str
    source_sha256: str
    chapters: list[CatalogChapter]


def _catalog(registration: CorpusRegistration) -> ChapterCatalog:
    try:
        catalog = ChapterCatalog.model_validate_json(
            (registration.root / "catalog.json").read_text(encoding="utf-8")
        )
        book = registration.book
        if (
            catalog.work_id != book.work_id
            or catalog.book_version_id != book.book_version_id
            or catalog.source_sha256 != book.source_sha256
            or not catalog.chapters
            or [chapter.chapter_number for chapter in catalog.chapters]
            != list(range(1, len(catalog.chapters) + 1))
        ):
            raise ValueError("invalid catalog identity or chapter sequence")
        return catalog
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "The book's catalog is unavailable.") from exc


@router.get("", response_model=list[LibraryBook])
def list_books(settings: LibrarySettings) -> list[LibraryBook]:
    books = []
    for registration in registry.CORPORA.values():
        book = registration.book
        if book.book_version_id not in settings.allowed_book_version_ids or book.unit_kind != "chapter":
            continue
        catalog = _catalog(registration)
        books.append(LibraryBook(
            work_id=book.work_id,
            book_version_id=book.book_version_id,
            title=book.title,
            author=book.author,
            chapters=[LibraryChapter(
                number=chapter.chapter_number,
                title=chapter.title,
                summary=chapter.routing_description,
            ) for chapter in catalog.chapters],
        ))
    return books


@router.get("/{work_id}/{book_version_id}/chapters/{chapter_number}", response_model=ChapterText)
def read_chapter(
    work_id: str,
    book_version_id: str,
    chapter_number: int,
    settings: LibrarySettings,
) -> ChapterText:
    registration = registry.CORPORA.get(work_id)
    if (
        registration is None
        or registration.book.book_version_id != book_version_id
        or book_version_id not in settings.allowed_book_version_ids
        or registration.book.unit_kind != "chapter"
    ):
        raise HTTPException(404, "Book is unavailable.")
    catalog = _catalog(registration)
    chapter = next((item for item in catalog.chapters if item.chapter_number == chapter_number), None)
    if chapter is None:
        raise HTTPException(404, "Chapter is unavailable.")
    try:
        root = registration.root.resolve()
        path = (root / chapter.path).resolve()
        if not path.is_relative_to(root) or Path(chapter.path).is_absolute():
            raise ValueError("chapter path is outside its corpus")
        metadata, body = parse_chapter_markdown(path.read_text(encoding="utf-8"))
        heading, separator, story = body.partition("\n\n")
        if (
            metadata.work_id != work_id
            or metadata.book_version_id != book_version_id
            or metadata.chapter_id != chapter.chapter_id
            or metadata.chapter_number != chapter_number
            or metadata.source_sha256 != registration.book.source_sha256
            or not heading.startswith("# ")
            or not separator
            or sha256(story) != metadata.body_sha256
        ):
            raise ValueError("chapter does not match its canonical metadata")
        return ChapterText(text=story)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "The chapter text is unavailable.") from exc
