"""Browser recovery tool -- adaptive Playwright recovery after RPA failure."""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserUnavailable
from browser.recovery import recover_submit


def browser_recover(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    trace.recover("Agent recovery started (Playwright)")
    state.record_tool("browser_recover")
    try:
        result = recover_submit(
            claim_id=claim.get("claim_id", ""),
            amount=str(claim.get("amount", "")),
            ui_variant=claim.get("legacy_ui_variant", "v2"),
        )
    except BrowserUnavailable as exc:
        state.recovery_result = {"success": False, "steps": [str(exc)]}
        trace.fail(f"Browser unavailable: {exc}")
        return {"success": False, "error": str(exc), "browser_unavailable": True}

    state.recovery_result = result.as_dict()
    for step in result.steps:
        trace.ok(step) if result.success else trace.add(step)
    if result.success:
        trace.ok(f"Automation recovered via \"{result.matched_label}\"")
    else:
        trace.fail("Recovery did not succeed")
    return {"success": result.success, "result": result.as_dict()}
