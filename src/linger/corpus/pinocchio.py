"""Exact extraction of Project Gutenberg ebook 500, Della Chiesa translation."""

from __future__ import annotations

import re
from pathlib import Path

from src.linger.corpus.book import BookCorpus, CorpusBuildError, ParsedChapter, sha256

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = "data/gutenberg/the-adventures-of-pinocchio.txt"
DEFAULT_SOURCE = REPO_ROOT / SOURCE_PATH
SOURCE_SHA256 = "6bdc173408a95ee683f0013e8a098fac66965af34bbcb9c52cfe632d23f76ff9"
WORK_ID = "pg500"
BOOK_VERSION_ID = f"{WORK_ID}-v{SOURCE_SHA256[:8]}"
DEFAULT_OUTPUT = REPO_ROOT / "data/corpus/the-adventures-of-pinocchio" / BOOK_VERSION_ID
START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK THE ADVENTURES OF PINOCCHIO ***"
END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK THE ADVENTURES OF PINOCCHIO ***"

# Inclusive heading, narrative start, narrative end positions in immutable source.
BOUNDARIES = (
    (57, 63, 142),
    (147, 154, 278),
    (283, 289, 424),
    (429, 436, 523),
    (528, 534, 598),
    (603, 609, 663),
    (668, 673, 782),
    (787, 793, 886),
    (891, 897, 988),
    (993, 1000, 1078),
    (1083, 1089, 1197),
    (1202, 1208, 1382),
    (1387, 1392, 1512),
    (1517, 1523, 1625),
    (1630, 1636, 1723),
    (1728, 1735, 1849),
    (1854, 1861, 2060),
    (2065, 2071, 2238),
    (2243, 2249, 2359),
    (2364, 2370, 2448),
    (2453, 2459, 2540),
    (2545, 2551, 2668),
    (2673, 2680, 2854),
    (2859, 2865, 3070),
    (3075, 3081, 3204),
    (3209, 3215, 3313),
    (3318, 3324, 3554),
    (3559, 3564, 3735),
    (3740, 3747, 4017),
    (4022, 4028, 4255),
    (4260, 4266, 4483),
    (4488, 4494, 4731),
    (4736, 4743, 5006),
    (5011, 5018, 5261),
    (5266, 5272, 5440),
    (5445, 5450, 5864),
)

