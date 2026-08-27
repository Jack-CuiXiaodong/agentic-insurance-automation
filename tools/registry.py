"""Tool registry: the single catalogue the Agent selects from.

Each entry couples a callable (executed identically in both LLM modes) with an
Anthropic-style JSON schema (used only by the real-Claude backend). Keeping tools
here -- rather than hard-wiring a fixed sequence into the agent -- is what makes
RPA *one tool among several* instead of "the workflow".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from agent.state import AgentState
from agent.trace import Trace
from tools import (
    browser_tools,
    human_tools,
    insurance_tools,
    rag_tools,
    risk_tools,
    rpa_tools,
)

ToolFn = Callable[..., Dict[str, Any]]


@dataclass
class Tool:
    name: str
    fn: ToolFn
    description: str
    input_schema: Dict[str, Any]

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _obj(props: Dict[str, Any] | None = None, required: List[str] | None = None) -> Dict[str, Any]:
    return {"type": "object", "properties": props or {}, "required": required or []}


TOOLS: Dict[str, Tool] = {
    "get_claim": Tool(
        "get_claim", insurance_tools.get_claim,
        "按报案号从保司系统读取车险报案记录。",
        _obj({"claim_id": {"type": "string", "description": "报案号，例如 BX-2024-0001"}}),
    ),
    "get_policy": Tool(
        "get_policy", insurance_tools.get_policy,
        "读取当前报案对应的保单（或指定 policy_id 的保单）。",
        _obj({"policy_id": {"type": "string"}}),
    ),
    "get_claim_history": Tool(
        "get_claim_history", insurance_tools.get_claim_history,
        "读取该保单的历史出险记录（用于风险评估）。",
        _obj({"policy_id": {"type": "string"}}),
    ),
    "search_rules": Tool(
        "search_rules", rag_tools.search_rules,
        "RAG：从知识库检索适用的业务规则依据。",
        _obj({"query": {"type": "string", "description": "要检索什么规则"}}),
    ),
    "calculate_risk": Tool(
        "calculate_risk", risk_tools.calculate_risk,
        "确定性地计算风险评分/等级与核赔结论"
        "（AUTO_PROCESS 自动核赔 / HUMAN_REVIEW 人工核赔 / REJECT 拒赔）。"
        "需在报案、保单、规则都已加载后调用。",
        _obj(),
    ),
    "execute_rpa": Tool(
        "execute_rpa", rpa_tools.execute_rpa,
        "在增值税发票查验平台上执行确定性 RPA 流程，查验维修发票真伪。"
        "用于 AUTO_PROCESS 的报案，或核赔员 APPROVE 之后。",
        _obj(),
    ),
    "browser_recover": Tool(
        "browser_recover", browser_tools.browser_recover,
        "Playwright 自适应自愈。仅在 execute_rpa 因页面改版/选择器失效而失败后使用。",
        _obj(),
    ),
    "request_human_approval": Tool(
        "request_human_approval", human_tools.request_human_approval,
        "暂停并请求核赔员明确审批。用于 HUMAN_REVIEW 结论。"
        "在核赔员通过之前，不得继续调用 execute_rpa。",
        _obj(),
    ),
}


def tool_schemas() -> List[Dict[str, Any]]:
    return [t.schema() for t in TOOLS.values()]


def execute(name: str, state: AgentState, trace: Trace, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if name not in TOOLS:
        trace.fail(f"Unknown tool: {name}")
        return {"error": f"unknown tool {name}"}
    return TOOLS[name].fn(state, trace, **(arguments or {}))
