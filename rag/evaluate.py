"""Regression harness for the retriever: recall@k, MRR, refusal accuracy.

Run standalone:  ``python -m rag.evaluate``

The point is not to prove the lexical retriever is good -- on a 12-chunk,
hand-curated knowledge base it barely has to try. The point is to have a fixed
question set (``rag/eval_set.json``) that a *future* retriever (embeddings,
hybrid search, a reranker) has to be measured against before it replaces this
one. "We swapped the backend and recall@3 held at 1.00" is a claim you can
check; "the new one feels smarter" is not.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List

from rag.retriever import LexicalRetriever, Retriever

_EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set.json")


@dataclass
class EvalResult:
    recall_at_k: float
    mrr: float
    refusal_accuracy: float
    k: int
    misses: List[dict] = field(default_factory=list)       # answerable, not recalled
    false_refusals: List[dict] = field(default_factory=list)  # answerable, retriever returned nothing
    false_answers: List[dict] = field(default_factory=list)   # should-refuse, got a hit anyway


def load_eval_set(path: str = _EVAL_SET_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def evaluate(retriever: Retriever | None = None, k: int = 3,
             eval_set: dict | None = None) -> EvalResult:
    retriever = retriever or LexicalRetriever()
    eval_set = eval_set if eval_set is not None else load_eval_set()

    answerable = eval_set.get("answerable", [])
    refuse = eval_set.get("refuse", [])

    hits = 0
    reciprocal_ranks = []
    misses: List[dict] = []
    false_refusals: List[dict] = []
    for item in answerable:
        query = item["query"]
        expected = set(item.get("expected_sources", []))
        results = retriever.search(query, k=k)
        sources = [r.source for r in results]
        rank = next((i for i, s in enumerate(sources, start=1) if s in expected), None)
        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
            if not results:
                false_refusals.append(item)
            else:
                misses.append({**item, "got_sources": sources})

    recall_at_k = hits / len(answerable) if answerable else 1.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 1.0

    false_answers: List[dict] = []
    refused_correctly = 0
    for item in refuse:
        results = retriever.search(item["query"], k=k)
        if results:
            false_answers.append({**item, "got_sources": [r.source for r in results]})
        else:
            refused_correctly += 1
    refusal_accuracy = refused_correctly / len(refuse) if refuse else 1.0

    return EvalResult(
        recall_at_k=recall_at_k, mrr=mrr, refusal_accuracy=refusal_accuracy, k=k,
        misses=misses, false_refusals=false_refusals, false_answers=false_answers,
    )


def _print_report(result: EvalResult) -> None:
    print(f"recall@{result.k}       {result.recall_at_k:.2f}")
    print(f"MRR            {result.mrr:.2f}")
    print(f"拒答正确率      {result.refusal_accuracy:.2f}")
    if result.misses:
        print("\n未命中（有结果但来源不对）：")
        for m in result.misses:
            print(f"  - {m['query']!r}  期望 {m['expected_sources']}  实得 {m['got_sources']}")
    if result.false_refusals:
        print("\n应该能答却返回空（可能是 min_score 太高或语料没覆盖）：")
        for m in result.false_refusals:
            print(f"  - {m['query']!r}  期望 {m['expected_sources']}")
    if result.false_answers:
        print("\n应该拒答却给了结果（可能是 min_score 太低）：")
        for m in result.false_answers:
            print(f"  - {m['query']!r}  实得 {m['got_sources']}")
    if not (result.misses or result.false_refusals or result.false_answers):
        print("\n全部命中，无需复核。")


if __name__ == "__main__":
    _print_report(evaluate())
