"""Expand the sentence labels a Muse revision writes in place of kept draft sentences.

`draft_sentences` labels each unit of unflagged sentences the revision can keep
losslessly. Muse writes the label, such as `{{SENTENCE_2}}`, instead of retyping
that unit; before schema validation the application substitutes the unit's exact
draft text and its draft declarations, shaped as if Muse had typed them, so the
existing validators and the second review see an ordinary candidate.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from src.linger.agents.muse.claim_repair import (
    _occurrences, _sentence_mappings, _sentence_spans, label_sentences,
)
from src.linger.agents.muse.models import LABEL_TRACE, DraftSentence, MuseCandidate

# pydantic-ai's tool return for the one output call it accepted as the run's result.
_FINAL_RESULT_PROCESSED = "Final result processed."
# A label is valid only exactly as listed, with only whitespace or another label beside it.
_LABEL = re.compile(r"(?<![^\s}])\{\{SENTENCE_\d+\}\}(?![^\s{])")
_HAS_WORD = re.compile(r"\w")
_EVIDENCE_PATH = re.compile(r"^evidence_uses\[(\d+)\](?:\.(supported_claims|limit_claims)\[\d+\])?")
_MALFORMED = (
    "Copy labels exactly as listed in draft_sentences, such as {{SENTENCE_2}}, each standing alone "
    "between sentences; a label already includes its sentence's punctuation. Ranges such as "
    "{{SENTENCE_1-SENTENCE_3}}, altered or partial labels, labels "
    "inside code, links or quotation marks, and {{ }} braces are not accepted: write each label "
    "separately, or write the text out."
)


@dataclass(frozen=True)
class Expansion:
    """Where labelled text landed, for pointing retry errors back at the label."""

    reply: str
    placements: tuple[tuple[str, int, int], ...]  # (label, start, end) in the expanded reply
    origins: tuple[int | None, ...]  # Muse's own index of each expanded declaration; None if carried only


def accepted_output_call(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The last output call pydantic-ai accepted, matched by its tool return; None when ambiguous."""
    accepted = [part.tool_call_id for message in messages if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, ToolReturnPart) and part.content == _FINAL_RESULT_PROCESSED]
    if not accepted:
        return None
    calls = [part for message in messages if isinstance(message, ModelResponse) for part in message.parts
             if isinstance(part, ToolCallPart) and part.tool_call_id == accepted[-1]]
    return calls[0] if len(calls) == 1 else None


def reviewed_draft(ctx: Any, sentences: tuple[DraftSentence, ...]) -> MuseCandidate | None:
    """The draft output accepted before this revision, or None unless it rebuilds `sentences` exactly."""
    call = accepted_output_call(list(getattr(ctx, "messages", None) or ()))
    if call is None:
        return None
    try:
        draft = MuseCandidate.model_validate(call.args_as_dict())
    except (ValidationError, ValueError):
        return None
    spans = _sentence_spans(draft.reply)
    if len(spans) != len(sentences):
        return None
    # Sentence text, flags, labels, and every declaration, field and text a label can carry.
    rebuilt = tuple(
        sentence.model_copy(update={
            "text": draft.reply[start:end], "label": None,
            "source_mappings": _sentence_mappings(draft, start, end),
        })
        for sentence, (start, end) in zip(sentences, spans)
    )
    return draft if label_sentences(draft, rebuilt) == sentences else None


