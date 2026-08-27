"""RAG tool -- retrieve business-rule evidence from the knowledge base."""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from rag.retriever import get_retriever


def search_rules(state: AgentState, trace: Trace, query: str | None = None, k: int = 3) -> Dict[str, Any]:
    if not query:
        # Build a sensible default query from the claim context.
        claim = state.claim or {}
        query = (
            f"claim amount {claim.get('amount', '')} auto processing limit "
            f"approval documents fraud escalation risk"
        )
    trace.add(f"Searching business rules (RAG): \"{query[:60]}...\"")
    rules = [r.as_dict() for r in get_retriever().search(query, k=k)]
    state.retrieved_rules = rules
    state.record_tool("search_rules")
    if rules:
        top = rules[0]
        trace.ok(f"Retrieved {len(rules)} rule(s); top: {top['source']} -> {top['heading']}")
    else:
        trace.warn("No matching rules retrieved")
    return {"query": query, "rules": rules}