TITLES = (
    'How it happened that Mastro Cherry, carpenter, found a piece of wood that wept and laughed like a child.',
    'Mastro Cherry gives the piece of wood to his friend Geppetto, who takes it to make himself a Marionette that will dance, fence, and turn somersaults.',
    'As soon as he gets home, Geppetto fashions the Marionette and calls it Pinocchio. The first pranks  of the Marionette.',
    'The story of Pinocchio and the Talking Cricket, in which one sees that bad children do not like to be corrected by those who know more than they do.',
    'Pinocchio is hungry and looks for an egg to cook himself an omelet; but, to his surprise, the omelet flies out of the window.',
    'Pinocchio falls asleep with his feet on a foot warmer, and awakens the next day with his feet all burned off.',
    'Geppetto returns home and gives his own breakfast to the Marionette',
    'Geppetto makes Pinocchio a new pair of feet, and sells his coat to buy him an A-B-C book.',
    'Pinocchio sells his A-B-C book to pay his way into the Marionette Theater.',
    'The Marionettes recognize their brother Pinocchio, and greet him with loud cheers; but the Director, Fire Eater, happens along and poor Pinocchio almost loses his life.',
    'Fire Eater sneezes and forgives Pinocchio, who saves his friend, Harlequin, from death.',
    'Fire Eater gives Pinocchio five gold pieces for his father, Geppetto; but the Marionette meets a Fox and a Cat and follows them.',
    'The Inn of the Red Lobster',
    'Pinocchio, not having listened to the good advice of the Talking Cricket, falls into the hands of the Assassins.',
    'The Assassins chase Pinocchio, catch him, and hang him to the branch of a giant oak tree.',
    'The Lovely Maiden with Azure Hair sends for the poor Marionette, puts him to bed, and calls three Doctors to tell her if Pinocchio is dead or alive.',
    'Pinocchio eats sugar, but refuses to take medicine. When the undertakers come for him, he drinks the medicine and feels better. Afterwards he tells a lie and, in punishment, his nose grows longer and longer.',
    'Pinocchio finds the Fox and the Cat again, and goes with them to sow the gold pieces in the Field of Wonders.',
    'Pinocchio is robbed of his gold pieces and, in punishment, is sentenced to four months in prison.',
    'Freed from prison, Pinocchio sets out to return to the Fairy; but on the way he meets a Serpent and later is caught in a trap.',
    'Pinocchio is caught by a Farmer, who uses him as a watchdog for his chicken coop.',
    'Pinocchio discovers the thieves and, as a reward for faithfulness, he regains his liberty.',
    'Pinocchio weeps upon learning that the Lovely Maiden with Azure Hair is dead. He meets a Pigeon, who carries him to the seashore. He throws himself into the sea to go to the aid of his father.',
    'Pinocchio reaches the Island of the Busy Bees and finds the Fairy once more.',
    'Pinocchio promises the Fairy to be good and to study, as he is growing tired of being a Marionette, and wishes to become a real boy.',
    'Pinocchio goes to the seashore with his friends to see the Terrible Shark.',
    'The great battle between Pinocchio and his playmates. One is wounded. Pinocchio is arrested.',
    'Pinocchio runs the danger of being fried in a pan like a fish',
    'Pinocchio returns to the Fairy’s house and she promises him that, on the morrow, he will cease to be a Marionette and become a boy. A wonderful party of coffee-and-milk to celebrate the great event.',
    'Pinocchio, instead of becoming a boy, runs away to the Land of Toys with his friend, Lamp-Wick.',
    'After five months of play, Pinocchio wakes up one fine morning and finds a great surprise awaiting him.',
    'Pinocchio’s ears become like those of a Donkey. In a little while he changes into a real Donkey and begins to bray.',
    'Pinocchio, having become a Donkey, is bought by the owner of a Circus, who wants to teach him to do tricks. The Donkey becomes lame and is sold to a man who wants to use his skin for a drumhead.',
    'Pinocchio is thrown into the sea, eaten by fishes, and becomes a Marionette once more. As he swims to land, he is swallowed by the Terrible Shark.',
    'In the Shark’s body Pinocchio finds whom? Read this chapter, my children, and you will know.',
    'Pinocchio finally ceases to be a Marionette and becomes a boy',
)

