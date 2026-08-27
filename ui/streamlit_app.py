"""Streamlit UI for the Agentic Insurance Automation Lab.

Simple but polished: it renders the full agent execution trace, the retrieved
RAG evidence, deterministic risk, tool routing, RPA / recovery status, and the
human-in-the-loop approval gate.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import streamlit as st

from agent.agent import AgentResult, run_agent
from agent.router import AWAITING_HUMAN
from agent.state import AgentState, decision_label
from agent.trace import Trace
from config import settings
from demo.knowledge_qa import SAMPLE_QUESTIONS, ask, survey
from demo.storyboard import Act, run_storyboard
from insurance.carrier_client import get_provider
from rag.retriever import get_retriever, reset_retriever
from legacy_app import manager

CASES = {
    "BX-2024-0001": "案例 1 · 快速理赔直通（小额、低风险）",
    "BX-2024-0002": "案例 2 · 转人工核赔（金额超限）",
    "BX-2024-0003": "案例 3 · 查验平台改版 → RPA 中断 → Agent 自愈",
}

# --------------------------------------------------------------------------
# 视觉风格：对齐国内保险门户「服务大厅」的设计语言
# 主色 #4B76FC · 深蓝 #3D38FD · 画布 #EDEFF1 · 卡片 #FFFFFF
# --------------------------------------------------------------------------
BRAND = "#4B76FC"

PORTAL_CSS = """
<style>
:root {
  --brand: #4B76FC; --brand-deep: #3D38FD; --brand-dark: #2F55D4;
  --tint: #E8EDFF; --tint-2: #F4F7FF;
  --canvas: #EDEFF1; --line: #E3E6EA;
  --ink: #1F2329; --ink-2: #5A6068; --ink-3: #919192;
}

/* 画布与主容器 */
.stApp, [data-testid="stAppViewContainer"] { background: var(--canvas); }
[data-testid="stMainBlockContainer"] { padding-top: .8rem; max-width: 1180px; }
[data-testid="stHeader"] { background: transparent; }

/* 顶部蓝条导航 */
.portalnav {
  background: var(--brand); color: #fff;
  border-radius: 4px;
  padding: 0 20px;
}
.portalnav-inner {
  display: flex; align-items: center; gap: 14px; height: 54px;
}
.portalnav .glyph {
  width: 28px; height: 28px; border-radius: 50%; flex: none;
  background: #fff; color: var(--brand);
  display: grid; place-items: center; font-weight: 800; font-size: 14px;
}
.portalnav .name { font-weight: 700; font-size: 16px; white-space: nowrap; }
.portalnav .en {
  font-size: 11px; letter-spacing: .1em; text-transform: uppercase; opacity: .85;
  border-left: 1px solid rgba(255,255,255,.4); padding-left: 10px;
}
.portalnav .spacer { flex: 1; }
.portalnav .navitem { font-weight: 600; font-size: 14px; opacity: .95; white-space: nowrap; }

/* 面包屑 */
.crumb {
  font-size: 13px; color: var(--ink-2);
  padding: 12px 0 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.crumb .sep { color: var(--ink-3); }
.crumb strong { color: var(--ink); font-weight: 600; }
.crumb .live { margin-left: auto; color: #16A34A; }

/* 白卡片：表单、结果容器、展开面板 */
[data-testid="stForm"],
[data-testid="stExpander"],
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #fff !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
  box-shadow: 0 1px 2px rgba(31,35,41,.04);
}
[data-testid="stForm"] { padding: 22px 26px !important; }

/* 主按钮 */
.stButton button, [data-testid="stFormSubmitButton"] button {
  border-radius: 4px !important; font-weight: 600 !important;
}
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
  background: var(--brand) !important; border-color: var(--brand) !important;
  padding-left: 2.2em !important; padding-right: 2.2em !important;
}
.stButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
  background: var(--brand-dark) !important; border-color: var(--brand-dark) !important;
}

