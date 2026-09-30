"""Typed input and output contracts for Sculptor memory curation."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter
from pydantic import field_validator, model_validator


class StrictModel(BaseModel):
    """Reject schema drift and keep curation values immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CuratableMemory(StrictModel):
    """The minimum memory data Sculptor needs to propose curation."""

    memory_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class CurationMemory(CuratableMemory):
    """A memory offered for curation, with its capture time when known."""

    recorded_at: AwareDatetime | None = None


class ExistingDuplicateLink(StrictModel):
    """One supplied memory and the supplied memories already linked to it."""

    memory_id: str = Field(min_length=1)
    duplicate_memory_ids: tuple[str, ...] = Field(min_length=1)


class ExistingTombstone(StrictModel):
    """One supplied memory already suppressed from retrieval."""

    memory_id: str = Field(min_length=1)
    canonical_memory_id: str | None = None


class ExistingDerivedSummary(StrictModel):
    """One derived summary already stored for supplied memories."""

    source_memory_ids: tuple[str, ...] = Field(min_length=2, max_length=12)
    summary: str = Field(min_length=1)


class ExistingTopicGroup(StrictModel):
    """One topic group already assigned to supplied memories."""

    source_memory_ids: tuple[str, ...] = Field(min_length=2, max_length=12)
    topic_label: str = Field(min_length=1)


class ExistingCuration(StrictModel):
    """Application-owned curation already applied to the supplied memories."""

    duplicate_links: tuple[ExistingDuplicateLink, ...] = ()
    tombstones: tuple[ExistingTombstone, ...] = ()
    derived_summaries: tuple[ExistingDerivedSummary, ...] = ()
    topic_groups: tuple[ExistingTopicGroup, ...] = ()

    def referenced_memory_ids(self) -> frozenset[str]:
        return frozenset(
            memory_id
            for link in self.duplicate_links
            for memory_id in (link.memory_id, *link.duplicate_memory_ids)
        ) | frozenset(
            memory_id
            for tombstone in self.tombstones
            for memory_id in (tombstone.memory_id, tombstone.canonical_memory_id)
            if memory_id is not None
        ) | frozenset(
            memory_id
            for item in (*self.derived_summaries, *self.topic_groups)
            for memory_id in item.source_memory_ids
        )


class AccountScopedMemories(StrictModel):
    """A bounded memory set selected for one account by application code."""

    account_scope: str = Field(min_length=1)
    memories: tuple[CurationMemory, ...] = Field(min_length=2, max_length=12)
    existing_curation: ExistingCuration = ExistingCuration()

    @model_validator(mode="after")
    def require_unique_memory_ids(self) -> Self:
        memory_ids = tuple(memory.memory_id for memory in self.memories)
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("memory IDs must be unique")
        if self.existing_curation.referenced_memory_ids() - set(memory_ids):
            raise ValueError("existing curation must reference supplied memories only")
        return self


class SourceMemoryAction(StrictModel):
    """A proposed action whose provenance resolves to supplied memories."""

    source_memory_ids: tuple[str, ...] = Field(min_length=2, max_length=12)

    @field_validator("source_memory_ids")
    @classmethod
    def require_unique_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source memory IDs must be unique")
        return value


class DuplicateLink(SourceMemoryAction):
    """Link records that express the same durable memory."""

    action: Literal["link_duplicates"]


class DerivedSummary(SourceMemoryAction):
    """Store a concise retrieval summary without changing its sources."""

    action: Literal["update_derived_summary"]
    summary: str = Field(min_length=1, max_length=1_000)

    @field_validator("summary")
    @classmethod
    def limit_summary_words(cls, value: str) -> str:
        if len(value.split()) > 100:
            raise ValueError("derived summaries must contain at most 100 words")
        return value


class TopicGroup(SourceMemoryAction):
    """Assign related but distinct memories to one retrieval topic."""

    action: Literal["assign_topic_group"]
    topic_label: str = Field(min_length=1, max_length=100)


class RetrievalTombstone(SourceMemoryAction):
    """Suppress one linked duplicate from retrieval without deleting it."""

    action: Literal["tombstone_for_retrieval"]
    memory_id: str = Field(min_length=1)
    canonical_memory_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_linked_distinct_sources(self) -> Self:
        if self.memory_id == self.canonical_memory_id:
            raise ValueError("a retrieval tombstone requires a distinct canonical memory")
        source_ids = set(self.source_memory_ids)
        if {self.memory_id, self.canonical_memory_id} != source_ids:
            raise ValueError(
                "retrieval tombstone sources must be the target and canonical memory"
            )
        return self


class RetrievalRestore(StrictModel):
    """Restore one tombstoned original to the retrieval view."""

    action: Literal["restore_to_retrieval"]
    source_memory_ids: tuple[str] = Field(min_length=1, max_length=1)
    memory_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_target_source(self) -> Self:
        if self.source_memory_ids != (self.memory_id,):
            raise ValueError("retrieval restore source must be the target memory")
        return self


CurationAction = Annotated[
    DuplicateLink
    | DerivedSummary
    | TopicGroup
    | RetrievalTombstone
    | RetrievalRestore,
    Field(discriminator="action"),
]


class CurationProposal(StrictModel):
    """One read-only curation proposal for deterministic validation."""

    kind: Literal["curation_proposal"]
    action: CurationAction


class NoCurationProposal(StrictModel):
    """An explicit decision to leave the supplied memories unchanged."""

    kind: Literal["no_curation_proposal"]
    reason: str = Field(min_length=1, max_length=1_000)


SculptorResponse = CurationProposal | NoCurationProposal
SCULPTOR_RESPONSE_ADAPTER = TypeAdapter(
    Annotated[SculptorResponse, Field(discriminator="kind")]
)
