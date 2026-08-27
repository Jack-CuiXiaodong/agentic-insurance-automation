"""A narrated, three-act replay of the failure this project exists to solve.

A normal run already does the right thing -- but it does it in one shot. By the
time anyone looks, the platform has *already* been redesigned and the RPA has
*already* broken. A viewer sees an outcome, never a story, and "RPA 失败 /
浏览器自愈 成功" means nothing to someone who did not watch it happen.

This module replays the same machinery as three deliberate acts. Each act carries
the screenshot the automation actually saw, the narration that says what is
happening, and the context that says why it matters:

    1. RPA works.        The recorded selector matches. These are the good years.
    2. RPA breaks.       The platform is redesigned and the selector finds nothing.
    3. The agent adapts. It reads the DOM, scores the controls, and clicks.

The redesign and the breakage are deliberately one act, not two. They are one
event: nobody announces a redesign to a bot, so from the automation's point of
view the page simply *is* different and the lookup simply *fails*.

Nothing here is staged. Every act drives the real mock platform through the real
adapter and the real recovery path; act 2 fails because it genuinely fails. The
only things this module adds are pacing, captions, and screenshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from browser.driver import page_session
from browser.recovery import _highlight, _inspect_buttons, _shoot
from config import settings
from rpa.mock_rpa import BRITTLE_SELECTOR

# Tone drives the colour of both the in-browser banner and the UI card.
OK = "ok"
INFO = "info"
FAIL = "fail"
AGENT = "agent"


@dataclass
class Shot:
    """One screenshot plus the caption that says what to look at in it."""

    png: bytes = field(repr=False)
    caption: str = ""


@dataclass
class Act:
    """One beat of the story, with the evidence that it really happened."""

    title: str
    narration: str          # what is happening, in plain language
    context: str            # why it matters -- the line worth saying out loud
    tone: str = INFO
    headline: str = ""      # the one short phrase to put in lights
    # Ordered evidence. An act can need more than one frame: the moment the agent
    # locks onto the control is the point, and the verified result is the payoff.
    shots: List[Shot] = field(default_factory=list)
    table: List[Dict[str, Any]] = field(default_factory=list)
    table_caption: str = ""


def _url(ui: str, claim: Dict[str, Any]) -> str:
    query = urlencode(
        {
            "ui": ui,
            "claim_id": claim.get("claim_id", ""),
            "invoice_code": claim.get("invoice_code", ""),
            "invoice_no": claim.get("invoice_no", ""),
            "amount": claim.get("amount", ""),
        }
    )
    return f"{settings.legacy_base_url}/?{query}"


_BANNER_JS = """([title, text, tone]) => {
  const palette = {info:'#4B76FC', ok:'#16A34A', fail:'#E23B3B', agent:'#3D38FD'};
  let el = document.getElementById('__demo_banner');
  if (!el) {
    el = document.createElement('div');
    el.id = '__demo_banner';
    document.body.appendChild(el);
  }
  el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;' +
    'background:' + (palette[tone] || palette.info) + ';color:#fff;' +
    'padding:13px 22px;box-shadow:0 2px 14px rgba(0,0,0,.28);' +
    'font-family:"PingFang SC","Microsoft YaHei",-apple-system,sans-serif;';
  el.innerHTML =
    '<div style="font-size:12.5px;opacity:.85;letter-spacing:.04em">' + title + '</div>' +
    '<div style="font-size:15px;font-weight:600;margin-top:3px;line-height:1.5">' + text + '</div>';
  document.body.style.paddingTop = el.offsetHeight + 'px';
}"""


def _banner(page, title: str, text: str, tone: str) -> None:
    """Caption the page the automation is driving. Cosmetic; never load-bearing."""
    try:
        page.evaluate(_BANNER_JS, [title, text, tone])
    except Exception:  # pragma: no cover - decoration must not break a run
        pass


def _frame(page) -> Optional[bytes]:
    """Screenshot with the page scrolled home.

    ``_highlight`` calls ``scrollIntoView``, which nudges the page and pushes the
    fixed narration banner out from under the platform's own header. Scrolling
    back first keeps every frame framed the same way.
    """
    try:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(80)
    except Exception:  # pragma: no cover - cosmetic only
        pass
    return _shoot(page)


def _pause(page, ms: int) -> None:
    if ms:
        try:
            page.wait_for_timeout(ms)
        except Exception:  # pragma: no cover
            pass


def run_storyboard(
    claim: Dict[str, Any],
    headless: bool = True,
    pace: float = 0.0,
) -> List[Act]:
    """Play the three acts against the real mock platform and return them.

    **One browser, one tab, start to finish.** Opening and closing a window per
    act would be easier to write and completely wrong: a real bot sits on an open
    browser while the platform changes underneath it. Navigating within a single
    session is what actually happens, and it is also the only version that reads
    as one continuous story rather than three disconnected clips.
    """
    slow_mo = int(pace * 1000)
    # Headless still needs a hair of settle time for the banner to paint before a
    # screenshot, but nobody is watching -- don't burn seconds on drama.
    beat = slow_mo * 2 if slow_mo else 120
    acts: List[Act] = []

    with page_session(_url("v1", claim), headless=headless, slow_mo=slow_mo,
                      linger_ms=slow_mo * 3) as page:

        # ------------------------------------------------------------ act 1
        # The recorded selector matches, the click lands, the invoice verifies.
        _banner(page, "传统 RPA 正常工作",
                f"按录制那天记下的 {BRITTLE_SELECTOR} 定位「查验」按钮 —— 稳定命中", OK)
        _pause(page, beat)
        v1_controls = _inspect_buttons(page)
        target = page.locator(BRITTLE_SELECTOR)
        found_v1 = target.count() > 0
        if found_v1:
            _highlight(target)
            _pause(page, beat)
        shot1 = _frame(page)
        if found_v1:
            target.click(timeout=3000)
            page.wait_for_selector("#result", timeout=5000)
            _banner(page, "传统 RPA 正常工作", "查验完成 —— 它每天都这样跑，从不出错", OK)
            _pause(page, beat)

        acts.append(Act(
            title="传统 RPA 正常工作",
            tone=OK,
            headline="选择器命中,点击成功",
            narration="传统 RPA 在刚上线时非常稳定。录制那天,查验平台上有一个 id 为 "
                      f"{BRITTLE_SELECTOR}、文案是「查验」的按钮,机器人把它记了下来,"
                      "此后每天照着点,一次都没错过。",
            context="这就是 RPA 值钱的地方,也是它被大规模部署的原因:流程固定、规则固定、"
                    "选择器固定,它就能不知疲倦地跑下去,比人快、比人稳、比人便宜。"
                    "问题不在这一步——问题在这一步太好用了,好到没人给它准备后路。",
            shots=[Shot(shot1, "录制时记下的「查验」按钮——红框就是 RPA 定位到的元素")]
                  if shot1 else [],
        ))

        # ------------------------------------------------------------ act 2
        # Same browser, same tab. The platform is simply not what it was.
        page.goto(_url("v2", claim), wait_until="domcontentloaded")
        _banner(page, "网页系统更新", "查验平台改版上线,页面变成了现在这样", INFO)
        _pause(page, beat)
        v2_controls = _inspect_buttons(page)

        count = page.locator(BRITTLE_SELECTOR).count()
        _banner(page, "RPA 获取元素失败",
                f"仍然去找 {BRITTLE_SELECTOR} —— 匹配到 {count} 个,流程就此中断", FAIL)
        _pause(page, beat)
        shot2 = _frame(page)
        _pause(page, beat)

        def _first(controls):
            return controls[0] if controls else {"label": "-", "id": "-"}

        a, b = _first(v1_controls), _first(v2_controls)
        acts.append(Act(
            title="网页系统更新，RPA 获取元素失败",
            tone=FAIL,
            headline=f"元素未找到:{BRITTLE_SELECTOR}",
            narration="但是网页系统会更新。查验平台改版上线,新的页面变成了现在这样:"
                      "主按钮的文案从「查验」变成了「查验发票信息」,id 从 "
                      f"{BRITTLE_SELECTOR} 变成了 #check-invoice-btn。"
                      f"RPA 仍然按录制那天记下的元素去找,在新页面上匹配到 {count} 个。"
                      "获取失败,流程停在这里。",
            context="难缠的地方在于:字段名没变、表单提交地址没变、页面结构没变,"
                    "接口层面完全看不出异样,人打开也还是那个页面、那套流程。"
                    "唯一变的是按钮怎么称呼自己——而这恰恰是写死选择器的机器人唯一认得的东西。"
                    "它不理解「查验发票信息」和「查验」是同一件事,因为它根本不理解任何事。"
                    "于是它报错、停在原地、等人来修脚本,而所有走这条流程的单子开始堆积。",
            shots=[Shot(shot2, "改版后的新页面——原来那个按钮已经不在了")] if shot2 else [],
            table=[
                {"项目": "主按钮文案", "改版前 v1": a.get("label", "-"), "改版后 v2": b.get("label", "-")},
                {"项目": "主按钮 id", "改版前 v1": "#" + (a.get("id") or "-"), "改版后 v2": "#" + (b.get("id") or "-")},
                {"项目": "表单字段名", "改版前 v1": "invoice_code / invoice_no / amount", "改版后 v2": "完全一致"},
                {"项目": "表单提交地址", "改版前 v1": "POST /verify", "改版后 v2": "完全一致"},
            ],
            table_caption="只有机器人认的那两行变了,其余一模一样",
        ))

        # ------------------------------------------------------------ act 3
        # Still the same tab, still the page that just broke the RPA. No reload:
        # the agent recovers *in place*, which is the whole claim.
        _banner(page, "Agent 接手",
                "读取实时 DOM → 枚举可操作控件 → 按意图打分 → 用 role=button 定位", AGENT)
        _pause(page, beat)
        candidates = _inspect_buttons(page)
        best = max(candidates, key=lambda c: c.get("score", 0)) if candidates else {}
        label = best.get("label", "")
        status = ""
        shot_pick = shot_done = None
        if label:
            picked = page.get_by_role("button", name=label)
            _highlight(picked)
            _pause(page, beat)
            # The moment it locks on is the point of the whole demo -- keep it.
            shot_pick = _frame(page)
            picked.click(timeout=3000)
            page.wait_for_selector("#result", timeout=5000)
            status = page.locator("#result").get_attribute("data-status") or ""
            _banner(page, "Agent 接手",
                    f"已用「{label}」完成查验 —— 状态 {status},全程零人工介入", OK)
            _pause(page, beat)
            shot_done = _frame(page)
        else:
            shot_pick = _frame(page)

        acts.append(Act(
            title="Agent 接手",
            tone=AGENT,
            headline=f"改用「{label}」完成查验 · {status or '—'}",
            narration="Agent 没有猜,也没有用坐标。它读取实时 DOM,枚举页面上所有可操作控件,"
                      "按意图关键词打分,选出得分最高的那个,再用 role=button + 可访问名称"
                      "去定位——这是选择器失效后依然站得住的路径。",
            context="此时传统 RPA 已经跑不下去了,整条流程停在原地等人来救。Agent 就是在这里"
                    "接的手——不用等人改脚本,也不必事先知道新按钮叫什么,它当场读页面、"
                    "当场判断、当场把断掉的流程续上。注意它是在同一个浏览器、同一个标签页、"
                    "同一张刚刚让 RPA 崩掉的页面上完成的,中间没有重来一次。\n\n"
                    "它扛得住改版,是因为定位锚在「人怎么读这个按钮」上,而不是「开发当时"
                    "怎么命名它」上:id 和 class 可以随便改,按钮上写给人看的那几个字不会——"
                    "一变,用户就不认识这个页面了。",
            shots=[s for s in (
                Shot(shot_pick, "Agent 按语义锁定的控件——红框标出的就是它自己找回来的那个")
                if shot_pick else None,
                Shot(shot_done, "点击之后：查验一致，断掉的流程接上了")
                if shot_done else None,
            ) if s],
            table=[
                {
                    "页面上的控件": c.get("label", ""),
                    "id": "#" + (c.get("id") or "-"),
                    "意图得分": c.get("score", 0),
                    "_hit": c.get("label") == label,
                }
                for c in sorted(candidates, key=lambda c: -c.get("score", 0))
            ],
            table_caption="Agent 读到的全部候选控件与打分结果",
        ))

    return acts
