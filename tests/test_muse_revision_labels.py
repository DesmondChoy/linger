"""Sentence labels in Muse revisions: a kept sentence written as `{{SENTENCE_2}}` must release exactly
the text and sources a correct typed revision would, and no candidate may ever hold a label."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry, UsageLimits, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart, UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from evals.muse import revision_run
from evals.muse.revision_run import (
    RevisionCase, draft_messages, draft_sentences, load_revision_cases, measure,
)
from src.linger.agents.muse.agent import build_muse_agent, validate_muse_output
from src.linger.agents.muse.claim_repair import _sentence_mappings, _sentence_spans, label_sentences
from src.linger.agents.muse.labels import Expansion, accepted_output_call, annotate_retry, expand_labels
from src.linger.agents.muse.models import DraftSentence, MuseCandidate
from src.linger.agents.muse.skills import reflection_run_options
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence

CASES = load_revision_cases()
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def by_id(case_id: str) -> RevisionCase:
    return next(case for case in CASES if case.case_id == case_id)


def book(evidence_id: str, *claims: str, limits=(), quote=None) -> dict:
    return {"source_kind": "book_corpus", "evidence_id": evidence_id, "source_location": f"{evidence_id} loc",
            "supported_claims": list(claims), "limit_claims": list(limits), "exact_quote": quote}


def record(evidence_id: str, location: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id, work_id="w", book_version_id="w-v1", chapter_id="w-v1-ch05",
        chapter_number=5, location=location, source_sha256="a" * 64, source_lines=(1, 2), text="text",
    )


# Recorded (run3 pigeon-serpent): the splitter cuts inside “…from the sky! Ugh, Serpent!”.
PIGEON_QUOTE = "wriggling down\nfrom the sky! Ugh, Serpent!"
PIGEON = {
    "reply": (
        "In Chapter 5, the Pigeon is preoccupied with serpents that threaten its eggs. "
        f"It sees Alice’s unusually long neck and says serpents come “{PIGEON_QUOTE}”—so it takes her "
        "for one. When Alice admits she has tasted eggs, the Pigeon treats that as further reason to "
        "distrust her. It reads Alice through the danger it already fears."
    ),
    "evidence_uses": [
        book("ch05-a", "In Chapter 5, the Pigeon is preoccupied with serpents that threaten its eggs.",
             f"It sees Alice’s unusually long neck and says serpents come “{PIGEON_QUOTE}”—so it takes her for one.",
             quote=PIGEON_QUOTE),
        book("ch05-b", "When Alice admits she has tasted eggs, the Pigeon treats that as further reason to "
             "distrust her."),
    ],
    "memory": NO_MEMORY,
}
# Recorded shapes reduced: a claim across two sentences, a limit, a session line, a memory nomination.
MIXED = {
    "reply": (
        "Marta sees the storm first. She tells Oren before the boat leaves.\n\n"
        "Oren boards anyway, and the passage does not say whether he believes her. "
        "You said you read it twice. What do you make of her warning?"
    ),
    "evidence_uses": [
        book("ch01-a", "Marta sees the storm first. She tells Oren before the boat leaves.", "Oren boards anyway",
             limits=["the passage does not say whether he believes her."]),
        {"source_kind": "session_line", "quote": "I read the storm chapter twice",
         "supported_claims": ["You said you read it twice."]},
    ],
    "memory": {"kind": "memory_candidate", "text": "I read the storm chapter twice", "start_codepoint": 0,
               "end_codepoint": 30, "reason_code": "durable_reflection", "evidence_ids": []},
}


def sentences_for(draft: MuseCandidate, flagged=(), needs_source=()) -> tuple[DraftSentence, ...]:
    """Production placement for the given flags, then production labelling."""
    sentences = tuple(
        DraftSentence(text=draft.reply[a:b], flagged=i in flagged, needs_source=i in needs_source,
                      finding_indexes=(0,) if i in flagged else (),
                      source_mappings=_sentence_mappings(draft, a, b))
        for i, (a, b) in enumerate(_sentence_spans(draft.reply)))
    return label_sentences(draft, sentences)


def labels_of(sentences) -> list[str | None]:
    return [sentence.label for sentence in sentences]


def accepted(*outputs: dict, accept: int = 0) -> list:
    """History of one draft response with these output calls, pydantic-ai accepting `outputs[accept]`."""
    calls = [ToolCallPart("final_result", output, tool_call_id=f"call-{i}") for i, output in enumerate(outputs)]
    returns = [ToolReturnPart("final_result", "Final result processed." if i == accept else
                              "Output tool not used - a final result was already processed.", tool_call_id=f"call-{i}")
               for i in range(len(outputs))]
    return [ModelResponse(parts=calls), ModelRequest(parts=returns)]


def expand(history: list, sentences, raw: dict, records=()):
    """Run the boundary's expansion with this history before the revision envelope."""
    prompt = "<revision envelope>"
    ctx = SimpleNamespace(prompt=prompt, messages=[*history, ModelRequest(parts=[UserPromptPart(content=prompt)])])
    token = set_turn_evidence(tuple(records))
    try:
        data, expansion = expand_labels(ctx, raw, sentences)
    finally:
        reset_turn_evidence(token)
    return MuseCandidate.model_validate(data), expansion


