"""Five signed-up readers chatting at once against one Linger backend.

Starts the real FastAPI app under uvicorn in this process, with accounts,
transcripts, reading progress, and memories kept in a scratch directory so the
repository's own data is untouched. Five readers sign up and each holds one
conversation through `/api/chat/stream` at the same time, waiting for each
reply as a person would. `--scenario light` (the default) uses personal
reflections that need no book lookup; `--scenario spoilers` asks about books
on every turn, close to Linger's heaviest conversation. The run then checks that every reader's
`/api/history` holds only their own conversation and that no reader can
continue or delete another's.

Latency is measured at the client. Tokens and cost come from the same
content-free agent spans the backend sends to Logfire, joined to each turn by
its trace ID. When the model has no public price, pass `--usd-per-m-input`
and `--usd-per-m-output` to price the measured tokens.

This makes live model calls and spends provider tokens.

    uv run python -m evals.load.five_sessions
"""

import argparse
import asyncio
import json
import logging
import math
import re
import secrets
import socket
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import logfire
import uvicorn
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

from apps.backend import auth, main
from apps.backend.accounts import AccountStore
from apps.backend.progress_store import ReadingProgressStore
from apps.backend.transcripts import TranscriptStore
from src.linger.services.memory import MemoryPolicyService

REPORTS = Path(__file__).parent / "reports"

# Five readers each, with different lines per reader, so a leak between
# accounts would show up as another reader's words in someone's history.
SCENARIOS = {
    # Personal reflections and details used later in the same chat, from the
    # app's "Remembering you" and "Staying within the chat" paths. No message
    # asks about a book, so no turn needs a book lookup.
    "light": [
        [
            "When I stay with friends, I write their house rules in a notebook so I remember them.",
            "My book club meets on Thursday and I'm the one choosing the next book.",
            "Given what I just told you, when do I need to have decided by?",
        ],
        [
            "I learned to cook from my grandmother by watching her, never from recipes.",
            "I'm reading on the train this week, only about twenty minutes each way.",
            "With the time I just mentioned, how much could I realistically read by Friday?",
        ],
        [
            "I learned to swim as an adult by practising a little every morning before work.",
            "My niece turns ten next month and I want to give her a book I loved at her age.",
            "Based on what I said, what should I keep in mind when choosing?",
        ],
        [
            "I taught myself to play the guitar from library books after school.",
            "I still go to the library every Saturday morning; it is my favourite part of the week.",
            "On Sunday evenings I reread my old notebooks; it is a small ritual I really enjoy.",
        ],
        [
            "Before I start anything new, I read all the instructions twice so I know the rules first.",
            "I learn new skills by trying them first and only reading the manual afterwards.",
            "I keep a list of new words I come across and look them up on Sunday afternoons.",
        ],
    ],
    # One book per reader from the "Keeping spoilers out" path: every turn looks
    # up the book, so this is close to Linger's heaviest conversation.
    "spoilers": [
        [
            "I've just finished chapter 5 of Alice's Adventures in Wonderland, the one with the Caterpillar.",
            "Could you quote how Alice answers when the Caterpillar asks who she is?",
            "So what happens to Alice at the very end?",
        ],
        [
            "I've finished chapter 6 of Animal Farm.",
            "Could you quote the commandment about beds as it reads once the animals notice it has changed?",
            "Does Napoleon stay in charge right to the end?",
        ],
        [
            "I've finished chapter 4 of Pinocchio, where he meets the Talking Cricket.",
            "Could you quote what the Talking Cricket warns Pinocchio about?",
            "Does the Talking Cricket come back later in the story?",
        ],
        [
            "I've finished chapter 4 of The Story of My Life, at the water pump.",
            "Could you quote the moment at the water pump when she understands what the word means?",
            "Does she ever learn to speak out loud?",
        ],
        [
            "I've finished chapter 6 of Narrative of the Life of Frederick Douglass.",
            "Could you quote what Mr. Auld says when he forbids his wife to keep teaching him to read?",
            "Does he manage to escape in the end?",
        ],
    ],
}


