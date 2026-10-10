"""Adaptive browser recovery with Playwright.

When the brittle RPA workflow fails because the UI changed, the agent hands the
task here. Unlike the RPA path, recovery does not depend on a recorded
selector. It **inspects the live page**, fingerprints every actionable
control, and asks ``browser.healing.decide`` whether any of them is confident
enough to be the one -- preferring accessible, role-based selectors over
coordinates, and preferring *not clicking anything* over a guess.

This is the concrete difference the demo is built to show:

    RPA        = deterministic, selector-bound, breaks on UI change.
    Playwright = inspects + adapts, recovers from the same UI change --
                 but only when it is actually confident, not merely first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

from browser import fingerprint, healing
from browser.driver import page_session
from browser.healing import HealStore, HealTarget
from config import settings

# ---------------------------------------------------------------------------
# Legacy keyword scorer -- kept ONLY for the UI's side-by-side comparison and
# for tests that pin the old behaviour (picking "保存草稿" on the v3 trap page
# is the whole reason this project moved to fingerprints + confidence gates).
# ---------------------------------------------------------------------------
LEGACY_INTENT_KEYWORDS = [
    "查验", "验真", "提交", "确认", "保存", "完成",
    "submit", "confirm", "save", "send", "complete",
]


def legacy_keyword_score(label: str) -> int:
    text = (label or "").lower()
    score = 0
    for i, kw in enumerate(LEGACY_INTENT_KEYWORDS):
        if kw in text:
            score += len(LEGACY_INTENT_KEYWORDS) - i  # earlier keyword => higher weight
    return score


# Back-compat alias: this used to be the only scorer, named ``_score_label``.
_score_label = legacy_keyword_score


# This project's one real recovery target today. Negative keywords are the
# whole point of the v3 trap page: "立即校验" and "保存草稿" both contain
# nothing the old scorer would veto, so the old scorer picks whichever one
# happens to score higher on positive words alone (and "保存" is one of them).
VERIFY_INVOICE = HealTarget(
    key="verify_invoice:#verify-invoice-btn",
    original_selector="#verify-invoice-btn",
    intent_keywords=["查验", "验真", "核验", "校验", "verify", "check"],
    negative_keywords=["草稿", "保存", "重置", "取消", "返回", "draft", "save", "reset", "cancel"],
)


@dataclass
class RecoveryResult:
    success: bool
    matched_label: str = ""
    steps: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    needs_human: bool = False
    in_place: bool = False
    decision: Dict[str, Any] = field(default_factory=dict)
    proposal: Optional[Dict[str, Any]] = None
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
            "needs_human": self.needs_human,
            "in_place": self.in_place,
            "decision": self.decision,
            "proposal": self.proposal,
        }


def _highlight(locator) -> None:
    """Outline the control the agent is about to click. Cosmetic, demo-only."""
    try:
        locator.evaluate(
            "el => { el.style.outline = '3px solid #E23B3B';"
            " el.style.outlineOffset = '4px';"
            " el.style.boxShadow = '0 0 0 8px rgba(226,59,59,.18)';"
            " el.scrollIntoView({block: 'center'}); }"
        )
    except Exception:  # pragma: no cover - never let decoration break a run
        pass


def _shoot(page) -> bytes | None:
    """Best-effort page screenshot. Evidence is nice to have, never load-bearing."""
    try:
        return page.screenshot(full_page=True)
    except Exception:  # pragma: no cover - a missing screenshot must not fail a run
        return None


def _inspect_buttons(page) -> List[Dict[str, Any]]:
    """Legacy-shaped candidate list (label/id/name/score), for UI comparison."""
    out = []
    for c in fingerprint.candidates(page):
        fp = c.fingerprint
        out.append({"label": fp.label, "id": fp.id, "name": fp.name,
                    "score": legacy_keyword_score(fp.label)})
    return out


def _decision_summary(decision: healing.Decision) -> Dict[str, Any]:
    return {
        "status": decision.status,
        "status_label": healing.STATUS_LABELS.get(decision.status, decision.status),
        "tier": decision.tier,
        "tier_label": healing.TIER_LABELS.get(decision.tier, decision.tier),
        "best_similarity": round(decision.best.similarity, 4) if decision.best else 0.0,
        "margin": round(decision.margin, 4),
        "reason": decision.reason(),
    }


def _candidate_rows(decision: healing.Decision) -> List[Dict[str, Any]]:
    rows = []
    for cs in decision.scored:
        fp = cs.fingerprint
        rows.append({
            "label": fp.label,
            "id": fp.id,
            "name": fp.name,
            "type": fp.type,
            "action": fp.action,
            "similarity": round(cs.similarity, 4),
            "keyword_score": round(cs.keyword_score, 4),
            "legacy_score": legacy_keyword_score(fp.label),
            "breakdown": {
                healing.FEATURE_LABELS.get(k, k): round(v, 4) for k, v in cs.breakdown.items()
            },
            "why": decision.reason() if decision.best is cs else "",
        })
    return rows


def _stable_selector(page, fp: fingerprint.Fingerprint) -> str:
    """Prefer a unique #id; fall back to a role+accessible-name description."""
    if fp.id:
        try:
            if page.locator(f"#{fp.id}").count() == 1:
                return f"#{fp.id}"
        except Exception:  # pragma: no cover - malformed id characters
            pass
    return f'role={fp.role or "button"}[name="{fp.label}"]'


