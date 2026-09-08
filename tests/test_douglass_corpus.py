"""Source fidelity and canonical lifecycle for the complete Douglass edition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.linger.corpus import douglass
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


EXPECTED_TITLES = [
    'PREFACE', 'LETTER FROM WENDELL PHILLIPS, ESQ.', 'FREDERICK DOUGLASS.',
    'CHAPTER I', 'CHAPTER II', 'CHAPTER III', 'CHAPTER IV', 'CHAPTER V',
    'CHAPTER VI', 'CHAPTER VII', 'CHAPTER VIII', 'CHAPTER IX', 'CHAPTER X',
    'CHAPTER XI', 'APPENDIX', 'A PARODY',
]
EXPECTED_RANGES = [
    (81, 373), (378, 486), (491, 515), (520, 695), (700, 883),
    (888, 1016), (1021, 1161), (1166, 1313), (1318, 1424), (1429, 1629),
    (1634, 1802), (1807, 1975), (1980, 3044), (3049, 3505),
    (3509, 3645), (3648, 3740),
]
EXPECTED_WORD_COUNTS = [
    3160, 1073, 255, 2049, 2013, 1455, 1575, 1657,
    1282, 2464, 1804, 2035, 12812, 5305, 1399, 484,
]


def test_immutable_complete_source_and_all_natural_units() -> None:
    raw = douglass.DEFAULT_SOURCE.read_bytes()
    assert sha256(raw) == douglass.SOURCE_SHA256
    assert len(raw) == 244960
    assert raw.count(b'\n') == 4099
    assert b'\r' not in raw
    assert not raw.startswith(b'\xef\xbb\xbf')
    sections = douglass.parse_sections()
    assert len(sections) == 16
    assert [s.number for s in sections] == list(range(1, 17))
    assert [s.title for s in sections] == EXPECTED_TITLES
    assert [s.source_lines for s in sections] == EXPECTED_RANGES
    assert [s.body_lines for s in sections] == [(start + 3, end) for start, end in EXPECTED_RANGES]
    assert [len(WORD.findall(s.body)) for s in sections] == EXPECTED_WORD_COUNTS
    assert sum(EXPECTED_WORD_COUNTS) == 40822


def test_exact_body_fidelity_and_complete_source_coverage() -> None:
    lines = douglass.DEFAULT_SOURCE.read_text().splitlines()
    covered: set[int] = set()
    last_end = 0
    for section in douglass.parse_sections():
        start, end = section.source_lines
        assert start > last_end
        last_end = end
        covered.update(range(start, end + 1))
        assert section.body == '\n'.join(lines[section.body_lines[0] - 1:end]) + '\n'
    nonblank = {n for n in range(81, 3750) if lines[n - 1].strip()}
    assert nonblank - covered == {3743}
    combined = ''.join(s.body for s in douglass.parse_sections())
    assert 'PROJECT GUTENBERG' not in combined
    assert '\nTHE END\n' not in combined
    assert 'Contents' not in combined
    assert 'Note from the original file' not in combined


def test_poetry_unicode_artifacts_and_closing_signature_preserved() -> None:
    sections = douglass.parse_sections()
    assert 'Daniel O’Connell' in sections[0].body
    assert '_Frederick Douglass_' in sections[0].body
    assert '“I am going away to the Great House Farm!\nO, yea! O, yea! O!”' in sections[4].body
    assert '“Gone, gone, sold and gone\nTo the rice swamp dank and lone,' in sections[10].body
    assert 'these are they,v Who minister' in sections[14].body
    assert '“Pilate and Herod friends!' in sections[14].body
    assert 'They’ll bleat and baa, dona like goats,' in sections[15].body
    assert 'FREDERICK DOUGLASS.\n\n\nLYNN, _Mass., April_ 28, 1845.\n' in sections[15].body
    assert sha256(sections[14].body) == 'f9a1ab77ccbc14891832327dfff62cba921a8899528ea85c39c1a7c7c5b0cfd0'
    assert sha256(sections[15].body) == '9fbbf972980c4581d6c128e4aad17fdc7357387a2d2e514516702a62830304bf'


def test_stable_section_schema_paths_and_catalog_projection() -> None:
    artifacts = render_initial_corpus(douglass.BOOK)
    assert len(artifacts) == 17
    assert list(artifacts)[0] == Path('sections/01-preface.md')
    assert Path('sections/14-chapter-11.md') in artifacts
    assert Path('sections/16-a-parody.md') in artifacts
    metadata, body = parse_chapter_markdown(artifacts[Path('sections/01-preface.md')], unit_kind='section')
    record = metadata.model_dump(mode='json')
    assert record['schema_version'] == 2
    assert record['section_id'] == 'pg23-vd3f08ac3-sec01'
    assert record['section_number'] == 1
    assert record['word_count'] == 3160
    assert 'chapter_number' not in record
    assert body.startswith('# PREFACE\n\nIn the month of August, 1841,')
    catalog = json.loads(artifacts[Path('catalog.json')])
    assert catalog['section_count'] == 16
    assert [s['title'] for s in catalog['sections']] == EXPECTED_TITLES
    assert [s['section_number'] for s in catalog['sections']] == list(range(1, 17))
    assert all('body_sha256' not in s and 'source_lines' not in s for s in catalog['sections'])


def test_deterministic_initialization_and_overwrite_refusal(tmp_path: Path) -> None:
    first, second = tmp_path / 'first', tmp_path / 'second'
    initialise_corpus(douglass.BOOK, output=first)
    initialise_corpus(douglass.BOOK, output=second)
    read = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert read(first) == read(second)
    with pytest.raises(CorpusBuildError, match='refusing to overwrite'):
        initialise_corpus(douglass.BOOK, output=first)


def test_catalog_regeneration_preserves_curated_sections(tmp_path: Path) -> None:
    initialise_corpus(douglass.BOOK, output=tmp_path)
    path = tmp_path / 'sections/16-a-parody.md'
    metadata, body = parse_chapter_markdown(path.read_text(), unit_kind='section')
    record = metadata.model_dump(mode='json')
    record['routing_description'] = 'The parody and Douglass’s closing pledge.'
    path.write_text('---\n' + json.dumps(record, ensure_ascii=False, indent=2) + '\n---\n\n' + body)
    originals = {p: p.read_bytes() for p in (tmp_path / 'sections').glob('*.md')}
    assert 'catalog.json is missing or stale' in check_corpus(douglass.BOOK, output=tmp_path)
    (tmp_path / 'catalog.json').unlink()
    build_catalog(douglass.BOOK, output=tmp_path)
    assert check_corpus(douglass.BOOK, output=tmp_path) == ()
    assert all(p.read_bytes() == content for p, content in originals.items())
    assert json.loads((tmp_path / 'catalog.json').read_text())['sections'][-1]['routing_description'] == record['routing_description']


def test_invalid_sections_block_catalog_writes(tmp_path: Path) -> None:
    initialise_corpus(douglass.BOOK, output=tmp_path)
    path = tmp_path / 'sections/01-preface.md'
    path.write_text(path.read_text().replace('In the month of August', 'In August'))
    (tmp_path / 'sections/02-letter-from-wendell-phillips.md').unlink()
    (tmp_path / 'notes.txt').write_text('unexpected')
    original = (tmp_path / 'catalog.json').read_bytes()
    errors = check_corpus(douglass.BOOK, output=tmp_path)
    assert any('body differs from source' in e for e in errors)
    assert 'missing section file: sections/02-letter-from-wendell-phillips.md' in errors
    assert 'unexpected file: notes.txt' in errors
    with pytest.raises(CorpusBuildError, match='cannot build catalog'):
        build_catalog(douglass.BOOK, output=tmp_path)
    assert (tmp_path / 'catalog.json').read_bytes() == original


@pytest.mark.parametrize('old,new', [
    ('"section_id": "pg23-vd3f08ac3-sec01"', '"section_id": "wrong"'),
    ('"schema_version": 2', '"schema_version": 3'),
])
def test_structural_metadata_tampering_is_rejected(tmp_path: Path, old: str, new: str) -> None:
    initialise_corpus(douglass.BOOK, output=tmp_path)
    path = tmp_path / 'sections/01-preface.md'
    path.write_text(path.read_text().replace(old, new, 1))
    assert check_corpus(douglass.BOOK, output=tmp_path)
    with pytest.raises(CorpusBuildError, match='cannot build catalog'):
        build_catalog(douglass.BOOK, output=tmp_path)


@pytest.mark.parametrize('old,new', [
    ('  CHAPTER I \n', '  CHAPTER ZERO \n'),
    ('\n CHAPTER I\n', '\n CHAPTER ZERO\n'),
    ('\nTHE END\n', '\nEND\n'),
    ('\nA PARODY\n', '\nPARODY\n'),
    ('\n_May_ 1, 1845.\n', '\n\n'),
    ('\n\n\n\n\n CHAPTER I', '\nextra\n\n\n\n CHAPTER I'),
])
def test_structural_drift_fails_even_with_updated_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    original = douglass.DEFAULT_SOURCE.read_text()
    assert old in original
    source = tmp_path / 'changed.txt'
    source.write_text(original.replace(old, new, 1))
    monkeypatch.setattr(douglass, 'SOURCE_SHA256', sha256(source.read_bytes()))
    with pytest.raises(CorpusBuildError, match='changed'):
        douglass.parse_sections(source)


def test_raw_hash_truncation_and_strict_decoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / 'truncated.txt'
    source.write_bytes(douglass.DEFAULT_SOURCE.read_bytes()[:219602])
    with pytest.raises(CorpusBuildError, match='SHA-256'):
        douglass.parse_sections(source)
    monkeypatch.setattr(douglass, 'SOURCE_SHA256', sha256(source.read_bytes()))
    with pytest.raises(CorpusBuildError, match='line count changed'):
        douglass.parse_sections(source)
    source.write_bytes(b'\xff')
    monkeypatch.setattr(douglass, 'SOURCE_SHA256', sha256(source.read_bytes()))
    with pytest.raises(UnicodeDecodeError):
        douglass.parse_sections(source)
    with pytest.raises(FileNotFoundError):
        douglass.parse_sections(tmp_path / 'missing.txt')


def test_only_newline_normalization_is_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = douglass.parse_sections()
    source = tmp_path / 'crlf.txt'
    source.write_bytes(douglass.DEFAULT_SOURCE.read_bytes().replace(b'\n', b'\r\n'))
    monkeypatch.setattr(douglass, 'SOURCE_SHA256', sha256(source.read_bytes()))
    assert douglass.parse_sections(source) == expected


def test_checked_in_corpus_is_current() -> None:
    assert check_corpus(douglass.BOOK) == ()
