"""Offline recall and pool size of multi-book candidate gathering.

Replays frozen Librarian book-request plans from the combined Scenario through
local retrieval only (no model calls), then checks that every required book
passage from the adopted Ground truth reaches the evidence-assessment pool.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from apps.backend.contracts import BookScope
from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.librarian import Librarian
from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from src.linger.agents.librarian.models import BookRequestPlan, LibrarianBookRequestInput
from src.linger.orchestration.book_evidence import PART_CANDIDATES, gather_book_candidates

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = Path(__file__).with_name("part_recall_cases.json")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    required: int
    found: int
    missing: tuple[str, ...]
    pool_size: int
    pool_characters: int


def _required_passages(scenario: Path) -> dict[str, tuple[tuple[str, frozenset[str]], ...]]:
    """Map each Scene to its required book items and their accepted runtime windows."""
    plan = compile_connection_replay_plan(
        SyntheticBackstory.model_validate_json((scenario / "backstory.json").read_text(encoding="utf-8")),
        ProposedGroundTruth.model_validate_json((scenario / "ground-truth.json").read_text(encoding="utf-8")),
    )
    required: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {}
    for scene in plan.scenes:
        items = []
        for proposal in scene.proposals:
            if proposal.connection is None:
                continue
            alternatives = {
                item.evidence_id: item.accepted_evidence_ids
                for item in proposal.connection.evidence_alternatives
            }
            for evidence_id in proposal.connection.required_evidence_ids:
                accepted = frozenset(
                    record.evidence_id
                    for option in (evidence_id, *alternatives.get(evidence_id, ()))
                    if option in scene.evidence_by_id
                    for record in scene.evidence_by_id[option].accepted_runtime_records
                )
                if accepted:
                    items.append((evidence_id, accepted))
        required[scene.scene.scene_id] = tuple(items)
    return required


def run(
    cases_path: Path = DEFAULT_CASES, librarian: Librarian | None = None,
    part_candidates: int = PART_CANDIDATES,
) -> list[CaseResult]:
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    required = _required_passages(REPOSITORY_ROOT / document["scenario"])
    librarian = librarian or HybridLibrarian()
    results = []
    for case in document["cases"]:
        pool = gather_book_candidates(
            BookRequestPlan.model_validate({"parts": case["parts"]}),
            LibrarianBookRequestInput(
                current_line=case["current_line"],
                prior_reader_statements=case["prior_reader_statements"],
            ),
            book_scopes=tuple(BookScope(**scope) for scope in case["book_scopes"]),
            librarian=librarian,
            purpose="connection_discovery",
            part_candidates=part_candidates,
        )
        pool_ids = {item.evidence_id for item in pool}
        needed = required.get(case["scene_id"], ())
        missing = tuple(evidence_id for evidence_id, accepted in needed if not accepted & pool_ids)
        results.append(CaseResult(
            case_id=case["case_id"], required=len(needed), found=len(needed) - len(missing),
            missing=missing, pool_size=len(pool),
            pool_characters=sum(len(item.excerpt) for item in pool),
        ))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--read-chapter-cues", action="store_true",
        help="search with chapter cues, as chapter-cue activation requires",
    )
    parser.add_argument(
        "--part-candidates", type=int, default=PART_CANDIDATES,
        help="windows kept per planned part, as an Experiment 4 build may opt into",
    )
    args = parser.parse_args()
    results = run(args.cases, HybridLibrarian(read_chapter_cues=args.read_chapter_cues), args.part_candidates)
    for result in results:
        print(
            f"{result.case_id:18s} recall {result.found}/{result.required} "
            f"pool {result.pool_size:3d} records {result.pool_characters:7d} chars"
            + (f"  missing {', '.join(result.missing)}" if result.missing else "")
        )
    required = sum(result.required for result in results)
    found = sum(result.found for result in results)
    print(
        f"\nrecall {found}/{required}; mean pool "
        f"{sum(r.pool_size for r in results) / len(results):.1f} records, "
        f"{sum(r.pool_characters for r in results) / len(results):.0f} chars"
    )


if __name__ == "__main__":
    main()