def heal_on_page(
    page,
    target: HealTarget,
    store: HealStore,
    result: RecoveryResult,
    expected_status: str = "VERIFIED",
    pace_ms: int = 0,
    before_click: Optional[Callable[[Any], None]] = None,
) -> RecoveryResult:
    """Resolve ``target`` on the page already open in ``page``, writing into
    ``result`` as it goes. Never navigates -- the caller decides whether this
    is an in-place recovery or a fresh page, and has already gotten there.
    """
    approved_selector = store.approved_selector(target.key)
    recorded_fp = store.fingerprint(target.key)

    target_locator = None
    matched_fp: Optional[fingerprint.Fingerprint] = None
    tier = healing.TIER_L0

    # -- L0: an already-approved selector, re-validated against its fingerprint
    if approved_selector and recorded_fp is not None:
        try:
            loc = page.locator(approved_selector)
            unique = loc.count() == 1
        except Exception:  # pragma: no cover - a malformed stored selector
            unique = False
        if unique:
            try:
                cand_fp = fingerprint.capture(loc)
                sim, _ = fingerprint.similarity(recorded_fp, cand_fp)
            except Exception:  # pragma: no cover
                sim = 0.0
            if sim >= healing.MIN_CONFIDENCE:
                target_locator = loc
                matched_fp = cand_fp
                result.steps.append(f"L0 命中已批准的修复：{approved_selector}")

    decision: Optional[healing.Decision] = None
    if target_locator is None:
        # -- L1 (have a baseline/runtime fingerprint) or L2 (keyword fallback)
        cands = fingerprint.candidates(page)
        decision = healing.decide(target, cands, recorded_fp)
        result.candidates = _candidate_rows(decision)
        result.decision = _decision_summary(decision)
        tier = decision.tier
        result.steps.append(healing.TIER_LABELS.get(tier, tier))

        if not decision.passed:
            result.needs_human = True
            result.success = False
            result.steps.append(f"自愈未通过置信度闸门（{decision.reason()}）—— 不点击任何控件，转人工")
            return result

        best = decision.best
        result.steps.append(
            f"置信度 {best.similarity:.2f}，领先第二名 {decision.margin:.2f}"
        )
        target_locator = page.locator(f'[data-agent-cand="{best.index}"]')
        matched_fp = best.fingerprint

    suggested_selector = _stable_selector(page, matched_fp)
    result.matched_label = matched_fp.label

    if pace_ms:
        _highlight(target_locator)
        page.wait_for_timeout(pace_ms * 2)
    if before_click is not None:
        try:
            before_click(target_locator)
        except Exception:  # pragma: no cover - a hook must never break the run
            pass

    result.steps.append(f"按建议选择器定位控件：{suggested_selector}")
    target_locator.click(timeout=3000)
    page.wait_for_selector("#result", timeout=5000)
    status = page.locator("#result").get_attribute("data-status")

    if status != expected_status:
        result.success = False
        result.needs_human = True
        result.details = {"result_status": status, "postcondition": "POSTCONDITION_FAILED"}
        result.steps.append(f"后置校验失败：期望 {expected_status}，实际 {status} —— 转人工")
        return result

    result.success = True
    result.details = {"result_status": status, "selector_strategy": suggested_selector}
    result.steps.append(f"后置校验通过：{status}")

    if tier != healing.TIER_L0:
        proposal = store.propose(target.key, matched_fp, suggested_selector)
        result.proposal = {
            "id": proposal.id, "key": proposal.key, "selector": proposal.selector,
            "status": proposal.status, "seen": proposal.seen,
        }
        result.steps.append(f"已生成修复提案：{proposal.id}（approve 后下次直接 L0 命中）")

    return result


def recover_action(
    claim_id: str,
    amount: str,
    invoice_code: str = "",
    invoice_no: str = "",
    ui_variant: str = "v2",
    base_url: str | None = None,
    headless: bool | None = None,
    pace: float = 0.0,
    page: Any = None,
    store: Optional[HealStore] = None,
) -> RecoveryResult:
    """Resolve the invoice-verification action -- in place if given ``page``
    (the normal path: ``execute_rpa`` failed on this exact page), otherwise by
    opening a fresh one (used when nothing shared a session, e.g. a bare
    ``recover_action`` call with no prior RPA step)."""
    store = store or HealStore()
    target = VERIFY_INVOICE
    result = RecoveryResult(success=False)
    slow_mo = int(pace * 1000)

    if page is not None:
        result.in_place = True
        result.steps.append("读取当前页面 DOM（就地，不重新加载）")
        result.screenshot_before = _shoot(page)
        heal_on_page(page, target, store, result, pace_ms=slow_mo)
        result.screenshot_after = _shoot(page)
        return result

    base_url = base_url or settings.legacy_base_url
    query = urlencode({
        "ui": ui_variant, "claim_id": claim_id, "invoice_code": invoice_code,
        "invoice_no": invoice_no, "amount": amount,
    })
    url = f"{base_url}/?{query}"
    result.steps.append("新开页面重试（非就地）")
    with page_session(url, headless=headless, slow_mo=slow_mo,
                      linger_ms=slow_mo * 3) as pg:
        result.screenshot_before = _shoot(pg)
        heal_on_page(pg, target, store, result, pace_ms=slow_mo)
        result.screenshot_after = _shoot(pg)
    return result
