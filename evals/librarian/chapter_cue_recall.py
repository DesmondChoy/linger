"""Experiment 3: Sculptor chapter cues for book retrieval, on frozen request plans.

- `freeze` runs one production Librarian planning pass per need and stores the
  plans, so later scoring changes only what search reads.
- `propose --stage N` asks Sculptor to revise every chapter's cues from the
  earlier stages' practice outcomes and writes a proposal and readable diff.
- `approve --stage N` records the owner's approval of that exact proposal.
- `score --search S` replays the frozen plans through local retrieval only (no
  model calls) and records, per need, whether a passage containing its quote
  reaches the assessment pool under production limits. Revised cues are applied
  to a temporary copy of the corpus; the canonical corpus never changes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, UserPromptPart

from apps.backend.contracts import BookScope, EvidenceItem
from apps.backend.hybrid_librarian import HybridLibrarian
from src.linger.agents.librarian.models import BookRequestPlan, LibrarianBookRequestInput
from src.linger.agents.librarian.skills import BOOK_REQUEST
from src.linger.agents.sculptor.chapter_cue_models import (
    ChapterCueRevision,
    ChapterCueRevisionInput,
    ChapterCues,
    CueChapter,
    CueRound,
    PracticeOutcome,
    chapter_cue_errors,
)
from src.linger.corpus import registry
from src.linger.corpus.book import parse_chapter_markdown
from src.linger.corpus.units import load_units, read_unit
from src.linger.orchestration.book_evidence import evidence_record_from_item, gather_book_candidates

NEEDS = Path(__file__).with_name("chapter_cue_needs.json")
PLANS = Path(__file__).with_name("chapter_cue_plans.json")
RUNS = Path(__file__).with_name("chapter_cue_runs")
WORD_BUDGET = 60
MAX_SELECTED = 5  # Production `max_final_evidence`.
SELECTION_CONCURRENCY = 4
SEARCHES = ("today", "stage1", "stage2", "stage3")
ROUND_LABELS = {
    "stage1": "Stage 1: the book's existing cues",
    "stage2": "Stage 2: your first rewrite",
}


def _normalised(text: str) -> str:
    return " ".join(text.split())


def _needs(set_name: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    document = json.loads(NEEDS.read_text(encoding="utf-8"))
    return document, document[set_name]["needs"]


def _read(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(RUNS.parent)}; run the earlier step first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validated_revision(proposal: Path) -> ChapterCueRevision:
    """Hold an approved revision to the same coverage and budget as a fresh proposal."""
    document = _needs("practice")[0]
    revision = ChapterCueRevision.model_validate(_read(proposal)["revision"])
    chapters = [unit.chapter_number for unit in load_units(registry.CORPORA[document["work_id"]])]
    errors = chapter_cue_errors(revision, chapters, WORD_BUDGET)
    if errors:
        raise SystemExit(f"{proposal.name} is invalid: " + "; ".join(errors))
    return revision


def approved_sha256(stage: int) -> str:
    """Return the hash of a stage's proposal only when the owner approved exactly it."""
    proposal = RUNS / f"stage{stage}-proposal.json"
    approval = _read(RUNS / f"stage{stage}-approval.json")
    if approval["proposal_sha256"] != _sha256(proposal):
        raise SystemExit(f"stage{stage}-proposal.json changed after approval; approve it again.")
    return approval["proposal_sha256"]


def approved_cues(stage: int) -> dict[int, ChapterCues]:
    approved_sha256(stage)
    revision = _validated_revision(RUNS / f"stage{stage}-proposal.json")
    return {chapter.chapter_number: chapter for chapter in revision.chapters}


def _identity(search: str) -> dict[str, str | None]:
    """What a score depends on, so later steps can refuse stale results."""
    return {
        "needs_sha256": _sha256(NEEDS),
        "plans_sha256": _sha256(PLANS),
        "proposal_sha256": approved_sha256(int(search[-1])) if search in ("stage2", "stage3") else None,
    }


def _practice_results(search: str) -> list[dict[str, object]]:
    """Return practice results only when they came from the current needs, plans, and proposal."""
    recorded = _read(RUNS / f"{search}-practice.json")
    if recorded.get("identity") != _identity(search):
        raise SystemExit(f"{search}-practice.json is stale; score it again.")
    practice_ids = [need["id"] for need in _needs("practice")[1]]
    if [result["id"] for result in recorded["needs"]] != practice_ids:
        raise SystemExit(f"{search}-practice.json does not cover every practice need.")
    return recorded["needs"]


def _sealed() -> bool:
    return (RUNS / "sealed-lock.json").exists()


