"""Retrieval abstraction for the knowledge base.

The Agent must decide on **retrieved evidence**, not on the model's memory. This
module defines a small :class:`Retriever` interface and a dependency-free
:class:`LexicalRetriever` (TF-IDF cosine) as the default backend -- so the demo
runs offline with zero heavy dependencies.

A :class:`FaissRetriever` skeleton documents exactly where an embeddings + FAISS
(or any vector DB) backend plugs in. The interface never changes, so callers do
not care which backend is active.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List

from rag.ingest import Chunk, load_chunks

_LATIN_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize(text: str) -> List[str]:
    """Tokenize mixed Chinese/English text.

    Latin runs split on word boundaries as usual. Chinese has no spaces between
    words, so a Latin-only tokenizer returns *nothing* for a Chinese sentence --
    every vector comes out empty and retrieval silently returns zero hits. Each
    CJK run is therefore indexed as both single characters and adjacent-character
    bigrams, which is enough for a small curated rule base: a query for
    "自动核赔" still overlaps a rule that says "自动核赔限额", without pulling in a
    segmentation library and giving up the offline, dependency-free design.
    """
    text = text.lower()
    tokens = _LATIN_RE.findall(text)
    for run in _CJK_RE.findall(text):
        tokens.extend(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


@dataclass
class RetrievedRule:
    source: str
    heading: str
    text: str
    score: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "heading": self.heading,
            "text": self.text,
            "score": round(self.score, 4),
        }


class Retriever(ABC):
    """Every retrieval backend implements this and nothing more."""

    name: str = "abstract"

    @abstractmethod
    def search(self, query: str, k: int = 3) -> List[RetrievedRule]:
        ...


class LexicalRetriever(Retriever):
    """TF-IDF cosine retriever in pure Python -- no external services.

    Good enough for a small, curated rule base and, crucially, deterministic and
    offline. For a large corpus, switch to :class:`FaissRetriever`.
    """

    name = "lexical-tfidf"

    def __init__(self, chunks: List[Chunk] | None = None):
        self.chunks: List[Chunk] = chunks if chunks is not None else load_chunks()
        self._doc_tokens = [_tokenize(f"{c.heading} {c.text}") for c in self.chunks]
        self._idf = self._compute_idf(self._doc_tokens)
        self._doc_vecs = [self._vectorize(toks) for toks in self._doc_tokens]

    @staticmethod
    def _compute_idf(docs: List[List[str]]) -> Dict[str, float]:
        n = len(docs) or 1
        df: Counter = Counter()
        for toks in docs:
            for term in set(toks):
                df[term] += 1
        return {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def _vectorize(self, tokens: List[str]) -> Dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        length = len(tokens)
        vec = {t: (cnt / length) * self._idf.get(t, math.log(len(self.chunks) + 1) + 1.0)
               for t, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        # iterate the smaller vector
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(t, 0.0) for t, v in a.items())

    def search(self, query: str, k: int = 3) -> List[RetrievedRule]:
        qvec = self._vectorize(_tokenize(query))
        scored = []
        for chunk, dvec in zip(self.chunks, self._doc_vecs):
            score = self._cosine(qvec, dvec)
            if score > 0:
                scored.append(RetrievedRule(chunk.source, chunk.heading, chunk.text, score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]


class FaissRetriever(Retriever):  # pragma: no cover - optional heavy path
    """Skeleton: embeddings + FAISS.

    To enable, install ``faiss-cpu`` and an embedding model, build the index from
    ``load_chunks()`` in ``__init__``, and implement ``search`` to embed the
    query and run a nearest-neighbour lookup. The return type
    (``List[RetrievedRule]``) must stay identical so nothing else changes.
    """

    name = "faiss"

    def __init__(self) -> None:
        raise NotImplementedError(
            "FaissRetriever is a documented extension point. The default "
            "LexicalRetriever keeps the PoC offline and deterministic."
        )

    def search(self, query: str, k: int = 3) -> List[RetrievedRule]:
        raise NotImplementedError


_RETRIEVER_SINGLETON: Retriever | None = None


def get_retriever() -> Retriever:
    global _RETRIEVER_SINGLETON
    if _RETRIEVER_SINGLETON is None:
        _RETRIEVER_SINGLETON = LexicalRetriever()
    return _RETRIEVER_SINGLETON


def reset_retriever() -> None:
    """Drop the cached index so the next search re-reads ``knowledge/``.

    The knowledge base is a folder of Chinese Markdown the business side owns.
    Editing a rule and having the system pick it up **without a code change or a
    restart** is the point of keeping rules in documents rather than in ``if``
    statements, so the demo needs a way to prove it.
    """
    global _RETRIEVER_SINGLETON
    _RETRIEVER_SINGLETON = None
