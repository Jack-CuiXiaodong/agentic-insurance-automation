"""Claim-data + end-to-end (no browser) + governance guardrail tests."""

from agent.agent import Agent, run_agent
from agent.router import AWAITING_HUMAN
from agent.state import AgentState
from agent.trace import Trace
from insurance.carrier_client import MockCarrierProvider
from llm.base import LLMDecision, ToolCall


def test_demo_claims_present():
    p = MockCarrierProvider()
    for cid in ("BX-2024-0001", "BX-2024-0002", "BX-2024-0003"):
        claim = p.get_claim(cid)
        assert claim["claim_id"] == cid
        assert claim["currency"] == "CNY"
        assert p.get_policy(claim["policy_id"])["status"] == "有效"


def test_case3_invoice_platform_ui_changed():
    p = MockCarrierProvider()
    assert p.get_claim("BX-2024-0003")["invoice_platform_ui"] == "v2"


def test_case2_pauses_for_human_without_touching_browser():
    """High-value claim must reach the human gate and NOT run RPA."""
    res = run_agent("处理报案 BX-2024-0002")
    assert res.status == AWAITING_HUMAN
    assert res.state.decision == "HUMAN_REVIEW"
    assert "request_human_approval" in res.state.executed_tools
    assert "execute_rpa" not in res.state.executed_tools


class _AlwaysRPALLM:
    """A misbehaving 'LLM' that tries to run RPA immediately -- to prove the
    guardrail, not the policy, is what enforces human approval."""

    name = "always-rpa"

    def decide(self, *, system_prompt, transcript, tools_schema, state: AgentState) -> LLMDecision:
        if state.claim is None:
            return LLMDecision(tool_calls=[ToolCall("get_claim")])
        if state.policy is None:
            return LLMDecision(tool_calls=[ToolCall("get_policy")])
        if state.retrieved_rules is None:
            return LLMDecision(tool_calls=[ToolCall("search_rules")])
        if state.decision is None:
            return LLMDecision(tool_calls=[ToolCall("calculate_risk")])
        # decision is known -> try to bypass approval by going straight to RPA
        return LLMDecision(tool_calls=[ToolCall("execute_rpa")])


def test_guardrail_blocks_rpa_bypass_on_high_value():
    state = AgentState(task="处理报案 BX-2024-0002", claim_id="BX-2024-0002")
    res = Agent(llm=_AlwaysRPALLM(), trace=Trace()).run(state)
    assert res.status == AWAITING_HUMAN
    assert "execute_rpa" not in res.state.executed_tools
    assert "request_human_approval" in res.state.executed_tools


def test_claim_id_is_parsed_from_a_chinese_task_line():
    from agent.agent import parse_claim_id

    assert parse_claim_id("处理报案 BX-2024-0003") == "BX-2024-0003"
    assert parse_claim_id("没有报案号") == ""
