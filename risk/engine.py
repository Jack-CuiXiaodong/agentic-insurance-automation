"""Deterministic risk & decision engine (motor claims).

Design rule: **the LLM never invents the risk score or the routing decision.**
Those are computed here by explicit, testable business logic. The LLM's job is
to orchestrate and to *explain* -- not to be the source of truth for money
decisions. This separation is a core part of the project's thesis.

Identifiers stay English so control flow, tests and guardrails read the same in
any locale; the Chinese labels used by the UI and the trace live in
``RISK_LEVEL_LABELS`` here and ``DECISION_LABELS`` in :mod:`agent.state`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

# --- Business constants (single source of truth) --------------------------
# Claims at or below this amount may be auto-adjudicated; above it a human
# adjuster must approve. The same number is stated in knowledge/理赔规则.md and
# knowledge/核赔权限.md so RAG can surface matching textual evidence.
AUTO_LIMIT = 10_000  # CNY

# A claim filed this soon after the policy incepted is a classic motor-fraud
# pattern in this market ("新保即出险"), so it carries its own risk factor.
FRESH_POLICY_DAYS = 30

# Required document *types* per coverage. Matching is by filename substring.
REQUIRED_DOCS: Dict[str, List[str]] = {
    "机动车损失保险": ["定损单", "维修发票", "事故认定书"],
}

RISK_LEVEL_LABELS = {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}


def _parse_date(value: Any) -> Optional[date]:
    """Parse an ISO ``YYYY-MM-DD`` string; return None for anything unusable."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def missing_documents(claim: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    coverage = policy.get("coverage", "")
    required = REQUIRED_DOCS.get(coverage, [])
    present = [d.lower() for d in claim.get("documents", [])]
    missing = []
    for req in required:
        if not any(req in doc for doc in present):
            missing.append(req)
    return missing


def days_since_inception(claim: Dict[str, Any], policy: Dict[str, Any]) -> Optional[int]:
    """Days between policy inception and the loss date, when both are known."""
    incepted = _parse_date(policy.get("inception_date"))
    accident = _parse_date(claim.get("accident_date"))
    if incepted is None or accident is None:
        return None
    return (accident - incepted).days


def assess_risk(
    claim: Dict[str, Any],
    policy: Dict[str, Any],
    history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return ``{risk_score, risk_level, risk_level_label, risk_factors}``."""
    history = history or []
    score = 0
    factors: List[str] = []

    if str(policy.get("status", "")) != "有效":
        score += 40
        factors.append("保单非有效状态")

    amount = float(claim.get("amount", 0) or 0)
    if amount > AUTO_LIMIT:
        score += 25
        factors.append("金额超自动核赔限额")
    if amount > 4 * AUTO_LIMIT:
        score += 15
        factors.append("金额远超限额")

    missing = missing_documents(claim, policy)
    if missing:
        score += 30
        factors.append("单证缺失：" + "、".join(missing))

    if claim.get("fraud_flag"):
        score += 50
        factors.append("欺诈嫌疑标记")

    elapsed = days_since_inception(claim, policy)
    if elapsed is not None and 0 <= elapsed < FRESH_POLICY_DAYS:
        score += 20
        factors.append(f"新保即出险（起保后 {elapsed} 天）")

    if any(h.get("fraud_flag") for h in history):
        score += 20
        factors.append("历史出险异常")

    score = max(0, min(100, score))
    if score < 25:
        level = "LOW"
    elif score < 60:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "risk_score": score,
        "risk_level": level,
        "risk_level_label": RISK_LEVEL_LABELS[level],
        "risk_factors": factors,
    }


def decide(
    claim: Dict[str, Any],
    policy: Dict[str, Any],
    risk: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministic routing decision + human-readable reasons.

    Returns ``{decision, reasons}`` where decision is one of
    ``AUTO_PROCESS`` / ``HUMAN_REVIEW`` / ``REJECT``.
    """
    reasons: List[str] = []
    amount = float(claim.get("amount", 0) or 0)

    policy_active = str(policy.get("status", "")) == "有效"
    if not policy_active:
        reasons.append("保单不在有效期内。")
    if claim.get("fraud_flag"):
        reasons.append("存在欺诈嫌疑标记，必须升级处理。")

    missing = missing_documents(claim, policy)
    if missing:
        reasons.append("必需单证缺失：" + "、".join(missing) + "。")

    over_limit = amount > AUTO_LIMIT
    if over_limit:
        reasons.append(
            f"赔付金额 ¥{amount:,.0f} 超过自动核赔限额 ¥{AUTO_LIMIT:,.0f}。"
        )

    elapsed = days_since_inception(claim, policy)
    if elapsed is not None and 0 <= elapsed < FRESH_POLICY_DAYS:
        reasons.append(f"新保即出险：保单起保后第 {elapsed} 天出险。")

    high_risk = risk.get("risk_level") == "HIGH"
    if high_risk:
        reasons.append("风险等级为高。")

    # 已失效 / 已注销 / 已过期的保单根本不能继续处理。
    if str(policy.get("status", "")) in {"已失效", "已注销", "已过期", "退保"}:
        return {"decision": "REJECT", "reasons": reasons or ["保单不在有效期内。"]}

    needs_human = (
        over_limit
        or high_risk
        or bool(missing)
        or claim.get("fraud_flag")
        or not policy_active
    )
    if needs_human:
        return {"decision": "HUMAN_REVIEW", "reasons": reasons}

    return {
        "decision": "AUTO_PROCESS",
        "reasons": [
            "保单有效、单证齐全、金额在自动核赔限额内、无欺诈标记、风险等级为低。",
        ],
    }
