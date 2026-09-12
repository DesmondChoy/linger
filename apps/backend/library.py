"""Read-only Reader access to granted, registered canonical literary units."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.linger.corpus import registry
from src.linger.corpus.registry import CorpusRegistration
from src.linger.corpus.units import CorpusUnit, load_units, read_unit

from .config import Settings, get_settings

router = APIRouter(prefix="/api/library")
LibrarySettings = Annotated[Settings, Depends(get_settings)]


class LibraryUnit(BaseModel):
    unit_id: str
    chapter_number: int | None
    part_id: str
    part_title: str
    kind: str
    title: str
    label: str
    summary: str


class LibraryBook(BaseModel):
    work_id: str
    book_version_id: str
    title: str
    author: str
    units: list[LibraryUnit]
    start_unit_id: str


class UnitText(BaseModel):
    text: str


def _units(registration: CorpusRegistration) -> tuple[CorpusUnit, ...]:
    try:
        return load_units(registration)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "The book's contents are unavailable.") from exc


@router.get("", response_model=list[LibraryBook])
def list_books(settings: LibrarySettings) -> list[LibraryBook]:
    books = []
    for registration in registry.CORPORA.values():
        book = registration.book
        if book.book_version_id not in settings.allowed_book_version_ids:
            continue
        units = _units(registration)
        start = next((unit for unit in units if unit.part_id == "main" and unit.kind == "chapter"), None)
        if start is None:
            raise HTTPException(503, "The book's starting location is unavailable.")
        books.append(LibraryBook(
            work_id=book.work_id,
            book_version_id=book.book_version_id,
            title=book.title,
            author=book.author,
            units=[LibraryUnit(
                unit_id=unit.chapter_id,
                chapter_number=unit.chapter_number,
                part_id=unit.part_id,
                part_title=unit.part_title,
                kind=unit.kind,
                title=unit.title,
                label=unit.label,
                summary=unit.routing_description,
            ) for unit in units],
            start_unit_id=start.chapter_id,
        ))
    return books


@router.get("/{work_id}/{book_version_id}/units/{unit_id}", response_model=UnitText)
def read_library_unit(
    work_id: str,
    book_version_id: str,
    unit_id: str,
    settings: LibrarySettings,
) -> UnitText:
    registration = registry.CORPORA.get(work_id)
    if (
        registration is None
        or registration.book.book_version_id != book_version_id
        or book_version_id not in settings.allowed_book_version_ids
    ):
        raise HTTPException(404, "Book is unavailable.")
    unit = next((item for item in _units(registration) if item.chapter_id == unit_id), None)
    if unit is None:
        raise HTTPException(404, "Reading location is unavailable.")
    try:
        _, body = read_unit(registration, unit)
        heading, separator, story = body.partition("\n\n")
        if not heading.startswith("# ") or not separator:
            raise ValueError("canonical text has no generated heading")
        return UnitText(text=story)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "The text is unavailable.") from exc
