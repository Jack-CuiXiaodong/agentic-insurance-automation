"""Ask the business-rule knowledge base a question in plain Chinese.

The contrast this demo exists to make:

    Traditional RPA -- every new process means a fresh round of requirements
    gathering. A business person explains a rule, an analyst writes it down, a
    developer reads it and turns it into an ``if`` in a script. The rule now
    lives in exactly two places: that person's head, and hard-coded logic nobody
    outside the team can read. There is a human translation step in the middle,
    and that is where the misunderstandings come from. Change the rule and the
    whole chain runs again.

    Here -- the rule *is* the Chinese document the business team wrote. The
    system reads it directly. Ask a question, get the applicable clause back in
    seconds, with its source file and the original wording.

Deliberately honest about the boundary: retrieval produces **evidence**, not
**decisions**. Money decisions (the auto-adjudication limit, the risk score) are
computed by deterministic code in :mod:`risk.engine`, whose constants are kept
in sync with the wording in the documents on purpose. Rule documents should be
easy to change; guardrails should not be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from rag.ingest import load_chunks
from rag.retriever import get_retriever

_CJK_RE = re.compile(r"[一-鿿]{2,}")
_LATIN_RE = re.compile(r"[A-Za-z0-9]{2,}")

# Questions a claims adjuster would actually ask on their first day.
SAMPLE_QUESTIONS = [
    "8 万元的车损案子要不要转人工核赔？",
    "哪些单证是必需的？",
    "发票查验不通过怎么办？",
    "什么情况下可以直接拒赔？",
    "新保就出险要注意什么？",
]


@dataclass
class Hit:
    """One retrieved clause, ready to show to a human."""

    source: str
    heading: str
    text: str
    score: float
    html: str = ""          # text with the matched terms wrapped in <mark>


@dataclass
class KnowledgeBase:
    """What the knowledge base is made of -- shown so the claim is checkable."""

    files: List[str] = field(default_factory=list)
    clauses: int = 0
    characters: int = 0


def survey() -> KnowledgeBase:
    """Describe the knowledge base as it exists on disk right now."""
    chunks = load_chunks()
    files = sorted({c.source for c in chunks})
    return KnowledgeBase(
        files=files,
        clauses=len(chunks),
        characters=sum(len(c.text) for c in chunks),
    )


def _terms(query: str) -> List[str]:
    """Query fragments worth highlighting: CJK bigrams and Latin words.

    The retriever scores on the same kind of fragments, so highlighting them is
    an honest view of *why* a clause matched -- not a second, prettier guess.
    """
    terms: List[str] = []
    for run in _CJK_RE.findall(query):
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    terms.extend(m.lower() for m in _LATIN_RE.findall(query))
    # Longest first so "自动核赔" wins over "自动" when both are present.
    return sorted(set(terms), key=len, reverse=True)


def _mark(text: str, query: str) -> str:
    """Wrap query fragments found in ``text`` with <mark>, without nesting."""
    spans: List[tuple[int, int]] = []
    low = text.lower()
    for term in _terms(query):
        start = 0
        while True:
            i = low.find(term, start)
            if i < 0:
                break
            spans.append((i, i + len(term)))
            start = i + 1

    if not spans:
        return _bold(_escape(text))

    # Merge overlaps so marks never nest.
    spans.sort()
    merged: List[List[int]] = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])

    out, cursor = [], 0
    for a, b in merged:
        out.append(_escape(text[cursor:a]))
        out.append(f"<mark>{_escape(text[a:b])}</mark>")
        cursor = b
    out.append(_escape(text[cursor:]))
    return _bold("".join(out))


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)


def _bold(html: str) -> str:
    """Render the source document's ``**emphasis**`` instead of showing asterisks.

    The clauses are Markdown the business team wrote; the emphasis is theirs and
    usually falls on the number that matters. Leaking raw ``**`` into the UI just
    makes their document look like a bug.
    """
    return _BOLD_RE.sub(r"<strong>\1</strong>", html)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ask(query: str, k: int = 4) -> List[Hit]:
    """Retrieve the clauses that apply to ``query``, best first."""
    if not query.strip():
        return []
    hits = []
    for r in get_retriever().search(query, k=k):
        hits.append(Hit(
            source=r.source,
            heading=r.heading,
            text=r.text,
            score=r.score,
            html=_mark(r.text, query),
        ))
    return hits
