"""heal_bench: the read-only self-healing benchmark for real web pages. Pages
here are inline data: URLs, so no server and no network are needed -- only a
browser (skipped otherwise)."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from browser.driver import BrowserSession, BrowserUnavailable, page_session
from heal_bench.runner import ABSTAIN, CORRECT, ERROR, WRONG, run, summarize


def _browser_available() -> bool:
    try:
        with page_session("data:text/html,<button>x</button>"):
            return True
    except BrowserUnavailable:
        return False


pytestmark = pytest.mark.skipif(
    not _browser_available(), reason="Playwright/Chromium not available in this environment"
)

FORM = '<form action="https://example.test/{action}">' \
       '<input name="invoice_code"><input name="invoice_no">{buttons}</form>'
# Counts every click that reaches the document -- the benchmark must never cause one.
SPY = "<script>window.__clicks=0;document.addEventListener('click',()=>window.__clicks++,true)</script>"


def _page(buttons: str, action: str = "verify", extra: str = "") -> str:
    html = SPY + FORM.format(action=action, buttons=buttons) + extra
    return "data:text/html;charset=utf-8," + quote(html)


BASELINE = _page('<button type="submit" id="verify-btn" name="verify">查验</button>')
REDESIGN = _page('<button type="submit" id="check-btn" name="check">查验发票信息</button>'
                 '<button type="button" id="reset-btn" name="reset">重置</button>')
TWINS = _page('<button type="submit" id="a">查验</button><button type="submit" id="b">查验</button>')


def _case(versions):
    return [{
        "name": "测试用例",
        "intent_keywords": ["查验"],
        "negative_keywords": ["重置"],
        "baseline": {"url": BASELINE, "selector": "#verify-btn"},
        "versions": versions,
    }]


@pytest.fixture
def session():
    s = BrowserSession(headless=True)
    yield s
    s.close()


def test_redesign_is_found(session):
    [r] = run(_case([{"label": "改版", "url": REDESIGN, "expected": "#check-btn"}]), session, delay=0)
    assert r.outcome == CORRECT
    assert r.picked_label == "查验发票信息"


def test_identical_twins_abstain(session):
    [r] = run(_case([{"label": "双胞胎", "url": TWINS, "expected": "#a"}]), session, delay=0)
    assert r.outcome == ABSTAIN


def test_confident_pick_of_the_wrong_control_counts_as_wrong(session):
    """A human label that disagrees with a confident pick must be scored 找错, not hidden."""
    [r] = run(_case([{"label": "标成重置", "url": REDESIGN, "expected": "#reset-btn"}]), session, delay=0)
    assert r.outcome == WRONG


def test_control_inside_an_iframe_is_reported(session):
    inner = '<button type="submit" id="check-btn">查验发票信息</button>'
    framed = _page("", extra=f'<iframe srcdoc="{inner.replace(chr(34), "&quot;")}"></iframe>')
    [r] = run(_case([{"label": "iframe", "url": framed, "expected": "#check-btn"}]), session, delay=0)
    assert r.outcome in (ABSTAIN, WRONG)
    assert any("iframe" in n for n in r.notes)


def test_broken_label_is_an_error_not_a_score(session):
    [r] = run(_case([{"label": "错标注", "url": REDESIGN, "expected": "#nope"}]), session, delay=0)
    assert r.outcome == ERROR
    assert any("标注失效" in n for n in r.notes)


def test_bad_baseline_marks_every_version_as_error(session):
    cases = _case([{"label": "x", "url": REDESIGN, "expected": "#check-btn"}])
    cases[0]["baseline"]["selector"] = "#missing"
    [r] = run(cases, session, delay=0)
    assert r.outcome == ERROR and "基线" in r.notes[0]


def test_benchmark_never_clicks(session):
    run(_case([{"label": "改版", "url": REDESIGN, "expected": "#check-btn"}]), session, delay=0)
    assert session.page.evaluate("window.__clicks") == 0
    assert session.page.url.startswith("data:")  # nothing submitted, never navigated away


def test_summary_rates():
    from heal_bench.runner import VersionResult

    rs = [VersionResult("c", "v", "u", o) for o in (CORRECT, CORRECT, ABSTAIN, WRONG, ERROR)]
    s = summarize(rs)
    assert s["scored"] == 4
    assert s["correct_rate"] == 0.5 and s["wrong_rate"] == 0.25
