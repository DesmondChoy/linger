"""Blind rubric grading of Muse reports, with a scripted judge (no provider calls)."""

import asyncio
import json
import unittest

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.muse import blind_review
from evals.muse.blind_review import JudgeVerdict, verdict_of
from evals.muse.harness import load_muse_eval_cases

CASE_ID = "muse-relay-tentative-connection-v1"


def _report(digest: str, replies: list[str]) -> dict:
    return {
        "model": "gpt-6-luna",
        "prompt": {"digest": digest},
        "per_case": {CASE_ID: {"runs": [{"reply": reply} for reply in replies] + [{"error": "X"}]}},
    }


class VerdictTests(unittest.TestCase):
    def _judged(self, *grades: str, **extra) -> JudgeVerdict:
        return JudgeVerdict(
            criteria=tuple(
                {"criterion": index, "grade": grade, "note": ""}
                for index, grade in enumerate(grades, start=1)
            ),
            rationale="",
            **extra,
        )

    def test_verdict_rules(self) -> None:
        self.assertEqual("pass", verdict_of(self._judged("met", "met"), 2))
        self.assertEqual("partial", verdict_of(self._judged("met", "partly"), 2))
        self.assertEqual("partial", verdict_of(self._judged("met", "not_met"), 2))
        self.assertEqual("fail", verdict_of(self._judged("not_met", "not_met", "met"), 3))
        # A criterion the judge skipped counts as not met.
        self.assertEqual("partial", verdict_of(self._judged("met"), 2))
        self.assertEqual(
            "fail", verdict_of(self._judged("met", unsupported_details=("sitting by the river",)), 1)
        )
        self.assertEqual("fail", verdict_of(self._judged("met", forbidden_claims_present=(1,)), 1))


class BlindReviewTests(unittest.TestCase):
    def test_replies_are_graded_blind_then_counted_per_version(self) -> None:
        prompts: list[str] = []
        criteria = len(next(
            case for case in load_muse_eval_cases() if case.case_id == CASE_ID
        ).expected.semantic_review.criteria)

        def judge(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            prompt = messages[-1].parts[-1].content
            prompts.append(prompt)
            invented = ["Alice sat by the river"] if "riverbank" in prompt else []
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "criteria": [
                    {"criterion": index, "grade": "met", "note": "ok"}
                    for index in range(1, criteria + 1)
                ],
                "unsupported_details": invented,
                "rationale": "graded",
            })])

        reports = [
            ("vHEADX", _report("HEADDIGEST", ["It may loosely echo Alice.", "Maybe at the riverbank."])),
            ("vCURX", _report("CURDIGEST", ["It may loosely echo Alice."])),
        ]
        result = asyncio.run(blind_review.review(reports, FunctionModel(judge), seed=7))

        self.assertEqual(3, len(prompts))
        for prompt in prompts:
            for identity in ("vHEADX", "vCURX", "HEADDIGEST", "CURDIGEST", "gpt-6-luna"):
                self.assertNotIn(identity, prompt)
        self.assertIn("could not even get her head through the doorway", prompts[0])
        self.assertEqual(
            {"pass": 1, "partial": 0, "fail": 1, "errors": 0,
             "unsupported_detail_replies": 1, "forbidden_claim_replies": 0},
            {key: result["versions"]["vHEADX"][key] for key in (
                "pass", "partial", "fail", "errors",
                "unsupported_detail_replies", "forbidden_claim_replies")},
        )
        self.assertEqual(1, result["versions"]["vCURX"]["pass"])
        self.assertEqual(1, result["per_case"][CASE_ID]["vCURX"]["pass"])
        self.assertEqual("HEADDIGEST", result["versions"]["vHEADX"]["report_prompt_digest"])
        self.assertEqual(3, result["items"])
        for key in ("prompt", "runs", "cases", "errors", "hard_pass_rate", "mean_input_tokens"):
            self.assertIn(key, result)
        json.dumps(result)

    def test_shuffle_is_seeded_and_mixes_versions(self) -> None:
        reports = [
            ("a", _report("A", [f"a{index}" for index in range(10)])),
            ("b", _report("B", [f"b{index}" for index in range(10)])),
        ]
        first = blind_review.pool_replies(reports, {CASE_ID}, seed=1)
        again = blind_review.pool_replies(reports, {CASE_ID}, seed=1)
        self.assertEqual(first, again)
        self.assertNotEqual(["a"] * 10 + ["b"] * 10, [item.label for item in first])
        self.assertEqual(20, len({item.item_id for item in first}))


if __name__ == "__main__":
    unittest.main()
