"""Tests for the deterministic first-person self-harm/suicide detector."""

import unittest

from apps.backend.message_normalization import normalize_reader_message
from src.linger.orchestration.self_harm_detection import detect_first_person_self_harm


def detect_as_ingested(raw: str) -> bool:
    """Run `raw` through the same normalisation production applies before detection."""
    return detect_first_person_self_harm(normalize_reader_message(raw))


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


class ObfuscationBypassTests(unittest.TestCase):
    """Each case is run through `normalize_reader_message` first, as production does."""

    def test_combining_mark_threaded_through_a_flagged_word(self) -> None:
        self.assertTrue(detect_as_ingested("i want to ki̴ll myself"))

    def test_fullwidth_letters(self) -> None:
        self.assertTrue(detect_as_ingested("i want to ｋｉｌｌ myself"))

    def test_leetspeak(self) -> None:
        self.assertTrue(detect_as_ingested("i want to k1ll myself"))

    def test_spaced_letters(self) -> None:
        self.assertTrue(detect_as_ingested("i want to k i l l myself"))

    def test_hyphenated_letters(self) -> None:
        self.assertTrue(detect_as_ingested("i want to k-i-l-l myself"))

    def test_dotted_letters(self) -> None:
        self.assertTrue(detect_as_ingested("i want to k.i.l.l myself"))

    def test_cyrillic_homoglyphs(self) -> None:
        self.assertTrue(detect_as_ingested("i want to kіll myself"))

    def test_wanna_contraction(self) -> None:
        self.assertTrue(detect_as_ingested("i wanna kill myself"))

    def test_gonna_contraction(self) -> None:
        self.assertTrue(detect_as_ingested("i'm gonna kill myself"))

    def test_unalive_myself(self) -> None:
        self.assertTrue(detect_as_ingested("i wanna unalive myself"))
        self.assertTrue(detect_as_ingested("i am going to unalive myself"))

    def test_unalive_me(self) -> None:
        self.assertTrue(detect_as_ingested("i want to unalive me"))

    def test_not_want_to_be_here_anymore(self) -> None:
        self.assertTrue(detect_as_ingested("i don't want to be here anymore"))
        self.assertTrue(detect_as_ingested("i do not want to be here any more"))

    def test_end_it_all(self) -> None:
        self.assertTrue(detect_as_ingested("i want to end it all"))

    def test_typo_wnat(self) -> None:
        self.assertTrue(detect_as_ingested("i wnat to kill myself"))

    def test_dont_want_to_live_bare(self) -> None:
        self.assertTrue(detect_as_ingested("i don't want to live"))
        self.assertTrue(detect_as_ingested("i don't want to live anymore"))

    def test_no_reason_to_live_or_go_on(self) -> None:
        self.assertTrue(detect_as_ingested("i have no reason to live"))
        self.assertTrue(detect_as_ingested("i have no reason to go on"))

    def test_better_off_without_me(self) -> None:
        self.assertTrue(detect_as_ingested("everyone would be better off without me"))
        self.assertTrue(detect_as_ingested("i think i'm better off without me"))

    def test_still_ignores_third_person_and_idioms_after_folding(self) -> None:
        for message in (
            "I'd kill myself laughing at that scene",
            "This commute makes me want to die",
            "I want to die of embarrassment",
            "She takes her own life at the end.",
            "I don't want to live in this city anymore",
            "I don't want to be here at this meeting.",
        ):
            with self.subTest(message=message):
                self.assertFalse(detect_as_ingested(message))


if __name__ == "__main__":
    unittest.main()
