"""Model token limits must not discard decisive query or passage text."""
from types import SimpleNamespace

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers, processors


def encoder():
    tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2, "filler": 3, "decisive": 4, "question": 5}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", 1), ("[SEP]", 2)],
    )
    tokenizer.enable_truncation(max_length=32)
    calls = []

    def rerank(query, documents):
        calls.extend((query, document) for document in documents)
        return [float(4 in tokenizer.encode(query, document).ids) for document in documents]

    return SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer), rerank=rerank, calls=calls)


def test_library_truncation_reproduces_hidden_tail():
    model = encoder()
    assert model.rerank("question", ["filler " * 80 + "decisive"]) == [0.0]


@pytest.mark.parametrize("long_query", [False, True])
def test_windows_cover_tail_and_every_pair_fits(long_query):
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    query = "filler " * 80 + "decisive" if long_query else "question"
    document = "filler " * 80 + "decisive"
    scores = list(TokenWindowReranker(model).rerank(query, [document, "filler"]))
    assert scores[0] == 1.0
    tokenizer = Tokenizer.from_str(model.model.tokenizer.to_str())
    tokenizer.no_truncation()
    assert all(len(tokenizer.encode(q, d).ids) <= 32 for q, d in model.calls)
    assert any("decisive" in d for _, d in model.calls)
    if long_query:
        assert any("decisive" in q for q, _ in model.calls)
    assert model.model.tokenizer.truncation["max_length"] == 32


def test_short_inputs_are_scored_once_without_changes():
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    assert list(TokenWindowReranker(model).rerank("question", ["decisive", "filler"])) == [1.0, 0.0]
    assert model.calls == [("question", "decisive"), ("question", "filler")]


def test_long_query_with_short_passage_keeps_complete_fitting_pair():
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    query = "filler " * 20 + "decisive"
    assert list(TokenWindowReranker(model).rerank(query, ["question"])) == [1.0]
    assert model.calls == [(query, "question")]


def test_overflow_covers_intermediate_windows_not_only_the_final_tail():
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    document = "filler " * 45 + "decisive " + "filler " * 60
    assert list(TokenWindowReranker(model).rerank("question", [document])) == [1.0]
    assert len(model.calls) > 2


def test_windows_retain_unicode_and_wordpiece_text():
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    model.model.tokenizer.model = models.WordPiece(
        {"[UNK]": 0, "[CLS]": 1, "[SEP]": 2, "un": 3, "##usual": 4, "café": 5},
        unk_token="[UNK]",
    )
    wrapper = TokenWindowReranker(model)
    text = "unusual café " * 50
    windows = wrapper._windows(text, 13)
    assert len(windows) > 2
    assert all(window in text for window in windows)
    assert all(len(wrapper.tokenizer.encode(window, add_special_tokens=False).ids) <= 13 for window in windows)
    assert windows[-1].endswith("café")


def test_mixed_batch_preserves_each_fitting_pair_score_and_single_call():
    from apps.backend.rerank_windows import TokenWindowReranker

    model = encoder()
    record_call = model.rerank

    def score_full_query(query, documents):
        record_call(query, documents)
        return [float(len(query.split()) + {"question": 100, "decisive": 200}.get(document, 0)) for document in documents]

    model.rerank = score_full_query
    reranker = TokenWindowReranker(model)
    query = "filler " * 20 + "decisive"
    expected = reranker.rerank(query, ["question", "decisive"])
    model.calls.clear()
    overflow = "filler " * 80 + "decisive"
    actual = reranker.rerank(query, ["question", overflow, "decisive"])

    assert len(actual) == 3
    assert [actual[0], actual[2]] == expected
    assert [(q, d) for q, d in model.calls if d in {"question", "decisive"}] == [
        (query, "question"), (query, "decisive"),
    ]
    assert all(len(reranker.tokenizer.encode(q, d).ids) <= reranker.max_length for q, d in model.calls)