def all_labels(sentences, joiner: str) -> str:
    return joiner.join(dict.fromkeys(s.label for s in sentences))


def raw(reply: str, *uses: dict) -> dict:
    return {"reply": reply, "evidence_uses": list(uses), "memory": NO_MEMORY}


# --- round trip ------------------------------------------------------------------


@pytest.mark.parametrize("joiner", [" ", "\n", "", "  \n "])
@pytest.mark.parametrize("data", [PIGEON, MIXED], ids=["quotation-split", "mixed-shapes"])
def test_every_label_reproduces_the_draft_exactly(data, joiner):
    draft = MuseCandidate.model_validate(data)
    sentences = sentences_for(draft)
    assert all(labels_of(sentences))
    expanded, _ = expand(accepted(data), sentences, raw(all_labels(sentences, joiner)) | {"memory": data["memory"]})
    assert expanded.model_dump(mode="json") == draft.model_dump(mode="json")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_every_label_reproduces_each_eval_draft_from_its_replayed_history(case):
    reset = revision_run._bind_turn(case)
    try:
        history = asyncio.run(draft_messages(case))
        draft = MuseCandidate.model_validate(case.draft)
        sentences = sentences_for(draft)
        expanded, _ = expand(history, sentences, raw(all_labels(sentences, " ")) | {"memory": case.draft["memory"]},
                             revision_run._records(case))
    finally:
        reset()
    assert expanded.model_dump(mode="json") == draft.model_dump(mode="json")


def test_book_source_location_comes_from_the_turn_ledger():
    draft = MuseCandidate.model_validate(PIGEON)
    expanded, _ = expand(accepted(PIGEON), sentences_for(draft), raw("{{SENTENCE_1}}"),
                         [record("ch05-a", "Ledger loc")])
    assert expanded.evidence_uses[0].source_location == "Ledger loc"


def test_typed_whitespace_between_adjacent_labels_becomes_the_draft_separator():
    draft = MuseCandidate.model_validate(MIXED)
    sentences = sentences_for(draft)
    expanded, _ = expand(accepted(MIXED), sentences, raw("{{SENTENCE_2}} {{SENTENCE_3}}"))
    assert expanded.reply == (
        "She tells Oren before the boat leaves.\n\n"
        "Oren boards anyway, and the passage does not say whether he believes her."
    )
    # Not adjacent in the draft: typed whitespace stays.
    expanded, _ = expand(accepted(MIXED), sentences, raw("{{SENTENCE_1}}\n{{SENTENCE_5}}"))
    assert expanded.reply == "Marta sees the storm first.\nWhat do you make of her warning?"


def test_a_claim_across_two_sentences_is_carried_whole_or_clipped_to_the_kept_one():
    draft = MuseCandidate.model_validate(MIXED)
    sentences = sentences_for(draft)
    whole = "Marta sees the storm first. She tells Oren before the boat leaves."
    expanded, _ = expand(accepted(MIXED), sentences, raw("{{SENTENCE_1}} {{SENTENCE_2}}"))
    assert expanded.evidence_uses[0].supported_claims == (whole,)
    expanded, _ = expand(accepted(MIXED), sentences, raw("{{SENTENCE_1}} Then {{SENTENCE_2}}"))
    assert expanded.evidence_uses[0].supported_claims == ("Marta sees the storm first.",
                                                          "She tells Oren before the boat leaves.")


