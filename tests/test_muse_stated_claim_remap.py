"""A claim Muse maps only to the wrong one of its declared records gains the record whose
stated answer supplies its words, before the review sees it; nothing else about a candidate moves."""

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry, UsageLimits, capture_run_messages
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.contracts import ContextResolution, MuseRevisionInput, MuseRevisionReview, MuseTurn, TurnPolicy
from src.linger.agents.muse.agent import MuseSkillBoundary, build_muse_agent, validate_muse_output
from src.linger.agents.muse.claim_remap import stated_claim_additions
from src.linger.agents.muse.claim_repair import _sentence_mappings, sentence_spans, label_sentences
from src.linger.agents.muse.models import DraftSentence, MuseCandidate
from src.linger.agents.muse.skills import reflection_run_options
from src.linger.contracts.librarian import EvidenceRecord, StatedAnswer
from src.linger.orchestration.turn_context import (
    add_turn_stated_answers, reset_turn_evidence, set_turn_evidence, turn_stated_answers,
)
from tests.test_muse_claim_retention import review

NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def record(evidence_id: str, text: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id, work_id="w", book_version_id="w-v1", chapter_id="w-v1-ch05",
        chapter_number=5, location=f"{evidence_id} loc", source_sha256="a" * 64, source_lines=(1, 2), text=text,
    )


NECK = record("ch05-neck", "“Serpent!” screamed the Pigeon. Alice’s neck would bend about easily in any direction.")
SKY = record("ch05-sky", (
    "“As if it wasn’t trouble enough hatching the eggs,” said the Pigeon. “They must needs come\n"
    "wriggling down from the sky! Ugh, Serpent!”"
))
# A third passage, stating another phrase.
DUSK = record("ch05-dusk", "At dusk a grey heron dropped from the clouds.")
DUSK_ANSWER = StatedAnswer(answer="A bird came down at dusk.", evidence_id=DUSK.evidence_id,
                           source_quote="a grey heron dropped")
DUSK_CLAIM = "Something arrives at dusk."
# A neck passage that itself has the sky wording.
NECK_AND_SKY = record("ch05-neck", NECK.text + " She came wriggling down out of the sky.")
SKY_ANSWER = StatedAnswer(
    answer="The Pigeon thinks Alice is a serpent because she came wriggling down from the sky.",
    evidence_id=SKY.evidence_id, source_quote="come wriggling down from the sky! Ugh, Serpent!",
)
# The recorded draft's shape: the sky clause sits in a claim mapped only to the neck passage.
# A second answer of the same record that supplies the same words.
SKY_AGAIN = StatedAnswer(
    answer="Serpents come down from above.", evidence_id=SKY.evidence_id,
    source_quote="needs come wriggling down from the sky!",
)
NECK_CLAIM = (
    "The Pigeon takes Alice for a serpent because her long neck bends about, and she appears "
    "to be wriggling down from the sky."
)
EGGS_CLAIM = "The Pigeon is busy hatching its eggs."
CERTAIN = "The Pigeon is quite certain."


def book(source: EvidenceRecord, *claims: str, limits=()) -> dict:
    return {"source_kind": "book_corpus", "evidence_id": source.evidence_id, "source_location": source.location,
            "supported_claims": list(claims), "limit_claims": list(limits), "exact_quote": None}


def candidate(*uses: dict, reply: str = f"{NECK_CLAIM} {EGGS_CLAIM}") -> MuseCandidate:
    return MuseCandidate.model_validate({"reply": reply, "evidence_uses": list(uses), "memory": NO_MEMORY})


@contextmanager
def turn(records=(NECK, SKY), answers=(SKY_ANSWER,)):
    token = set_turn_evidence(tuple(records))
    add_turn_stated_answers(tuple(answers))
    try:
        yield
    finally:
        reset_turn_evidence(token)


def released(output: MuseCandidate, ctx=None) -> MuseCandidate:
    """What Muse's run returns for this output: the boundary's validation of it."""
    return asyncio.run(MuseSkillBoundary().after_output_validate(
        ctx or SimpleNamespace(), output_context=None, output=output))


