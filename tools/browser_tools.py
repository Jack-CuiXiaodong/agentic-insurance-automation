"""Browser recovery tool -- adaptive Playwright recovery after RPA failure."""

from __future__ import annotations

from typing import Any, Dict

from agent.state import AgentState
from agent.trace import Trace
from browser.driver import BrowserUnavailable
from browser.recovery import recover_action


def browser_recover(state: AgentState, trace: Trace) -> Dict[str, Any]:
    claim = state.claim or {}
    trace.recover("启动浏览器自愈（Playwright）")
    state.record_tool("browser_recover")
    try:
        result = recover_action(
            claim_id=claim.get("claim_id", ""),
            amount=str(claim.get("amount", "")),
            invoice_code=claim.get("invoice_code", ""),
            invoice_no=claim.get("invoice_no", ""),
            ui_variant=claim.get("invoice_platform_ui", "v2"),
            headless=not state.show_browser,
            pace=state.demo_pace if state.show_browser else 0.0,
        )
    except BrowserUnavailable as exc:
        state.recovery_result = {"success": False, "steps": [str(exc)]}
        trace.fail(f"浏览器不可用：{exc}")
        return {"success": False, "error": str(exc), "browser_unavailable": True}

    state.recovery_result = result.as_dict()
    state.add_evidence("recovery_before", result.screenshot_before)
    state.add_evidence("recovery_after", result.screenshot_after)
    for step in result.steps:
        trace.ok(step) if result.success else trace.add(step)
    if result.success:
        trace.ok(f"自动化已恢复，改用「{result.matched_label}」完成查验")
    else:
        trace.fail("自愈未成功")
    return {"success": result.success, "result": result.as_dict()}