# --- lossless labelling ----------------------------------------------------------


def test_sentences_sharing_a_quotation_form_one_unit_kept_or_dropped_together():
    draft = MuseCandidate.model_validate(PIGEON)
    sentences = sentences_for(draft)
    assert labels_of(sentences) == ["{{SENTENCE_1}}", "{{SENTENCE_2}}", "{{SENTENCE_2}}",
                                    "{{SENTENCE_4}}", "{{SENTENCE_5}}"]
    expanded, _ = expand(accepted(PIGEON), sentences, raw("{{SENTENCE_2}}"))
    spans = _sentence_spans(draft.reply)
    assert expanded.reply == draft.reply[spans[1][0]:spans[2][1]]
    assert expanded.evidence_uses[0].exact_quote == PIGEON_QUOTE


def test_a_sentence_sharing_a_quotation_with_a_flagged_sentence_has_no_label():
    draft = MuseCandidate.model_validate(PIGEON)
    expected = ["{{SENTENCE_1}}", None, None, "{{SENTENCE_4}}", "{{SENTENCE_5}}"]
    assert labels_of(sentences_for(draft, flagged={2})) == expected
    assert labels_of(sentences_for(draft, needs_source={1})) == expected


def test_a_sentence_whose_limit_or_quote_could_not_be_carried_whole_has_no_label():
    reply = "Marta sees the storm. The passage does not say. Whether Oren believes her is open."

    def labels(*uses):
        return labels_of(sentences_for(MuseCandidate.model_validate(raw(reply, *uses))))

    assert labels(book("a", "Marta sees the storm.", limits=["The passage does not say. Whether Oren believes her is open."])
                  ) == ["{{SENTENCE_1}}", None, None]
    assert labels(book("a", "Marta sees the storm.", limits=["The passage does not say."])
                  ) == ["{{SENTENCE_1}}", None, "{{SENTENCE_3}}"]
    assert labels(book("a", reply, quote="storm. The passage")) == [None, None, "{{SENTENCE_3}}"]


# --- the reviewed draft ------------------------------------------------------------


def test_labels_are_unusable_without_one_accepted_draft_that_rebuilds_the_sentences():
    draft = MuseCandidate.model_validate(MIXED)
    sentences = sentences_for(draft)
    reworded = copy.deepcopy(MIXED) | {"reply": MIXED["reply"].replace("storm", "squall")}
    for history in (
        [],  # no draft in history
        [ModelResponse(parts=[ToolCallPart("final_result", MIXED, tool_call_id="x")])],  # never accepted
        accepted(reworded),  # accepted, but not the reviewed draft
        [*accepted(MIXED)[:1], *accepted(MIXED)],  # the accepted call id is ambiguous
    ):
        with pytest.raises(ModelRetry) as retry:
            expand(history, sentences, raw("{{SENTENCE_1}}"))
        assert [e["label_error"] for e in json.loads(retry.value.message)["errors"]] == ["label_unknown"]


@pytest.mark.parametrize("second", ["extra_quote", "reworded"])
def test_the_accepted_output_call_is_the_draft_not_a_later_one_in_the_same_response(second):
    """pydantic-ai accepts the first output call; a second one in the same response is answered but unused."""
    case = by_id("muse-revision-unflagged-repeat-v1")
    kept = "He also wants every boat home before the lamps are lit."
    other = copy.deepcopy(case.draft)
    if second == "extra_quote":
        other["evidence_uses"][0]["exact_quote"] = kept
    else:
        other["reply"] = other["reply"].replace("He also wants", "He further wants")
        other["evidence_uses"][0]["supported_claims"][1] = kept.replace("He also wants", "He further wants")
    history = asyncio.run(_draft_run(case, [case.draft, other]))
    assert accepted_output_call(history).args_as_dict() == case.draft
    reference, _ = labelled_reference(case)
    run = _revise(case, [reference], history=history)
    plain = _revise(case, [case.reference_revision])
    assert run["output"] == plain["output"] and not run["retries"]


def test_a_rejected_revision_attempt_is_never_taken_for_the_draft():
    case = by_id("muse-revision-unflagged-repeat-v1")
    retyped = copy.deepcopy(case.reference_revision)
    retyped["reply"] = retyped["reply"].replace("Does his caution", "Does this caution")
    reference, _ = labelled_reference(case)
    run = _revise(case, [retyped, reference])
    assert len(run["retries"]) == 1 and run["output"] == _revise(case, [case.reference_revision])["output"]


