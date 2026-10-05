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


PAGE = "https://example.org/page"


def candidate(reply, *, claims=(), limits=(), source=PAGE):
    uses = []
    if claims or limits:
        uses.append({
            "source_kind": "web", "evidence_id": source,
            "supported_claims": list(claims),
            "limit_claims": list(limits),
        })
    return MuseCandidate.model_validate({
        "reply": reply, "evidence_uses": uses,
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def review(*locations, source_dependent=()):
    return ProvenanceReview.model_validate({
        "response_decision": "revise", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "findings": [{
            "code": "unsupported_claim", "applies_to": "response", "location": location,
            "explanation": "The passage shows a delay, not a broken promise.",
        } for location in locations],
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


def placed(draft, *flagged):
    """Production placement for a draft with one quoted finding per `flagged` text."""
    return draft_sentences_for_revision(draft, review(*(quoted(text) for text in flagged or (FLAGGED,))), ())


def declared(reply, *uses):
    """A candidate with one web declaration per `uses` dict."""
    return MuseCandidate.model_validate({
        "reply": reply,
        "evidence_uses": [{"source_kind": "web", **use} for use in uses],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def test_placement_records_draft_mappings_for_flagged_sentences_only():
    marks = placed(candidate(DRAFT, claims=(KEPT, FLAGGED)))
    assert [[(item.source_kind, item.evidence_id, item.mapped_text) for item in mark.source_mappings]
            for mark in marks] == [[], [("web", PAGE, FLAGGED)], []]


def test_flagged_sentence_restored_with_its_draft_mapping_is_rejected():
    errors = draft_sentence_errors(candidate(DRAFT, claims=(FLAGGED,)), placed(candidate(DRAFT, claims=(FLAGGED,))))
    assert [(error["value"], error["draft_sentence"]) for error in errors] == [(FLAGGED, FLAGGED)]


def test_unmapped_flagged_sentence_restored_unmapped_is_rejected():
    errors = draft_sentence_errors(candidate(DRAFT), placed(candidate(DRAFT)))
    assert [error["draft_sentence"] for error in errors] == [FLAGGED]


def test_moved_flagged_sentence_with_its_draft_mapping_is_rejected():
    moved = candidate(f"{FLAGGED} {KEPT} {QUESTION}", claims=(FLAGGED,))
    errors = draft_sentence_errors(moved, placed(candidate(DRAFT, claims=(FLAGGED,))))
    assert [error["draft_sentence"] for error in errors] == [FLAGGED]


@pytest.mark.parametrize("revised", [
    candidate(DRAFT, claims=(FLAGGED,), source="https://example.org/other"),
    candidate(DRAFT, claims=("Pinocchio breaks",)),
])
def test_flagged_sentence_kept_word_for_word_may_change_its_mapping(revised):
    assert draft_sentence_errors(revised, placed(candidate(DRAFT, claims=(FLAGGED,)))) == []


def test_flagged_claim_merged_into_an_unflagged_sentence_is_still_an_unflagged_rewrite():
    neck = "Alice’s neck has grown so long that her head rises above the trees."
    marks = placed(candidate(f"{neck} {FLAGGED}", claims=(neck,)))
    merged = neck[:-1] + ", so Pinocchio breaks his promise."
    errors = draft_sentence_errors(candidate(merged, claims=(merged,)), marks)
    assert [error["draft_sentence"] for error in errors] == [neck]


def test_flagged_sentence_split_inside_a_quotation_must_still_change():
    serpent = ("It sees Alice’s unusually long neck and says serpents come “wriggling down\nfrom the sky! "
               "Ugh, Serpent!”—so it takes her for one.")
    draft = f"{KEPT} {serpent} {QUESTION}"
    marks = placed(candidate(draft, claims=(serpent,)), serpent)
    pieces = [serpent[:serpent.index(" Ugh")], serpent[serpent.index("Ugh"):]]
    assert [mark.text for mark in marks if mark.flagged] == pieces
    errors = draft_sentence_errors(candidate(draft, claims=(serpent,)), marks)
    assert [error["draft_sentence"] for error in errors] == pieces
    rewrite = "It takes Alice for a serpent because of her long neck."
    assert draft_sentence_errors(candidate(f"{KEPT} {rewrite} {QUESTION}", claims=(rewrite,)), marks) == []


def test_actual_muse_validator_returns_a_restored_draft_for_repair():
    payload = json.loads(revision_context().prompt)
    payload["review"]["draft_sentences"] = [item.model_dump() for item in placed(candidate(DRAFT))]
    context = SimpleNamespace(prompt=json.dumps(payload))
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(context, candidate(DRAFT))
    assert [error.get("draft_sentence") for error in json.loads(str(caught.value))["errors"]] == [FLAGGED]
    repaired = candidate(f"{KEPT} Pinocchio is late. {QUESTION}")
    assert validate_muse_output(context, repaired) is repaired


PROMISE = "Pinocchio makes a promise to Geppetto."
BROKEN = "He breaks the promise the next morning."
LATE = "He delays keeping it."


def promise(second, second_claim):
    return declared(f"{PROMISE} {second} {QUESTION}",
                    {"evidence_id": "https://example.org/one", "supported_claims": [PROMISE]},
                    {"evidence_id": "https://example.org/two", "supported_claims": [second_claim]})


def test_finding_naming_two_sentences_is_addressed_by_repairing_one():
    marks = placed(promise(BROKEN, BROKEN), "promise")
    assert [mark.text for mark in marks if mark.flagged] == [PROMISE, BROKEN]
    assert draft_sentence_errors(promise(LATE, LATE), marks) == []
    restored = draft_sentence_errors(promise(BROKEN, BROKEN), marks)
    assert [error["draft_sentence"] for error in restored] == [PROMISE, BROKEN]


def test_declaration_finding_is_addressed_by_repairing_its_quotation_sentence():
    asked = "Alice asks, “Who in the world am I?”"
    fixed = "Alice asks, “Who am I, then?”"

    def draft(sentence, quote):
        return declared(f"{KEPT} {sentence} {QUESTION}", {
            "evidence_id": PAGE, "supported_claims": [KEPT, sentence], "exact_quote": quote,
        })

    location = {"kind": "structural", "source_field": "candidate.evidence_uses", "path": "/0/exact_quote"}
    marks = draft_sentences_for_revision(draft(asked, "Who in the world am I?"), review(location), ())
    assert [mark.text for mark in marks if mark.flagged] == [KEPT, asked]
    assert draft_sentence_errors(draft(fixed, "Who am I, then?"), marks) == []
    restored = draft_sentence_errors(draft(asked, "Who in the world am I?"), marks)
    assert [error["draft_sentence"] for error in restored] == [KEPT, asked]


def test_finding_quote_across_a_sentence_boundary_is_addressed_by_repairing_one_side():
    marks = placed(candidate(DRAFT, claims=(KEPT, FLAGGED)), "changed. Pinocchio")
    assert [mark.text for mark in marks if mark.flagged] == [KEPT, FLAGGED]
    late = "Pinocchio is late."
    assert draft_sentence_errors(candidate(f"{KEPT} {late} {QUESTION}", claims=(KEPT, late)), marks) == []
    restored = draft_sentence_errors(candidate(DRAFT, claims=(KEPT, FLAGGED)), marks)
    assert [error["draft_sentence"] for error in restored] == [KEPT, FLAGGED]


def test_each_finding_must_change_a_sentence_it_names():
    marks = placed(candidate(DRAFT, claims=(KEPT, FLAGGED)), "changed. Pinocchio", "Alice")
    late = "Pinocchio is late."
    errors = draft_sentence_errors(candidate(f"{KEPT} {late} {QUESTION}", claims=(KEPT, late)), marks)
    assert [error["draft_sentence"] for error in errors] == [KEPT]


def test_a_source_dependent_rewording_does_not_address_its_finding():
    start = DRAFT.index(FLAGGED)
    span = UncoveredResponseSpan(span_index=0, start=start, end=start + len(FLAGGED), text=FLAGGED)
    marks = draft_sentences_for_revision(
        candidate(DRAFT, claims=(KEPT,)), review(quoted("changed. Pinocchio"), source_dependent=(0,)), (span,),
    )
    reworded = "Pinocchio breaks his word."
    errors = draft_sentence_errors(candidate(f"{KEPT} {reworded} {QUESTION}", claims=(KEPT,)), marks)
    assert {(error["path"], error["value"]) for error in errors} == {
        ("evidence_uses", reworded), ("reply", KEPT),
    }


def test_dropping_a_flagged_sentences_mapping_counts_as_a_change():
    """A documented limit: the next review, not this check, judges the now-unmapped text."""
    assert draft_sentence_errors(candidate(DRAFT), placed(candidate(DRAFT, claims=(FLAGGED,)))) == []


def test_replacement_wording_beside_a_flagged_sentence_is_not_a_rewrite_of_its_neighbour():
    marks = (DraftSentence(text=FLAGGED, flagged=True, needs_source=False),
             DraftSentence(text="It was standardised in the 1920s.", flagged=False, needs_source=False))
    hedge = "I can't cite a source for that here. What drew you to the question?"
    assert draft_sentence_errors(candidate(hedge), marks) == []
    assert draft_sentence_errors(candidate("Pinocchio is late. It was standardized in the 1920s."), marks)
