"""Tool Router.

Makes the project's core claim explicit in code: **RPA is one execution tool the
agent can route to, not the agent itself.** The same context can route to an API
tool, an RPA workflow, a browser-recovery step, or a human -- depending on the
situation.

``choose_next_tool`` is the deterministic policy. It is used directly by the
deterministic LLM backend and is what makes the human-in-the-loop flow cleanly
resumable (it re-derives the next step from :class:`AgentState`, skipping work
already done).
"""

from __future__ import annotations

from typing import Optional, Tuple

from agent.state import AUTO_PROCESS, HUMAN_REVIEW, REJECT, AgentState

# Human-readable routing table (documentation + surfaced in the UI).
ROUTES = [
    ("Need claim / policy / history data", "-> insurance API tools"),
    ("Need the governing business rules", "-> RAG (search_rules)"),
    ("Need a risk score & decision", "-> deterministic risk engine (calculate_risk)"),
    ("Decision = AUTO_PROCESS", "-> RPA (execute_rpa)"),
    ("RPA failed on a changed UI", "-> Browser recovery (browser_recover)"),
    ("Decision = HUMAN_REVIEW", "-> Human approval (request_human_approval)"),
]

# Status of the agent run.
RUNNING = "RUNNING"
AWAITING_HUMAN = "AWAITING_HUMAN"
DONE = "DONE"


def _execution_step(state: AgentState) -> Tuple[Optional[str], str]:
    """Route the *execution* phase (after a claim is approved/auto)."""
    rpa = state.rpa_result
    if rpa is None:
        return "execute_rpa", "Approved/auto -> run deterministic RPA on the legacy system"
    if rpa.get("success"):
        return None, "RPA succeeded -- nothing left to do"
    # RPA failed.
    if rpa.get("message", "").lower().find("browser unavailable") != -1 or "Browser is not" in rpa.get("message", ""):
        # Recovery also needs a browser; can't recover.
        return None, "RPA failed and browser is unavailable -- cannot recover"
    if state.recovery_result is None:
        return "browser_recover", "RPA selector broke -> adaptive Playwright recovery"
    return None, "Recovery attempt already made -- nothing left to do"


def choose_next_tool(state: AgentState) -> Tuple[Optional[str], str]:
    """Return ``(tool_name_or_None, reasoning)`` for the next agent step."""
    if state.claim is None:
        return "get_claim", "No claim loaded yet -> retrieve it"
    if state.policy is None:
        return "get_policy", "Claim loaded; need policy status & coverage"
    if state.claim_history is None:
        return "get_claim_history", "Need prior history for risk assessment"
    if state.retrieved_rules is None:
        return "search_rules", "Need governing business rules (RAG evidence)"
    if state.decision is None:
        return "calculate_risk", "Have data + rules -> compute risk & decision"

    if state.decision == REJECT:
        return None, "Decision is REJECT -- claim cannot proceed"

    if state.decision == HUMAN_REVIEW:
        if state.human_request is None:
            return "request_human_approval", "High-value/high-risk -> request human approval"
        if state.human_decision is None:
            return None, "Waiting for a human decision"
        if state.human_decision == "REJECT":
            return None, "Human rejected the claim"
        # human APPROVE -> fall through to execution
        return _execution_step(state)

    if state.decision == AUTO_PROCESS:
        return _execution_step(state)

    return None, "No further action"


def run_status(state: AgentState) -> str:
    """Classify where a finished loop stands."""
    if (
        state.decision == HUMAN_REVIEW
        and state.human_request is not None
        and state.human_decision is None
    ):
        return AWAITING_HUMAN
    return DONE