@contextmanager
def revised_corpus(work_id: str, cues: dict[int, ChapterCues]) -> Iterator[None]:
    """Serve a temporary corpus copy whose chapter metadata carries revised cues."""
    registration = registry.CORPORA[work_id]
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / registration.root.name
        shutil.copytree(registration.root, root)
        fields = ("routing_description", "characters", "retrieval_cues")
        for path in sorted((root / "chapters").glob("*.md")):
            metadata, body = parse_chapter_markdown(path.read_text(encoding="utf-8"))
            revised = cues[metadata.chapter_number]
            metadata = metadata.model_copy(update={field: getattr(revised, field) for field in fields})
            front_matter = json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2)
            path.write_text(f"---\n{front_matter}\n---\n\n{body}", encoding="utf-8", newline="\n")
        catalog_path = root / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for row in catalog["chapters"]:
            revised = cues[row["chapter_number"]]
            row.update(routing_description=revised.routing_description,
                       characters=list(revised.characters), retrieval_cues=list(revised.retrieval_cues))
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        revised_registration = replace(registration, root=root)
        for unit in load_units(revised_registration):
            read_unit(revised_registration, unit)
        with patch.dict(registry.CORPORA, {work_id: revised_registration}):
            yield


def _pools(set_name: str, search: str) -> list[tuple[dict[str, object], BookRequestPlan, LibrarianBookRequestInput, tuple[EvidenceItem, ...]]]:
    """Gather each need's assessment pool for one search, exactly as production would."""
    document, needs = _needs(set_name)
    plans = json.loads(PLANS.read_text(encoding="utf-8"))["plans"]
    scope = BookScope(
        work_id=document["work_id"], book_version_id=document["book_version_id"],
        chapter_max=document["chapter_max"],
    )
    librarian = HybridLibrarian(read_chapter_cues=search != "today")
    cues = approved_cues(int(search[-1])) if search in ("stage2", "stage3") else None
    pools = []
    with revised_corpus(document["work_id"], cues) if cues else nullcontext():
        for need in needs:
            plan = BookRequestPlan.model_validate(plans[need["id"]])
            request = LibrarianBookRequestInput(current_line=need["question"])
            pools.append((need, plan, request, gather_book_candidates(
                plan, request, book_scopes=(scope,), librarian=librarian,
            )))
    return pools


def _containing(need: dict[str, object], items: Iterable[EvidenceItem]) -> list[str]:
    quote = _normalised(need["quote"])
    return [item.evidence_id for item in items if quote in _normalised(item.excerpt)]


def score(set_name: str, search: str) -> list[dict[str, object]]:
    results = []
    for need, _, _, pool in _pools(set_name, search):
        found = _containing(need, pool)
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


async def select(set_name: str, search: str) -> list[dict[str, object]]:
    """Run the production Librarian selection once per need and store it.

    A need passes when a selected passage contains its quote. Selections are
    never re-run, so a condition cannot be re-sampled until it looks better.
    """
    from apps.backend.config import get_settings
    from apps.backend.telemetry import configure_telemetry
    from src.linger.agents.librarian.prompt import PROMPT_FINGERPRINT
    from src.linger.orchestration.evidence_strength import assess_book_evidence

    output = RUNS / f"{search}-{set_name}-selected.json"
    if output.exists():
        raise SystemExit(f"{output.name} exists; each selection runs once.")
    lock = output.with_suffix(".lock")
    try:
        lock.open("x").close()
    except FileExistsError:
        raise SystemExit(f"{lock.name} exists: another selection is running, or one stopped; "
                         "remove the lock once nothing is running.") from None
    try:
        return await _select(set_name, search, output)
    finally:
        lock.unlink(missing_ok=True)


def _pool_sha256(pool: Iterable[EvidenceItem]) -> str:
    return hashlib.sha256(json.dumps(
        [(item.evidence_id, item.excerpt) for item in pool], ensure_ascii=False,
    ).encode()).hexdigest()


