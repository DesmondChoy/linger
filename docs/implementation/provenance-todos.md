# Provenance TODOs

The three Provenance skills and their deterministic safeguards are implemented.
Sections 4.2.3 and 4.2.4 reuse the candidate-review gate; neither needs another
Provenance runtime path. The remaining work is integration and evaluation.

## Remaining work

- [ ] **Refresh the candidate-gate measurement.** Run all 34 cases in
  `evals/provenance/risk-codes-cases.json` against the current prompt and make
  the suite pass without weakening its gates. The committed report covers only
  24 cases and has `targets_pass=false`.
- [x] **Add 4.2.3 semantic pairs.** The 34-case pack now pairs uncited and cited
  web claims, attributed personal memory, and misuse of memory as public or
  book evidence. Live measurement remains in the item above.
- [ ] **Finish 4.2.2 evaluation evidence.** Make the 12-case curation risk pack
  pass; its committed report has `targets_pass=false`. Author, adopt, and replay
  the sensitive-capture-veto scenario, including the prompt-injection overlay.
  Add scenario coverage for tombstone, restore, and fail-closed curation
  outcomes that currently have only focused tests. The curation review now
  receives trusted active/tombstoned state, and the invalid-restore and
  injection fixtures are corrected; the live rerun is pending credentials.
- [ ] **Complete the 4.2.5 conversation path.** After successful capture, add
  ordered-Scene Ground truth and replay for capture, curation, surfacing or
  silence, Provenance review, and final release.
  - [x] Runtime: a new durable capture triggers bounded reviewed curation once;
    a later chat passes validated same-account sources through Muse, canonical
    connection evidence, Provenance, and deterministic release validation.
  - [x] Contract: preserve the offline `component_v1` format and add a
    `conversational_v1` ordered Scene contract with symbolic runtime outcome
    references.
  - [ ] Replay: the ordered production runner now carries actual
    capture/curation outcomes between Scenes. Still author and independently
    adopt a concrete scenario, then run it through provider-backed production
    chat.
- [ ] **Correct stale status docs.** The older 4.2.2 implementation notes still
  describe committed live runs as pending; reconcile those historical status
  notes after the next credentialed evaluation run.
- [ ] **Add live-model CI only after the packs are repeatably green.** Keep the
  provider-backed job separate from deterministic tests and retain the
  metadata-only reports.

## No Provenance work remains here

- **4.2.4 inspection:** the API and developer Inspect UI already expose the
  Provenance verdict path, finding codes, boundary origin, failure type, and
  retryability without exposing critiques or rejected drafts.
- **4.2.1 boundary inference:** the open low-score localisation defect belongs
  to Librarian retrieval and boundary orchestration, not Provenance.

Focused verification on 2026-09-21: 187 tests and 85 subtests passed across the
new conversation path, Provenance risk contracts, curation gate, and affected
Muse and Sculptor behavior.
