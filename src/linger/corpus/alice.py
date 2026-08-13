"""Source-specific adapter for Project Gutenberg ebook 11."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.linger.corpus.book import BookCorpus, CorpusBuildError, ParsedChapter, sha256


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = REPO_ROOT / "data/gutenberg/alice-in-wonderland.txt"
SOURCE_PATH = "data/gutenberg/alice-in-wonderland.txt"
SOURCE_SHA256 = "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e"
WORK_ID = "pg11"
BOOK_VERSION_ID = f"{WORK_ID}-v{SOURCE_SHA256[:8]}"
DEFAULT_OUTPUT = (
    REPO_ROOT / "data/corpus/alice-in-wonderland" / BOOK_VERSION_ID
)
DOCUMENT_TITLE = "Alice's Adventures in Wonderland"
DOCUMENT_AUTHOR = "Lewis Carroll"
START_PREFIX = "*** START OF THE PROJECT GUTENBERG EBOOK"
END_PREFIX = "*** END OF THE PROJECT GUTENBERG EBOOK"
CHAPTER_HEADING = re.compile(r"^CHAPTER ([IVXLCDM]+)\.$")
TOC_ENTRY = re.compile(r"^ CHAPTER ([IVXLCDM]+)\.\s+(.*)$")


@dataclass(frozen=True)
class RoutingMetadata:
    """High-signal metadata used to decide whether to open a chapter."""

    title: str
    slug: str
    routing_description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    retrieval_cues: tuple[str, ...]


CHAPTERS: tuple[RoutingMetadata, ...] = (
    RoutingMetadata(
        title="Down the Rabbit-Hole",
        slug="down-the-rabbit-hole",
        routing_description=(
            "Alice follows a watch-carrying White Rabbit down a deep rabbit-hole "
            "into an underground hall, where a golden key, DRINK ME bottle, and "
            "EAT ME cake repeatedly change her size as she tries to reach a garden."
        ),
        characters=("Alice", "White Rabbit", "Alice's sister", "Dinah"),
        locations=(
            "riverbank",
            "rabbit-hole",
            "deep well",
            "underground hall",
            "garden doorway",
        ),
        retrieval_cues=(
            "waistcoat-pocket watch",
            "orange marmalade jar",
            "do cats eat bats",
            "golden key and glass table",
            "DRINK ME bottle",
            "EAT ME cake",
            "shutting up like a telescope",
        ),
    ),
    RoutingMetadata(
        title="The Pool of Tears",
        slug="the-pool-of-tears",
        routing_description=(
            "Alice grows more than nine feet tall, cries a pool of tears, then "
            "shrinks with the White Rabbit's fan and swims with a Mouse and other "
            "animals while questioning her identity and memory."
        ),
        characters=(
            "Alice",
            "White Rabbit",
            "Mouse",
            "Duck",
            "Dodo",
            "Lory",
            "Eaglet",
            "Dinah",
        ),
        locations=("underground hall", "pool of tears"),
        retrieval_cues=(
            "curiouser and curiouser",
            "nine feet high",
            "white kid gloves and fan",
            "who in the world am I",
            "How doth the little crocodile",
            "swimming in her own tears",
            "O Mouse",
            "cats and dogs offend the Mouse",
        ),
    ),
    RoutingMetadata(
        title="A Caucus-Race and a Long Tale",
        slug="a-caucus-race-and-a-long-tale",
        routing_description=(
            "The soaked animals try to dry themselves with a history lesson and a "
            "chaotic Caucus-race in which everyone wins. The Mouse tells a tail-shaped "
            "tale before Alice frightens the company away by praising Dinah."
        ),
        characters=(
            "Alice",
            "Mouse",
            "Dodo",
            "Lory",
            "Duck",
            "Eaglet",
            "Crab",
            "Magpie",
            "Canary",
        ),
        locations=("shore of the pool of tears",),
        retrieval_cues=(
            "driest thing I know",
            "William the Conqueror",
            "Caucus-race",
            "everybody has won",
            "comfits and thimble prizes",
            "long tale and long tail",
            "Fury as judge and jury",
            "Dinah scares the birds",
        ),
    ),
    RoutingMetadata(
        title="The Rabbit Sends in a Little Bill",
        slug="the-rabbit-sends-in-a-little-bill",
        routing_description=(
            "Mistaken for the White Rabbit's servant Mary Ann, Alice enters his "
            "house and grows until she fills it. After Bill the Lizard is sent down "
            "the chimney, Alice escapes, plays with a giant puppy, and finds a "
            "mushroom topped by a blue Caterpillar."
        ),
        characters=(
            "Alice",
            "White Rabbit",
            "Pat",
            "Bill the Lizard",
            "Puppy",
            "Caterpillar",
        ),
        locations=("White Rabbit's house", "thick wood", "mushroom"),
        retrieval_cues=(
            "Mary Ann",
            "W. RABBIT brass plate",
            "giant Alice trapped in house",
            "Bill down the chimney",
            "pebbles turn into cakes",
            "enormous puppy",
            "blue Caterpillar smoking a hookah",
        ),
    ),
    RoutingMetadata(
        title="Advice from a Caterpillar",
        slug="advice-from-a-caterpillar",
        routing_description=(
            "The Caterpillar questions Alice's identity, tests her memory, and "
            "explains that opposite sides of the mushroom change her size. A "
            "long-necked Alice is then mistaken for a serpent by a Pigeon guarding "
            "its eggs."
        ),
        characters=("Alice", "Caterpillar", "Pigeon"),
        locations=(
            "mushroom in the wood",
            "treetops",
            "Pigeon's nest",
            "woodland clearing",
        ),
        retrieval_cues=(
            "Who are you",
            "keep your temper",
            "You are old Father William",
            "three inches high",
            "mushroom makes Alice taller or shorter",
            "Alice's long neck",
            "Pigeon calls Alice a serpent",
            "eggs",
        ),
    ),
    RoutingMetadata(
        title="Pig and Pepper",
        slug="pig-and-pepper",
        routing_description=(
            "Alice visits the Duchess's pepper-filled kitchen, where the Cook "
            "throws dishes and a sneezing baby turns into a pig. The Cheshire Cat "
            "directs Alice toward the March Hare while appearing and disappearing."
        ),
        characters=(
            "Alice",
            "Fish-Footman",
            "Frog-Footman",
            "Duchess",
            "Cook",
            "Baby",
            "Cheshire Cat",
        ),
        locations=("Duchess's house", "kitchen", "wood", "March Hare's house"),
        retrieval_cues=(
            "invitation to play croquet",
            "too much pepper in the soup",
            "grinning Cheshire Cat",
            "Speak roughly to your little boy",
            "baby turns into a pig",
            "minding their own business",
            "we're all mad here",
            "grin without a cat",
        ),
    ),
    RoutingMetadata(
        title="A Mad Tea-Party",
        slug="a-mad-tea-party",
        routing_description=(
            "Alice joins the Hatter, March Hare, and Dormouse at an endless tea "
            "party filled with riddles, wordplay, a broken watch, and the Dormouse's "
            "treacle-well story. She leaves in disgust and finally enters the garden."
        ),
        characters=("Alice", "Hatter", "March Hare", "Dormouse"),
        locations=(
            "tea table outside the March Hare's house",
            "wood",
            "underground hall",
            "garden",
        ),
        retrieval_cues=(
            "no room",
            "raven and writing-desk",
            "best butter",
            "quarrel with Time",
            "always six o'clock",
            "Twinkle twinkle little bat",
            "treacle-well",
            "memory and muchness",
            "Dormouse in the teapot",
            "Alice enters the garden",
        ),
    ),
    RoutingMetadata(
        title="The Queen’s Croquet-Ground",
        slug="the-queens-croquet-ground",
        routing_description=(
            "Alice meets card gardeners painting white roses red, then joins the "
            "King and Queen of Hearts for a lawless croquet game using flamingoes, "
            "hedgehogs, and soldiers. The Cheshire Cat's bodiless head creates a "
            "dispute over whether it can be beheaded."
        ),
        characters=(
            "Alice",
            "Two",
            "Five",
            "Seven",
            "Queen of Hearts",
            "King of Hearts",
            "White Rabbit",
            "Knave of Hearts",
            "Cheshire Cat",
            "Executioner",
        ),
        locations=("rose garden", "Queen's croquet-ground"),
        retrieval_cues=(
            "painting the roses red",
            "pack of cards",
            "Off with her head",
            "flamingo mallets",
            "hedgehog balls",
            "soldiers as croquet arches",
            "unfair croquet game",
            "beheading the Cheshire Cat's head",
        ),
    ),
    RoutingMetadata(
        title="The Mock Turtle’s Story",
        slug="the-mock-turtles-story",
        routing_description=(
            "The Duchess searches for morals in everything until the Queen drives "
            "her away. The Gryphon then takes Alice to the sorrowful Mock Turtle, "
            "who describes his pun-filled education under the sea."
        ),
        characters=(
            "Alice",
            "Duchess",
            "Queen of Hearts",
            "King of Hearts",
            "Gryphon",
            "Mock Turtle",
        ),
        locations=("croquet-ground", "garden", "Mock Turtle's rocky ledge"),
        retrieval_cues=(
            "everything's got a moral",
            "mustard mine",
            "the more there is of mine",
            "all prisoners pardoned",
            "they never executes nobody",
            "once I was a real Turtle",
            "Tortoise because he taught us",
            "Reeling and Writhing",
            "Ambition Distraction Uglification and Derision",
            "lessons lessen from day to day",
        ),
    ),
    RoutingMetadata(
        title="The Lobster Quadrille",
        slug="the-lobster-quadrille",
        routing_description=(
            "The Mock Turtle and Gryphon demonstrate the Lobster Quadrille, explain "
            "fanciful facts about sea creatures, and make Alice recite altered "
            "poems. Their songs end when they hear that the Knave's trial is beginning."
        ),
        characters=("Alice", "Mock Turtle", "Gryphon"),
        locations=(
            "Mock Turtle's rocky ledge",
            "seashore imagined in the dance",
            "path to trial",
        ),
        retrieval_cues=(
            "Lobster Quadrille",
            "will you join the dance",
            "whiting and snail",
            "boots and shoes done with whiting",
            "soles and eels",
            "porpoise and purpose",
            "Tis the voice of the Lobster",
            "Beautiful Soup",
            "trial's beginning",
        ),
    ),
    RoutingMetadata(
        title="Who Stole the Tarts?",
        slug="who-stole-the-tarts",
        routing_description=(
            "The Knave of Hearts is tried for stealing the Queen's tarts in a "
            "chaotic courtroom overseen by the King. The Hatter and Cook give absurd "
            "evidence while Alice grows larger and is called as the next witness."
        ),
        characters=(
            "Alice",
            "King of Hearts",
            "Queen of Hearts",
            "Knave of Hearts",
            "White Rabbit",
            "Gryphon",
            "Hatter",
            "March Hare",
            "Dormouse",
            "Cook",
            "Bill the Lizard",
        ),
        locations=("royal courtroom",),
        retrieval_cues=(
            "Knave in chains",
            "dish of tarts",
            "jury writing on slates",
            "Queen of Hearts nursery rhyme",
            "Hatter as first witness",
            "teacup and bread-and-butter",
            "guinea-pigs suppressed",
            "tarts made of pepper or treacle",
            "Alice called as witness",
        ),
    ),
    RoutingMetadata(
        title="Alice’s Evidence",
        slug="alices-evidence",
        routing_description=(
            "Alice challenges the court's invented rules and meaningless evidence "
            "as she grows to full size. She rejects sentence before verdict, wakes "
            "on the riverbank, and tells her sister that Wonderland was a dream."
        ),
        characters=(
            "Alice",
            "King of Hearts",
            "Queen of Hearts",
            "Knave of Hearts",
            "White Rabbit",
            "Bill the Lizard",
            "Alice's sister",
        ),
        locations=("royal courtroom", "riverbank"),
        retrieval_cues=(
            "overturned jury-box",
            "Rule Forty-two",
            "more than a mile high",
            "unsigned verses as evidence",
            "begin at the beginning",
            "sentence first verdict afterwards",
            "nothing but a pack of cards",
            "Alice wakes from the dream",
            "sister dreams of Wonderland",
            "happy summer days",
        ),
    ),
)


def _nonempty_before(lines: Sequence[str], boundary: int) -> int:
    index = boundary - 1
    while index >= 0 and not lines[index].strip():
        index -= 1
    return index


def _next_nonempty(lines: Sequence[str], start: int) -> int:
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index == len(lines):
        raise CorpusBuildError("expected non-empty chapter content")
    return index


def parse_chapters(source: Path = DEFAULT_SOURCE) -> tuple[ParsedChapter, ...]:
    """Parse twelve exact chapter bodies and reject source or structure drift."""
    raw = source.read_bytes()
    source_hash = sha256(raw)
    if source_hash != SOURCE_SHA256:
        raise CorpusBuildError(f"unexpected Gutenberg source SHA-256: {source_hash}")

    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    start_markers = [
        index for index, line in enumerate(lines) if line.startswith(START_PREFIX)
    ]
    end_markers = [
        index for index, line in enumerate(lines) if line.startswith(END_PREFIX)
    ]
    if len(start_markers) != 1 or len(end_markers) != 1:
        raise CorpusBuildError("expected one Gutenberg start marker and one end marker")
    start_marker = start_markers[0]
    end_marker = end_markers[0]

    toc_entries = [
        (match.group(1), match.group(2))
        for line in lines[start_marker + 1 : end_marker]
        if (match := TOC_ENTRY.fullmatch(line))
    ]
    expected_toc = [
        (roman, routing.title)
        for roman, routing in zip(
            ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"),
            CHAPTERS,
            strict=True,
        )
    ]
    if toc_entries != expected_toc:
        raise CorpusBuildError("Gutenberg contents no longer matches chapter metadata")

    headings = [
        (index, match.group(1))
        for index, line in enumerate(
            lines[start_marker + 1 : end_marker], start_marker + 1
        )
        if (match := CHAPTER_HEADING.fullmatch(line))
    ]
    if len(headings) != len(CHAPTERS):
        raise CorpusBuildError(f"expected 12 chapter headings, found {len(headings)}")
    if [roman for _, roman in headings] != [roman for roman, _ in expected_toc]:
        raise CorpusBuildError("chapter numerals are missing or out of order")

    story_endings = [
        index
        for index, line in enumerate(
            lines[headings[-1][0] : end_marker], headings[-1][0]
        )
        if line == "THE END"
    ]
    if len(story_endings) != 1:
        raise CorpusBuildError("expected one THE END marker after chapter XII")
    story_end = story_endings[0]

    parsed: list[ParsedChapter] = []
    for chapter_number, ((heading_index, roman), routing) in enumerate(
        zip(headings, CHAPTERS, strict=True),
        start=1,
    ):
        title_index = _next_nonempty(lines, heading_index + 1)
        if lines[title_index] != routing.title:
            raise CorpusBuildError(
                f"chapter {chapter_number} title changed: {lines[title_index]!r}"
            )
        next_boundary = (
            headings[chapter_number][0]
            if chapter_number < len(headings)
            else story_end
        )
        end_index = _nonempty_before(lines, next_boundary)
        body_start = _next_nonempty(lines, title_index + 1)
        body = "\n".join(lines[body_start : end_index + 1]) + "\n"
        parsed.append(
            ParsedChapter(
                number=chapter_number,
                title=routing.title,
                slug=routing.slug,
                markdown_heading=f"Chapter {roman}: {routing.title}",
                routing_description=routing.routing_description,
                characters=routing.characters,
                locations=routing.locations,
                retrieval_cues=routing.retrieval_cues,
                source_lines=(heading_index + 1, end_index + 1),
                body_lines=(body_start + 1, end_index + 1),
                body=body,
            )
        )
    return tuple(parsed)


BOOK = BookCorpus(
    work_id=WORK_ID,
    book_version_id=BOOK_VERSION_ID,
    title=DOCUMENT_TITLE,
    author=DOCUMENT_AUTHOR,
    source_path=SOURCE_PATH,
    source_sha256=SOURCE_SHA256,
    default_source=DEFAULT_SOURCE,
    default_output=DEFAULT_OUTPUT,
    parse_source=parse_chapters,
)
