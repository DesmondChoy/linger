"""Tests for the retrieval-neutral Alice chapter corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.linger.corpus.alice import (
    CHAPTERS,
    DEFAULT_OUTPUT,
    DEFAULT_SOURCE,
    SOURCE_SHA256,
    CorpusBuildError,
    build_catalog,
    check_corpus,
    initialise_corpus,
    parse_chapter_markdown,
    parse_chapters,
    render_initial_corpus,
)


EXPECTED_TITLES = [
    "Down the Rabbit-Hole",
    "The Pool of Tears",
    "A Caucus-Race and a Long Tale",
    "The Rabbit Sends in a Little Bill",
    "Advice from a Caterpillar",
    "Pig and Pepper",
    "A Mad Tea-Party",
    "The Queen’s Croquet-Ground",
    "The Mock Turtle’s Story",
    "The Lobster Quadrille",
    "Who Stole the Tarts?",
    "Alice’s Evidence",
]

EXPECTED_SOURCE_LINES = [
    (58, 272),
    (277, 477),
    (482, 687),
    (692, 951),
    (956, 1250),
    (1255, 1577),
    (1582, 1922),
    (1927, 2230),
    (2235, 2552),
    (2557, 2853),
    (2858, 3115),
    (3120, 3406),
]


def _copy_initial_corpus(destination: Path) -> None:
    initialise_corpus(DEFAULT_SOURCE, destination)


def test_raw_source_is_immutable() -> None:
    assert hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256


def test_parser_extracts_ordered_story_chapters_only() -> None:
    chapters = parse_chapters()

    assert len(chapters) == 12
    assert [chapter.number for chapter in chapters] == list(range(1, 13))
    assert [chapter.title for chapter in chapters] == EXPECTED_TITLES
    assert [chapter.source_lines for chapter in chapters] == EXPECTED_SOURCE_LINES

    combined = "\n".join(chapter.body for chapter in chapters)
    assert "Contents" not in combined
    assert "[Illustration]" not in combined
    assert "PROJECT GUTENBERG" not in combined
    assert "THE END" not in combined


def test_parser_preserves_source_layout_and_codepoints() -> None:
    chapters = parse_chapters()

    assert "    *      *      *      *      *      *" in chapters[0].body
    assert "         “Fury said to a mouse" in chapters[2].body
    assert "_very_" in chapters[0].body
    assert "p\nennyworth" in chapters[9].body
    assert "Beau—ootiful Soo—oop!" in chapters[9].body


def test_initial_render_has_twelve_chapters_and_catalog() -> None:
    artifacts = render_initial_corpus()
    chapter_paths = sorted(path for path in artifacts if path.suffix == ".md")

    assert len(chapter_paths) == 12
    assert list(artifacts)[-1] == Path("catalog.json")
    assert chapter_paths[0] == Path("chapters/01-down-the-rabbit-hole.md")
    assert chapter_paths[-1] == Path("chapters/12-alices-evidence.md")

    metadata, body = parse_chapter_markdown(artifacts[chapter_paths[0]])
    assert metadata.chapter_id == "pg11-ch01"
    assert metadata.routing_description
    assert metadata.characters
    assert metadata.retrieval_cues
    assert body.startswith("# Chapter I: Down the Rabbit-Hole\n\nAlice was")


def test_initialization_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _copy_initial_corpus(first)
    _copy_initial_corpus(second)

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files

    with pytest.raises(CorpusBuildError, match="refusing to overwrite"):
        _copy_initial_corpus(first)


def test_catalog_projection(tmp_path: Path) -> None:
    _copy_initial_corpus(tmp_path)
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))

    assert catalog["chapter_count"] == 12
    assert [chapter["chapter_number"] for chapter in catalog["chapters"]] == list(
        range(1, 13)
    )
    assert all("body_sha256" not in chapter for chapter in catalog["chapters"])
    assert all("source_lines" not in chapter for chapter in catalog["chapters"])
    assert all(chapter["routing_description"] for chapter in catalog["chapters"])


def test_catalog_rebuild_preserves_canonical_chapter(tmp_path: Path) -> None:
    _copy_initial_corpus(tmp_path)
    chapter_path = tmp_path / "chapters/01-down-the-rabbit-hole.md"
    original = chapter_path.read_text(encoding="utf-8")
    metadata, body = parse_chapter_markdown(original)
    revised = metadata.model_copy(
        update={"routing_description": "A revised routing description."}
    )
    encoded = json.dumps(revised.model_dump(mode="json"), ensure_ascii=False, indent=2)
    chapter_path.write_text(
        f"---\n{encoded}\n---\n\n{body}", encoding="utf-8", newline="\n"
    )

    assert "catalog.json is missing or stale" in check_corpus(DEFAULT_SOURCE, tmp_path)
    build_catalog(tmp_path)

    assert check_corpus(DEFAULT_SOURCE, tmp_path) == ()
    assert chapter_path.read_text(encoding="utf-8") != original
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["chapters"][0]["routing_description"] == (
        "A revised routing description."
    )


def test_check_detects_tampered_or_missing_chapters(tmp_path: Path) -> None:
    _copy_initial_corpus(tmp_path)
    chapter_path = tmp_path / "chapters/01-down-the-rabbit-hole.md"
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace(
            "Alice was beginning", "Alice started"
        ),
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "chapters/02-the-pool-of-tears.md").unlink()

    errors = check_corpus(DEFAULT_SOURCE, tmp_path)

    assert "chapters/01-down-the-rabbit-hole.md: body differs from source" in errors
    assert "missing chapter file: chapters/02-the-pool-of-tears.md" in errors


def test_checked_in_corpus_is_current() -> None:
    assert len(CHAPTERS) == 12
    assert check_corpus(DEFAULT_SOURCE, DEFAULT_OUTPUT) == ()
