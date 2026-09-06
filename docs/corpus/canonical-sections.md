# Canonical sections for mixed literary works

The corpus formatter uses schema 2 for works that combine chapters with letters,
prefaces, dedications, or other named divisions. This keeps a preface from
appearing as chapter 1 and preserves repeated chapter numerals in different
parts of a book.

A source adapter selects this format with `BookCorpus(unit_kind="section")`.
The shared `src.linger.corpus.book` commands still initialize the canonical
files, rebuild the catalog from reviewed front matter, and check integrity.
Existing chapter corpora retain schema 1 and their established paths and IDs.

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

Section corpora are formatting artifacts. They are not registered with the
chapter-based Librarian runtime by this change. Runtime support would require
an explicit contract for section identities and request-scoped reading boundaries
before registration. See [book registration](../book-registration.md).

Run the section lifecycle tests with:

```sh
.venv/bin/python -m pytest tests/test_section_corpus.py
```
