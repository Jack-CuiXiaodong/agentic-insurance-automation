"""Benchmark runner. Everything here is read-only: pages are opened and read,
nothing is ever clicked or submitted."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from browser import fingerprint
from browser.fingerprint import Fingerprint
from browser.healing import STATUS_LABELS, TIER_LABELS, HealTarget, decide

CORRECT = "找对"
ABSTAIN = "停手"
WRONG = "找错"
ERROR = "出错"

# Locate the human-labelled element after CANDIDATES_FN has stamped the page,
# and map it to a candidate index. A label often points at an inner <span> or
# an outer wrapper rather than the <a>/<button> itself, so look both ways.
_EXPECTED_FN = """(el) => {
  const hit = el.closest('[data-agent-cand]') || el.querySelector('[data-agent-cand]');
  return {
    cand: hit ? Number(hit.getAttribute('data-agent-cand')) : null,
    label: (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
  };
}"""


@dataclass
class VersionResult:
    case: str
    version: str
    url: str
    outcome: str
    tier: str = ""
    status: str = ""
    picked_label: str = ""
    similarity: float = 0.0
    margin: float = 0.0
    expected_label: str = ""
    notes: List[str] = field(default_factory=list)


def _settle(page, wait_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # long-polling pages never go idle; that is fine
        pass
    if wait_ms:
        page.wait_for_timeout(wait_ms)


def _in_child_frame(page, selector: str) -> bool:
    for frame in page.frames[1:]:
        try:
            if frame.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


def record_baseline(page, selector: str) -> Fingerprint:
    loc = page.locator(selector)
    if loc.count() == 0:
        if _in_child_frame(page, selector):
            raise LookupError(f"基线控件 {selector} 在 iframe 里，当前自愈只看主页面")
        raise LookupError(f"基线页面上找不到 {selector}")
    return fingerprint.capture(loc.first)


def evaluate_version(
    page,
    case: str,
    version: str,
    url: str,
    target: HealTarget,
    recorded: Optional[Fingerprint],
    expected: str,
) -> VersionResult:
    """Score one already-loaded page. Reads only; never clicks."""
    cands = fingerprint.candidates(page)
    decision = decide(target, cands, recorded)
    result = VersionResult(
        case=case, version=version, url=url, outcome=ERROR,
        tier=TIER_LABELS.get(decision.tier, decision.tier),
        status=STATUS_LABELS.get(decision.status, decision.status),
        margin=round(decision.margin, 4),
    )
    if decision.best is not None:
        result.picked_label = decision.best.fingerprint.label
        result.similarity = round(decision.best.similarity, 4)

    exp = page.locator(expected)
    if exp.count() == 0:
        if _in_child_frame(page, expected):
            result.notes.append("正确控件在 iframe 里，当前自愈只看主页面")
            result.outcome = WRONG if decision.passed else ABSTAIN
        else:
            result.notes.append(f"标注失效：页面上找不到 {expected}，请检查标注")
        return result
    info = exp.first.evaluate(_EXPECTED_FN)
    result.expected_label = info["label"]
    if info["cand"] is None:
        result.notes.append("正确控件不在候选列表里（不是按钮/链接，或不可见）")

    if not decision.passed:
        result.outcome = ABSTAIN
    elif decision.best.index == info["cand"]:
        result.outcome = CORRECT
    else:
        result.outcome = WRONG
    return result


def run(cases: List[Dict[str, Any]], session, delay: float = 3.0) -> List[VersionResult]:
    """Open each baseline and version with ``session`` (a BrowserSession), in order."""
    results: List[VersionResult] = []
    first = True

    def _open(url: str, wait_ms: int):
        nonlocal first
        if not first and delay:
            time.sleep(delay)  # be a polite visitor, not a crawler
        first = False
        page = session.open(url)
        _settle(page, wait_ms)
        return page

    for case in cases:
        name = case.get("name", "?")
        target = HealTarget(
            key=name,
            original_selector=(case.get("baseline") or {}).get("selector", ""),
            intent_keywords=case.get("intent_keywords", []),
            negative_keywords=case.get("negative_keywords", []),
        )
        recorded: Optional[Fingerprint] = None
        baseline = case.get("baseline")
        if baseline:
            try:
                page = _open(baseline["url"], int(baseline.get("wait_ms", case.get("wait_ms", 0))))
                recorded = record_baseline(page, baseline["selector"])
            except Exception as exc:
                for v in case.get("versions", []):
                    results.append(VersionResult(case=name, version=v.get("label", ""),
                                                 url=v.get("url", ""), outcome=ERROR,
                                                 notes=[f"基线采集失败：{exc}"]))
                continue

        for v in case.get("versions", []):
            label = v.get("label", v.get("url", ""))
            try:
                page = _open(v["url"], int(v.get("wait_ms", case.get("wait_ms", 0))))
                results.append(evaluate_version(page, name, label, v["url"], target,
                                                recorded, v["expected"]))
            except Exception as exc:
                results.append(VersionResult(case=name, version=label, url=v.get("url", ""),
                                             outcome=ERROR, notes=[f"页面打开或读取失败：{exc}"]))
    return results


def summarize(results: List[VersionResult]) -> Dict[str, Any]:
    counts = {k: 0 for k in (CORRECT, ABSTAIN, WRONG, ERROR)}
    for r in results:
        counts[r.outcome] += 1
    scored = counts[CORRECT] + counts[ABSTAIN] + counts[WRONG]
    return {
        "counts": counts,
        "scored": scored,
        "correct_rate": round(counts[CORRECT] / scored, 4) if scored else 0.0,
        "wrong_rate": round(counts[WRONG] / scored, 4) if scored else 0.0,
    }


def to_json(results: List[VersionResult]) -> str:
    return json.dumps(
        {"summary": summarize(results), "results": [asdict(r) for r in results]},
        ensure_ascii=False, indent=2,
    )
