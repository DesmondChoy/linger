"""Validation, API visibility, and isolation for synthetic demo readers."""

from fastapi.testclient import TestClient
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from apps.backend import main, sessions
from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    ConnectionDiscoveryInput,
    ConnectionScope,
)
from src.linger.agents.serendipity.tools import (
    SerendipityDependencies,
    search_librarian,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService
from src.linger.synthetic_readers import (
    load_synthetic_readers,
    synthetic_memory_evidence,
    synthetic_reader,
    synthetic_scenarios,
)


def test_dataset_contains_three_rich_isolated_histories() -> None:
    dataset = load_synthetic_readers()

    assert {reader.reader_id for reader in dataset.users} == {
        "demo-maya",
        "demo-theo",
        "demo-noor",
    }
    assert sum(len(reader.memories) for reader in dataset.users) == 16
    assert len(dataset.connection_scenarios) == 9
    for reader in dataset.users:
        assert len(reader.days) == 4
        assert sum(len(day.turns) for day in reader.days) == 8
        assert len(synthetic_scenarios(reader.reader_id)) == 3


def test_memory_search_never_leaks_between_synthetic_readers() -> None:
    cue = "How do written rules make authority and equality appear stable?"

    for reader_id in ("demo-maya", "demo-theo", "demo-noor"):
        evidence = synthetic_memory_evidence(reader_id, cue)
        assert all(
            item.evidence_id.startswith(f"synthetic:{reader_id}:")
            for item in evidence
        )

    theo_ids = {
        item.evidence_id for item in synthetic_memory_evidence("demo-theo", cue)
    }
    noor_ids = {
        item.evidence_id for item in synthetic_memory_evidence("demo-noor", cue)
    }
    assert theo_ids.isdisjoint(noor_ids)


def test_librarian_tool_includes_only_selected_synthetic_history(tmp_path) -> None:
    task = ConnectionDiscoveryInput(
        request_id="synthetic-librarian-test",
        cue="Why do written rules make authority feel stable?",
        intent="find_connection",
        presentation="ask_before_showing",
        scope=ConnectionScope(allowed_sources=("authorised_memory",)),
    )
    deps = SerendipityDependencies(
        task=task,
        librarian=Librarian(),
        memory_service=MemoryPolicyService(tmp_path),
        account=AccountContext("synthetic-tool-test"),
        synthetic_reader_id="demo-noor",
    )
    context = RunContext(deps=deps, model=TestModel(), usage=RunUsage())

    result = search_librarian(
        context,
        query=task.cue,
        sources=("authorised_memory",),
    )

    assert result.evidence
    assert all(
        item.evidence_id.startswith("synthetic:demo-noor:")
        for item in result.evidence
    )
    assert all("demo-maya" not in item.evidence_id for item in result.evidence)


def test_demo_reader_api_lists_profiles_and_selects_one_per_session() -> None:
    client = TestClient(main.app)
    session_id = "synthetic-reader-api-test"
    sessions.clear(session_id)

    listing = client.get("/api/demo/readers")
    assert listing.status_code == 200
    readers = listing.json()["readers"]
    assert [reader["display_name"] for reader in readers] == ["Maya", "Theo", "Noor"]
    assert all(len(reader["scenarios"]) == 3 for reader in readers)
    assert "connect" in readers[0]["scenarios"][0]["prompt"].casefold()
    assert "connect" in readers[1]["scenarios"][0]["prompt"].casefold()
    assert "artwork" in readers[2]["scenarios"][0]["prompt"].casefold()

    selection = client.put(
        f"/api/sessions/{session_id}/synthetic-reader",
        json={"reader_id": "demo-noor"},
    )
    assert selection.status_code == 200
    assert selection.json()["reader_id"] == "demo-noor"

    memories = client.get("/api/memories", params={"session_id": session_id})
    assert memories.status_code == 200
    payload = memories.json()
    assert payload["active_test_profile"]["reader_id"] == "demo-noor"
    synthetic = [
        memory for memory in payload["memories"]
        if memory["source"] == "synthetic"
    ]
    assert len(synthetic) == len(synthetic_reader("demo-noor").memories)
    assert all(memory["memory_id"].startswith("synthetic:demo-noor:noor-") for memory in synthetic)
    assert all(memory["read_only"] for memory in synthetic)

    client.delete(f"/api/sessions/{session_id}")
    cleared = client.get("/api/memories", params={"session_id": session_id})
    assert cleared.json()["active_test_profile"] is None
    assert not any(
        memory["source"] == "synthetic"
        for memory in cleared.json()["memories"]
    )


def test_unknown_demo_reader_fails_closed() -> None:
    response = TestClient(main.app).put(
        "/api/sessions/unknown-reader-test/synthetic-reader",
        json={"reader_id": "demo-unknown"},
    )

    assert response.status_code == 404
    assert sessions.synthetic_reader("unknown-reader-test") is None