# Description, named characters, setting, and discriminating cues, in source order.
ROUTING = (
    ("Mastro Cherry tries to cut a log that cries and laughs, frightening him into a faint.", ("Mastro Cherry", "Mastro Antonio"), "carpenter’s shop", ("talking firewood", "hatchet and plane")),
    ("A talking log provokes fights between Mastro Cherry and Geppetto before Geppetto takes it home to make a performing Marionette.", ("Mastro Cherry", "Geppetto", "Polendina"), "carpenter’s shop", ("yellow wig", "Cornmeal mush", "dancing Marionette")),
    ("Geppetto carves and names Pinocchio, who steals his wig and runs away; a Carabineer arrests Geppetto after the crowd intervenes.", ("Geppetto", "Pinocchio"), "Geppetto’s house and street", ("painted fireplace", "growing nose", "Carabineer")),
    ("Pinocchio rejects the Talking Cricket’s advice about obedience, study and work, then kills him with a hammer.", ("Pinocchio", "Talking Cricket"), "Geppetto’s house", ("wooden head", "hammer", "cri-cri-cri")),
    ("Hungry Pinocchio searches for food and tries to cook an egg, but a live Chick emerges and flies away.", ("Pinocchio", "Chick"), "Geppetto’s house", ("painted pot", "omelet", "empty eggshell")),
    ("An old man drenches the hungry Pinocchio with water; back home, his feet burn away while he sleeps beside the stove.", ("Pinocchio", "Geppetto"), "village and Geppetto’s house", ("thunderstorm", "ice-cold water", "burned feet")),
    ("Geppetto climbs through the window to reach the footless Pinocchio and gives him three pears, including their skins and cores.", ("Geppetto", "Pinocchio"), "Geppetto’s house", ("breakfast pears", "pear cores", "fussy eating")),
    ("Geppetto makes new feet and simple clothes for Pinocchio, then sells his coat to buy an A-B-C book.", ("Geppetto", "Pinocchio"), "Geppetto’s house", ("glued feet", "flowered paper suit", "coat sold for schoolbook")),
    ("Music draws Pinocchio away from school; he sells his A-B-C book to a ragpicker for four pennies to enter the theater.", ("Pinocchio",), "village square", ("pipes and drums", "four pennies", "Marionette Theater")),
    ("The Marionettes welcome Pinocchio and interrupt their performance; Fire Eater orders him brought to the kitchen as firewood.", ("Pinocchio", "Harlequin", "Pulcinella", "Signora Rosaura", "Fire Eater"), "Marionette Theater", ("wooden brothers", "roast lamb", "black beard")),
    ("Fire Eater spares Pinocchio but threatens Harlequin; Pinocchio offers himself in his friend’s place and wins both their pardons.", ("Pinocchio", "Harlequin", "Fire Eater"), "Marionette Theater", ("compassionate sneezing", "your Excellency", "sacrifice for Harlequin")),
    ("Fire Eater gives Pinocchio five gold pieces for Geppetto; a Fox and Cat lure him with promises of multiplying money in the Field of Wonders.", ("Pinocchio", "Fire Eater", "Fox", "Cat", "Blackbird"), "road from the theater", ("five gold pieces", "Cat eats Blackbird", "money tree")),
    ("The Fox and Cat leave Pinocchio to pay their inn bill; setting out alone at midnight, he ignores the Talking Cricket’s ghost warning of swindlers and Assassins.", ("Pinocchio", "Fox", "Cat", "Talking Cricket"), "Inn of the Red Lobster", ("lavish supper", "midnight departure", "ghost’s warning")),
    ("Two masked Assassins chase Pinocchio for the coins under his tongue; he bites off a cat’s paw and escapes a burning pine tree and muddy pool.", ("Pinocchio", "Assassins"), "forest road", ("black sacks", "coins under tongue", "severed cat’s paw")),
    ("A maiden with azure hair refuses Pinocchio shelter; the Assassins catch him, fail to stab his wooden body, and hang him from an oak.", ("Pinocchio", "Assassins", "Lovely Maiden with Azure Hair"), "white cottage and giant oak", ("closed window", "broken knives", "hanging")),
    ("The Fairy sends a Falcon and Medoro to rescue Pinocchio; a Crow, Owl and Talking Cricket debate whether he is alive until he weeps.", ("Pinocchio", "Fairy", "Falcon", "Medoro", "Crow", "Owl", "Talking Cricket"), "Fairy’s house", ("glass coach", "three doctors", "dead weep")),
    ("Black Rabbits with a coffin persuade Pinocchio to take his medicine; lies about the gold pieces make his nose too long to pass through the door.", ("Pinocchio", "Fairy", "Rabbits"), "Fairy’s bedroom", ("bitter medicine", "sugar", "lies with long noses")),
    ("Woodpeckers shorten Pinocchio’s nose, but on his way to meet Geppetto he follows the Fox and Cat and buries four coins in the Field of Wonders.", ("Pinocchio", "Fairy", "Fox", "Cat"), "City of Simple Simons and Field of Wonders", ("thousand woodpeckers", "paw in a sling", "buried gold")),
    ("A Parrot reveals that the Fox and Cat stole the buried gold; a Gorilla judge imprisons Pinocchio, who gains release by calling himself a thief.", ("Pinocchio", "Parrot", "Fox", "Cat", "Gorilla"), "Field of Wonders and courthouse", ("four months in prison", "robbery victim punished", "emperor’s amnesty")),
    ("Returning toward the Fairy, Pinocchio meets a smoking-tailed Serpent that dies laughing, then is trapped while trying to take grapes.", ("Pinocchio", "Serpent"), "muddy road and vineyard", ("smoking tail", "head in mud", "weasel trap")),
    ("A Glowworm rebukes the trapped Pinocchio for stealing grapes; the Farmer chains him in place of his dead watchdog Melampo.", ("Pinocchio", "Glowworm", "Melampo"), "Farmer’s chicken coop", ("dog collar", "iron chain", "doghouse")),
    ("Pinocchio refuses the Weasels’ bribe, traps them in the henhouse and earns his freedom, keeping the dead Melampo’s collusion secret.", ("Pinocchio", "Weasels", "Melampo"), "Farmer’s chicken coop", ("one chicken bribe", "barking alarm", "freedom for honesty")),
    ("Pinocchio mourns at the Fairy’s tombstone; a Pigeon carries him to the coast, where he dives after Geppetto’s sinking boat.", ("Pinocchio", "Fairy", "Pigeon", "Geppetto"), "Fairy’s former home and seashore", ("marble epitaph", "chick-peas", "father’s boat")),
    ("Washed onto an island, Pinocchio hears a Dolphin’s warning about the Shark, refuses work, then carries a woman’s water and recognizes the Fairy.", ("Pinocchio", "Dolphin", "Fairy"), "Island of the Busy Bees", ("water jugs", "cauliflower", "azure hair")),
    ("The grown Fairy becomes Pinocchio’s mother and promises he can become a boy if he obeys, studies and works.", ("Pinocchio", "Fairy"), "Fairy’s house", ("Marionettes never grow", "never too late to learn", "promise to study")),
    ("Pinocchio wins respect at school and studies well, but classmates tempt him to skip lessons to see a supposed Shark at the shore.", ("Pinocchio", "Fairy"), "school and road to the seashore", ("schoolboy teasing", "bad companions", "race to the Shark")),
    ("Classmates fight Pinocchio with schoolbooks and wound Eugene; the Carabineers arrest Pinocchio, who escapes while retrieving his cap.", ("Pinocchio", "Eugene", "Crab"), "seashore and village road", ("arithmetic textbook", "injured schoolmate", "Mastiff pursuit")),
    ("Pinocchio rescues the pursuing Alidoro from drowning, then a Green Fisherman catches him in a net and prepares to fry him as a fish.", ("Pinocchio", "Alidoro", "Green Fisherman"), "sea and fisherman’s cave", ("Mastiff rescue", "Marionette fish", "flour and hot oil")),
    ("Alidoro rescues Pinocchio from the frying pan; after a long wait for the Snail and another forgiveness, Pinocchio excels at school and the Fairy plans his transformation party.", ("Pinocchio", "Alidoro", "Eugene", "Snail", "Fairy"), "fisherman’s cave and Fairy’s house", ("hops bag clothes", "foot through door", "chalk bread", "coffee-and-milk party")),
    ("While delivering party invitations, Pinocchio finds Lamp-Wick waiting for the Land of Toys wagon and stays past his promised return time, tempted by endless holidays.", ("Pinocchio", "Fairy", "Lamp-Wick", "Romeo"), "beside a farmer’s wagon", ("six Saturdays", "no schools", "midnight wagon")),
    ("Pinocchio joins Lamp-Wick in the wagon, hears a donkey’s warning and watches the driver bite its ears; in the Land of Toys they spend five months playing.", ("Pinocchio", "Lamp-Wick", "Little Man"), "wagon and Land of Toys", ("donkeys in boys’ shoes", "weeping donkey", "DOWN WITH ARITHMETIC")),
    ("A Dormouse diagnoses Pinocchio’s growing ears as donkey fever; he and Lamp-Wick hide their ears, laugh at each other, then turn into donkeys.", ("Pinocchio", "Dormouse", "Lamp-Wick", "Little Man"), "Land of Toys", ("cotton bags", "donkey ears", "braying")),
    ("Sold to a circus, the donkey Pinocchio is trained by beatings, sees the Fairy in the audience and becomes lame; a buyer throws him into the sea for his skin.", ("Pinocchio", "Lamp-Wick", "Little Man", "Fairy"), "marketplace and circus", ("STAR OF THE DANCE", "jumping rings", "drumhead")),
    ("Fish eat away Pinocchio’s donkey covering and restore his wooden form; he escapes his buyer but is swallowed by the Shark while swimming toward an azure Goat.", ("Pinocchio", "Fairy", "Goat", "Shark", "Tunny"), "sea and Shark’s stomach", ("donkey skin eaten", "Attila of the Sea", "faint light")),
    ("Inside the Shark, Pinocchio reunites with Geppetto, who survived on a swallowed ship’s supplies; after a failed attempt, he carries his father out through the sleeping Shark’s mouth.", ("Pinocchio", "Geppetto", "Shark", "Tunny"), "Shark’s body", ("last candle", "two years inside Shark", "escape past teeth")),
    ("The Tunny brings father and son ashore; Pinocchio cares for Geppetto, sees Lamp-Wick die, works and studies, and gives his savings to the Fairy before waking as a real boy.", ("Pinocchio", "Geppetto", "Tunny", "Fox", "Cat", "Talking Cricket", "Farmer John", "Lamp-Wick", "Snail", "Fairy"), "shore, straw cottage and Farmer John’s farm", ("milk for father", "reed baskets", "fifty pennies", "real boy")),
)