def expand_labels(
    ctx: Any, raw: Any, sentences: tuple[DraftSentence, ...],
) -> tuple[Any, Expansion | None]:
    """Raw output with every label expanded; ModelRetry for anything label-like that cannot be."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return raw, None
    # Anything malformed passes through unchanged for schema validation to reject.
    if (not isinstance(data, dict) or not isinstance(data.get("reply"), str)
            or not isinstance(data.get("evidence_uses", []), list)
            or not all(isinstance(use, dict) for use in data.get("evidence_uses", []))):
        return raw, None
    uses = [dict(use) for use in data.get("evidence_uses", [])]
    if not any(LABEL_TRACE.search(text) for text in [data["reply"], *_use_texts(uses)]):
        return raw, None
    draft = reviewed_draft(ctx, sentences)
    units = _units(draft, sentences) if draft is not None else {}
    errors: list[dict[str, object]] = []
    placements: list[tuple[str, int, int]] = []
    reply = _expand(data["reply"], "reply", units, draft, errors, placements)
    for index, use in enumerate(uses):
        for field in ("supported_claims", "limit_claims"):
            if isinstance(use.get(field), list):
                use[field] = [_expand(text, f"evidence_uses[{index}].{field}", units, draft, errors)
                              if isinstance(text, str) else text for text in use[field]]
        if isinstance(use.get("exact_quote"), str):
            use["exact_quote"] = _expand(use["exact_quote"], f"evidence_uses[{index}].exact_quote",
                                         units, draft, errors)
    if errors:
        raise ModelRetry(json.dumps({
            "error": "The reply's sentence labels could not be expanded.",
            "repair": _MALFORMED,
            "errors": errors,
        }, ensure_ascii=False))
    carried = _carried(draft, units, placements, reply)
    uses, origins = _merge(uses, carried, reply) if carried else (uses, tuple(range(len(uses))))
    return {**data, "reply": reply, "evidence_uses": uses}, Expansion(reply, tuple(placements), origins)


def _use_texts(uses: list[dict]) -> list[str]:
    texts = []
    for use in uses:
        for field in ("supported_claims", "limit_claims"):
            texts += [text for text in use.get(field) or () if isinstance(text, str)]
        if isinstance(use.get("exact_quote"), str):
            texts.append(use["exact_quote"])
    return texts


def _units(draft: MuseCandidate, sentences: tuple[DraftSentence, ...]) -> dict[str, tuple[int, int, int, int]]:
    """Label -> (draft start, draft end, first sentence, last sentence)."""
    spans = _sentence_spans(draft.reply)
    units: dict[str, tuple[int, int, int, int]] = {}
    for index, sentence in enumerate(sentences):
        if sentence.label:
            first = units.get(sentence.label, (spans[index][0], 0, index, 0))
            units[sentence.label] = (first[0], spans[index][1], first[2], index)
    return units


def _error(kind: str, where: str, token: str, message: str) -> dict[str, object]:
    return {"path": where, "value": token, "label_error": kind, "error": message}


def _expand(
    value: str, where: str, units: dict[str, tuple[int, int, int, int]], draft: MuseCandidate | None,
    errors: list[dict[str, object]], placements: list[tuple[str, int, int]] | None = None,
) -> str:
    out: list[str] = []
    cursor, previous, seen = 0, None, set()
    for match in [*_LABEL.finditer(value), None]:
        typed = value[cursor:match.start() if match else len(value)]
        if bad := LABEL_TRACE.search(typed):
            errors.append(_error("label_malformed", where, typed[max(0, bad.start() - 20):bad.end() + 20],
                                 _MALFORMED))
        if match is None:
            out.append(typed)
            break
        cursor, label = match.end(), match.group(0)
        if label not in units:
            errors.append(_error("label_unknown", where, label, (
                "draft_sentences lists no such label; flagged and needs_source sentences have none."
            ) if units else "This revision has no usable sentence labels: write every sentence out."))
        elif label in seen:
            errors.append(_error("label_duplicate", where, label, "Use each label at most once."))
        else:
            seen.add(label)
            start, end, first, _ = units[label]
            if previous is not None and not typed.strip() and units[previous][3] + 1 == first:
                # Draft-adjacent units keep the draft's own separator, whatever whitespace was typed.
                typed = draft.reply[units[previous][1]:start]
            out.append(typed)
            offset = sum(map(len, out))
            out.append(draft.reply[start:end])
            if placements is not None:
                placements.append((label, offset, offset + end - start))
            previous = label
            continue
        out.append(typed)
        previous = None
    return "".join(out)


def _carried(
    draft: MuseCandidate | None, units: dict[str, tuple[int, int, int, int]],
    placements: list[tuple[str, int, int]], reply: str,
) -> list[dict[str, Any]]:
    """Draft declarations of placed units, in draft order: a mapping whole where its text survives
    verbatim, otherwise clipped to the placed units; limits and quotes only whole."""
    if not placements:
        return []
    from src.linger.orchestration.turn_context import turn_evidence

    spans = _sentence_spans(draft.reply)
    placed = {label: start - units[label][0] for label, start, _ in placements}  # draft -> reply offset
    owner = {index: label for label, (_, _, first, last) in units.items()
             if label in placed for index in range(first, last + 1)}

    def whole(a: int, b: int) -> bool:
        touched = [i for i, (s, e) in enumerate(spans) if s < b and a < e]
        if not touched or not all(i in owner for i in touched):
            return False
        offset = placed[owner[touched[0]]]
        return (all(placed[owner[i]] == offset for i in touched)
                and reply[a + offset:b + offset] == draft.reply[a:b])

    def clips(a: int, b: int) -> list[str]:
        return [text for label in placed
                if (text := draft.reply[max(a, units[label][0]):min(b, units[label][1])].strip())
                and _HAS_WORD.search(text)]

    carried = []
    for use in draft.evidence_uses:
        claims: list[str] = []
        for claim in use.supported_claims:
            found = _occurrences(draft.reply, claim)
            for text in [claim] if any(whole(a, b) for a, b in found) else [
                    piece for a, b in found for piece in clips(a, b)]:
                if text not in claims:
                    claims.append(text)
        if not claims:
            continue
        quote = getattr(use, "exact_quote", None)
        data = use.model_dump(mode="json") | {"supported_claims": claims}
        if use.source_kind != "session_line":
            data["limit_claims"] = [text for text in use.limit_claims
                                    if any(whole(a, b) for a, b in _occurrences(draft.reply, text))]
            data["exact_quote"] = quote if quote and any(
                whole(a, b) for a, b in _occurrences(draft.reply, quote)) else None
        if use.source_kind == "book_corpus" and (record := turn_evidence().get(use.evidence_id)):
            data["source_location"] = record.location
        carried.append(data)
    return carried


def _identity(use: dict[str, Any]) -> tuple[object, ...]:
    return (use.get("source_kind"), use.get("evidence_id"), use.get("quote"), use.get("exact_quote"))


def _merge(
    uses: list[dict[str, Any]], carried: list[dict[str, Any]], reply: str,
) -> tuple[list[dict[str, Any]], tuple[int | None, ...]]:
    """Shape the declarations as if Muse had typed the labelled text: each carried declaration joins
    Muse's declaration of the same source and quote, and claims and declarations follow the reply."""
    def position(text: object) -> int:
        found = reply.find(text) if isinstance(text, str) else -1
        return found if found >= 0 else len(reply)

    merged, origins = list(uses), list(range(len(uses)))
    for extra in carried:
        target = next((use for use in merged if _identity(use) == _identity(extra)), None)
        if target is None:
            merged.append(extra)
            origins.append(None)
            continue
        for field in ("supported_claims", "limit_claims"):
            if extra.get(field):
                current = list(target.get(field) or ())
                target[field] = sorted(current + [t for t in extra[field] if t not in current], key=position)
    order = sorted(range(len(merged)), key=lambda i: min(map(position, merged[i].get("supported_claims") or [None])))
    return [merged[i] for i in order], tuple(origins[i] for i in order)


