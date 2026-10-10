"""Mock RPA adapter that automates the local invoice-verification platform.

It intentionally behaves like *classic, brittle* RPA: it drives the page through
a single **hard-coded selector** (``#verify-invoice-btn``) captured when the
workflow was first "recorded" against v1 of the 查验 screen. It has no
understanding of the page -- so when the screen is redesigned to v2 (the control
becomes ``#check-invoice-btn`` / "查验发票信息"), the selector no longer matches
and the workflow fails with "元素未找到".

That failure is not a bug; it is the whole point. Invoice verification is one of
the most RPA-heavy steps in this market precisely because the platform is
web-only, and a portal redesign taking every carrier's verification bot offline
on the same morning is an ordinary event, not a hypothetical.

README note: this is a mock adapter for a public PoC. The adapter boundary
(``RPAAdapter.execute_workflow``) is designed so a real enterprise RPA
implementation (UiPath / 艺赛旗 iS-RPA / 影刀 / Automation Anywhere) can be
integrated later. It is NOT a real enterprise RPA product.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode

from browser.driver import BrowserSession, BrowserUnavailable, page_session
from config import settings
from rpa.interface import RPAAdapter, RPAExecutionError, RPAResult

# The single brittle selector this "recorded" workflow depends on.
BRITTLE_SELECTOR = "#verify-invoice-btn"

WORKFLOW = "verify_invoice"


def _shoot(page) -> bytes | None:
    """Best-effort page screenshot. Evidence is nice to have, never load-bearing."""
    try:
        return page.screenshot(full_page=True)
    except Exception:  # pragma: no cover - a missing screenshot must not fail a run
        return None


def build_url(base_url: str, parameters: Dict[str, Any]) -> str:
    """Public so callers that open the shared session themselves (rpa_tools,
    the v3-trap tests) build the exact same URL this adapter would."""
    query = urlencode(
        {
            # The platform's *current* UI state (v1 original, v2/v3 redesigned).
            "ui": parameters.get("ui_variant", "v1"),
            "claim_id": parameters.get("claim_id", ""),
            "invoice_code": parameters.get("invoice_code", ""),
            "invoice_no": parameters.get("invoice_no", ""),
            "amount": parameters.get("amount", ""),
        }
    )
    return f"{base_url}/?{query}"


class MockRPAAdapter(RPAAdapter):
    name = "mock-rpa"
    supports_shared_page = True

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.legacy_base_url

    def execute_workflow(
        self,
        workflow_name: str,
        parameters: Dict[str, Any],
        page: Any = None,
        on_located: Optional[Callable[[Any], None]] = None,
    ) -> RPAResult:
        """Run ``workflow_name``.

        ``page`` is the *optional* shared-session capability from
        ``RPAAdapter.supports_shared_page``: when given a live Playwright
        ``Page``, this method navigates it and does **not** own its lifecycle
        -- on failure the page is left exactly where it broke, open, for
        recovery to pick up in place. With no ``page`` it falls back to
        ``page_session`` and manages its own short-lived browser, same as
        before this capability existed.
        """
        if workflow_name != WORKFLOW:
            raise RPAExecutionError(f"未知的 RPA 流程：{workflow_name}")

        url = build_url(self.base_url, parameters)
        headless = parameters.get("headless", True)
        slow_mo = int(float(parameters.get("pace", 0.0)) * 1000)

        try:
            if page is not None:
                page.goto(url, wait_until="domcontentloaded")
                return self._run(workflow_name, page, on_located)
            with page_session(url, headless=headless, slow_mo=slow_mo,
                              linger_ms=slow_mo * 3) as pg:
                return self._run(workflow_name, pg, on_located)
        except BrowserUnavailable:
            raise
        except RPAExecutionError:
            raise
        except Exception as exc:  # a Playwright timeout on the click == selector broke
            raise RPAExecutionError(
                f"RPA 流程「{workflow_name}」在选择器 {BRITTLE_SELECTOR} 上失败："
                f"{type(exc).__name__}"
            ) from exc

    def _run(self, workflow_name: str, page: Any, on_located) -> RPAResult:
        # Classic RPA: go straight for the recorded selector, short timeout,
        # no fallback, no semantic reasoning.
        locator = page.locator(BRITTLE_SELECTOR)
        if locator.count() == 0:
            # Photograph the wall before walking into it. This screenshot is
            # what turns "元素未找到" from an assertion into evidence.
            raise RPAExecutionError(
                f"元素未找到：{BRITTLE_SELECTOR}"
                f"（该页面上已不存在原「查验」按钮）",
                screenshot=_shoot(page),
            )
        if on_located is not None:
            try:
                on_located(locator)
            except Exception:  # pragma: no cover - a hook must never break the run
                pass
        locator.click(timeout=3000)
        page.wait_for_selector("#result", timeout=5000)
        status = page.locator("#result").get_attribute("data-status")
        return RPAResult(
            success=True,
            workflow=workflow_name,
            message="维修发票已通过查验平台验真。",
            details={"selector": BRITTLE_SELECTOR, "result_status": status},
            screenshot=_shoot(page),
        )