def claims(output: MuseCandidate) -> dict[str, tuple[str, ...]]:
    return {use.evidence_id: use.supported_claims for use in output.evidence_uses}


WRONG_RECORD = candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM))


def test_a_claim_mapped_only_to_the_wrong_declared_record_gains_the_record_that_states_it():
    with turn():
        output = released(WRONG_RECORD)
    assert claims(output) == {SKY.evidence_id: (EGGS_CLAIM, NECK_CLAIM), NECK.evidence_id: (NECK_CLAIM,)}
    # Nothing else moves, and the input is left as Muse wrote it.
    assert output.model_dump(exclude={"evidence_uses"}) == WRONG_RECORD.model_dump(exclude={"evidence_uses"})
    assert [use.model_dump(exclude={"supported_claims"}) for use in output.evidence_uses] == [
        use.model_dump(exclude={"supported_claims"}) for use in WRONG_RECORD.evidence_uses]
    assert claims(WRONG_RECORD)[SKY.evidence_id] == (EGGS_CLAIM,)


def test_several_answers_of_one_record_add_the_claim_once_to_its_first_declaration():
    cry = "The Pigeon cries “Ugh, Serpent!”"
    output = candidate(
        book(NECK, NECK_CLAIM), book(SKY, EGGS_CLAIM), book(SKY, cry) | {"exact_quote": "Ugh, Serpent!"},
        reply=f"{NECK_CLAIM} {EGGS_CLAIM} {cry}")
    with turn(answers=(SKY_ANSWER, SKY_AGAIN)):
        result = released(output)
    assert [use.supported_claims for use in result.evidence_uses] == [
        (NECK_CLAIM,), (EGGS_CLAIM, NECK_CLAIM), (cry,)]


def test_a_claim_from_another_book_gains_the_record_whose_quote_states_it():
    quay = record("ch02-quay", "Marta mended the nets on the quay while the harbour bell rang.")
    storm = record("ch02-storm", "Oren laughed at the warning. By dusk a black _squall_ tore the mainsail away.")
    nets = "Marta mends nets on the quay before the Black Squall hits."
    laugh = "Oren laughs at the warning."
    answer = StatedAnswer(answer="A storm damages the boat.", evidence_id=storm.evidence_id,
                          source_quote="a black _squall_ tore the mainsail")
    with turn((quay, storm), (answer,)):
        result = released(candidate(book(quay, nets), book(storm, laugh), reply=f"{nets} {laugh}"))
    assert claims(result) == {quay.evidence_id: (nets,), storm.evidence_id: (laugh, nets)}


def test_only_an_overlapping_claim_of_the_stating_record_that_holds_the_phrase_blocks_the_addition():
    def output(*parts: str, limits=(), reply=f"{NECK_CLAIM} {EGGS_CLAIM}") -> MuseCandidate:
        return candidate(book(SKY, EGGS_CLAIM, *parts, limits=limits), book(NECK, NECK_CLAIM), reply=reply)

    phrase = "she appears to be wriggling down from the sky"
    elsewhere = "Serpents come wriggling down from the sky."
    with turn():
        covered = output(phrase)
        assert released(covered) is covered
        # Half the phrase, the phrase in another sentence, or the phrase as a limit does not cover it.
        assert claims(released(output("and she appears to be wriggling")))[SKY.evidence_id][-1] == NECK_CLAIM
        assert claims(released(output(elsewhere, reply=f"{NECK_CLAIM} {EGGS_CLAIM} {elsewhere}")))[
            SKY.evidence_id] == (EGGS_CLAIM, elsewhere, NECK_CLAIM)
        assert claims(released(output(limits=[phrase])))[SKY.evidence_id] == (EGGS_CLAIM, NECK_CLAIM)


