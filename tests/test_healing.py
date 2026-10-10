"""Decision-layer tests for browser/healing.py -- no browser required.

Candidates are hand-built Fingerprint objects that reproduce exactly what the
real v2/v3 trap pages look like (see rag... er, browser/fingerprint.py's
self-check numbers in CLAUDE.md), so this file exercises the confidence gate
and the L0/L1/L2 tiering without ever opening Chromium.
"""

from __future__ import annotations

import json
import os

import pytest

from browser.fingerprint import Candidate, Fingerprint
from browser.healing import (
    AMBIGUOUS,
    HEALED,
    LOW_CONFIDENCE,
    MIN_CONFIDENCE,
    MIN_MARGIN,
    NO_CANDIDATES,
    TIER_L1,
    TIER_L2,
    HealStore,
    HealTarget,
    decide,
    keyword_score,
)
from browser.recovery import LEGACY_INTENT_KEYWORDS, VERIFY_INVOICE, legacy_keyword_score

RECORDED = Fingerprint(
    label="查验", tag="button", type="submit", role="button", action="/verify",
    fields=["amount", "claim_id", "invoice_code", "invoice_no", "status", "ui"],
    id="verify-invoice-btn", name="verify_invoice", ordinal=0,
)

V2_MATCH = Fingerprint(
    label="查验发票信息", tag="button", type="submit", role="button", action="/verify",
    fields=list(RECORDED.fields), id="check-invoice-btn", name="check_invoice", ordinal=0,
)
V2_RESET = Fingerprint(
    label="重置", tag="button", type="button", role="button", action="",
    fields=list(RECORDED.fields), id="reset-btn", name="reset", ordinal=1,
)
V3_SAVE_DRAFT = Fingerprint(
    label="保存草稿", tag="button", type="submit", role="button", action="/draft",
    fields=list(RECORDED.fields), id="save-draft-btn", name="save_draft", ordinal=0,
)
V3_REAL = Fingerprint(
    label="立即校验", tag="button", type="submit", role="button", action="/verify",
    fields=list(RECORDED.fields), id="btn-x7f2", name="submit_check", ordinal=1,
)
V3_RESET = Fingerprint(
    label="重置", tag="button", type="button", role="button", action="",
    fields=list(RECORDED.fields), id="reset-btn", name="reset", ordinal=2,
)


def _cands(*fps: Fingerprint) -> list[Candidate]:
    return [Candidate(index=i, fingerprint=fp) for i, fp in enumerate(fps)]


# ---------------------------------------------------------------------------
# Confidence gate
# ---------------------------------------------------------------------------

def test_v2_heals_with_high_confidence_and_margin():
    d = decide(VERIFY_INVOICE, _cands(V2_MATCH, V2_RESET), recorded=RECORDED)
    assert d.status == HEALED
    assert d.tier == TIER_L1
    assert d.best.fingerprint.label == "查验发票信息"
    assert d.best.similarity >= 0.8
    assert d.margin >= 0.5


def test_legacy_scorer_picks_save_draft_on_v3():
    """This is the failure mode the whole project moved away from: a
    keyword-only scorer with no veto happily matches '保存草稿' on the
    positive word '保存', scoring it *higher* than the real verify control
    because 保存 ranks earlier in the old global keyword list."""
    best = max([V3_SAVE_DRAFT, V3_REAL, V3_RESET], key=lambda fp: legacy_keyword_score(fp.label))
    assert best.label == "保存草稿"
    assert legacy_keyword_score("保存草稿") > 0
    assert legacy_keyword_score("立即校验") == 0


def test_fingerprint_decision_picks_the_real_control_on_v3():
    """The real control's form action (/verify) matches the recording; the
    decoy's (/draft) does not -- that is what fingerprint similarity sees that
    a label-only scorer cannot."""
    d = decide(VERIFY_INVOICE, _cands(V3_SAVE_DRAFT, V3_REAL, V3_RESET), recorded=RECORDED)
    assert d.status == HEALED
    assert d.best.fingerprint.label == "立即校验"
    assert d.best.breakdown["action"] == 1.0
    assert d.best.breakdown["label"] < 0.5


def test_two_identical_controls_are_ambiguous():
    twin_a = Fingerprint(label="查验", tag="button", type="submit", role="button",
                         action="/verify", fields=list(RECORDED.fields),
                         id="a", name="a", ordinal=0)
    twin_b = Fingerprint(label="查验", tag="button", type="submit", role="button",
                         action="/verify", fields=list(RECORDED.fields),
                         id="b", name="b", ordinal=1)
    d = decide(VERIFY_INVOICE, _cands(twin_a, twin_b), recorded=RECORDED)
    assert d.status == AMBIGUOUS
    assert d.margin < MIN_MARGIN


def test_unrelated_page_is_low_confidence():
    unrelated = Fingerprint(label="退出登录", tag="button", type="button", role="button",
                            action="", fields=["username"], id="logout", name="logout", ordinal=0)
    d = decide(VERIFY_INVOICE, _cands(unrelated), recorded=RECORDED)
    assert d.status == LOW_CONFIDENCE
    assert d.best.similarity < MIN_CONFIDENCE


