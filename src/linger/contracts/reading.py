"""Reading locations and shared scope checks."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from src.linger.contracts.base import StrictModel


def validate_selector(chapter: int | None, unit_ids: tuple[str, ...]) -> None:
    if (chapter is None) == (not unit_ids):
        raise ValueError("choose a chapter boundary or exact units")
    if any(not identity.strip() for identity in unit_ids):
        raise ValueError("unit IDs must not be blank")
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("unit IDs must be unique")


def scope_fields(scope: object) -> dict[str, object]:
    return {"chapter_max": getattr(scope, "chapter_max", getattr(scope, "max_chapter_inclusive", None)),
            "part_id": scope.part_id, "unit_ids": scope.unit_ids}


def permits_scope(scope: object, record: object) -> bool:
    if scope.work_id != record.work_id:
        return False
    revision = getattr(scope, "book_version_id", None)
    if revision is not None and revision != record.book_version_id:
        return False
    if scope.part_id != record.part_id:
        return False
    if scope.unit_ids:
        return record.chapter_id in scope.unit_ids
    chapter = getattr(record, "chapter_number", getattr(record, "chapter", None))
    ceiling = scope_fields(scope)["chapter_max"]
    return chapter is not None and ceiling is not None and chapter <= ceiling


def contains_scope(outer: object, inner: object) -> bool:
    if outer.work_id != inner.work_id or outer.book_version_id != inner.book_version_id or outer.part_id != inner.part_id:
        return False
    if outer.unit_ids:
        return bool(inner.unit_ids) and set(inner.unit_ids) <= set(outer.unit_ids)
    ceiling = scope_fields(outer)["chapter_max"]
    candidate = scope_fields(inner)["chapter_max"]
    return not inner.unit_ids and ceiling is not None and candidate is not None and candidate <= ceiling


class ReadingScope(StrictModel):
    chapter_max: int | None = Field(default=None, ge=1)
    part_id: str = "main"
    unit_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_selector(self) -> Self:
        validate_selector(self.chapter_max, self.unit_ids)
        return self


class ReadingBoundary(StrictModel):
    """Actual chapter within a part, or exact named units."""
    chapter_number: int | None = Field(default=None, ge=1)
    chapter_state: Literal["started", "completed"]
    part_id: str = "main"
    unit_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_selector(self) -> Self:
        validate_selector(self.chapter_number, self.unit_ids)
        return self
