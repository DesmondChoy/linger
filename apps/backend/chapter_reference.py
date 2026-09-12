"""Whole-message chapter references, e.g. "chapter six" -> 6."""

import re

_MAX_CHAPTER = 999

_CARDINALS = (
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "twenty one", "twenty two", "twenty three",
    "twenty four", "twenty five", "twenty six", "twenty seven", "twenty eight",
    "twenty nine", "thirty",
)

_ORDINALS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
    "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
    "twenty first", "twenty second", "twenty third", "twenty fourth", "twenty fifth",
    "twenty sixth", "twenty seventh", "twenty eighth", "twenty ninth", "thirtieth",
)

_NUMBER_WORDS = {
    word: value
    for words in (_CARDINALS, _ORDINALS)
    for value, word in enumerate(words, start=1)
}

_MAX_DIGITS = len(str(_MAX_CHAPTER))

# The optional chapter token may lead, but nothing else may: any other word means
# the message carries content beyond the reference and is not purely an answer.
# A word reference needs a real separator, so "chapterone" is not a reference.
_ANSWER = re.compile(
    r"^(?:(?:chapters|chapter|chaps|chap|ch)(?:[.\s:#]+|(?=\d)))?"
    r"(?P<reference>\d+(?:st|nd|rd|th)?|[a-z]+(?: [a-z]+)?)"
    r"[.!]*$"
)


def parse_chapter_answer(message: str) -> int | None:
    """Return the chapter when the whole message is only a chapter reference."""
    text = re.sub(r"\s+", " ", message.lower()).strip()
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    match = _ANSWER.match(text)
    if match is None:
        return None
    reference = match.group("reference")
    if reference[0].isdigit():
        digits = reference[:-2] if reference[-1].isalpha() else reference
        if len(digits) > _MAX_DIGITS:
            return None
        chapter = int(digits)
    else:
        chapter = _NUMBER_WORDS.get(reference, 0)
    return chapter if 1 <= chapter <= _MAX_CHAPTER else None
