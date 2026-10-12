"""After a revision's review asks for another change, the application removes the named sentences."""

import asyncio
import json
from unittest.mock import AsyncMock

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_ai.messages import ToolReturnPart

from src.linger.agents.muse.models import (
    BookEvidenceUse,
    MemoryCandidate,
    MuseCandidate,
    NoMemoryCandidate,
    SessionLineUse,
)
from src.linger.agents.provenance.models import ProvenanceReview, RiskCode, RiskFinding
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection,
    reset_connection_inspection,
)
from src.linger.orchestration.progress_context import begin_progress, reset_progress
from src.linger.orchestration import reflection
from src.linger.orchestration.sentence_trim import TrimRefused, trim_named_sentences
from src.linger.orchestration.reflection import (
    EVIDENCE_DECLINE,
    PIPELINE_FAILURE_DECLINE,
    decline_text,
)
from src.linger.orchestration.turn_context import (
    add_turn_evidence,
    reset_active_memories,
    reset_turn_evidence,
    set_active_memories,
    set_turn_evidence,
)
from tests.test_reflection import (
    EVIDENCE_ID,
    LOCATION,
    RELEASE_SCOPE,
    SECOND_EVIDENCE_ID,
    SECOND_LOCATION,
    QUOTE,
    canonical_record,
    evidence_record,
    reflection_reply,
    result,
    retrieval_result,
    review,
    route_clarification,
)

ALLOWED = {
    RiskCode.UNSUPPORTED_CLAIM, RiskCode.UNRESOLVED_EVIDENCE, RiskCode.MISATTRIBUTION, RiskCode.UNCITED_WEB_CLAIM,
}
MESSAGE = "Why does the Pigeon call Alice a serpent? I keep thinking about being misread."
NECK = "The Pigeon points to her long neck."
EGGS = "It also fears serpents raiding its eggs."
MIDDLE = "It has never seen a girl like her."
CLOSE = "What do you make of that?"
REVISION = f"{NECK} {EGGS} {CLOSE}"
NO_MEMORY = NoMemoryCandidate(kind="no_memory_candidate", reason_code="transient_or_low_signal")
RESOLVED = {"finding_index": 0, "status": "resolved", "explanation": "The sentence is gone."}


@pytest.fixture(autouse=True)
def turn():
    """One turn whose search returned two permitted book records."""
    evidence = set_turn_evidence(())
    connection = begin_connection_inspection()
    memories = set_active_memories(())
    add_turn_evidence((
        canonical_record(),
        canonical_record(evidence_id=SECOND_EVIDENCE_ID, location=SECOND_LOCATION),
    ))
    yield
    reset_active_memories(memories)
    reset_connection_inspection(connection)
    reset_turn_evidence(evidence)


def book(*claims: str, second: bool = False, **fields: object) -> BookEvidenceUse:
    """Map each sentence without its full stop, so a finding that quotes the sentence is not a whole-claim finding."""
    return BookEvidenceUse(
        source_kind="book_corpus",
        evidence_id=SECOND_EVIDENCE_ID if second else EVIDENCE_ID,
        source_location=SECOND_LOCATION if second else LOCATION,
        supported_claims=tuple(claim.removesuffix(".") for claim in claims),
        **fields,
    )


def revision(reply: str = REVISION, *uses, memory=NO_MEMORY) -> MuseCandidate:
    return MuseCandidate(reply=reply, evidence_uses=uses or (book(NECK, EGGS),), memory=memory)