async def _select(set_name: str, search: str, output: Path) -> list[dict[str, object]]:
    """Checkpoint each need as it finishes; a resumed run never re-samples a finished need."""
    from apps.backend.config import get_settings
    from apps.backend.telemetry import configure_telemetry
    from src.linger.agents.librarian.prompt import PROMPT_FINGERPRINT
    from src.linger.orchestration.evidence_strength import assess_book_evidence

    identity = _identity(search)
    pools = _pools(set_name, search)
    checkpoint = output.with_suffix(".partial.jsonl")
    done = {}
    if checkpoint.exists():
        done = {record["id"]: record for record in map(json.loads, checkpoint.read_text(encoding="utf-8").splitlines())}
        current = {need["id"]: _pool_sha256(pool) for need, _, _, pool in pools}
        if any(record["pool_sha256"] != current[need_id] for need_id, record in done.items()):
            raise SystemExit(f"{checkpoint.name} came from different retrieval; it cannot be resumed.")
    configure_telemetry()
    slots = asyncio.Semaphore(SELECTION_CONCURRENCY)

    async def run(need, plan, request, pool) -> dict[str, object]:
        if need["id"] in done:
            return done[need["id"]]
        decision, error, responses = None, None, []
        if pool:
            async with slots:
                with capture_run_messages() as messages:
                    try:
                        decision = await assess_book_evidence(
                            plan, tuple(evidence_record_from_item(item) for item in pool),
                            original_request=request, max_evidence_records=MAX_SELECTED,
                        )
                    except Exception as failure:
                        error = f"{type(failure).__name__}: {failure}"[:500]
                responses = [message for message in messages if isinstance(message, ModelResponse)]
        selected = decision.relevant_evidence_ids if decision else ()
        by_id = {item.evidence_id: item for item in pool}
        record = {
            "id": need["id"],
            "chapter": need["chapter"],
            "passed": bool(_containing(need, (by_id[evidence_id] for evidence_id in selected))),
            "reached": bool(_containing(need, pool)),
            "selected": list(selected),
            "evidence_strength": decision.evidence_strength if decision else "none",
            "strength_reason": decision.strength_reason if decision else None,
            "limitations": list(decision.limitations) if decision else [],
            "error": error,
            "pool": [item.evidence_id for item in pool],
            "pool_sha256": _pool_sha256(pool),
            "pool_size": len(pool),
            "pool_words": sum(len(item.excerpt.split()) for item in pool),
            "selected_words": sum(len(by_id[evidence_id].excerpt.split()) for evidence_id in selected),
            "model_calls": len(responses),
            "input_tokens": sum(response.usage.input_tokens for response in responses),
            "output_tokens": sum(response.usage.output_tokens for response in responses),
        }
        with checkpoint.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    results = list(await asyncio.gather(*(run(*entry) for entry in pools)))
    output.write_text(json.dumps({
        "set": set_name, "search": search, "identity": identity,
        "model": get_settings().linger_model,
        "prompt_template_id": PROMPT_FINGERPRINT.template_id,
        "prompt_digest": PROMPT_FINGERPRINT.digest,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": sum(result["passed"] for result in results),
        "needs": results,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checkpoint.unlink()
    return results


def revision_input(stage: int) -> ChapterCueRevisionInput:
    """Build Sculptor's task from the book and every earlier practice stage."""
    document, practice = _needs("practice")
    registration = registry.CORPORA[document["work_id"]]
    current = approved_cues(stage - 1) if stage > 2 else None
    chapters = []
    for unit in load_units(registration):
        _, markdown = read_unit(registration, unit)
        chapters.append(CueChapter(
            chapter_number=unit.chapter_number, title=unit.title,
            text=markdown.split("\n\n", 1)[1],
            cues=current[unit.chapter_number] if current else ChapterCues(
                chapter_number=unit.chapter_number, routing_description=unit.routing_description,
                characters=unit.characters, retrieval_cues=unit.retrieval_cues,
            ),
        ))
    questions = {need["id"]: need["question"] for need in practice}
    rounds = []
    for earlier in range(1, stage):
        results = _practice_results(f"stage{earlier}")
        patterns = (
            _read(RUNS / f"stage{earlier}-proposal.json")["revision"]["failure_patterns"]
            if earlier > 1 else ()
        )
        rounds.append(CueRound(
            label=ROUND_LABELS[f"stage{earlier}"], failure_patterns=tuple(patterns),
            outcomes=tuple(PracticeOutcome(
                need_id=result["id"], question=questions[result["id"]],
                target_chapter=result["chapter"], reached=result["reached"],
                chapters_returned=tuple(result["pool_chapters"]),
            ) for result in results),
        ))
    return ChapterCueRevisionInput(
        book_title=registration.book.title, word_budget=WORD_BUDGET,
        chapters=tuple(chapters), rounds=tuple(rounds),
    )


def _diff(task: ChapterCueRevisionInput, revision: ChapterCueRevision, stage: int) -> str:
    revised = {chapter.chapter_number: chapter for chapter in revision.chapters}
    lines = [
        f"# Stage {stage} chapter-cue proposal: {task.book_title}", "",
        f"Word budget: {task.word_budget} per chapter. Approve with "
        f"`uv run python -m evals.librarian.chapter_cue_recall approve --stage {stage}`.", "",
        "## Failure patterns Sculptor named", "",
        *(f"- {pattern}" for pattern in revision.failure_patterns), "",
    ]
    for chapter in task.chapters:
        before, after = chapter.cues, revised[chapter.chapter_number]
        lines += [f"## Chapter {chapter.chapter_number}: {chapter.title}", ""]
        for label, field in (("Description", "routing_description"), ("Characters", "characters"),
                             ("Cues", "retrieval_cues")):
            old, new = getattr(before, field), getattr(after, field)
            old, new = (old, new) if isinstance(old, str) else ("; ".join(old), "; ".join(new))
            lines.append(f"- **{label}:** {new}" if old == new else
                         f"- **{label}:** ~~{old}~~ → {new}")
        lines += [f"- Words: {before.word_count} → {after.word_count}", ""]
    return "\n".join(lines)


async def propose(stage: int) -> None:
    from apps.backend.config import get_settings
    from apps.backend.telemetry import configure_telemetry
    from src.linger.orchestration.chapter_cues import PROMPT_FINGERPRINT, propose_chapter_cues

    if _sealed():
        raise SystemExit("The sealed set has been scored; stages are frozen.")
    if (RUNS / f"stage{stage}-approval.json").exists():
        raise SystemExit(f"Stage {stage} is already approved.")
    if stage == 3:
        _check_stop_rule()
    task = revision_input(stage)
    configure_telemetry()
    input_sha256 = hashlib.sha256(task.model_dump_json().encode()).hexdigest()
    with capture_run_messages() as messages:
        try:
            revision = await propose_chapter_cues(task)
        except Exception as error:
            _record_attempt(stage, input_sha256, messages, f"{type(error).__name__}: {error}")
            raise
    _record_attempt(stage, input_sha256, messages, None)
    proposal = RUNS / f"stage{stage}-proposal.json"
    proposal.write_text(json.dumps({
        "stage": stage,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": get_settings().linger_model,
        "prompt_template_id": PROMPT_FINGERPRINT.template_id,
        "prompt_digest": PROMPT_FINGERPRINT.digest,
        "input_sha256": input_sha256,
        "revision": revision.model_dump(mode="json"),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    review = RUNS / f"stage{stage}-proposal.md"
    review.write_text(_diff(task, revision, stage) + "\n", encoding="utf-8")
    print(f"Wrote {proposal.name} and {review.name} for review.")


def _record_attempt(stage: int, input_sha256: str, messages: list, error: str | None) -> None:
    """Keep every Sculptor attempt, failed or not, with each answer and each retry request."""
    turns = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                turns.append({"part": "input", "input_sha256": input_sha256})
            elif isinstance(part, ToolCallPart):
                turns.append({"part": "answer", "args": part.args_as_dict()})
            elif isinstance(part, RetryPromptPart):
                turns.append({"part": "retry_request", "content": part.model_response()})
            elif isinstance(part, TextPart):
                turns.append({"part": "text", "content": part.content})
    attempts = RUNS / f"stage{stage}-attempts"
    attempts.mkdir(exist_ok=True)
    number = len(list(attempts.glob("attempt-*.json"))) + 1
    (attempts / f"attempt-{number}.json").write_text(json.dumps({
        "stage": stage,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "failed" if error else "succeeded",
        "error": error,
        "turns": turns,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Recorded {attempts.name}/attempt-{number}.json ({'failed' if error else 'succeeded'}).")


def _check_stop_rule() -> None:
    """The loop stops when Stage 2 brings no net practice gain or loses a Stage 1 success."""
    before = {result["id"] for result in _practice_results("stage1") if result["reached"]}
    after = {result["id"] for result in _practice_results("stage2") if result["reached"]}
    if before - after or len(after) <= len(before):
        raise SystemExit(
            f"Stop rule: Stage 2 reached {len(after)} against Stage 1's {len(before)}, "
            f"losing {sorted(before - after)}. The loop stops after Stage 2."
        )


def _approver() -> str:
    return subprocess.run(
        ["git", "config", "user.name"], capture_output=True, text=True, check=False,
    ).stdout.strip() or "unknown"


def approve(stage: int) -> None:
    if _sealed():
        raise SystemExit("The sealed set has been scored; stages are frozen.")
    proposal = RUNS / f"stage{stage}-proposal.json"
    _validated_revision(proposal)
    approver = _approver()
    (RUNS / f"stage{stage}-approval.json").write_text(json.dumps({
        "stage": stage,
        "proposal_sha256": _sha256(proposal),
        "approved_by": approver,
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Approved stage{stage}-proposal.json as {approver}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze", help="plan every practice and sealed need once")
    for name, help_text in (("propose", "ask Sculptor to revise every chapter's cues"),
                            ("approve", "record the owner's approval of a proposal")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--stage", type=int, choices=(2, 3), required=True)
    selecting = commands.add_parser("select", help="store the Librarian's selection once per need")
    selecting.add_argument("--search", choices=SEARCHES, required=True)
    selecting.add_argument("--set", choices=("practice", "sealed"), default="practice", dest="set_name")
    scoring = commands.add_parser("score", help="score frozen plans with local retrieval")
    scoring.add_argument("--search", choices=SEARCHES, required=True)
    scoring.add_argument("--set", choices=("practice", "sealed"), default="practice", dest="set_name")
    args = parser.parse_args()
    if args.command == "freeze":
        asyncio.run(freeze())
        return
    if args.command == "propose":
        asyncio.run(propose(args.stage))
        return
    if args.command == "approve":
        approve(args.stage)
        return
    if args.command == "select":
        results = asyncio.run(select(args.set_name, args.search))
        for result in results:
            print(
                f"{result['id']} ch{result['chapter']:02d} "
                f"{'passed' if result['passed'] else 'FAILED'} "
                f"(pool {'has' if result['reached'] else 'lacks'} quote) "
                f"selected {len(result['selected'])} {result['evidence_strength']}"
                + (f"  ERROR {result['error']}" if result["error"] else "")
            )
        print(
            f"\npassed {sum(r['passed'] for r in results)}/{len(results)}; "
            f"{sum(r['model_calls'] for r in results)} model calls, "
            f"{sum(r['input_tokens'] for r in results):,} input tokens, "
            f"mean pool {sum(r['pool_words'] for r in results) / len(results):.0f} words"
        )
        return
    output = RUNS / f"{args.search}-{args.set_name}.json"
    identity = _identity(args.search)
    if args.set_name == "sealed":
        _lock_stages_for_sealed(output)
    results = score(args.set_name, args.search)
    _check_selection_still_matches(args.search, args.set_name, output, results)
    baseline_path = RUNS / f"stage1-{args.set_name}.json"
    baseline = (
        {need["id"]: need["reached"] for need in _read(baseline_path)["needs"]}
        if args.search in ("stage2", "stage3") and baseline_path.exists() else {}
    )
    for result in results:
        chapter_found = result["chapter"] in result["pool_chapters"]
        change = ("" if result["id"] not in baseline or baseline[result["id"]] == result["reached"]
                  else "  GAINED vs Stage 1" if result["reached"] else "  LOST vs Stage 1")
        print(
            f"{result['id']} ch{result['chapter']:02d} "
            f"{'reached' if result['reached'] else 'MISSED '} "
            f"pool {result['pool_size']:2d} chapters {result['pool_chapters']}"
            + ("" if result["reached"] else f"  (chapter {'in' if chapter_found else 'not in'} pool)")
            + change
        )
    reached = sum(result["reached"] for result in results)
    print(f"\nreached {reached}/{len(results)}")
    output.write_text(json.dumps({
        "set": args.set_name, "search": args.search, "identity": identity,
        "reached": reached, "needs": results,
    }, indent=2) + "\n", encoding="utf-8")


def _check_selection_still_matches(search: str, set_name: str, output: Path, results: list[dict[str, object]]) -> None:
    """Refuse to rescore a condition whose stored Librarian selection saw different passages."""
    selection = RUNS / f"{search}-{set_name}-selected.json"
    if not selection.exists():
        return
    stored = {need["id"]: need.get("pool") for need in _read(selection)["needs"]}
    previous = {need["id"]: need["pool"] for need in _read(output)["needs"]} if output.exists() else {}
    for result in results:
        expected = stored.get(result["id"]) or previous.get(result["id"])
        if expected is not None and expected != result["pool"]:
            raise SystemExit(
                f"{result['id']}: retrieval differs from the pool {selection.name} was selected from; "
                "record the change as a new condition instead."
            )


def _lock_stages_for_sealed(output: Path) -> None:
    """Run each sealed score once, against stages that can no longer change."""
    if output.exists():
        raise SystemExit(f"{output.name} exists; the sealed set runs once per search.")
    stages = {
        f"stage{stage}": approved_sha256(stage)
        for stage in (2, 3) if (RUNS / f"stage{stage}-approval.json").exists()
    }
    lock = {"needs_sha256": _sha256(NEEDS), "plans_sha256": _sha256(PLANS), "stages": stages}
    path = RUNS / "sealed-lock.json"
    if path.exists() and _read(path) != lock:
        raise SystemExit("Stages, plans, or needs changed after the sealed set was first scored.")
    path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


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


if __name__ == "__main__":
    main()
