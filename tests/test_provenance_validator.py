"""Tests for Provenance's generation-time candidate-review validator."""

import json
import unittest
from types import SimpleNamespace

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
from src.linger.agents.provenance.review_validation import validate_provenance_review
from src.linger.agents.provenance.models import (
    FindingResolution,
    ProvenanceReview,
    RiskFinding,
    StructuralLocation,
    TextSpanLocation,
)
from src.linger.agents.provenance.review_context import (
    reset_review_input,
    set_review_input,
)
from tests.test_provenance_review import provenance_input

RESPONSE = (
    "Short answer: yes, there is a braille form of notation, and blind musicians "
    "use a mix of approaches: reading by touch."
)
EXACT_QUOTE = RESPONSE[: RESPONSE.index("approaches:") + len("approaches:")]
MISMATCHED_QUOTE = EXACT_QUOTE[:-1] + "."


def _revise(quote: str) -> ProvenanceReview:
    return ProvenanceReview(
        findings=(
            RiskFinding(
                code="uncited_web_claim",
                applies_to="response",
                location=TextSpanLocation(
                    kind="text_span",
                    source_field="candidate.response",
                    path="",
                    quote=quote,
                ),
                explanation="A public fact is stated without a citation.",
            ),
        ),
        response_decision="revise",
        emotional_boundary_decision="not_required",
        capture_decision="no_candidate",
    )


class ProvenanceReviewValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review_input = provenance_input(RESPONSE)
        self.context = SimpleNamespace(deps=None)

    def _bind(self) -> None:
        token = set_review_input(self.review_input)
        self.addCleanup(reset_review_input, token)

    def test_retries_a_quote_that_does_not_match_its_source(self) -> None:
        self._bind()
        with self.assertRaises(ModelRetry) as caught:
            validate_provenance_review(self.context, _revise(MISMATCHED_QUOTE))
        message = str(caught.exception)
        self.assertIn("does not match", message)
        self.assertIn(MISMATCHED_QUOTE, message)
        repair = json.loads(message)
        self.assertEqual(MISMATCHED_QUOTE, repair["errors"][0]["quote"])
        self.assertIn("approaches:", repair["errors"][0]["source_excerpt"])

    def test_returns_an_exact_quote_unchanged(self) -> None:
        self._bind()
        review = _revise(EXACT_QUOTE)
        self.assertIs(review, validate_provenance_review(self.context, review))

    def test_is_a_no_op_without_a_bound_review_input(self) -> None:
        review = _revise(MISMATCHED_QUOTE)
        self.assertIs(review, validate_provenance_review(self.context, review))

    def test_retries_resolutions_for_a_nonexistent_previous_finding(self) -> None:
        self._bind()
        review = ProvenanceReview(
            response_decision="pass",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
            finding_resolutions=(
                FindingResolution(
                    finding_index=0, status="resolved", explanation="Fixed.",
                ),
            ),
        )
        with self.assertRaises(ModelRetry) as caught:
            validate_provenance_review(self.context, review)
        self.assertIn("finding_resolutions", str(caught.exception))


class FindingSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review_input = provenance_input(RESPONSE)

    def test_resolves_the_candidate_response(self) -> None:
        location = StructuralLocation(
            kind="structural", source_field="candidate.response", path="",
        )
        self.assertEqual(RESPONSE, self.review_input.finding_source(location))

    def test_rejects_a_missing_path(self) -> None:
        for source_field, path in (
            ("canonical_book_evidence", "/0"),
            ("candidate.response", "/text"),
            ("candidate.memory", "/missing"),
        ):
            with self.subTest(source_field=source_field, path=path):
                location = StructuralLocation(
                    kind="structural", source_field=source_field, path=path,
                )
                with self.assertRaises(ValueError):
                    self.review_input.finding_source(location)


class CandidateReviewOutputToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_validated_run_keeps_the_plain_review_output_tool(self) -> None:
        seen: list[tuple[str, str | None, dict]] = []

        def respond(messages, info: AgentInfo) -> ModelResponse:
            tool, = info.output_tools
            seen.append((tool.name, tool.description, tool.parameters_json_schema))
            return ModelResponse(parts=[ToolCallPart(tool.name, {
                "findings": [],
                "response_decision": "pass",
                "emotional_boundary_decision": "not_required",
                "capture_decision": "no_candidate",
            })])

        agent = build_provenance_agent(FunctionModel(respond))
        prompt = provenance_input(RESPONSE).model_dump_json()
        validated = await agent.run(prompt, **CANDIDATE_REVIEW.run_options())
        plain = await agent.run(prompt, output_type=ProvenanceReview)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(validated.output, plain.output)
        self.assertIsInstance(validated.output, ProvenanceReview)


if __name__ == "__main__":
    unittest.main()
