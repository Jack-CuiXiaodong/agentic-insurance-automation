"""Real-browser end-to-end tests for the healing pipeline.

Skipped outright if Playwright/Chromium is not available on this machine --
these prove the pipeline against the actual mock platform, not a stand-in for
one, and that requires a real browser. Every ``HealStore`` here is pointed at
``tmp_path``, never the real ``data/heal_runtime.json``.
"""

from __future__ import annotations

import pytest

from browser import fingerprint
from browser.driver import BrowserUnavailable, page_session
from browser.healing import HealStore
from browser.recovery import VERIFY_INVOICE, heal_on_page, legacy_keyword_score, RecoveryResult
from legacy_app import manager

CLAIM = {"claim_id": "BX-2024-0003", "invoice_code": "033002100286",
         "invoice_no": "47715630", "amount": "4200"}
QUERY = "&".join(f"{k}={v}" for k, v in CLAIM.items())


def _browser_available() -> bool:
    try:
        with page_session("data:text/html,<button>x</button>"):
            return True
    except BrowserUnavailable:
        return False


pytestmark = pytest.mark.skipif(
    not _browser_available(), reason="Playwright/Chromium not available in this environment"
)


@pytest.fixture(autouse=True)
def _legacy_app():
    manager.ensure_running()


@pytest.fixture()
def store(tmp_path):
    baseline = tmp_path / "baseline.json"
    with page_session(f"http://127.0.0.1:5001/?ui=v1&{QUERY}") as pg:
        loc = pg.locator("#verify-invoice-btn")
        fp = fingerprint.capture(loc)
    import json
    baseline.write_text(json.dumps({VERIFY_INVOICE.key: fp.as_dict()}), encoding="utf-8")
    return HealStore(path=str(tmp_path / "runtime.json"), baseline_path=str(baseline))


def test_v2_heals_in_place_after_rpa_failure(store):
    """execute_rpa's own failure path, then recovery on the *same* page."""
    with page_session(f"http://127.0.0.1:5001/?ui=v2&{QUERY}") as pg:
        locator = pg.locator("#verify-invoice-btn")
        assert locator.count() == 0  # the RPA failure this is recovering from

        result = RecoveryResult(success=False)
        heal_on_page(pg, VERIFY_INVOICE, store, result)

    assert result.success is True
    assert result.details["result_status"] == "VERIFIED"
    assert result.proposal is not None
    assert result.proposal["selector"] == "#check-invoice-btn"


def test_v3_fingerprint_method_picks_the_real_control(store):
    with page_session(f"http://127.0.0.1:5001/?ui=v3&{QUERY}") as pg:
        result = RecoveryResult(success=False)
        heal_on_page(pg, VERIFY_INVOICE, store, result)

    assert result.success is True
    assert result.matched_label == "立即校验"
    assert result.details["result_status"] == "VERIFIED"


def test_v3_legacy_method_clicks_the_decoy_draft_button():
    """Pin the failure mode this project moved away from: a positive-keyword
    scorer with no veto picks '保存草稿' because it contains '保存'."""
    with page_session(f"http://127.0.0.1:5001/?ui=v3&{QUERY}") as pg:
        cands = fingerprint.candidates(pg)
        best = max(cands, key=lambda c: legacy_keyword_score(c.fingerprint.label))
        assert best.fingerprint.label == "保存草稿"

        pg.locator(f'[data-agent-cand="{best.index}"]').click(timeout=3000)
        pg.wait_for_selector("#result", timeout=5000)
        status = pg.locator("#result").get_attribute("data-status")

    assert status == "DRAFT_SAVED"


def test_approved_proposal_is_used_directly_next_time_with_no_new_proposal(store):
    with page_session(f"http://127.0.0.1:5001/?ui=v2&{QUERY}") as pg:
        first = RecoveryResult(success=False)
        heal_on_page(pg, VERIFY_INVOICE, store, first)
    assert first.success and first.proposal is not None
    store.review(first.proposal["id"], approve=True)
    assert len(store.list_proposals()) == 1

    with page_session(f"http://127.0.0.1:5001/?ui=v2&{QUERY}") as pg:
        second = RecoveryResult(success=False)
        heal_on_page(pg, VERIFY_INVOICE, store, second)

    assert second.success is True
    assert any("L0" in step for step in second.steps)
    assert second.proposal is None  # L0 hits do not propose anything new
    assert len(store.list_proposals()) == 1  # unchanged -- no duplicate


def test_v1_success_captures_a_fingerprint_whose_action_is_verify(store):
    """Guards against the formAction trap: el.formAction falls back to the
    *current page URL* when there is no formaction attribute, which would
    silently make every captured action '/'."""
    with page_session(f"http://127.0.0.1:5001/?ui=v1&{QUERY}") as pg:
        loc = pg.locator("#verify-invoice-btn")
        fp = fingerprint.capture(loc)

    assert fp.action == "/verify"
    assert fp.action != "/"