@dataclass
class AgentUsage:
    role: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class UsageCollector(SpanProcessor):
    """Keep the token usage and failures each span reports, by trace."""

    def __init__(self) -> None:
        self.by_trace: dict[str, list[AgentUsage]] = {}
        self.failures: dict[str, list[str]] = {}

    def on_end(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        if span.context is None:
            return
        trace_id = format(span.context.trace_id, "032x")
        if attrs.get("status") == "failure":
            self.failures.setdefault(trace_id, []).append(
                f"{attrs.get('agent.role', span.name)}/{attrs.get('failure.stage')}: "
                f"{attrs.get('failure.category', attrs.get('failure.type'))} ({attrs.get('failure.code')})"
            )
        if "input_tokens" not in attrs:
            return
        self.by_trace.setdefault(trace_id, []).append(
            AgentUsage(
                role=str(attrs.get("agent.role")),
                model=f"{attrs.get('model.provider')}:{attrs.get('model.name')}",
                input_tokens=int(attrs.get("input_tokens") or 0),
                output_tokens=int(attrs.get("output_tokens") or 0),
                cost_usd=float(cost) if (cost := attrs.get("cost.usd")) is not None else None,
            )
        )


class ProviderStatuses(logging.Handler):
    """Count provider HTTP statuses from httpx's content-free request log."""

    LINE = re.compile(r'^HTTP Request: \w+ https?://([^/\s]+)\S* "HTTP/[\d.]+ (\d{3})')

    def __init__(self) -> None:
        super().__init__()
        self.counts: dict[str, int] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if match := self.LINE.match(record.getMessage()):
            key = f"{match[1]} {match[2]}"
            self.counts[key] = self.counts.get(key, 0) + 1


@dataclass
class Turn:
    reader: str
    index: int
    outcome: str
    started_s: float
    latency_s: float
    first_progress_s: float | None
    trace_id: str | None
    release_source: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    agent_runs: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class Reader:
    username: str
    session_id: str
    lines: list[str]
    client: httpx.AsyncClient
    turns: list[Turn] = field(default_factory=list)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _isolate_stores(directory: Path) -> None:
    main.transcript_store = TranscriptStore(directory / "transcripts.sqlite3")
    main.reading_progress_store = ReadingProgressStore(directory / "reading_progress.sqlite3")
    main.memory_service = MemoryPolicyService(directory / "memories", capture_enabled_by_default=True)
    auth.account_store = AccountStore(directory / "accounts.sqlite3")


async def _sign_up(base_url: str, username: str, lines: list[str]) -> Reader:
    client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(600))
    response = await client.post(
        "/api/auth/signup", json={"username": username, "password": secrets.token_urlsafe(16)}
    )
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return Reader(username=username, session_id=f"{username}-conversation", lines=lines, client=client)


async def _send(reader: Reader, index: int, message: str, run_started: float) -> Turn:
    started = time.perf_counter()
    first_progress: float | None = None
    outcome, trace_id, release_source = "no_result", None, None
    async with reader.client.stream(
        "POST", "/api/chat/stream", json={"session_id": reader.session_id, "message": message}
    ) as response:
        if response.status_code == 429:
            outcome = "rate_limited"
        elif response.status_code != 200:
            outcome = f"http_{response.status_code}"
        else:
            event = None
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    payload = json.loads(line.removeprefix("data: "))
                    if event == "progress" and first_progress is None:
                        first_progress = time.perf_counter() - started
                    elif event == "result":
                        trace_id = payload["trace"]["trace_id"]
                        release_source = payload["inspection"]["release"]["release_source"]
                        outcome = "declined" if release_source == "application_safe_decline" else "answered"
                    elif event == "error":
                        outcome = "failed"
                        trace_id = (payload.get("trace") or {}).get("trace_id")
    return Turn(
        reader=reader.username,
        index=index,
        outcome=outcome,
        started_s=round(started - run_started, 2),
        latency_s=round(time.perf_counter() - started, 2),
        first_progress_s=round(first_progress, 2) if first_progress is not None else None,
        trace_id=trace_id,
        release_source=release_source,
    )


async def _converse(reader: Reader, run_started: float) -> None:
    for index, message in enumerate(reader.lines):
        reader.turns.append(await _send(reader, index, message, run_started))


