"""A revision rewrites only the sentences its findings name."""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.claim_repair import draft_sentence_errors, draft_sentences_for_revision
from src.linger.agents.muse.models import DraftSentence, MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview, UncoveredResponseSpan
from tests.test_muse_claim_retention import revision_context

KEPT = "Alice feels changed."
FLAGGED = "Pinocchio breaks his promise."
QUESTION = "What would you weigh?"
DRAFT = f"{KEPT} {FLAGGED} {QUESTION}"


def candidate(reply, *, claims=(), limits=()):
    uses = []
    if claims or limits:
        uses.append({
            "source_kind": "web", "evidence_id": "https://example.org/page",
            "supported_claims": list(claims),
            "limit_claims": list(limits),
        })
    return MuseCandidate.model_validate({
        "reply": reply, "evidence_uses": uses,
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def review(location, *, source_dependent=()):
    return ProvenanceReview.model_validate({
        "response_decision": "revise", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "findings": [{
            "code": "unsupported_claim", "applies_to": "response", "location": location,
            "explanation": "The passage shows a delay, not a broken promise.",
        }],
        "coverage_audit": [
            {"span_index": index, "classification": "source_dependent"}
            for index in source_dependent
        ],
    })


def quoted(text):
    return {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": text}


def sentences(*, flagged=(FLAGGED,), needs_source=()):
    return tuple(DraftSentence(text=text, flagged=text in flagged, needs_source=text in needs_source)
                 for text in (KEPT, FLAGGED, QUESTION))


def test_findings_mark_only_the_sentences_they_name():
    marked = draft_sentences_for_revision(candidate(DRAFT), review(quoted("breaks his")), ())
    assert [(item.text, item.flagged) for item in marked] == [
        (KEPT, False), (FLAGGED, True), (QUESTION, False),
    ]


def test_limit_claim_finding_marks_the_limit_sentence():
    draft = candidate(DRAFT, claims=(KEPT,), limits=(QUESTION,))
    location = {"kind": "structural", "source_field": "candidate.evidence_uses", "path": "/0/limit_claims/0"}
    marked = draft_sentences_for_revision(draft, review(location), ())
    assert [item.text for item in marked if item.flagged] == [QUESTION]


@pytest.mark.parametrize("location", [
    quoted("Not in the draft."),
    {"kind": "structural", "source_field": "candidate.response", "path": ""},
    {"kind": "structural", "source_field": "canonical_book_evidence", "path": "/0"},
])
def test_a_finding_that_cannot_be_placed_leaves_every_sentence_open(location):
    assert draft_sentences_for_revision(candidate(DRAFT), review(location), ()) == ()


def test_source_dependent_uncovered_span_marks_its_sentence():
    start = DRAFT.index(FLAGGED)
    span = UncoveredResponseSpan(span_index=0, start=start, end=start + len(FLAGGED), text=FLAGGED)
    marked = draft_sentences_for_revision(candidate(DRAFT), review(quoted(FLAGGED), source_dependent=(0,)), (span,))
    assert [item.text for item in marked if item.needs_source] == [FLAGGED]


def test_flagged_rewrite_and_unflagged_deletion_are_allowed():
    assert draft_sentence_errors(candidate(f"{KEPT} Pinocchio is late. {QUESTION}"), sentences()) == []
    assert draft_sentence_errors(candidate(f"Pinocchio is late. {QUESTION}"), sentences()) == []
    assert draft_sentence_errors(candidate(f"{KEPT} Pinocchio is late. He stays. {QUESTION}"), sentences()) == []


def test_rewording_an_unflagged_sentence_names_the_draft_sentence():
    errors = draft_sentence_errors(candidate(f"Alice feels different. Pinocchio is late. {QUESTION}"), sentences())
    assert [(error["value"], error["draft_sentence"]) for error in errors] == [("Alice feels different.", KEPT)]


def test_new_sentence_away_from_any_flagged_sentence_is_rejected():
    errors = draft_sentence_errors(candidate(f"{KEPT} Pinocchio is late. {QUESTION} Hume agrees."), sentences())
    assert [error["value"] for error in errors] == ["Hume agrees."]


def test_source_dependent_sentence_must_be_mapped_or_deleted():
    marks = sentences(needs_source=(FLAGGED,))
    rewrite = "Pinocchio delays his promise."
    assert draft_sentence_errors(candidate(f"{KEPT} {rewrite} {QUESTION}"), marks)
    assert draft_sentence_errors(candidate(f"{KEPT} {rewrite} {QUESTION}", claims=(rewrite,)), marks) == []
    assert draft_sentence_errors(candidate(f"{KEPT} {QUESTION}"), marks) == []
    assert draft_sentence_errors(candidate(f"{KEPT} Why does Pinocchio delay his promise? {QUESTION}"), marks) == []
    hedge = "I can't cite a source for that here, so I won't describe it."
    assert draft_sentence_errors(candidate(f"{KEPT} {hedge} {QUESTION}"), marks) == []


def test_whitespace_changes_and_captured_envelopes_without_sentences_pass():
    assert draft_sentence_errors(candidate(f"{KEPT}\n\nPinocchio is late.  {QUESTION}"), sentences()) == []
    assert draft_sentence_errors(candidate("Anything at all."), ()) == []


def test_actual_muse_validator_returns_an_unflagged_rewrite_for_repair():
    payload = json.loads(revision_context().prompt)
    payload["review"]["draft_sentences"] = [item.model_dump() for item in sentences()]
    context = SimpleNamespace(prompt=json.dumps(payload))
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(context, candidate(f"Alice feels different. Pinocchio is late. {QUESTION}"))
    assert KEPT in str(caught.value)
    kept = candidate(f"{KEPT} Pinocchio is late. {QUESTION}")
    assert validate_muse_output(context, kept) is kept


def test_replacement_wording_beside_a_flagged_sentence_is_not_a_rewrite_of_its_neighbour():
    marks = (DraftSentence(text=FLAGGED, flagged=True, needs_source=False),
             DraftSentence(text="It was standardised in the 1920s.", flagged=False, needs_source=False))
    hedge = "I can't cite a source for that here. What drew you to the question?"
    assert draft_sentence_errors(candidate(hedge), marks) == []
    assert draft_sentence_errors(candidate("Pinocchio is late. It was standardized in the 1920s."), marks)
