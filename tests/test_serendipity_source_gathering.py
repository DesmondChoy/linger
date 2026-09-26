"""Named-source gathering as its own Serendipity skill, intent, and result."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from apps.backend.contracts import ConnectionBrief, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.agent import build_serendipity_agent, validate_serendipity_output
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionScope,
    MemoryRecall,
    PublicSourceCheck,
    SourceBundle,
)
from src.linger.agents.serendipity.skills import SOURCE_GATHERING
from src.linger.agents.serendipity.tools import GuardedExaSearch, SearchTrace, SerendipityDependencies
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.triage import TurnNeeds
from src.linger.orchestration.connection import (
    ExplorationResult, InvalidConnectionResponse, _validate_response, connection_exploration,
)
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection,
    canonical_connection_evidence,
    connection_inspections,
    reset_connection_inspection,
)
from src.linger.orchestration.triage import expose_tools
from src.linger.orchestration.turn_context import reset_active_memories, set_active_memories
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence, WebConnectionEvidence

NOTE = CuratedMemory(
    memory_id="memory-host", text="I promised to host the reading circle next month.",
    kind="original", source_memory_ids=("memory-host",), created_at="2026-09-07T00:00:00Z",
)
PASSAGE = EvidenceItem(
    evidence_id="pg500-v1-ch30-ln4028-4081", work_id="pg500", book_version_id="pg500-v1",
    chapter_id="pg500-v1-ch30", chapter=30, source_title="The Adventures of Pinocchio",
    location="Chapter 30", source_sha256="a" * 64, source_lines=(4028, 4081),
    excerpt="I'll be back in one hour without fail.", relevance=.9,
)


def dependencies(*, prior_book_results=()):
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue="Put Pinocchio's promise next to what I wrote about hosting.",
            intent="gather_sources", presentation="direct",
            scope=ConnectionScope(allowed_sources=("memory",)),
        ),
        librarian=Librarian(), memories=(NOTE,),
    )
    # Stands in for records an earlier search_librarian call returned in this run.
    deps.evidence.update({item.evidence_id: item for item in prior_book_results})
    return deps


def bundle(*evidence_ids, unfound=(), public_checks=()):
    return SourceBundle(
        evidence_ids=evidence_ids, unfound_sources=unfound,
        relevance_note="The note is the hosting promise the reader named.",
        public_source_checks=public_checks,
    )


def run(deps, outputs):
    """Search memories once, then return each scripted output until one is accepted."""
    retries = []
    remaining = list(outputs)

    async def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("search_memories", {"query": "host the reading circle"})])
        retries.extend(
            str(part.content) for part in messages[-1].parts if isinstance(part, RetryPromptPart)
        )
        assert remaining, f"no scripted output left; last request: {messages[-1].parts}"
        output = remaining.pop(0)
        tool = next(tool for tool in info.output_tools if tool.name.endswith(type(output).__name__))
        return ModelResponse(parts=[ToolCallPart(tool.name, output.model_dump(mode="json"))])

    result = asyncio.run(build_serendipity_agent(FunctionModel(model)).run(
        deps.task.model_dump_json(), deps=deps, **SOURCE_GATHERING.run_options(),
    ))
    return result.output, retries


def test_named_sources_are_returned_as_one_bundle():
    output, retries = run(dependencies(), [bundle("memory-host", unfound=("Keller at the lake",))])

    assert output == bundle("memory-host", unfound=("Keller at the lake",))
    assert retries == []


def test_gather_task_retries_another_result_shape():
    recall = MemoryRecall(evidence_ids=("memory-host",), relevance_note="The hosting note.")
    output, retries = run(dependencies(), [recall, bundle("memory-host")])

    assert isinstance(output, SourceBundle)
    assert "gather_sources task returns a bundle" in retries[0]


def test_bundle_keeps_every_passage_librarian_returned():
    deps = dependencies(prior_book_results=(PASSAGE,))
    output, retries = run(deps, [bundle("memory-host"), bundle("memory-host", PASSAGE.evidence_id)])

    assert set(output.evidence_ids) == {"memory-host", PASSAGE.evidence_id}
    assert PASSAGE.evidence_id in retries[0]


def test_bundle_keeps_every_page_it_opened():
    # Run 7: the Hume page was opened but left out as if it had no evidence ID.
    page = WebConnectionEvidence(
        evidence_id="https://example.org/hume", title="Of personal identity", excerpt="A bundle of perceptions.",
    )
    deps = dependencies()
    deps.evidence[page.evidence_id] = page
    deps.opened_web_evidence[page.evidence_id] = page
    output, retries = run(deps, [bundle("memory-host"), bundle("memory-host", page.evidence_id)])

    assert set(output.evidence_ids) == {"memory-host", page.evidence_id}
    assert page.evidence_id in retries[0]
    assert "exact URL" in retries[0]


def test_unfound_public_source_cannot_skip_the_supplied_page():
    deps = dependencies()
    deps.task = deps.task.model_copy(update={
        "cue": "Put that essay next to what I wrote about hosting.",
        "scope": ConnectionScope(
            allowed_sources=("memory", "web"),
            web_source_urls=("https://example.org/essay",),
        ),
    })
    deps.record("memory", "search_memories", "evidence_found", (
        MemoryConnectionEvidence(evidence_id=NOTE.memory_id, excerpt=NOTE.text),
    ))

    with pytest.raises(ModelRetry, match="public_source_checks"):
        validate_serendipity_output(
            SimpleNamespace(deps=deps), bundle(NOTE.memory_id, unfound=("that essay",)),
        )


PAGE_URL = "https://example.org/essay"
UNREQUESTED_URL = "https://example.org/another-essay"


def public_dependencies():
    deps = dependencies()
    deps.task = deps.task.model_copy(update={
        "cue": "Put that essay next to what I wrote about hosting.",
        "scope": ConnectionScope(
            allowed_sources=("memory", "web"),
            web_source_urls=(PAGE_URL, UNREQUESTED_URL),
        ),
    })
    deps.record("memory", "search_memories", "evidence_found", (
        MemoryConnectionEvidence(evidence_id=NOTE.memory_id, excerpt=NOTE.text),
    ))
    return deps


def public_checks():
    return (
        PublicSourceCheck(url=PAGE_URL, requested_as="that essay"),
        PublicSourceCheck(url=UNREQUESTED_URL, requested_as=None),
    )


class PageClient:
    def __init__(self, *, unavailable=False):
        self.calls = []
        self.unavailable = unavailable

    async def get_contents(self, urls, **_kwargs):
        url = urls[0] if isinstance(urls, (list, tuple)) else urls
        self.calls.append(url)
        if self.unavailable:
            return SimpleNamespace(results=[])
        return SimpleNamespace(results=[SimpleNamespace(
            url=url, title="An essay", published_date=None, author=None,
            text="The essay considers continuity through change.",
        )])


@pytest.mark.parametrize("unavailable", [False, True])
def test_indirect_requested_page_is_attempted_and_unrequested_permission_is_not(unavailable):
    deps = public_dependencies()
    client = PageClient(unavailable=unavailable)
    retries = []

    def model(messages, info):
        retries.extend(str(part.content) for part in messages[-1].parts if isinstance(part, RetryPromptPart))
        if retries and not client.calls:
            assert "get_page" in retries[-1] and PAGE_URL in retries[-1]
            return ModelResponse(parts=[ToolCallPart("get_page", {"url": PAGE_URL})])
        opened = any(
            isinstance(part, ToolReturnPart) and part.tool_name == "get_page"
            for message in messages for part in message.parts
        )
        output = bundle(
            NOTE.memory_id, *((PAGE_URL,) if opened else ()),
            unfound=() if opened else ("that essay",), public_checks=public_checks(),
        )
        tool = next(tool for tool in info.output_tools if tool.name.endswith("SourceBundle"))
        return ModelResponse(parts=[ToolCallPart(tool.name, output.model_dump(mode="json"))])

    result = asyncio.run(build_serendipity_agent(FunctionModel(model)).run(
        deps.task.model_dump_json(), deps=deps,
        capabilities=[GuardedExaSearch(client=client, guidance="")],
        **SOURCE_GATHERING.run_options(),
    ))

    assert client.calls == [PAGE_URL]
    assert deps.attempted_web_urls == {PAGE_URL}
    assert set(result.output.evidence_ids) == ({NOTE.memory_id} if unavailable else {NOTE.memory_id, PAGE_URL})
    assert result.output.unfound_sources == (("that essay",) if unavailable else ())
    assert len(retries) == (2 if unavailable else 1)


@pytest.mark.parametrize("requested_as", ["that different essay", " "])
def test_public_source_request_must_use_exact_reader_words(requested_as):
    deps = public_dependencies()
    checks = (PublicSourceCheck(url=PAGE_URL, requested_as=requested_as), public_checks()[1])
    with pytest.raises(ModelRetry, match="non-empty exact span"):
        validate_serendipity_output(SimpleNamespace(deps=deps), bundle(NOTE.memory_id, public_checks=checks))


def test_privacy_block_does_not_count_as_a_page_open_attempt():
    deps = public_dependencies()
    private_url = "https://example.org/reader@example.com"
    deps.task = deps.task.model_copy(update={"scope": ConnectionScope(
        allowed_sources=("memory", "web"), web_source_urls=(private_url,),
    )})
    client = PageClient()
    ctx = RunContext(deps=deps, model=TestModel(), usage=RunUsage())

    async def exercise():
        async with GuardedExaSearch(client=client).get_toolset() as toolset:
            tools = await toolset.get_tools(ctx)
            with pytest.raises(ModelRetry, match="privacy checks"):
                await toolset.call_tool("get_page", {"url": private_url}, ctx, tools["get_page"])

    asyncio.run(exercise())
    assert client.calls == []
    assert deps.attempted_web_urls == set()


def test_application_rejects_claimed_public_source_inspection_without_actual_attempt():
    deps = public_dependencies()
    output = bundle(NOTE.memory_id, unfound=("that essay",), public_checks=public_checks())
    run = ExplorationResult(
        response=output, evidence=(), searches=tuple(deps.searches),
    )
    with pytest.raises(InvalidConnectionResponse, match="not been attempted"):
        _validate_response(run, deps.task)


def test_bundle_retries_an_id_this_run_did_not_return():
    output, retries = run(dependencies(), [bundle("memory-host", "memory-unseen"), bundle("memory-host")])

    assert output == bundle("memory-host")
    assert "memory-unseen" in retries[0]


def test_bundle_contract_rejects_duplicates_and_discriminates():
    with pytest.raises(ValidationError):
        bundle("memory-host", "memory-host")
    with pytest.raises(ValidationError):
        bundle("memory-host", unfound=("Keller", "Keller"))
    assert SERENDIPITY_RESPONSE_ADAPTER.validate_python(
        bundle("memory-host").model_dump(mode="json")
    ) == bundle("memory-host")


def test_named_sources_triage_pins_gather_sources():
    exposure = expose_tools(
        TurnNeeds(book_content="yes", memory="named_sources"),
        previously_called=frozenset(), book_override=False,
    )

    assert exposure.pinned_intent == "gather_sources"
    assert "serendipity_explore" in exposure.tools


def explore_gather(*, searched):
    tasks = []

    async def explorer(task: ConnectionDiscoveryInput) -> ExplorationResult:
        tasks.append(task)
        return ExplorationResult(
            response=bundle(NOTE.memory_id),
            evidence=(MemoryConnectionEvidence(evidence_id=NOTE.memory_id, excerpt=NOTE.text),),
            searches=(
                SearchTrace(source="memory", operation="search_memories", outcome="evidence_found"),
            ) if searched else (),
        )

    async def scenario():
        memories = set_active_memories((NOTE,))
        inspection = begin_connection_inspection()
        try:
            with patch("src.linger.orchestration.connection.web_reach_permitted", return_value=False):
                result = await connection_exploration(
                    ConnectionBrief(cue="Put my note beside Pinocchio.", intent="gather_sources"),
                    explorer=explorer, librarian=Librarian(),
                )
            return result, dict(canonical_connection_evidence()), connection_inspections()
        finally:
            reset_connection_inspection(inspection)
            reset_active_memories(memories)

    return (*asyncio.run(scenario()), tasks[0])


def test_gathered_bundle_is_presented_directly_and_registers_its_evidence():
    result, registered, inspections, task = explore_gather(searched=True)

    assert task.presentation == "direct"
    assert result.decision == bundle(NOTE.memory_id)
    assert [item.evidence_id for item in result.evidence] == [NOTE.memory_id]
    assert NOTE.memory_id in registered
    assert [inspection.status for inspection in inspections] == ["gathered"]


def test_a_bundle_that_never_searched_is_declined():
    result, registered, _, _ = explore_gather(searched=False)

    assert isinstance(result.decision, ConnectionDecline)
    assert result.evidence == ()
    assert NOTE.memory_id not in registered