def test_a_draft_reply_with_outer_whitespace_still_labels_and_expands():
    padded = MIXED | {"reply": "\n  " + MIXED["reply"] + "  \n"}
    draft = MuseCandidate.model_validate(MIXED)
    expanded, _ = expand(accepted(padded), sentences_for(draft), raw("{{SENTENCE_1}} {{SENTENCE_2}}"))
    assert expanded.reply == "Marta sees the storm first. She tells Oren before the boat leaves."


# --- no candidate holds a label ---------------------------------------------------


@pytest.mark.parametrize("token", ["{{SENTENCE_2}}", "SENTENCE_2", "{{S2}}", "｛｛x｝｝", "&#123;&#123;x", "&lbrace;x"])
@pytest.mark.parametrize("field", ["reply", "claim", "limit", "quote", "session_quote", "memory"])
def test_no_candidate_can_be_built_with_a_label(field, token):
    def candidate(text: str) -> dict:
        clean = "Marta sees the storm first."
        memory = {"kind": "memory_candidate", "text": text, "start_codepoint": 0,
                  "end_codepoint": len(text), "reason_code": "durable_reflection", "evidence_ids": []}
        return raw(clean) | {
            "reply": {"reply": text},
            "claim": {"evidence_uses": [book("a", text)]},
            "limit": {"evidence_uses": [book("a", clean, limits=[text])]},
            "quote": {"evidence_uses": [book("a", clean, quote=text)]},
            "session_quote": {"evidence_uses": [
                {"source_kind": "session_line", "quote": text, "supported_claims": [clean]}]},
            "memory": {"memory": memory},
        }[field]

    with pytest.raises(ValidationError):
        MuseCandidate.model_validate(candidate(f"Marta sees the storm {token} first."))
    MuseCandidate.model_validate(candidate("Marta sees the storm first, again."))


@pytest.mark.parametrize("prose", [
    "Dear [Name],", "Season 2 [S2] was better", "<s3> tags", "Psalm [s23]", "{the}", "a <3 b",
    "In sentence 2 she lies.", "an s390x host", "Read S2 then S3.",
])
def test_ordinary_text_is_not_a_label(prose):
    MuseCandidate.model_validate(raw(prose))


def test_a_draft_output_with_a_label_is_retried():
    case = by_id("muse-revision-unflagged-repeat-v1")
    bad = case.draft | {"reply": "{{SENTENCE_1}} " + case.draft["reply"]}
    result = asyncio.run(_draft_run(case, [bad], then=[case.draft], keep_result=True))
    assert sum(isinstance(part, RetryPromptPart) for m in result.new_messages() for part in m.parts) == 1
    assert result.output.model_dump(mode="json") == MuseCandidate.model_validate(case.draft).model_dump(mode="json")


# --- end to end with a scripted model ----------------------------------------------


async def _draft_run(case: RevisionCase, final: list[dict], then=(), keep_result=False):
    """The case's draft run, its final response holding `final` output calls (then `then`)."""
    tools = list(case.draft_tool_calls)
    responses = [final, *([output] for output in then)]

    def respond(messages, info):
        if tools:
            tool = tools.pop(0)
            args = {} if tool == "librarian_route" else {
                "work_id": revision_run.WORK_ID, "book_version_id": revision_run.BOOK_VERSION_ID}
            return ModelResponse(parts=[ToolCallPart(tool, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output) for output in responses.pop(0)])

    reset = revision_run._bind_turn(case)
    try:
        muse = build_muse_agent(FunctionModel(respond))
        with muse.override(tools=revision_run._tools(case)):
            result = await muse.run(revision_run._draft_input(case).model_dump_json(),
                                    message_history=revision_run._history(case),
                                    **reflection_run_options(revision=False, tools=case.exposed_tools))
    finally:
        reset()
    return result if keep_result else [*revision_run._history(case), *result.new_messages()]


