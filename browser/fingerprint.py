"""Element fingerprints: what the agent remembers about a control, not where.

A CSS selector is a claim about *where* a control lives in the DOM. A redesign
breaks that claim constantly -- ids get renamed, wrappers get added, nothing
about the control's actual job changes. A fingerprint instead records *what the
control does*: what it submits to, what fields travel with it, what kind of
control it is, what it is labelled, roughly where among its siblings it sits.
Comparing two fingerprints survives a redesign that invalidates every selector.

``browser/recovery.py`` is the only caller; this module has no opinion about
confidence thresholds or what to do with a low score -- that policy lives in
``browser/healing.py`` so it can be unit-tested without a browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# JS evaluated in the page. Kept as raw strings (not Python-side DOM walking)
# because Playwright's locator API is the only thing that can see the live,
# rendered page -- shadow DOM, computed roles, the works.
# ---------------------------------------------------------------------------

# Single-element fingerprint. IMPORTANT: uses textContent, not innerText.
# innerText forces a synchronous layout pass; on some headless Chromium builds
# that reflow during an automated click sequence crashes the render process.
# textContent is layout-independent and good enough -- the label is used for
# fuzzy text comparison, not pixel-perfect display text.
FINGERPRINT_FN = """(el) => {
  function text(e) {
    const t = (e.textContent || '').trim();
    if (t) return t.slice(0, 80);
    const v = (e.value || '').trim();
    if (v) return v.slice(0, 80);
    const aria = (e.getAttribute('aria-label') || '').trim();
    if (aria) return aria.slice(0, 80);
    const title = (e.getAttribute('title') || '').trim();
    return title.slice(0, 80);
  }

  function role(e) {
    const explicit = e.getAttribute('role');
    if (explicit) return explicit;
    const tag = e.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'input') {
      const t = (e.getAttribute('type') || '').toLowerCase();
      if (t === 'submit' || t === 'button' || t === 'reset') return 'button';
    }
    return '';
  }

  function formAction(e, form) {
    try {
      const u = e.hasAttribute('formaction')
        ? e.formAction
        : (form ? form.action : '');
      if (!u) return '';
      return new URL(u, window.location.href).pathname;
    } catch (err) {
      return '';
    }
  }

  function linkAction(e) {
    try {
      return new URL(e.href, window.location.href).pathname;
    } catch (err) {
      return '';
    }
  }

  const tag = el.tagName.toLowerCase();
  const type = tag === 'input' || tag === 'button'
    ? (el.getAttribute('type') || '').toLowerCase()
    : '';
  const form = el.closest ? el.closest('form') : null;

  let action = '';
  if (type === 'submit') {
    action = formAction(el, form);
  } else if (tag === 'a') {
    action = linkAction(el);
  }

  let fields = [];
  if (form) {
    const ctrls = form.querySelectorAll('input,select,textarea');
    const seen = new Set();
    ctrls.forEach((c) => {
      const t = (c.getAttribute('type') || '').toLowerCase();
      if (['submit', 'button', 'reset'].includes(t)) return;
      const name = c.getAttribute('name');
      if (name) seen.add(name);
    });
    fields = Array.from(seen).sort();
  }

  const scope = form || document.body;
  const scopedCandidates = Array.from(
    scope.querySelectorAll(
      'button, input[type=submit], input[type=button], input[type=reset], a[href], [role=button], [onclick]'
    )
  ).filter((c) => c.offsetParent !== null || c === el);
  let ordinal = scopedCandidates.indexOf(el);
  if (ordinal < 0) ordinal = 0;

  return {
    label: text(el),
    tag: tag,
    type: type,
    role: role(el),
    action: action,
    fields: fields,
    id: el.getAttribute('id') || '',
    name: el.getAttribute('name') || '',
    ordinal: ordinal,
  };
}"""

# Enumerate every visible, usable candidate control and stamp it with
# data-agent-cand=<index> so the Python side can click it later by that stable
# marker rather than re-deriving a selector (which is exactly the brittleness
# this module exists to avoid).
CANDIDATES_FN = """() => {
  const nodes = Array.from(document.querySelectorAll(
    'button, input[type=submit], input[type=button], input[type=reset], a[href], [role=button], [onclick]'
  )).filter((el) => {
    if (el.disabled) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    return true;
  });
  nodes.forEach((el, i) => el.setAttribute('data-agent-cand', String(i)));
  return nodes.length;
}"""


@dataclass
class Fingerprint:
    label: str = ""
    tag: str = ""
    type: str = ""
    role: str = ""
    action: str = ""
    fields: List[str] = None  # type: ignore[assignment]
    id: str = ""
    name: str = ""
    ordinal: int = 0

    def __post_init__(self) -> None:
        if self.fields is None:
            self.fields = []

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Fingerprint":
        return cls(
            label=d.get("label", ""),
            tag=d.get("tag", ""),
            type=d.get("type", ""),
            role=d.get("role", ""),
            action=d.get("action", ""),
            fields=list(d.get("fields", []) or []),
            id=d.get("id", ""),
            name=d.get("name", ""),
            ordinal=int(d.get("ordinal", 0) or 0),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "tag": self.tag,
            "type": self.type,
            "role": self.role,
            "action": self.action,
            "fields": self.fields,
            "id": self.id,
            "name": self.name,
            "ordinal": self.ordinal,
        }


def capture(locator) -> Fingerprint:
    """Fingerprint a single Playwright locator (must resolve to exactly one element)."""
    return Fingerprint.from_dict(locator.evaluate(FINGERPRINT_FN))


@dataclass
class Candidate:
    index: int
    fingerprint: Fingerprint


def candidates(page) -> List[Candidate]:
    """Enumerate and fingerprint every actionable control on the live page."""
    count = page.evaluate(CANDIDATES_FN)
    out: List[Candidate] = []
    for i in range(count):
        loc = page.locator(f'[data-agent-cand="{i}"]')
        try:
            fp = capture(loc)
        except Exception:  # pragma: no cover - a detached node between enum and read
            continue
        out.append(Candidate(index=i, fingerprint=fp))
    return out


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

_WORD_SPLIT_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")


def _ident_words(s: str) -> set:
    """Split an id/name into lowercase words, handling camelCase and snake_case."""
    if not s:
        return set()
    parts = re.split(r"[-_]+", s)
    words = []
    for p in parts:
        words.extend(_WORD_SPLIT_RE.findall(p))
    return {w.lower() for w in words if w}


def _dice_bigram(a: str, b: str) -> float:
    """Dice coefficient over character bigrams -- cheap fuzzy string match."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    def bigrams(s: str) -> List[str]:
        s = s.lower()
        return [s[i:i + 2] for i in range(len(s) - 1)] or [s]

    ba, bb = bigrams(a), bigrams(b)
    from collections import Counter

    ca, cb = Counter(ba), Counter(bb)
    overlap = sum((ca & cb).values())
    total = len(ba) + len(bb)
    return (2.0 * overlap / total) if total else 0.0


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _score_action(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if a and b:
        return 1.0 if a == b else 0.0
    return 0.0


def _score_fields(a: List[str], b: List[str]) -> float:
    return _jaccard(set(a), set(b))


def _score_type(a: str, b: str) -> float:
    return 1.0 if a == b else 0.0


def _score_label(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = a.lower(), b.lower()
    if la in lb or lb in la:
        short, long_ = (la, lb) if len(la) <= len(lb) else (lb, la)
        return 0.5 + 0.5 * (len(short) / len(long_))
    return _dice_bigram(a, b)


def _score_ident(a_id: str, a_name: str, b_id: str, b_name: str) -> float:
    aw = _ident_words(a_id) | _ident_words(a_name)
    bw = _ident_words(b_id) | _ident_words(b_name)
    if not aw or not bw:
        return 0.0
    return _jaccard(aw, bw)


def _score_role(a: str, b: str) -> float:
    return 1.0 if a and a == b else 0.0


def _score_ordinal(a: int, b: int) -> float:
    return 1.0 if a == b else max(0.0, 1.0 - abs(a - b) * 0.25)


# Weights, in the order the breakdown is reported.
WEIGHTS: Dict[str, float] = {
    "action": 0.25,
    "fields": 0.20,
    "type": 0.15,
    "label": 0.20,
    "ident": 0.10,
    "role": 0.05,
    "ordinal": 0.05,
}

FEATURE_LABELS: Dict[str, str] = {
    "action": "提交地址",
    "fields": "表单字段",
    "type": "控件类型",
    "label": "按钮文案",
    "ident": "id/name",
    "role": "可访问角色",
    "ordinal": "表单内位置",
}


def similarity(recorded: Fingerprint, candidate: Fingerprint) -> Tuple[float, Dict[str, float]]:
    """Weighted similarity in [0, 1] between a recorded and a live fingerprint.

    Returns ``(score, breakdown)`` where breakdown maps each feature name to
    its own [0, 1] sub-score, so a human (or a test) can see *why* two
    controls matched or did not -- a bare float is a claim, a breakdown is
    evidence.
    """
    breakdown = {
        "action": _score_action(recorded.action, candidate.action),
        "fields": _score_fields(recorded.fields, candidate.fields),
        "type": _score_type(recorded.type, candidate.type),
        "label": _score_label(recorded.label, candidate.label),
        "ident": _score_ident(recorded.id, recorded.name, candidate.id, candidate.name),
        "role": _score_role(recorded.role, candidate.role),
        "ordinal": _score_ordinal(recorded.ordinal, candidate.ordinal),
    }
    score = sum(breakdown[k] * w for k, w in WEIGHTS.items())
    return score, breakdown
