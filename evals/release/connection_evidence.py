"""Verify that connection grading mismatches stay inside source authority."""

from __future__ import annotations

import json


_CODES = frozenset({"authorized_book_citation_mismatch", "authorized_book_selection_mismatch"})


def verified_connection_book_evidence(
    scene: dict, planned: dict, backstory: dict, truth: dict, runner: str,
) -> bool:
    """Verify book authority from successful observations, retaining unrelated failed attempts."""
    try:
        return _verified_connection_book_evidence(scene, planned, backstory, truth, runner)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _verified_connection_book_evidence(
    scene: dict, planned: dict, backstory: dict, truth: dict, runner: str,
) -> bool:
    """Prove every claimed book mismatch without trusting its recorded label."""
    if runner.removeprefix("evals.synthetic_journals.") != "connection_replay" or not any(
        _CODES.intersection(grade.get("failures", ())) for grade in scene.get("grades", ())
    ):
        return False
    from apps.backend.contracts import EvidenceItem
    from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
    from evals.synthetic_journals.connection_replay import (
        ConnectionSceneObservation, _authorized_book_extras, _evidence_ledger, _runtime_ids,
    )
    from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
    from src.linger.agents.librarian.models import (
        BookEvidenceAssessment, LibrarianEvidenceStrengthInput, evidence_assessment_errors,
    )
    from src.linger.agents.muse.models import MuseCandidate
    from src.linger.agents.provenance.models import CandidateUnderReview, ProvenanceInput, ProvenanceReview
    from src.linger.agents.serendipity.models import (
        ConnectionDiscoveryInput, ConnectionProposal, InternalSearchResult, SERENDIPITY_RESPONSE_ADAPTER, SourceBundle,
    )
    from src.linger.contracts.reading import contains_scope, permits_scope
    from src.linger.contracts.turn import ReleaseScope
    from src.linger.orchestration.book_evidence import evidence_record_from_item

    observed = ConnectionSceneObservation.model_validate_json(json.dumps(scene))
    plan = compile_connection_replay_plan(
        SyntheticBackstory.model_validate_json(json.dumps(backstory)),
        ProposedGroundTruth.model_validate_json(json.dumps(truth)),
    )
    compiled = next(item for item in plan.scenes if item.scene.scene_id == observed.scene_id)
    if (
        planned["scene_id"] != observed.scene_id or planned["line_ids"] != [observed.line_id]
        or observed.line_id != compiled.line.line_id or compiled.source_setup is None
        or observed.release_source != "muse_candidate"
        or observed.hard_gate_pass
    ):
        return False
    releases = [event for event in observed.events if event.kind == "release"]
    discoveries = [event for event in observed.events
                   if event.kind == "discovery" and event.status in {"proposal", "gathered"}]
    if (
        len(releases) != 1 or len(discoveries) != 1 or observed.events[-1] != releases[0]
        or releases[0].status != "released" or releases[0].release_source != observed.release_source
        or releases[0].released_evidence_ids != observed.released_evidence_ids
        or not releases[0].provenance_verdicts or releases[0].provenance_verdicts[-1] != "pass"
        or releases[0].failure_code or releases[0].failure_stage
    ):
        return False
    exchanges = observed.agent_exchanges
    if tuple(item.sequence for item in exchanges) != tuple(range(1, len(exchanges) + 1)) or not exchanges:
        return False
    successful = [item for item in exchanges if item.status == "success" and item.output is not None
                  and not item.failure_code and not item.failure_category
                  and not item.provider_status_code and not item.provider_error_kind]
    selections = [item for item in successful if item.role == "Serendipity"]
    reviews = [item for item in successful if item.role == "Provenance" and item.stage == "review"]
    candidates = [item for item in successful if item.role == "Muse" and item.stage in {"draft", "revision"}]
    if len(selections) != 1 or not reviews or not candidates:
        return False
    if (selections[0].input_contract != "src.linger.agents.serendipity.models.ConnectionDiscoveryInput"
            or reviews[-1].input_contract != "src.linger.agents.provenance.models.ProvenanceInput"):
        return False
    task = ConnectionDiscoveryInput.model_validate_json(selections[0].input_prompt)
    decision = SERENDIPITY_RESPONSE_ADAPTER.validate_json(discoveries[0].decision_json or "null")
    if (
        decision != SERENDIPITY_RESPONSE_ADAPTER.validate_python(selections[0].output)
        or not isinstance(decision, (ConnectionProposal, SourceBundle))
        or discoveries[0].status != decision.status
    ):
        return False
    selected = set(decision.selected_candidate.evidence_ids if isinstance(decision, ConnectionProposal)
                   else decision.evidence_ids)
    response_flow = [item for item in successful if (
        (item.role == "Muse" and item.stage in {"draft", "revision"})
        or (item.role == "Provenance" and item.stage == "review")
    )]
    if tuple((item.role, item.stage) for item in response_flow) not in (
        (("Muse", "draft"), ("Provenance", "review")),
        (("Muse", "draft"), ("Provenance", "review"), ("Muse", "revision"), ("Provenance", "review")),
    ):
        return False
    previous_candidate = previous_review = None
    verdicts = []
    for candidate_exchange, review_exchange in zip(response_flow[::2], response_flow[1::2], strict=True):
        candidate = MuseCandidate.model_validate(candidate_exchange.output)
        review_input = ProvenanceInput.model_validate_json(review_exchange.input_prompt)
        review = ProvenanceReview.model_validate(review_exchange.output)
        review_input.validate_review(review)
        expected_candidate = CandidateUnderReview(
            response=candidate.reply, memory=candidate.memory, evidence_uses=candidate.evidence_uses,
        )
        if (review_input.current_line.text != compiled.line.text
                or review_input.candidate != expected_candidate
                or review.capture_decision != "no_candidate"
                or review_input.context.policy.allow_memory_capture
                or not review_input.context.policy.allow_retrieval
                or not review_input.context.policy.allow_connection):
            return False
        prior = review_input.previous_response_review
        if previous_candidate is None:
            if prior is not None:
                return False
        elif (prior is None or previous_review.response_decision != "revise"
              or prior.candidate != previous_candidate or prior.findings != previous_review.response_findings):
            return False
        previous_candidate, previous_review = expected_candidate, review
        verdicts.append(review.response_decision)
    if (
        review.response_decision != "pass" or candidate.reply != observed.reply
        or tuple(verdicts) != releases[0].provenance_verdicts
        or set(observed.released_evidence_ids) != {
            use.evidence_id for use in candidate.evidence_uses if hasattr(use, "evidence_id")
        }
    ):
        return False
    scopes = tuple(ReleaseScope(
        work_id=scope.work_id, book_version_id=scope.book_version_id,
        chapter_max=scope.safe_ceiling_chapter,
    ) for scope in compiled.source_setup.book_scopes)
    if not task.scope.book_scopes or any(
        not any(contains_scope(grant, requested) for grant in scopes)
        for requested in task.scope.book_scopes
    ):
        return False
    ledger = _evidence_ledger(observed.events)
    book_tools = [tool for tool in selections[0].tool_exchanges
                  if tool.tool_name == "search_librarian" and tool.outcome == "success"]
    returned_books = {}
    searched_books = _evidence_ledger(tuple(
        event for event in observed.events
        if event.kind == "search" and event.operation == "search_librarian"
        and event.source == "book_corpus" and event.status == "evidence_found"
    ))
    assessments = []
    for exchange in successful:
        if exchange.role != "Librarian" or exchange.stage != "evidence_strength":
            continue
        request = LibrarianEvidenceStrengthInput.model_validate_json(exchange.input_prompt)
        assessment = BookEvidenceAssessment.model_validate(exchange.output)
        if (request.original_request.current_line != compiled.line.text
                or evidence_assessment_errors(assessment, request)):
            return False
        by_label = {record.evidence_id: record for record in request.evidence}
        selected_records = tuple(by_label[label] for label in assessment.relevant_evidence_ids)
        assessments.append((assessment.evidence_strength, selected_records))
    for tool in book_tools:
        result = InternalSearchResult.model_validate(tool.result)
        if result.outcome == "retrieval_unavailable":
            continue
        returned_records = tuple(evidence_record_from_item(item) for item in result.evidence)
        if not any(
            strength == result.judgement.evidence_strength
            and len(records) == len(returned_records)
            and all(any(record.model_copy(update={"evidence_id": actual.evidence_id}) == actual
                        for actual in returned_records) for record in records)
            for strength, records in assessments
        ):
            return False
        for item in result.evidence:
            record = item.model_dump(mode="json")
            identity = record["evidence_id"]
            if identity in returned_books and returned_books[identity] != record:
                return False
            returned_books[identity] = record
    prop_ids = {}
    for prop in compiled.props:
        matches = [identity for identity, record in ledger.items()
                   if record.get("source_kind") == "memory" and record.get("excerpt") == prop.source_text]
        if len(matches) != 1:
            return False
        prop_ids[prop.prop_id] = matches[0]
    proposals = {item.proposal_id: item for item in compiled.proposals}
    reviewed_books = {record.evidence_id: record for record in review_input.canonical_book_evidence}
    for grade in observed.grades:
        codes = _CODES.intersection(grade.failures)
        if not codes:
            continue
        proposal = proposals[grade.proposal_id]
        if grade.objective_id != proposal.objective_id or proposal.connection is None:
            return False
        mapped, failures = _runtime_ids(compiled, proposal, prop_ids, ledger)
        if failures:
            return False
        permitted = set().union(*(mapped[identity] for identity in proposal.connection.permitted_evidence_ids))
        for code in codes:
            cited = code == "authorized_book_citation_mismatch"
            extra = (set(observed.released_evidence_ids) if cited else selected) - permitted
            if not _authorized_book_extras(compiled, proposal.connection, extra, ledger):
                return False
            for identity in extra:
                if (returned_books.get(identity) != ledger[identity]
                        or searched_books.get(identity) != ledger[identity]):
                    return False
                canonical = evidence_record_from_item(EvidenceItem.model_validate(ledger[identity]))
                if not any(permits_scope(scope, canonical) for scope in task.scope.book_scopes):
                    return False
                if cited and reviewed_books.get(identity) != canonical:
                    return False
    return True
