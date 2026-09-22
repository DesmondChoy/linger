"""Frozen page replay preserves production access and release boundaries."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from apps.backend.librarian import Librarian
from evals.synthetic_journals.frozen_public_sources import (
    FrozenPublicSourceSearch, bind_frozen_public_sources,
)
from evals.synthetic_journals.models import PublicSourceSnapshot
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import GuardedExaSearch, SerendipityDependencies
from src.linger.orchestration import connection
from tests.test_public_source_capture import FakeExaClient, TITLE, URL


def snapshot(text="Title: Frozen title\nURL: https://example.org/literature\n\nReviewed exact text."):
    return PublicSourceSnapshot(
        source_id="frozen-source", url=URL, title=TITLE, text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        retrieved_at=datetime.now(timezone.utc),
    )


def context(*, urls=(URL,), cue="."):
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=cue, intent="find_connection", presentation="direct",
            scope=ConnectionScope(allowed_sources=("web",), web_source_urls=urls),
        ),
        librarian=Librarian(),
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


def test_frozen_page_is_exact_and_search_still_uses_the_client():
    source = snapshot()
    client = FakeExaClient(text="Live citation count changed.")
    ctx = context()

    async def exercise():
        async with FrozenPublicSourceSearch(client=client, snapshots=(source,)).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            await toolset.call_tool("web_search", {"query": "literary imagery"}, ctx, tools["web_search"])
            assert ctx.deps.evidence == {}
            assert URL in ctx.deps.web_leads
            result = await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])
            assert result.return_value == source.text
            assert ctx.deps.opened_web_evidence[URL].excerpt == source.text
            assert ctx.deps.evidence[URL].excerpt == source.text

    asyncio.run(exercise())
    assert client.calls == [("search", "literary imagery")]


@pytest.mark.parametrize("operation,args,match", [
    ("get_page", {"url": URL}, "returned by web_search"),
    ("get_page", {"url": "https://example.com/unapproved"}, "outside this request"),
    ("web_search", {"query": "reader@example.com literary imagery"}, "privacy checks"),
    ("web_search", {"query": "+44 20 7946 0958 literary imagery"}, "privacy checks"),
])
def test_frozen_page_cannot_bypass_production_guards(operation, args, match):
    client = FakeExaClient()
    ctx = context(urls=None if match == "returned by web_search" else (URL,))

    async def exercise():
        async with FrozenPublicSourceSearch(client=client, snapshots=(snapshot(),)).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry, match=match):
                await toolset.call_tool(operation, args, ctx, tools[operation])
            assert ctx.deps.evidence == {}
            assert ctx.deps.opened_web_evidence == {}

    asyncio.run(exercise())
    assert client.calls == []


def test_unknown_snapshot_has_no_live_page_fallback():
    client = FakeExaClient()
    ctx = context()

    async def exercise():
        async with FrozenPublicSourceSearch(client=client, snapshots=()).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            await toolset.call_tool("web_search", {"query": "literary imagery"}, ctx, tools["web_search"])
            with pytest.raises(ModelRetry, match="no adopted source snapshot"):
                await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])
            assert ctx.deps.opened_web_evidence == {}

    asyncio.run(exercise())
    assert client.calls == [("search", "literary imagery")]


def test_scene_binding_restores_factory_and_never_reuses_previous_snapshot():
    source = snapshot()
    base = GuardedExaSearch(client=FakeExaClient(), max_text_chars=8_000, guidance="")
    original = connection._web_capability
    with patch.object(connection, "_web_capability", return_value=base) as factory:
        with pytest.raises(RuntimeError, match="scene failure"):
            with bind_frozen_public_sources((source,)):
                capability = connection._web_capability()
                assert capability.snapshots == (source,)
                assert capability.client is base.client
                assert capability.guidance == base.guidance
                assert capability.max_text_chars == 8_000
                raise RuntimeError("scene failure")
        assert connection._web_capability is factory
        with bind_frozen_public_sources(()):
            assert connection._web_capability().snapshots == ()
        assert connection._web_capability() is base
    assert connection._web_capability is original


def test_historical_run_without_source_mode_stays_labeled_live():
    from evals.synthetic_journals.connection_replay import ConnectionEvaluationRun

    run = ConnectionEvaluationRun.model_validate_json(json.dumps({
        "artifact_schema_version": "1", "run_id": "historical-run",
        "objective_ids": ["cross_source_tentative_connection"],
        "dataset_version": "adopted-v1", "system_variant": "old-runtime",
        "runtime_prompt_fingerprints": [], "scenes": [],
    }))
    assert run.public_source_mode == "live"
    current = run.model_copy(update={
        "artifact_schema_version": "2", "public_source_mode": "adopted_snapshot",
    })
    assert ConnectionEvaluationRun.model_validate_json(current.model_dump_json()).public_source_mode == "adopted_snapshot"
