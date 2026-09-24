"""Muse repairs reader application and undeclared source quotes before review."""

import json

import pytest
from pydantic_ai import ModelRetry

from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.models import MuseCandidate
from src.linger.contracts.connection_evidence import (
    MemoryConnectionEvidence, WebConnectionEvidence,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection, register_connection_evidence, reset_connection_inspection,
)
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence

BOOK_TEXT = (
    'The captain said, “I gave my word at the harbour, you know, and I will keep it.”\n'
    'Then the crew spent the whole night singing on the deck.'
)
BOOK = EvidenceRecord(
    evidence_id="vow", work_id="fiction", book_version_id="fiction-v1",
    chapter_id="fiction-ch1", chapter_number=1,
    location="Chapter 1, source lines 1-2", source_sha256="a" * 64,
    source_lines=(1, 2), text=BOOK_TEXT,
)
URL = "https://example.org/essay"
WEB = WebConnectionEvidence(
    evidence_id=URL, title="Essays Online",
    excerpt="Title: Essays Online\n\n#### Of changing minds.\n\nA mind is a procession of passing moods.",
)
MEMORY_ID = "mem_" + "1234567890abcdef" * 4
MEMORY = MemoryConnectionEvidence(
    evidence_id=MEMORY_ID, excerpt="Both felt like me, even at work and at dinner.",
)


@pytest.fixture(autouse=True)
def authorized_sources():
    evidence = set_turn_evidence((BOOK,))
    inspection = begin_connection_inspection()
    register_connection_evidence([WEB, MEMORY])
    try:
        yield
    finally:
        reset_connection_inspection(inspection)
        reset_turn_evidence(evidence)


def book_use(*claims, quote=None):
    return {
        "source_kind": "book_corpus", "evidence_id": "vow",
        "source_location": BOOK.location, "supported_claims": list(claims), "exact_quote": quote,
    }


def candidate(reply, *uses):
    return MuseCandidate.model_validate({
        "reply": reply, "evidence_uses": list(uses),
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def errors(output):
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(None, output)
    return json.loads(str(caught.value))["errors"]


def test_reader_application_inside_a_book_mapping_is_returned_for_splitting():
    welded = "The captain keeps his vow despite the singing, so you can keep yours too."
    error, = errors(candidate(welded, book_use(welded)))
    assert error["path"] == "evidence_uses[0].supported_claims[0]"
    assert error["reader_reference"] == "you"

    source_claim = "The captain keeps his vow despite the singing."
    split = source_claim + " You might ask which of your promises still matter."
    output = candidate(split, book_use(source_claim))
    assert validate_muse_output(None, output) == output


def test_reader_words_inside_a_source_quotation_are_not_application():
    quote = "I gave my word at the harbour, you know, and I will keep it."
    reply = f"The captain says, “{quote}”"
    output = candidate(reply, book_use(reply, quote=quote))
    assert validate_muse_output(None, output) == output


def test_memory_mappings_may_address_the_reader():
    claim = "You wrote that you felt like yourself at work and at dinner."
    output = candidate(claim, {
        "source_kind": "memory", "evidence_id": MEMORY_ID, "supported_claims": [claim],
    })
    assert validate_muse_output(None, output) == output


def test_verbatim_source_wording_in_quotes_needs_an_exact_quote_on_the_first_draft():
    claim = "The captain says “I will keep it” and the crew spent “the whole night singing”."
    error, = errors(candidate(claim, book_use(claim, quote="I will keep it")))
    assert error["value"] == "the whole night singing"
    assert error["matching_declared_sources"][0]["declaration_index"] == 0

    both = candidate(
        claim,
        book_use(claim, quote="I will keep it"),
        book_use(claim, quote="the whole night singing"),
    )
    assert validate_muse_output(None, both) == both


def test_undeclared_memory_wording_in_quotes_is_flagged():
    claim = "You wrote that both modes “felt like me, even at work”."
    error, = errors(candidate(claim, {
        "source_kind": "memory", "evidence_id": MEMORY_ID, "supported_claims": [claim],
    }))
    assert error["value"] == "felt like me, even at work"


def test_a_quoted_title_matching_a_source_heading_is_not_a_quotation():
    claim = f"In “Of changing minds” the essay calls a mind a procession of moods ([Essays]({URL}))"
    output = candidate(claim + ".", {
        "source_kind": "web", "evidence_id": URL, "supported_claims": [claim],
    })
    assert validate_muse_output(None, output) == output