def test_a_claim_gains_one_record_and_the_result_is_a_fixed_point():
    both = NECK_CLAIM[:-1] + " like a grey heron."  # A phrase of each of the other two passages.

    def output(sky=(), dusk=()) -> MuseCandidate:
        return candidate(book(NECK, both), book(SKY, EGGS_CLAIM, *sky), book(DUSK, DUSK_CLAIM, *dusk),
                         reply=f"{both} {EGGS_CLAIM} {DUSK_CLAIM}")

    for answers, gained, written in (
        ((SKY_ANSWER, DUSK_ANSWER), SKY, output(sky=[both])), ((DUSK_ANSWER, SKY_ANSWER), DUSK, output(dusk=[both])),
    ):
        with turn((NECK, SKY, DUSK), answers):
            once = released(output())
            assert [use.evidence_id for use in once.evidence_uses if both in use.supported_claims] == [
                NECK.evidence_id, gained.evidence_id]
            assert released(once) is once
            assert released(written) is written  # Muse mapped it to that passage itself.


def test_a_claim_under_a_record_the_turn_does_not_hold_is_left_alone():
    assert stated_claim_additions(WRONG_RECORD, (SKY_ANSWER,), {SKY.evidence_id: SKY}) == []
    assert stated_claim_additions(WRONG_RECORD, (SKY_ANSWER,), {NECK.evidence_id: NECK}) == []
    assert stated_claim_additions(WRONG_RECORD, (SKY_ANSWER,), {NECK.evidence_id: NECK, SKY.evidence_id: SKY}) == [
        (0, NECK_CLAIM)]


def test_an_answer_of_a_record_the_candidate_does_not_declare_is_passed_over():
    apart = record("ch05-apart", "Snakes came wriggling down from the sky.")
    undeclared = StatedAnswer(answer="Snakes fall.", evidence_id=apart.evidence_id,
                              source_quote="came wriggling down from the sky")
    with turn((NECK, SKY, apart), (undeclared, SKY_ANSWER)):
        assert claims(released(WRONG_RECORD))[SKY.evidence_id] == (EGGS_CLAIM, NECK_CLAIM)


# The claim's own record has none of these words, so only the phrase rule keeps the other record off it.
@pytest.mark.parametrize(("claim", "text", "quote"), [
    ("The Pigeon said Alice was rude.", "“Well!” said Alice to the Pigeon.", "said Alice"),
    ("The Pigeon and Alice quarrel.", "It threw itself, the Pigeon at Alice, with a shriek.", "the Pigeon at Alice"),
    ("They don’t know the way.", "“I don’t know,” it sighed.", "I don’t know"),
    ("She looks at the sky. Alice then sits.", "It fell from the sky. Alice stared.", "from the sky. Alice stared"),
    ("She looks at the sky\n\nAlice then sits.", "It fell from the sky\n\nAlice stared.", "the sky\n\nAlice stared"),
    ("The pair are happily married.", "They were unhappily married.", "happily married"),
    ("Theirs was a happy marriage.", "The happy marriages lasted.", "happy marriage"),
    ("She was wriggling down from the sky.", "They came wriggling, twisting down from the sky.",
     "wriggling, twisting down from the sky"),
    ("The grey heron sleeps.", "It was a heron grey with age.", "a heron grey with age"),
    ("She climbs down from the tree.", "They came wriggling down from the sky.", "wriggling down from the sky"),
    ("She walks up to the house.", "It flew up to the sky.", "flew up to the sky"),
], ids=[
    "speech-verb", "different-words-between", "contraction-stem", "across-a-sentence", "across-a-paragraph",
    "quote-starts-inside-a-word", "quote-ends-inside-a-word", "not-neighbours-in-the-quote", "reversed-in-the-quote",
    "only-function-words-shared", "only-short-words-shared",
])
def test_words_that_do_not_form_one_shared_phrase_attach_nothing(claim, text, quote):
    own = record("ch03-own", "She nibbled a little of the right-hand bit.")
    stating = record("ch03-stating", text)
    answer = StatedAnswer(answer="An answer.", evidence_id=stating.evidence_id, source_quote=quote)
    output = candidate(book(own, claim), book(stating, EGGS_CLAIM), reply=f"{claim} {EGGS_CLAIM}")
    with turn((own, stating), (answer,)):
        assert released(output) is output


