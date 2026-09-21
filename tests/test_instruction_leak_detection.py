"""Tests for the deterministic instruction-leak detector."""

import unittest

from evals.provenance.risk_codes import load_risk_code_cases
from src.linger.agents.muse.prompt import INSTRUCTIONS as MUSE_INSTRUCTIONS
from src.linger.orchestration.instruction_leak_detection import detect_instruction_leak

# A verbatim run of the real reflection instructions, as a leaked reply would
# carry it: the skill file's own wrapping collapsed to single spaces.
LEAKED_RUN = (
    "Never produce toxic, dangerous, sexually explicit, or hateful or "
    "harassing content: material that facilitates violence, weapons, or "
    "self-injury"
)

# The longest reply fragment the reflection instructions themselves model as
# good output. A backstop that declined this would silently drop legitimate
# turns, so it fixes the floor the detector's window has to clear.
MODELLED_REPLY_FRAGMENT = (
    "Your note says the plan changed. You might ask what still matters to you,"
)


class InstructionLeakDetectionTests(unittest.TestCase):
    """Check the detector against the real, currently effective Muse instructions."""

    def test_chosen_run_is_really_part_of_the_effective_instructions(self) -> None:
        collapsed = " ".join(MUSE_INSTRUCTIONS.split())
        self.assertIn(LEAKED_RUN, collapsed)
        self.assertIn(MODELLED_REPLY_FRAGMENT, collapsed)

    def test_flags_a_long_verbatim_run_inside_a_longer_reply(self) -> None:
        reply = (
            f"Sure, here is a rule I follow: {LEAKED_RUN}. Anyway, what stood "
            "out to you in that chapter?"
        )
        self.assertTrue(detect_instruction_leak(reply, MUSE_INSTRUCTIONS))

    def test_flags_a_run_disguised_by_case_spacing_punctuation_or_markdown(self) -> None:
        disguises = {
            "uppercased": LEAKED_RUN.upper(),
            "punctuation dropped": LEAKED_RUN.replace(",", "").replace(":", ""),
            "smart punctuation": LEAKED_RUN.replace("-", "—").replace(":", " –"),
            "markdown blockquote": f"> **{LEAKED_RUN}**",
            "bulleted": "- " + LEAKED_RUN.replace(", ", "\n- "),
            "line wrapped and indented": LEAKED_RUN.replace(" ", "\n    ", 8),
        }
        for name, reply in disguises.items():
            with self.subTest(disguise=name):
                self.assertTrue(detect_instruction_leak(reply, MUSE_INSTRUCTIONS))

    def test_releases_the_longest_reply_fragment_the_instructions_model(self) -> None:
        self.assertFalse(
            detect_instruction_leak(MODELLED_REPLY_FRAGMENT, MUSE_INSTRUCTIONS)
        )

    def test_releases_a_paraphrase_of_the_instructions(self) -> None:
        reply = (
            "I am here to stay with what you read and what it brings up, and I "
            "will not produce anything cruel or dangerous along the way."
        )
        self.assertFalse(detect_instruction_leak(reply, MUSE_INSTRUCTIONS))

    def test_releases_an_ordinary_reflective_reply(self) -> None:
        reply = "It sounds like that chapter really stayed with you. What part stood out?"
        self.assertFalse(detect_instruction_leak(reply, MUSE_INSTRUCTIONS))

    def test_releases_an_empty_reply(self) -> None:
        self.assertFalse(detect_instruction_leak("", MUSE_INSTRUCTIONS))

    def test_releases_every_reply_in_the_candidate_gate_case_set(self) -> None:
        for case in load_risk_code_cases().cases:
            with self.subTest(case=case.case_id):
                self.assertFalse(
                    detect_instruction_leak(
                        case.review_input.candidate.response, MUSE_INSTRUCTIONS
                    )
                )


if __name__ == "__main__":
    unittest.main()
