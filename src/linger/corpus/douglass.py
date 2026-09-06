"""Audited mixed-section extraction for Project Gutenberg ebook 23."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.linger.corpus.book import BookCorpus, CorpusBuildError, ParsedChapter, sha256


REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = "data/gutenberg/narrative-of-the-life-of-frederick-douglass.txt"
DEFAULT_SOURCE = REPO_ROOT / SOURCE_PATH
SOURCE_SHA256 = "d3f08ac357d284b0328ccc9b434f2dd7abd71b6037cf49d11cce4c1b098e2534"
WORK_ID = "pg23"
BOOK_VERSION_ID = f"{WORK_ID}-v{SOURCE_SHA256[:8]}"
DEFAULT_OUTPUT = REPO_ROOT / "data/corpus/narrative-of-the-life-of-frederick-douglass" / BOOK_VERSION_ID
START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK NARRATIVE OF THE LIFE OF FREDERICK DOUGLASS, AN AMERICAN SLAVE ***"
END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK NARRATIVE OF THE LIFE OF FREDERICK DOUGLASS, AN AMERICAN SLAVE ***"
HEADING = re.compile(r" (?:PREFACE|LETTER FROM WENDELL PHILLIPS, ESQ\.|FREDERICK DOUGLASS\.|CHAPTER [IVX]+|APPENDIX)|A PARODY")


@dataclass(frozen=True)
class Section:
    title: str
    slug: str
    start: int
    end: int
    description: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    cues: tuple[str, ...]


SECTIONS = (
    Section('PREFACE', 'preface', 81, 373,
        "Garrison recalls Douglass's first antislavery speech at Nantucket, endorses his narrative, and challenges readers to oppose slavery and the laws shielding its violence.",
        ('Frederick Douglass', 'WM. LLOYD GARRISON', 'John A. Collins', 'Charles Lenox Remond', 'Daniel O’Connell'), ('Nantucket', 'New Bedford', 'Massachusetts'),
        ('first speech', 'lecturing agent', 'NO COMPROMISE WITH SLAVERY')),
    Section('LETTER FROM WENDELL PHILLIPS, ESQ.', 'letter-from-wendell-phillips', 378, 486,
        "Phillips praises Douglass's testimony, invokes the fable of the lions writing history, and warns that publishing his identity exposes him to recapture under Northern law.",
        ('Wendell Phillips', 'Frederick Douglass'), ('Boston', 'Massachusetts', 'New England'),
        ('lions write history', 'declaration of freedom', 'hide the outcast')),
    Section('FREDERICK DOUGLASS.', 'frederick-douglass', 491, 515,
        "An editorial biography traces Douglass's life from enslavement and escape through marriage, abolitionist speaking, Civil War recruitment, public appointments, and his death in 1895.",
        ('Frederick Douglass', 'Frederick Augustus Washington Bailey', 'Anna Murray'), ('Baltimore', 'New York City', 'Nantucket', 'Haiti'),
        ('54th and 55th', 'My Bondage And My Freedom', '1895')),
    Section('CHAPTER I', 'chapter-01', 520, 695,
        "Douglass describes his uncertain age and parentage, separation from his mother Harriet Bailey, and witnessing Captain Anthony's brutal whipping of Aunt Hester.",
        ('Frederick Douglass', 'Harriet Bailey', 'Captain Anthony', 'Plummer', 'Aunt Hester', 'Ned Roberts'), ('Tuckahoe', 'Talbot county', 'Maryland'),
        ('mother and I were separated', 'blood-stained gate', 'Aunt Hester')),
    Section('CHAPTER II', 'chapter-02', 700, 883,
        "Douglass describes Colonel Lloyd's plantation, food and clothing allowances, overseers Severe and Hopkins, and the sorrow expressed in songs about the Great House Farm.",
        ('Frederick Douglass', 'Colonel Edward Lloyd', 'Captain Thomas Auld', 'Mr. Severe', 'Mr. Hopkins'), ('Great House Farm', 'Miles River', 'Wye Town', 'New Design', 'Baltimore'),
        ('monthly allowance', 'driver’s horn', 'O, yea!', 'sing most when they are most unhappy')),
    Section('CHAPTER III', 'chapter-03', 888, 1016,
        "Douglass recounts punishments over Lloyd's garden and horses, a man's sale for speaking honestly about his master, and quarrels among enslaved people over their owners' status.",
        ('Frederick Douglass', 'Colonel Lloyd', 'old Barney', 'young Barney', 'Jacob Jepson'), ('Great House Farm', 'garden', 'stable'),
        ('tarring his fence', 'telling the truth', 'still tongue makes a wise head')),
    Section('CHAPTER IV', 'chapter-04', 1021, 1161,
        "Douglass describes Austin Gore's murder of Demby and other killings of enslaved people, showing how barred testimony and unserved warrants let perpetrators escape punishment.",
        ('Frederick Douglass', 'Austin Gore', 'Demby', 'Colonel Lloyd', 'Thomas Lanman', 'Mrs. Hicks', 'Beal Bondly'), ('Great House Farm', 'St. Michael’s', 'Talbot county'),
        ('three calls', 'judicial investigation', 'warrant', 'oysters')),
    Section('CHAPTER V', 'chapter-05', 1166, 1313,
        "Douglass recalls childhood hunger and cold, his joyful preparations to leave the plantation for Baltimore, and the kind welcome from Sophia Auld as he becomes Thomas's caretaker.",
        ('Frederick Douglass', 'Daniel Lloyd', 'Lucretia Auld', 'Hugh Auld', 'Sophia Auld', 'Thomas'), ('Miles River', 'Annapolis', 'Baltimore', 'Fells Point', 'Alliciana Street'),
        ('corn meal', 'bag', 'pair of trousers', 'kind providence')),
    Section('CHAPTER VI', 'chapter-06', 1318, 1424,
        "Mrs. Auld begins teaching Douglass to read until her husband forbids it, revealing literacy's threat to slavery. Douglass contrasts city conditions with the Hamiltons' abuse of Henrietta and Mary.",
        ('Frederick Douglass', 'Mr. Auld', 'Mrs. Auld', 'Thomas Hamilton', 'Mrs. Hamilton', 'Henrietta', 'Mary'), ('Baltimore', 'Philpot Street'),
        ('A, B, C', 'pathway from slavery to freedom', 'pecked')),
    Section('CHAPTER VII', 'chapter-07', 1429, 1629,
        'Douglass trades bread for reading lessons, studies The Columbian Orator, learns the meaning of abolition, and develops escape hopes while teaching himself to write from shipyard marks and copybooks.',
        ('Frederick Douglass', 'Master Hugh', 'Master Thomas', 'Sheridan'), ('Philpot Street', 'Durgin and Bailey’s ship-yard', 'Wilk Street meetinghouse'),
        ('bread of knowledge', 'The Columbian Orator', 'abolitionist', 'lump of chalk', 'Webster’s Spelling Book')),
    Section('CHAPTER VIII', 'chapter-08', 1634, 1802,
        "Douglass returns for an estate valuation among livestock, escapes Andrew's ownership, condemns the abandonment of his grandmother, and is sent from Baltimore to Thomas Auld at St. Michael's.",
        ('Frederick Douglass', 'Captain Anthony', 'Andrew', 'Lucretia', 'Master Hugh', 'Master Thomas', 'Rowena Hamilton'), ('Baltimore', 'St. Michael’s', 'North Point'),
        ('valuation', 'grandmother', 'Gone, gone, sold and gone', 'sloop Amanda')),
    Section('CHAPTER IX', 'chapter-09', 1807, 1975,
        "Douglass describes hunger under Thomas Auld, increased cruelty after Auld's religious conversion, the destruction of a Sabbath school, Henny's abuse, and being hired to Edward Covey for breaking.",
        ('Frederick Douglass', 'Thomas Auld', 'Eliza', 'Priscilla', 'Henny', 'George Cookman', 'Mr. Wilson', 'Edward Covey'), ('St. Michael’s', 'Bay-side', 'Talbot county'),
        ('March, 1832', 'camp-meeting', 'Sabbath school', 'Henny', 'breaking young slaves')),
    Section('CHAPTER X', 'chapter-10', 1980, 3044,
        "Douglass describes Covey's violence and surveillance, his own resistance after seeking protection and receiving Sandy's root, and the confidence restored by their fight. At Freeland's he teaches reading and plans an escape with fellow slaves, but they are arrested. Returned to Baltimore, he survives a shipyard assault, learns calking, and must surrender his wages to Hugh.",
        ('Frederick Douglass', 'Edward Covey', 'Sandy Jenkins', 'Master Thomas', 'William Freeland', 'Henry Harris', 'John Harris', 'Henry Bailey', 'Charles Roberts', 'William Hamilton', 'Master Hugh', 'William Gardner', 'Walter Price'), ("Covey's farm", 'Chesapeake Bay', "St. Michael's", "Freeland's farm", 'Easton jail', 'Baltimore', "Fell's Point", "Gardner's ship-yard"),
        ('unbroken oxen', 'Covey the snake', 'Caroline and forced breeding', "Sandy's protective root", 'fight with Covey', 'Christmas holidays and drunkenness', 'religious slaveholders', 'Sabbath school', 'escape by canoe', 'forged protections', 'Own nothing', 'Easton imprisonment', 'shipyard assault', 'calking wages')),
    Section('CHAPTER XI', 'chapter-11', 3049, 3505,
        "Douglass explains why he withholds escape details, describes hiring his time and reaching New York, and recounts Ruggles's help, marriage to Anna, and settlement in New Bedford. He adopts the name Douglass, finds paid work despite discrimination, reads the Liberator, and begins public antislavery speaking at Nantucket.",
        ('Frederick Douglass', 'Master Hugh', 'Master Thomas', 'David Ruggles', 'Anna Murray', 'J. W. C. Pennington', 'Nathan Johnson', 'William C. Coffin'), ('Baltimore', 'New York', 'New Bedford', 'Nantucket'),
        ('upperground railroad', 'hiring my time', 'September, 1838', 'Trust no man', 'Lady of the Lake', 'Liberator', 'prejudice against color', '11th of August, 1841')),
    Section('APPENDIX', 'appendix', 3509, 3645,
        "Douglass distinguishes the Christianity of Christ from slaveholding religion, condemns churches' complicity in enslavement, quotes a poem and Scripture, and introduces a parody of religious hypocrisy.",
        ('Frederick Douglass', 'Christ', 'Pilate', 'Herod'), ('America',),
        ('slaveholding religion', 'Christianity of Christ', 'whited sepulchres', 'northern Methodist preacher')),
    Section('A PARODY', 'a-parody', 3648, 3740,
        'A satirical poem contrasts professions of heavenly union with whipping, selling, and starving enslaved people. Douglass closes with a renewed antislavery pledge and his April 28, 1845 dateline.',
        ('Frederick Douglass', 'Jack', 'Nell', 'Tony', 'Nanny'), ('Lynn',),
        ('heavenly union', 'children-stealing', 'truth, love, and justice', 'April')),

)


def parse_sections(source: Path = DEFAULT_SOURCE) -> tuple[ParsedChapter, ...]:
    """Preserve all literary units and reject changed bytes or structure."""
    raw = source.read_bytes()
    if sha256(raw) != SOURCE_SHA256:
        raise CorpusBuildError("unexpected Douglass source SHA-256")
    lines = raw.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) != 4100:
        raise CorpusBuildError("Douglass source line count changed")
    for number, marker in ((27, START_MARKER), (3743, "THE END"), (3750, END_MARKER)):
        if lines[number - 1] != marker or lines.count(marker) != 1:
            raise CorpusBuildError(f"Douglass marker changed at line {number}")
    if lines[58] != "Contents" or [line.strip() for line in lines[60:76]] != [s.title for s in SECTIONS]:
        raise CorpusBuildError("Douglass contents changed")
    headings = [(n, line.strip()) for n, line in enumerate(lines, 1) if HEADING.fullmatch(line)]
    if headings != [(s.start, s.title) for s in SECTIONS]:
        raise CorpusBuildError("Douglass section headings changed")
    parsed = []
    for number, section in enumerate(SECTIONS, 1):
        body_start = section.start + 3
        if any(lines[section.start:body_start - 1]) or not lines[body_start - 1].strip():
            raise CorpusBuildError(f"Douglass body start changed for section {number}")
        next_start = SECTIONS[number].start if number < len(SECTIONS) else 3743
        if not lines[section.end - 1].strip() or any(lines[section.end:next_start - 1]):
            raise CorpusBuildError(f"Douglass body end changed for section {number}")
        parsed.append(ParsedChapter(
            number=number,
            title=section.title,
            slug=section.slug,
            markdown_heading=section.title,
            routing_description=section.description,
            characters=section.characters,
            locations=section.locations,
            retrieval_cues=section.cues,
            source_lines=(section.start, section.end),
            body_lines=(body_start, section.end),
            body="\n".join(lines[body_start - 1:section.end]) + "\n",
        ))
    return tuple(parsed)


BOOK = BookCorpus(
    work_id=WORK_ID,
    book_version_id=BOOK_VERSION_ID,
    title="Narrative of the Life of Frederick Douglass, an American Slave",
    author="Frederick Douglass",
    source_path=SOURCE_PATH,
    source_sha256=SOURCE_SHA256,
    default_source=DEFAULT_SOURCE,
    default_output=DEFAULT_OUTPUT,
    parse_source=parse_sections,
    unit_kind="section",
)