def test_only_a_book_declaration_of_the_stating_record_can_receive_the_claim():
    page = {"source_kind": "web", "evidence_id": SKY.evidence_id, "supported_claims": [EGGS_CLAIM]}
    output = candidate(page, book(NECK, NECK_CLAIM))
    assert stated_claim_additions(output, (SKY_ANSWER,), {NECK.evidence_id: NECK, SKY.evidence_id: SKY}) == []


def test_the_remap_is_idempotent():
    with turn():
        once = released(WRONG_RECORD)
        assert released(once) is once


# Both words of the quote, but not side by side.
APART = "The Pigeon takes Alice for a serpent because her long neck keeps wriggling under a grey sky."
# "serpent" is in the neck passage too.
HALF_NEW = "The Pigeon greets her long neck with an ugh, serpent."
# "thinks" and "came" are the Librarian's paraphrase, not words of the record.
PARAPHRASED = "The Pigeon thinks Alice came to steal."


@pytest.mark.parametrize(("output", "records", "answers"), [
    (candidate(book(SKY, EGGS_CLAIM, NECK_CLAIM), book(NECK, NECK_CLAIM)), (NECK, SKY), (SKY_ANSWER,)),
    (candidate(book(NECK, NECK_CLAIM, EGGS_CLAIM)), (NECK, SKY), (SKY_ANSWER,)),
    (candidate(book(SKY, EGGS_CLAIM), book(NECK, APART), reply=f"{APART} {EGGS_CLAIM}"),
     (NECK, SKY), (SKY_ANSWER,)),
    (candidate(book(SKY, EGGS_CLAIM), book(NECK, HALF_NEW), reply=f"{HALF_NEW} {EGGS_CLAIM}"),
     (NECK, SKY), (SKY_ANSWER,)),
    (WRONG_RECORD, (NECK, SKY), (
        SKY_ANSWER.model_copy(update={"source_quote": "They must needs come wriggling"}),
        SKY_ANSWER.model_copy(update={"source_quote": "down from the sky! Ugh, Serpent!"}))),
    (WRONG_RECORD, (NECK, SKY), (SKY_ANSWER.model_copy(update={"source_quote": "kept wriggling down from the sky"}),)),
    (candidate(book(SKY, EGGS_CLAIM), book(NECK, PARAPHRASED), reply=f"{PARAPHRASED} {EGGS_CLAIM}"),
     (NECK, SKY), (SKY_ANSWER,)),
    (WRONG_RECORD, (NECK_AND_SKY, SKY), (SKY_ANSWER,)),
    (WRONG_RECORD, (NECK, SKY), ()),
    (WRONG_RECORD, (NECK, SKY), (SKY_ANSWER.model_copy(update={"evidence_id": NECK.evidence_id}),)),
    (candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM),
               {"source_kind": "session_line", "quote": "she came wriggling down from the sky",
                "supported_claims": [NECK_CLAIM]}), (NECK, SKY), (SKY_ANSWER,)),
    (candidate(book(SKY, EGGS_CLAIM, limits=[NECK_CLAIM]), book(NECK, NECK_CLAIM)), (NECK, SKY), (SKY_ANSWER,)),
], ids=[
    "already-mapped-to-the-stating-record", "stating-record-not-declared", "shared-words-not-consecutive", "one-phrase-word-in-the-declared-record",
    "phrase-split-across-two-answers",
    "quote-not-in-its-record",
    "words-only-in-the-answer-paraphrase",
    "words-in-the-declared-record", "no-stated-answers", "answer-names-the-declared-record",
    "claim-also-mapped-to-a-reader-line", "claim-is-a-limit-of-the-stating-record",
])
def test_a_candidate_the_rule_does_not_cover_is_returned_as_written(output, records, answers):
    with turn(records, answers):
        assert released(output) is output


def test_an_invalid_candidate_is_still_retried_as_muse_wrote_it():
    output = candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM, "Not in the reply."))
    with turn(), pytest.raises(ModelRetry) as retry:
        released(output)
    errors = json.loads(retry.value.message)["errors"]
    assert [error["path"] for error in errors] == ["evidence_uses[1].supported_claims[1]"]