async def _isolation_checks(readers: list[Reader], base_url: str) -> dict[str, Any]:
    history: dict[str, Any] = {}
    for reader in readers:
        conversations = (await reader.client.get("/api/history")).json()
        saved = [turn["user_message"] for c in conversations for turn in c["turns"]]
        expected = sum(
            turn.release_source in main._TRANSCRIBED_RELEASES for turn in reader.turns
        )
        history[reader.username] = {
            "sessions": [c["session_id"] for c in conversations],
            "saved_turns": len(saved),
            "expected_saved_turns": expected,
            "only_own_session": all(c["session_id"] == reader.session_id for c in conversations),
            "only_own_lines": set(saved) <= set(reader.lines),
        }
    cross: list[dict[str, Any]] = []
    for reader, other in zip(readers, readers[1:] + readers[:1]):
        chat = await reader.client.post(
            "/api/chat", json={"session_id": other.session_id, "message": "What were we discussing?"}
        )
        delete = await reader.client.delete(f"/api/sessions/{other.session_id}")
        cross.append(
            {"reader": reader.username, "target": other.username,
             "continue_status": chat.status_code, "delete_status": delete.status_code}
        )
    async with httpx.AsyncClient(base_url=base_url) as anonymous:
        anonymous_status = (await anonymous.get("/api/history")).status_code
    passed = (
        all(h["only_own_session"] and h["only_own_lines"] and h["saved_turns"] == h["expected_saved_turns"]
            for h in history.values())
        and all(c["continue_status"] == 404 and c["delete_status"] == 404 for c in cross)
        and anonymous_status == 401
    )
    return {"passed": passed, "history": history, "cross_account": cross,
            "anonymous_history_status": anonymous_status}


