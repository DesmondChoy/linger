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


async def _open_page(ctx, client, url, *, search_first=False):
    async with GuardedExaSearch(client=client).get_toolset() as toolset:
        tools = await toolset.get_tools(ctx)
        if search_first:
            await toolset.call_tool(
                "web_search", {"query": "comparative criticism ideas"}, ctx, tools["web_search"],
            )
        return await toolset.call_tool("get_page", {"url": url}, ctx, tools["get_page"])


@pytest.mark.parametrize("explicit_grant", [False, True])
@pytest.mark.parametrize(("url", "cue"), [
    (URL, f"Please compare this book with {URL} and explain their differences."),
    (URL, f"Please inspect {URL}."),
    (URL, f"Please inspect [this essay]({URL})."),
    (URL, f"Please inspect <{URL}>."),
    (URL + "/literary%20imagery", f"Please inspect {URL}/literary%20imagery."),
    (URL + "/Identity_(philosophy)", f"Please inspect [this essay]({URL}/Identity_(philosophy))."),
])
def test_reader_supplied_public_url_can_be_opened(explicit_grant, url, cue):
    client = FakeExaClient(search_url=url, page_url=url)
    ctx = context(urls=(url,) if explicit_grant else None, cue=cue)

    asyncio.run(_open_page(ctx, client, url, search_first=not explicit_grant))

    assert client.calls == (
        [] if explicit_grant else [("search", "comparative criticism ideas")]
    ) + [("get_contents", url)]
    assert ctx.deps.opened_web_evidence[url] == ctx.deps.evidence[url]


def test_exact_url_in_prior_reader_statement_can_be_opened():
    client = FakeExaClient()
    ctx = context(cue="Please compare that article with the book.")
    ctx.deps.prior_reader_statements = (ReaderStatement(
        statement_id="earlier-line", text=f"Please inspect {URL}.",
    ),)

    asyncio.run(_open_page(ctx, client, URL))

    assert client.calls == [("get_contents", URL)]
    assert URL in ctx.deps.evidence


def test_reader_supplied_url_still_requires_an_application_grant_or_search_lead():
    client = FakeExaClient()
    ctx = context(urls=None, cue=f"Please inspect {URL}.")

    with pytest.raises(ModelRetry, match="returned by web_search"):
        asyncio.run(_open_page(ctx, client, URL))

    assert not client.calls
    assert not ctx.deps.evidence


def test_reader_supplied_url_does_not_relax_web_search_privacy():
    client = FakeExaClient()
    ctx = context(cue=f"Please inspect {URL}.")

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry):
                await toolset.call_tool("web_search", {"query": URL}, ctx, tools["web_search"])

    asyncio.run(exercise())
    assert not client.calls


@pytest.mark.parametrize("url", [
    "https://example.org/profile?email=reader@example.com",
    "https://example.org/profile?email=reader%40example.com",
    "https://reader:password@example.org/literature",
])
def test_reader_supplied_url_still_rejects_private_data(url):
    client = FakeExaClient(page_url=url)
    ctx = context(urls=(url,), cue=f"Please inspect {url}.")

    with pytest.raises(ModelRetry, match="privacy"):
        asyncio.run(_open_page(ctx, client, url))

    assert not client.calls
    assert not ctx.deps.evidence


@pytest.mark.parametrize("private_source", ["cue", "prior_statement", "memory", "memory_locator"])
@pytest.mark.parametrize("path", ["my/private/divorce", "my%20private%20divorce"])
def test_reader_supplied_url_keeps_checks_against_private_wording(private_source, path):
    url = f"https://example.org/{path}"
    client = FakeExaClient(page_url=url)
    ctx = context(urls=(url,), cue=f"Please inspect {url}.")
    private_text = "My private divorce."
    if private_source == "cue":
        ctx.deps.task = ctx.deps.task.model_copy(update={"cue": private_text + " " + ctx.deps.task.cue})
    elif private_source == "prior_statement":
        ctx.deps.prior_reader_statements = (ReaderStatement(
            statement_id="earlier-line", text=private_text,
        ),)
    else:
        ctx.deps.memories = (CuratedMemory(
            memory_id="private-note", text=url if private_source == "memory_locator" else private_text,
            kind="original",
            source_memory_ids=("private-note",), created_at="2026-09-15T00:00:00Z",
        ),)

    with pytest.raises(ModelRetry, match="privacy"):
        asyncio.run(_open_page(ctx, client, url))

    assert not client.calls
    assert not ctx.deps.evidence


@pytest.mark.parametrize("suffix", ["/private", "?detail=private", "#private", ")private", "(private)"])
@pytest.mark.parametrize("request_is_prefix", [False, True])
def test_url_privacy_exception_requires_the_complete_exact_locator(suffix, request_is_prefix):
    supplied, requested = (URL + suffix, URL) if request_is_prefix else (URL, URL + suffix)
    client = FakeExaClient(page_url=requested)
    ctx = context(urls=(requested,), cue=f"Please inspect {supplied}.")

    with pytest.raises(ModelRetry, match="privacy"):
        asyncio.run(_open_page(ctx, client, requested))

    assert not client.calls
    assert not ctx.deps.evidence