# --- revision ----------------------------------------------------------------------


def sentences_for(draft: MuseCandidate, flagged=()) -> tuple[DraftSentence, ...]:
    """Production sentence mappings and labelling for a draft whose `flagged` sentences a finding names."""
    return label_sentences(draft, tuple(
        DraftSentence(text=draft.reply[a:b], flagged=i in flagged, needs_source=False,
                      finding_indexes=(0,) if i in flagged else (), source_mappings=_sentence_mappings(draft, a, b))
        for i, (a, b) in enumerate(sentence_spans(draft.reply))))


def revision_prompt(draft: MuseCandidate, flagged_text: str, *, sentences: bool = True) -> str:
    flagged = [i for i, (a, b) in enumerate(sentence_spans(draft.reply)) if draft.reply[a:b] == flagged_text]
    return MuseRevisionInput(
        mode="revision",
        muse_turn=MuseTurn(
            turn_id="revision", user_message="Why a serpent?", reading_context=None,
            policy=TurnPolicy(allow_retrieval=False, allow_connection=False),
        ),
        context_resolution=ContextResolution(status="unknown", explanation="Test context."),
        review=MuseRevisionReview(
            findings=review(location={
                "kind": "text_span", "source_field": "candidate.response", "path": "", "quote": flagged_text,
            }).response_findings,
            previously_accepted_claims=(), draft_sentences=sentences_for(draft, flagged) if sentences else (),
            source_quote_interiors=(), released_reader_lines=(),
        ),
    ).model_dump_json()


def run_muse(prompt: str, output: dict, *, revision: bool, history=None):
    """One Muse run whose model answers with `output`: the result and the retries it took."""
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    async def run():
        with capture_run_messages() as messages:
            result = await build_muse_agent(FunctionModel(respond)).run(
                prompt, message_history=history, usage_limits=UsageLimits(request_limit=2),
                **reflection_run_options(revision=revision, tools=()))
        return result, [part.content for message in messages[len(history or ()):] for part in message.parts
                        if isinstance(part, RetryPromptPart)]

    return asyncio.run(run())


def test_a_revision_can_keep_a_remapped_draft_sentence_by_its_label():
    draft = candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM, CERTAIN),
                      reply=f"{NECK_CLAIM} {EGGS_CLAIM} {CERTAIN}")
    with turn(answers=(SKY_ANSWER, SKY_AGAIN)):
        drafted, _ = run_muse("Why a serpent?", draft.model_dump(mode="json"), revision=False)
        assert claims(drafted.output)[SKY.evidence_id] == (EGGS_CLAIM, NECK_CLAIM)
        sentences = sentences_for(drafted.output, flagged=(2,))
        assert [sentence.label for sentence in sentences] == ["{{SENTENCE_1}}", "{{SENTENCE_2}}", None]
        revised, retries = run_muse(
            revision_prompt(drafted.output, CERTAIN),
            {"reply": "{{SENTENCE_1}} {{SENTENCE_2}}", "evidence_uses": [], "memory": NO_MEMORY},
            revision=True, history=drafted.new_messages(),
        )
    assert retries == []
    assert revised.output.reply == f"{NECK_CLAIM} {EGGS_CLAIM}"
    assert claims(revised.output) == {
        SKY.evidence_id: (EGGS_CLAIM, NECK_CLAIM), NECK.evidence_id: (NECK_CLAIM,)}


def test_a_revision_that_is_valid_as_written_is_not_remapped_into_a_retention_error():
    # The draft was reviewed with the neck claim under the neck passage alone, and no finding disputes it.
    draft = candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM))
    rewritten = "The Pigeon has eggs to hatch."
    revision = candidate(book(SKY, rewritten), book(NECK, NECK_CLAIM), reply=f"{NECK_CLAIM} {rewritten}")
    remapped = candidate(book(SKY, rewritten, NECK_CLAIM), book(NECK, NECK_CLAIM), reply=revision.reply)
    ctx = SimpleNamespace(prompt=revision_prompt(draft, EGGS_CLAIM))
    with turn():
        with pytest.raises(ModelRetry, match="must keep the draft's sources"):
            validate_muse_output(ctx, remapped)
        assert released(revision, ctx) is revision


