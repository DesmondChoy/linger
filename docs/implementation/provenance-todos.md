# Provenance TODOs

The three Provenance skills and their deterministic safeguards are implemented.
Sections 4.2.3 and 4.2.4 reuse the candidate-review gate; neither needs another
Provenance runtime path. The remaining work is integration and evaluation.

## Remaining work

- [ ] **Refresh the candidate-gate measurement.** Run all cases in
  `evals/provenance/risk-codes-cases.json` against the current prompt and make
  the suite pass without weakening its gates. The committed report covers only
  24 cases and has `targets_pass=false`.
- [x] **Add 4.2.3 semantic pairs.** The 34-case pack now pairs uncited and cited
  web claims, attributed personal memory, and misuse of memory as public or
  book evidence. Live measurement remains in the item above.
- [x] **Finish 4.2.2 evaluation evidence.** Make the 12-case curation risk pack
  pass; its committed report has `targets_pass=false`. Author, adopt, and replay
  the sensitive-capture-veto scenario, including the prompt-injection overlay.
  Add scenario coverage for tombstone, restore, and fail-closed curation
  outcomes that currently have only focused tests. The curation review now
  receives trusted active/tombstoned state, and the invalid-restore and
  injection fixtures are corrected; the live rerun is pending credentials.
  - Completed, see [curation risk pack evals results](../../evals/provenance/curation-risk-codes-live-report.json)
- [ ] **Complete the 4.2.5 conversation path.** Add ordered-Scene Ground truth
  and replay for capture, curation, surfacing or silence, Provenance review,
  and final release.
  - [x] Runtime: a durable capture triggers bounded reviewed curation once,
    and a later chat can pass validated same-account sources through Muse,
    canonical connection evidence, Provenance, and deterministic release
    validation.
  - [x] Contract: keep the offline `component_v1` format and add the
    `conversational_v1` ordered Scene contract with symbolic runtime-outcome
    references.
  - [ ] Replay: the ordered production runner carries actual capture and
    curation outcomes between Scenes. The full replay still needs an adopted
    `proactive_memory_surfacing` Scenario and a provider-backed production-chat
    run.
  - [x] Prerequisite replay: the adopted capture and bounded-curation Scenario
    ran three times, then ran once more after Ground truth revision. See
    [4.2.5 replay findings](provenance-4.2.5.md).
  - [x] Resolve the two unstable behaviors. `scene-capture-07` now uses the
    shorter observed span, and `scene-curation-evolving` now expects the
    coherent evolving-summary source set. Fresh independent adoption and replay
    passed all 16 Scenes. The historical failures and revised-run evidence are
    recorded in [4.2.5 replay findings](provenance-4.2.5.md).
- [ ] **Correct stale status docs.** The older 4.2.2 implementation notes still
  describe committed live runs as pending; reconcile those historical status
  notes after the next credentialed evaluation run.

## No Provenance work remains here

- **4.2.4 inspection:** the API and developer Inspect UI already expose the
  Provenance verdict path, finding codes, boundary origin, failure type, and
  retryability without exposing critiques or rejected drafts.
- **4.2.1 boundary inference:** the open low-score localisation defect belongs
  to Librarian retrieval and boundary orchestration, not Provenance.

Focused verification on 2026-09-21: 187 tests and 85 subtests passed across the
new conversation path, Provenance risk contracts, curation gate, and affected
Muse and Sculptor behavior.
