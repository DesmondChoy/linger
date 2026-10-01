"""Bounded, recorded web search for Sculptor's offline retrieval research."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.output import OutputContext
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.exa import ExaSearch

from src.linger.agents.sculptor.research_models import (
    ResearchInput,
    ResearchSpecification,
    specification_errors,
)

MAX_QUERY_CHARS = 500


@dataclass
class ResearchLedger:
    """What one research run searched and read; the run's citations must come from `opened`."""

    max_searches: int
    max_pages: int
    searches: list[str] = field(default_factory=list)
    leads: dict[str, str] = field(default_factory=dict)
    opened: dict[str, str] = field(default_factory=dict)


def _sources(result: ToolReturn) -> dict[str, str]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    found = {}
    for source in metadata.get("sources", []):
        url = source.get("url") if isinstance(source, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            found[url] = str(source.get("title") or url)[:300]
    return found


@dataclass
class ResearchToolset(WrapperToolset[Any]):
    """Enforce the search and page budgets and open only pages this run found."""

    ledger: ResearchLedger = field(default_factory=lambda: ResearchLedger(0, 0))

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any],
    ) -> Any:
        ledger = self.ledger
        if name == "web_search":
            query = str(tool_args.get("query", "")).strip()
            if not query or len(query) > MAX_QUERY_CHARS:
                raise ModelRetry(f"Use one non-empty query of at most {MAX_QUERY_CHARS} characters.")
            if len(ledger.searches) >= ledger.max_searches:
                raise ModelRetry(f"The {ledger.max_searches}-search budget is used; work with what you found.")
            ledger.searches.append(query)
        elif name == "get_page":
            url = str(tool_args.get("url", "")).strip()
            if url not in ledger.leads:
                raise ModelRetry("Open only an exact URL returned by web_search in this run.")
            if url not in ledger.opened and len(ledger.opened) >= ledger.max_pages:
                raise ModelRetry(f"The {ledger.max_pages}-page budget is used; work with what you read.")
        else:
            raise ModelRetry("Only web_search and get_page are available.")
        result = await super().call_tool(name, tool_args, ctx, tool)
        if isinstance(result, ToolReturn):
            sources = _sources(result)
            if name == "web_search":
                ledger.leads.update(sources)
            elif url in sources:
                ledger.opened[url] = sources[url]
        return result


@dataclass
class ResearchSearch(ExaSearch):
    """Exa search for one research run, with its budget and citation check."""

    ledger: ResearchLedger = field(default_factory=lambda: ResearchLedger(0, 0))

    def get_toolset(self) -> AbstractToolset[Any]:
        return ResearchToolset(super().get_toolset(), ledger=self.ledger)

    async def after_output_validate(
        self, ctx: RunContext[Any], *, output_context: OutputContext, output: Any,
    ) -> Any:
        if not isinstance(output, ResearchSpecification):
            return output
        if not isinstance(ctx.prompt, str):
            raise ValueError("Research validation requires the typed research prompt")
        errors = specification_errors(output, ResearchInput.model_validate_json(ctx.prompt), set(self.ledger.opened))
        if errors:
            raise ModelRetry(json.dumps({
                "error": "The specification breaks the application's contract.",
                "errors": errors,
            }, ensure_ascii=False))
        return output
