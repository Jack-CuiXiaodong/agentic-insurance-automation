"""RPA execution tool -- deterministic automation of the invoice platform.

On failure this tool does NOT raise into the agent loop; it records a structured
failure so the agent can *decide* to recover (that decision is the whole point).
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserUnavailable
from rpa.interface import RPAExecutionError
from rpa.mock_rpa import WORKFLOW, MockRPAAdapter

_adapter = MockRPAAdapter()


def execute_rpa(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    params = {
        "claim_id": claim.get("claim_id", ""),
        "invoice_code": claim.get("invoice_code", ""),
        "invoice_no": claim.get("invoice_no", ""),
        "amount": claim.get("amount", ""),
        # The platform's *current* UI state (v1 original, v2 redesigned).
        "ui_variant": claim.get("invoice_platform_ui", "v1"),
    }
    trace.add(f"执行 RPA 流程「发票查验」（{_adapter.name}）")
    state.record_tool("execute_rpa")
    try:
        result = _adapter.execute_workflow(WORKFLOW, params)
        state.rpa_result = result.as_dict()
        trace.ok(f"RPA 执行完成（{result.details.get('result_status')}）")
        return {"success": True, "result": result.as_dict()}
    except BrowserUnavailable as exc:
        # Record *why* it failed as a flag, not just in the message: the router
        # has to tell "the selector broke, try recovering" apart from "there is
        # no browser at all, recovery cannot help either", and matching on
        # message text silently stops working the moment that text is reworded.
        state.rpa_result = {
            "success": False,
            "workflow": WORKFLOW,
            "message": str(exc),
            "browser_unavailable": True,
        }
        trace.fail(f"浏览器不可用：{exc}")
        return {"success": False, "error": str(exc), "browser_unavailable": True}
    except RPAExecutionError as exc:
        state.rpa_result = {"success": False, "workflow": WORKFLOW, "message": str(exc)}
        trace.fail(f"RPA 失败：{exc}")
        return {"success": False, "error": str(exc)}
