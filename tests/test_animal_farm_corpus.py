"""Source fidelity and canonical lifecycle checks for Animal Farm."""

import hashlib
import json
from pathlib import Path

import pytest

from src.linger.corpus import animal_farm as book
from src.linger.corpus.book import (
    CorpusBuildError, build_catalog, check_corpus, initialise_corpus,
    parse_chapter_markdown, render_initial_corpus,
)

BOUNDS = [(38, 42, 288), (293, 297, 539), (544, 548, 741), (746, 750, 910),
          (915, 919, 1203), (1208, 1212, 1460), (1465, 1469, 1814),
          (1819, 1823, 2218), (2223, 2227, 2553), (2558, 2562, 2877)]
TITLES = ["Chapter I", "Chapter II", "Chapter III", "Chapter IV", "Chapter V",
          "Chapter VI", "Chapter VII", "Chapter VIII", "Chapter IX", "Chapter X"]
COUNTS = [2689, 2554, 2289, 1757, 3153, 2839, 3665, 4101, 3661, 3372]


def test_source_and_every_retained_line_are_exact():
    raw = book.DEFAULT_SOURCE.read_bytes()
    assert len(raw) == 169717
    assert raw.isascii() and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    assert hashlib.sha256(raw).hexdigest() == book.SOURCE_SHA256
    lines = raw.decode("ascii").split("\n")
    chapters = book.parse_chapters()
    assert len(chapters) == 10
    assert [c.number for c in chapters] == list(range(1, 11))
    assert [c.title for c in chapters] == TITLES
    for chapter, (start, body_start, end) in zip(chapters, BOUNDS, strict=True):
        assert chapter.source_lines == (start, end)
        assert chapter.body_lines == (body_start, end)
        assert chapter.body == "\n".join(lines[body_start - 1:end]) + "\n"
        assert "Project Gutenberg" not in chapter.body
        assert "THE END" not in chapter.body
    assert chapters[-1].body.endswith("which was which.\n\n\nNovember 1943-February 1944\n")


def test_poetry_commandments_and_source_errors_survive():
    chapters = book.parse_chapters()
    assert "Beasts of England, beasts of Ireland,\nBeasts of every land and clime," in chapters[0].body
    assert "4. No animal shall sleep in a bed.\n5. No animal shall drink alcohol." in chapters[1].body
    assert "make them selves" in chapters[5].body
    assert "sniffs, ad exclaim" in chapters[6].body
    assert "Friend of fatherless!\nFountain of happiness!" in chapters[7].body
    assert "tatted wall" in chapters[9].body
    assert "ALL ANIMALS ARE EQUAL\nBUT SOME ANIMALS ARE MORE EQUAL THAN OTHERS" in chapters[9].body


def test_metadata_ids_counts_and_hashes():
    artifacts = render_initial_corpus(book.BOOK)
    assert len(artifacts) == 11
    paths = [p for p in artifacts if p.suffix == ".md"]
    assert paths[0] == Path("chapters/01-chapter-i.md")
    assert paths[-1] == Path("chapters/10-chapter-x.md")
    for n, (path, chapter) in enumerate(zip(paths, book.parse_chapters(), strict=True), 1):
        metadata, body = parse_chapter_markdown(artifacts[path])
        assert metadata.chapter_id == f"pga0100011-vc7ff4da7-ch{n:02}"
        assert metadata.word_count == COUNTS[n - 1]
        assert metadata.body_sha256 == hashlib.sha256(chapter.body.encode()).hexdigest()
        assert metadata.source_path == "data/gutenberg/animal-farm.txt"
        assert metadata.title == TITLES[n - 1]
        assert body == f"# {chapter.title}\n\n{chapter.body}"


def test_initialization_and_catalog_preserve_curated_metadata(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    initialise_corpus(book.BOOK, output=first)
    initialise_corpus(book.BOOK, output=second)
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    with pytest.raises(CorpusBuildError, match="refusing to overwrite"):
        initialise_corpus(book.BOOK, output=first)
    chapter = first / "chapters/01-chapter-i.md"
    metadata, body = parse_chapter_markdown(chapter.read_text())
    revised = metadata.model_dump(mode="json")
    revised["routing_description"] = "Old Major teaches Beasts of England."
    chapter.write_text("---\n" + json.dumps(revised, indent=2) + "\n---\n\n" + body)
    preserved = {p: p.read_bytes() for p in (first / "chapters").iterdir()}
    assert "catalog.json is missing or stale" in check_corpus(book.BOOK, output=first)
    (first / "catalog.json").unlink()
    build_catalog(book.BOOK, output=first)
    assert check_corpus(book.BOOK, output=first) == ()
    assert all(p.read_bytes() == value for p, value in preserved.items())
    catalog = json.loads((first / "catalog.json").read_text())
    assert catalog["chapter_count"] == 10
    assert [c["chapter_number"] for c in catalog["chapters"]] == list(range(1, 11))
    assert catalog["chapters"][0]["routing_description"] == revised["routing_description"]
    assert all(not ({"body", "source_lines", "body_sha256"} & c.keys()) for c in catalog["chapters"])


@pytest.mark.parametrize("old,new", [(b"Chapter II\n", b"Chapter XI\n"),
                                      (b"THE END\n", b"THE FINISH\n"),
                                      (b"\n\n\nMr. Jones", b"\nX\n\nMr. Jones")])
def test_source_drift_rejected_even_with_updated_hash(tmp_path, monkeypatch, old, new):
    source = tmp_path / "source.txt"
    modified = book.DEFAULT_SOURCE.read_bytes().replace(old, new, 1)
    source.write_bytes(modified)
    with pytest.raises(CorpusBuildError, match="SHA-256"):
        book.parse_chapters(source)
    monkeypatch.setattr(book, "SOURCE_SHA256", hashlib.sha256(modified).hexdigest())
    with pytest.raises(CorpusBuildError, match="changed"):
        book.parse_chapters(source)


@pytest.mark.parametrize("damage", ["body", "id", "missing", "unexpected"])
def test_invalid_corpus_blocks_catalog_writes(tmp_path, damage):
    initialise_corpus(book.BOOK, output=tmp_path)
    chapter = tmp_path / "chapters/01-chapter-i.md"
    catalog = (tmp_path / "catalog.json").read_bytes()
    if damage == "body":
        chapter.write_text(chapter.read_text().replace("Mr. Jones, of", "Mr. Jones from", 1))
    elif damage == "id":
        chapter.write_text(chapter.read_text().replace("vc7ff4da7-ch01", "vc7ff4da7-ch99", 1))
    elif damage == "missing":
        chapter.unlink()
    else:
        (tmp_path / "chapters/extra.md").write_text("unexpected")
    assert check_corpus(book.BOOK, output=tmp_path)
    with pytest.raises(CorpusBuildError, match="cannot build catalog"):
        build_catalog(book.BOOK, output=tmp_path)
    assert (tmp_path / "catalog.json").read_bytes() == catalog


def test_checked_in_corpus():
    assert check_corpus(book.BOOK) == ()
