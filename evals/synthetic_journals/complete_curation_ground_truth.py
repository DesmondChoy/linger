"""Complete evaluator-owned curation policy before independent label adoption."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from evals.sculptor.harness import SemanticReview
from evals.synthetic_journals.models import (
    ProposedGroundTruth,
    RunConfiguration,
    SyntheticBackstory,
)
from evals.synthetic_journals.validate_scenario import (
    BOUNDED_CURATION_OBJECTIVE_ID,
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    REPOSITORY_ROOT,
    load_run_configurations,
    validate_scenario,
)

# Match the word bound enforced by Sculptor's DerivedSummary response contract.
_MAX_SUMMARY_WORDS = 100
_SUMMARY_REVIEW = SemanticReview(
    criteria=(
        "The summary faithfully compresses the cited source memories and preserves "
        "their material distinctions.",
    ),
    forbidden_claims=(
        "Facts, causes, emotions, preferences, or conclusions unsupported by the "
        "cited source memories.",
    ),
)
_TOPIC_REVIEW = SemanticReview(
    criteria=(
        "The topic label names a theme supported by every cited source memory "
        "while preserving them as related, distinct records.",
    ),
    forbidden_claims=(
        "Treating related memories as duplicates, grouping unrelated memories, "
        "or inventing a theme unsupported by the cited source memories.",
    ),
)
_EVALUATOR_FIELDS = frozenset({"max_summary_words", "semantic_review"})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def complete_curation_ground_truth(
    backstory_bytes: bytes,
    ground_truth_bytes: bytes,
    *,
    run_configurations: dict[str, RunConfiguration],
    repository_root: Path = REPOSITORY_ROOT,
) -> bytes:
    """Fill omitted policy fields and validate without changing candidate labels.

    Supplied evaluator fields are refused even when they match current policy.
    Completion therefore runs once, before normal validation and adoption.
    """

    backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
    if BOUNDED_CURATION_OBJECTIVE_ID not in backstory.objective_ids:
        raise ValueError("policy completion requires bounded_memory_curation")
    document = json.loads(ground_truth_bytes, object_pairs_hook=_unique_object)
    if not isinstance(document, dict) or not isinstance(document.get("proposals"), list):
        raise ValueError("Ground truth must be an object with a proposals array")

    for index, proposal in enumerate(document["proposals"]):
        if not isinstance(proposal, dict):
            continue  # The unchanged strict model reports malformed entries below.
        curation = proposal.get("curation")
        if not isinstance(curation, dict):
            continue
        expected = curation.get("expected")
        if not isinstance(expected, dict):
            continue
        action = expected.get("action")
        if not isinstance(action, dict):
            continue
        supplied = _EVALUATOR_FIELDS.intersection(action)
        if supplied:
            raise ValueError(
                f"proposal {index + 1} supplies evaluator-owned fields: "
                f"{', '.join(sorted(supplied))}; completion requires their omission"
            )
        if (
            proposal.get("objective_id") != BOUNDED_CURATION_OBJECTIVE_ID
            or expected.get("kind") != "curation_proposal"
        ):
            continue
        if action.get("action") == "update_derived_summary":
            action["max_summary_words"] = _MAX_SUMMARY_WORDS
            action["semantic_review"] = _SUMMARY_REVIEW.model_dump(mode="json")
        elif action.get("action") == "assign_topic_group":
            action["semantic_review"] = _TOPIC_REVIEW.model_dump(mode="json")

    completed_bytes = (
        json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    ground_truth = ProposedGroundTruth.model_validate_json(completed_bytes)
    validate_scenario(
        backstory,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=run_configurations,
        repository_root=repository_root,
    )
    return completed_bytes


def _refuse_adopted(ground_truth_path: Path) -> None:
    adoption_path = ground_truth_path.with_name("ground-truth-adoption.json")
    if adoption_path.exists() or adoption_path.is_symlink():
        raise ValueError(f"refusing completion beside existing adoption: {adoption_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Complete evaluator-owned curation policy in proposed ground-truth.json."
    )
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    args = parser.parse_args(argv)
    temporary_path: Path | None = None
    try:
        _refuse_adopted(args.ground_truth)
        backstory_path = args.backstory.resolve(strict=True)
        ground_truth_path = args.ground_truth.resolve(strict=True)
        _refuse_adopted(ground_truth_path)
        backstory_bytes = backstory_path.read_bytes()
        ground_truth_bytes = ground_truth_path.read_bytes()
        completed_bytes = complete_curation_ground_truth(
            backstory_bytes,
            ground_truth_bytes,
            run_configurations=load_run_configurations(DEFAULT_RUN_CONFIGURATION_DIRECTORY),
        )
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{ground_truth_path.name}.", suffix=".tmp",
            dir=ground_truth_path.parent, delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(completed_bytes)
            output.flush()
            os.fsync(output.fileno())
        _refuse_adopted(args.ground_truth)
        _refuse_adopted(ground_truth_path)
        if (
            ground_truth_path.read_bytes() != ground_truth_bytes
            or backstory_path.read_bytes() != backstory_bytes
        ):
            raise ValueError("scenario files changed during completion; no rewrite applied")
        os.replace(temporary_path, ground_truth_path)
    except (OSError, ValueError) as error:
        print(f"CURATION_GROUND_TRUTH_COMPLETION_FAILED={error}", file=sys.stderr)
        return 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(f"CURATION_GROUND_TRUTH_COMPLETION_OK={ground_truth_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
