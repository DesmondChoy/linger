"""Application trigger for capture-triggered conversational curation."""

import asyncio
import math

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

from conftest import TermEmbedding

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
                embedding=TermEmbedding(),
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
                account, captured, created=False, service=service,
                embedding=TermEmbedding(), run_loop=loop,
            )
        )
        unrelated = asyncio.run(
            curate_after_capture(
                account, captured, created=True, service=service,
                embedding=TermEmbedding(), run_loop=loop,
            )
        )

        assert replay.status == "not_triggered"
        assert unrelated.status == "no_relevant_prior_memory"
        loop.assert_not_awaited()


class ScriptedEmbedding:
    """Places each text at a fixed angle, so tests set meaning without a model."""

    def __init__(self, angles: dict[str, float]) -> None:
        self.angles = angles

    def _vector(self, text: str) -> list[float]:
        angle = math.radians(self.angles[text])
        return [math.cos(angle), math.sin(angle)]

    def passage_embed(self, documents: list[str]):
        return iter([self._vector(document) for document in documents])

    def query_embed(self, query: str):
        return iter((self._vector(query),))


def test_curation_batch_follows_meaning_not_filler_words() -> None:
    new = "since I will have a lot more tools to hold classes for others, I now need much more storage to keep these"
    # cos(angle) is the similarity to the new memory; the floor is 0.5 (60°).
    earlier = {
        "I use a wooden rib tool to smooth clay slabs before trimming them.": 30.0,
        "Ah I think I will arrange a pottery class inspired by the book Pinocchio.": 40.0,
        "My kiln maintenance notebook is in the second drawer beneath the wedging table.": 45.0,
        # Shares "have" and "keep" with the new memory, but not its meaning.
        "I want to read them again but I don't have the time": 75.0,
        "I keep a list of new words I come across.": 80.0,
    }
    with TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        account = AccountContext("account")
        service.set_capture_enabled(account, True)
        saved = {
            text: service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=text,
                    source_event_id=f"prior-{index}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            ).record
            for index, text in enumerate([*earlier, new])
        }
        loop = AsyncMock()
        loop.return_value = SimpleNamespace(status="no_change", proposal_digest=None)

        outcome = asyncio.run(
            curate_after_capture(
                account,
                saved[new],
                created=True,
                service=service,
                embedding=ScriptedEmbedding({new: 0.0, **earlier}),
                run_loop=loop,
            )
        )

        expected = [saved[text].memory_id for text in list(earlier)[:3]]
        assert outcome.memory_ids == (saved[new].memory_id, *expected)
        assert outcome.scored_count == len(earlier)
        assert [(item.memory_id, item.selected) for item in outcome.candidates] == [
            *((memory_id, True) for memory_id in expected),
            (saved["I want to read them again but I don't have the time"].memory_id, False),
            (saved["I keep a list of new words I come across."].memory_id, False),
        ]
        rib_tool = outcome.candidates[0]
        assert rib_tool.similarity == round(math.cos(math.radians(30)), 3)
        assert rib_tool.keyword_rank is None
