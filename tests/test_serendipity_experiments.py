"""Experiment arms change only what the experiment is about."""

from evals.serendipity import experiments
from evals.serendipity.harness import load_serendipity_eval_cases


def test_triage_intent_changes_only_web_recommendation_cases_sent_as_connections():
    cases = load_serendipity_eval_cases()
    variants = experiments.triage_intent_variants(cases)
    assert variants
    for case_id, variant in variants.items():
        original = next(case for case in cases if case.case_id == case_id)
        assert original.primary_behavior == experiments.WEB_RECOMMENDATION
        assert original.input.intent == "find_connection"
        assert variant.input.intent == "get_recommendation"
        assert variant.input.presentation == variant.expected.presentation == "direct"
        assert variant.tool_evidence == original.tool_evidence


def test_real_pages_replace_only_web_excerpts():
    cases = load_serendipity_eval_cases()
    snapshots = {"https://plato.stanford.edu/entries/identity-personal/": {"text": "Full article text.", "title": "t"}}
    variants = experiments.real_page_variants(cases, snapshots)
    assert variants
    for case_id, variant in variants.items():
        original = next(case for case in cases if case.case_id == case_id)
        for before, after in zip(original.tool_evidence, variant.tool_evidence):
            if before.evidence_id in snapshots:
                assert after.excerpt == "Full article text."
            else:
                assert after == before