def _revise(case: RevisionCase, outputs: list, history=None) -> dict:
    """One revision run with scripted outputs: the returned candidate (or None) and the retry contents."""
    seen = []

    def respond(messages, info):
        output = outputs[min(len(seen), len(outputs) - 1)]
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    async def run():
        nonlocal history
        if history is None:
            history = [*revision_run._history(case), *await draft_messages(case)]
        muse = build_muse_agent(FunctionModel(respond))
        with capture_run_messages() as messages, muse.override(tools=revision_run._tools(case)):
            try:
                result = await muse.run(revision_run.revision_input(case).model_dump_json(), message_history=history,
                                        usage_limits=UsageLimits(request_limit=10),
                                        **reflection_run_options(revision=True, tools=case.exposed_tools))
                output = result.output.model_dump(mode="json")
            except UnexpectedModelBehavior:
                output = None
        return output, [part.content for m in messages[len(history):] for part in m.parts
                        if isinstance(part, RetryPromptPart)]

    reset = revision_run._bind_turn(case)
    try:
        output, retries = asyncio.run(run())
    finally:
        reset()
    return {"output": output, "retries": retries}


def _run(case: RevisionCase, *outputs) -> tuple[dict, list]:
    calls = []

    def respond(messages, info):
        output = outputs[min(len(calls), len(outputs) - 1)]
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    report = asyncio.run(measure(FunctionModel(respond), runs=1, cases=(case,)))
    return report["per_case"][case.case_id]["runs"][0], calls


def _retries(calls) -> list[dict]:
    return [json.loads(part.content) for part in calls[-1][-1].parts if isinstance(part, RetryPromptPart)
            and isinstance(part.content, str)] if calls else []


