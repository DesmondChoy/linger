# Synthetic evaluation packages

`packages/` contains seven generated packages. Generation, human review,
formal adoption, replay, and current compatibility are separate stages. A missing
adoption sidecar or replay artifact does not mean a scenario was never
implemented. `clean-up/` contains the everyday-curation package and the
report-only memory–book–web plan, both deferred by explicit developer choice.
Failed evaluations remain useful evidence and stay with their packages.

Housekeeping checked this evidence on 11 September 2026 against `a2e9c0b`.
Bead `linger-e0xi` tracks the cleanup. Recorded replay outcomes below are
historical results, not fresh model evaluations.

## Folder names

Packages use `<scenario-set>--<agents>--<YYYY-MM-DD>`. For example,
`pottery-memory-curation--sculptor--2026-08-29` identifies the scenario set,
evaluated agent, and creation date without opening a report. A name describes
the complete Scene set, including its comparison cases.

Agent names follow the fixed order `muse`, `librarian`, `serendipity`,
`sculptor`, `provenance`, omitting agents outside the evaluation. This order is
for naming consistency, not a runtime call sequence. In `clean-up/`, agent names
describe the intended evaluation path and do not establish implementation.
Status, grades, and compatibility belong in this index. Same-day name collisions
use `-02`, `-03`, and so on. Full timestamps remain in report snapshots.

The [generation skill](../.agents/skills/generate-synthetic-journals/SKILL.md)
uses this convention for new reports. Canonical Objective IDs and generated
package identifiers are unchanged by directory renaming. Recorded JSON artifacts
may contain historical paths; their bytes remain unchanged to preserve evidence.

## Packages with recorded adoption and replay

| Package | Evaluated behavior | Adoption and replay evidence | Recorded result | Current package compatibility |
| --- | --- | --- | --- | --- |
| [pottery-memory-curation--sculptor--2026-08-29](packages/pottery-memory-curation--sculptor--2026-08-29/) | Bounded memory curation: five offline Scenes using 15 Props. | Local adoption record; closed Bead `linger-3ry` records independent approval and one completed provider replay. No replay transcript is retained in this directory. | Five Scenes passed deterministic hard gates and source-immutability checks. This evaluates curation proposals, not applied memory changes or semantic quality. | Package and adoption validate. |
| [alice-quotation-grounding--muse-librarian-provenance--2026-08-31](packages/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/) | Grounded book reflection: quotation request and personal-reflection comparison. | Local adoption record and eight full transcripts: `reflection-run.json` and `reflection-run-0.json` through `reflection-run-6.json`. | Quotation Scene passed in runs 2 and 5 and failed in six runs. Personal comparison passed in all eight. | Historical schema. Current validation rejects book proposals without typed `book_expectation`. |
| [alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01](packages/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/) | Spoiler-boundary clarification: a remembered kitchen event and an ambiguous size-change comparison. | Local adoption record and [full replay transcript](packages/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/reflection-run.json). | Grounded Scene failed with `missing_retrieval`; ambiguous comparison passed its hard gates. | Historical schema. Current validation rejects book proposals without typed `book_expectation`. |
| [alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/) | Grounded reflection and spoiler clarification: three Scenes with four adopted judgments. | Local adoption, nine adopted replay summaries, and [evaluation findings](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/evaluation-findings.md). Closed Beads `linger-h4gl` and `linger-hzdg` record passing replays. | Earlier runs passed two or three judgments. Conditional-policy, post-pull, and [connection-update regression](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/connection-update-regression-summary.json) runs each passed all four. | Package and adoption validate. |

All four adoption records still match the exact Backstory and proposed Ground
truth bytes. Hash agreement does not make the two historical schemas valid
under the current contract. Their generated files, adoption records, and
transcripts are preserved unchanged. Report path references follow the renamed
directories; recorded timestamps and evaluation results remain historical. Changed Ground truth requires fresh
independent adoption before a new graded replay.

The September 3 summaries retain outcomes and selected evidence. Their full
transcripts point to temporary local paths whose availability is not established
by this index. The directory also contains a
[clarification follow-up](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/clarification-followup-findings.md)
that tests a separate two-message conversation. That follow-up is not a replay
of the adopted package. The connection-update regression summary follows the
post-pull result described as latest in the older findings narrative.

Deterministic passes do not establish independent semantic quality or a general
model success rate. Keep failed runs alongside passing runs.

## Other generated packages

These packages have generated Backstory and Ground truth files. Their later
review and replay stages differ; they are not classified as abandoned work.

