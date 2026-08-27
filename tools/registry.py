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
        "Retrieve a claim record by claim_id from the insurance backend.",
        _obj({"claim_id": {"type": "string", "description": "Claim id, e.g. CLM-001"}}),
    ),
    "get_policy": Tool(
        "get_policy", insurance_tools.get_policy,
        "Retrieve the policy for the current claim (or an explicit policy_id).",
        _obj({"policy_id": {"type": "string"}}),
    ),
    "get_claim_history": Tool(
        "get_claim_history", insurance_tools.get_claim_history,
        "Retrieve prior claim history for the policy (used in risk assessment).",
        _obj({"policy_id": {"type": "string"}}),
    ),
    "search_rules": Tool(
        "search_rules", rag_tools.search_rules,
        "RAG: retrieve relevant business-rule evidence from the knowledge base.",
        _obj({"query": {"type": "string", "description": "What rules to look up"}}),
    ),
    "calculate_risk": Tool(
        "calculate_risk", risk_tools.calculate_risk,
        "Deterministically compute risk score/level and the routing decision "
        "(AUTO_PROCESS / HUMAN_REVIEW / REJECT). Call after claim, policy and rules are loaded.",
        _obj(),
    ),
    "execute_rpa": Tool(
        "execute_rpa", rpa_tools.execute_rpa,
        "Execute the deterministic RPA workflow against the legacy claim system. "
        "Use for AUTO_PROCESS claims, or after a human APPROVE.",
        _obj(),
    ),
    "browser_recover": Tool(
        "browser_recover", browser_tools.browser_recover,
        "Adaptive Playwright recovery. Use ONLY after execute_rpa failed due to a "
        "changed/broken UI selector.",
        _obj(),
    ),
    "request_human_approval": Tool(
        "request_human_approval", human_tools.request_human_approval,
        "Pause and request explicit human approval. Use for HUMAN_REVIEW decisions. "
        "Do NOT proceed to execute_rpa until a human has approved.",
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