def parse_chapters(source: Path = DEFAULT_SOURCE) -> tuple[ParsedChapter, ...]:
    """Extract exact chapter slices, rejecting changed bytes or audited structure."""
    raw = source.read_bytes()
    if sha256(raw) != SOURCE_SHA256:
        raise CorpusBuildError("unexpected Pinocchio source SHA-256")
    lines = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if [i + 1 for i, line in enumerate(lines) if line == START_MARKER] != [29]:
        raise CorpusBuildError("Pinocchio start marker changed")
    if [i + 1 for i, line in enumerate(lines) if line == END_MARKER] != [5875]:
        raise CorpusBuildError("Pinocchio end marker changed")
    headings = [(i + 1, line) for i, line in enumerate(lines) if re.fullmatch(r"CHAPTER \d+", line)]
    expected = [(bounds[0], f"CHAPTER {n}") for n, bounds in enumerate(BOUNDARIES, 1)]
    if headings != expected:
        raise CorpusBuildError("Pinocchio chapter headings changed")
    parsed = []
    for n, ((start, body_start, end), title, routing) in enumerate(
        zip(BOUNDARIES, TITLES, ROUTING, strict=True), 1
    ):
        title_end = start + 1
        while lines[title_end]:
            title_end += 1
        if " ".join(lines[start + 1:title_end]) != title:
            raise CorpusBuildError(f"Pinocchio chapter {n} title changed")
        boundary = BOUNDARIES[n][0] - 1 if n < 36 else 5874
        if (
            lines[start] != ""
            or any(lines[title_end:body_start - 1])
            or not lines[body_start - 1]
            or not lines[end - 1]
            or any(lines[end:boundary])
        ):
            raise CorpusBuildError(f"Pinocchio chapter {n} boundaries changed")
        description, characters, location, cues = routing
        parsed.append(ParsedChapter(
            number=n, title=title, slug=f"chapter-{n:02d}",
            markdown_heading=f"Chapter {n}: {title}",
            routing_description=description, characters=characters,
            locations=(location,), retrieval_cues=cues,
            source_lines=(start, end), body_lines=(body_start, end),
            body="\n".join(lines[body_start - 1:end]) + "\n",
        ))
    return tuple(parsed)


BOOK = BookCorpus(
    work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
    title="The Adventures of Pinocchio", author="Carlo Collodi",
    source_path=SOURCE_PATH, source_sha256=SOURCE_SHA256,
    default_source=DEFAULT_SOURCE, default_output=DEFAULT_OUTPUT,
    parse_source=parse_chapters,
)
