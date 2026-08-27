"""Adaptive browser recovery with Playwright.

When the brittle RPA workflow fails because the UI changed, the agent hands the
task here. Unlike the RPA path, recovery does not depend on a recorded selector.
It **inspects the live page**, enumerates the actionable controls, and picks the
one that is *semantically* equivalent to the intended action ("查验这张发票")
-- preferring accessible, role-based selectors over coordinates.

This is the concrete difference the demo is built to show:

    RPA        = deterministic, selector-bound, breaks on UI change.
    Playwright = inspects + adapts, recovers from the same UI change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from urllib.parse import urlencode

from browser.driver import page_session
from config import settings

# Words that indicate the intended "verify / submit" control, in priority order.
# Chinese first: the legacy screens this recovers against are Chinese, and a
# Latin-only list scores every Chinese label at 0 -- recovery would report "no
# semantically equivalent control found" on a page that plainly has one.
_INTENT_KEYWORDS = [
    "查验", "验真", "提交", "确认", "保存", "完成",
    "submit", "confirm", "save", "send", "complete",
]


@dataclass
class RecoveryResult:
    success: bool
    matched_label: str = ""
    steps: List[str] = field(default_factory=list)
    candidates: List[Dict[str, str]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    # PNGs of the changed screen before the click and the outcome after it.
    # Kept off as_dict(): binary never enters the JSON state.
    screenshot_before: bytes | None = field(default=None, repr=False)
    screenshot_after: bytes | None = field(default=None, repr=False)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "matched_label": self.matched_label,
            "steps": self.steps,
            "candidates": self.candidates,
            "details": self.details,
        }


def _score_label(label: str) -> int:
    text = label.lower()
    score = 0
    for i, kw in enumerate(_INTENT_KEYWORDS):
        if kw in text:
            score += len(_INTENT_KEYWORDS) - i  # earlier keyword => higher weight
    return score


def _shoot(page) -> bytes | None:
    """Best-effort page screenshot. Evidence is nice to have, never load-bearing."""
    try:
        return page.screenshot(full_page=True)
    except Exception:  # pragma: no cover - a missing screenshot must not fail a run
        return None


def _inspect_buttons(page) -> List[Dict[str, str]]:
    """Enumerate visible button-like controls with their accessible names.

    Each candidate carries its intent ``score`` so the UI can show *why* one
    control was chosen over another, instead of asking anyone to take it on faith.
    """
    buttons = []
    handles = page.query_selector_all("button, input[type=submit]")
    for h in handles:
        label = (h.inner_text() or h.get_attribute("value") or "").strip()
        if not label:
            continue
        buttons.append(
            {
                "label": label,
                "id": h.get_attribute("id") or "",
                "name": h.get_attribute("name") or "",
                "score": _score_label(label),
            }
        )
    return buttons


def recover_action(
    claim_id: str,
    amount: str,
    invoice_code: str = "",
    invoice_no: str = "",
    ui_variant: str = "v2",
    base_url: str | None = None,
    headless: bool | None = None,
) -> RecoveryResult:
    """Inspect the changed screen and complete the intended action semantically."""
    base_url = base_url or settings.legacy_base_url
    query = urlencode(
        {
            "ui": ui_variant,
            "claim_id": claim_id,
            "invoice_code": invoice_code,
            "invoice_no": invoice_no,
            "amount": amount,
        }
    )
    url = f"{base_url}/?{query}"
    result = RecoveryResult(success=False)

    with page_session(url, headless=headless) as page:
        result.steps.append("读取当前页面 DOM")
        result.screenshot_before = _shoot(page)
        candidates = _inspect_buttons(page)
        result.candidates = candidates
        if not candidates:
            result.steps.append("页面上找不到可操作控件")
            return result

        # Semantic match: pick the highest-scoring control for the submit intent.
        best = max(candidates, key=lambda c: _score_label(c["label"]))
        if _score_label(best["label"]) == 0:
            result.steps.append("未找到语义等价的控件")
            return result

        result.matched_label = best["label"]
        result.steps.append(f"语义匹配命中：「{best['label']}」")

        # Prefer an accessible, role-based selector over a brittle CSS id.
        result.steps.append("按 role=button + 可访问名称定位控件")
        page.get_by_role("button", name=best["label"]).click(timeout=3000)
        page.wait_for_selector("#result", timeout=5000)
        status = page.locator("#result").get_attribute("data-status")

        result.success = status == "VERIFIED"
        result.details = {"result_status": status, "selector_strategy": "role=button[name]"}
        result.screenshot_after = _shoot(page)
        result.steps.append("替代路径执行成功" if result.success else "操作未确认成功")
    return result
