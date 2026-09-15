"""Known application-granted pages do not depend on search ranking."""

import asyncio

import pytest
from pydantic_ai import ModelRetry

from evals.synthetic_journals.frozen_public_sources import FrozenPublicSourceSearch
from src.linger.agents.serendipity.tools import GuardedExaSearch
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.session import ReaderStatement
from tests.test_frozen_public_sources import context, snapshot
from tests.test_public_source_capture import FakeExaClient, URL


@pytest.mark.parametrize("search_first", [False, True])
def test_exact_granted_page_opens_even_when_search_omits_it(search_first):
    client = FakeExaClient(search_url=URL + "/sibling")
    ctx = context()

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            if search_first:
                await toolset.call_tool("web_search", {"query": URL}, ctx, tools["web_search"])
            assert not ctx.deps.web_leads
            assert not ctx.deps.evidence
            await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])
            assert ctx.deps.opened_web_evidence[URL] == ctx.deps.evidence[URL]
            assert not ctx.deps.web_leads  # Direct access never invents a search result.

    asyncio.run(exercise())
    assert client.calls == ([("search", URL)] if search_first else []) + [("get_contents", URL)]


@pytest.mark.parametrize("urls", [None, (), (URL + "/other",)])
def test_model_url_without_a_grant_or_search_lead_never_reaches_client(urls):
    client = FakeExaClient()
    ctx = context(urls=urls)

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry):
                await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])

    asyncio.run(exercise())
    assert not client.calls
    assert not ctx.deps.evidence


@pytest.mark.parametrize(("url", "cue"), [
    ("https://example.org/profile?email=reader@example.com", "."),
    ("https://example.org/profile?email=reader%40example.com", "."),
    ("https://example.org/my/private/divorce", "My private divorce"),
    ("https://example.org/my%20private%20divorce", "My private divorce"),
])
def test_even_granted_pages_must_pass_url_privacy_checks(url, cue):
    client = FakeExaClient(page_url=url)
    ctx = context(urls=(url,), cue=cue)

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry, match="privacy"):
                await toolset.call_tool("get_page", {"url": url}, ctx, tools["get_page"])

    asyncio.run(exercise())
    assert not client.calls
    assert not ctx.deps.evidence


def test_known_url_does_not_make_redirected_page_citable():
    client = FakeExaClient(page_url=URL + "/redirected")
    ctx = context()

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])
            assert not ctx.deps.opened_web_evidence
            assert not ctx.deps.evidence
            assert ctx.deps.searches[-1].outcome == "no_evidence"

    asyncio.run(exercise())
    assert client.calls == [("get_contents", URL)]


def test_encoded_private_memory_in_a_granted_url_never_reaches_client():
    url = "https://example.org/fixed%20the%20billing%20error%20myself"
    client = FakeExaClient(page_url=url)
    ctx = context(urls=(url,))
    ctx.deps.memories = (CuratedMemory(
        memory_id="private-note", text="Yesterday I fixed the billing error myself before telling the team.",
        kind="original", source_memory_ids=("private-note",), created_at="2026-09-15T00:00:00Z",
    ),)

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry, match="privacy"):
                await toolset.call_tool("get_page", {"url": url}, ctx, tools["get_page"])

    asyncio.run(exercise())
    assert not client.calls


@pytest.mark.parametrize(("operation", "arguments"), [
    ("web_search", {"query": "brass fox behind our classroom cupboard"}),
    ("get_page", {"url": "https://example.org/brass/fox/behind/our/classroom/cupboard"}),
    ("get_page", {"url": "https://example.org/brass%20fox%20behind%20our%20classroom%20cupboard"}),
])
def test_prior_reader_wording_never_reaches_public_client(operation, arguments):
    url = arguments.get("url", URL)
    client = FakeExaClient(page_url=url)
    ctx = context(urls=(url,), cue="I finished chapter five.")
    ctx.deps.prior_reader_statements = (ReaderStatement(
        statement_id="earlier-line",
        text="I privately call our reading group the brass fox behind our classroom cupboard.",
    ),)

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry):
                await toolset.call_tool(operation, arguments, ctx, tools[operation])

    asyncio.run(exercise())
    assert not client.calls
    assert not ctx.deps.evidence
    assert not ctx.deps.opened_web_evidence


def test_prior_reader_context_still_allows_a_general_public_query():
    client = FakeExaClient()
    ctx = context(cue="I finished chapter five.")
    ctx.deps.prior_reader_statements = (ReaderStatement(
        statement_id="earlier-line",
        text="I privately call our reading group the brass fox behind our classroom cupboard.",
    ),)
    query = "literary commentary symbolism reading"

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            await toolset.call_tool("web_search", {"query": query}, ctx, tools["web_search"])

    asyncio.run(exercise())
    assert client.calls == [("search", query)]


def test_adopted_page_can_be_inspected_without_a_live_search_result():
    source = snapshot()
    client = FakeExaClient(search_url=URL + "/sibling", text="Changed live page")
    ctx = context()

    async def exercise():
        async with FrozenPublicSourceSearch(client=client, snapshots=(source,)).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            result = await toolset.call_tool("get_page", {"url": URL}, ctx, tools["get_page"])
            assert result.return_value == source.text
            assert ctx.deps.evidence[URL].excerpt == source.text

    asyncio.run(exercise())
    assert not client.calls
