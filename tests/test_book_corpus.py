"""Tests for the source-neutral book corpus lifecycle."""

from pathlib import Path

from src.linger.corpus.book import (
    BookCorpus,
    ParsedChapter,
    parse_chapter_markdown,
    render_initial_corpus,
    sha256,
)


def test_shared_lifecycle_uses_book_wide_number_padding(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("A synthetic immutable source.\n", encoding="utf-8")
    source_hash = sha256(source.read_bytes())
    version_id = f"test-book-v{source_hash[:8]}"

    def parse_source(_: Path) -> tuple[ParsedChapter, ...]:
        return tuple(
            ParsedChapter(
                number=number,
                title=f"Part {number}",
                slug=f"part-{number}",
                markdown_heading=f"Part {number}",
                routing_description=f"The events of part {number}.",
                characters=(),
                locations=(),
                retrieval_cues=(f"part {number}",),
                source_lines=(number, number),
                body_lines=(number, number),
                body=f"Text for part {number}.\n",
            )
            for number in range(1, 101)
        )

    book = BookCorpus(
        work_id="test-book",
        book_version_id=version_id,
        title="Synthetic Book",
        author="Test Author",
        source_path="book.txt",
        source_sha256=source_hash,
        default_source=source,
        default_output=tmp_path / version_id,
        parse_source=parse_source,
    )

    artifacts = render_initial_corpus(book)

    first_path = Path("chapters/001-part-1.md")
    last_path = Path("chapters/100-part-100.md")
    assert first_path in artifacts
    assert last_path in artifacts
    first, _ = parse_chapter_markdown(artifacts[first_path])
    assert first.chapter_id == f"{version_id}-ch001"
