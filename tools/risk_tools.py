"""Risk tool -- deterministic risk scoring + routing decision.

The score and the decision come from ``risk.engine`` (explicit business logic),
never from the LLM. The LLM may *explain* the result, but this tool is the
source of truth.
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from risk.engine import assess_risk, decide


def calculate_risk(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    policy = state.policy or {}
    history = state.claim_history or []

    risk = assess_risk(claim, policy, history)
    decision = decide(claim, policy, risk)

    state.risk = risk
    state.decision = decision["decision"]
    state.record_tool("calculate_risk")

    trace.add(f"Risk score: {risk['risk_score']}/100 ({risk['risk_level']})")
    marker_msg = f"Decision: {decision['decision']}"
    if decision["decision"] == "AUTO_PROCESS":
        trace.ok(marker_msg)
    else:
        trace.warn(marker_msg)
    return {"risk": risk, "decision": decision["decision"], "reasons": decision["reasons"]}