def test_a_label_still_rebuilds_a_draft_whose_addition_was_refused():
    # The sky passage declares the whole claim as a limit, so the claim cannot also be its supported claim.
    start = "The Pigeon takes Alice for a serpent"
    draft = candidate(book(SKY, start, limits=[NECK_CLAIM]), book(NECK, NECK_CLAIM, CERTAIN),
                      reply=f"{NECK_CLAIM} {CERTAIN}")
    with turn():
        drafted, _ = run_muse("Why a serpent?", draft.model_dump(mode="json"), revision=False)
        assert drafted.output == draft
        revised, retries = run_muse(
            revision_prompt(drafted.output, CERTAIN),
            {"reply": "{{SENTENCE_1}}", "evidence_uses": [], "memory": NO_MEMORY},
            revision=True, history=drafted.new_messages(),
        )
    assert retries == []
    assert claims(revised.output) == {SKY.evidence_id: (start,), NECK.evidence_id: (NECK_CLAIM,)}


def test_a_label_still_rebuilds_a_draft_reviewed_before_its_answer_was_listed():
    draft = candidate(book(SKY, EGGS_CLAIM), book(NECK, NECK_CLAIM, CERTAIN),
                      reply=f"{NECK_CLAIM} {EGGS_CLAIM} {CERTAIN}")
    with turn(answers=()):
        drafted, _ = run_muse("Why a serpent?", draft.model_dump(mode="json"), revision=False)
        assert drafted.output == draft
        add_turn_stated_answers((SKY_ANSWER,))  # A later search lists it.
        revised, retries = run_muse(
            revision_prompt(drafted.output, CERTAIN),
            {"reply": "{{SENTENCE_1}} {{SENTENCE_2}}", "evidence_uses": [], "memory": NO_MEMORY},
            revision=True, history=drafted.new_messages(),
        )
    assert retries == []
    assert claims(revised.output) == {NECK.evidence_id: (NECK_CLAIM,), SKY.evidence_id: (EGGS_CLAIM,)}


REWORDED = (
    "The Pigeon takes Alice for a serpent because her long neck bends, and she seems to come "
    "wriggling down from the sky."
)
REWORDED_REVISION = candidate(book(SKY, EGGS_CLAIM), book(NECK, REWORDED), reply=f"{REWORDED} {EGGS_CLAIM}")


def test_a_revision_repeating_a_mistake_the_draft_was_flagged_for_is_remapped():
    # The flagged draft sentence was reviewed under the neck passage alone.
    with turn():
        output = released(REWORDED_REVISION, SimpleNamespace(prompt=revision_prompt(WRONG_RECORD, NECK_CLAIM)))
    assert claims(output) == {SKY.evidence_id: (EGGS_CLAIM, REWORDED), NECK.evidence_id: (REWORDED,)}


def test_a_revision_does_not_regain_a_record_the_review_saw_on_a_flagged_sentence():
    reviewed = candidate(book(SKY, EGGS_CLAIM, NECK_CLAIM), book(NECK, NECK_CLAIM))
    with turn():
        ctx = SimpleNamespace(prompt=revision_prompt(reviewed, NECK_CLAIM))
        assert released(REWORDED_REVISION, ctx) is REWORDED_REVISION


def test_a_revision_whose_findings_could_not_be_placed_is_not_remapped():
    with turn():
        ctx = SimpleNamespace(prompt=revision_prompt(WRONG_RECORD, NECK_CLAIM, sentences=False))
        assert released(REWORDED_REVISION, ctx) is REWORDED_REVISION


