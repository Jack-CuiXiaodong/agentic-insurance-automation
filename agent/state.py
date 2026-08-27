"""Shared, explicit Agent state.

Business state lives here as plain data -- not hidden inside prompt strings --
so deterministic business rules (risk, approval thresholds) can be reasoned
about and unit-tested independently of the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# High-level decisions the agent can reach for a claim. The identifiers stay
# English so router logic, guardrails and tests read the same in any locale;
# DECISION_LABELS is the only place they turn into user-facing Chinese.
AUTO_PROCESS = "AUTO_PROCESS"
HUMAN_REVIEW = "HUMAN_REVIEW"
REJECT = "REJECT"

DECISION_LABELS = {
    AUTO_PROCESS: "自动核赔",
    HUMAN_REVIEW: "人工核赔",
    REJECT: "拒赔",
}


def decision_label(decision: str | None) -> str:
    """User-facing Chinese label for a decision id."""
    return DECISION_LABELS.get(decision or "", decision or "-")


@dataclass
class AgentState:
    task: str = ""
    claim_id: str = ""

    claim: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    claim_history: Optional[List[Dict[str, Any]]] = None
    retrieved_rules: Optional[List[Dict[str, Any]]] = None
    risk: Optional[Dict[str, Any]] = None
    decision: Optional[str] = None

    rpa_result: Optional[Dict[str, Any]] = None
    recovery_result: Optional[Dict[str, Any]] = None
    human_request: Optional[Dict[str, Any]] = None
    human_decision: Optional[str] = None  # APPROVE | REJECT | None (pending)

    executed_tools: List[str] = field(default_factory=list)
    final_summary: Optional[str] = None

    def record_tool(self, name: str) -> None:
        self.executed_tools.append(name)

    def snapshot(self) -> Dict[str, Any]:
        """A JSON-friendly view for the UI / tests."""
        return {
            "task": self.task,
            "claim_id": self.claim_id,
            "claim": self.claim,
            "policy": self.policy,
            "claim_history": self.claim_history,
            "retrieved_rules": self.retrieved_rules,
            "risk": self.risk,
            "decision": self.decision,
            "rpa_result": self.rpa_result,
            "recovery_result": self.recovery_result,
            "human_request": self.human_request,
            "human_decision": self.human_decision,
            "executed_tools": self.executed_tools,
            "final_summary": self.final_summary,
        }
