"""Capture trusted public text through the production guarded Exa tools."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import TypeAdapter
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import GuardedExaSearch, SerendipityDependencies
from src.linger.orchestration.connection import _web_capability

from .models import Identifier, PublicSourceSnapshot


async def capture_public_source(
    *,
    source_id: str,
    url: str,
    public_query: str,
    capability: GuardedExaSearch | None = None,
) -> PublicSourceSnapshot:
    """Search and open one public source, without invoking a generation model."""
    TypeAdapter(Identifier).validate_python(source_id)
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("public source URL must be an absolute HTTP(S) URL without credentials")
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            # This operation has no reader cue or private memory content.
            cue=".",
            intent="find_connection",
            presentation="direct",
            scope=ConnectionScope(allowed_sources=("web",), web_source_urls=(url,)),
        ),
        librarian=Librarian(),
    )
    ctx = RunContext(deps=deps, model=TestModel(), usage=RunUsage())
    async with (capability or _web_capability()).get_toolset() as toolset:
        tools = await toolset.get_tools(ctx)
        await toolset.call_tool("web_search", {"query": public_query}, ctx, tools["web_search"])
        if url not in deps.web_leads:
            raise ValueError("the exact permitted source URL was not returned by public search")
        await toolset.call_tool("get_page", {"url": url}, ctx, tools["get_page"])
    evidence = deps.opened_web_evidence.get(url)
    if evidence is None:
        raise ValueError("the permitted source did not produce guarded opened-page evidence")
    return PublicSourceSnapshot(
        source_id=source_id,
        url=url,
        title=evidence.title,
        text=evidence.excerpt,
        source_sha256=hashlib.sha256(evidence.excerpt.encode("utf-8")).hexdigest(),
        retrieved_at=datetime.now(timezone.utc),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--public-query", required=True, help="Public terms only; never include reader or memory text.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new path")
    snapshot = asyncio.run(capture_public_source(
        source_id=args.source_id, url=args.url, public_query=args.public_query,
    ))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(snapshot.model_dump_json(indent=2) + "\n")
    print(f"Captured {len(snapshot.text)} characters to {args.output}; SHA-256 {snapshot.source_sha256}")


if __name__ == "__main__":
    main()
