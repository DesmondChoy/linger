"""Experiment arms change only what the experiment is about."""

from evals.serendipity import analysis, experiments
from evals.serendipity.harness import load_serendipity_eval_cases


def test_triage_intent_changes_only_web_recommendation_cases_sent_as_connections():
    # The suite's web cases already carry the triage intent (8 Oct), so build
    # the as-written form the experiment compared against.
    cases = tuple(
        experiments._variant(case, **{"input.intent": "find_connection", "input.presentation": "ask_before_showing",
                                      "expected.presentation": "ask_before_showing"})
        if case.primary_behavior == experiments.WEB_RECOMMENDATION else case
        for case in load_serendipity_eval_cases()
    )
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


def _proposal_run(cue_fit, *, hard_pass, failures=()):
    return {
        "hard_pass": hard_pass,
        "failures": list(failures),
        "response": {"status": "proposal", "shortlist": [{"rubric": {"cue_fit": cue_fit}}]},
    }


def test_direct_gate_turns_a_partial_winner_into_a_decline():
    cases = {case.case_id: case for case in load_serendipity_eval_cases()}
    generic = cases["serendipity-decline-generic-bridge-v3"]
    bridge = cases["serendipity-select-real-semantic-bridge-v3"]
    # A wrong proposal on a restraint case becomes an accepted decline.
    assert analysis.gated_pass(_proposal_run("partial", hard_pass=False, failures=["expected_decline"]), generic)
    # Another failure on the same run still fails.
    assert not analysis.gated_pass(
        _proposal_run("partial", hard_pass=False, failures=["expected_decline", "unexpected_search:web_search"]),
        generic,
    )
    # A right proposal with a partial winner is lost; a direct winner is kept.
    assert not analysis.gated_pass(_proposal_run("partial", hard_pass=True), bridge)
    assert analysis.gated_pass(_proposal_run("direct", hard_pass=True), bridge)
    # Declines are untouched.
    assert analysis.gated_pass({"hard_pass": True, "failures": [], "response": {"status": "decline"}}, generic)


def test_cost_prices_tokens_per_passing_run():
    report = {
        "model": "openai:gpt-6-luna (reasoning medium)",
        "cases": [{"runs": [
            {"hard_pass": True, "input_tokens": 1_000_000, "output_tokens": 1_000_000},
            {"hard_pass": False, "input_tokens": 0, "output_tokens": 0},
        ]}],
    }
    result = analysis.cost(report)
    assert result["usd_total"] == 0.6
    assert result["usd_per_pass"] == 0.6