/* 指标卡：门户常见的分栏数字条 */
[data-testid="stMetric"] {
  background: var(--tint-2); border: 1px solid var(--line);
  border-radius: 4px; padding: 14px 16px;
}
[data-testid="stMetricValue"] {
  color: var(--brand); font-weight: 700;
  font-size: 1.55rem !important; line-height: 1.35;
  /* 中文四个字在默认字号下会被省略号截断，这里放开换行 */
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; word-break: keep-all;
}
[data-testid="stMetricValue"] > div,
[data-testid="stMetricValue"] * {
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important;
}
[data-testid="stMetricLabel"] p { color: var(--ink-2) !important; font-size: 13px !important; }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
  white-space: normal !important; overflow: visible !important;
}

/* 小标题：细分隔线，对齐门户「保单查询」标题 */
h3 {
  font-size: 1.05rem !important; font-weight: 700 !important;
  padding-bottom: .45em; border-bottom: 1px solid var(--line); margin-bottom: .8em !important;
}

/* 执行轨迹终端 */
[data-testid="stCode"] pre, .stCode pre {
  background: #0E1420 !important; color: #C7CDD6 !important;
  border: 1px solid #222B3B !important; border-radius: 4px !important;
  font-size: 12.5px !important; line-height: 1.8 !important;
}

