"""System prompt and state rendering for the real-Claude backend."""

from __future__ import annotations

import json
from typing import Any

from agent.state import AgentState

SYSTEM_PROMPT = """\
You are an insurance claim automation agent. You ORCHESTRATE tools; you do not \
guess business outcomes.

Operating rules:
1. Gather data before deciding: retrieve the claim, its policy, and claim \
history, then retrieve governing business rules via RAG (search_rules).
2. The risk score and the routing decision are computed by a deterministic tool \
(calculate_risk). Treat its `decision` as authoritative. Do NOT invent a risk \
score or override the decision.
3. Route execution by the decision:
   - AUTO_PROCESS: run execute_rpa against the legacy system.
   - HUMAN_REVIEW: call request_human_approval and STOP. Never call execute_rpa \
until a human has approved. Human approval must not be bypassed.
   - REJECT: stop; the claim cannot proceed.
4. If execute_rpa fails because a UI selector no longer matches, call \
browser_recover to adapt and complete the action. Use browser_recover only after \
an RPA failure.
5. Call exactly one tool per step. When no tool is needed, give a short final \
summary of what happened and why.

You will be shown the task and a snapshot of the current state each step. Choose \
the single best next tool, or finish."""


def render_state(state: AgentState) -> str:
    """A compact, model-friendly snapshot of where things stand."""
    def brief(d: Any, keys: list[str]) -> dict:
        d = d or {}
        return {k: d.get(k) for k in keys if k in d}

    snap = {
        "task": state.task,
        "claim": brief(state.claim, ["claim_id", "policy_id", "amount", "currency",
                                     "status", "documents", "fraud_flag", "legacy_ui_variant"]),
        "policy": brief(state.policy, ["policy_id", "status", "coverage", "limit", "deductible"]),
        "claim_history_count": len(state.claim_history) if state.claim_history is not None else None,
        "retrieved_rules": [f"{r['source']}: {r['heading']}" for r in (state.retrieved_rules or [])],
        "risk": state.risk,
        "decision": state.decision,
        "rpa_result": brief(state.rpa_result, ["success", "message"]),
        "recovery_result": brief(state.recovery_result, ["success", "matched_label"]),
        "human_approval_requested": state.human_request is not None,
        "human_decision": state.human_decision,
        "executed_tools": state.executed_tools,
    }
    return (
        f"TASK: {state.task}\n\nCURRENT STATE:\n"
        + json.dumps(snap, ensure_ascii=False, indent=2, default=str)
        + "\n\nChoose the single best next tool, or finish with a short summary."
    )
