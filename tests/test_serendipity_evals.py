"""Deterministic gates for the versioned Serendipity baseline."""

import unittest

from evals.serendipity.harness import (
    REQUIRED_BEHAVIORS,
    ExpectedDecline,
    ExpectedProposal,
    SerendipityEvalCase,
    grade_serendipity_response,
    load_serendipity_eval_cases,
)
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDecline,
    ConnectionProposal,
)


def _response_for(case: SerendipityEvalCase):
    if isinstance(case.expected, ExpectedDecline):
        return ConnectionDecline(
            reason=case.expected.allowed_reasons[0],
            safe_next_step="Describe a more specific moment or continue reading.",
        )
    assert isinstance(case.expected, ExpectedProposal)
    evidence_by_id = {item.evidence_id: item for item in case.tool_evidence}
    cited_kinds = {
        evidence_by_id[evidence_id].source_kind
        for evidence_id in case.expected.required_evidence_ids
    }
    rubric = CandidateRubric(
        cue_fit="direct",
        reflective_value="high",
        safety="clear",
    )

    def candidate(candidate_id: str, rank: int) -> ConnectionCandidate:
        return ConnectionCandidate(
            candidate_id=candidate_id,
            rank=rank,
            tentative_claim=(
                "Alice's changing size may complicate her effort to describe who she is."
                if rank == 1
                else "The exchange may also connect self-description with unequal authority."
            ),
            evidence_ids=case.expected.required_evidence_ids,
            shared_structure="Both passages unsettle a stable sense of self.",
            meaningful_difference=(
                "One stages physical change while the other demands self-explanation."
            ),
            interpretation=(
                "The recurrence may make the question feel more like a test than an invitation."
            ),
            rubric=rubric,
            comparison_note=(
                "This is the most directly supported interpretation."
                if rank == 1
                else "This is plausible but less specific to the cue."
            ),
        )

    return ConnectionProposal(
        shortlist=(
            candidate("candidate-primary", 1),
            candidate("candidate-alternative", 2),
        ),
        selected_candidate_id="candidate-primary",
        uncertainty="medium",
        presentation=case.expected.presentation,
        suggested_follow_up="Does that repetition change how the scene feels?",
        policy_flags=tuple(
            flag
            for source, flag in (
                ("authorised_memory", "uses_authorised_memory"),
                ("web", "contains_web_claim"),
            )
            if source in cited_kinds
        ),
    )


class SerendipityEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_serendipity_eval_cases()

    def test_loads_one_case_for_every_current_behavior(self) -> None:
        self.assertEqual(7, len(self.cases))
        self.assertEqual(
            REQUIRED_BEHAVIORS,
            {case.primary_behavior for case in self.cases},
        )

    def test_expected_responses_pass_hard_gates(self) -> None:
        for case in self.cases:
            with self.subTest(case=case.case_id):
                grade = grade_serendipity_response(case, _response_for(case))
                self.assertTrue(grade.hard_pass, grade.failures)

    def test_proposal_with_unknown_evidence_fails(self) -> None:
        case = next(
            case
            for case in self.cases
            if isinstance(case.expected, ExpectedProposal)
        )
        response = _response_for(case)
        changed = response.shortlist[0].model_copy(
            update={
                "evidence_ids": (
                    case.expected.required_evidence_ids[0],
                    "unknown",
                )
            }
        )
        response = response.model_copy(
            update={"shortlist": (changed, response.shortlist[1])}
        )

        grade = grade_serendipity_response(case, response)

        self.assertFalse(grade.hard_pass)
        self.assertIn("proposal_references_unknown_evidence", grade.failures)

    def test_wrong_decline_reason_fails(self) -> None:
        case = next(
            case
            for case in self.cases
            if case.primary_behavior == "unsafe_evidence_decline"
        )

        grade = grade_serendipity_response(
            case,
            ConnectionDecline(
                reason="generic_theme_match",
                safe_next_step="Try another cue.",
            ),
        )

        self.assertFalse(grade.hard_pass)
        self.assertIn("unexpected_decline_reason:generic_theme_match", grade.failures)


if __name__ == "__main__":
    unittest.main()
