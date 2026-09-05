"""Application-owned reader statements supplied to private book inference."""

from pydantic import Field

from src.linger.contracts.base import StrictModel


class ReaderStatement(StrictModel):
    statement_id: str = Field(min_length=1, strict=True)
    text: str = Field(min_length=1, strict=True)
