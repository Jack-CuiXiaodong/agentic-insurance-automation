"""Deterministic risk engine & decision tests."""

from risk.engine import (
    AUTO_LIMIT,
    FRESH_POLICY_DAYS,
    assess_risk,
    days_since_inception,
    decide,
    missing_documents,
)

ACTIVE_POLICY = {
    "status": "有效",
    "coverage": "机动车损失保险",
    "limit": 500000,
    "deductible": 500,
    "currency": "CNY",
    "inception_date": "2024-01-15",
    "expiry_date": "2025-01-14",
}

FULL_DOCS = ("定损单.pdf", "维修发票.pdf", "事故认定书.pdf")


def _claim(amount, docs=FULL_DOCS, fraud=False, accident_date="2024-07-12"):
    return {
        "claim_id": "BX-TEST",
        "amount": amount,
        "currency": "CNY",
        "accident_date": accident_date,
        "documents": list(docs),
        "fraud_flag": fraud,
    }


def test_auto_limit_constant():
    assert AUTO_LIMIT == 10_000


def test_low_value_complete_is_auto_process():
    claim = _claim(3800)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert risk["risk_level"] == "LOW"
    assert risk["risk_level_label"] == "低"
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "AUTO_PROCESS"


def test_high_value_requires_human():
    claim = _claim(86000)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert "金额超自动核赔限额" in risk["risk_factors"]
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_missing_documents_blocks_auto():
    claim = _claim(3800, docs=("定损单.pdf", "维修发票.pdf"))  # 缺事故认定书
    assert "事故认定书" in missing_documents(claim, ACTIVE_POLICY)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_fraud_flag_always_escalates_regardless_of_level():
    """A fraud flag routes to a human on its own -- it does not have to push the
    score into HIGH first. 50 points alone lands in MEDIUM; escalation comes from
    the flag being an independent condition in ``decide``."""
    claim = _claim(1000, fraud=True)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert "欺诈嫌疑标记" in risk["risk_factors"]
    assert risk["risk_level"] == "MEDIUM"
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_fraud_plus_missing_docs_reaches_high():
    claim = _claim(1000, docs=("定损单.pdf",), fraud=True)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert risk["risk_level"] == "HIGH"
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_inactive_policy_is_rejected():
    claim = _claim(3800)
    policy = dict(ACTIVE_POLICY, status="已失效")
    risk = assess_risk(claim, policy, [])
    assert decide(claim, policy, risk)["decision"] == "REJECT"


def test_fresh_policy_claim_raises_risk():
    """新保即出险 -- a claim days after inception is a motor-fraud red flag."""
    claim = _claim(3800, accident_date="2024-01-20")  # 起保后第 5 天
    assert days_since_inception(claim, ACTIVE_POLICY) == 5
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert any("新保即出险" in f for f in risk["risk_factors"])
    assert risk["risk_score"] > assess_risk(_claim(3800), ACTIVE_POLICY, [])["risk_score"]


def test_claim_well_after_inception_is_not_flagged():
    claim = _claim(3800, accident_date="2024-07-12")
    assert days_since_inception(claim, ACTIVE_POLICY) >= FRESH_POLICY_DAYS
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert not any("新保即出险" in f for f in risk["risk_factors"])


def test_missing_dates_do_not_crash_the_engine():
    claim = _claim(3800, accident_date=None)
    assert days_since_inception(claim, ACTIVE_POLICY) is None
    assert assess_risk(claim, ACTIVE_POLICY, [])["risk_level"] == "LOW"
