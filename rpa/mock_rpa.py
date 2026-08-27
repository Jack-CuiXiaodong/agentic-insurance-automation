"""Mock RPA adapter that automates the local legacy claim system.

It intentionally behaves like *classic, brittle* RPA: it drives the UI through a
single **hard-coded selector** (``#submit-claim-btn``) captured when the workflow
was first "recorded" against v1 of the legacy screen. It has no understanding of
the page -- so when the screen changes to v2 (the button becomes
``#confirm-submit-btn`` / "Confirm & Submit Claim"), the selector no longer
matches and the workflow fails with "element not found".

That failure is not a bug; it is the whole point. It is the exact class of
breakage that keeps traditional RPA fragile, and the trigger for the agent's
browser-based recovery.

README note: this is a mock adapter for a public PoC. The adapter boundary
(``RPAAdapter.execute_workflow``) is designed so a real enterprise RPA
implementation can be integrated later. It is NOT a real enterprise RPA product.
"""

from __future__ import annotations

from typing import Any, Dict

from browser.driver import BrowserUnavailable, page_session
from config import settings
from rpa.interface import RPAAdapter, RPAExecutionError, RPAResult

# The single brittle selector this "recorded" workflow depends on.
BRITTLE_SELECTOR = "#submit-claim-btn"


class MockRPAAdapter(RPAAdapter):
    name = "mock-rpa"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.legacy_base_url

    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        if workflow_name != "submit_claim":
            raise RPAExecutionError(f"Unknown RPA workflow: {workflow_name}")

        claim_id = parameters.get("claim_id", "")
        amount = parameters.get("amount", "")
        ui_variant = parameters.get("ui_variant", "v1")  # current state of legacy UI
        url = f"{self.base_url}/?ui={ui_variant}&claim_id={claim_id}&amount={amount}"

        try:
            with page_session(url) as page:
                # Classic RPA: go straight for the recorded selector, short timeout,
                # no fallback, no semantic reasoning.
                locator = page.locator(BRITTLE_SELECTOR)
                if locator.count() == 0:
                    raise RPAExecutionError(
                        f"Element not found: {BRITTLE_SELECTOR} "
                        f"(the legacy 'Submit Claim' control is missing on this screen)"
                    )
                locator.click(timeout=3000)
                page.wait_for_selector("#result", timeout=5000)
                status = page.locator("#result").get_attribute("data-status")
                return RPAResult(
                    success=True,
                    workflow=workflow_name,
                    message="Claim submitted via legacy RPA workflow.",
                    details={"selector": BRITTLE_SELECTOR, "result_status": status},
                )
        except BrowserUnavailable:
            raise
        except RPAExecutionError:
            raise
        except Exception as exc:  # a Playwright timeout on the click == selector broke
            raise RPAExecutionError(
                f"RPA workflow '{workflow_name}' failed on selector "
                f"{BRITTLE_SELECTOR}: {type(exc).__name__}"
            ) from exc
