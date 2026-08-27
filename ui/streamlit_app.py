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
from agent.state import AgentState
from agent.trace import Trace
from config import settings
from legacy_app import manager

CASES = {
    "CLM-001": "Case 1 · Straight-through (low value, low risk)",
    "CLM-002": "Case 2 · Human-in-the-loop (high value)",
    "CLM-003": "Case 3 · RPA failure → agent recovery",
}


# Run the agent off the Streamlit script thread so Playwright's sync API never
# collides with an event loop.
def _run(state: AgentState, trace: Trace, human_decision: Optional[str] = None) -> AgentResult:
    manager.ensure_running()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            run_agent, task=state.task, state=state, trace=trace, human_decision=human_decision
        ).result()


def _status_chip(label: str, ok: Optional[bool], pending: bool = False) -> str:
    if pending:
        return f"⚠ {label}"
    if ok is None:
        return f"• {label}"
    return f"{'✓' if ok else '❌'} {label}"


def _sidebar() -> None:
    st.sidebar.header("Runtime")
    mode = settings.resolve_llm_mode()
    st.sidebar.write(f"**LLM backend:** `{mode}`")
    if mode == "deterministic":
        st.sidebar.caption("No API key set → deterministic policy. The demo runs "
                            "fully offline and identically every time.")
    elif mode == "openai_compatible":
        endpoint = settings.openai_compatible_endpoint()
        st.sidebar.caption(f"Provider: `{settings.llm_provider}` · Model: `{endpoint['model']}`")
    else:
        st.sidebar.caption(f"Model: `{settings.anthropic_model}`")
    st.sidebar.write(f"**Insurance provider:** `{settings.insurance_provider}`")
    st.sidebar.write(f"**Legacy system:** {settings.legacy_base_url}")
    st.sidebar.divider()
    st.sidebar.markdown("**Thesis**\n\n> Don't replace RPA. Orchestrate it.")


def _render_result(res: AgentResult) -> None:
    s = res.state

    # Top-line status chips.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decision", s.decision or "-")
    risk = s.risk or {}
    c2.metric("Risk", f"{risk.get('risk_score', '-')}/100", risk.get("risk_level", ""))
    rpa_ok = (s.rpa_result or {}).get("success") if s.rpa_result else None
    c3.metric("RPA", "SUCCESS" if rpa_ok else ("FAILED" if s.rpa_result else "-"))
    rec_ok = (s.recovery_result or {}).get("success") if s.recovery_result else None
    c4.metric("Recovery", "SUCCESS" if rec_ok else ("-" if s.recovery_result is None else "FAILED"))

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Agent execution trace")
        st.code(res.trace.as_text(), language="text")
        st.caption(f"Outcome: {s.final_summary}")

    with right:
        st.subheader("Claim & policy")
        if s.claim:
            st.write({k: s.claim.get(k) for k in
                      ["claim_id", "amount", "currency", "status", "documents", "fraud_flag"]})
        if s.policy:
            st.write({k: s.policy.get(k) for k in
                      ["policy_id", "status", "coverage", "limit", "deductible"]})

        st.subheader("Tools used")
        st.write(" → ".join(s.executed_tools) or "-")

    if s.retrieved_rules:
        with st.expander("RAG evidence (retrieved business rules)", expanded=False):
            for r in s.retrieved_rules:
                st.markdown(f"**{r['source']} · {r['heading']}**  \n{r['text']}")

    # Human-in-the-loop gate.
    if res.status == AWAITING_HUMAN and s.human_decision is None:
        _approval_panel(s)


def _approval_panel(s: AgentState) -> None:
    req = s.human_request or {}
    st.divider()
    st.subheader("⚠ Human approval required")
    box = st.container(border=True)
    with box:
        cA, cB = st.columns(2)
        cA.write(f"**Claim:** {req.get('claim_id')}")
        cA.write(f"**Amount:** {req.get('currency')} {req.get('amount'):,}")
        cB.write(f"**Risk:** {req.get('risk_level')} ({req.get('risk_score')}/100)")
        cB.write(f"**Decision:** {req.get('decision')}")
        st.write("**Reasons:**")
        for reason in req.get("reasons", []):
            st.write(f"- {reason}")
        a, r = st.columns(2)
        if a.button("APPROVE", type="primary", use_container_width=True):
            _resume("APPROVE")
        if r.button("REJECT", use_container_width=True):
            _resume("REJECT")


def _resume(decision: str) -> None:
    res: AgentResult = st.session_state["result"]
    new = _run(res.state, res.trace, human_decision=decision)
    st.session_state["result"] = new
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Agentic Insurance Automation Lab", page_icon="🤖", layout="wide")
    st.title("Agentic Insurance Automation Lab")
    st.caption("AI Agent orchestration of insurance APIs, RPA, browser automation and human approval.")
    _sidebar()

    with st.form("run"):
        col1, col2 = st.columns([1, 2])
        claim_id = col1.selectbox("Claim", list(CASES.keys()),
                                  format_func=lambda k: f"{k} — {CASES[k]}")
        task = col2.text_input("Task", value=f"Process claim {claim_id}")
        submitted = st.form_submit_button("Run Agent", type="primary")

    if submitted:
        state = AgentState(task=task or f"Process claim {claim_id}", claim_id=claim_id)
        with st.spinner("Agent working..."):
            st.session_state["result"] = _run(state, Trace())

    if "result" in st.session_state:
        _render_result(st.session_state["result"])
    else:
        st.info("Pick a claim and click **Run Agent**. "
                "CLM-001 = straight-through · CLM-002 = human approval · CLM-003 = RPA failure & recovery.")


if __name__ == "__main__":
    main()
