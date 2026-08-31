"""RPA execution tool -- deterministic automation of the invoice platform.

On failure this tool does NOT raise into the agent loop; it records a structured
failure so the agent can *decide* to recover (that decision is the whole point).
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserUnavailable
from rpa.factory import build_adapter
from rpa.interface import RPAExecutionError
from rpa.mock_rpa import WORKFLOW

# Which RPA product actually runs the workflow is a deployment decision
# (RPA_PROVIDER=mock | shadowbot), resolved once here. Everything below -- and
# everything above, in the agent -- is written against RPAAdapter and does not
# know or care which one it got.
_adapter = build_adapter()


def execute_rpa(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    params = {
        "claim_id": claim.get("claim_id", ""),
        "invoice_code": claim.get("invoice_code", ""),
        "invoice_no": claim.get("invoice_no", ""),
        "amount": claim.get("amount", ""),
        # The platform's *current* UI state (v1 original, v2 redesigned).
        "ui_variant": claim.get("invoice_platform_ui", "v1"),
        "headless": not state.show_browser,
        "pace": state.demo_pace if state.show_browser else 0.0,
    }
    trace.add(f"执行 RPA 流程「发票查验」（{_adapter.name}）")
    state.record_tool("execute_rpa")
    try:
        result = _adapter.execute_workflow(WORKFLOW, params)
        state.rpa_result = result.as_dict()
        state.add_evidence("rpa_success", result.screenshot)
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
        state.add_evidence("rpa_failure", getattr(exc, "screenshot", None))
        trace.fail(f"RPA 失败：{exc}")
        return {"success": False, "error": str(exc)}
