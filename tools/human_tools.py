"""Human-in-the-loop tool.

This tool *pauses* the agent. It packages everything a human adjuster needs
(claim, amount, risk, decision, reasons, retrieved evidence) and records a
pending approval request. The agent must not proceed past this gate on its own.
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from risk.engine import decide


def request_human_approval(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    policy = state.policy or {}
    risk = state.risk or {}
    reasons = decide(claim, policy, risk).get("reasons", [])

    request = {
        "claim_id": claim.get("claim_id", ""),
        "amount": claim.get("amount", ""),
        "currency": claim.get("currency", "EUR"),
        "risk_level": risk.get("risk_level", ""),
        "risk_score": risk.get("risk_score", ""),
        "decision": state.decision,
        "reasons": reasons,
        "evidence": state.retrieved_rules or [],
    }
    state.human_request = request
    state.record_tool("request_human_approval")
    trace.warn(
        f"HUMAN APPROVAL REQUIRED -- claim {request['claim_id']} "
        f"({request['currency']} {request['amount']:,})"
    )
    return {"status": "PENDING_HUMAN_APPROVAL", "request": request}