def annotate_retry(retry: ModelRetry, expansion: Expansion) -> ModelRetry:
    """Name the label behind each error on inserted text, and cite Muse's own declarations."""
    try:
        body = json.loads(retry.message)
    except ValueError:
        return retry
    for error in body.get("errors") or ():
        start, end, value = error.get("response_start"), error.get("response_end"), error.get("value")
        if isinstance(start, int) and isinstance(end, int):
            spans = [(start, max(end, start + 1))]
        else:
            spans = _occurrences(expansion.reply, value) if isinstance(value, str) and value.strip() else []
        labels = [label for label, a, b in expansion.placements if any(s < b and a < e for s, e in spans)]
        if labels:
            error["from_labels"] = labels
    if expansion.placements:  # carried declarations may have been merged and reordered
        body = _renumber(body, expansion.origins)
    body["labels_note"] = (
        "Offsets and text refer to the reply with each label replaced by its draft text. An error with "
        "from_labels concerns that labelled text or its carried draft sources: keep the label unless "
        "the repair must change or delete that text."
    )
    return ModelRetry(json.dumps(body, ensure_ascii=False))


def _renumber(value: Any, origins: tuple[int | None, ...]) -> Any:
    """Cite each expanded declaration by Muse's own index; claim positions within it may have moved."""
    if isinstance(value, list):
        return [_renumber(item, origins) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        if key == "declaration_index" and isinstance(item, int) and 0 <= item < len(origins):
            item = origins[item] if origins[item] is not None else "carried draft declaration"
        elif (key == "path" and isinstance(item, str) and (match := _EVIDENCE_PATH.match(item))
              and int(match.group(1)) < len(origins)):
            origin = origins[int(match.group(1))]
            field = f".{match.group(2)}" if match.group(2) else ""
            item = (f"evidence_uses[{origin}]" if origin is not None else "carried draft declaration") + (
                field + item[match.end():])
        else:
            item = _renumber(item, origins)
        out[key] = item
    return out
