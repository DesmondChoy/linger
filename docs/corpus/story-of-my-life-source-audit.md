# The Story of My Life source audit

The supplied edition produces 140 natural sections: a dedication, an editor's
preface, 23 autobiographical chapters, an introduction to the letters, 109
letters, and five supplementary chapters. The 141 canonical files include one
metadata-only catalog. The extracted bodies contain 134,963 words under the
shared Unicode-aware `WORD` counting rule.

## Immutable source and provenance

| Property | Value |
| --- | --- |
| Path | `data/gutenberg/the-story-of-my-life.txt` |
| SHA-256 | `b3cc1e13a7bc36510c2b90759956999ba2f836f36d53760ff62d46d2ccd0fe6e` |
| Size | 761,031 bytes |
| Encoding | Strict UTF-8, no BOM |
| Newlines | 13,666 LF characters, no CR characters, final LF present |
| Source identity | Project Gutenberg ebook 2397 |
| Version ID | `pg2397-vb3cc1e13` |
| Author | Helen Keller |
| Contributors named in header | John Albert Macy and Annie Sullivan |
| Header release date | November 1, 2000 |
| Header update date | March 29, 2026 |

The header identifies `www.gutenberg.org/ebooks/2397`. The source carries Project
Gutenberg's US reuse notice and its license footer. That notice directs users
outside the United States to check local laws. This audit makes no worldwide
public-domain claim. The requested operation formats the supplied source
locally; it does not publish or distribute an edition. The source bytes remain
unchanged.

## Exclusions and retained layout

The unique start marker is at line 30 and the unique end marker at line 13,317.
The title page occupies lines 35 through 45. The contents are at lines 101
through 113 and differ from the real headings by indentation and combined
chapter listings. `THE END` is at line 13,312. The title page, contents,
Gutenberg wrappers, license, and terminal marker are excluded from bodies.

The standalone part labels at lines 118, 3,575, 3,581, 3,656, and 7,553 are
excluded. The identical Part II label appears twice in the supplied file.
These labels separate groups and carry no prose. The section paths distinguish
Part I and Part III chapters without altering their source titles.

All other nonblank lines from the dedication through the last literary body
are accounted for by the source ranges below. Internal hard wraps, indentation,
blank lines, punctuation, spelling, emphasis, editorial brackets, ellipses,
poems, and the parallel Frost King stories remain exact. No illustrations or
notes are removed from within those ranges. Representative preserved strings
include `Frau Gröte`, `Mérimée`, `wingéd things`, and `Volapük`.

The supplementary chapters retain embedded reports, dated correspondence,
Sullivan's teaching records, the Frost King documents, literary samples, a
Horace translation, and the closing dream passage within the source's chapter
structure. Those embedded materials do not become invented chapters.

## Section boundaries

Schema 2 uses `section_id`, `section_number`, `section_count`, `sections`, and
`sections/` paths for this mixed work. Source order is consecutive across the
whole edition. Three-digit file prefixes and `secNNN` IDs preserve that order.

All ranges below are inclusive and one-based. Ordinary source ranges begin at
the original heading. Their body ranges exclude the heading and surrounding
blank lines. Letters retain their original heading, date, and any preceding
editorial bridge inside the body, so their source and body ranges are equal.
A bridge introducing multiple letters stays with the first letter it
introduces. This placement preserves order and every word without attributing
Macy's commentary to Helen.

Letter titles preserve the recipient label. Two recipient labels carry bracketed
editorial notes that remain in the body, and one label wraps onto a second
line, joined by a space in the title. Original spacing and line breaks remain
untouched in every letter body. Three separately headed replies and the
Exposition president's access letter are separate sections. The mixed-case
headings `To St. Nicholas` and `To THE GREAT ROUND WORLD` are also real letters.

