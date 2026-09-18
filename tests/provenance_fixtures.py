"""Explicit audits for mocked reviewers, never a semantic production validator."""

from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from src.linger.agents.provenance.quotation_audit import quote_is_bound


def review_with_audits(payload, review):
    """Complete a fixture's coverage and claim audits, preserving its chosen verdict.

    These mocks deliberately assert support for declared claims, including in
    tests of a fallible reviewer rejected by deterministic release checks. They
    classify gaps as reader reflection without establishing that judgment or
    actual semantic support. Excerpts use real named sources; unresolved sources
    remain noncontributing and cannot pass current-input validation. Nonempty
    supplied audits are preserved. Unbound quoted text is treated as proposed
    wording by these fallible mocks, not by production validation. Tests
    for either behavior must supply their own coverage/claim audits explicitly.
    """
    request = (ProvenanceInput.model_validate_json(payload) if isinstance(payload, str)
               else payload if isinstance(payload, ProvenanceInput)
               else ProvenanceInput.model_validate(payload))
    output = review if isinstance(review, ProvenanceReview) else ProvenanceReview.model_validate(review)
    quote_valid = {check.declaration_index for check in request.quote_checks
                   if check.source_found and check.quote_in_source and check.quote_in_response}
    quotation_audit = []
    for span in request.quoted_response_spans:
        bound = next((index for index, use in enumerate(request.candidate.evidence_uses)
                      if quote_is_bound(span, request.candidate.response, use,
                                        quote_valid=index in quote_valid,
                                        verified_session_lines=request.canonical_session_lines)), None)
        quotation_audit.append({
            "span_index": span.span_index,
            "classification": ("source_quote" if bound is not None else
                               "current_reader_wording" if span.text and span.text in request.current_line.text else
                               "proposed_wording"),
            "declaration_index": bound,
        })
    return ProvenanceReview.model_validate({
        **output.model_dump(mode="json"),
        "quotation_audit": [audit.model_dump(mode="json") for audit in output.quotation_audit] or quotation_audit,
        "coverage_audit": [audit.model_dump(mode="json") for audit in output.coverage_audit] or [
            {"span_index": span.span_index, "classification": "reader_reflection"}
            for span in request.uncovered_response_spans
        ],
        "claim_audit": [audit.model_dump(mode="json") for audit in output.claim_audit] or [
            {"group_index": group.group_index, "supported": True,
             "support_summary": "The mocked reviewer asserts collective support; semantic correctness is not established by this fixture.",
             "source_contributions": [
                 {"declaration_index": member.declaration_index, "claim_index": member.claim_index,
                  "contributes": bool(source := request.contribution_source_text(member.declaration_index)),
                  "source_excerpt": source[:800] if source else None}
                 for member in group.declarations
             ]}
            for group in request.claim_support_groups
        ],
    })
