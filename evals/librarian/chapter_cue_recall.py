"""Chapter-cue recall for Experiment 3 on frozen Librarian request plans.

`freeze` runs one production Librarian planning pass per need and stores the
plans, so later scoring changes only what search reads. `score` replays those
plans through local retrieval only (no model calls) and records, per need,
whether a passage containing its quote reaches the assessment pool under
production limits.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from apps.backend.contracts import BookScope
from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import BookRequestPlan, LibrarianBookRequestInput
from src.linger.agents.librarian.skills import BOOK_REQUEST
from src.linger.orchestration.book_evidence import gather_book_candidates

NEEDS = Path(__file__).with_name("chapter_cue_needs.json")
PLANS = Path(__file__).with_name("chapter_cue_plans.json")


def _normalised(text: str) -> str:
    return " ".join(text.split())


def _needs(set_name: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    document = json.loads(NEEDS.read_text(encoding="utf-8"))
    return document, document[set_name]["needs"]


async def freeze() -> None:
    from apps.backend.config import get_settings
    from apps.backend.telemetry import configure_telemetry
    from src.linger.orchestration.evidence_strength import plan_book_request

    if PLANS.exists():
        raise SystemExit(f"{PLANS.name} is frozen; delete it deliberately to replan.")
    configure_telemetry()
    plans = {}
    for set_name in ("practice", "sealed"):
        for need in _needs(set_name)[1]:
            plan = await plan_book_request(need["question"])
            plans[need["id"]] = plan.model_dump(mode="json")
            print(f"{need['id']} {len(plan.parts)} part(s)", flush=True)
    fingerprint = BOOK_REQUEST.fingerprint()
    PLANS.write_text(json.dumps({
        "schema_version": 1,
        "frozen_on": datetime.now(UTC).date().isoformat(),
        "model": get_settings().linger_model,
        "prompt_template_id": fingerprint.template_id,
        "prompt_digest": fingerprint.digest,
        "plans": plans,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def score(set_name: str, librarian: Librarian) -> list[dict[str, object]]:
    document, needs = _needs(set_name)
    plans = json.loads(PLANS.read_text(encoding="utf-8"))["plans"]
    scope = BookScope(
        work_id=document["work_id"], book_version_id=document["book_version_id"],
        chapter_max=document["chapter_max"],
    )
    results = []
    for need in needs:
        pool = gather_book_candidates(
            BookRequestPlan.model_validate(plans[need["id"]]),
            LibrarianBookRequestInput(current_line=need["question"]),
            book_scopes=(scope,), librarian=librarian,
        )
        quote = _normalised(need["quote"])
        found = [item.evidence_id for item in pool if quote in _normalised(item.excerpt)]
        results.append({
            "id": need["id"],
            "chapter": need["chapter"],
            "reached": bool(found),
            "evidence_ids": found,
            "pool_chapters": list(dict.fromkeys(item.chapter for item in pool)),
            "pool_size": len(pool),
            "pool": [item.evidence_id for item in pool],
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze", help="plan every practice and sealed need once")
    scoring = commands.add_parser("score", help="score frozen plans with local retrieval")
    scoring.add_argument("--set", choices=("practice", "sealed"), default="practice", dest="set_name")
    scoring.add_argument("--read-chapter-cues", action="store_true")
    scoring.add_argument("--output", type=Path, help="write per-need results as JSON")
    args = parser.parse_args()
    if args.command == "freeze":
        asyncio.run(freeze())
        return
    results = score(args.set_name, HybridLibrarian(read_chapter_cues=args.read_chapter_cues))
    for result in results:
        chapter_found = result["chapter"] in result["pool_chapters"]
        print(
            f"{result['id']} ch{result['chapter']:02d} "
            f"{'reached' if result['reached'] else 'MISSED '} "
            f"pool {result['pool_size']:2d} chapters {result['pool_chapters']}"
            + ("" if result["reached"] else f"  (chapter {'in' if chapter_found else 'not in'} pool)")
        )
    reached = sum(result["reached"] for result in results)
    print(f"\nreached {reached}/{len(results)}")
    if args.output:
        args.output.write_text(json.dumps({
            "set": args.set_name, "read_chapter_cues": args.read_chapter_cues,
            "reached": reached, "needs": results,
        }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
