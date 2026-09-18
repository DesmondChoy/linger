"""Explicit occurrence proof for controlled boundary judges in local tests."""


def event_resolution(reader_text, evidence, selected_ids):
    selected_ids = tuple(dict.fromkeys(selected_ids))
    available = [item for item in evidence if item.evidence_id in selected_ids]
    if available:
        chapter = max(
            getattr(item, "chapter_number", getattr(item, "chapter", None))
            for item in available
        )
        current_ids = tuple(
            item.evidence_id
            for item in available
            if getattr(item, "chapter_number", getattr(item, "chapter", None))
            == chapter
        )
    else:
        current_ids = selected_ids
    return {
        "reader_event_spans": (reader_text,),
        "occurrences": (
            {
                "evidence_ids": current_ids,
                "disposition": "selected",
                "distinguishing_reader_spans": (reader_text,),
                "explanation": "The controlled test judge identifies this supplied event from the reader's wording.",
            },
        ),
        "other_evidence_ids": tuple(
            item.evidence_id for item in evidence if item.evidence_id not in current_ids
        ),
    }


def quoted_support(evidence, selected_ids=None):
    """Bind controlled judge support to the actual supplied fixture text."""
    by_id = {item.evidence_id: item for item in evidence}
    if selected_ids is None:
        selected_ids = tuple(by_id)
    anchors = []
    for identity in selected_ids:
        record = by_id[identity]
        anchors.append({
            "evidence_id": identity,
            "source_excerpt": getattr(record, "text", getattr(record, "excerpt", None)),
        })
    return tuple(anchors)


def identify_fixture_event(chapter):
    """Explicit fake identification for tests whose controlled stop is already fixed."""
    async def identify(request):
        from src.linger.agents.librarian.models import BoundaryEventIdentified
        selected = tuple(record.evidence_id for record in request.full_work_candidates
                         if record.chapter_number == chapter)
        return BoundaryEventIdentified(
            outcome="identified", evidence_ids=selected,
            reader_spans=(request.current_line,),
            explanation="The independent controlled fixture identifies this event.",
        )
    return identify
