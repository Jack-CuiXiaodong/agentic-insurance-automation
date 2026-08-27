"""Adaptive browser recovery with Playwright.

When the brittle RPA workflow fails because the UI changed, the agent hands the
task here. Unlike the RPA path, recovery does not depend on a recorded selector.
It **inspects the live page**, enumerates the actionable controls, and picks the
one that is *semantically* equivalent to the intended action ("submit the
claim") -- preferring accessible, role-based selectors over coordinates.

This is the concrete difference the demo is built to show:

    RPA        = deterministic, selector-bound, breaks on UI change.
    Playwright = inspects + adapts, recovers from the same UI change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from browser.driver import page_session
from config import settings

# Words that indicate a "submit the claim" control, in priority order.
_INTENT_KEYWORDS = ["submit", "confirm", "save", "send", "complete"]


@dataclass
class RecoveryResult:
    success: bool
    matched_label: str = ""
    steps: List[str] = field(default_factory=list)
    candidates: List[Dict[str, str]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

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


def _inspect_buttons(page) -> List[Dict[str, str]]:
    """Enumerate visible button-like controls with their accessible names."""
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
            }
        )
    return buttons


def recover_submit(
    claim_id: str,
    amount: str,
    ui_variant: str = "v2",
    base_url: str | None = None,
) -> RecoveryResult:
    """Inspect the changed screen and complete the submit action semantically."""
    base_url = base_url or settings.legacy_base_url
    url = f"{base_url}/?ui={ui_variant}&claim_id={claim_id}&amount={amount}"
    result = RecoveryResult(success=False)

    with page_session(url) as page:
        result.steps.append("Inspecting current page DOM")
        candidates = _inspect_buttons(page)
        result.candidates = candidates
        if not candidates:
            result.steps.append("No actionable controls found")
            return result

        # Semantic match: pick the highest-scoring control for the submit intent.
        best = max(candidates, key=lambda c: _score_label(c["label"]))
        if _score_label(best["label"]) == 0:
            result.steps.append("No semantically equivalent control found")
            return result

        result.matched_label = best["label"]
        result.steps.append(f"Semantic match found: \"{best['label']}\"")

        # Prefer an accessible, role-based selector over a brittle CSS id.
        result.steps.append("Selecting control via role=button + accessible name")
        page.get_by_role("button", name=best["label"]).click(timeout=3000)
        page.wait_for_selector("#result", timeout=5000)
        status = page.locator("#result").get_attribute("data-status")

        result.success = status == "SUBMITTED"
        result.details = {"result_status": status, "selector_strategy": "role=button[name]"}
        result.steps.append("Alternative action executed" if result.success else "Action did not confirm")
    return result