def finding(quote: str | None = None, *, code: str = "unsupported_claim", **location: object) -> RiskFinding:
    location = location or {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": quote}
    return RiskFinding(code=code, applies_to="response", location=location, explanation="Not established.")


def second_review(*findings: RiskFinding, decision: str = "revise", resolved: str = "resolved", **fields) -> ProvenanceReview:
    return ProvenanceReview(
        findings=findings, response_decision=decision, emotional_boundary_decision="not_required",
        capture_decision=fields.pop("capture_decision", "no_candidate"),
        finding_resolutions=({**RESOLVED, "status": resolved},), **fields,
    )


def third_review(decision: str = "pass", *, count: int = 1, **fields) -> ProvenanceReview:
    findings = () if decision == "pass" else (finding(code="unsupported_claim", kind="structural",
                                                      source_field="candidate.response", path=""),)
    return ProvenanceReview(
        findings=fields.pop("findings", findings), response_decision=decision,
        emotional_boundary_decision=fields.pop("emotional_boundary_decision", "not_required"),
        capture_decision=fields.pop("capture_decision", "no_candidate"),
        finding_resolutions=tuple({**RESOLVED, "finding_index": index} for index in range(count)),
        **fields,
    )


def run(
    revised: MuseCandidate, second: ProvenanceReview, *third: ProvenanceReview | Exception,
    message: str = MESSAGE, draft: str = "A first draft.", first: ProvenanceReview | None = None,
    revision_tools: tuple[ToolReturnPart, ...] = (), review_context: dict | None = None,
):
    """Draft, first `revise`, Muse's revision, then the scripted later reviews."""
    muse = AsyncMock()
    muse.run.side_effect = [
        result(draft, ToolReturnPart("librarian_search", retrieval_result(evidence=[
            evidence_record(),
            evidence_record(evidence_id=SECOND_EVIDENCE_ID, location=SECOND_LOCATION),
        ]))),
        result(revised, *revision_tools),
    ]
    provenance = AsyncMock()
    provenance.run.side_effect = [
        result(first or review("revise")), result(second),
        *(item if isinstance(item, Exception) else result(item) for item in third),
    ]
    release = asyncio.run(reflection_reply(
        message, [], muse=muse, provenance=provenance, release_scope=RELEASE_SCOPE,
        source_event_id="test-turn", review_context=review_context,
    ))
    inputs = [json.loads(call.args[0]) for call in provenance.run.await_args_list]
    return release, inputs, muse


def test_named_sentence_is_removed_and_the_trimmed_candidate_released_after_a_third_review():
    second = second_review(finding(EGGS))

    release, inputs, muse = run(revision(), second, third_review())

    assert release.reply == f"{NECK} {CLOSE}"
    assert release.release_source == "muse_candidate"
    assert release.provenance_verdicts == ("revise", "revise", "pass")
    assert release.review_finding_codes == (("unsupported_claim",), ("unsupported_claim",), ())
    assert release.revision_count == 1
    assert release.trimmed_sentence_count == 1
    assert release.released_evidence_ids == (EVIDENCE_ID,)
    assert muse.run.await_count == 2
    assert len(inputs) == 3
    assert inputs[2]["candidate"] == {
        "response": f"{NECK} {CLOSE}",
        "evidence_uses": [book(NECK).model_dump(mode="json")],
        "memory": NO_MEMORY.model_dump(mode="json"),
    }


def test_third_review_rechecks_the_revision_and_the_findings_that_prompted_the_trim():
    second = second_review(finding(EGGS))

    _, inputs, _ = run(revision(), second, third_review())

    previous = inputs[2]["previous_response_review"]
    assert previous["candidate"] == inputs[1]["candidate"]
    assert previous["candidate"]["response"] == REVISION
    assert previous["findings"] == [item.model_dump(mode="json") for item in second.response_findings]


@pytest.mark.parametrize("verdict", ["revise", "reject"])
def test_trimmed_candidate_that_does_not_pass_is_declined(verdict):
    release, inputs, _ = run(revision(), second_review(finding(EGGS)), third_review(verdict))

    assert release.reply == EVIDENCE_DECLINE
    assert release.release_source == "application_safe_decline"
    assert release.provenance_verdicts == ("revise", "revise", verdict)
    assert release.failure_stage is None
    assert release.released_evidence_ids == ()
    assert release.trimmed_sentence_count == 1
    assert len(inputs) == 3


def test_a_pass_that_leaves_a_prompting_finding_unresolved_cannot_release():
    unaccounted = ProvenanceReview(
        response_decision="pass", emotional_boundary_decision="not_required", capture_decision="no_candidate",
    )

    release, inputs, _ = run(revision(), second_review(finding(EGGS)), unaccounted)

    assert release.reply == PIPELINE_FAILURE_DECLINE
    assert (release.failure_stage, release.failure_type) == ("provenance_review", "validation")
    assert release.provenance_verdicts == ("revise", "revise")
    assert len(inputs) == 3


def test_trimmed_review_that_requires_the_emotional_boundary_applies_it():
    boundary = third_review(
        "reject", emotional_boundary_decision="required",
        findings=(finding(code="emotional_policy_violation", kind="structural",
                          source_field="current_line.text", path=""),),
    )

    release, _, _ = run(revision(), second_review(finding(EGGS)), boundary)

    assert release.release_source == "application_emotional_boundary"
    assert release.provenance_verdicts == ("revise", "revise", "reject")
    assert release.revision_count == 1
    assert release.trimmed_sentence_count == 1


def test_third_review_keeps_the_reading_context_the_revision_was_reviewed_under():
    routed = ToolReturnPart("librarian_route", {
        "kind": "routed", "request_id": "routereq-routed", "work_id": "pg11",
        "book_version_id": "pg11-v01b38ea4", "title": "Alice's Adventures in Wonderland",
        "routing_confidence": 1.0, "max_chapter_inclusive": 3, "boundary_confidence": 0.9,
        "selection_basis": "resolved_book_identity",
    })
    policy = {"spoiler_ceiling": None, "allow_retrieval": False, "allow_connection": False,
              "allow_memory_capture": False}

    release, inputs, _ = run(
        revision(), second_review(finding(EGGS)), third_review(),
        revision_tools=(routed,), review_context={"policy_constraints": policy},
    )

    assert release.reply == f"{NECK} {CLOSE}"
    assert inputs[0]["context"]["reading_context"] is None
    assert inputs[1]["context"]["reading_context"]["work_id"] == "pg11"
    assert inputs[2]["context"] == inputs[1]["context"]


@pytest.mark.parametrize(
    ("revised", "second"),
    [
        pytest.param(revision(), second_review(finding(EGGS), decision="reject"), id="second-review-rejects"),
        pytest.param(
            revision(),
            second_review(finding(kind="structural", source_field="candidate.response", path="")),
            id="finding-names-no-sentence",
        ),
        pytest.param(
            revision(),
            second_review(finding(kind="structural", source_field="untrusted_tool_outcomes", path="")),
            id="finding-is-not-about-reply-text",
        ),
        *(
            pytest.param(revision(), second_review(finding(EGGS, code=code.value)), id=code.value)
            for code in RiskCode if code not in ALLOWED
        ),
        pytest.param(
            revision(f"{NECK} {MIDDLE} {EGGS} {CLOSE}", book(NECK, MIDDLE, EGGS)),
            second_review(finding(EGGS), finding(MIDDLE, code="harmful_content")),
            id="one-finding-of-two-is-not-allowed",
        ),
        pytest.param(revision(), second_review(finding(NECK), finding(EGGS)), id="no-mapped-claim-left"),
        pytest.param(
            revision(NECK, book(NECK)), second_review(finding("her long neck")), id="nothing-left",
        ),
        pytest.param(
            revision(
                f"{NECK} You said it stayed with you.", book(NECK),
                SessionLineUse(source_kind="session_line", quote="I keep thinking about being misread",
                               supported_claims=("You said it stayed with you.",)),
            ),
            second_review(finding(NECK)), id="only-the-reader's-own-line-left",
        ),
    ],
)
def test_excluded_conditions_decline_without_a_third_review(revised, second):
    release, inputs, _ = run(revised, second)

    assert release.release_source == "application_safe_decline"
    assert release.reply == decline_text(None, tuple(item.code for item in second.response_findings))
    assert release.provenance_verdicts == ("revise", second.response_decision)
    assert release.trimmed_sentence_count == 0
    assert len(inputs) == 2


@pytest.mark.parametrize("code", sorted(code.value for code in ALLOWED))
def test_each_evidence_code_can_be_trimmed(code):
    release, inputs, _ = run(revision(), second_review(finding(EGGS, code=code)), third_review())

    assert release.reply == f"{NECK} {CLOSE}"
    assert len(inputs) == 3


def earlier(quote: str | None, code: str = "unsupported_claim") -> ProvenanceReview:
    """A first review whose one finding the second review can leave unresolved."""
    location = {} if quote else {"kind": "structural", "source_field": "candidate.response", "path": ""}
    return ProvenanceReview(
        findings=(finding(quote, code=code, **location),), response_decision="revise",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
    )


WITH_MIDDLE = dict(draft=f"A first draft. {MIDDLE}")


def test_an_earlier_finding_left_unresolved_is_removed_too_and_named_to_the_third_review():
    first = earlier("never seen a girl like her")
    revised = revision(f"{NECK} {MIDDLE} {EGGS} {CLOSE}", book(NECK, MIDDLE, EGGS))

    release, inputs, _ = run(
        revised, second_review(finding(EGGS), resolved="unresolved"), third_review(count=2),
        first=first, **WITH_MIDDLE,
    )

    assert release.reply == f"{NECK} {CLOSE}"
    assert release.trimmed_sentence_count == 2
    assert inputs[2]["previous_response_review"]["findings"] == [
        finding(EGGS).model_dump(mode="json"), first.findings[0].model_dump(mode="json"),
    ]


@pytest.mark.parametrize(
    ("first", "revised"),
    [
        pytest.param(earlier("never seen a girl like her"), revision(), id="its-text-is-no-longer-in-the-reply"),
        pytest.param(earlier(None), revision(), id="it-names-no-text"),
        pytest.param(
            earlier("never seen a girl like her", code="spoiler"),
            revision(f"{NECK} {MIDDLE} {EGGS} {CLOSE}", book(NECK, MIDDLE, EGGS)),
            id="it-is-a-safety-finding",
        ),
    ],
)
def test_an_earlier_finding_left_unresolved_that_cannot_be_trimmed_declines(first, revised):
    release, inputs, _ = run(
        revised, second_review(finding(EGGS), resolved="unresolved"), first=first, **WITH_MIDDLE,
    )

    assert release.release_source == "application_safe_decline"
    assert release.trimmed_sentence_count == 0
    assert len(inputs) == 2


def test_a_pending_clarification_is_never_trimmed():
    release, inputs, _ = run(
        revision(), second_review(finding(EGGS)),
        revision_tools=(route_clarification("Which book are you reading?"),),
    )

    assert release.release_source == "application_safe_decline"
    assert len(inputs) == 2


def test_a_failed_third_review_declines_and_releases_nothing():
    release, inputs, _ = run(revision(), second_review(finding(EGGS)), RuntimeError("provider down"))

    assert release.reply == PIPELINE_FAILURE_DECLINE
    assert release.release_source == "application_safe_decline"
    assert (release.failure_stage, release.failure_type, release.failure_retryable) == (
        "provenance_review", "model", True,
    )
    assert release.provenance_verdicts == ("revise", "revise")
    assert release.released_evidence_ids == ()
    assert release.trimmed_sentence_count == 1
    assert len(inputs) == 3


def test_a_fault_in_the_trim_declines_as_before_with_a_warning_that_holds_no_text(monkeypatch, caplog):
    def broken(*_args):
        raise RuntimeError(EGGS)

    monkeypatch.setattr(reflection, "trim_named_sentences", broken)

    with caplog.at_level("WARNING", logger="linger.backend"):
        release, inputs, _ = run(revision(), second_review(finding(EGGS)))

    assert release.reply == EVIDENCE_DECLINE
    assert release.failure_stage is None
    assert len(inputs) == 2
    assert "Sentence trim failed closed error_type=RuntimeError" in caplog.text
    assert "eggs" not in caplog.text


def test_trimmed_candidate_that_cannot_pass_release_validation_is_not_reviewed():
    out_of_scope = canonical_record(evidence_id="pg11-v01b38ea4-ch09-ln0001-0002", chapter_number=9)
    add_turn_evidence((out_of_scope,))
    revised = revision(REVISION, BookEvidenceUse(
        source_kind="book_corpus", evidence_id=out_of_scope.evidence_id,
        source_location=out_of_scope.location, supported_claims=(NECK[:-1], EGGS[:-1]),
    ))

    release, inputs, _ = run(revised, second_review(finding(EGGS)))

    assert release.reply == EVIDENCE_DECLINE
    assert release.provenance_verdicts == ("revise", "revise")
    assert len(inputs) == 2


def test_first_review_revise_goes_to_muse_never_to_a_trim():
    muse = AsyncMock()
    muse.run.side_effect = [result(revision()), result(revision(f"{NECK} {CLOSE}", book(NECK)))]
    first = ProvenanceReview(
        findings=(finding(EGGS),), response_decision="revise",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
    )
    provenance = AsyncMock()
    provenance.run.side_effect = [result(first), result(third_review())]

    release = asyncio.run(reflection_reply(MESSAGE, [], muse=muse, provenance=provenance))

    assert muse.run.await_count == 2
    assert json.loads(muse.run.await_args_list[1].args[0])["mode"] == "revision"
    assert provenance.run.await_count == 2
    assert release.provenance_verdicts == ("revise", "pass")
    assert release.trimmed_sentence_count == 0


def test_failed_revision_is_not_trimmed():
    muse = AsyncMock()
    muse.run.side_effect = [result(revision()), RuntimeError("provider down")]
    first = ProvenanceReview(
        findings=(finding(EGGS),), response_decision="revise",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
    )
    provenance = AsyncMock()
    provenance.run.side_effect = [result(first)]

    release = asyncio.run(reflection_reply(MESSAGE, [], muse=muse, provenance=provenance))

    assert release.failure_stage == "muse_revision"
    assert provenance.run.await_count == 1
    assert release.trimmed_sentence_count == 0


def test_a_finding_on_a_clause_removes_its_whole_sentence():
    release, _, _ = run(revision(), second_review(finding("serpents raiding its eggs")), third_review())

    assert release.reply == f"{NECK} {CLOSE}"


def test_a_finding_on_a_mapping_removes_the_sentence_that_holds_the_claim():
    on_mapping = finding(kind="structural", source_field="candidate.evidence_uses", path="/0/supported_claims/1")
    audit = [
        {"group_index": 0, "supported": True, "support_summary": "The record shows it.", "source_contributions": [
            {"declaration_index": 0, "claim_index": 0, "contributes": True, "source_excerpt": "Alice asked"}]},
        {"group_index": 1, "supported": False, "support_summary": "The record does not show it.", "source_contributions": [
            {"declaration_index": 0, "claim_index": 1, "contributes": False, "source_excerpt": None}]},
    ]

    release, _, _ = run(revision(), second_review(on_mapping, claim_audit=audit), third_review())

    assert release.reply == f"{NECK} {CLOSE}"


def test_two_findings_on_two_sentences_remove_both_and_keep_the_paragraph_break():
    middle = "It has never seen a girl like her."
    reply = f"{NECK} {middle}\n\n{EGGS} {CLOSE}"
    revised = revision(reply, book(NECK, middle, EGGS))

    release, inputs, _ = run(
        revised, second_review(finding(middle), finding(EGGS)), third_review(count=2),
    )

    assert release.reply == f"{NECK}\n\n{CLOSE}"
    assert release.trimmed_sentence_count == 2
    assert inputs[2]["candidate"]["evidence_uses"] == [book(NECK).model_dump(mode="json")]


def test_a_claim_spanning_a_removed_sentence_is_removed_whole():
    spanning = f"{EGGS} So it calls her a serpent."
    reply = f"{NECK} {spanning} {CLOSE}"
    revised = revision(reply, book(NECK, spanning))

    release, inputs, _ = run(revised, second_review(finding("raiding its eggs")), third_review())

    assert release.reply == f"{NECK} {CLOSE}"
    assert release.trimmed_sentence_count == 2
    assert inputs[2]["candidate"]["evidence_uses"] == [book(NECK).model_dump(mode="json")]


def test_a_declaration_left_without_a_claim_is_dropped_and_the_rest_is_unchanged():
    limit = "The passage does not say why."
    reply = f"{NECK} {limit} {EGGS} {CLOSE}"
    kept = book(NECK, limit_claims=(limit,))
    revised = revision(reply, kept, book(EGGS, second=True))

    limits = [{"limit_index": 0, "withholds_only": True, "accurate": True}]

    release, inputs, _ = run(
        revised, second_review(finding(EGGS), limit_audit=limits), third_review(limit_audit=limits),
    )

    assert release.reply == f"{NECK} {limit} {CLOSE}"
    assert inputs[2]["candidate"]["evidence_uses"] == [kept.model_dump(mode="json")]
    assert release.released_evidence_ids == (EVIDENCE_ID,)
    assert release.released_citations == (("book_corpus", EVIDENCE_ID),)
    assert release.evidence_ids == (EVIDENCE_ID,)


def test_a_quotation_cut_by_the_sentence_splitter_is_removed_whole():
    reply = f'{NECK} The Pigeon cries, "Serpent! I say it again." {CLOSE}'

    release, _, _ = run(revision(reply, book(NECK)), second_review(finding("I say it again")), third_review())

    assert release.reply == f"{NECK} {CLOSE}"
    assert release.trimmed_sentence_count == 1


def test_a_claim_that_also_stands_in_a_kept_sentence_keeps_its_mapping():
    repeat = f"It fears for its eggs, and {NECK[0].lower()}{NECK[1:]}"
    revised = revision(f"{NECK} {repeat} {CLOSE}", book(NECK[4:]))

    release, inputs, _ = run(revised, second_review(finding("It fears for its eggs")), third_review())

    assert release.reply == f"{NECK} {CLOSE}"
    assert inputs[2]["candidate"]["evidence_uses"] == [book(NECK[4:]).model_dump(mode="json")]


def test_an_exact_quote_and_a_limit_in_removed_sentences_are_dropped_from_a_kept_declaration():
    limit = "The passage does not say why it asks."
    quoting = f'Rudely it asks, "{QUOTE}"'
    revised = revision(
        f"{NECK} {quoting} {limit} {CLOSE}", book(NECK, exact_quote=QUOTE, limit_claims=(limit,)),
    )
    limits = [{"limit_index": 0, "withholds_only": True, "accurate": True}]
    second = second_review(finding("Rudely it asks"), finding("does not say why"), limit_audit=limits)

    release, inputs, _ = run(revised, second, third_review(count=2))

    assert release.reply == f"{NECK} {CLOSE}"
    assert inputs[2]["candidate"]["evidence_uses"] == [book(NECK).model_dump(mode="json")]


def test_memory_nomination_is_carried_unchanged_and_the_releasing_review_decides_capture():
    start = MESSAGE.index("I keep thinking")
    nomination = MemoryCandidate(
        kind="memory_candidate", text=MESSAGE[start:], start_codepoint=start,
        end_codepoint=len(MESSAGE), reason_code="durable_reflection",
    )
    refused = RiskFinding(
        code="sensitive_content", applies_to="capture", explanation="Not safe to keep.",
        location={"kind": "structural", "source_field": "candidate.memory", "path": ""},
    )
    second = second_review(finding(EGGS), refused, capture_decision="reject_capture")

    release, inputs, _ = run(
        revision(memory=nomination), second, third_review(capture_decision="allow_capture"),
    )

    assert inputs[2]["candidate"]["memory"] == nomination.model_dump(mode="json")
    assert inputs[2]["previous_response_review"]["findings"] == [finding(EGGS).model_dump(mode="json")]
    assert release.capture_nomination == "candidate"
    assert release.capture_decision == "allow_capture"
    assert release.automatic_capture_candidate.text == nomination.text
    assert release.automatic_capture_candidate.review_allows_capture is True


def test_trim_is_recorded_without_text_and_the_extra_review_is_shown_as_a_review():
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False, console=False, inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )
    events = []
    token = begin_progress(events.append)
    try:
        run(revision(), second_review(finding(EGGS)), third_review())
    finally:
        reset_progress(token)

    spans = exporter.exported_spans_as_dict()
    released = next(span for span in spans if span["name"] == "reflection.release")
    assert released["attributes"]["release.trimmed_sentence_count"] == 1
    assert released["attributes"]["release.revision_count"] == 1
    assert "raiding its eggs" not in json.dumps(spans, default=str)
    reviews = [event for event in events if (event.agent, event.stage) == ("Provenance", "review")]
    assert [event.status for event in reviews] == ["running", "complete"] * 3
    assert {event.detail for event in reviews} == {
        "Provenance release review is in progress.", "Provenance release review completed.",
    }