| Package | Generation | Review and adoption | Replay evidence | Current compatibility |
| --- | --- | --- | --- | --- |
| [Everyday memory capture](packages/everyday-memory-capture--muse-provenance--2026-08-23/) | Complete: 11 Scenes and 11 proposals. | `linger-1y3` records human approval of all 11 labels. No hash-bound adoption sidecar exists; that tooling was outside the original task. | `linger-n4h` records replay `e0b8d0a8847e48d3818e4fbe7aed8a66` and a capture failure. Its temporary transcript is unavailable. `linger-urvq` subsequently changed the grader, so the old run does not establish success under current capture grading. | Package validates. |
| [Alice Caterpillar grounding and spoilers](packages/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/) | Complete: three Scenes and four proposals. | [Adoption record](packages/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/ground-truth-adoption.json) records a human developer's interactive review on 29 August 2026 at 15:31 +08 and four adopted decisions. Source hashes, proposal references, and adoption identity match. | Completion unverified. `linger-ck1` records implementation and generation, not a completed provider evaluation. | Historical schema; current validator rejects removed book fields. The adoption record does not establish compatibility with the current schema. |
| [Alice identity connections and restraint](packages/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/) | Complete: three Scenes and four proposals. | No adoption sidecar or verified adoption completion. | No verified completed replay. | Package validates. |

The capture test fixture retains an unchanged copy of the everyday capture JSON.
Generated package files and historical adoption records are preserved unchanged;
review and replay evidence are reported at the level supported by files and Beads.

## Cleanup items

[Memory–book–web connections](clean-up/memory-book-web-connections--muse-librarian-serendipity-provenance--2026-09-01/)
contains only a historical pre-generation report. It has no generated Backstory,
Ground truth, adoption, or replay.

[Everyday memory curation](clean-up/everyday-memory-curation--sculptor--2026-08-24/)
was moved here at the developer's request. It remains a valid generated package
with five Scenes and five proposals. `linger-a4u.2` records human coherence and
plausibility inspection, but no adoption sidecar exists. The same Bead records
provider replay `db8f77cafb434e7d80b1324367a0b287`, with four of five proposal
comparisons matching and all source hashes unchanged. Its temporary transcript
is unavailable. The move does not erase that completed work or imply that it
was never implemented. Existing Beads retain their own scope and status.

The September 5 report directories `2026-09-05T170147+0800` and
`2026-09-05T231756+0800` were already deleted in the working tree before this
cleanup. Their deletion was preserved.

## Definitions and tooling

[evaluation-objectives.yaml](evaluation-objectives.yaml) remains the authority
for Objective definitions and selection rules. Its catalog is not limited to
Objectives with completed evaluations. The shared files in
[generation-presets/](generation-presets/) remain inputs to generation and
validation, including the capture test fixture. The generation skill and
validators use these files; the everyday capture package selects the capture preset.
Presets define reusable Scene
and Prop proportions; they are not execution settings or replay results.

### Preset references

A package selects a preset through `backstory.json`'s `run_configuration_ids`,
which matches the preset's `run_configuration_id`. These existing JSON fields
retain their names so generated files and adoption hashes remain unchanged.
The directory name does not create a one-to-one mapping between presets and
packages.

| Generation preset | Saved package that references it | Other consumers |
| --- | --- | --- |
| [reviewed-automatic-memory-capture-10-to-1.json](generation-presets/reviewed-automatic-memory-capture-10-to-1.json) | [Everyday capture Backstory](packages/everyday-memory-capture--muse-provenance--2026-08-23/backstory.json), via `reviewed-automatic-memory-capture-10-to-1`. | Its unchanged [test fixture](../tests/fixtures/synthetic_capture/backstory.json) selects the same ID. |
| [longitudinal-memory-retrieval-10-to-1.json](generation-presets/longitudinal-memory-retrieval-10-to-1.json) | None. | No saved package in `packages/` or `clean-up/` references it. The generation skill uses it for future longitudinal-retrieval packages; retrieval validation tests exercise it. |

The other seven generated Backstories have empty or omitted
`run_configuration_ids`. Their Scenes, Props, and Lines are defined directly in
each Backstory, with expected outcomes in the sibling Ground truth file.

The [evaluation guide](../evals/synthetic_journals/README.md) documents package
contracts, review, and replay commands. The generation skill still creates a
report first. New reports may appear under `packages/` while work is active.
Generated packages remain there with generation, review, adoption, replay, and
compatibility recorded separately. Moving a plan to `clean-up/` is an explicit
housekeeping decision, not an automatic consequence of a missing later stage.

Package validation runs without a provider call:

```bash
uv run python -m evals.synthetic_journals.validate_package \
  synthetic-journal-evaluation/packages/<package-name>/backstory.json \
  synthetic-journal-evaluation/packages/<package-name>/ground-truth.json
```

The compatibility column above distinguishes expected historical failures from
currently valid inputs. Do not repair old adopted files merely to make this
command pass.
