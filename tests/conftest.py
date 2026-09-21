"""Offline regressions must not make accidental provider or model requests."""

import re
import zlib

import numpy as np
import pytest
from pydantic_ai.models import override_allow_model_requests

from apps.backend.hybrid_librarian import HybridLibrarian


WORDS = re.compile(r"[a-z]+")


def _terms(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.casefold()) if len(word) > 3}


class TermEmbedding:
    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(256)
        for term in _terms(text):
            vector[zlib.crc32(term.encode()) % 256] += 1
        return vector

    def passage_embed(self, documents: list[str]):
        return iter([self._vector(document) for document in documents])

    def query_embed(self, query: str):
        return iter((self._vector(query),))


class TermReranker:
    def rerank(self, query: str, documents: list[str]):
        terms = _terms(query)
        return [10.0 if terms & _terms(document) else -10.0 for document in documents]


@pytest.fixture(autouse=True)
def offline_model_requests():
    with override_allow_model_requests(False):
        yield


@pytest.fixture(autouse=True)
def reset_chat_rate_limit():
    """Give each test its own request-rate budget instead of a shared one."""
    from apps.backend.rate_limit import reset_rate_limit

    reset_rate_limit()


@pytest.fixture(autouse=True)
def unsure_turn_triage(monkeypatch):
    """Chat turns triage as unsure, offering every tool unpinned, unless a test scripts triage."""
    from src.linger.contracts.triage import TurnNeeds

    async def triage(current_line, **_):
        return TurnNeeds(book_content="unsure", memory="unsure")

    monkeypatch.setattr("apps.backend.chat_turn.triage_turn", triage)


# Loads the real models once and keeps their indexes apart from fake-built ones.
REAL_MODELS = HybridLibrarian()


@pytest.fixture(autouse=True)
def offline_retrieval_models(request, monkeypatch):
    if request.node.get_closest_marker("embeddings"):
        from src.linger.orchestration.grounding import librarian_service

        monkeypatch.setattr(librarian_service, "_embedding", REAL_MODELS._embedding_model())
        monkeypatch.setattr(librarian_service, "_reranker", REAL_MODELS._reranker_model())
        monkeypatch.setattr(librarian_service, "_indexes", REAL_MODELS._indexes)
        return
    embedding, reranker = TermEmbedding(), TermReranker()
    monkeypatch.setattr(
        HybridLibrarian, "_embedding_model", lambda self: embedding if self._embedding is None else self._embedding
    )
    monkeypatch.setattr(
        HybridLibrarian, "_reranker_model", lambda self: reranker if self._reranker is None else self._reranker
    )
