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
    st.title("车险理赔 Agent 自动化实验台")
    st.caption("AI Agent 编排保司数据、RAG 业务规则、RPA 发票查验、浏览器自愈与人工核赔。")
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


if __name__ == "__main__":
    main()
