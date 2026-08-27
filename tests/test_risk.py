"""Deterministic risk engine & decision tests."""

from risk.engine import AUTO_LIMIT, assess_risk, decide, missing_documents


ACTIVE_POLICY = {"status": "ACTIVE", "coverage": "Accidental Medical Expense",
                 "limit": 50000, "deductible": 1000, "currency": "EUR"}


def _claim(amount, docs=("medical_receipt.pdf", "accident_report.pdf"), fraud=False):
    return {"claim_id": "CLM-X", "amount": amount, "currency": "EUR",
            "documents": list(docs), "fraud_flag": fraud}


def test_auto_limit_constant():
    assert AUTO_LIMIT == 5000


def test_low_value_complete_is_auto_process():
    claim = _claim(2500)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert risk["risk_level"] == "LOW"
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "AUTO_PROCESS"


def test_high_value_requires_human():
    claim = _claim(12000)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert "amount_above_auto_limit" in risk["risk_factors"]
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_missing_documents_blocks_auto():
    claim = _claim(2500, docs=("medical_receipt.pdf",))  # no accident_report
    assert "accident_report" in missing_documents(claim, ACTIVE_POLICY)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_fraud_flag_escalates_and_scores_high():
    claim = _claim(1000, fraud=True)
    risk = assess_risk(claim, ACTIVE_POLICY, [])
    assert "fraud_indicator" in risk["risk_factors"]
    assert decide(claim, ACTIVE_POLICY, risk)["decision"] == "HUMAN_REVIEW"


def test_inactive_policy_needs_human():
    claim = _claim(2500)
    policy = dict(ACTIVE_POLICY, status="ACTIVE")
    policy["status"] = "CANCELLED"
    risk = assess_risk(claim, policy, [])
    assert decide(claim, policy, risk)["decision"] == "REJECT"
