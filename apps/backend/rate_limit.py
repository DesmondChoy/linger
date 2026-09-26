"""Deterministic per-account request rate limiting for the chat endpoints."""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

import logfire
from typing import Annotated

from fastapi import Depends, HTTPException

from src.linger.services.memory import AccountContext

from .auth import current_account
from .telemetry import failure_attrs

MAX_REQUESTS_PER_WINDOW = 10
WINDOW_SECONDS = 60.0

_REFUSAL_DETAIL = "Too many requests. Please wait a moment and try again."


class SlidingWindowRateLimiter:
    """Tracks recent request timestamps per key over a rolling window."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._lock = Lock()
        self._requests: dict[str, deque[float]] = {}

    def check(self, key: str, now: float) -> float | None:
        """Record an allowed request, or return seconds until one frees up."""
        cutoff = now - self._window_seconds
        with self._lock:
            self._evict_stale(cutoff)
            timestamps = self._requests.setdefault(key, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self._limit:
                # Surviving timestamps sit inside the window, so this is above 0.
                return timestamps[0] + self._window_seconds - now
            timestamps.append(now)
            return None

    def reset(self) -> None:
        """Forget every recorded request."""
        with self._lock:
            self._requests.clear()

    def _evict_stale(self, cutoff: float) -> None:
        """Drop keys with no request still inside the window, bounding memory."""
        stale = [
            key for key, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for key in stale:
            del self._requests[key]


_limiter = SlidingWindowRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_SECONDS)


def reset_rate_limit() -> None:
    """Return every client to a full request budget."""
    _limiter.reset()


def enforce_chat_rate_limit(
    account: Annotated[AccountContext, Depends(current_account)],
) -> None:
    """Refuse the request before any pipeline or model work when over budget."""
    retry_after = _limiter.check(account.account_id, monotonic())
    if retry_after is None:
        return
    logfire.warning(
        "chat.rate_limit",
        **failure_attrs(
            stage="http_request",
            code="rate_limited",
            retryable=True,
            failure_type="application",
        ),
        **{"http.response.status_code": 429, "request.outcome": "rate_limited"},
    )
    raise HTTPException(
        status_code=429,
        detail=_REFUSAL_DETAIL,
        headers={"Retry-After": str(ceil(retry_after))},
    )
