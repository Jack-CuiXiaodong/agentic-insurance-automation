"""Decide whether a fingerprint match is confident enough to act on, and
remember what worked -- all as plain data, testable with no browser at all.

This is the layer that answers the question the old keyword scorer never asked:
*how sure are we?* A single top score is not enough -- a page with two nearly
identical controls can hand you a "winner" that is really a coin flip. Passing
requires both a floor (``MIN_CONFIDENCE``) and a lead over whatever is second
(``MIN_MARGIN``). Fail either and the agent does not click anything; it reports
why and hands the case to a human. An automation that cannot tell you when it
is guessing is more dangerous than one that is merely brittle.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from browser.fingerprint import FEATURE_LABELS, Candidate, Fingerprint, similarity

MIN_CONFIDENCE = 0.65
MIN_MARGIN = 0.15

HEALED = "HEALED"
AMBIGUOUS = "AMBIGUOUS"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
NO_CANDIDATES = "NO_CANDIDATES"

STATUS_LABELS: Dict[str, str] = {
    HEALED: "已自愈",
    AMBIGUOUS: "存在歧义",
    LOW_CONFIDENCE: "置信度不足",
    NO_CANDIDATES: "无可用控件",
}

# Tier labels, surfaced in traces/UI so a human can see *how* a match was made.
TIER_L0 = "L0"
TIER_L1 = "L1"
TIER_L2 = "L2"

TIER_LABELS: Dict[str, str] = {
    TIER_L0: "L0 已批准的修复缓存",
    TIER_L1: "L1 指纹比对",
    TIER_L2: "L2 意图关键词（无指纹时兜底）",
}


@dataclass
class HealTarget:
    """What the agent is trying to accomplish, independent of any one page.

    Intent keywords are defined *per step*, not globally: "保存" is the right
    word for a save-draft button and the wrong word for a verify button, and a
    single shared keyword table cannot express that. ``negative_keywords`` is a
    hard veto -- a candidate that says "取消" is never the control this step
    wants, no matter how it scores otherwise.
    """

    key: str
    original_selector: str
    intent_keywords: List[str] = field(default_factory=list)
    negative_keywords: List[str] = field(default_factory=list)


def keyword_score(label: str, target: HealTarget) -> float:
    """Legacy-shaped but veto-aware: scores a label against one target's own
    keyword lists (not a global table). Used as the L2 fallback when no
    fingerprint is on file yet, and this is also what ``legacy_keyword_score``
    in ``browser/recovery.py`` reimplements without the veto, for comparison."""
    text = (label or "").lower()
    for neg in target.negative_keywords:
        if neg.lower() in text:
            return 0.0
    n = len(target.intent_keywords)
    for i, kw in enumerate(target.intent_keywords):
        if kw.lower() in text:
            return round(1.0 - 0.3 * (i / max(n - 1, 1)), 4)  # 0.7 .. 1.0, best rank first
    return 0.0


@dataclass
class CandidateScore:
    index: int
    fingerprint: Fingerprint
    similarity: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    keyword_score: float = 0.0


@dataclass
class Decision:
    status: str
    tier: str
    best: Optional[CandidateScore] = None
    runner_up: Optional[CandidateScore] = None
    margin: float = 0.0
    scored: List[CandidateScore] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == HEALED

    def reason(self) -> str:
        if self.status == NO_CANDIDATES:
            return "页面上没有可操作的控件"
        if self.status == LOW_CONFIDENCE:
            top = self.best.similarity if self.best else 0.0
            return f"最高置信度 {top:.2f} 低于闸门 {MIN_CONFIDENCE:.2f}"
        if self.status == AMBIGUOUS:
            return f"置信度够了（{self.best.similarity:.2f}），但领先第二名只有 {self.margin:.2f}（< {MIN_MARGIN:.2f}）"
        return f"置信度 {self.best.similarity:.2f}，领先第二名 {self.margin:.2f}"


def decide(
    target: HealTarget,
    candidates: List[Candidate],
    recorded: Optional[Fingerprint] = None,
) -> Decision:
    """Score every candidate against ``target`` and decide whether to act.

    With a recorded fingerprint, scoring is similarity-based (L1). Without one
    (first run, nothing approved yet), scoring falls back to per-target keyword
    matching (L2) -- still gated by the same two thresholds, just fed a
    different number.
    """
    tier = TIER_L1 if recorded is not None else TIER_L2
    scored: List[CandidateScore] = []
    for c in candidates:
        cs = CandidateScore(index=c.index, fingerprint=c.fingerprint)
        cs.keyword_score = keyword_score(c.fingerprint.label, target)
        if recorded is not None:
            cs.similarity, cs.breakdown = similarity(recorded, c.fingerprint)
        else:
            cs.similarity = cs.keyword_score
        scored.append(cs)

    scored.sort(key=lambda cs: cs.similarity, reverse=True)

    if not scored:
        return Decision(status=NO_CANDIDATES, tier=tier, scored=scored)

    best = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None
    margin = best.similarity - (runner_up.similarity if runner_up else 0.0)

    if best.similarity < MIN_CONFIDENCE:
        status = LOW_CONFIDENCE
    elif margin < MIN_MARGIN:
        status = AMBIGUOUS
    else:
        status = HEALED

    return Decision(status=status, tier=tier, best=best, runner_up=runner_up,
                     margin=margin, scored=scored)


# ---------------------------------------------------------------------------
# Persistence: baseline (checked in, read-only) + runtime (gitignored) + a
# small human-review queue of proposed fixes.
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASELINE_PATH = os.path.join(_DATA_DIR, "locator_fingerprints.json")


def _runtime_path() -> str:
    override = os.environ.get("HEAL_STORE_PATH")
    if override:
        return override
    return os.path.join(_DATA_DIR, "heal_runtime.json")


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_LOCK = threading.Lock()


@dataclass
class Proposal:
    id: str
    key: str
    fingerprint: Dict[str, Any]
    selector: str
    status: str = "PENDING"  # PENDING | APPROVED | REJECTED
    seen: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class HealStore:
    """Baseline fingerprints (checked in) + runtime fingerprints & proposals
    (gitignored, one JSON file, written atomically under a lock).

    Runtime state always wins over baseline when both exist for the same key:
    an approved fix is a *correction* to the baseline, and the baseline file is
    not meant to be hand-edited on every redesign.
    """

    def __init__(self, path: Optional[str] = None, baseline_path: str = BASELINE_PATH):
        self.path = path or _runtime_path()
        self.baseline_path = baseline_path
        self._baseline = _load_json(self.baseline_path)
        self._runtime = _load_json(self.path)
        self._runtime.setdefault("fingerprints", {})
        self._runtime.setdefault("proposals", {})
        self._runtime.setdefault("approved_selectors", {})

    def _save(self) -> None:
        with _LOCK:
            _atomic_write(self.path, self._runtime)

    # -- fingerprints ---------------------------------------------------
    def fingerprint(self, key: str) -> Optional[Fingerprint]:
        d = self._runtime.get("fingerprints", {}).get(key) or self._baseline.get(key)
        return Fingerprint.from_dict(d) if d else None

    def record(self, key: str, fp: Fingerprint) -> None:
        self._runtime.setdefault("fingerprints", {})[key] = fp.as_dict()
        self._save()

    # -- proposals --------------------------------------------------------
    def propose(self, key: str, fp: Fingerprint, selector: str) -> Proposal:
        props = self._runtime.setdefault("proposals", {})
        # Dedup: same key + same selector + same label already pending/approved.
        for pid, p in props.items():
            if p["key"] == key and p["selector"] == selector and p["status"] != "REJECTED":
                p["seen"] = p.get("seen", 1) + 1
                p["updated_at"] = time.time()
                self._save()
                return Proposal(**p)
        pid = f"{key.split(':')[0]}-{int(time.time() * 1000) % 1_000_000}"
        prop = Proposal(id=pid, key=key, fingerprint=fp.as_dict(), selector=selector)
        props[pid] = prop.__dict__.copy()
        self._save()
        return prop

    def list_proposals(self, status: Optional[str] = None) -> List[Proposal]:
        out = []
        for d in self._runtime.get("proposals", {}).values():
            if status is None or d.get("status") == status:
                out.append(Proposal(**d))
        return sorted(out, key=lambda p: p.updated_at, reverse=True)

    def review(self, proposal_id: str, approve: bool) -> Optional[Proposal]:
        props = self._runtime.setdefault("proposals", {})
        d = props.get(proposal_id)
        if d is None:
            return None
        d["status"] = "APPROVED" if approve else "REJECTED"
        d["updated_at"] = time.time()
        if approve:
            self._runtime.setdefault("fingerprints", {})[d["key"]] = d["fingerprint"]
            self._runtime.setdefault("approved_selectors", {})[d["key"]] = d["selector"]
        self._save()
        return Proposal(**d)

    def approved_selector(self, key: str) -> Optional[str]:
        return self._runtime.get("approved_selectors", {}).get(key)


# ---------------------------------------------------------------------------
# CLI: python -m browser.healing list | approve <id> | reject <id>
# ---------------------------------------------------------------------------

def _print_proposals(store: HealStore) -> None:
    pending = store.list_proposals("PENDING")
    if not pending:
        print("没有待审核的修复提案。")
        return
    for p in pending:
        print(f"{p.id}  key={p.key}  selector={p.selector}  "
              f"label={p.fingerprint.get('label')!r}  seen={p.seen}")


def _main() -> None:
    import sys

    store = HealStore()
    args = sys.argv[1:]
    if not args or args[0] == "list":
        _print_proposals(store)
        return
    if args[0] in ("approve", "reject") and len(args) == 2:
        p = store.review(args[1], approve=(args[0] == "approve"))
        if p is None:
            print(f"未找到提案：{args[1]}")
            raise SystemExit(1)
        verb = "已批准" if args[0] == "approve" else "已拒绝"
        print(f"{verb}：{p.id}  key={p.key}  selector={p.selector}")
        return
    print("用法：python -m browser.healing list | approve <id> | reject <id>")
    raise SystemExit(2)


if __name__ == "__main__":
    _main()
