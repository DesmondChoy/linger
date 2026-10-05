"""A revision rewrites only the sentences its findings name."""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.claim_repair import (
    added_source_errors, draft_sentence_errors, draft_sentences_for_revision,
)
from src.linger.agents.muse.models import DraftSentence, MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview, UncoveredResponseSpan
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence
from tests.test_muse_claim_retention import revision_context
from tests.test_muse_repair_feedback import BOOK

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


def test_placement_records_draft_mappings_for_every_sentence():
    marks = placed(candidate(DRAFT, claims=(KEPT, FLAGGED)))
    assert [[(item.source_kind, item.evidence_id, item.mapped_text) for item in mark.source_mappings]
            for mark in marks] == [[("web", PAGE, KEPT)], [("web", PAGE, FLAGGED)], []]


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


ONE = "https://example.org/one"
TWO = "https://example.org/two"
IDENTITY = "Alice says she hardly knows who she is."
CLAUSE = "grounding the identity question in her body."
SIZE = f"Later, she says she dislikes changing so often and wants to be a little taller, {CLAUSE}"
TALLER = "Later, she says she dislikes changing so often and wants to be a little taller."


def identity_draft(size=SIZE):
    return declared(f"{IDENTITY} {size} {QUESTION}",
                    {"evidence_id": ONE, "supported_claims": [IDENTITY]},
                    {"evidence_id": TWO, "supported_claims": [size]})


def mapped(reply, *pairs):
    """One web declaration per (source, claims) pair."""
    return declared(reply, *({"evidence_id": source, "supported_claims": list(claims)}
                             for source, claims in pairs))


def added(revised, *locations):
    """The added-source errors for a revision of `identity_draft()` under these findings."""
    findings = review(*locations).response_findings
    marks = draft_sentences_for_revision(identity_draft(), review(*locations), ())
    return added_source_errors(revised, marks, findings)


REPAIRED = f"{IDENTITY} {TALLER} {QUESTION}"


def test_kept_wording_given_a_source_the_draft_did_not_map_is_rejected():
    """The recorded run: the flagged clause removed, the kept claim also mapped to another source."""
    errors = added(mapped(REPAIRED, (ONE, (IDENTITY, TALLER)), (TWO, (TALLER,))), quoted(CLAUSE))
    assert [(error["path"], error["value"], error["evidence_id"]) for error in errors] == [
        ("evidence_uses", TALLER, ONE),
    ]
    assert REPAIRED[errors[0]["response_start"]:errors[0]["response_end"]] == TALLER


def test_kept_wording_with_only_its_draft_source_passes():
    assert added(mapped(REPAIRED, (ONE, (IDENTITY,)), (TWO, (TALLER,))), quoted(CLAUSE)) == []


def test_unflagged_sentence_kept_word_for_word_cannot_gain_a_source():
    errors = added(mapped(REPAIRED, (ONE, (IDENTITY,)), (TWO, (IDENTITY, TALLER))), quoted(CLAUSE))
    assert [(error["value"], error["evidence_id"]) for error in errors] == [(IDENTITY, TWO)]


def test_wording_inside_a_finding_quote_may_be_mapped_to_another_source():
    assert added(mapped(REPAIRED, (ONE, (IDENTITY, TALLER))), quoted(SIZE)) == []
    assert added(mapped(REPAIRED, (ONE, (IDENTITY, TALLER)), (TWO, (TALLER,))), quoted(SIZE)) == []


@pytest.mark.parametrize("path", ["/1/supported_claims/0", "/1/evidence_id"])
def test_wording_whose_draft_mapping_a_finding_names_may_change_source(path):
    location = {"kind": "structural", "source_field": "candidate.evidence_uses", "path": path}
    kept = f"{IDENTITY} {SIZE} {QUESTION}"
    revised = mapped(kept, (ONE, (IDENTITY, SIZE)))
    assert added(revised, location) == []
    marks = draft_sentences_for_revision(identity_draft(), review(location), ())
    assert draft_sentence_errors(revised, marks) == []


def test_new_wording_beside_a_flagged_sentence_may_cite_any_source():
    new = "She wants to be bigger."
    reply = f"{IDENTITY} {TALLER} {new} {QUESTION}"
    assert added(mapped(reply, (ONE, (IDENTITY, new)), (TWO, (TALLER,))), quoted(CLAUSE)) == []


def test_draft_wording_the_draft_left_unmapped_may_gain_a_source():
    draft = mapped(f"{IDENTITY} {SIZE} {QUESTION}", (TWO, (SIZE,)))
    marks = draft_sentences_for_revision(draft, review(quoted(CLAUSE)), ())
    revised = mapped(REPAIRED, (ONE, (IDENTITY,)), (TWO, (TALLER,)))
    assert added_source_errors(revised, marks, review(quoted(CLAUSE)).response_findings) == []


def test_without_placement_the_added_source_rule_does_not_run():
    revised = mapped(REPAIRED, (ONE, (IDENTITY, TALLER)), (TWO, (TALLER,)))
    assert added_source_errors(revised, (), review(quoted(CLAUSE)).response_findings) == []


