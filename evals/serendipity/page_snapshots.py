"""Snapshot the real text of every web page the component cases cite.

Component cases describe each web page in one sentence. This fetches each
page's text through Exa, as production `get_page` would, so an experiment can
test whether thin fixtures, rather than the agent, cause web declines.

    uv run python -m evals.serendipity.page_snapshots
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from exa_py import AsyncExa

from apps.backend.config import get_settings

from .harness import load_serendipity_eval_cases

SNAPSHOTS = Path(__file__).with_name("page_snapshots.json")
# Production opens pages with this text limit (orchestration.connection).
MAX_TEXT_CHARS = 8_000


async def fetch() -> dict[str, dict[str, str]]:
    urls = sorted({
        item.evidence_id
        for case in load_serendipity_eval_cases()
        for item in case.tool_evidence
        if item.source_kind == "web"
    })
    key = get_settings().exa_api_key
    if key is None:
        raise SystemExit("EXA_API_KEY is required")
    client = AsyncExa(api_key=key.get_secret_value().strip())
    response = await client.get_contents(urls, text={"max_characters": MAX_TEXT_CHARS})
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    pages = {
        result.url: {"title": result.title or "", "text": result.text or "", "fetched_at": fetched_at}
        for result in response.results
    }
    missing = sorted(set(urls) - set(pages))
    if missing:
        print(f"not returned: {missing}")
    return pages


def main() -> None:
    pages = asyncio.run(fetch())
    SNAPSHOTS.write_text(json.dumps(pages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for url, page in pages.items():
        print(f"{len(page['text']):6} chars  {url}")


if __name__ == "__main__":
    main()
