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
            f"赔付金额 {claim.get('amount', '')} 元 自动核赔限额 人工核赔 "
            f"必需单证 发票查验 欺诈 转人工 风险等级"
        )
    trace.add(f"检索业务规则（RAG）：「{query[:34]}…」")
    rules = [r.as_dict() for r in get_retriever().search(query, k=k)]
    state.retrieved_rules = rules
    state.record_tool("search_rules")
    if rules:
        top = rules[0]
        trace.ok(f"命中 {len(rules)} 条规则；最相关：{top['source']} → {top['heading']}")
    else:
        trace.warn("未检索到匹配的规则")
    return {"query": query, "rules": rules}