| Order | Title | Heading line | Source lines | Body lines |
| --- | --- | --- | --- | --- |
| 1 | To ALEXANDER GRAHAM BELL | 47 | 47–52 | 49–52 |
| 2 | Editor's Preface | 57 | 57–96 | 59–96 |
| 3 | CHAPTER I | 122 | 122–259 | 124–259 |
| 4 | CHAPTER II | 263 | 263–464 | 265–464 |
| 5 | CHAPTER III | 468 | 468–551 | 470–551 |
| 6 | CHAPTER IV | 555 | 555–649 | 557–649 |
| 7 | CHAPTER V | 653 | 653–736 | 655–736 |
| 8 | CHAPTER VI | 740 | 740–844 | 742–844 |
| 9 | CHAPTER VII | 848 | 848–1037 | 850–1037 |
| 10 | CHAPTER VIII | 1041 | 1041–1090 | 1043–1090 |
| 11 | CHAPTER IX | 1094 | 1094–1191 | 1096–1191 |
| 12 | CHAPTER X | 1195 | 1195–1254 | 1197–1254 |
| 13 | CHAPTER XI | 1258 | 1258–1388 | 1260–1388 |
| 14 | CHAPTER XII | 1392 | 1392–1461 | 1394–1461 |
| 15 | CHAPTER XIII | 1465 | 1465–1591 | 1467–1591 |
| 16 | CHAPTER XIV | 1595 | 1595–1841 | 1597–1841 |
| 17 | CHAPTER XV | 1845 | 1845–1965 | 1847–1965 |
| 18 | CHAPTER XVI | 1969 | 1969–2019 | 1971–2019 |
| 19 | CHAPTER XVII | 2023 | 2023–2097 | 2025–2097 |
| 20 | CHAPTER XVIII | 2101 | 2101–2267 | 2103–2267 |
| 21 | CHAPTER XIX | 2271 | 2271–2416 | 2273–2416 |
| 22 | CHAPTER XX | 2420 | 2420–2645 | 2422–2645 |
| 23 | CHAPTER XXI | 2649 | 2649–2998 | 2651–2998 |
| 24 | CHAPTER XXII | 3002 | 3002–3333 | 3004–3333 |
| 25 | CHAPTER XXIII | 3337 | 3337–3570 | 3339–3570 |
| 26 | INTRODUCTION | 3586 | 3586–3651 | 3588–3651 |
| 27 | TO HER COUSIN ANNA, MRS. GEORGE T. TURNER | 3662 | 3658–3668 | 3658–3668 |
| 28 | TO MRS. KATE ADAMS KELLER | 3675 | 3671–3691 | 3671–3691 |
| 29 | TO THE BLIND GIRLS AT THE PERKINS INSTITUTION IN SOUTH BOSTON | 3697 | 3694–3713 | 3694–3713 |
| 30 | TO THE BLIND GIRLS AT THE PERKINS INSTITUTION | 3721 | 3716–3739 | 3716–3739 |
| 31 | TO MR. MICHAEL ANAGNOS, DIRECTOR OF THE PERKINS INSTITUTION | 3742 | 3742–3758 | 3742–3758 |
| 32 | TO DR. ALEXANDER GRAHAM BELL | 3761 | 3761–3778 | 3761–3778 |
| 33 | TO MISS SARAH TOMLINSON | 3788 | 3781–3818 | 3781–3818 |
| 34 | TO DR. EDWARD EVERETT HALE | 3829 | 3821–3847 | 3821–3847 |
| 35 | TO MR. MICHAEL ANAGNOS | 3850 | 3850–3891 | 3850–3891 |
| 36 | TO MR. MORRISON HEADY | 3898 | 3894–3928 | 3894–3928 |
| 37 | TO MR. MICHAEL ANAGNOS | 3935 | 3931–3966 | 3931–3966 |
| 38 | TO MISS MARY C. MOORE | 3980 | 3969–4027 | 3969–4027 |
| 39 | TO MRS. KATE ADAMS KELLER | 4035 | 4030–4082 | 4030–4082 |
| 40 | TO MR. MORRISON HEADY | 4089 | 4085–4147 | 4085–4147 |
| 41 | TO MR. MICHAEL ANAGNOS | 4161 | 4150–4197 | 4150–4197 |
| 42 | TO MISS EVELINA H. KELLER | 4200 | 4200–4212 | 4200–4212 |
| 43 | TO MRS. SOPHIA C. HOPKINS | 4215 | 4215–4247 | 4215–4247 |
| 44 | TO MISS DELLA BENNETT | 4250 | 4250–4287 | 4250–4287 |
| 45 | TO DR. EDWARD EVERETT HALE | 4290 | 4290–4334 | 4290–4334 |
| 46 | TO MR. MICHAEL ANAGNOS | 4344 | 4337–4392 | 4337–4392 |
| 47 | TO MISS FANNIE S. MARRETT | 4400 | 4395–4433 | 4395–4433 |
| 48 | TO MISS MARY E. RILEY | 4436 | 4436–4461 | 4436–4461 |
| 49 | TO MISS ANNE MANSFIELD SULLIVAN | 4469 | 4464–4529 | 4464–4529 |
| 50 | TO MISS MILDRED KELLER | 4535 | 4532–4561 | 4532–4561 |
| 51 | TO MR. WILLIAM WADE | 4564 | 4564–4595 | 4564–4595 |
| 52 | TO JOHN GREENLEAF WHITTIER | 4602 | 4598–4628 | 4598–4628 |
| 53 | TO MRS. KATE ADAMS KELLER | 4634 | 4631–4668 | 4631–4668 |
| 54 | TO MRS. KATE ADAMS KELLER | 4671 | 4671–4709 | 4671–4709 |
| 55 | TO DR. EDWARD EVERETT HALE | 4712 | 4712–4734 | 4712–4734 |
| 56 | TO DR. OLIVER WENDELL HOLMES | 4741 | 4737–4780 | 4737–4780 |
| 57 | TO MISS SARAH FULLER | 4783 | 4783–4829 | 4783–4829 |
| 58 | TO  REV. PHILLIPS BROOKS | 4836 | 4832–4881 | 4832–4881 |
| 59 | DR. BROOKS'S REPLY | 4884 | 4884–4963 | 4884–4963 |
| 60 | DR. HOLMES'S REPLY | 4966 | 4966–5010 | 4966–5010 |
| 61 | TO MESSRS. BRADSTREET | 5016 | 5013–5034 | 5013–5034 |
| 62 | TO  MRS. KATE ADAMS KELLER | 5040 | 5037–5098 | 5037–5098 |
| 63 | TO  JOHN GREENLEAF WHITTIER | 5101 | 5101–5136 | 5101–5136 |
| 64 | WHITTIER'S REPLY | 5139 | 5139–5157 | 5139–5157 |
| 65 | TO MR. GEORGE R. KREHL | 5192 | 5160–5225 | 5160–5225 |
| 66 | TO  DR. OLIVER WENDELL HOLMES | 5228 | 5228–5248 | 5228–5248 |
| 67 | TO  SIR JOHN EVERETT MILLAIS | 5251 | 5251–5292 | 5251–5292 |
| 68 | TO  REV. PHILLIPS BROOKS | 5295 | 5295–5313 | 5295–5313 |
| 69 | TO MR. JOHN H. HOLMES | 5326 | 5316–5344 | 5316–5344 |
| 70 | TO DR. OLIVER WENDELL HOLMES | 5347 | 5347–5383 | 5347–5383 |
| 71 | TO REV. PHILLIPS BROOKS | 5386 | 5386–5410 | 5386–5410 |
| 72 | TO  MR. ALBERT H. MUNSELL | 5423 | 5413–5448 | 5413–5448 |
| 73 | To St. Nicholas | 5455 | 5451–5476 | 5451–5476 |
| 74 | TO MISS CAROLINE DERBY | 5485 | 5479–5509 | 5479–5509 |
| 75 | TO  MR. JOHN P. SPAULDING | 5512 | 5512–5535 | 5512–5535 |
| 76 | TO MR. EDWARD H. CLEMENT | 5538 | 5538–5561 | 5538–5561 |
| 77 | TO MISS CAROLINE DERBY | 5567 | 5564–5611 | 5564–5611 |
| 78 | TO  MRS. GROVER CLEVELAND | 5614 | 5614–5630 | 5614–5630 |
| 79 | TO MR. JOHN HITZ | 5636 | 5633–5701 | 5633–5701 |
| 80 | TO MISS CAROLINE DERBY | 5704 | 5704–5726 | 5704–5726 |
| 81 | TO  MRS. KATE ADAMS KELLER | 5740 | 5729–5802 | 5729–5802 |
| 82 | TO THE CHIEFS OF THE DEPARTMENTS AND OFFICERS IN CHARGE OF BUILDINGS AND EXHIBITS | 5812 | 5805–5828 | 5805–5828 |
| 83 | TO MISS CAROLINE DERBY | 5831 | 5831–5873 | 5831–5873 |
| 84 | TO  MRS. CHARLES E. INCHES | 5888 | 5876–5933 | 5876–5933 |
| 85 | TO MISS CAROLINE DERBY | 5936 | 5936–5944 | 5936–5944 |
| 86 | TO  DR. EDWARD EVERETT HALE | 5947 | 5947–5968 | 5947–5968 |
| 87 | TO MISS CAROLINE DERBY | 5985 | 5971–6011 | 5971–6011 |
| 88 | TO  MISS CAROLINE DERBY | 6014 | 6014–6055 | 6014–6055 |
| 89 | TO  MRS. KATE ADAMS KELLER | 6058 | 6058–6092 | 6058–6092 |
| 90 | TO  MRS. LAURENCE HUTTON | 6098 | 6095–6131 | 6095–6131 |
| 91 | TO MRS. WILLIAM THAW | 6134 | 6134–6158 | 6134–6158 |
| 92 | TO MISS CAROLINE DERBY | 6161 | 6161–6188 | 6161–6188 |
| 93 | TO  MRS. GEORGE H. BRADFORD | 6194 | 6191–6206 | 6191–6206 |
| 94 | TO MISS CAROLINE DERBY | 6209 | 6209–6239 | 6209–6239 |
| 95 | TO MISS CAROLINE DERBY | 6242 | 6242–6258 | 6242–6258 |
| 96 | TO MR. JOHN HITZ | 6261 | 6261–6312 | 6261–6312 |
| 97 | TO  CHARLES DUDLEY WARNER | 6315 | 6315–6332 | 6315–6332 |
| 98 | TO  MRS. LAURENCE HUTTON | 6342 | 6335–6363 | 6335–6363 |
| 99 | TO MRS. WILLIAM THAW | 6366 | 6366–6384 | 6366–6384 |
| 100 | TO  MRS. LAURENCE HUTTON | 6387 | 6387–6399 | 6387–6399 |
| 101 | TO MR. JOHN HITZ | 6402 | 6402–6420 | 6402–6420 |
| 102 | TO  MRS. LAURENCE HUTTON | 6431 | 6423–6456 | 6423–6456 |
| 103 | TO  MRS. LAURENCE HUTTON | 6459 | 6459–6470 | 6459–6470 |
| 104 | TO  MRS. LAURENCE HUTTON | 6473 | 6473–6487 | 6473–6487 |
| 105 | TO  CHARLES DUDLEY WARNER | 6490 | 6490–6519 | 6490–6519 |
| 106 | TO MISS CAROLINE DERBY | 6522 | 6522–6536 | 6522–6536 |
| 107 | TO  MRS. LAURENCE HUTTON | 6539 | 6539–6584 | 6539–6584 |
| 108 | TO MRS. WILLIAM THAW | 6587 | 6587–6607 | 6587–6607 |
| 109 | TO MRS. WILLIAM THAW | 6610 | 6610–6624 | 6610–6624 |
| 110 | TO  MRS. LAURENCE HUTTON | 6627 | 6627–6639 | 6627–6639 |
| 111 | TO  MRS. LAURENCE HUTTON | 6642 | 6642–6670 | 6642–6670 |
| 112 | TO MR. JOHN HITZ | 6673 | 6673–6706 | 6673–6706 |
| 113 | TO MR. WILLIAM WADE | 6709 | 6709–6734 | 6709–6734 |
| 114 | TO  MRS. LAURENCE HUTTON | 6737 | 6737–6771 | 6737–6771 |
| 115 | TO DR. DAVID H. GREER | 6774 | 6774–6815 | 6774–6815 |
| 116 | TO  MRS. LAURENCE HUTTON | 6818 | 6818–6827 | 6818–6827 |
| 117 | TO MR. WILLIAM WADE | 6838 | 6830–6868 | 6830–6868 |
| 118 | TO  MRS. LAURENCE HUTTON | 6871 | 6871–6898 | 6871–6898 |
| 119 | TO  MRS. SAMUEL RICHARD FULLER | 6901 | 6901–6931 | 6901–6931 |
| 120 | TO MR. JOHN HITZ | 6934 | 6934–7005 | 6934–7005 |
| 121 | TO MISS MILDRED KELLER | 7008 | 7008–7058 | 7008–7058 |
| 122 | TO  MRS. LAURENCE HUTTON | 7061 | 7061–7079 | 7061–7079 |
| 123 | TO MR. JOHN HITZ | 7082 | 7082–7113 | 7082–7113 |
| 124 | TO THE CHAIRMAN OF THE ACADEMIC BOARD OF RADCLIFFE COLLEGE | 7116 | 7116–7145 | 7116–7145 |
| 125 | TO  MRS. LAURENCE HUTTON | 7148 | 7148–7161 | 7148–7161 |
| 126 | TO MR. JOHN HITZ | 7167 | 7164–7229 | 7164–7229 |
| 127 | TO MR. JOHN D. WRIGHT | 7232 | 7232–7264 | 7232–7264 |
| 128 | TO MR. WILLIAM WADE | 7267 | 7267–7315 | 7267–7315 |
| 129 | TO  MR. CHARLES T. COPELAND | 7318 | 7318–7347 | 7318–7347 |
| 130 | TO  MRS. LAURENCE HUTTON | 7350 | 7350–7385 | 7350–7385 |
| 131 | TO MR. WILLIAM WADE | 7388 | 7388–7403 | 7388–7403 |
| 132 | To THE GREAT ROUND WORLD | 7416 | 7406–7445 | 7406–7445 |
| 133 | TO MISS NINA RHOADES | 7448 | 7448–7475 | 7448–7475 |
| 134 | TO DR. EDWARD EVERETT HALE | 7478 | 7478–7522 | 7478–7522 |
| 135 | TO THE HON. GEORGE FRISBIE HOAR | 7525 | 7525–7548 | 7525–7548 |
| 136 | CHAPTER I. The Writing of the Book | 7557 | 7557–7650 | 7559–7650 |
| 137 | CHAPTER II. PERSONALITY | 7653 | 7653–8096 | 7655–8096 |
| 138 | CHAPTER III. EDUCATION | 8100 | 8100–11491 | 8102–11491 |
| 139 | CHAPTER IV. SPEECH | 11494 | 11494–11844 | 11496–11844 |
| 140 | CHAPTER V. LITERARY STYLE | 11847 | 11847–13310 | 11849–13310 |

## Curation and validation

Routing proposals were written after reading all bodies: one reader handled
Part I, another handled the prefatory material and Part II, and two readers
covered Part III. Proposals were reviewed against the source before canonical
metadata was finalized. Near-exact retrieval cues summarize events without
changing source text. The parser alone owns ranges, identity, and body bytes.
Routine catalog regeneration reads reviewed canonical front matter and does
not repeat semantic curation.

`src.linger.corpus.story_of_my_life` exposes `BOOK` to the shared lifecycle.
Initialization refuses nonempty destinations. Checking validates the immutable
source, audited headings and separators, all canonical bodies and metadata,
expected paths, and catalog freshness. Rebuilding writes only `catalog.json`.

The focused tests check all retained lines against the immutable source and
account for every nonblank literary line with an explicit exclusion set. They
also cover section ordering, schema, IDs, filenames, representative body hashes,
Unicode, layout, deterministic initialization, overwrite refusal, curated
metadata preservation, missing and unexpected artifacts, source drift, strict
decoding, and stale catalog detection.

The source-specific commands are:

```text
.venv/bin/python -m src.linger.corpus.book src.linger.corpus.story_of_my_life check
.venv/bin/python -m pytest tests/test_story_of_my_life_corpus.py -q
```
