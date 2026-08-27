"""RPA execution tool -- deterministic automation of the legacy system.

On failure this tool does NOT raise into the agent loop; it records a structured
failure so the agent can *decide* to recover (that decision is the whole point).
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserUnavailable
from rpa.interface import RPAExecutionError
from rpa.mock_rpa import MockRPAAdapter

_adapter = MockRPAAdapter()


def execute_rpa(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    params = {
        "claim_id": claim.get("claim_id", ""),
        "amount": claim.get("amount", ""),
        # The legacy system's *current* UI state (v1 original, v2 changed).
        "ui_variant": claim.get("legacy_ui_variant", "v1"),
    }
    trace.add(f"Executing RPA workflow 'submit_claim' via {_adapter.name}")
    state.record_tool("execute_rpa")
    try:
        result = _adapter.execute_workflow("submit_claim", params)
        state.rpa_result = result.as_dict()
        trace.ok(f"RPA completed ({result.details.get('result_status')})")
        return {"success": True, "result": result.as_dict()}
    except BrowserUnavailable as exc:
        state.rpa_result = {"success": False, "workflow": "submit_claim", "message": str(exc)}
        trace.fail(f"Browser unavailable: {exc}")
        return {"success": False, "error": str(exc), "browser_unavailable": True}
    except RPAExecutionError as exc:
        state.rpa_result = {"success": False, "workflow": "submit_claim", "message": str(exc)}
        trace.fail(f"RPA failed: {exc}")
        return {"success": False, "error": str(exc)}
