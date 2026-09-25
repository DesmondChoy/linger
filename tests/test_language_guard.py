"""Tests for the deterministic, conservative English-only message guard."""

import unittest

from src.linger.orchestration.language_guard import detect_non_english


class NonEnglishParagraphsAreRefusedTests(unittest.TestCase):
    """Clear, paragraph-length, single-language non-English text is refused."""

    def test_spanish_paragraph_is_refused(self) -> None:
        verdict = detect_non_english(
            "Hola, como estas hoy? Espero que todo vaya muy bien contigo, "
            "amigo mio, porque hace mucho tiempo que no hablamos de nada."
        )
        self.assertIsNotNone(verdict)
        self.assertEqual("es", verdict.language)
        self.assertGreaterEqual(verdict.confidence, 0.7)

    def test_french_paragraph_is_refused(self) -> None:
        verdict = detect_non_english(
            "Ceci est un livre magnifique sur la vie et l'amour, je le "
            "recommande vivement a tous mes amis proches qui aiment lire."
        )
        self.assertIsNotNone(verdict)
        self.assertEqual("fr", verdict.language)

    def test_chinese_paragraph_is_refused(self) -> None:
        verdict = detect_non_english(
            "这是一本关于爱情的小说，我非常喜欢这个故事的发展和人物描写。"
            "这本书让我想起了自己年轻时候的一些经历和感受。"
        )
        self.assertIsNotNone(verdict)
        self.assertEqual("zh", verdict.language)

    def test_malay_paragraph_is_refused(self) -> None:
        verdict = detect_non_english(
            "Selamat pagi, saya sangat suka membaca buku ini kerana "
            "ceritanya sangat menarik dan penuh emosi bagi setiap pembaca."
        )
        self.assertIsNotNone(verdict)
        self.assertIn(verdict.language, ("ms", "id"))

    def test_single_malay_sentence_is_refused(self) -> None:
        verdict = detect_non_english(
            "Saya rasa bab ini sangat menarik dan penuh dengan makna."
        )
        self.assertIsNotNone(verdict)
        self.assertIn(verdict.language, ("ms", "id"))

    def test_short_chinese_sentence_is_refused(self) -> None:
        verdict = detect_non_english("我觉得这本书的第三章写得非常好，你怎么看？")
        self.assertIsNotNone(verdict)
        self.assertEqual("zh", verdict.language)


class ConservativePassThroughTests(unittest.TestCase):
    """Short, ambiguous, or otherwise-English text must never be refused."""

    def test_short_english_greeting_passes(self) -> None:
        self.assertIsNone(detect_non_english("Hello there!"))

    def test_bare_yes_passes(self) -> None:
        self.assertIsNone(detect_non_english("yes"))

    def test_bare_ok_passes(self) -> None:
        self.assertIsNone(detect_non_english("ok"))

    def test_bare_hmm_passes(self) -> None:
        self.assertIsNone(detect_non_english("hmm"))

    def test_chapter_reference_passes(self) -> None:
        self.assertIsNone(detect_non_english("Ch. 12"))

    def test_page_reference_passes(self) -> None:
        self.assertIsNone(detect_non_english("p. 45"))

    def test_chapter_question_passes(self) -> None:
        self.assertIsNone(detect_non_english("Chapter 3?"))

    def test_english_with_quoted_french_phrase_passes(self) -> None:
        self.assertIsNone(
            detect_non_english(
                "The book mentions a phrase, c'est la vie, right when the "
                "main character gives up looking for answers."
            )
        )

    def test_english_with_japanese_book_title_passes(self) -> None:
        self.assertIsNone(
            detect_non_english(
                "I just finished reading Kokoro, a short Japanese novel "
                "about isolation and guilt in a changing society."
            )
        )

    def test_english_with_character_name_passes(self) -> None:
        self.assertIsNone(
            detect_non_english(
                "I really think Raskolnikov was the most tragic character "
                "in the entire novel, more than any of the others."
            )
        )

    def test_empty_after_normalisation_passes(self) -> None:
        self.assertIsNone(detect_non_english("   "))
        self.assertIsNone(detect_non_english(""))

    def test_mostly_punctuation_and_numbers_passes(self) -> None:
        self.assertIsNone(detect_non_english("12345 - 67890 !!! ??? ..."))

    def test_ordinary_long_english_reflection_passes(self) -> None:
        self.assertIsNone(
            detect_non_english(
                "I really think chapter 12 was way better written than "
                "chapter 9, honestly, because the pacing felt much tighter."
            )
        )

    def test_single_foreign_word_passes(self) -> None:
        # Fewer than 4 words: the short-message guard applies regardless of
        # what a single word might classify as on its own.
        self.assertIsNone(detect_non_english("Bonjour"))


_FRENCH_PARAGRAPH = (
    "Ceci est un livre magnifique sur la vie et l'amour, je le recommande vivement "
    "a tous mes amis proches qui aiment lire. L'auteur decrit chaque personnage avec "
    "tant de details qu'on a l'impression de les connaitre depuis toujours, et la fin "
    "du roman m'a vraiment bouleverse plus que je ne l'aurais imagine."
)
_MALAY_PARAGRAPH = (
    # This exact wording matters: one ~80-char window of it ("dan penuh emosi
    # ... digambarkan denga(n)") scores well under the detector's confidence
    # floor on its own (top language still Malay, ~0.64 confidence), so this
    # paragraph pins the "unsure middle window" regression at several lengths.
    "Selamat pagi, saya sangat suka membaca buku ini kerana ceritanya sangat menarik "
    "dan penuh emosi bagi setiap pembaca. Watak utama dalam buku ini digambarkan dengan "
    "sangat mendalam sehingga saya berasa seperti mengenali mereka sejak sekian lama, "
    "dan pengakhiran cerita ini benar-benar mengejutkan saya."
)


class TruncationLengthRegressionTests(unittest.TestCase):
    """A single-language paragraph must stay refused at every truncation length.

    Windowing the message past the detector's 80-character limit must not let
    an incidental short trailing fragment (a stray word, a cut-off word, an
    unsure middle window) flip the verdict just because the cut happens to
    land past that boundary. Every length past the first window is checked,
    not a hand-picked sample, since the failure mode is length-dependent.
    """

    def test_refusal_is_stable_across_truncation_lengths(self) -> None:
        for name, paragraph in (("french", _FRENCH_PARAGRAPH), ("malay", _MALAY_PARAGRAPH)):
            whole_refused = detect_non_english(paragraph) is not None
            self.assertTrue(whole_refused, f"{name} paragraph fixture must itself be refused")
            for length in range(81, len(paragraph) + 1):
                with self.subTest(language=name, length=length):
                    truncated = paragraph[:length]
                    refused = detect_non_english(truncated) is not None
                    self.assertEqual(
                        refused,
                        whole_refused,
                        f"{name}[:{length}] refused={refused} but whole paragraph={whole_refused}",
                    )


if __name__ == "__main__":
    unittest.main()
