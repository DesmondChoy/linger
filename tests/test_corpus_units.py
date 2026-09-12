"""Literary locations do not inherit file ordinals or grant unrelated content."""

from dataclasses import replace
from pathlib import Path
from shutil import copytree
from unittest.mock import patch

import pytest

from src.linger.corpus import alice, douglass, story_of_my_life
from src.linger.corpus.book import CorpusBuildError, parse_chapter_markdown
from src.linger.corpus.registry import CorpusRegistration
from src.linger.corpus.units import load_units, read_unit


def registration(book):
    return CorpusRegistration(book, book.default_output)


def test_douglass_chapters_preserve_real_numbers_without_frontmatter():
    units = load_units(registration(douglass.BOOK))
    chapters = [unit for unit in units if unit.kind == "chapter"]
    assert [unit.chapter_number for unit in chapters] == list(range(1, 12))
    assert chapters[0].chapter_id == "pg23-vd3f08ac3-sec04"
    assert chapters[0].label == "Chapter 1"
    assert [unit.kind for unit in units[:3]] == ["preface", "letter", "biography"]
    assert all(unit.chapter_number is None for unit in units if unit.kind != "chapter")


def test_keller_repeated_numbering_and_letters_have_distinct_locations():
    units = load_units(registration(story_of_my_life.BOOK))
    first = next(unit for unit in units if unit.part_id == "main" and unit.chapter_number == 1)
    supplementary = next(unit for unit in units if unit.part_id == "part-iii" and unit.chapter_number == 1)
    assert first.chapter_id == "pg2397-vb3cc1e13-sec003"
    assert supplementary.chapter_id == "pg2397-vb3cc1e13-sec136"
    assert first.label == "Part I, Chapter 1"
    assert supplementary.label == "Part III, Chapter 1"
    letters = [unit for unit in units if unit.kind == "letter"]
    assert len(letters) == 109
    assert all(unit.chapter_number is None and unit.part_id == "letters" for unit in letters)
    assert letters[0].date == "June 17, 1887"
    assert "Anna" in letters[0].recipient
    assert len({unit.label for unit in letters}) == len(letters)


@pytest.mark.parametrize("book", [alice.BOOK, douglass.BOOK, story_of_my_life.BOOK])
def test_catalog_does_not_open_bodies_and_read_preserves_exact_source(book):
    reg = registration(book)
    opened = []
    original = Path.read_text

    def read(path, *args, **kwargs):
        opened.append(path.name)
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", read):
        units = load_units(reg)
    assert opened == ["catalog.json"]
    unit = next(unit for unit in units if unit.kind == "chapter")
    record, markdown = read_unit(reg, unit)
    canonical_metadata, canonical_body = parse_chapter_markdown(
        (reg.root / unit.path).read_text(), unit_kind=book.unit_kind,
    )
    assert markdown == canonical_body
    assert record.body_sha256 == canonical_metadata.body_sha256
    assert record.body_lines == canonical_metadata.body_lines
    assert record.chapter_id == unit.chapter_id
    assert record.chapter_number == 1


def test_tampered_canonical_body_is_rejected(tmp_path):
    reg = registration(douglass.BOOK)
    copytree(reg.root, tmp_path / "corpus")
    reg = replace(reg, root=tmp_path / "corpus")
    unit = load_units(reg)[3]
    target = reg.root / unit.path
    target.write_text(target.read_text().replace("I was born", "I was raised", 1))
    with pytest.raises(CorpusBuildError, match="checksum"):
        read_unit(reg, unit)


def test_unreviewed_section_corpus_is_not_mislabelled_as_chapters():
    book = replace(douglass.BOOK, unit_locations=())
    with pytest.raises(CorpusBuildError, match="reviewed literary locations"):
        load_units(registration(book))


def test_escaping_catalog_path_is_rejected(tmp_path):
    import json

    reg = registration(douglass.BOOK)
    catalog = json.loads((reg.root / "catalog.json").read_text())
    catalog["sections"][3]["path"] = "../outside.md"
    (tmp_path / "catalog.json").write_text(json.dumps(catalog))
    with pytest.raises(CorpusBuildError, match="path"):
        load_units(replace(reg, root=tmp_path))
