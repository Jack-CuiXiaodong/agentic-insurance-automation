"""Deterministic risk & decision engine.

Design rule: **the LLM never invents the risk score or the routing decision.**
Those are computed here by explicit, testable business logic. The LLM's job is
to orchestrate and to *explain* -- not to be the source of truth for money
decisions. This separation is a core part of the project's thesis.
"""

from __future__ import annotations

from typing import Any, Dict, List

# --- Business constants (single source of truth) --------------------------
# Claims at or below this amount may be auto-processed; above it a human must
# approve. The same number is stated in knowledge/approval_rules.md so RAG can
# surface matching textual evidence.
AUTO_LIMIT = 5000

# Required document *types* per coverage. Matching is by filename substring.
REQUIRED_DOCS: Dict[str, List[str]] = {
    "Accidental Medical Expense": ["medical_receipt", "accident_report"],
}


def missing_documents(claim: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    coverage = policy.get("coverage", "")
    required = REQUIRED_DOCS.get(coverage, [])
    present = [d.lower() for d in claim.get("documents", [])]
    missing = []
    for req in required:
        if not any(req in doc for doc in present):
            missing.append(req)
    return missing


def assess_risk(
    claim: Dict[str, Any],
    policy: Dict[str, Any],
    history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return ``{risk_score, risk_level, risk_factors}`` deterministically."""
    history = history or []
    score = 0
    factors: List[str] = []

    if str(policy.get("status", "")).upper() != "ACTIVE":
        score += 40
        factors.append("policy_not_active")

    amount = float(claim.get("amount", 0) or 0)
    if amount > AUTO_LIMIT:
        score += 25
        factors.append("amount_above_auto_limit")
    if amount > 4 * AUTO_LIMIT:  # very large claim
        score += 15
        factors.append("amount_very_high")

    missing = missing_documents(claim, policy)
    if missing:
        score += 30
        factors.append("missing_documents:" + ",".join(missing))

    if claim.get("fraud_flag"):
        score += 50
        factors.append("fraud_indicator")

    if any(h.get("fraud_flag") for h in history):
        score += 20
        factors.append("suspicious_history")

    score = max(0, min(100, score))
    if score < 25:
        level = "LOW"
    elif score < 60:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {"risk_score": score, "risk_level": level, "risk_factors": factors}


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
    currency = claim.get("currency", "EUR")

    policy_active = str(policy.get("status", "")).upper() == "ACTIVE"
    if not policy_active:
        reasons.append("Policy is not active.")
    if claim.get("fraud_flag"):
        reasons.append("Fraud indicator present -- must escalate.")

    missing = missing_documents(claim, policy)
    if missing:
        reasons.append("Required documents missing: " + ", ".join(missing) + ".")

    over_limit = amount > AUTO_LIMIT
    if over_limit:
        reasons.append(
            f"Amount {currency} {amount:,.0f} exceeds auto-processing limit "
            f"{currency} {AUTO_LIMIT:,.0f}."
        )

    high_risk = risk.get("risk_level") == "HIGH"
    if high_risk:
        reasons.append("Risk level is HIGH.")

    # Cancelled/void policies cannot proceed at all.
    if str(policy.get("status", "")).upper() in {"CANCELLED", "VOID", "EXPIRED"}:
        return {"decision": "REJECT", "reasons": reasons or ["Policy not in force."]}

    needs_human = over_limit or high_risk or bool(missing) or claim.get("fraud_flag") or not policy_active
    if needs_human:
        return {"decision": "HUMAN_REVIEW", "reasons": reasons}

    return {
        "decision": "AUTO_PROCESS",
        "reasons": [
            "Policy active, documents complete, amount within auto limit, "
            "no fraud indicator, low risk.",
        ],
    }
