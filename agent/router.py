"""Tool Router.

Makes the project's core claim explicit in code: **RPA is one execution tool the
agent can route to, not the agent itself.** The same context can route to a data
tool, an RPA workflow, a browser-recovery step, or a human adjuster -- depending
on the situation.

``choose_next_tool`` is the deterministic policy. It is used directly by the
deterministic LLM backend and is what makes the human-in-the-loop flow cleanly
resumable (it re-derives the next step from :class:`AgentState`, skipping work
already done).
"""

from __future__ import annotations

from typing import Optional, Tuple

from agent.state import AUTO_PROCESS, HUMAN_REVIEW, REJECT, AgentState

# Human-readable routing table (documentation + surfaced in the UI).
ROUTES = [
    ("需要报案 / 保单 / 历史出险数据", "→ 保司数据工具"),
    ("需要适用的业务规则", "→ RAG 检索（search_rules）"),
    ("需要风险评分与核赔结论", "→ 确定性风险引擎（calculate_risk）"),
    ("结论 = 自动核赔", "→ RPA 发票查验（execute_rpa）"),
    ("RPA 因页面改版失败", "→ 浏览器自愈（browser_recover）"),
    ("结论 = 人工核赔", "→ 核赔员审批（request_human_approval）"),
]

# Status of the agent run.
RUNNING = "RUNNING"
AWAITING_HUMAN = "AWAITING_HUMAN"
DONE = "DONE"


def _execution_step(state: AgentState) -> Tuple[Optional[str], str]:
    """Route the *execution* phase (after a claim is approved/auto)."""
    rpa = state.rpa_result
    if rpa is None:
        return "execute_rpa", "已通过/可自动 → 运行 RPA 到查验平台验票"
    if rpa.get("success"):
        return None, "RPA 已成功 —— 无后续动作"
    # RPA failed.
    if rpa.get("browser_unavailable"):
        # Recovery drives the same browser, so it cannot help here.
        return None, "RPA 失败且浏览器不可用 —— 无法自愈"
    if state.recovery_result is None:
        return "browser_recover", "RPA 选择器失效 → 启动 Playwright 自适应自愈"
    return None, "已尝试过自愈 —— 无后续动作"


def choose_next_tool(state: AgentState) -> Tuple[Optional[str], str]:
    """Return ``(tool_name_or_None, reasoning)`` for the next agent step."""
    if state.claim is None:
        return "get_claim", "尚未加载报案 → 先读取报案"
    if state.policy is None:
        return "get_policy", "报案已加载；需要保单状态与险种"
    if state.claim_history is None:
        return "get_claim_history", "风险评估需要历史出险"
    if state.retrieved_rules is None:
        return "search_rules", "需要适用的业务规则（RAG 依据）"
    if state.decision is None:
        return "calculate_risk", "数据与规则齐备 → 计算风险与核赔结论"

    if state.decision == REJECT:
        return None, "结论为拒赔 —— 报案不能继续"

    if state.decision == HUMAN_REVIEW:
        if state.human_request is None:
            return "request_human_approval", "高金额/高风险 → 请求核赔员审批"
        if state.human_decision is None:
            return None, "等待核赔员给出结论"
        if state.human_decision == "REJECT":
            return None, "核赔员已拒赔"
        # human APPROVE -> fall through to execution
        return _execution_step(state)

    if state.decision == AUTO_PROCESS:
        return _execution_step(state)

    return None, "无后续动作"


def run_status(state: AgentState) -> str:
    """Classify where a finished loop stands."""
    if (
        state.decision == HUMAN_REVIEW
        and state.human_request is not None
        and state.human_decision is None
    ):
        return AWAITING_HUMAN
    return DONE
