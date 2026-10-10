"""Regression tests for rag/evaluate.py and the MIN_SCORE refusal gate."""

from __future__ import annotations

from rag.evaluate import evaluate
from rag.retriever import LexicalRetriever, MIN_SCORE


def test_eval_metrics_do_not_regress():
    result = evaluate(k=3)
    assert result.recall_at_k == 1.0, result.misses + result.false_refusals
    assert result.mrr == 1.0
    assert result.refusal_accuracy == 1.0


def test_weather_question_returns_nothing():
    r = LexicalRetriever()
    assert r.search("今天天气怎么样？", k=3) == []


def test_min_score_actually_filters_something():
    """A regression guard on the filter itself, not just the eval harness:
    search_full (unfiltered) must return hits for the weather question that
    search (filtered) discards -- otherwise MIN_SCORE could be silently
    disconnected from search() and this file would not notice."""
    r = LexicalRetriever()
    unfiltered = r.search_full("今天天气怎么样？", k=3)
    assert unfiltered  # the lexical index has *some* nonzero-overlap noise
    assert all(h.score < MIN_SCORE for h in unfiltered)


class _NoFilterRetriever(LexicalRetriever):
    """Counterfactual: what the eval would show if nobody had added the floor
    at all. This is the test the spec calls for -- it proves refusal_accuracy
    is actually measuring MIN_SCORE, not something that would read 1.00 no
    matter what threshold (or lack of one) were in place."""

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list:
        return self.search_full(query, k=k)


def test_refusal_accuracy_is_zero_without_the_floor():
    result = evaluate(retriever=_NoFilterRetriever(), k=3)
    assert result.refusal_accuracy == 0.0
