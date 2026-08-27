"""System prompt and state rendering for the real-LLM backends."""

from __future__ import annotations

import json
from typing import Any

from agent.state import AgentState

SYSTEM_PROMPT = """\
你是一名车险理赔自动化 Agent。你的职责是**编排工具**，而不是自己猜测业务结论。

工作规则：
1. 先取数再决策：依次读取报案、对应保单、历史出险，然后通过 RAG（search_rules）\
检索适用的业务规则。
2. 风险评分与核赔结论由确定性工具（calculate_risk）计算。它返回的 `decision` \
是唯一权威结论。不得自行编造风险分，也不得推翻该结论。
3. 按结论路由执行：
   - AUTO_PROCESS（自动核赔）：调用 execute_rpa，到增值税发票查验平台验证维修发票。
   - HUMAN_REVIEW（人工核赔）：调用 request_human_approval 后**立即停止**。在核赔员\
明确通过之前，绝不可调用 execute_rpa。人工审批环节不可绕过。
   - REJECT（拒赔）：停止，报案不能继续处理。
4. 若 execute_rpa 因页面元素不再匹配而失败（查验平台改版），调用 browser_recover \
自适应地完成该操作。browser_recover 只能在 RPA 失败之后使用。
5. 每一步只调用一个工具。当无需再调用工具时，用一段简短的中文总结说明发生了什么、\
以及为什么。

每一步都会给你任务描述和当前状态快照。请选出唯一最合适的下一个工具，或结束。"""


def render_state(state: AgentState) -> str:
    """A compact, model-friendly snapshot of where things stand."""
    def brief(d: Any, keys: list[str]) -> dict:
        d = d or {}
        return {k: d.get(k) for k in keys if k in d}

    snap = {
        "任务": state.task,
        "报案": brief(state.claim, ["claim_id", "policy_id", "plate_no", "amount", "currency",
                                    "status", "accident_date", "documents", "fraud_flag",
                                    "invoice_code", "invoice_no", "invoice_platform_ui"]),
        "保单": brief(state.policy, ["policy_id", "status", "coverage", "limit",
                                     "deductible", "inception_date", "expiry_date"]),
        "历史出险笔数": len(state.claim_history) if state.claim_history is not None else None,
        "已检索规则": [f"{r['source']}: {r['heading']}" for r in (state.retrieved_rules or [])],
        "风险": state.risk,
        "核赔结论": state.decision,
        "RPA结果": brief(state.rpa_result, ["success", "message"]),
        "自愈结果": brief(state.recovery_result, ["success", "matched_label"]),
        "是否已请求人工审批": state.human_request is not None,
        "核赔员结论": state.human_decision,
        "已执行工具": state.executed_tools,
    }
    return (
        f"任务：{state.task}\n\n当前状态：\n"
        + json.dumps(snap, ensure_ascii=False, indent=2, default=str)
        + "\n\n请选出唯一最合适的下一个工具，或给出简短总结后结束。"
    )