/* 侧栏 */
[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h2 { font-size: 1rem !important; color: var(--brand); }

/* ---- 四幕演示：每幕一张卡，context 单独高亮成解释框 ---- */
.stepper { display: flex; gap: 8px; margin: 6px 0 16px; flex-wrap: wrap; }
.step {
  flex: 1; min-width: 150px;
  border: 1px solid var(--line); border-radius: 4px;
  background: #fff; padding: 10px 14px;
  border-top: 3px solid var(--line);
}
.step .v { font-size: 13.5px; font-weight: 600; }
.step.ok    { border-top-color: #16A34A; } .step.ok .v    { color: #16A34A; }
.step.info  { border-top-color: #4B76FC; } .step.info .v  { color: #4B76FC; }
.step.fail  { border-top-color: #E23B3B; } .step.fail .v  { color: #E23B3B; }
.step.agent { border-top-color: #3D38FD; } .step.agent .v { color: #3D38FD; }

.act {
  background: #fff; border: 1px solid var(--line); border-radius: 4px;
  border-left: 4px solid var(--line);
  padding: 20px 24px 22px; margin-bottom: 14px;
  box-shadow: 0 1px 2px rgba(31,35,41,.04);
}
.act.ok    { border-left-color: #16A34A; }
.act.info  { border-left-color: #4B76FC; }
.act.fail  { border-left-color: #E23B3B; }
.act.agent { border-left-color: #3D38FD; }

.act-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.act-title { font-size: 18px; font-weight: 700; color: var(--ink); }
.act-badge {
  margin-left: auto; font-size: 12px; font-weight: 600;
  border-radius: 999px; padding: 3px 12px;
}
.act.ok .act-badge    { background: #E7F6EC; color: #16A34A; }
.act.info .act-badge  { background: #E8EDFF; color: #4B76FC; }
.act.fail .act-badge  { background: #FDECEC; color: #E23B3B; }
.act.agent .act-badge { background: #ECEBFF; color: #3D38FD; }

/* 醒目结论：一句话,放在灯下 */
.act-headline {
  font-size: 21px; font-weight: 700; margin: 14px 0 10px; line-height: 1.4;
}
.act.ok .act-headline    { color: #16A34A; }
.act.info .act-headline  { color: var(--ink); }
.act.fail .act-headline  {
  color: #E23B3B; font-family: "IBM Plex Mono", Consolas, monospace;
  font-size: 18px; background: #FDECEC; border: 1px dashed #F3B4B4;
  border-radius: 4px; padding: 12px 16px; display: inline-block;
}
.act.agent .act-headline { color: #3D38FD; }

.act-narration { font-size: 14.5px; color: var(--ink); line-height: 1.85; margin: 0 0 14px; }
.act-fig { margin: 0 0 16px; }
.act-shot {
  width: 100%; max-width: 620px; display: block;
  border: 1px solid var(--line); border-radius: 4px; margin: 0 auto;
}
.shot-cap {
  max-width: 620px; margin: 8px auto 0; text-align: center;
  font-size: 12.5px; color: var(--ink-3); line-height: 1.7;
}

/* context：整个演示的解说词，必须比正文更抢眼 */
.act-context {
  background: linear-gradient(90deg, var(--tint-2), #fff 70%);
  border: 1px solid var(--line); border-left: 3px solid var(--brand);
  border-radius: 4px; padding: 14px 18px; margin-top: 4px;
}
.act.ok .act-context    { border-left-color: #16A34A; }
.act.fail .act-context  { border-left-color: #E23B3B; }
.act.agent .act-context { border-left-color: #3D38FD; }
.act-context .lbl {
  display: block; font-size: 12px; font-weight: 700; letter-spacing: .08em;
  color: var(--ink-3); margin-bottom: 6px;
}
.act-context p { margin: 0; font-size: 14px; color: var(--ink-2); line-height: 1.9; }
.act-context p + p { margin-top: 10px; }

table.acttbl {
  width: 100%; border-collapse: collapse; margin-top: 14px;
  border: 1px solid var(--line); border-radius: 4px; font-size: 13px; overflow: hidden;
}
table.acttbl th {
  text-align: left; background: #F7F8FA; color: var(--ink-2); font-weight: 600;
  padding: 8px 12px; border-bottom: 1px solid var(--line); white-space: nowrap;
}
table.acttbl td { padding: 8px 12px; border-bottom: 1px solid var(--line); }
table.acttbl tr:last-child td { border-bottom: none; }
table.acttbl tr.hit td { background: var(--tint); font-weight: 600; }
.acttbl-cap { font-size: 12px; color: var(--ink-3); margin-top: 6px; }

/* ---- 问规则：业务知识库检索 ---- */
.vs { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 4px 0 18px; }
@media (max-width: 820px) { .vs { grid-template-columns: 1fr; } }
.vs-col {
  background: #fff; border: 1px solid var(--line); border-radius: 4px;
  border-top: 3px solid var(--ink-3); padding: 16px 18px;
}
.vs-col.now { border-top-color: var(--brand); }
.vs-col h4 {
  margin: 0 0 8px; font-size: 14px; font-weight: 700; color: var(--ink-3);
  letter-spacing: .04em;
}
.vs-col.now h4 { color: var(--brand); }
.vs-col p { margin: 0; font-size: 13.5px; color: var(--ink-2); line-height: 1.9; }

.kbstat {
  display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
  background: var(--tint-2); border: 1px solid var(--line); border-radius: 4px;
  padding: 12px 16px; margin-bottom: 14px; font-size: 13px; color: var(--ink-2);
}
.kbstat b { color: var(--brand); font-size: 16px; }
.kbstat .file {
  font-family: "IBM Plex Mono", Consolas, monospace; font-size: 12px;
  background: #fff; border: 1px solid var(--line); border-radius: 3px; padding: 2px 8px;
}

.hit {
  background: #fff; border: 1px solid var(--line); border-radius: 4px;
  border-left: 3px solid var(--brand); padding: 14px 18px; margin-bottom: 10px;
}
.hit-head {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  margin-bottom: 8px;
}
.hit-src {
  font-family: "IBM Plex Mono", Consolas, monospace; font-size: 12px;
  color: var(--brand); background: var(--tint); border-radius: 3px; padding: 2px 8px;
}
.hit-heading { font-size: 14px; font-weight: 700; }
.hit-score {
  margin-left: auto; font-size: 11.5px; color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
.hit-bar { height: 3px; background: var(--line); border-radius: 2px; margin-bottom: 10px; }
.hit-bar i { display: block; height: 100%; background: var(--brand); border-radius: 2px; }
.hit-text {
  font-size: 13.5px; color: var(--ink); line-height: 1.95; white-space: pre-wrap;
  margin: 0;
}
.hit-text mark {
  background: #FFF1A8; color: inherit; border-radius: 2px; padding: 0 1px;
}

.honest {
  background: linear-gradient(90deg, var(--tint-2), #fff 70%);
  border: 1px solid var(--line); border-left: 3px solid var(--ink-3);
  border-radius: 4px; padding: 14px 18px; margin-top: 18px;
}
.honest .lbl {
  display: block; font-size: 12px; font-weight: 700; letter-spacing: .08em;
  color: var(--ink-3); margin-bottom: 6px;
}
.honest p { margin: 0; font-size: 13.5px; color: var(--ink-2); line-height: 1.9; }

/* 现场取证：截图 + 候选控件表 */
.evidence-head {
  display: flex; align-items: baseline; gap: 10px;
  margin: 26px 0 2px;
}
.evidence-head h3 {
  margin: 0 !important; border: none !important; padding: 0 !important;
  font-size: 1.05rem !important;
}
.evidence-head .sub { font-size: 12.5px; color: var(--ink-3); }
.evidence-note {
  background: var(--tint-2); border: 1px solid var(--line);
  border-left: 3px solid var(--brand); border-radius: 4px;
  padding: 10px 14px; margin: 10px 0 14px;
  font-size: 13px; color: var(--ink-2);
}
table.evidence {
  width: 100%; border-collapse: collapse;
  background: #fff; border: 1px solid var(--line); border-radius: 4px;
  font-size: 13px; overflow: hidden;
}
table.evidence th {
  text-align: left; font-weight: 600; color: var(--ink-2);
  background: var(--surface-2, #F7F8FA);
  padding: 9px 12px; border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
table.evidence td {
  padding: 9px 12px; border-bottom: 1px solid var(--line); color: var(--ink);
}
table.evidence tr:last-child td { border-bottom: none; }
table.evidence td.mono {
  font-family: "IBM Plex Mono", Consolas, monospace;
  font-size: 12px; color: var(--ink-2);
}
table.evidence tr.hit td { background: var(--tint); font-weight: 600; }
table.evidence .hitmark {
  color: var(--brand); font-weight: 600; font-size: 12px; margin-left: 8px;
}
table.evidence td.score { text-align: right; font-variant-numeric: tabular-nums; }

/* 页面标题卡：对齐门户「保单查询」白卡片 */
.titlecard {
  background: #fff; border: 1px solid var(--line); border-radius: 4px;
  box-shadow: 0 1px 2px rgba(31,35,41,.04);
  padding: 22px 26px; margin-bottom: 12px;
  border-left: 4px solid var(--brand);
}
.titlecard h1 { margin: 0; font-size: 26px; font-weight: 700; color: var(--ink); }
.titlecard p { margin: 6px 0 0; font-size: 14px; color: var(--ink-2); }

/* 免责声明 */
.portal-foot {
  margin-top: 28px; padding-top: 14px; border-top: 1px solid var(--line);
  font-size: 12px; color: var(--ink-3);
  display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
}
</style>
"""


def _portal_chrome(claim_id: str = "") -> None:
    """顶部蓝条 + 面包屑，复刻保险门户「服务大厅」的页面框架。"""
    st.markdown(PORTAL_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="portalnav"><div class="portalnav-inner">'
        '<span class="glyph">✓</span>'
        '<span class="name">车险理赔 Agent 实验台</span>'
        '<span class="en">Claims Automation Lab</span>'
        '<span class="spacer"></span>'
        '<span class="navitem">案件处理</span>'
        '<span class="navitem">执行轨迹</span>'
        '<span class="navitem">规则库</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    live = f"● 当前案件 {claim_id}" if claim_id else "● 系统正常运行"
    st.markdown(
        '<div class="crumb">⌂ 首页 <span class="sep">&gt;</span> 服务大厅 '
        '<span class="sep">&gt;</span> <strong>理赔自动化演示</strong>'
        f'<span class="live">{live}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="titlecard"><h1>车险理赔 Agent 自动化实验台</h1>'
        "<p>AI Agent 编排保司数据、RAG 业务规则、RPA 发票查验、浏览器自愈与人工核赔。</p></div>",
        unsafe_allow_html=True,
    )


def _evidence_panel(s: AgentState) -> None:
    """Show what the automation actually saw.

    The recovery story lives or dies here: without the screenshots and the
    candidate table, "Agent 自己找回了按钮" is a claim in a log file. With them,
    a reviewer can check it in three seconds.
    """
    ev = s.evidence or {}
    rec = s.recovery_result or {}
    candidates = rec.get("candidates") or []
    if not ev and not candidates:
        return

    st.markdown(
        '<div class="evidence-head"><h3>现场取证</h3>'
        "<span class='sub'>以下截图与控件清单来自本次真实运行，非示意图</span></div>",
        unsafe_allow_html=True,
    )

    shots = [
        ("rpa_failure", "① RPA 撞墙的那一刻", "写死的 #verify-invoice-btn 在改版后的页面上已不存在"),
        ("recovery_after", "② Agent 自愈后的结果页", "换用「查验发票信息」完成查验，状态 VERIFIED"),
        ("rpa_success", "RPA 执行成功的结果页", "页面未改版，写死的选择器仍然有效"),
    ]
    present = [(k, t, c) for k, t, c in shots if ev.get(k)]
    if present:
        cols = st.columns(len(present))
        for col, (key, title, cap) in zip(cols, present):
            with col:
                st.markdown(f"**{title}**")
                st.image(ev[key], caption=cap, use_container_width=True)

    if candidates:
        matched = rec.get("matched_label", "")
        st.markdown(
            '<div class="evidence-note">Agent 没有猜，也没有用坐标。它读取实时 DOM，'
            "枚举页面上所有可操作控件，按意图关键词打分，选出得分最高的那个，"
            "再用 <code>role=button</code> + 可访问名称去定位——这是选择器失效后依然站得住的路径。</div>",
            unsafe_allow_html=True,
        )
        rows = []
        for c in sorted(candidates, key=lambda x: -int(x.get("score", 0) or 0)):
            is_hit = c.get("label") == matched
            hit = " class='hit'" if is_hit else ""
            mark = "<span class='hitmark'>&larr; 命中</span>" if is_hit else ""
            rows.append(
                f"<tr{hit}><td>{c.get('label','')}{mark}</td>"
                f"<td class='mono'>#{c.get('id','') or '-'}</td>"
                f"<td class='mono'>{c.get('name','') or '-'}</td>"
                f"<td class='score'>{c.get('score', 0)}</td></tr>"
            )
        st.markdown(
            "<table class='evidence'><thead><tr>"
            "<th>页面上的控件</th><th>id</th><th>name</th><th>意图得分</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>",
            unsafe_allow_html=True,
        )


_TONE_BADGE = {
    "ok": "稳定运行",
    "info": "环境变化",
    "fail": "自动化中断",
    "agent": "Agent 接手",
}


def _render_acts(acts: List[Act]) -> None:
    """Render the four-act replay: one card per act, context in its own spotlight."""
    steps = "".join(
        f"<div class='step {a.tone}'><div class='v'>{a.title}</div></div>"
        for a in acts
    )
    st.markdown(f"<div class='stepper'>{steps}</div>", unsafe_allow_html=True)

    for a in acts:
        shots = ""
        for sh in a.shots:
            b64 = base64.b64encode(sh.png).decode("ascii")
            cap = f"<div class='shot-cap'>{sh.caption}</div>" if sh.caption else ""
            shots += (f"<figure class='act-fig'>"
                      f"<img class='act-shot' src='data:image/png;base64,{b64}' alt='{a.title}'>"
                      f"{cap}</figure>")

        tbl = ""
        if a.table:
            cols = [k for k in a.table[0] if not k.startswith("_")]
            head = "".join(f"<th>{c}</th>" for c in cols)
            body = ""
            for row in a.table:
                cls = " class='hit'" if row.get("_hit") else ""
                body += f"<tr{cls}>" + "".join(f"<td>{row.get(c, '')}</td>" for c in cols) + "</tr>"
            cap = f"<div class='acttbl-cap'>{a.table_caption}</div>" if a.table_caption else ""
            tbl = f"<table class='acttbl'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{cap}"

        st.markdown(
            f"<div class='act {a.tone}'>"
            f"<div class='act-bar'>"
            f"<span class='act-title'>{a.title}</span>"
            f"<span class='act-badge'>{_TONE_BADGE.get(a.tone, '')}</span></div>"
            f"<div class='act-headline'>{a.headline}</div>"
            f"<p class='act-narration'>{a.narration}</p>"
            f"{shots}"
            f"<div class='act-context'><span class='lbl'>这一幕背后</span>"
            + "".join(f"<p>{para}</p>" for para in a.context.split("\n\n"))
            + "</div>"
            f"{tbl}"
            "</div>",
            unsafe_allow_html=True,
        )


def _knowledge_panel() -> None:
    """Demo 2: ask the rule base a question in plain Chinese.

    Traditional RPA turns business rules into hard-coded branches via a human
    translation step. Here the rule *is* the document, and it answers directly.
    """
    st.markdown(
        "<div class='vs'>"
        "<div class='vs-col'><h4>传统 RPA 怎么做</h4><p>每上一个新流程，业务规则要经过一次"
        "人肉翻译：业务人员口述 → 需求文档 → 开发理解 → 写成脚本里的 if-else。规则从此只活在"
        "两个地方——业务人员的脑子里，和外人读不懂的代码里。中间那次翻译，就是误解的来源；"
        "规则一改，整条链路重来一遍。</p></div>"
        "<div class='vs-col now'><h4>这套系统怎么做</h4><p>规则就是业务人员自己写的中文文档，"
        "系统直接读，不经过翻译。用一句话提问，秒级返回适用条款、出处文件和原文措辞。"
        "加一条规则不用改代码，改一条规则不用重新提需求——存进去，下一次检索就能找到它。</p></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    kb = survey()
    files = "".join(f"<span class='file'>{f}</span>" for f in kb.files)
    st.markdown(
        f"<div class='kbstat'>知识库现状：<b>{len(kb.files)}</b> 个中文文档 ·"
        f" <b>{kb.clauses}</b> 个条款 · <b>{kb.characters:,}</b> 字 {files}</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(len(SAMPLE_QUESTIONS))
    for i, (col, q) in enumerate(zip(cols, SAMPLE_QUESTIONS)):
        if col.button(q, key=f"kbq{i}", use_container_width=True):
            st.session_state["kb_input"] = q
            st.rerun()

    q1, q2 = st.columns([5, 1])
    query = q1.text_input("用一句话问业务规则", key="kb_input",
                          placeholder="例如：8 万元的车损案子要不要转人工核赔？")
    if q2.button("重新加载知识库", use_container_width=True,
                 help="清掉检索索引，重新读一遍 knowledge/ 目录。"
                      "改完规则文档点这里，不用重启、不用改代码。"):
        reset_retriever()
        st.toast(f"已重新读取知识库（{survey().clauses} 个条款）")

    if query:
        hits = ask(query, k=4)
        if not hits:
            st.warning("没有检索到相关条款。换个说法试试，或者这条规则还没写进知识库。")
        else:
            st.caption(f"检索后端：`{get_retriever().name}` · 命中 {len(hits)} 条，按相关度排序")
            top = max(h.score for h in hits) or 1.0
            for h in hits:
                pct = int(100 * h.score / top)
                st.markdown(
                    f"<div class='hit'><div class='hit-head'>"
                    f"<span class='hit-src'>{h.source}</span>"
                    f"<span class='hit-heading'>{h.heading}</span>"
                    f"<span class='hit-score'>相关度 {h.score:.3f}</span></div>"
                    f"<div class='hit-bar'><i style='width:{pct}%'></i></div>"
                    f"<p class='hit-text'>{h.html}</p></div>",
                    unsafe_allow_html=True,
                )

    st.markdown(
        "<div class='honest'><span class='lbl'>说清楚边界</span>"
        "<p>检索出来的是<b>依据</b>，不是<b>决定</b>。动钱的判断——自动核赔限额、风险评分、"
        "能不能直通——由 <code>risk/engine.py</code> 里的确定性代码执行，"
        "代码里的常量和文档里的措辞刻意保持一致。这样安排的理由很简单："
        "<b>规则文档应该好改，护栏不应该好改。</b>"
        "所以核赔员看到的每一条结论，既有代码算出的结果，也有文档里的原文可以回溯。</p></div>",
        unsafe_allow_html=True,
    )


def _portal_footer() -> None:
    st.markdown(
        '<div class="portal-foot"><span>Agentic Insurance Automation Lab</span>'
        "<span>合成数据 · 独立技术验证 · 非任何厂商或平台的官方产品</span></div>",
        unsafe_allow_html=True,
    )


# Run the agent off the Streamlit script thread so Playwright's sync API never
# collides with an event loop.
def _run(state: AgentState, trace: Trace, human_decision: Optional[str] = None) -> AgentResult:
    manager.ensure_running()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            run_agent, task=state.task, state=state, trace=trace, human_decision=human_decision
        ).result()


def _sidebar() -> None:
    st.sidebar.header("运行环境")
    mode = settings.resolve_llm_mode()
    st.sidebar.write(f"**LLM 后端：** `{mode}`")
    if mode == "deterministic":
        st.sidebar.caption("未配置 API Key → 使用确定性策略。完全离线运行，"
                           "每次结果一致。")
    elif mode == "openai_compatible":
        endpoint = settings.openai_compatible_endpoint()
        st.sidebar.caption(f"厂商：`{settings.llm_provider}` · 模型：`{endpoint['model']}`")
    else:
        st.sidebar.caption(f"模型：`{settings.anthropic_model}`")
    st.sidebar.write(f"**保司数据源：** `{settings.insurance_provider}`")
    st.sidebar.write(f"**发票查验平台：** {settings.legacy_base_url}")
    st.sidebar.divider()
    st.sidebar.markdown("**核心论点**\n\n> 不是取代 RPA，而是给 RPA 装上大脑。")


def _render_result(res: AgentResult) -> None:
    s = res.state

    # Top-line status chips.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("核赔结论", decision_label(s.decision) if s.decision else "-")
    risk = s.risk or {}
    c2.metric("风险评分", f"{risk.get('risk_score', '-')}/100", risk.get("risk_level_label", ""))
    rpa_ok = (s.rpa_result or {}).get("success") if s.rpa_result else None
    c3.metric("RPA 发票查验", "成功" if rpa_ok else ("失败" if s.rpa_result else "-"))
    rec_ok = (s.recovery_result or {}).get("success") if s.recovery_result else None
    c4.metric("浏览器自愈", "成功" if rec_ok else ("-" if s.recovery_result is None else "失败"))

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Agent 执行轨迹")
        st.code(res.trace.as_text(), language="text")
        st.caption(f"结果：{s.final_summary}")

    with right:
        st.subheader("报案与保单")
        if s.claim:
            st.write({
                "报案号": s.claim.get("claim_id"),
                "车牌": s.claim.get("plate_no"),
                "出险日期": s.claim.get("accident_date"),
                "赔付金额": f"¥{s.claim.get('amount', 0):,}",
                "状态": s.claim.get("status"),
                "单证": s.claim.get("documents"),
                "发票号码": s.claim.get("invoice_no"),
                "欺诈标记": s.claim.get("fraud_flag"),
            })
        if s.policy:
            st.write({
                "保单号": s.policy.get("policy_id"),
                "状态": s.policy.get("status"),
                "险种": s.policy.get("coverage"),
                "保额": f"¥{s.policy.get('limit', 0):,}",
                "免赔额": f"¥{s.policy.get('deductible', 0):,}",
                "保险期间": f"{s.policy.get('inception_date')} 至 {s.policy.get('expiry_date')}",
            })

        st.subheader("已调用工具")
        st.write(" → ".join(s.executed_tools) or "-")

    _evidence_panel(s)

    if risk.get("risk_factors"):
        st.info("风险因子：" + "、".join(risk["risk_factors"]))

    if s.retrieved_rules:
        with st.expander("RAG 依据（检索到的业务规则）", expanded=False):
            for r in s.retrieved_rules:
                st.markdown(f"**{r['source']} · {r['heading']}**  \n{r['text']}")

    # Human-in-the-loop gate.
    if res.status == AWAITING_HUMAN and s.human_decision is None:
        _approval_panel(s)


def _approval_panel(s: AgentState) -> None:
    req = s.human_request or {}
    st.divider()
    st.subheader("⚠ 需要核赔员人工审核")
    box = st.container(border=True)
    with box:
        cA, cB = st.columns(2)
        cA.write(f"**报案号：** {req.get('claim_id')}")
        cA.write(f"**车牌：** {req.get('plate_no')}")
        cA.write(f"**赔付金额：** ¥{req.get('amount'):,}")
        cB.write(f"**风险：** {req.get('risk_level_label')}（{req.get('risk_score')}/100）")
        cB.write(f"**结论：** {req.get('decision_label')}")
        st.write("**理由：**")
        for reason in req.get("reasons", []):
            st.write(f"- {reason}")
        a, r = st.columns(2)
        if a.button("通过", type="primary", use_container_width=True):
            _resume("APPROVE")
        if r.button("拒赔", use_container_width=True):
            _resume("REJECT")


def _resume(decision: str) -> None:
    res: AgentResult = st.session_state["result"]
    new = _run(res.state, res.trace, human_decision=decision)
    st.session_state["result"] = new
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="车险理赔 Agent 自动化实验台", page_icon="🚗", layout="wide")
    current = st.session_state.get("result")
    _portal_chrome(current.state.claim_id if current else "")
    _sidebar()

    tab_case, tab_rules = st.tabs(["案件处理", "问规则 · 业务知识库"])

    with tab_case:
        with st.form("run"):
            col1, col2 = st.columns([1, 2])
            claim_id = col1.selectbox("报案", list(CASES.keys()),
                                      format_func=lambda k: f"{k} — {CASES[k]}")
            task = col2.text_input("任务", value=f"处理报案 {claim_id}")
            cb, sl = st.columns([1, 1])
            show_browser = cb.checkbox(
                "显示浏览器窗口（面试现场演示用）",
                value=False,
                help="勾选后会弹出真实浏览器窗口，你可以亲眼看着它定位控件、点击。"
                     "需要一个完整浏览器（Edge / Chrome）；Playwright 自带的 "
                     "chrome-headless-shell 无法有头运行。",
            )
            demo_pace = sl.slider(
                "每步停顿（秒）", 0.0, 2.0, 0.8, 0.1,
                help="仅在勾选「显示浏览器窗口」时生效。Playwright 默认全速执行，"
                     "每步几十毫秒，人眼跟不上。0.8 秒左右适合现场讲解。",
            )
            b1, b2 = st.columns([1, 1])
            submitted = b1.form_submit_button("运行 Agent", type="primary",
                                              use_container_width=True)
            story = b2.form_submit_button("▶ 三幕演示（面试讲解用）",
                                          use_container_width=True,
                                          help="不跑完整 Agent，而是把「RPA 好用 → 网页更新导致"
                                               "取元素失败 → Agent 接手救场」这条时间线一幕一幕"
                                               "演一遍，每幕都有真实截图和解说。")

        if story:
            claim = get_provider().get_claim(claim_id) or {}
            with st.spinner("正在按三幕重放…（有头模式下请看弹出的浏览器窗口）"):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    manager.ensure_running()
                    st.session_state["acts"] = pool.submit(
                        run_storyboard, claim=claim,
                        headless=not show_browser,
                        # Pacing exists for a human watching a real window. Headless
                        # runs must stay fast, or "四幕演示" takes a minute for nothing.
                        pace=demo_pace if show_browser else 0.0,
                    ).result()
            st.session_state.pop("result", None)

        if submitted:
            st.session_state.pop("acts", None)
            state = AgentState(
                task=task or f"处理报案 {claim_id}",
                claim_id=claim_id,
                show_browser=show_browser,
                demo_pace=demo_pace,
            )
            with st.spinner("Agent 处理中…"):
                st.session_state["result"] = _run(state, Trace())

        if "acts" in st.session_state:
            st.markdown(
                "### 一次网页改版，从头到尾发生的全部事情\n"
                "下面的截图都来自刚刚这次真实运行，不是示意图；"
                "整场只开了一个浏览器、一个标签页。"
            )
            _render_acts(st.session_state["acts"])
        elif "result" in st.session_state:
            _render_result(st.session_state["result"])
        else:
            st.info("选择一笔报案并点击 **运行 Agent**。"
                    "BX-2024-0001 = 快速直通 · BX-2024-0002 = 转人工核赔 · "
                    "BX-2024-0003 = 查验平台改版后的 RPA 中断与自愈。")

    with tab_rules:
        _knowledge_panel()

    _portal_footer()


if __name__ == "__main__":
    main()
