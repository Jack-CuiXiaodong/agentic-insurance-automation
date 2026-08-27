"""Streamlit UI for the Agentic Insurance Automation Lab.

Simple but polished: it renders the full agent execution trace, the retrieved
RAG evidence, deterministic risk, tool routing, RPA / recovery status, and the
human-in-the-loop approval gate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import streamlit as st

from agent.agent import AgentResult, run_agent
from agent.router import AWAITING_HUMAN
from agent.state import AgentState, decision_label
from agent.trace import Trace
from config import settings
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
[data-testid="stMetricValue"] { color: var(--brand); font-weight: 700; }
[data-testid="stMetricLabel"] p { color: var(--ink-2) !important; font-size: 13px !important; }

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

    with st.form("run"):
        col1, col2 = st.columns([1, 2])
        claim_id = col1.selectbox("报案", list(CASES.keys()),
                                  format_func=lambda k: f"{k} — {CASES[k]}")
        task = col2.text_input("任务", value=f"处理报案 {claim_id}")
        submitted = st.form_submit_button("运行 Agent", type="primary")

    if submitted:
        state = AgentState(task=task or f"处理报案 {claim_id}", claim_id=claim_id)
        with st.spinner("Agent 处理中…"):
            st.session_state["result"] = _run(state, Trace())

    if "result" in st.session_state:
        _render_result(st.session_state["result"])
    else:
        st.info("选择一笔报案并点击 **运行 Agent**。"
                "BX-2024-0001 = 快速直通 · BX-2024-0002 = 转人工核赔 · "
                "BX-2024-0003 = 查验平台改版后的 RPA 中断与自愈。")

    _portal_footer()


if __name__ == "__main__":
    main()
