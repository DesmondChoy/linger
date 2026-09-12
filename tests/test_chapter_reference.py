import unittest

from apps.backend.chapter_reference import parse_chapter_answer


class ChapterAnswerTests(unittest.TestCase):
    def test_bare_numbers_are_chapter_answers(self) -> None:
        for message in ("6", "6.", "6!", " 6 "):
            with self.subTest(message=message):
                self.assertEqual(6, parse_chapter_answer(message))

    def test_number_words_and_ordinals_are_chapter_answers(self) -> None:
        for message, expected in (
            ("six", 6),
            ("Six", 6),
            ("6th", 6),
            ("sixth", 6),
            ("one", 1),
            ("first", 1),
            ("1st", 1),
            ("2nd", 2),
            ("3rd", 3),
            ("twelfth", 12),
            ("twenty-one", 21),
            ("twenty one", 21),
            ("twenty-first", 21),
            ("thirty", 30),
            ("thirtieth", 30),
        ):
            with self.subTest(message=message):
                self.assertEqual(expected, parse_chapter_answer(message))

    def test_chapter_token_with_digits_is_a_chapter_answer(self) -> None:
        for message in (
            "chapter 6",
            "Chapter 6.",
            "ch 6",
            "ch. 6",
            "chap 6",
            "chapter: 6",
            "chapter #6",
            "CHAPTER 6",
            "chapter 6th",
        ):
            with self.subTest(message=message):
                self.assertEqual(6, parse_chapter_answer(message))

    def test_chapter_token_with_a_word_or_ordinal_is_a_chapter_answer(self) -> None:
        for message in ("chapter six", "chap six", "chapter sixth", "ch. six"):
            with self.subTest(message=message):
                self.assertEqual(6, parse_chapter_answer(message))

    def test_digits_are_accepted_up_to_a_sane_cap(self) -> None:
        self.assertEqual(999, parse_chapter_answer("chapter 999"))
        self.assertIsNone(parse_chapter_answer("1000"))
        self.assertIsNone(parse_chapter_answer("chapter 1000"))

    def test_progress_statements_are_not_chapter_answers(self) -> None:
        for message in (
            "I'm at chapter 6",
            "im on chapter 6",
            "I'm at chap six",
            "I'm halfway through chapter 6",
            "just finished chapter 6",
            "I've finished chapter 6",
            "up to chapter 6",
            "finished 6",
        ):
            with self.subTest(message=message):
                self.assertIsNone(parse_chapter_answer(message))

    def test_hedged_references_are_not_chapter_answers(self) -> None:
        for message in ("maybe chapter 6", "chapter 6 i think", "about 6"):
            with self.subTest(message=message):
                self.assertIsNone(parse_chapter_answer(message))

    def test_scene_descriptions_are_not_chapter_answers(self) -> None:
        for message in ("the windmill scene", "I stopped after the windmill scene"):
            with self.subTest(message=message):
                self.assertIsNone(parse_chapter_answer(message))

    def test_empty_incomplete_and_out_of_range_references_are_not_chapter_answers(self) -> None:
        for message in (
            "",
            "   ",
            "chapter",
            "six hundred chapters in",
            "0",
            "-1",
            "chapter 0",
            "zero",
            "chapter -1",
        ):
            with self.subTest(message=message):
                self.assertIsNone(parse_chapter_answer(message))

    def test_questions_are_not_chapter_answers(self) -> None:
        for message in ("6?", "chapter 6?", "which chapter?", "is it chapter six?"):
            with self.subTest(message=message):
                self.assertIsNone(parse_chapter_answer(message))


if __name__ == "__main__":
    unittest.main()
