"""Application trigger for capture-triggered conversational curation."""

import asyncio

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.linger.orchestration.conversational_memory import curate_after_capture
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)


def test_new_capture_triggers_curation_with_new_and_relevant_prior_original() -> None:
    with TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        account = AccountContext("account")
        service.set_capture_enabled(account, True)
        prior = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I prefer mint tea while reading.",
                source_event_id="prior",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        created = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I now prefer jasmine tea while reading.",
                source_event_id="new",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        loop = AsyncMock()
        loop.return_value = SimpleNamespace(
            status="no_change",
            proposal_digest=None,
        )

        outcome = asyncio.run(
            curate_after_capture(
                account,
                created,
                created=True,
                service=service,
                run_loop=loop,
            )
        )

        assert outcome.status == "no_change"
        assert outcome.memory_ids == (created.memory_id, prior.memory_id)
        loop.assert_awaited_once_with(
            account,
            (created.memory_id, prior.memory_id),
            service=service,
        )


def test_idempotent_capture_and_unrelated_prior_memory_do_not_run_curation() -> None:
    with TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        account = AccountContext("account")
        service.set_capture_enabled(account, True)
        service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I commute by bus.",
                source_event_id="prior",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        captured = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text="I prefer jasmine tea while reading.",
                source_event_id="new",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        ).record
        loop = AsyncMock()

        replay = asyncio.run(
            curate_after_capture(
                account, captured, created=False, service=service, run_loop=loop
            )
        )
        unrelated = asyncio.run(
            curate_after_capture(
                account, captured, created=True, service=service, run_loop=loop
            )
        )

        assert replay.status == "not_triggered"
        assert unrelated.status == "no_relevant_prior_memory"
        loop.assert_not_awaited()
