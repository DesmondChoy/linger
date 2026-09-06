# Douglass source audit

The complete edition produces 16 canonical sections and one metadata-only
catalog. The sections preserve the preface, Wendell Phillips's letter, a short
editorial biography, chapters I through XI, the appendix, and A PARODY.
The retained bodies contain 40,822 words under the shared Unicode-aware rule.

## Immutable source

| Property | Value |
| --- | --- |
| Path | `data/gutenberg/narrative-of-the-life-of-frederick-douglass.txt` |
| SHA-256 | `d3f08ac357d284b0328ccc9b434f2dd7abd71b6037cf49d11cce4c1b098e2534` |
| Size | 244,960 bytes |
| Encoding | Strict UTF-8, no BOM |
| Newlines | 4,099 LF characters, no CR characters, final LF present |
| Source identity | Project Gutenberg ebook 23 |
| Title | Narrative of the Life of Frederick Douglass, an American Slave |
| Author | Frederick Douglass |
| Header release date | January 12, 2006 |
| Header update date | July 18, 2026 |
| Version ID | `pg23-vd3f08ac3` |

The supplied file identifies `www.gutenberg.org/ebooks/23` and includes the
Project Gutenberg reuse notice and complete license footer. Formatting retains
the supplied source and its license unchanged. No publication or distribution
is part of this operation.

The earlier source in commit `7f34d01` was truncated at line 3582, ending in
`“Pi`. Its hash was
`04ba1b77673312515cf374a01e828b50233a3274ca1dfef028737fda2c3ba5e5`.
The user repaired the source in commit `38dd451`. A requested fast-forward pull
resolved the blocker before extraction. The earlier bytes remain in Git history.

## Boundaries and exclusions

All ranges below are inclusive and one-based. Source ranges begin at the
original heading and end at the last retained nonblank body line. Body ranges
omit the heading and the two following blank lines. Only separator blank lines
are excluded between sections. Internal blank lines and hard wraps remain exact.

The Gutenberg start marker is unique at line 27. Lines 32 through 56 contain
the title page and an electronic-edition note. The contents occupy lines 59
through 76. Contents entries have two leading spaces and trailing spaces;
actual headings have one leading space, except the unindented A PARODY.
These wrappers and contents do not enter canonical bodies.

| Section | Source lines | Body lines | Words |
| --- | --- | --- | --- |
| PREFACE | 81–373 | 84–373 | 3,160 |
| LETTER FROM WENDELL PHILLIPS, ESQ. | 378–486 | 381–486 | 1,073 |
| FREDERICK DOUGLASS. | 491–515 | 494–515 | 255 |
| CHAPTER I | 520–695 | 523–695 | 2,049 |
| CHAPTER II | 700–883 | 703–883 | 2,013 |
| CHAPTER III | 888–1016 | 891–1016 | 1,455 |
| CHAPTER IV | 1021–1161 | 1024–1161 | 1,575 |
| CHAPTER V | 1166–1313 | 1169–1313 | 1,657 |
| CHAPTER VI | 1318–1424 | 1321–1424 | 1,282 |
| CHAPTER VII | 1429–1629 | 1432–1629 | 2,464 |
| CHAPTER VIII | 1634–1802 | 1637–1802 | 1,804 |
| CHAPTER IX | 1807–1975 | 1810–1975 | 2,035 |
| CHAPTER X | 1980–3044 | 1983–3044 | 12,812 |
| CHAPTER XI | 3049–3505 | 3052–3505 | 5,305 |
| APPENDIX | 3509–3645 | 3512–3645 | 1,399 |
| A PARODY | 3648–3740 | 3651–3740 | 484 |

The appendix introduces A PARODY, which has its own heading and contents entry.
The parody section retains the closing prose pledge, signature, and
`LYNN, _Mass., April_ 28, 1845.` dateline through line 3740. The unindented
signature at line 3737 is not another biographical introduction.
The unique `THE END` at line 3743, Gutenberg end marker at line 3750,
and license footer are excluded. Every nonblank line from the preface through
the closing dateline belongs to a retained source range.

## Preservation and routing

Bodies preserve curly quotes, em dashes, underscore emphasis, footnotes,
verse, indentation, and source spelling. Representative cases include
`Daniel O’Connell`, the Great House Farm song, the grandmother passage's
`Gone, gone, sold and gone` stanza, the marriage certificate and footnotes in
chapter XI, and the complete appendix poems. Apparent source errors such as
`these are they,v` and `baa, dona like goats` remain unchanged.

Each complete body was read before its routing description was drafted.
Descriptions identify what the section says, preserving Douglass's deliberate
withholding of escape mechanics in chapter XI. They do not fill those gaps from
later accounts. Curated routing prose remains reviewable in canonical front
matter. The formatter validates source hashes, boundaries, body fidelity,
identities, and counts; rebuilding a catalog does not regenerate that prose.

This work uses the existing [schema 2 section contract](canonical-sections.md).
Filenames range from `sections/01-preface.md` to `sections/16-a-parody.md`.
Section ordinals record source order, so chapter I is section 4 and retains its
original title. No chapter-runtime registration or retrieval settings are added.

## Verification

`tests/test_douglass_corpus.py` checks every source range, exact bodies, complete
source coverage, representative layout, stable IDs and counts, deterministic
initialization, overwrite refusal, catalog regeneration, stale detection,
source drift, metadata tampering, missing files, and unexpected artifacts.
An independent audit also compared all 16 generated records with separately
calculated titles, ranges, word counts, and body hashes.

```sh
.venv/bin/python -m src.linger.corpus.book src.linger.corpus.douglass check
.venv/bin/python -m pytest tests/test_douglass_corpus.py -q
```