def _percentile(values: list[float], share: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def _price(usages: list[AgentUsage], usd_per_m_input: float | None, usd_per_m_output: float | None) -> tuple[float | None, str]:
    if usages and all(usage.cost_usd is not None for usage in usages):
        return sum(usage.cost_usd or 0 for usage in usages), "span cost.usd"
    if usd_per_m_input is not None and usd_per_m_output is not None:
        return (
            sum(u.input_tokens for u in usages) * usd_per_m_input / 1e6
            + sum(u.output_tokens for u in usages) * usd_per_m_output / 1e6,
            "supplied per-million rates",
        )
    return None, "unpriced: pass --usd-per-m-input and --usd-per-m-output"


async def run(scenario: str, readers_count: int, turns: int, sequential: bool, usd_per_m_input: float | None, usd_per_m_output: float | None) -> dict[str, Any]:
    statuses = ProviderStatuses()
    httpx_log = logging.getLogger("httpx")
    httpx_log.addHandler(statuses)
    httpx_log.setLevel(logging.INFO)
    httpx_log.propagate = False
    collector = UsageCollector()
    logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_tracer_provider().add_span_processor(collector)
    scratch = Path(tempfile.mkdtemp(prefix="linger-load-"))
    _isolate_stores(scratch)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    run_id = secrets.token_hex(3)
    readers = [
        await _sign_up(base_url, f"load-{run_id}-{n}", lines[:turns])
        for n, lines in enumerate(SCENARIOS[scenario][:readers_count])
    ]
    run_started = time.perf_counter()
    conversations = [_converse(reader, run_started) for reader in readers]
    if sequential:
        for conversation in conversations:
            await conversation
    else:
        await asyncio.gather(*conversations)
    wall_s = time.perf_counter() - run_started
    isolation = await _isolation_checks(readers, base_url)

    for reader in readers:
        await reader.client.aclose()
    server.should_exit = True
    await serving
    logfire.force_flush()

    all_turns = [turn for reader in readers for turn in reader.turns]
    usages: list[AgentUsage] = []
    for turn in all_turns:
        turn_usage = collector.by_trace.get(turn.trace_id or "", [])
        turn.input_tokens = sum(u.input_tokens for u in turn_usage)
        turn.output_tokens = sum(u.output_tokens for u in turn_usage)
        turn.agent_runs = len(turn_usage)
        turn.failures = collector.failures.get(turn.trace_id or "", [])
        usages.extend(turn_usage)
    replied = [turn.latency_s for turn in all_turns if turn.outcome in ("answered", "declined")]
    answered = [turn.latency_s for turn in all_turns if turn.outcome == "answered"]
    first_progress = [t.first_progress_s for t in all_turns if t.first_progress_s is not None]
    cost, cost_basis = _price(usages, usd_per_m_input, usd_per_m_output)
    outcomes: dict[str, int] = {}
    for turn in all_turns:
        outcomes[turn.outcome] = outcomes.get(turn.outcome, 0) + 1

    return {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": main.settings.linger_model,
        "readers": len(readers),
        "scenario": scenario,
        "turns_per_reader": turns,
        "mode": "sequential control" if sequential else "concurrent",
        "server": "one uvicorn process, one worker, SQLite stores in a scratch directory",
        "wall_clock_s": round(wall_s, 1),
        "outcomes": outcomes,
        "release_sources": {
            source: sum(t.release_source == source for t in all_turns)
            for source in sorted({t.release_source for t in all_turns if t.release_source})
        },
        "failures": {
            failure: sum(failure in t.failures for t in all_turns)
            for failure in sorted({f for t in all_turns for f in t.failures})
        },
        "provider_http_statuses": {
            key: count for key, count in sorted(statuses.counts.items()) if not key.startswith("127.0.0.1")
        },
        "latency_s": {
            "p50": _percentile(replied, 0.5),
            "p95": _percentile(replied, 0.95),
            "max": max(replied, default=None),
            "answered_p50": _percentile(answered, 0.5),
            "answered_p95": _percentile(answered, 0.95),
            "first_progress_p50": _percentile(first_progress, 0.5),
        },
        "tokens": {
            "input": sum(u.input_tokens for u in usages),
            "output": sum(u.output_tokens for u in usages),
            "agent_runs": len(usages),
            "by_role": {
                role: {
                    "input": sum(u.input_tokens for u in usages if u.role == role),
                    "output": sum(u.output_tokens for u in usages if u.role == role),
                    "runs": sum(u.role == role for u in usages),
                }
                for role in sorted({u.role for u in usages})
            },
        },
        "cost_usd": round(cost, 4) if cost is not None else None,
        "cost_basis": cost_basis,
        "isolation": isolation,
        "turns": [asdict(turn) for turn in all_turns],
    }


def _summary(report: dict[str, Any]) -> str:
    latency = report["latency_s"]
    tokens = report["tokens"]
    total = report["readers"] * report["turns_per_reader"]
    cost = f"${report['cost_usd']:.4f}" if report["cost_usd"] is not None else report["cost_basis"]
    return "\n".join(
        [
            f"{report['readers']} readers x {report['turns_per_reader']} {report['scenario']} turns ({report['mode']}) on {report['model']}, "
            f"wall clock {report['wall_clock_s']}s",
            f"outcomes: {report['outcomes']} of {total}",
            f"latency (all replies): p50 {latency['p50']}s, p95 {latency['p95']}s, max {latency['max']}s; "
            f"answered only: p50 {latency['answered_p50']}s, p95 {latency['answered_p95']}s; "
            f"first progress p50 {latency['first_progress_p50']}s",
            f"turns with internal failures: {report['failures']}",
            f"provider HTTP statuses: {report['provider_http_statuses']}",
            f"tokens: {tokens['input']} in / {tokens['output']} out over {tokens['agent_runs']} agent runs",
            f"cost: {cost}",
            f"isolation: {'passed' if report['isolation']['passed'] else 'FAILED'}",
        ]
    )


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="light")
    parser.add_argument("--readers", type=int, default=5, choices=range(2, 6), help="readers at once")
    parser.add_argument("--turns", type=int, default=3, choices=range(1, 4), help="turns per reader")
    parser.add_argument(
        "--sequential", action="store_true", help="control run: the same readers one after another"
    )
    parser.add_argument("--usd-per-m-input", type=float)
    parser.add_argument("--usd-per-m-output", type=float)
    args = parser.parse_args()
    report = asyncio.run(run(args.scenario, args.readers, args.turns, args.sequential, args.usd_per_m_input, args.usd_per_m_output))
    REPORTS.mkdir(exist_ok=True)
    mode = "sequential" if args.sequential else "concurrent"
    path = REPORTS / f"five-sessions-{args.scenario}-{args.readers}r-{mode}-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(_summary(report))
    print(f"report: {path}")


if __name__ == "__main__":
    cli()