ASKS = "The Caterpillar asks who she is."
SHRINKS = "Alice cries and then shrinks to three inches."


@pytest.mark.parametrize("location", [
    quoted(SHRINKS), {"kind": "structural", "source_field": "candidate.evidence_uses", "path": "/1/supported_claims/0"},
])
def test_flagged_sentence_kept_with_a_second_source_for_joint_support_passes(location):
    """A declaration's sources may together establish a claim, so a disputed claim may gain one."""
    reply = f"{ASKS} {SHRINKS} {QUESTION}"
    draft = mapped(reply, (TWO, (ASKS,)), (ONE, (SHRINKS,)))
    marks = draft_sentences_for_revision(draft, review(location), ())
    joint = mapped(reply, (TWO, (ASKS, SHRINKS)), (ONE, (SHRINKS,)))
    assert draft_sentence_errors(joint, marks) == []
    assert added_source_errors(joint, marks, review(location).response_findings) == []


def test_flagged_sentence_kept_with_a_source_added_outside_the_quote_is_rejected():
    kept = "Later, she says she dislikes changing so often and wants to be a little taller"
    revised = mapped(f"{IDENTITY} {SIZE} {QUESTION}", (ONE, (IDENTITY, kept)), (TWO, (SIZE,)))
    assert [(error["value"], error["evidence_id"]) for error in added(revised, quoted(CLAUSE))] == [(kept, ONE)]


def test_moving_kept_wording_outside_a_partial_quote_to_another_source_is_rejected():
    """A documented limit: when the finding quotes only part of a sentence, re-sourcing the rest is
    indistinguishable from the recorded failure, even if the explanation asked for it."""
    errors = added(mapped(REPAIRED, (ONE, (IDENTITY, TALLER))), quoted(CLAUSE))
    assert [(error["value"], error["evidence_id"]) for error in errors] == [(TALLER, ONE)]


def test_restoring_a_flagged_sentence_with_only_whitespace_changed_is_unaddressed():
    broken = "Alice cries and then\nshrinks to three inches."
    draft = mapped(f"{ASKS} {broken} {QUESTION}", (TWO, (ASKS,)), (ONE, (broken,)))
    marks = draft_sentences_for_revision(draft, review(quoted("shrinks to three")), ())
    restored = mapped(f"{ASKS} {SHRINKS} {QUESTION}", (TWO, (ASKS,)), (ONE, (SHRINKS,)))
    assert [error["value"] for error in draft_sentence_errors(restored, marks)] == [SHRINKS]


def test_short_new_claim_that_prefixes_a_draft_sentence_is_new_wording():
    draft = mapped(f"{ASKS} {SIZE} {QUESTION}", (ONE, (ASKS,)), (TWO, (SIZE,)))
    marks = draft_sentences_for_revision(draft, review(quoted(CLAUSE)), ())
    short = "The Caterpillar asks."
    revised = mapped(f"{ASKS} {TALLER} {short} {QUESTION}", (ONE, (ASKS,)), (TWO, (TALLER, short)))
    assert added_source_errors(revised, marks, review(quoted(CLAUSE)).response_findings) == []


def test_finding_index_without_a_finding_is_ignored():
    marks = tuple(mark.model_copy(update={"finding_indexes": (3,)}) if mark.flagged else mark
                  for mark in draft_sentences_for_revision(identity_draft(), review(quoted(CLAUSE)), ()))
    revised = mapped(REPAIRED, (ONE, (IDENTITY,)), (TWO, (TALLER,)))
    assert added_source_errors(revised, marks, review(quoted(CLAUSE)).response_findings) == []


def test_actual_muse_validator_returns_an_added_source_for_repair():
    records = [BOOK.model_copy(update={"evidence_id": source}) for source in ("book-one", "book-two")]

    def book(reply, *pairs):
        return MuseCandidate.model_validate({
            "reply": reply,
            "evidence_uses": [{"source_kind": "book_corpus", "evidence_id": record.evidence_id,
                               "source_location": record.location, "supported_claims": list(claims)}
                              for record, claims in zip(records, pairs) if claims],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        })

    draft = book(f"{IDENTITY} {SIZE} {QUESTION}", (IDENTITY,), (SIZE,))
    payload = json.loads(revision_context().prompt)
    payload["review"]["findings"] = [finding.model_dump(mode="json")
                                     for finding in review(quoted(CLAUSE)).response_findings]
    payload["review"]["draft_sentences"] = [
        item.model_dump(mode="json") for item in draft_sentences_for_revision(draft, review(quoted(CLAUSE)), ())
    ]
    context = SimpleNamespace(prompt=json.dumps(payload))
    token = set_turn_evidence(records)
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(context, book(REPAIRED, (IDENTITY, TALLER), (TALLER,)))
        assert [(error["path"], error["value"], error.get("evidence_id"))
                for error in json.loads(str(caught.value))["errors"]] == [("evidence_uses", TALLER, "book-one")]
        repaired = book(REPAIRED, (IDENTITY,), (TALLER,))
        assert validate_muse_output(context, repaired) is repaired
    finally:
        reset_turn_evidence(token)


