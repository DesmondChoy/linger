"""Replay adopted page text under production access and privacy guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from typing import Any
from unittest.mock import patch

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.exa import ExaSearch

from src.linger.agents.serendipity.tools import (
    GuardedExaSearch, GuardedExaToolset, SerendipityDependencies,
)
from src.linger.orchestration import connection

from .models import PublicSourceSnapshot


@dataclass
class FrozenPageToolset(WrapperToolset[SerendipityDependencies]):
    snapshots: tuple[PublicSourceSnapshot, ...] = ()

    async def call_tool(
        self, name: str, tool_args: dict[str, Any],
        ctx: RunContext[SerendipityDependencies], tool: ToolsetTool[SerendipityDependencies],
    ) -> Any:
        if name != "get_page":
            return await super().call_tool(name, tool_args, ctx, tool)
        url = str(tool_args.get("url", "")).strip()
        snapshot = next((item for item in self.snapshots if item.url == url), None)
        if snapshot is None:
            raise ModelRetry("This page has no adopted source snapshot for the current Scene.")
        return ToolReturn(
            snapshot.text,
            metadata={"sources": [{"url": snapshot.url, "title": snapshot.title}]},
        )


@dataclass
class FrozenPublicSourceSearch(GuardedExaSearch):
    snapshots: tuple[PublicSourceSnapshot, ...] = ()

    def get_toolset(self) -> AbstractToolset[SerendipityDependencies]:
        return GuardedExaToolset(FrozenPageToolset(
            ExaSearch.get_toolset(self), snapshots=self.snapshots,
        ))


@contextmanager
def bind_frozen_public_sources(snapshots: tuple[PublicSourceSnapshot, ...]) -> Iterator[None]:
    """Bind source inputs only for one sequential replay Scene, restoring on error."""
    original_factory = connection._web_capability

    def capability() -> FrozenPublicSourceSearch:
        base = original_factory()
        return FrozenPublicSourceSearch(
            **{field.name: getattr(base, field.name) for field in fields(ExaSearch) if field.init},
            snapshots=snapshots,
        )

    with patch.object(connection, "_web_capability", side_effect=capability):
        yield
