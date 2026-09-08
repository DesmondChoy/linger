"""Mixed literary divisions preserve section identities through the lifecycle."""

import json
from pathlib import Path

import pytest

from src.linger.corpus.book import (
    BookCorpus, CorpusBuildError, ParsedChapter, build_catalog, check_corpus,
    initialise_corpus, parse_chapter_markdown, sha256,
)


@pytest.fixture
def section_book(tmp_path: Path) -> BookCorpus:
    source = tmp_path / 'source.txt'
    source.write_text('Preface\nA preface.\nLetter\nA letter.\n', encoding='utf-8')
    digest = sha256(source.read_bytes())
    version = f'test-chapters-v{digest[:8]}'

    def parse(path: Path) -> tuple[ParsedChapter, ...]:
        lines = path.read_text(encoding='utf-8').splitlines()
        return tuple(
            ParsedChapter(
                number=n, title=lines[start], slug=lines[start].lower(),
                markdown_heading=lines[start], routing_description=lines[start + 1],
                characters=(), locations=(), retrieval_cues=(lines[start],),
                source_lines=(start + 1, start + 2),
                body_lines=(start + 2, start + 2), body=lines[start + 1] + '\n',
            )
            for n, start in enumerate((0, 2), 1)
        )

    return BookCorpus(
        work_id='test-chapters', book_version_id=version, title='Mixed units',
        author='Test', source_path='source.txt', source_sha256=digest,
        default_source=source, default_output=tmp_path / version,
        parse_source=parse, unit_kind='section',
    )


def test_section_schema_round_trip_and_curated_catalog(section_book: BookCorpus) -> None:
    book = section_book
    initialise_corpus(book)
    root = book.default_output
    path = root / 'sections/01-preface.md'
    metadata, body = parse_chapter_markdown(path.read_text(), unit_kind="section")
    fields = metadata.model_dump(mode='json')
    assert fields['schema_version'] == 2
    assert fields['section_id'] == f'{book.book_version_id}-sec01'
    assert fields['section_number'] == 1
    assert 'chapter_id' not in fields and 'chapter_number' not in fields
    assert body == '# Preface\n\nA preface.\n'
    assert check_corpus(book) == ()

    fields['routing_description'] = 'Reviewed preface routing.'
    path.write_text('---\n' + json.dumps(fields) + '\n---\n\n' + body)
    before = {p.name: p.read_bytes() for p in (root / 'sections').glob('*.md')}
    assert check_corpus(book) == ('catalog.json is missing or stale',)
    build_catalog(book)
    assert before == {p.name: p.read_bytes() for p in (root / 'sections').glob('*.md')}
    catalog = json.loads((root / 'catalog.json').read_text())
    assert catalog['section_count'] == 2
    assert catalog['schema_version'] == 2
    assert 'chapters' not in catalog and 'chapter_count' not in catalog
    assert [s['section_number'] for s in catalog['sections']] == [1, 2]
    assert catalog['sections'][0]['routing_description'] == 'Reviewed preface routing.'
    assert catalog['sections'][0]['path'] == 'sections/01-preface.md'
    assert check_corpus(book) == ()
    with pytest.raises(CorpusBuildError, match='refusing to overwrite'):
        initialise_corpus(book)


@pytest.mark.parametrize('mutation', ['chapter_keys', 'schema', 'body', 'missing', 'unexpected'])
def test_section_validation_fails_closed(section_book: BookCorpus, mutation: str) -> None:
    book = section_book
    initialise_corpus(book)
    path = book.default_output / 'sections/01-preface.md'
    original_catalog = (book.default_output / 'catalog.json').read_bytes()
    original = path.read_text()
    if mutation == 'chapter_keys':
        path.write_text(original.replace('section_id', 'chapter_id'))
    elif mutation == 'schema':
        path.write_text(original.replace('"schema_version": 2', '"schema_version": 1'))
    elif mutation == 'body':
        path.write_text(original.replace('\nA preface.\n', '\nChanged.\n'))
    elif mutation == 'missing':
        path.unlink()
    else:
        (book.default_output / 'chapters').mkdir()
    assert check_corpus(book)
    with pytest.raises(CorpusBuildError, match='cannot build catalog'):
        build_catalog(book)
    assert (book.default_output / 'catalog.json').read_bytes() == original_catalog
