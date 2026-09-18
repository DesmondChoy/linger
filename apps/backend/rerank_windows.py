"""Score complete text with the existing cross-encoder's actual token budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tokenizers import Tokenizer

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder


class TokenWindowReranker:
    """Aggregate overlapping local scores without changing canonical evidence."""

    def __init__(self, encoder: TextCrossEncoder) -> None:
        self.encoder = encoder
        tokenizer = encoder.model.tokenizer
        if tokenizer is None or tokenizer.truncation is None:
            raise ValueError("Reranking requires the model's configured token limit")
        self.max_length = tokenizer.truncation["max_length"]
        self.tokenizer = Tokenizer.from_str(tokenizer.to_str())
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        self.special_tokens = self.tokenizer.num_special_tokens_to_add(is_pair=True)

    def _windows(self, text: str, budget: int) -> list[str]:
        first = self.tokenizer.encode(text, add_special_tokens=False)
        if len(first.ids) <= budget:
            return [text]
        first.truncate(budget, stride=min(32, budget // 4))
        windows = []
        for encoding in [first, *first.overflowing]:
            offsets = [(start, end) for start, end in encoding.offsets if end > start]
            window = text[offsets[0][0]:offsets[-1][1]]
            # A slice beginning inside a WordPiece can tokenize differently alone.
            if len(self.tokenizer.encode(window, add_special_tokens=False).ids) > budget:
                if budget <= 1:
                    raise ValueError("A text span cannot fit the reranker token budget")
                windows.extend(self._windows(window, budget - 1))
            else:
                windows.append(window)
        return windows

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        fitting: list[int] = []
        overflowing: list[int] = []
        for index, document in enumerate(documents):
            destination = (fitting if len(self.tokenizer.encode(query, document).ids) <= self.max_length
                           else overflowing)
            destination.append(index)
        scores = [float("-inf")] * len(documents)
        if fitting:
            raw_scores = self.encoder.rerank(query, [documents[index] for index in fitting])
            for index, score in zip(fitting, raw_scores, strict=True):
                scores[index] = float(score)
        if not overflowing:
            return scores
        available = self.max_length - self.special_tokens
        query_budget = available - min(64, available // 2)
        query_windows = self._windows(query, query_budget)
        for query_window in query_windows:
            budget = available - len(self.tokenizer.encode(query_window, add_special_tokens=False).ids)
            windows: list[str] = []
            owners: list[int] = []
            for index in overflowing:
                for window in self._windows(documents[index], budget):
                    if len(self.tokenizer.encode(query_window, window).ids) > self.max_length:
                        raise ValueError("Reranker pair exceeds its token budget")
                    windows.append(window)
                    owners.append(index)
            for owner, score in zip(owners, self.encoder.rerank(query_window, windows), strict=True):
                scores[owner] = max(scores[owner], float(score))
        return scores