def test_a_replayed_captured_stage_registers_its_recorded_stated_answers():
    from evals.synthetic_journals.muse_stage_replay import CapturedMuseTask, recorded_stated_answers

    search = {"evidence": [], "stated_answers": [SKY_ANSWER.model_dump(mode="json")]}
    history = [{"parts": [
        {"part_kind": "tool-return", "tool_name": "librarian_search", "content": json.dumps(search)},
        {"part_kind": "tool-return", "tool_name": "librarian_search", "content": search},
        {"part_kind": "tool-return", "tool_name": "serendipity_explore", "content": search},
    ]}]
    assert recorded_stated_answers(history) == (SKY_ANSWER,)

    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, WRONG_RECORD.model_dump(mode="json"))])

    prompt = json.loads(revision_prompt(WRONG_RECORD, NECK_CLAIM)) | {"mode": "draft"}
    del prompt["review"]
    task = CapturedMuseTask(
        prompt=json.dumps(prompt), history_json="[]", book_records=(NECK, SKY), connection_records=(),
        stated_answers=(SKY_ANSWER,), stage="draft", agent=build_muse_agent(FunctionModel(respond)),
    )
    assert claims(asyncio.run(task.invoke()))[SKY.evidence_id] == (EGGS_CLAIM, NECK_CLAIM)


# --- the turn's stated answers -----------------------------------------------------


def test_stated_answers_live_and_end_with_the_turn_evidence_ledger():
    assert turn_stated_answers() == ()
    add_turn_stated_answers((SKY_ANSWER,))  # No turn is bound: nothing is kept.
    assert turn_stated_answers() == ()
    with turn(answers=(SKY_ANSWER, SKY_ANSWER)):
        add_turn_stated_answers((SKY_ANSWER,))
        assert turn_stated_answers() == (SKY_ANSWER,)
    assert turn_stated_answers() == ()


def test_a_judged_search_registers_its_stated_answers_for_the_turn():
    from tests import test_librarian_stated_answers as librarian

    seen = []

    def run(search):
        response = asyncio.run(search)
        seen.extend(turn_stated_answers())
        return response

    _, response, _ = librarian.search(librarian.LibrarianScript(), run=run)
    assert response.stated_answers and tuple(seen) == response.stated_answers


# --- recorded candidates -----------------------------------------------------------

# Every Muse candidate of 15 recorded pigeon-serpent turns, with the records and stated answers
# its search returned. Only run two6 mapped a clause to the wrong record. Its first revision is
# not remapped: only the Librarian's paraphrase of the answer, not the record's quote, has its words.
# The "authored-" runs are written for this test, not recorded: another question of the same
# chapter whose claim shares only character names with a quote, and another book.
SAVED = json.loads((Path(__file__).parent / "fixtures" / "muse_stated_claim_remap.json").read_text(encoding="utf-8"))
REMAPPED = {
    ("two6", 0): "In Chapter 5, the Pigeon mistakes Alice for a serpent because her unusually long, flexible "
                 "neck looks serpent-like, and she appears to be wriggling down from the sky.",
    ("two6", 2): "The Pigeon identifies Alice as a serpent because her neck bends like one, and Alice appears "
                 "to come wriggling down from the sky.",
    ("authored-storm", 0): "Marta mends her nets on the quay, and at dusk a black squall tears the mainsail away.",
}


@pytest.mark.parametrize(("run", "index"), [
    (run["run"], index) for run in SAVED["runs"] for index in range(len(run["candidates"]))
])
def test_recorded_candidates_change_only_where_a_clause_was_mapped_to_the_wrong_record(run, index):
    saved = next(item for item in SAVED["runs"] if item["run"] == run)
    output = MuseCandidate.model_validate(saved["candidates"][index]["candidate"])
    records = [EvidenceRecord.model_validate(item) for item in SAVED["records"]
               if item["evidence_id"] in saved["evidence_ids"]]
    with turn(records, [StatedAnswer.model_validate(item) for item in saved["stated_answers"]]):
        result = released(output)
    claim = REMAPPED.get((run, index))
    if claim is None:
        assert result is output
        return
    before, after = claims(output), claims(result)
    gained = [evidence_id for evidence_id in after if after[evidence_id] != before[evidence_id]]
    assert len(gained) == 1 and after[gained[0]] == (*before[gained[0]], claim)
