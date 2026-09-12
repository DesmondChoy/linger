# Canonical sections for mixed literary works

The corpus formatter uses schema 2 for works that combine chapters with letters,
prefaces, dedications, or other named divisions. This keeps a preface from
appearing as chapter 1 and preserves repeated chapter numerals in different
parts of a book.

A source adapter selects this format with `BookCorpus(unit_kind="section")`.
The shared `src.linger.corpus.book` commands still initialize the canonical
files, rebuild the catalog from reviewed front matter, and check integrity.
Chapter corpora use schema 1 with chapter paths and IDs.

## File contract

Schema 2 uses the schema 1 provenance, body, title, and routing fields, with
these changes:

| Schema 1 | Schema 2 |
| --- | --- |
| `schema_version: 1` | `schema_version: 2` |
| `chapter_id` ending in `-chNN` | `section_id` ending in `-secNN` |
| `chapter_number` | `section_number` |
| `chapters/NN-slug.md` | `sections/NN-slug.md` |
| Catalog `chapter_count` | Catalog `section_count` |
| Catalog `chapters` | Catalog `sections` |

Section numbers record consecutive source order, including prefatory material.
They do not replace the original chapter numeral in the title. Files and IDs
use at least two digits, or three when the corpus contains at least 100 sections.
Titles and rendered headings retain the source division's name.

`source_lines` and `body_lines` remain inclusive, one-based source coordinates.
An adapter may retain a letter's original heading inside its body when an
editorial introduction precedes that heading. In that case, both ranges cover
the complete retained section. Each source audit records that choice and its
exact boundaries. Only line endings are normalized in bodies. Interior spacing,
indentation, notes, and verse remain intact.

The catalog contains routing metadata and relative section paths. It contains
no source bodies or retrieval settings. Catalog regeneration does not rewrite
canonical section files or regenerate routing prose.

## Validation and runtime scope

The checker rejects schema 1 keys in schema 2 front matter, source changes,
body changes, incorrect ranges or IDs, missing sections, unexpected artifacts,
and stale catalogs. A corpus cannot be initialized over existing files.

Section corpora are formatting artifacts outside the chapter-based Librarian
runtime. Registration requires an explicit runtime contract for section
identities and request-scoped reading boundaries. Alice, Animal Farm, and
Pinocchio use schema 1 and are registered and enabled by default for Librarian
and Reader. See [book registration](../book-registration.md).

## Adapters and source audits

The shared command loads a source-specific `BOOK` from one of these modules:

| Adapter | Format | Source audit |
| --- | --- | --- |
| `src.linger.corpus.alice` | Chapter schema 1 | Source ranges and routing metadata in `src/linger/corpus/alice.py` |
| `src.linger.corpus.animal_farm` | Chapter schema 1 | [Animal Farm](animal-farm-source-audit.md) |
| `src.linger.corpus.pinocchio` | Chapter schema 1 | [Pinocchio](pinocchio-source-audit.md) |
| `src.linger.corpus.douglass` | Section schema 2 | [Frederick Douglass](douglass-source-audit.md) |
| `src.linger.corpus.story_of_my_life` | Section schema 2 | [The Story of My Life](story-of-my-life-source-audit.md) |

The audits record source boundaries, retained material, and source-specific
preservation decisions. Adapter defaults point to the immutable text under
`data/gutenberg/` and its versioned directory under `data/corpus/`.

## Commands

```sh
uv run python -m src.linger.corpus.book ADAPTER COMMAND [--source PATH] [--output PATH]
```

| Argument | Meaning |
| --- | --- |
| `ADAPTER` | Importable module from the table above |
| `init` | Render canonical files and build the catalogue in an empty destination |
| `build-catalog` | Rebuild `catalog.json` from reviewed canonical front matter |
| `check` | Verify source integrity, canonical content, metadata, file inventory, and catalogue consistency |
| `--source PATH` | Override the adapter's source path; the adapter's integrity checks still apply |
| `--output PATH` | Override the corpus directory for the selected command |

For example, check Douglass or rebuild its derived catalogue:

```sh
uv run python -m src.linger.corpus.book src.linger.corpus.douglass check
uv run python -m src.linger.corpus.book src.linger.corpus.douglass build-catalog
```

To render a separate copy, choose an empty output directory:

```sh
uv run python -m src.linger.corpus.book src.linger.corpus.story_of_my_life init \
	--output /tmp/linger-story-of-my-life
```

Successful commands return `0`, canonical-artifact check findings return `1`,
and source, adapter, build, or file errors return `2`.

Run the section lifecycle tests with:

```sh
uv run pytest tests/test_section_corpus.py tests/test_section_runtime_boundary.py
```