def test_empty_page_has_no_candidates():
    d = decide(VERIFY_INVOICE, [], recorded=RECORDED)
    assert d.status == NO_CANDIDATES
    assert d.best is None


def test_l2_fallback_vetoes_negative_keywords_without_a_fingerprint():
    """No recorded fingerprint yet (first ever run) -> L2 keyword fallback.
    '保存草稿' must score 0 because 保存 is one of this target's own negative
    keywords -- a per-target veto list is the one thing the *old* global
    scorer never had, and it alone is enough to dodge this particular decoy.
    '立即校验' still contains the positive keyword '校验' as a substring, so
    L2 finds it too; L1 (fingerprint) is what is needed once the wording
    changes enough that no keyword survives at all."""
    assert keyword_score("保存草稿", VERIFY_INVOICE) == 0.0
    assert keyword_score("立即校验", VERIFY_INVOICE) > 0.0
    d = decide(VERIFY_INVOICE, _cands(V3_SAVE_DRAFT, V3_REAL), recorded=None)
    assert d.tier == TIER_L2
    assert d.status == HEALED
    assert d.best.fingerprint.label == "立即校验"


def test_l2_fallback_finds_the_real_label_when_it_is_literal():
    literal = Fingerprint(label="查验", tag="button", type="submit", role="button",
                          action="/verify", fields=[], id="x", name="x", ordinal=0)
    draft = Fingerprint(label="保存草稿", tag="button", type="submit", role="button",
                        action="/draft", fields=[], id="y", name="y", ordinal=1)
    d = decide(VERIFY_INVOICE, _cands(draft, literal), recorded=None)
    assert d.tier == TIER_L2
    assert d.status == HEALED
    assert d.best.fingerprint.label == "查验"


# ---------------------------------------------------------------------------
# HealStore
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    return HealStore(path=str(tmp_path / "runtime.json"),
                     baseline_path=str(tmp_path / "baseline.json"))


def test_runtime_fingerprint_overrides_baseline(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"k": {"label": "旧", "tag": "button", "type": "submit", "role": "button",
                          "action": "", "fields": [], "id": "", "name": "", "ordinal": 0}}),
        encoding="utf-8",
    )
    s = HealStore(path=str(tmp_path / "runtime.json"), baseline_path=str(baseline_path))
    assert s.fingerprint("k").label == "旧"
    s.record("k", Fingerprint(label="新"))
    assert s.fingerprint("k").label == "新"
    # A second store instance pointed at the same files sees the runtime write.
    s2 = HealStore(path=str(tmp_path / "runtime.json"), baseline_path=str(baseline_path))
    assert s2.fingerprint("k").label == "新"


def test_proposal_dedup_increments_seen_not_count(store):
    p1 = store.propose("k", V2_MATCH, "#check-invoice-btn")
    p2 = store.propose("k", V2_MATCH, "#check-invoice-btn")
    assert p1.id == p2.id
    assert store.list_proposals("PENDING")[0].seen == 2
    assert len(store.list_proposals()) == 1


def test_approve_promotes_to_l0(store):
    p = store.propose("k", V2_MATCH, "#check-invoice-btn")
    assert store.approved_selector("k") is None
    store.review(p.id, approve=True)
    assert store.approved_selector("k") == "#check-invoice-btn"
    assert store.fingerprint("k").label == "查验发票信息"


def test_reject_does_not_promote(store):
    p = store.propose("k", V3_SAVE_DRAFT, "#save-draft-btn")
    store.review(p.id, approve=False)
    assert store.approved_selector("k") is None
    assert store.list_proposals("PENDING") == []
    assert store.list_proposals("REJECTED")[0].id == p.id


# ---------------------------------------------------------------------------
# Router / final-summary behaviour when healing refuses to act
# ---------------------------------------------------------------------------

def test_router_stops_on_needs_human():
    from agent.router import choose_next_tool
    from agent.state import AgentState

    s = AgentState(task="t", claim_id="BX-2024-0003")
    s.claim = {"claim_id": "BX-2024-0003", "invoice_platform_ui": "v3"}
    s.policy = {"status": "有效"}
    s.claim_history = []
    s.retrieved_rules = []
    s.decision = "AUTO_PROCESS"
    s.rpa_result = {"success": False, "message": "元素未找到"}
    s.recovery_result = {"success": False, "needs_human": True,
                         "decision": {"status_label": "存在歧义"}}
    tool, reason = choose_next_tool(s)
    assert tool is None
    assert "转人工" in reason


def test_final_summary_reports_needs_human():
    from agent.agent import build_final_summary
    from agent.state import AgentState

    s = AgentState(task="t", claim_id="BX-2024-0003")
    s.decision = "AUTO_PROCESS"
    s.rpa_result = {"success": False}
    s.recovery_result = {"success": False, "needs_human": True,
                         "decision": {"status_label": "存在歧义"}}
    summary = build_final_summary(s)
    assert "存在歧义" in summary
    assert "已停手" in summary
    assert "等待人工处理" in summary