def labelled_reference(case: RevisionCase) -> tuple[dict, int]:
    """The reference revision with each kept labelled unit written as its label."""
    reference = json.loads(json.dumps(case.reference_revision))
    units: dict[str, str] = {}
    for sentence in draft_sentences(case):
        if sentence.label:
            units[sentence.label] = (units[sentence.label] + " " if sentence.label in units else "") + sentence.text
    kept = {label: text for label, text in units.items() if text in reference["reply"]}

    def labelled(text: str) -> str:
        for label, unit in kept.items():
            text = text.replace(unit, label)
        return text

    reference["reply"] = labelled(reference["reply"])
    uses = []
    for use in reference["evidence_uses"]:
        # A claim that is only labels is carried from the draft; Muse declares only what it typed.
        use["supported_claims"] = [c for c in map(labelled, use["supported_claims"]) if c not in kept]
        if use["supported_claims"]:
            uses.append(use)
    reference["evidence_uses"] = uses
    return reference, len(kept)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_labelled_reference_releases_what_the_plain_reference_releases(case):
    plain, _ = _run(case, case.reference_revision)
    reference, count = labelled_reference(case)
    labelled, _ = _run(case, reference)
    assert count >= 2
    assert plain["retries"] == 0 and plain["hard_pass"], plain
    assert labelled["retries"] == 0, labelled["retry_categories"]
    # The second review sees the same candidate, declarations included.
    for key in ("reply", "evidence_uses", "hard_pass", "failures"):
        assert labelled[key] == plain[key], key
    assert labelled["labels_used"] == count and labelled["expansion_changed"]
    assert labelled["raw_outputs"][-1]["reply"] == reference["reply"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_a_label_free_output_passes_the_hook_untouched_and_gets_the_validator_retry(case):
    sentences = draft_sentences(case)
    for output in (case.draft, case.reference_revision):
        assert expand_labels(SimpleNamespace(prompt="", messages=[]), output, sentences) == (output, None)
    run, calls = _run(case, case.draft, case.reference_revision)
    reset = revision_run._bind_turn(case)
    try:
        ctx = SimpleNamespace(prompt=revision_run.revision_input(case).model_dump_json())
        with pytest.raises(ModelRetry) as direct:
            validate_muse_output(ctx, MuseCandidate.model_validate(case.draft))
    finally:
        reset()
    assert _retries(calls) == [json.loads(direct.value.message)]
    assert run["labelled_retyped"] == labelled_reference(case)[1] and not run["expansion_changed"]


UNFLAGGED = by_id("muse-revision-unflagged-repeat-v1")
_FIRST = UNFLAGGED.reference_revision["evidence_uses"][0]["supported_claims"][0]
_KEPT = "He also wants every boat home before the lamps are lit."
_ASK = "Does his caution seem reasonable to you?"
UNUSABLE = {
    "unknown": ("{{SENTENCE_9}}", "label_unknown"),
    "flagged": ("{{SENTENCE_1}}", "label_unknown"),
    "duplicate": ("{{SENTENCE_2}} {{SENTENCE_2}}", "label_duplicate"),
    **{form: (form, "label_malformed") for form in [
        "{{label}}", "SENTENCE_2", "{{SENTENCE_2a}}", "{{Sentence 2}}", "{{2}}", "{{SENTENCE:2}}",
        "{{SENTENCE.2}}", "{{#SENTENCE_2}}", "{{SENT2}}", "{{S2}}", "｛｛SENTENCE_2｝｝",
        "&#123;&#123;SENTENCE_2&#125;&#125;", "&lbrace;&lbrace;SENTENCE_2&rbrace;&rbrace;", "((SENTENCE_2))",
        "(SENTENCE_2)", '"SENTENCE_2"', "%%SENTENCE_2%%", "__SENTENCE_2__", "{{SENTENCE_\n2}}",
        "`{{SENTENCE_2}}`", "[{{SENTENCE_2}}](https://example.com)", "{{SENTENCE_1-SENTENCE_3}}",
        "{{SENTENCE_2,SENTENCE_3}}", "{{SENTENCE_2}}.", "{{ SENTENCE_2 }}", "{{sentence_2}}", "{SENTENCE_2}",
        "{{SENTENCE_2}}​", "{{{SENTENCE_2}}}",
    ]},
}


@pytest.mark.parametrize("name", list(UNUSABLE))
def test_an_unusable_label_is_retried_and_never_returned(name):
    token, category = UNUSABLE[name]
    # A paragraph break after the token, so nothing is caught by an accident of sentence splitting.
    bad = UNFLAGGED.reference_revision | {"reply": f"{_FIRST} {token}\n\n{_ASK}"}
    bad["evidence_uses"] = [bad["evidence_uses"][0] | {"supported_claims": [_FIRST]}]
    run = _revise(UNFLAGGED, [bad])
    assert run["output"] is None
    errors = [json.loads(retry)["errors"] for retry in run["retries"]]
    assert all(error["label_error"] == category for attempt in errors for error in attempt)
    repaired = _revise(UNFLAGGED, [bad, UNFLAGGED.reference_revision])
    assert repaired["output"] == _revise(UNFLAGGED, [UNFLAGGED.reference_revision])["output"]


def test_a_label_inside_a_claim_is_expanded_and_a_malformed_one_retried():
    good = UNFLAGGED.reference_revision | {"reply": f"{_FIRST} {{{{SENTENCE_2}}}} {_ASK}"}
    good["evidence_uses"] = [good["evidence_uses"][0] | {"supported_claims": [f"{_FIRST} {{{{SENTENCE_2}}}}"]}]
    run, _ = _run(UNFLAGGED, good)
    assert run["retries"] == 0 and run["evidence_uses"][0]["supported_claims"] == [f"{_FIRST} {_KEPT}", _KEPT]
    bad = good | {"evidence_uses": [good["evidence_uses"][0] | {"supported_claims": [f"{_FIRST} {{{{ SENTENCE_2 }}}}"]}]}
    run, _ = _run(UNFLAGGED, bad, good)
    assert run["retry_categories"][0] == ["label_malformed"]


def test_a_label_in_a_revision_without_labels_is_retried():
    data = json.loads(UNFLAGGED.model_dump_json())
    data["review"]["needs_source_sentences"] = [1, 2, 3]
    case = RevisionCase.model_validate(data)
    assert not any(labels_of(draft_sentences(case)))
    run, _ = _run(case, case.reference_revision | {"reply": f"{_FIRST} {{{{SENTENCE_2}}}} {_ASK}"})
    assert run.get("retry_exhausted") and run["retry_categories"][0] == ["label_unknown"]


def test_the_reply_limit_applies_after_expansion():
    data = json.loads(UNFLAGGED.model_dump_json())
    long_sentence = ("The tide turns slowly while the gulls circle over the quiet water, " * 200).strip(" ,") + "."
    data["draft"]["reply"] = f"{data['draft']['evidence_uses'][0]['supported_claims'][0]} {long_sentence}"
    data["draft"]["evidence_uses"][0]["supported_claims"] = data["draft"]["evidence_uses"][0]["supported_claims"][:1]
    data["review"]["previously_accepted_claims"] = []
    data["expect"] = {"flagged_sentences": [0]}
    data["reference_revision"]["reply"] = f"{_FIRST} {long_sentence}"
    data["reference_revision"]["evidence_uses"][0]["supported_claims"] = [_FIRST]
    case = RevisionCase.model_validate(data)
    extra = " ".join(["The lamps are lit one by one along the quay."] * 150)
    bad = case.reference_revision | {"reply": f"{_FIRST} {{{{SENTENCE_2}}}} {extra}"}
    assert len(bad["reply"]) < 20_000
    run, _ = _run(case, bad, case.reference_revision)
    assert run["retry_categories"][0] == ["schema"] and run["retries"] == 1 and run["hard_pass"]


# --- Muse redeclaring a labelled sentence --------------------------------------------


def test_a_labelled_claim_redeclared_under_its_draft_source_is_not_duplicated():
    reference, _ = labelled_reference(UNFLAGGED)
    redeclared = json.loads(json.dumps(reference))
    redeclared["evidence_uses"][0]["supported_claims"].append(_KEPT)
    run, _ = _run(UNFLAGGED, redeclared)
    plain, _ = _run(UNFLAGGED, reference)
    assert run["retries"] == 0 and run["evidence_uses"] == plain["evidence_uses"]


def test_a_redeclaring_declaration_with_its_own_quote_is_left_as_written():
    draft = MuseCandidate.model_validate(MIXED)
    own = book("ch01-a", "Oren boards anyway", "She tells Oren before the boat leaves.", quote="Oren")
    expanded, _ = expand(accepted(MIXED), sentences_for(draft),
                         raw("{{SENTENCE_2}} Oren boards anyway.", own))
    assert own in [use.model_dump(mode="json") for use in expanded.evidence_uses]


def test_a_labelled_claim_given_a_new_source_is_retried_and_names_the_label():
    reference, _ = labelled_reference(UNFLAGGED)
    bad = json.loads(json.dumps(reference))
    bad["evidence_uses"][0]["supported_claims"].append("Not in the reply.")
    bad["evidence_uses"].append({"source_kind": "session_line", "quote": UNFLAGGED.reader_message,
                                 "supported_claims": ["{{SENTENCE_2}}"]})
    run, calls = _run(UNFLAGGED, bad, reference)
    retry = _retries(calls)[0]
    assert run["retry_categories"][0] == ["claim_span", "added_source"] and run["label_annotated_errors"] == 1
    assert "labels_note" in retry
    # Paths cite Muse's own declarations, not the merged and reordered expanded ones.
    assert "evidence_uses[0].supported_claims" in [error["path"] for error in retry["errors"]]
    assert [error.get("from_labels") for error in retry["errors"]] == [None, ["{{SENTENCE_2}}"]]


def test_nested_declaration_indexes_in_a_retry_are_muses_own():
    """quoted-fragment: the quotation error lists declared sources by index; Muse wrote one declaration."""
    case = by_id("muse-revision-quoted-fragment-v1")
    reference, _ = labelled_reference(case)
    new = "In Chapter 1, Ines calls the ferry “a patient animal,” as if it were alive."
    bad = reference | {"reply": f"{new} {{{{SENTENCE_2}}}} Does that match how the crossing felt to you as you read?"}
    bad["evidence_uses"] = [reference["evidence_uses"][0] | {"supported_claims": [new]}]
    _, calls = _run(case, bad, reference)
    indexes = []

    def collect(value):
        if isinstance(value, dict):
            indexes.extend(v for k, v in value.items() if k == "declaration_index")
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    collect(_retries(calls)[0])
    assert indexes and set(indexes) <= {0, "carried draft declaration"}


def test_from_labels_follows_positions_not_text_that_also_occurs_in_a_label():
    expansion = Expansion(reply="Kept sentence here. Typed here.", placements=(("{{SENTENCE_1}}", 0, 19),),
                          origins=(0,))
    retry = ModelRetry(json.dumps({"errors": [
        {"path": "reply", "value": "here", "response_start": 26, "response_end": 30},
        {"path": "reply", "value": "Kept sentence"},
    ]}))
    errors = json.loads(annotate_retry(retry, expansion).message)["errors"]
    assert [error.get("from_labels") for error in errors] == [None, ["{{SENTENCE_1}}"]]
