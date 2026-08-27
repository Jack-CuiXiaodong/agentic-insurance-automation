"""Insurance data tools (API-style access to the insurance backend)."""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from insurance.facio_client import InsuranceError, get_provider


def get_claim(state: AgentState, trace: Trace, claim_id: str | None = None) -> Dict[str, Any]:
    claim_id = claim_id or state.claim_id
    trace.add(f"Retrieving claim {claim_id}")
    try:
        claim = get_provider().get_claim(claim_id)
    except InsuranceError as exc:
        trace.fail(str(exc))
        return {"error": str(exc)}
    state.claim = claim
    state.claim_id = claim["claim_id"]
    state.record_tool("get_claim")
    trace.ok(f"Claim found: {claim['currency']} {claim['amount']:,} ({claim['status']})")
    return claim


def get_policy(state: AgentState, trace: Trace, policy_id: str | None = None) -> Dict[str, Any]:
    policy_id = policy_id or (state.claim or {}).get("policy_id")
    if not policy_id:
        trace.fail("No policy_id available (retrieve the claim first)")
        return {"error": "missing policy_id"}
    trace.add(f"Retrieving policy {policy_id}")
    try:
        policy = get_provider().get_policy(policy_id)
    except InsuranceError as exc:
        trace.fail(str(exc))
        return {"error": str(exc)}
    state.policy = policy
    state.record_tool("get_policy")
    trace.ok(f"Policy {policy['status']} -- {policy['coverage']} (limit {policy['currency']} {policy['limit']:,})")
    return policy


def get_claim_history(state: AgentState, trace: Trace, policy_id: str | None = None) -> Dict[str, Any]:
    policy_id = policy_id or (state.policy or state.claim or {}).get("policy_id")
    trace.add(f"Retrieving claim history for {policy_id}")
    history = get_provider().get_claim_history(policy_id) if policy_id else []
    state.claim_history = history
    state.record_tool("get_claim_history")
    trace.ok(f"Claim history: {len(history)} prior claim(s)")
    return {"policy_id": policy_id, "history": history}
