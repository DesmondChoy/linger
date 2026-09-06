"""Integrity and lifecycle checks for the immutable Pinocchio edition."""

import hashlib
import json
from pathlib import Path

import pytest

from src.linger.corpus import pinocchio
from src.linger.corpus.book import (
    CorpusBuildError, build_catalog, check_corpus, initialise_corpus,
    parse_chapter_markdown, render_initial_corpus, WORD,
)

EXPECTED_BOUNDARIES = (
    (57, 63, 142), (147, 154, 278), (283, 289, 424), (429, 436, 523),
    (528, 534, 598), (603, 609, 663), (668, 673, 782), (787, 793, 886),
    (891, 897, 988), (993, 1000, 1078), (1083, 1089, 1197),
    (1202, 1208, 1382), (1387, 1392, 1512), (1517, 1523, 1625),
    (1630, 1636, 1723), (1728, 1735, 1849), (1854, 1861, 2060),
    (2065, 2071, 2238), (2243, 2249, 2359), (2364, 2370, 2448),
    (2453, 2459, 2540), (2545, 2551, 2668), (2673, 2680, 2854),
    (2859, 2865, 3070), (3075, 3081, 3204), (3209, 3215, 3313),
    (3318, 3324, 3554), (3559, 3564, 3735), (3740, 3747, 4017),
    (4022, 4028, 4255), (4260, 4266, 4483), (4488, 4494, 4731),
    (4736, 4743, 5006), (5011, 5018, 5261), (5266, 5272, 5440),
    (5445, 5450, 5864),
)


def test_source_bytes_ranges_titles_and_exact_bodies():
    raw = pinocchio.DEFAULT_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pinocchio.SOURCE_SHA256
    assert not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw
    lines = raw.decode('utf-8').split('\n')
    chapters = pinocchio.parse_chapters()
    assert len(chapters) == 36
    for n, (chapter, (start, body, end)) in enumerate(zip(chapters, EXPECTED_BOUNDARIES, strict=True), 1):
        assert chapter.number == n
        assert chapter.source_lines == (start, end)
        assert chapter.body_lines == (body, end)
        assert chapter.title == ' '.join(line for line in lines[start:body-1] if line)
        assert chapter.body == '\n'.join(lines[body-1:end]) + '\n'
    combined = ''.join(chapter.body for chapter in chapters)
    for excluded in ('PROJECT GUTENBERG', 'Produced by Charles Keller', 'gutchecked twice', 'CHAPTER 1\n'):
        assert excluded not in combined
    assert 'pranks  of' in chapters[2].title
    assert '     * Cornmeal mush\n' in chapters[1].body
    assert '     * A military policeman\n' in chapters[2].body
    assert '     HERE LIES\n     THE LOVELY FAIRY WITH AZURE HAIR' in chapters[22].body
    assert '     First Public Appearance\n\n     of the\n' in chapters[32].body
    assert '     fifty pennies to her dear Pinocchio\n' in chapters[35].body
    assert '\n asked Pinocchio,' in chapters[23].body
    assert 'a Crow, and Owl' in chapters[15].body
    assert 'ugly Gab' in chapters[26].body


def test_stable_render_identity_hashes_and_counts():
    artifacts = render_initial_corpus(pinocchio.BOOK)
    assert len(artifacts) == 37
    chapters = pinocchio.parse_chapters()
    for n, chapter in enumerate(chapters, 1):
        path = Path(f'chapters/{n:02d}-chapter-{n:02d}.md')
        meta, body = parse_chapter_markdown(artifacts[path])
        assert meta.chapter_id == f'pg500-v6bdc1734-ch{n:02d}'
        assert meta.body_sha256 == hashlib.sha256(chapter.body.encode()).hexdigest()
        assert meta.word_count == len(WORD.findall(chapter.body))
        assert body == f'# {chapter.markdown_heading}\n\n{chapter.body}'
    assert len(WORD.findall('café Pinocchio’s A-B-C _word_ 42')) == 5


def test_determinism_overwrite_and_catalog_curation(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    for output in (first, second):
        initialise_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, output)
    snapshot = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert snapshot(first) == snapshot(second)
    with pytest.raises(CorpusBuildError, match='refusing to overwrite'):
        initialise_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, first)
    chapter = first / 'chapters/01-chapter-01.md'
    text = chapter.read_text()
    meta, _ = parse_chapter_markdown(text)
    chapter.write_text(text.replace(meta.routing_description, 'A carpenter discovers a talking log.'))
    assert 'catalog.json is missing or stale' in check_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, first)
    before = chapter.read_bytes()
    build_catalog(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, first)
    assert chapter.read_bytes() == before
    assert check_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, first) == ()
    catalog = json.loads((first / 'catalog.json').read_text())
    assert catalog['chapter_count'] == 36
    assert [c['chapter_number'] for c in catalog['chapters']] == list(range(1, 37))
    assert catalog['chapters'][0]['routing_description'] == 'A carpenter discovers a talking log.'
    assert all('body_sha256' not in c and 'source_lines' not in c for c in catalog['chapters'])


@pytest.mark.parametrize('old,new,error', [
    ('CHAPTER 2\n', 'CHAPTER 9\n', 'headings'),
    ('The Inn of the Red Lobster\n', 'The Inn of the Blue Lobster\n', 'title'),
    (pinocchio.START_MARKER, 'START', 'start marker'),
    (pinocchio.END_MARKER, 'END', 'end marker'),
    ('\n\n\n\nCHAPTER 2', '\nextra\n\n\nCHAPTER 2', 'boundaries'),
])
def test_raw_and_independent_structural_drift(tmp_path, monkeypatch, old, new, error):
    path = tmp_path / 'changed.txt'
    path.write_text(pinocchio.DEFAULT_SOURCE.read_text().replace(old, new, 1))
    with pytest.raises(CorpusBuildError, match='SHA-256'):
        pinocchio.parse_chapters(path)
    monkeypatch.setattr(pinocchio, 'SOURCE_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(CorpusBuildError, match=error):
        pinocchio.parse_chapters(path)


def test_tampered_missing_unexpected_and_stale_artifacts(tmp_path):
    initialise_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, tmp_path)
    one = tmp_path / 'chapters/01-chapter-01.md'
    one.write_text(one.read_text().replace('Centuries ago', 'Years ago'))
    (tmp_path / 'chapters/02-chapter-02.md').unlink()
    (tmp_path / 'extra.txt').write_text('extra')
    (tmp_path / 'catalog.json').write_text('{}')
    errors = check_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, tmp_path)
    assert any('body differs' in e for e in errors)
    assert any('missing chapter' in e for e in errors)
    assert 'unexpected file: extra.txt' in errors
    with pytest.raises(CorpusBuildError):
        build_catalog(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, tmp_path)


def test_checked_in_corpus():
    assert check_corpus(pinocchio.BOOK, pinocchio.DEFAULT_SOURCE, pinocchio.DEFAULT_OUTPUT) == ()
