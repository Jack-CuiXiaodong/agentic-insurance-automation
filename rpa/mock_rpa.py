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

from typing import Any, Dict
from urllib.parse import urlencode

from browser.driver import BrowserUnavailable, page_session
from config import settings
from rpa.interface import RPAAdapter, RPAExecutionError, RPAResult

# The single brittle selector this "recorded" workflow depends on.
BRITTLE_SELECTOR = "#verify-invoice-btn"

WORKFLOW = "verify_invoice"


class MockRPAAdapter(RPAAdapter):
    name = "mock-rpa"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.legacy_base_url

    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        if workflow_name != WORKFLOW:
            raise RPAExecutionError(f"未知的 RPA 流程：{workflow_name}")

        query = urlencode(
            {
                # The platform's *current* UI state (v1 original, v2 redesigned).
                "ui": parameters.get("ui_variant", "v1"),
                "claim_id": parameters.get("claim_id", ""),
                "invoice_code": parameters.get("invoice_code", ""),
                "invoice_no": parameters.get("invoice_no", ""),
                "amount": parameters.get("amount", ""),
            }
        )
        url = f"{self.base_url}/?{query}"

        try:
            with page_session(url) as page:
                # Classic RPA: go straight for the recorded selector, short timeout,
                # no fallback, no semantic reasoning.
                locator = page.locator(BRITTLE_SELECTOR)
                if locator.count() == 0:
                    raise RPAExecutionError(
                        f"元素未找到：{BRITTLE_SELECTOR}"
                        f"（该页面上已不存在原「查验」按钮）"
                    )
                locator.click(timeout=3000)
                page.wait_for_selector("#result", timeout=5000)
                status = page.locator("#result").get_attribute("data-status")
                return RPAResult(
                    success=True,
                    workflow=workflow_name,
                    message="维修发票已通过查验平台验真。",
                    details={"selector": BRITTLE_SELECTOR, "result_status": status},
                )
        except BrowserUnavailable:
            raise
        except RPAExecutionError:
            raise
        except Exception as exc:  # a Playwright timeout on the click == selector broke
            raise RPAExecutionError(
                f"RPA 流程「{workflow_name}」在选择器 {BRITTLE_SELECTOR} 上失败："
                f"{type(exc).__name__}"
            ) from exc
