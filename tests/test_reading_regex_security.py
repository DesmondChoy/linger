"""Malformed reading declarations cannot consume a request worker indefinitely."""

import json
import subprocess
import sys
import time

import pytest

from apps.backend import chat_turn, reading_progress


@pytest.mark.parametrize("message, expected", [
    ("I am reading Book\tand I have finished chapter 2", "Book"),
    ("I am reading Book\u00a0and I have finished chapter 2", "Book"),
    ("I am reading Book\t,x", "Book"),
    ("I am reading Book\u00a0;x", "Book"),
    ("I am reading Book\n", "Book"),
    ("I am reading Book\t", "Book\t"),
    ("Chapter 3 of   ", None),
])
def test_title_delimiters_preserve_current_whitespace_semantics(message, expected):
    assert chat_turn._declared_title(message, chat_turn.CHAPTER_PATTERN.search(message)) == expected


@pytest.mark.parametrize("message, expected", [
    ("chapter 12", "12"),
    ("ch.\t#\n12!", "12"),
    ("chapter\u00a0:\t3", "3"),
    ("chapter :", None),
    ("chapter #0", None),
])
def test_chapter_separators_preserve_supported_declarations(message, expected):
    for pattern in (chat_turn.CHAPTER_PATTERN, chat_turn.BARE_CHAPTER_ANSWER_PATTERN):
        match = pattern.search(message)
        assert (match.group(1) if match else None) == expected


def test_long_malformed_declarations_complete_without_backtracking_explosion():
    spaces = " " * 50_000
    cases = [
        (chat_turn.CHAPTER_PATTERN, "search", "chapter " + spaces + "x"),
        (chat_turn.BARE_CHAPTER_ANSWER_PATTERN, "fullmatch", "ch " + spaces + "x"),
        (chat_turn.TITLE_PREFIX_PATTERN, "search", "read " + spaces + "a\nb"),
        (chat_turn.TITLE_SUFFIX_PATTERN, "match", " of " + spaces + "a\nb"),
        (chat_turn.TITLE_SUFFIX_SEARCH_PATTERN, "search", "of " + spaces + "a\nb"),
        (chat_turn.TITLE_SCENE_LABEL_PATTERN, "fullmatch", spaces + "x"),
        (chat_turn.TITLE_END_PATTERN, "search", spaces + "x"),
        (chat_turn.DECLARATION_END_PATTERN, "search", spaces + "x"),
    ]
    payload = json.dumps([
        (pattern.pattern, pattern.flags, method, text)
        for pattern, method, text in cases
    ])
    subprocess.run(
        [sys.executable, "-c", (
            "import json, re, sys\n"
            "for pattern, flags, method, text in json.load(sys.stdin):\n"
            "    assert getattr(re.compile(pattern, flags), method)(text) is None\n"
        )],
        input=payload, text=True, capture_output=True, check=True, timeout=5,
    )


@pytest.mark.parametrize("message", [
    "He said “stop” and left",
    "« bonjour » ok",
    "she said 'it's fine' today",
    "‘chapter 9’ was quoted",
    "```\nchapter 9\n```",
    "> chapter 9 quote\nmine: chapter 2",
    'say "chapter 7" lol',
])
def test_mask_quotes_blanks_quoted_text_and_keeps_offsets(message):
    masked = reading_progress.mask_quotes(message)
    assert len(masked) == len(message)
    assert "9" not in masked and "7" not in masked
    assert "stop" not in masked and "bonjour" not in masked and "fine" not in masked


@pytest.mark.parametrize("message", [
    "I'm at chapter 3, don't spoil",
    # An unclosed single quote ends with its line, so the next line is the reader's own.
    "Rock 'n roll fan here.\nI've finished chapter 4 of the twins' story.",
])
def test_mask_quotes_keeps_the_reader_s_own_words(message):
    assert reading_progress.mask_quotes(message) == message


@pytest.mark.parametrize("message, expected", [
    ("> chapter 9 quote\nmine: chapter 2", "                 \nmine: chapter 2"),
    ("He said “stop” and left", "He said        and left"),
])
def test_mask_quotes_blanks_only_the_quote(message, expected):
    assert reading_progress.mask_quotes(message) == expected


def test_unclosed_quotes_complete_without_quadratic_scanning():
    # A backtracking pattern takes several seconds per text here; the scan takes milliseconds.
    texts = ["“" * 50_000, "«" * 50_000, "‘" * 50_000, " ‘a" * 16_000, " 'a" * 16_000]
    started = time.perf_counter()
    for text in texts:
        assert reading_progress.mask_quotes(text) == text
    assert time.perf_counter() - started < 1