K = NECK[:-1]


def pure(reply: str, *quotes: str, uses=None, earlier_findings=(), resolved: str = "resolved"):
    """The trim alone, on a reply whose neck sentence is mapped so a refusal is the guard's."""
    candidate = MuseCandidate(reply=reply, evidence_uses=uses or (book(NECK),), memory=NO_MEMORY)
    answer = ProvenanceReview(
        findings=tuple(finding(quote) for quote in quotes), response_decision="revise",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
        finding_resolutions=tuple(
            {**RESOLVED, "finding_index": index, "status": resolved} for index in range(len(earlier_findings))
        ),
    )
    return trim_named_sentences(candidate, answer, earlier_findings)


@pytest.mark.parametrize(
    ("reply", "quote", "reason"),
    [
        (f"{NECK}\n\n1. It fears for its eggs.\n2. It has seen serpents before.\n\n{CLOSE}", "fears for its eggs", "structured_reply"),
        (f"{NECK} It gives two reasons.\n- It fears for its eggs.\n- It has seen serpents.\n{CLOSE}", "fears for its eggs", "structured_reply"),
        (f"{NECK} See [the chapter](http://x.org/a) for the eggs claim it makes. {CLOSE}", "the eggs claim", "structured_reply"),
        (f"{NECK} [1] It fears for its eggs. [2] {CLOSE}", "fears for its eggs", "structured_reply"),
        (f"{NECK} Mr. Darcy insults her at the ball. {CLOSE}", "Darcy insults her", "unsafe_boundary"),
        (f"{NECK} Others, e.g. the Caterpillar, mock her size. {CLOSE}", "mock her size", "unsafe_boundary"),
        (f"{NECK} And then... it screams at her loudly. {CLOSE}", "it screams at her", "unsafe_boundary"),
        (f"{NECK} There J. R. Smith says the eggs were lost. {CLOSE}", "eggs were lost", "unsafe_boundary"),
        (f"{NECK} It gives these reasons for its fear:\n\nIt fears for its eggs every day. {CLOSE}", "fears for its eggs", "unsafe_boundary"),
        (f"{NECK} It fears for its eggs, as follows:\n\nSerpents come in the night for them. {CLOSE}", "fears for its eggs", "unsafe_boundary"),
        (f'{NECK} It cries "Serpent!" loudly at her face. {CLOSE}', "loudly at her", "unsafe_boundary"),
        (f'{NECK} It cries "Serpent!" loudly at her face. {CLOSE}', "It cries", "unsafe_boundary"),
        (f"{NECK} (It fears for its eggs. Or so it tells her.) {CLOSE}", "fears for its eggs", "split_delimiters"),
        (f"**{NECK} It fears for its eggs.** {CLOSE}", "fears for its eggs", "split_delimiters"),
        (f"{NECK} Le Pigeon dit : « Serpent ! Je le dis encore. Tu en es un. » {CLOSE}", "Je le dis encore", "split_delimiters"),
        (f"{NECK} It fears for its eggs (so it says. {CLOSE}", "fears for its eggs", "split_delimiters"),
        (f"{NECK} It fears for its eggs. What now?", "fears for its eggs", "fragment_remainder"),
        (f"Does it lie? It fears for its eggs. {NECK} {CLOSE}", "fears for its eggs", "fragment_remainder"),
        (f"{NECK} Alice had eaten the mushroom. That is why her neck grew. {CLOSE}", "eaten the mushroom", "dependent_remainder"),
        (f"It fears for its eggs. The Pigeon also points to her long neck. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"{NECK} It fears for its eggs. But the neck matters more here. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"{NECK} It fears for its eggs. As a result it screams at her. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"{NECK} It fears for its eggs. For example, it watches the sky. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"{NECK} There are two reasons. The first is its eggs. The second is her height. {CLOSE}", "The first is", "dependent_remainder"),
        (f"{NECK} The Caterpillar is rude to her. He smokes a long hookah. {CLOSE}", "is rude to her", "dependent_remainder"),
        (f"{NECK} The Caterpillar is rude to her. Their talk goes badly for her. {CLOSE}", "is rude to her", "dependent_remainder"),
        (f"{NECK} The Caterpillar is rude to her. It hisses at her for a while. {CLOSE}", "is rude to her", "dependent_remainder"),
        (f"{NECK} It fears for its eggs. There it sits all day long. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"{NECK} It fears for its eggs. Nevertheless the neck matters more here. {CLOSE}", "fears for its eggs", "dependent_remainder"),
        (f"*{NECK} It fears for its eggs.* {CLOSE}", "fears for its eggs", "split_delimiters"),
    ],
)
def test_a_trim_that_could_change_what_remains_is_refused(reply, quote, reason):
    uses = (book("The Pigeon also points to her long neck."),) if "Pigeon also" in reply else None

    with pytest.raises(TrimRefused) as refused:
        pure(reply, quote, uses=uses)

    assert refused.value.reason == reason


@pytest.mark.parametrize(
    ("reply", "quote", "trimmed"),
    [
        (f"{NECK} It fears for its eggs (or so it says). {CLOSE}", "fears for its eggs", f"{NECK} {CLOSE}"),
        (f"{NECK} Alice’s neck worries the Pigeon’s whole nest. {CLOSE}", "whole nest", f"{NECK} {CLOSE}"),
        (f"{NECK} Mr. Darcy insults her at the ball. It fears for its eggs. {CLOSE}", "fears for its eggs",
         f"{NECK} Mr. Darcy insults her at the ball. {CLOSE}"),
        (f"{NECK} It fears for its eggs. Hissing follows for a while. It then goes quiet again. {CLOSE}",
         "fears for its eggs", f"{NECK} Hissing follows for a while. It then goes quiet again. {CLOSE}"),
        (f"{NECK} It fears for its eggs. Its nest holds three small eggs. {CLOSE}", "fears for its eggs",
         f"{NECK} Its nest holds three small eggs. {CLOSE}"),
        (f"{NECK} It fears for its *eggs*. Hissing follows for a while. {CLOSE}", "fears for its",
         f"{NECK} Hissing follows for a while. {CLOSE}"),
        (f"It fears for its eggs. {NECK} {CLOSE}", "fears for its eggs", f"{NECK} {CLOSE}"),
    ],
)
def test_guards_do_not_refuse_text_they_do_not_concern(reply, quote, trimmed):
    assert pure(reply, quote).candidate.reply == trimmed


def test_a_candidate_whose_mappings_do_not_hold_is_refused():
    with pytest.raises(TrimRefused) as refused:
        pure(REVISION, "raiding its eggs", uses=(book(NECK, "A claim the reply never makes."),))

    assert refused.value.reason == "invalid_candidate"


def test_more_prompting_findings_than_a_review_may_carry_are_refused():
    sentences = [f"It hisses at her loudly for the {number}th time today." for number in range(20)]
    carried = (finding("The Pigeon points"),)

    with pytest.raises(TrimRefused) as refused:
        pure(" ".join([NECK, *sentences, CLOSE]), *sentences, earlier_findings=carried, resolved="unresolved")

    assert refused.value.reason == "finding_code"


def test_only_a_revise_is_trimmed():
    rejected = ProvenanceReview(
        findings=(finding("raiding its eggs"),), response_decision="reject",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
    )

    with pytest.raises(TrimRefused) as refused:
        trim_named_sentences(revision(), rejected)

    assert refused.value.reason == "review_not_revise"


def test_an_earlier_finding_on_a_draft_mapping_is_not_placed_on_the_revision():
    on_draft_mapping = finding(kind="structural", source_field="candidate.evidence_uses", path="/0")

    with pytest.raises(TrimRefused) as refused:
        pure(REVISION, "raiding its eggs", earlier_findings=(on_draft_mapping,), resolved="unresolved")

    assert refused.value.reason == "unplaced_finding"


def test_claims_and_limits_that_chain_across_sentences_are_removed_together():
    one, two, three = "It fears for its eggs.", "Serpents come at night.", "The passage does not say how often."
    uses = (book(NECK, f"{one} {two}", limit_claims=(f"{two} {three}",)),)

    trim = pure(f"{NECK} {one} {two} {three} {CLOSE}", "fears for its eggs", uses=uses)

    assert trim.candidate.reply == f"{NECK} {CLOSE}"
    assert trim.candidate.evidence_uses == (book(NECK),)
    assert len(trim.removed) == 3


def test_an_unresolved_resolution_that_names_no_earlier_finding_is_refused():
    answer = ProvenanceReview(
        findings=(finding("raiding its eggs"),), response_decision="revise",
        emotional_boundary_decision="not_required", capture_decision="no_candidate",
        finding_resolutions=({**RESOLVED, "finding_index": 3, "status": "unresolved"},),
    )
    with pytest.raises(TrimRefused) as refused:
        trim_named_sentences(revision(), answer, ())

    assert refused.value.reason == "unplaced_finding"
