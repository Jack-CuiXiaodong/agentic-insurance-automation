"""Human-in-the-loop tool.

This tool *pauses* the agent. It packages everything a human adjuster needs
(claim, amount, risk, decision, reasons, retrieved evidence) and records a
pending approval request. The agent must not proceed past this gate on its own.
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState, decision_label
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
        "currency": claim.get("currency", "CNY"),
        "risk_level": risk.get("risk_level", ""),
        "risk_level_label": risk.get("risk_level_label", ""),
        "plate_no": claim.get("plate_no", ""),
        "risk_score": risk.get("risk_score", ""),
        "decision": state.decision,
        "decision_label": decision_label(state.decision),
        "reasons": reasons,
        "evidence": state.retrieved_rules or [],
    }
    state.human_request = request
    state.record_tool("request_human_approval")
    trace.warn(
        f"需要核赔员人工审核 —— 报案 {request['claim_id']}"
        f"（¥{request['amount']:,}）"
    )
    return {"status": "PENDING_HUMAN_APPROVAL", "request": request}
