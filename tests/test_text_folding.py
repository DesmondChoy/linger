"""Tests for the detector-only Unicode/leet folding helpers."""

import unittest

from src.linger.contracts.text_folding import fold_for_detection, fold_for_self_harm


class FoldForDetectionTests(unittest.TestCase):
    def test_strips_combining_marks_threaded_through_a_word(self) -> None:
        self.assertEqual("kill", fold_for_detection("ki̴ll"))

    def test_strips_combining_marks_from_a_precomposed_accent(self) -> None:
        self.assertEqual("cafe", fold_for_detection("café"))

    def test_decomposes_fullwidth_letters_to_ascii(self) -> None:
        self.assertEqual("kill", fold_for_detection("ｋｉｌｌ"))

    def test_decomposes_the_fi_ligature(self) -> None:
        self.assertEqual("fine", fold_for_detection("ﬁne"))

    def test_maps_cyrillic_homoglyphs_to_latin(self) -> None:
        # k-і-l-l with a Cyrillic BYELORUSSIAN-UKRAINIAN I in place of "i".
        self.assertEqual("kill", fold_for_detection("kіll"))
        self.assertEqual(
            "example.com", fold_for_detection("еxаmplе.com")
        )

    def test_maps_greek_homoglyphs_to_latin(self) -> None:
        self.assertEqual("apple", fold_for_detection("αpplε"))
        # ρ (rho) is visually a lowercase Latin "p", not "r".
        self.assertEqual("pho", fold_for_detection("ρho"))

    def test_casefolds(self) -> None:
        self.assertEqual("kill myself", fold_for_detection("KILL MYSELF"))

    def test_leaves_ordinary_ascii_untouched(self) -> None:
        self.assertEqual(
            "an ordinary sentence.", fold_for_detection("an ordinary sentence.")
        )

    def test_is_idempotent(self) -> None:
        for text in ("ki̴ll", "ｋｉｌｌ", "kіll MYSELF", "plain"):
            once = fold_for_detection(text)
            twice = fold_for_detection(once)
            self.assertEqual(once, twice)


class FoldForSelfHarmTests(unittest.TestCase):
    def test_folds_leetspeak_digit_substitutions(self) -> None:
        self.assertEqual("kill myself", fold_for_self_harm("k1ll myself"))

    def test_does_not_touch_a_plain_number_token(self) -> None:
        self.assertEqual("i have 100 dollars", fold_for_self_harm("i have 100 dollars"))
        self.assertEqual("i have 3 cats", fold_for_self_harm("i have 3 cats"))

    def test_collapses_space_separated_single_letters(self) -> None:
        self.assertEqual("kill myself", fold_for_self_harm("k i l l myself"))

    def test_collapses_hyphen_separated_single_letters(self) -> None:
        self.assertEqual("kill myself", fold_for_self_harm("k-i-l-l myself"))

    def test_collapses_dot_separated_single_letters(self) -> None:
        self.assertEqual("kill myself", fold_for_self_harm("k.i.l.l myself"))

    def test_leaves_a_two_letter_pair_uncollapsed(self) -> None:
        self.assertEqual("a b", fold_for_self_harm("a b"))

    def test_applies_unicode_folding_before_leet_and_collapse(self) -> None:
        self.assertEqual("kill myself", fold_for_self_harm("KіLL MYSELF"))

    def test_is_idempotent(self) -> None:
        for text in ("k1ll myself", "k i l l myself", "k-i-l-l myself", "plain text"):
            once = fold_for_self_harm(text)
            twice = fold_for_self_harm(once)
            self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
