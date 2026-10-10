"""RPA execution tool -- deterministic automation of the invoice platform.

On failure this tool does NOT raise into the agent loop; it records a structured
failure so the agent can *decide* to recover (that decision is the whole point).
"""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserSession, BrowserUnavailable
from rpa.interface import RPAExecutionError
from rpa.mock_rpa import WORKFLOW
from rpa.provider import get_adapter

_adapter = get_adapter()


def _on_located_factory(state: AgentState):
    """Refresh the recorded fingerprint for this element right before the
    brittle click. Cheap insurance: if someone *does* re-record against a new
    UI later, the baseline should reflect the control RPA actually used, not
    whatever happened to be there when the demo data file was written."""
    def _on_located(locator) -> None:
        try:
            from browser import fingerprint
            from browser.healing import HealStore

            store: HealStore = state.runtime.get("heal_store") or HealStore()
            fp = fingerprint.capture(locator)
            store.record("verify_invoice:#verify-invoice-btn", fp)
        except Exception:  # pragma: no cover - never let bookkeeping break a run
            pass
    return _on_located


def execute_rpa(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    params = {
        "claim_id": claim.get("claim_id", ""),
        "invoice_code": claim.get("invoice_code", ""),
        "invoice_no": claim.get("invoice_no", ""),
        "amount": claim.get("amount", ""),
        # The platform's *current* UI state (v1 original, v2/v3 redesigned).
        "ui_variant": claim.get("invoice_platform_ui", "v1"),
        "headless": not state.show_browser,
        "pace": state.demo_pace if state.show_browser else 0.0,
    }
    if getattr(_adapter, "accepts_selector_hint", False):
        from browser.healing import HealStore
        from browser.recovery import VERIFY_INVOICE

        store = state.runtime.get("heal_store") or HealStore()
        approved = store.approved_selector(VERIFY_INVOICE.key)
        if approved:
            params["selector"] = approved
            trace.add(f"把人工批准过的修复交给 RPA：{approved}")
    trace.add(f"执行 RPA 流程「发票查验」（{_adapter.name}）")
    state.record_tool("execute_rpa")

    kwargs: Dict[str, Any] = {}
    if getattr(_adapter, "supports_shared_page", False):
        # Open the browser *before* the attempt, not around it: on failure the
        # page must stay open, exactly where it broke, for browser_recover to
        # pick up in place. A context manager that closes on exit cannot do
        # that -- lifecycle has to live on state.runtime instead.
        session = state.runtime.get("browser_session")
        if session is None:
            session = BrowserSession(headless=params["headless"])
            state.runtime["browser_session"] = session
        try:
            url = _rpa_url(params)
            session.open(url)
        except BrowserUnavailable as exc:
            state.rpa_result = {
                "success": False, "workflow": WORKFLOW, "message": str(exc),
                "browser_unavailable": True,
            }
            trace.fail(f"浏览器不可用：{exc}")
            return {"success": False, "error": str(exc), "browser_unavailable": True}
        kwargs = {"page": session.page, "on_located": _on_located_factory(state)}

    try:
        result = _adapter.execute_workflow(WORKFLOW, params, **kwargs)
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


def _rpa_url(params: Dict[str, Any]) -> str:
    from config import settings
    from rpa.mock_rpa import build_url

    return build_url(settings.legacy_base_url, params)
