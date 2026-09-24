# Provenance repair and source mapping design

The roses replay exposed two different failures: an invalid finding quoted text
outside its named field in the revised candidate, and a passing review missed
undeclared memory use and a claim mapped to the wrong available book record.

The implementation keeps one reusable Provenance agent and its existing
candidate-review run. A PydanticAI capability validates each candidate-review
output against that run's current typed input. Invalid finding locations,
incomplete prior-finding resolutions, or inconsistent audits raise `ModelRetry`
inside the existing two-output-retry budget. Repair feedback reports all detected
input-bound defects together, with field paths, offending values and exact
current targets. It requires inspecting the current candidate and never instructs the model to
change a substantive verdict to pass. Exhaustion remains an error, and the
application's final review/release validation remains in place.

Two compact output fields make the semantic checks explicit. `source_audit`
contains one entry per available canonical book or connection source, identified
by its application-assigned `source_index`. Each
entry reports only `unmapped_claims`: exact substantive reply spans whose source
contribution lacks an adequate declaration. Already covered claims, bound exact
quotations, and unused or overlapping available sources need no repeated
inventory. Empty lists record that the reviewer found no missing mapping.
`claim_audit` contains
one support judgment per declared claim, indexed into the existing declarations,
against that declaration's named source. It does not duplicate source content
or full findings. A source-use omission or unsupported mapping must have a
finding on the affected current claim or mapping; a passing decision cannot
contain such findings. A wrong-source declaration can be marked unsupported
without falsely claiming that the reply used that source.

Iteration 1 showed why the independent omission scan must remain separate from
the declaration audit. Repeating every source-use span introduced false errors
for adjacent sentence mappings, citation suffixes, separately bound quotations,
and equivalent overlapping records. Generic error messages then caused models
to critique unrelated text. The simplified contract removes both redundant
span-containment checks rather than adding normalization or fuzzy matching.
The reviewer still owns semantic identification of omissions and source
contributions. A negated proof claim is not treated as asserting the withheld
conclusion; affirmative personal explanations still require support.

Deterministic validation owns audit coverage, exact current reply spans, finding
locations, and consistency between recorded defects and findings. Existing
release validation continues to own source identity, exact declaration spans,
quotation binding, scope, and capture authority. The model still owns the
semantic classification: it can miss an undeclared use or incorrectly judge
support. The typed audit makes those judgments explicit and prevents an
admitted defect from silently receiving a pass; it is not a deterministic proof
of semantic correctness. Live wrong/right source-mapping cases and the original
scenario reruns are needed to measure that remaining risk.

Iteration 2 exposed two further review errors. A reviewer demanded that each
declared source independently establish an entire joint interpretation, although
the two declarations supplied complementary support. The typed audit description
now matches the skill: each named source must support its contribution, and the
declared sources together must support the complete claim. Two paired semantic
fixtures distinguish complete joint mapping from a missing contribution while
keeping both sources available.

The Pinocchio reviewer also twice invented a newline mismatch for a quotation
that exactly matched the current source and response. `ProvenanceInput` now
serializes computed `quote_checks` for declared exact quotes. These facts compare
decoded strings character for character against the matching source kind and ID.
They are recomputed on every access; serialized or supplied flags are discarded
on input validation, so a round trip cannot preserve stale or forged results.
The model still reviews meaning, attribution and undeclared visible quotations.
The application does not automatically accept a review because a quote matches,
and the final deterministic release checks remain unchanged. Tests cover real
newlines and Markdown, altered response/source text, wrong IDs and kinds, current
facts after model copies, and serialized round trips.

Iteration 3 showed a reviewer repeatedly transcribing an opaque memory ID
incorrectly despite exact repair feedback. Source audits now return a numeric
index from the computed `source_references` table, which binds every index to
the current canonical source kind and ID. The table is serialized for the model
and recomputed from current source records; supplied tables have no authority.
Audit validation still requires every current source exactly once and reports
the bound reference with missing-claim errors. No old ID-based audit alias is
retained, and archived run artifacts remain unchanged.

A matching chapter or section label introducing an already bound quotation is
covered by that declaration. It is not a new interpretation requiring a second
mapping. This exception does not cover wrong locations, undeclared quotations,
or additional substantive claims. Exact-quote matches do not override a
well-grounded semantic misattribution finding.

Muse's reflection instructions now require stored-memory declarations despite
phrases such as “your note,” and require each substantive clause to be mapped
to the record supporting it. The instructions also match the application-owned
Librarian scope interface: Muse selects the routed work and version while the
application supplies the validated chapter or passage permission.

The offline regression tests demonstrated missing repair before the capability:
invalid current quotes and paths returned after one call, and repeated invalid
locations did not exhaust the repair budget. These tests now pass. Audit tests
cover undeclared memory use, unused and overlapping available sources, split
claim mappings, separately bound quotations, citation suffixes, wrong named
records, missing audit coverage, invented current spans, and required defect
findings. Aggregate-feedback tests check exact paths and current targets, including
invalid claim indices. Mocked
review fixtures use `tests/provenance_fixtures.py` to state their chosen audits;
this helper is test-only and deliberately does not infer semantic support or
classify undeclared prose. Defect tests supply their audits explicitly.

## Iteration 6: complete response coverage and explicit joint membership

Iteration 5 Roses S2 removed the unsupported personal explanation, but its final reviewer demanded joint mapping of a sentence already repeated in both contributing declarations. The source-index repair had removed ID copying mistakes; it had not made the relationship between declarations explicit. Meanwhile, a source-by-source omission list allowed a reviewer to skip uncovered prose while still returning every expected source index.

The replacement stays in the same candidate-review call and retry budget. `ProvenanceInput` computes two current-input projections:

- `claim_support_groups` groups exactly identical declared claim strings and lists every declaration/claim index and its named source. It establishes membership, not support. Existing per-declaration `claim_audit` still assesses each member's contribution and the group's complete support.
- `uncovered_response_spans` is the complement of all exact claim occurrences and canonically matching bound quotation occurrences in the current response. It unions overlaps, retains original character offsets and punctuation, and omits only whitespace-only gaps. The reviewer must classify every span in the context of the full response as presentation, reader reflection, or source dependent. A source-dependent classification requires a grounded finding overlapping that exact current gap.

The old `source_audit` and `source_references` interfaces are removed without aliases. Serialized derived tables are discarded and recomputed; model copies also read current data. Fake broad declarations still face the independent claim support audit. Invalid quotes cannot remove a gap merely because Muse supplied `exact_quote`. The source identity, quote, scope, decision, prior-finding, release, and bounded repair gates remain intact.

This closes mechanical coverage omissions, including zero-source replies. It does not turn semantic support into a deterministic property: a reviewer can still misclassify a gap or a source contribution. No approval is inferred from the computed tables. The mock helper asserts deliberately fallible fixture judgments; it is never used as a production semantic validator.

Offline validation: 144 Provenance tests and 39 subtests passed. Regressions cover forged projections, Unicode offsets, overlapping/repeated coverage, incomplete/duplicate/out-of-range audits, exact overlapping findings, zero-source coverage, invalid quotation coverage, unsupported broad declarations, wrong-source mappings, joint membership including session statements, and current-input repair under the existing retry budget. The four-case claim-mapping evaluation inputs and expected outcomes are unchanged; their derived prompt projection follows the new contract. Live behavior remains to be measured by the parent-controlled batch.
