"""Capture a public source snapshot exactly as the runtime would retrieve it.

`connection_replay` re-opens each permitted URL and requires the returned
excerpt to be a substring of the stored `PublicSourceSnapshot.text`. That only
holds when the snapshot is rendered by the same formatter the guarded Exa
toolset uses, which prefixes labelled metadata lines before the body. Capturing
through the Exa client directly omits those lines and fails the check, so this
module reuses the harness formatter rather than re-implementing it.

Usage:

    python -m evals.synthetic_journals.capture_public_source URL --source-id ID
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime

from exa_py import AsyncExa

# Private harness helper on purpose: the stored snapshot must match the runtime
# byte for byte, and test_capture_public_source.py fails if this drifts.
from pydantic_ai_harness.exa._toolset import _format_result

from apps.backend.config import get_settings
from src.linger.orchestration.connection import _web_capability

MAX_TEXT_CHARS = 8_000


def render_snapshot(result: object) -> str:
    """Render one Exa result the way the guarded toolset renders an opened page."""
    return _format_result(result, getattr(result, "text", None))


async def capture(url: str, source_id: str) -> dict[str, object]:
    """Open one URL through the runtime's client and return snapshot fields."""
    settings = get_settings()
    key = settings.exa_api_key
    if key is None or not key.get_secret_value().strip():
        raise RuntimeError("EXA_API_KEY is required to capture a public source")
    client = AsyncExa(api_key=key.get_secret_value().strip())
    response = await client.get_contents([url], text={"max_characters": MAX_TEXT_CHARS})
    if not response.results:
        raise RuntimeError(f"no content returned for {url}")
    result = response.results[0]
    text = render_snapshot(result)
    return {
        "source_id": source_id,
        "url": result.url,
        "title": result.title or "(untitled)",
        "text": text,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = asyncio.run(capture(args.url, args.source_id))
    except (OSError, RuntimeError) as error:
        print(f"PUBLIC_SOURCE_CAPTURE_ERROR={error}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
