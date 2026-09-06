"""Exact chapter extraction for the immutable Animal Farm source."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.linger.corpus.book import BookCorpus, CorpusBuildError, ParsedChapter, sha256

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = "data/gutenberg/animal-farm.txt"
DEFAULT_SOURCE = REPO_ROOT / SOURCE_PATH
SOURCE_SHA256 = "c7ff4da710ebe39629c8f9eeb04b4eb8a411e12863df97ae0754f5164f9a2491"
WORK_ID = "pga0100011"
BOOK_VERSION_ID = f"{WORK_ID}-v{SOURCE_SHA256[:8]}"
DEFAULT_OUTPUT = REPO_ROOT / "data/corpus/animal-farm" / BOOK_VERSION_ID
ROMANS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
RANGES = (
    (38, 42, 288), (293, 297, 539), (544, 548, 741), (746, 750, 910),
    (915, 919, 1203), (1208, 1212, 1460), (1465, 1469, 1814),
    (1819, 1823, 2218), (2223, 2227, 2553), (2558, 2562, 2877),
)


@dataclass(frozen=True)
class RoutingMetadata:
    routing_description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    retrieval_cues: tuple[str, ...]


CHAPTERS = (
    RoutingMetadata(
        "Old Major gathers the farm animals in the barn, describes their exploitation "
        "by humans, urges rebellion and unity, and teaches them Beasts of England "
        "before Jones interrupts the singing with gunfire.",
        ("Old Major", "Mr. Jones", "Boxer", "Clover", "Benjamin", "Mollie"),
        ("Manor Farm", "big barn"),
        ("Major's dream", "Are rats comrades", "Beasts of England", "all animals are equal"),
    ),
    RoutingMetadata(
        "After Major's death, the pigs teach Animalism. Hungry animals drive Jones "
        "off the farm, destroy the implements of their captivity, inspect the "
        "farmhouse, and adopt the name Animal Farm and Seven Commandments; the milk disappears.",
        ("Snowball", "Napoleon", "Squealer", "Moses", "Mollie", "Boxer", "Mr. Jones"),
        ("Manor Farm", "Animal Farm", "farmhouse", "Sugarcandy Mountain"),
        ("Rebellion", "Seven Commandments", "Sugarcandy Mountain", "missing milk", "farmhouse museum"),
    ),
    RoutingMetadata(
        "The animals bring in a successful harvest while pigs supervise. Snowball "
        "organises committees and literacy classes, Napoleon takes the puppies away "
        "to educate them, and Squealer justifies reserving milk and apples for pigs.",
        ("Boxer", "Snowball", "Napoleon", "Squealer", "Benjamin", "Mollie", "Jessie", "Bluebell"),
        ("Animal Farm", "harness-room", "orchard", "barn"),
        ("I will work harder", "Four legs good, two legs bad", "milk and apples", "nine puppies", "reading classes"),
    ),
    RoutingMetadata(
        "News of the Rebellion spreads to neighbouring farms. Snowball directs "
        "the successful defence against Jones and his allies in the Battle of the "
        "Cowshed; Boxer fears he has killed a boy, and the animals award medals.",
        ("Snowball", "Boxer", "Mr. Jones", "Mr. Pilkington", "Mr. Frederick", "Mollie"),
        ("Animal Farm", "Foxwood", "Pinchfield", "Willingdon", "cowshed"),
        ("Battle of the Cowshed", "Julius Caesar's campaigns", "Animal Hero, First Class", "stunned stable-lad"),
    ),
    RoutingMetadata(
        "Mollie leaves the farm. During the windmill debate Napoleon's dogs chase "
        "Snowball away, and Napoleon abolishes debates at Sunday meetings. He later "
        "orders the windmill built while Squealer claims it was his plan all along.",
        ("Mollie", "Clover", "Snowball", "Napoleon", "Squealer", "Boxer", "Benjamin"),
        ("Animal Farm", "incubator shed", "big barn", "Willingdon"),
        ("windmill debate", "Snowball expelled", "Napoleon is always right", "three-day week", "Tactics"),
    ),
    RoutingMetadata(
        "The animals haul stone for the windmill and work longer hours. Napoleon "
        "starts trading through Whymper, and the pigs move into farmhouse beds. "
        "After a gale destroys the windmill, Napoleon blames Snowball and orders rebuilding.",
        ("Boxer", "Napoleon", "Squealer", "Mr. Whymper", "Clover", "Muriel", "Benjamin"),
        ("Animal Farm", "quarry", "windmill", "farmhouse"),
        ("sixty-hour week", "voluntary Sunday work", "beds with sheets", "trade with humans", "windmill in ruins"),
    ),
    RoutingMetadata(
        "Food shortages are concealed from Whymper. The hens resist surrendering "
        "their eggs, Snowball is accused of sabotage and treachery, and Napoleon's "
        "dogs execute animals after confessions. Beasts of England is banned.",
        ("Napoleon", "Squealer", "Boxer", "Clover", "Mr. Whymper", "Snowball", "Minimus"),
        ("Animal Farm", "store-shed", "yard", "windmill knoll"),
        ("sand in grain bins", "hens' rebellion", "confessions and executions", "Snowball's secret agents", "Beasts of England abolished"),
    ),
    RoutingMetadata(
        "Napoleon is celebrated in Minimus's poem and sells timber to Frederick "
        "for forged banknotes. Frederick's men blow up the windmill before being "
        "driven off. The pigs discover whisky, and the alcohol commandment gains an exception.",
        ("Napoleon", "Squealer", "Minimus", "Mr. Frederick", "Mr. Pilkington", "Mr. Whymper", "Boxer", "Muriel", "Benjamin"),
        ("Animal Farm", "windmill", "farmhouse", "Foxwood", "Pinchfield"),
        ("WITHOUT CAUSE", "Comrade Napoleon poem", "forged banknotes", "Battle of the Windmill", "TO EXCESS", "broken ladder and paint"),
    ),
    RoutingMetadata(
        "Rations shrink as privileges for pigs grow, and Napoleon becomes President. "
        "Moses returns. Boxer collapses while working and is taken away in a "
        "slaughterer's van; Squealer claims he died in hospital, and the pigs obtain whisky.",
        ("Boxer", "Clover", "Benjamin", "Squealer", "Napoleon", "Moses", "Alfred Simmonds"),
        ("Animal Farm", "quarry", "Boxer's stall", "Willingdon", "Sugarcandy Mountain"),
        ("retirement pension", "Spontaneous Demonstration", "Boxer's collapse", "Horse Slaughterer and Glue Boiler", "memorial banquet"),
    ),
    RoutingMetadata(
        "Years later the farm prospers while ordinary animals remain poor. Pigs "
        "walk on two legs, carry whips, and replace the Commandments with a rule "
        "of unequal equality. At dinner with farmers Napoleon restores the name "
        "Manor Farm, and the watching animals cannot distinguish pigs from men.",
        ("Clover", "Benjamin", "Napoleon", "Squealer", "Mr. Pilkington"),
        ("Animal Farm", "Manor Farm", "farmhouse dining-room", "barn"),
        ("two legs BETTER", "more equal than others", "pigs and men", "ace of spades", "Manor Farm restored"),
    ),
)


def parse_chapters(source: Path = DEFAULT_SOURCE) -> tuple[ParsedChapter, ...]:
    """Validate exact headings, boundaries, and wrappers before extracting bodies."""
    raw = source.read_bytes()
    if sha256(raw) != SOURCE_SHA256:
        raise CorpusBuildError("unexpected Animal Farm source SHA-256")
    lines = raw.decode("ascii").split("\n")
    headings = [(i + 1, line) for i, line in enumerate(lines)
                if re.fullmatch(r"Chapter [IVXLCDM]+", line)]
    expected = [(bounds[0], f"Chapter {roman}")
                for bounds, roman in zip(RANGES, ROMANS, strict=True)]
    if headings != expected:
        raise CorpusBuildError("Animal Farm chapter headings or order changed")
    if (
        len(lines) != 2886
        or [i + 1 for i, line in enumerate(lines) if line == "Project Gutenberg Australia"] != [3, 2884]
        or [i + 1 for i, line in enumerate(lines) if line == "THE END"] != [2881]
        or lines[9] != "eBook No.:  0100011.txt"
        or lines[2876] != "November 1943-February 1944"
        or any(lines[2877:2880]) or any(lines[2881:2883]) or any(lines[2884:])
    ):
        raise CorpusBuildError("Animal Farm wrapper or terminal structure changed")
    parsed = []
    for number, (roman, bounds, routing) in enumerate(zip(ROMANS, RANGES, CHAPTERS, strict=True), 1):
        start, body_start, end = bounds
        next_start = RANGES[number][0] if number < len(RANGES) else 2881
        if (any(lines[start:body_start - 1]) or any(lines[end:next_start - 1])
                or not lines[body_start - 1].strip() or not lines[end - 1].strip()):
            raise CorpusBuildError("Animal Farm chapter boundary changed")
        parsed.append(ParsedChapter(
            number=number, title=f"Chapter {roman}", slug=f"chapter-{roman.lower()}",
            markdown_heading=f"Chapter {roman}",
            routing_description=routing.routing_description, characters=routing.characters,
            locations=routing.locations, retrieval_cues=routing.retrieval_cues,
            source_lines=(start, end), body_lines=(body_start, end),
            body="\n".join(lines[body_start - 1:end]) + "\n",
        ))
    return tuple(parsed)


BOOK = BookCorpus(
    work_id=WORK_ID, book_version_id=BOOK_VERSION_ID, title="Animal Farm",
    author="George Orwell", source_path=SOURCE_PATH, source_sha256=SOURCE_SHA256,
    default_source=DEFAULT_SOURCE, default_output=DEFAULT_OUTPUT, parse_source=parse_chapters,
)
