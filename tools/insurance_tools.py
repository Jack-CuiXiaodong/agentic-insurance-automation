"""Insurance data tools (structured access to the carrier backend)."""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from insurance.carrier_client import InsuranceError, get_provider


def get_claim(state: AgentState, trace: Trace, claim_id: str | None = None) -> Dict[str, Any]:
    claim_id = claim_id or state.claim_id
    trace.add(f"读取报案 {claim_id}")
    try:
        claim = get_provider().get_claim(claim_id)
    except InsuranceError as exc:
        trace.fail(str(exc))
        return {"error": str(exc)}
    state.claim = claim
    state.claim_id = claim["claim_id"]
    state.record_tool("get_claim")
    trace.ok(f"报案已找到：{claim['plate_no']} ¥{claim['amount']:,}（{claim['status']}）")
    return claim


def get_policy(state: AgentState, trace: Trace, policy_id: str | None = None) -> Dict[str, Any]:
    policy_id = policy_id or (state.claim or {}).get("policy_id")
    if not policy_id:
        trace.fail("缺少保单号（请先读取报案）")
        return {"error": "missing policy_id"}
    trace.add(f"读取保单 {policy_id}")
    try:
        policy = get_provider().get_policy(policy_id)
    except InsuranceError as exc:
        trace.fail(str(exc))
        return {"error": str(exc)}
    state.policy = policy
    state.record_tool("get_policy")
    trace.ok(f"保单{policy['status']} —— {policy['coverage']}（保额 ¥{policy['limit']:,}，免赔 ¥{policy['deductible']:,}）")
    return policy


def get_claim_history(state: AgentState, trace: Trace, policy_id: str | None = None) -> Dict[str, Any]:
    policy_id = policy_id or (state.policy or state.claim or {}).get("policy_id")
    trace.add(f"读取保单 {policy_id} 的历史出险")
    history = get_provider().get_claim_history(policy_id) if policy_id else []
    state.claim_history = history
    state.record_tool("get_claim_history")
    trace.ok(f"历史出险：{len(history)} 笔")
    return {"policy_id": policy_id, "history": history}
