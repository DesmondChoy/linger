---
name: review-synthetic-ground-truth
description: Review a validated Linger synthetic Backstory and proposed Ground truth in a local interactive app, record independent human adoption, and continue to an implemented objective-specific replay only after explicit confirmation.
---

# Review Synthetic Ground Truth

Use this skill only after a generator has written sibling `backstory.json` and
`ground-truth.json` files in one synthetic-journal package directory. The human
reviewer must be independent of the generator. Neither proposed nor adopted
Ground truth enters the system under evaluation.

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
- For any other or mixed Objective set, preserve the adoption but stop: no
  generic replay path is implemented.

The browser server never invokes runtime itself. The agent maps the confirmed
Objective to the known runner, reports the durable run path and result, and
stops on any validation, provider, telemetry, or replay error. Do not rerun a
failed provider evaluation without fresh developer authorization.
