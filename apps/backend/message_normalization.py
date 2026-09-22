"""Deterministic normalisation of the reader's raw message, applied once at ingestion.

Removes invisible and control characters used to hide instructions from a human
reviewer while a model still reads them, or to split a keyword past a
deterministic detector, without rewriting characters a reader legitimately
typed. NFC keeps combining sequences canonical without also rewriting
compatibility forms (ligatures, full-width, "…") as NFKC would, so a reader's
own words stay their own words for memory-capture's exact-substring quoting.
"""

import unicodedata

# ZWNJ/ZWJ are legitimate inside emoji sequences and inside scripts such as
# Persian, Arabic, and Indic languages, so they are decided by context below
# rather than removed outright.
_CONDITIONAL_JOINERS = frozenset("\u200c\u200d")

# Unicode Default_Ignorable_Code_Point ranges: code points defined to render as
# nothing. Most are already category Cf, but the combining grapheme joiner,
# Hangul fillers, Khmer inherent vowels, the Mongolian and supplementary
# variation selectors, and the reserved default-ignorable blocks are not, and
# each of them splits a word invisibly.
_DEFAULT_IGNORABLE = frozenset(
    code
    for start, end in (
        (0x00AD, 0x00AD),
        (0x034F, 0x034F),
        (0x061C, 0x061C),
        (0x115F, 0x1160),
        (0x17B4, 0x17B5),
        (0x180B, 0x180F),
        (0x200B, 0x200F),
        (0x202A, 0x202E),
        (0x2060, 0x206F),
        (0x3164, 0x3164),
        (0xFE00, 0xFE0F),
        (0xFEFF, 0xFEFF),
        (0xFFA0, 0xFFA0),
        (0xFFF0, 0xFFF8),
        (0x1BCA0, 0x1BCA3),
        (0x1D173, 0x1D17A),
        (0xE0000, 0xE0FFF),
    )
    for code in range(start, end + 1)
)

# Variation selectors 1-16 choose an emoji's text or emoji presentation, so they
# carry meaning a reader can see even though they render as nothing themselves.
_VARIATION_SELECTORS = frozenset(chr(code) for code in range(0xFE00, 0xFE10))

_KEPT_INVISIBLES = _CONDITIONAL_JOINERS | _VARIATION_SELECTORS | frozenset("\t\n")


def _is_removable(char: str) -> bool:
    if char in _KEPT_INVISIBLES:
        return False
    # Cs covers lone surrogates, which are accepted by JSON parsing but raise
    # UnicodeEncodeError once the turn is serialised back out.
    return (
        unicodedata.category(char) in ("Cc", "Cf", "Cs")
        or ord(char) in _DEFAULT_IGNORABLE
    )


def _joins_non_ascii(text: str, start: int, end: int) -> bool:
    """Whether the joiner run text[start:end] sits between two non-ASCII characters."""
    if start == 0 or end == len(text):
        return False
    return ord(text[start - 1]) > 127 and ord(text[end]) > 127


def normalize_reader_message(text: str) -> str:
    """Strip invisible smuggling characters before anything else reads the message."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text if not _is_removable(char))
    kept: list[str] = []
    index = 0
    # Joiners are judged after the other invisibles are gone, so a joiner padded
    # with zero-width spaces cannot borrow their non-ASCII neighbourhood. Whole
    # runs are judged together, which keeps the result stable under re-running.
    while index < len(text):
        if text[index] not in _CONDITIONAL_JOINERS:
            kept.append(text[index])
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] in _CONDITIONAL_JOINERS:
            run_end += 1
        if _joins_non_ascii(text, index, run_end):
            kept.append(text[index:run_end])
        index = run_end
    # NFC last: stripping brings a base character and its combining marks back
    # together, so composing any earlier would leave the result uncomposed.
    return unicodedata.normalize("NFC", "".join(kept))
