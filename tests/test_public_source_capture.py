"""Public capture preserves the production formatter and replay source identity."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from evals.synthetic_journals.connection_replay import grade_connection_scene
from evals.synthetic_journals.public_source_capture import capture_public_source, main
from src.linger.agents.serendipity.tools import GuardedExaSearch
from tests.test_synthetic_connection_scenario import connection_documents, validate_documents
from tests.test_synthetic_connection_replay import response, restraint_events

URL = "https://example.org/literature"
TITLE = "Literary image"
ROOT = Path(__file__).resolve().parents[1]


class FakeExaClient:
    def __init__(
        self, text="A public literary image.", *, search_url=URL, page_url=URL,
        published_date=None, author=None,
    ):
        self.text = text
        self.search_url = search_url
        self.page_url = page_url
        self.published_date = published_date
        self.author = author
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append(("search", query))
        return SimpleNamespace(results=[SimpleNamespace(
            url=self.search_url, title=TITLE, published_date=None, author=None,
            highlights=["A search lead, not the opened source."],
        )], output=None)

    async def get_contents(self, url, **kwargs):
        self.calls.append(("get_contents", url))
        return SimpleNamespace(results=[SimpleNamespace(
            url=self.page_url, title=TITLE, published_date=self.published_date,
            author=self.author, text=self.text,
        )])


def capture(client, *, query="literary imagery"):
    return asyncio.run(capture_public_source(
        source_id="source-public", url=URL, public_query=query,
        capability=GuardedExaSearch(client=client, max_text_chars=8_000),
    ))


@pytest.mark.parametrize("body", ["A public literary image.", "A public literary image. " * 500])
@pytest.mark.parametrize(("published_date", "author", "metadata_headers"), [
    (None, None, ""),
    ("", "", ""),
    ("2026-09-12", "Public author", "\nPublished: 2026-09-12\nAuthor: Public author"),
])
def test_maintained_formatter_and_guarded_bound_match_replay(body, published_date, author, metadata_headers):
    client = FakeExaClient(body, published_date=published_date, author=author)
    snapshot = capture(client)
    expected = f"Title: {TITLE}\nURL: {URL}{metadata_headers}\n\n{body}"[:8_000]
    assert snapshot.text == expected
    assert snapshot.source_sha256 == hashlib.sha256(expected.encode()).hexdigest()
    assert snapshot.retrieved_at.utcoffset() == timedelta(0)
    assert client.calls == [("search", "literary imagery"), ("get_contents", URL)]

    content, labels = connection_documents(ROOT)
    for setup in content["source_setups"]:
        setup["public_sources"] = [snapshot.model_dump(mode="json")]
    quote = "A public literary image."
    for proposal in labels["proposals"]:
        for evidence in proposal["evidence"]:
            if evidence["kind"] == "public_source":
                evidence.update(start_codepoint=expected.index(quote),
                                end_codepoint=expected.index(quote) + len(quote), text=quote)
    scene = validate_documents(content, labels, ROOT).scenes[1]
    events = list(restraint_events(scene))
    record = json.loads(events[2].evidence_json[0])
    record["excerpt"] = expected
    events[2] = replace(events[2], evidence_json=(json.dumps(record),))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)

    record["excerpt"] = "Changed public evidence."
    events[2] = replace(events[2], evidence_json=(json.dumps(record),))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all("public_source_changed_or_unresolved" in grade.failures for grade in grades)


def test_capture_requires_the_exact_search_lead_before_opening():
    client = FakeExaClient(search_url=URL + "/different")
    with pytest.raises(ValueError, match="not returned by public search"):
        capture(client)
    assert client.calls == [("search", "literary imagery")]


def test_capture_rejects_a_different_opened_source():
    client = FakeExaClient(page_url=URL + "/different")
    with pytest.raises(ValueError, match="did not produce guarded opened-page evidence"):
        capture(client)


def test_capture_keeps_the_production_private_query_gate():
    client = FakeExaClient()
    with pytest.raises(ModelRetry, match="privacy checks"):
        capture(client, query="reader@example.com literary imagery")
    assert client.calls == []


def test_cli_refuses_existing_output_before_capture(tmp_path, monkeypatch):
    output = tmp_path / "snapshot.json"
    output.write_text("existing snapshot", encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "public_source_capture", "--source-id", "source-public", "--url", URL,
        "--public-query", "literary imagery", "--output", str(output),
    ])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
    assert output.read_text(encoding="utf-8") == "existing snapshot"