def kept_errors(draft_size, kept):
    """The recorded shape: the clause removed, the kept wording also mapped to the other source."""
    findings = review(quoted(CLAUSE)).response_findings
    marks = draft_sentences_for_revision(identity_draft(draft_size), review(quoted(CLAUSE)), ())
    revised = mapped(f"{IDENTITY} {kept} {QUESTION}", (ONE, (IDENTITY, kept)), (TWO, (kept,)))
    return [(error["value"], error["evidence_id"]) for error in added_source_errors(revised, marks, findings)]


WANTS = "Later, she says she dislikes changing so often and wants to be a little taller"


@pytest.mark.parametrize("draft_size", [
    f"{WANTS}—{CLAUSE}",
    f"{WANTS} — {CLAUSE}",
    f"Later, she says she “dislikes changing so often and wants to be a little taller” {CLAUSE}",
    f"Later, she says she (dislikes changing so often and wants to be a little taller) {CLAUSE}",
    f"Later, she says she dislikes changing so often and wants to be a little _taller_ {CLAUSE}",
    f"{WANTS}\n{CLAUSE}",
    f"{WANTS} {CLAUSE}",
], ids=["em-dash", "spaced-em-dash", "closing-quote", "bracket", "emphasis", "newline", "space"])
def test_kept_wording_is_recognised_whatever_followed_it_in_the_draft(draft_size):
    assert kept_errors(draft_size, TALLER) == [(TALLER, ONE)]


@pytest.mark.parametrize("kept", [
    "later, she says she dislikes changing so often and wants to be a little taller.",
    "Later, she says she dislikes changing so often and wants to be a bit taller.",
    f"{WANTS} ([the passage](https://example.org/two)).",
    f"{WANTS} than she is now.",
], ids=["capitalisation", "one-changed-word", "markdown-link", "added-words"])
def test_lightly_edited_kept_wording_is_still_kept_wording(kept):
    assert kept_errors(SIZE, kept) == [(kept, ONE)]


def test_mostly_new_claim_reusing_a_short_draft_phrase_is_new_wording():
    assert kept_errors(SIZE, "Later, she says nothing at all about the mushroom.") == []


def test_new_words_around_a_kept_run_below_the_share_threshold_are_new_wording():
    new = ("Like many children in old stories, she dislikes changing so often and wants to be different, "
           "and that restlessness drives the whole chapter onward.")
    assert kept_errors(SIZE, new) == []


def added_to(draft, location, revised):
    marks = draft_sentences_for_revision(draft, review(location), ())
    return [(error["value"], error["evidence_id"])
            for error in added_source_errors(revised, marks, review(location).response_findings)]


TEARS = "Alice cries a pool of tears and then shrinks to three inches tall in the hall."


def test_joint_support_on_a_claim_a_short_quote_touches_passes():
    draft = mapped(f"{TEARS} {QUESTION}", (ONE, (TEARS,)))
    location = quoted("shrinks to three inches")
    assert added_to(draft, location, mapped(f"{TEARS} {QUESTION}", (ONE, (TEARS,)), (TWO, (TEARS,)))) == []
    tail = "and then shrinks to three inches tall in the hall."
    assert added_to(draft, location, mapped(f"{TEARS} {QUESTION}", (ONE, (TEARS,)), (TWO, (tail,)))) == []


def test_claim_entirely_inside_a_finding_quote_may_take_any_source():
    inside = "She dislikes changing so often and wants to be a little taller."
    location = quoted("dislikes changing so often and wants to be a little taller")
    assert added_to(identity_draft(), location, mapped(f"{IDENTITY} {inside} {QUESTION}", (ONE, (IDENTITY, inside)))) == []


def test_kept_wording_repeated_in_the_draft_may_keep_either_draft_source():
    first = "First, she says she dislikes changing so often in one day."
    again = "Again, she says she dislikes changing so often in one day, the Pigeon notes."
    draft = mapped(f"{first} {again} {QUESTION}", (ONE, (first,)), (TWO, (again,)))
    kept = "she says she dislikes changing so often in one day"
    revised = mapped(f"{first} Again, {kept}. {QUESTION}", (ONE, (first,)), (TWO, (kept,)))
    assert added_to(draft, quoted("the Pigeon notes"), revised) == []


def test_short_kept_sentence_cannot_gain_a_source():
    screams = "The Pigeon screams at Alice."
    draft = mapped(f"{screams} {SIZE} {QUESTION}", (ONE, (screams,)), (TWO, (SIZE,)))
    revised = mapped(f"{screams} {TALLER} {QUESTION}", (ONE, (screams,)), (TWO, (screams, TALLER)))
    assert added_to(draft, quoted(CLAUSE), revised) == [(screams, TWO)]
