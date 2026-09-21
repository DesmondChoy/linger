"""Tests for the deterministic first-person self-harm/suicide detector."""

import unittest

from src.linger.orchestration.self_harm_detection import detect_first_person_self_harm


class FirstPersonSelfHarmDetectionTests(unittest.TestCase):
    def test_detects_first_person_disclosures(self) -> None:
        for message in (
            "I want to kill myself",
            "I just want to kill myself tonight",
            "I am going to kill myself",
            "I'm going to end my life",
            "Im going to end it all",
            "I want to take my own life",
            "I plan to end my life",
            "I want to die",
            "I need to die",
            "I want to hurt myself",
            "I've been cutting myself",
            "I keep hurting myself",
            "I've been thinking about suicide",
            "I've thought about killing myself",
            "I'm thinking about ending it all",
            "Lately I keep thinking about suicide.",
            "I'm suicidal and don't know what to do.",
            "I feel suicidal",
            "I've had suicidal thoughts for months",
            "I don't want to be alive",
            "I do not want to live anymore",
            "I'd be better off dead",
            "I want to commit suicide",
        ):
            with self.subTest(message=message):
                self.assertTrue(detect_first_person_self_harm(message))

    def test_ignores_third_person_and_literary_discussion(self) -> None:
        for message in (
            "Why does Anna kill herself?",
            "The character's suicide was the turning point of the novel.",
            "He wants to kill himself in the last act.",
            "She takes her own life at the end.",
            "The narrator says he is better off dead.",
            "My colleague said he wanted to end his life last year.",
            "My friend is suicidal and I don't know how to help.",
            "This chapter on suicide was hard to read.",
            "I keep thinking about the suicide in chapter seven.",
            "I want to write an essay about suicide in Victorian novels.",
        ):
            with self.subTest(message=message):
                self.assertFalse(detect_first_person_self_harm(message))

    def test_ignores_reading_statements_idioms_and_negations(self) -> None:
        for message in (
            "I'm reading a book about suicide",
            "I'm reading a book about a character who wants to die.",
            "I am reading a chapter where the protagonist plans to kill himself.",
            "I'd kill myself laughing at that scene",
            "I could kill myself for forgetting the book at home",
            "This commute makes me want to die",
            "I want to die of embarrassment",
            "I have been cutting myself off from friends lately",
            "I don't want to kill myself",
            "I never want to kill myself",
            "I'm not going to kill myself",
            "I'm not suicidal",
            "I would never take my own life",
            "I don't want to live in this city anymore",
            "I cannot cope anymore",
            "I'm mildly annoyed by the ending.",
        ):
            with self.subTest(message=message):
                self.assertFalse(detect_first_person_self_harm(message))

    def test_normalizes_case_and_curly_apostrophes(self) -> None:
        self.assertTrue(detect_first_person_self_harm("I’M GOING TO END MY LIFE"))
        self.assertTrue(detect_first_person_self_harm("i don’t want to be alive"))

    def test_quoted_first_person_dialogue_still_applies_the_boundary(self) -> None:
        """Attribution is beyond a deterministic phrase match, so quotation fails safe."""
        self.assertTrue(
            detect_first_person_self_harm(
                "The character says 'I want to die' in chapter three."
            )
        )


if __name__ == "__main__":
    unittest.main()
