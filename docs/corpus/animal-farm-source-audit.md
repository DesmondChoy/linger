# Animal Farm source audit

The immutable source is `data/gutenberg/animal-farm.txt`, eBook 0100011,
first posted August 2001 and updated March 2008 according to its header.
It contains 169,717 bytes, all ASCII (also valid UTF-8), no BOM, and 2,885 LF
line endings. There are no CR bytes. Its SHA-256 is
`c7ff4da710ebe39629c8f9eeb04b4eb8a411e12863df97ae0754f5164f9a2491`.

The source header identifies George Orwell and gives his dates as 1903–1950.
The [Orwell Foundation biography](https://www.orwellfoundation.com/the-orwell-foundation/orwell/biography/)
confirms his death on 21 January 1950.
[IPOS's copyright duration reference, pages 13–14](https://www.ipos.gov.sg/docs/default-source/resources-library/copyright/copyright-101-infopack.pdf)
gives the general term for identified literary authors as life plus 70 years.
This supports local formatting in Singapore in 2026: that term has elapsed.
This conclusion concerns local use, not worldwide publication.

The [source distributor's licence](https://gutenberg.net.au/licence.html),
checked on 5 September 2026, permits reuse subject to national copyright law.
For modified editions it requires removal of its header and proprietary
introductory material. Canonical chapters omit those wrappers and contain no
distributor branding. The original download remains unchanged as provenance.

## Source boundaries

All ranges below are inclusive, one-based source line numbers. Each source range
starts at the original heading and ends at the last retained nonempty line.
Each body range excludes the heading and the blank lines immediately after it.
Interchapter separator blank lines are excluded. Internal blank lines and hard
wraps remain exact. Every body ends with one LF.

| Source title | Source range | Body range |
| --- | --- | --- |
| Chapter I | 38–288 | 42–288 |
| Chapter II | 293–539 | 297–539 |
| Chapter III | 544–741 | 548–741 |
| Chapter IV | 746–910 | 750–910 |
| Chapter V | 915–1203 | 919–1203 |
| Chapter VI | 1208–1460 | 1212–1460 |
| Chapter VII | 1465–1814 | 1469–1814 |
| Chapter VIII | 1819–2218 | 1823–2218 |
| Chapter IX | 2223–2553 | 2227–2553 |
| Chapter X | 2558–2877 | 2562–2877 |

There is no contents page, repeated chapter heading, preface, appendix, footnote,
illustration, or running header. Lines 1–37 contain title and licence wrappers.
The source distributor's exact name occurs only at lines 3 and 2884.
The sole `THE END` marker is at line 2881 and is excluded.
The author's composition dateline, `November 1943-February 1944` at line 2877,
is retained with Chapter X, including the blank lines separating it from the
last narrative paragraph. It is authored closing material, not a wrapper.

## Preservation and routing

The source uses ASCII quotation marks, uppercase emphasis, and double hyphens.
There are no non-ASCII code points to normalize. Songs and poems retain their
short lines and stanza breaks. The Seven Commandments retain their numbered
layout. Source anomalies remain unchanged, including `make them selves`,
`sniffs, ad exclaim`, and `tatted wall`.

The ten bodies were read before writing routing descriptions. Each description
summarizes its own chapter. Reported accusations are described as accusations,
not as independently established events. Routing metadata is an initial,
reviewable proposal; subsequent edits belong in canonical front matter.
No runtime semantic generator was invoked or changed.

`src.linger.corpus.animal_farm` supplies the source-specific adapter to the shared
corpus lifecycle. The identity is `pga0100011-vc7ff4da7`; filenames run from
`chapters/01-chapter-i.md` to `chapters/10-chapter-x.md`. The shared Unicode-aware
word rule counts letter or digit runs with internal apostrophes and hyphens,
excluding underscores. This ASCII edition contains 30,080 words, including
the final dateline.

The verification command is
`python -m src.linger.corpus.book src.linger.corpus.animal_farm check`.
`tests/test_animal_farm_corpus.py` verifies boundaries, exact bodies, layout,
structural drift rejection, canonical immutability, and catalog regeneration.
