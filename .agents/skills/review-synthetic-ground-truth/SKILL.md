---
name: review-synthetic-ground-truth
description: Review a validated Linger synthetic Backstory and proposed Ground truth in a local interactive app, record independent human adoption, and continue to an implemented objective-specific replay only after explicit confirmation.
---

# Review Synthetic Ground Truth

Use this skill only after a generator has written sibling `backstory.json` and
`ground-truth.json` files in one synthetic-journal package directory. The human
reviewer must be independent of the generator. Neither proposed nor adopted
Ground truth enters the system under evaluation.

Before opening a review that can trigger a supported replay, ensure the
developer has configured the Linger Logfire project as described in the
[repository workflow](../../../README.md#human-gated-synthetic-evaluation).
Confirmation immediately authorizes one provider-backed replay for a supported
Objective selection. Without local Logfire project credentials or `LOGFIRE_TOKEN`, the
runner retains its durable JSON output but cannot publish the experiment and
synthetic traces to Logfire.

## Open the review

1. Resolve `scripts/ground_truth_reviewer.py` relative to this file.
2. Resolve a stable human reviewer ID from the developer's explicit input or the
   repository Git identity. Do not let the generator or a semantic judge act as
   the reviewer.
3. Run the launcher from the repository root with the repository Python
   environment:

   ```text
   ground_truth_reviewer.py BACKSTORY_PATH GROUND_TRUTH_PATH --reviewer-id REVIEWER_ID
   ```

   It validates both JSON files before binding. Surface its
   `GROUND_TRUTH_REVIEW_URL` as a clickable link and wait for the process to
   finish. If the first launch exits with status 3 and prints
   `GROUND_TRUTH_REVIEW_BIND_PERMISSION_REQUIRED=127.0.0.1`, retry that exact
   command once with narrow loopback-binding approval. Never bind to a
   non-loopback address.
4. Continue only after one `GROUND_TRUTH_REVIEW_JSON` record is printed. Verify
   the returned Backstory and proposed Ground truth hashes against the current
   files. A timeout, missing result, stale hash, invalid package, or malformed
   result is a hard stop.

## Follow the human decision

For `decision: "make_changes"`, stop without replay or adoption. Report the
flagged and unchecked proposal IDs, then ask the developer what should change.
After an approved revision, validate the successor JSON and open a fresh review
session. Never infer the requested correction from unchecked rows alone.

For `decision: "confirm"`, require the returned adoption path and validate it
against the exact two JSON files. Confirmation authorizes one objective-specific
replay because the app labels the action **Confirm and run evaluation** and
explains the provider-backed side effect.

- For exactly `reviewed_automatic_memory_capture`, run
  `evals.synthetic_journals.replay` with `--adoption` and a fresh temporary
  output path.
- For exactly `bounded_memory_curation`, run
  `evals.synthetic_journals.curation_replay` with `--adoption` and a fresh
  temporary output path.
- For exactly `proactive_memory_surfacing`, run
  `evals.synthetic_journals.surfacing_replay` with positional `BACKSTORY_PATH`
  and `GROUND_TRUTH_PATH`, `--adoption ADOPTION_PATH`, and
  `--output OUTPUT_PATH`. Use a fresh temporary output path. This runs Sculptor
  over supplied Props and typed offline context. It
  does not run a scheduler, send notifications, or invoke Muse or Provenance.
  Report the decision and deterministic hard-gate results separately from
  semantic quality. Usefulness, appropriate timing, and sensitive inference
  still require human review against the recorded `semantic_criteria` and
  `forbidden_claims`. This runner has no `--semantic-review` option.
- For exactly `session_scoped_conversation_continuity`, run
  `evals.synthetic_journals.continuity_replay` with `--adoption` and a fresh
  temporary output path. The runner grades only the session boundary; correction
  adoption and fresh-session leakage wording remain human reviewer judgments
  read from the durable run artifact.
- For exactly `grounded_book_reflection`, exactly
  `spoiler_boundary_clarification`, or their two-Objective combination in either
  order, run `evals.synthetic_journals.book_replay` with `--adoption` and a fresh
  temporary output path. Do not add `--semantic-review` unless the developer
  separately requests it. The optional semantic review makes another model call
  and produces a separate, non-independent result.
- For any other or mixed Objective set, preserve the adoption but stop: no
  generic replay path is implemented.

The browser server never invokes runtime itself. The agent maps the confirmed
Objective to the known runner, reports the durable run path and result, and
stops on any validation, provider, telemetry, or replay error. Do not rerun a
failed provider evaluation without fresh developer authorization.
