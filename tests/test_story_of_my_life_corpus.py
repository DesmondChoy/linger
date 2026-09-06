"""Integrity and lifecycle checks for Gutenberg 2397's mixed sections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.linger.corpus import story_of_my_life as story
from src.linger.corpus.book import (
    CorpusBuildError,
    WORD,
    build_catalog,
    check_corpus,
    initialise_corpus,
    parse_chapter_markdown,
    render_initial_corpus,
    sha256,
)


def test_source_identity_and_exact_ordered_units() -> None:
    raw = story.DEFAULT_SOURCE.read_bytes()
    assert sha256(raw) == story.SOURCE_SHA256
    assert len(raw) == 761031
    assert not raw.startswith(b'\xef\xbb\xbf')
    assert b'\r' not in raw
    assert raw.count(b'\n') == 13666
    raw.decode('utf-8', errors='strict')
    sections = story.parse_sections()
    assert len(sections) == 140
    assert [s.number for s in sections] == list(range(1, 141))
    assert [s.title for s in sections[:2]] == ['To ALEXANDER GRAHAM BELL', "Editor's Preface"]
    assert [s.title for s in sections[2:25]] == [
        f'CHAPTER {roman}' for roman in
        ('I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI XXII XXIII').split()
    ]
    assert sections[25].title == 'INTRODUCTION'
    assert len(sections[26:135]) == 109
    assert [s.title for s in sections[-5:]] == [
        'CHAPTER I. The Writing of the Book', 'CHAPTER II. PERSONALITY',
        'CHAPTER III. EDUCATION', 'CHAPTER IV. SPEECH', 'CHAPTER V. LITERARY STYLE',
    ]
    assert sections[26].source_lines == sections[26].body_lines == (3658, 3668)
    assert sections[58].source_lines == (4884, 4963)
    assert sections[134].source_lines == (7525, 7548)
    assert sections[-1].body_lines == (11849, 13310)


def test_every_retained_line_is_exact_and_every_prose_line_is_accounted_for() -> None:
    lines = story.DEFAULT_SOURCE.read_text(encoding='utf-8').splitlines()
    sections = story.parse_sections()
    covered: set[int] = set()
    last = 0
    for section in sections:
        start, end = section.source_lines
        assert last < start <= section.body_lines[0] <= end
        assert section.body_lines[1] == end
        assert section.body == '\n'.join(lines[section.body_lines[0] - 1:end]) + '\n'
        covered.update(range(start, end + 1))
        last = end
    nonblank = {n for n in range(47, 13312) if lines[n - 1].strip()}
    excluded = {101, 103, 104, 105, 106, 108, 109, 110, 111, 112, 113,
                118, 3575, 3581, 3656, 7553}
    assert nonblank - covered == excluded
    combined = ''.join(s.body for s in sections)
    assert 'TABLE OF CONTENTS' not in combined
    assert 'PROJECT GUTENBERG' not in combined
    assert '\nTHE END\n' not in combined
    assert 'II. LETTERS(1887-1901)' not in combined
    assert sum(len(WORD.findall(s.body)) for s in sections) == 134963


def test_layout_and_unicode_survive_in_natural_units() -> None:
    sections = story.parse_sections()
    assert 'Frau Gröte' in sections[19].body
    assert 'Mérimée' in sections[22].body
    assert '     Of sunshine and wide air and wingéd things,' in sections[23].body
    assert '  helen write anna george' in sections[26].body
    assert '[No signature]' in sections[26].body
    assert "  DR. BROOKS'S REPLY\n  London, August 3, 1890." in sections[58].body
    assert 'Volapük' in sections[-1].body
    assert 'THE ROSE FAIRIES' in sections[-1].body
    assert 'A FREE TRANSLATION FROM HORACE BOOK II-18.' in sections[-1].body
    assert sha256(sections[26].body) == 'b4f95fe3e184a5502ee762f4defd82cc95431bf823bb31741dd8f8123db775e1'
    assert sha256(sections[-1].body) == 'ac2728d8a485eb9dfc559e1c20c0c78808575620a7b42e41f52e2e006abd3c58'


def test_section_schema_and_stable_filenames() -> None:
    artifacts = render_initial_corpus(story.BOOK)
    assert len(artifacts) == 141
    first = Path('sections/001-dedication.md')
    assert first in artifacts
    assert Path('sections/140-part-iii-chapter-05.md') in artifacts
    metadata, body = parse_chapter_markdown(artifacts[first], unit_kind='section')
    record = metadata.model_dump(mode='json')
    assert record['schema_version'] == 2
    assert record['section_id'] == 'pg2397-vb3cc1e13-sec001'
    assert record['section_number'] == 1
    assert 'chapter_id' not in record and 'chapter_number' not in record
    assert record['word_count'] == 28
    assert body.startswith('# To ALEXANDER GRAHAM BELL\n\n  Who has taught')
    catalog = json.loads(artifacts[Path('catalog.json')])
    assert catalog['section_count'] == 140
    assert [s['section_number'] for s in catalog['sections']] == list(range(1, 141))
    assert all('body_sha256' not in s and 'source_lines' not in s for s in catalog['sections'])


def test_initialization_determinism_and_overwrite_refusal(tmp_path: Path) -> None:
    first, second = tmp_path / 'first', tmp_path / 'second'
    initialise_corpus(story.BOOK, output=first)
    initialise_corpus(story.BOOK, output=second)
    read = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert read(first) == read(second)
    with pytest.raises(CorpusBuildError, match='refusing to overwrite'):
        initialise_corpus(story.BOOK, output=first)


def test_catalog_rebuild_preserves_curated_metadata_and_bodies(tmp_path: Path) -> None:
    initialise_corpus(story.BOOK, output=tmp_path)
    path = tmp_path / 'sections/001-dedication.md'
    metadata, body = parse_chapter_markdown(path.read_text(), unit_kind='section')
    record = metadata.model_dump(mode='json')
    record['routing_description'] = 'The dedication to Alexander Graham Bell.'
    path.write_text('---\n' + json.dumps(record, indent=2) + '\n---\n\n' + body)
    originals = {p: p.read_bytes() for p in (tmp_path / 'sections').glob('*.md')}
    assert 'catalog.json is missing or stale' in check_corpus(story.BOOK, output=tmp_path)
    (tmp_path / 'catalog.json').unlink()
    build_catalog(story.BOOK, output=tmp_path)
    assert check_corpus(story.BOOK, output=tmp_path) == ()
    assert all(p.read_bytes() == original for p, original in originals.items())
    assert json.loads((tmp_path / 'catalog.json').read_text())['sections'][0]['routing_description'] == record['routing_description']


def test_tampered_missing_and_unexpected_artifacts_block_catalog_writes(tmp_path: Path) -> None:
    initialise_corpus(story.BOOK, output=tmp_path)
    path = tmp_path / 'sections/001-dedication.md'
    path.write_text(path.read_text().replace('Who has taught', 'Who taught'))
    (tmp_path / 'sections/002-editors-preface.md').unlink()
    (tmp_path / 'notes.txt').write_text('unexpected')
    previous = (tmp_path / 'catalog.json').read_bytes()
    errors = check_corpus(story.BOOK, output=tmp_path)
    assert any('body differs from source' in e for e in errors)
    assert 'missing section file: sections/002-editors-preface.md' in errors
    assert 'unexpected file: notes.txt' in errors
    with pytest.raises(CorpusBuildError, match='cannot build catalog'):
        build_catalog(story.BOOK, output=tmp_path)
    assert (tmp_path / 'catalog.json').read_bytes() == previous


@pytest.mark.parametrize('old,new', [
    ('CHAPTER I\n', 'CHAPTER ZERO\n'),
    ('II. LETTERS(1887-1901)', 'II. CORRESPONDENCE'),
    ('THE END\n', 'END\n'),
    ('  HELEN KELLER.\n', '\n'),
])
def test_structural_drift_rejected_even_with_updated_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    text = story.DEFAULT_SOURCE.read_text().replace(old, new, 1)
    source = tmp_path / 'changed.txt'
    source.write_text(text)
    monkeypatch.setattr(story, 'SOURCE_SHA256', sha256(source.read_bytes()))
    with pytest.raises(CorpusBuildError, match='changed'):
        story.parse_sections(source)


def test_source_hash_and_strict_decoding_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / 'changed.txt'
    source.write_bytes(story.DEFAULT_SOURCE.read_bytes() + b'changed')
    with pytest.raises(CorpusBuildError, match='SHA-256'):
        story.parse_sections(source)
    source.write_bytes(b'\xff')
    monkeypatch.setattr(story, 'SOURCE_SHA256', sha256(source.read_bytes()))
    with pytest.raises(UnicodeDecodeError):
        story.parse_sections(source)
    with pytest.raises(FileNotFoundError):
        story.parse_sections(tmp_path / 'missing.txt')


def test_checked_in_corpus_is_valid() -> None:
    assert check_corpus(story.BOOK) == ()
