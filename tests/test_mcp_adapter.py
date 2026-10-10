"""MCPRPAAdapter: any RPA product that publishes its workflows as MCP tools can
be the agent's hands. A fake RPA MCP server runs in-process here, so these tests
need no network and no real RPA product."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver import MCPServer  # noqa: E402

from agent.agent import run_agent  # noqa: E402
from browser.fingerprint import Fingerprint  # noqa: E402
from browser.healing import HealStore  # noqa: E402
from browser.recovery import VERIFY_INVOICE, RecoveryResult  # noqa: E402
from rpa.interface import RPAExecutionError  # noqa: E402
from rpa.mcp_adapter import MCPRPAAdapter  # noqa: E402
from tools import browser_tools, rpa_tools  # noqa: E402

PARAMS = {
    "claim_id": "BX-2024-0001", "invoice_code": "011002000000", "invoice_no": "12345678",
    "amount": 3800, "ui_variant": "v1", "headless": True, "pace": 0.0,
}


def _fake_rpa(reply):
    """A stand-in RPA product: records what it was called with, answers ``reply``."""
    server = MCPServer("fake-rpa")
    calls = []

    @server.tool()
    def verify_invoice(claim_id: str, invoice_code: str = "", invoice_no: str = "",
                       amount: float = 0, selector: str = "") -> dict:
        calls.append({"claim_id": claim_id, "invoice_code": invoice_code,
                      "invoice_no": invoice_no, "amount": amount, "selector": selector})
        return reply

    return server, calls


def _adapter(server):
    return MCPRPAAdapter(server=server, tool="verify_invoice", vendor="测试RPA", token="")


def test_success_returns_result_and_sends_only_contract_inputs():
    server, calls = _fake_rpa({"result_status": "VERIFIED", "message": "查验一致"})
    result = _adapter(server).execute_workflow("verify_invoice", PARAMS)
    assert result.success
    assert result.details["result_status"] == "VERIFIED"
    assert result.details["via"] == "测试RPA · MCP"
    assert calls[0]["claim_id"] == "BX-2024-0001"
    assert calls[0]["selector"] == ""  # no hint given -> nothing sent


def test_reported_failure_raises_so_the_agent_can_heal():
    server, _ = _fake_rpa({"success": False, "error": "元素未找到：#verify-invoice-btn"})
    with pytest.raises(RPAExecutionError, match="元素未找到"):
        _adapter(server).execute_workflow("verify_invoice", PARAMS)


def test_tool_exception_raises():
    server = MCPServer("fake-rpa")

    @server.tool()
    def verify_invoice(claim_id: str) -> dict:
        raise ValueError("boom")

    with pytest.raises(RPAExecutionError, match="执行失败"):
        _adapter(server).execute_workflow("verify_invoice", PARAMS)


def test_unstructured_reply_is_a_failure_not_a_success():
    """An adapter that cannot tell whether the hands did the job must not say they did."""
    server, _ = _fake_rpa("done")
    with pytest.raises(RPAExecutionError, match="不符合约定"):
        _adapter(server).execute_workflow("verify_invoice", PARAMS)
    server, _ = _fake_rpa({"message": "ok"})  # JSON, but no result_status
    with pytest.raises(RPAExecutionError):
        _adapter(server).execute_workflow("verify_invoice", PARAMS)


def test_unreachable_rpa_fails_fast_with_a_clear_message():
    adapter = MCPRPAAdapter(server="http://127.0.0.1:9/mcp", tool="verify_invoice",
                            vendor="测试RPA", token="", timeout=5)
    start = time.monotonic()
    with pytest.raises(RPAExecutionError, match="无法调用 测试RPA"):
        adapter.execute_workflow("verify_invoice", PARAMS)
    assert time.monotonic() - start < 30


def test_missing_url_is_reported():
    adapter = MCPRPAAdapter(server="", tool="verify_invoice", vendor="测试RPA", token="")
    with pytest.raises(RPAExecutionError, match="RPA_MCP_URL"):
        adapter.execute_workflow("verify_invoice", PARAMS)


@pytest.fixture
def swap_adapter():
    original = rpa_tools._adapter

    def _swap(adapter):
        rpa_tools._adapter = adapter

    yield _swap
    rpa_tools._adapter = original


def test_agent_finishes_straight_through_on_mcp_hands(swap_adapter):
    server, calls = _fake_rpa({"result_status": "VERIFIED"})
    swap_adapter(_adapter(server))
    r = run_agent("处理报案 BX-2024-0001", claim_id="BX-2024-0001")
    assert r.state.rpa_result["success"]
    assert r.state.rpa_result["details"]["via"] == "测试RPA · MCP"
    assert "browser_recover" not in r.state.executed_tools
    assert any("测试RPA · MCP" in line for line in r.trace.as_list())
    assert len(calls) == 1


def test_mcp_failure_routes_to_our_self_healing(swap_adapter, monkeypatch):
    server, _ = _fake_rpa({"success": False, "error": "元素未找到：#verify-invoice-btn"})
    swap_adapter(_adapter(server))
    healed = []

    def _fake_recover(*args, **kwargs):
        healed.append(kwargs)
        return RecoveryResult(success=True, matched_label="查验发票信息",
                              details={"result_status": "VERIFIED"})

    monkeypatch.setattr(browser_tools, "recover_action", _fake_recover)
    r = run_agent("处理报案 BX-2024-0001", claim_id="BX-2024-0001")
    assert not r.state.rpa_result["success"]
    assert "browser_recover" in r.state.executed_tools
    assert healed and r.state.recovery_result["success"]


def test_approved_fix_is_handed_to_the_rpa_as_a_selector(swap_adapter, tmp_path):
    store = HealStore(path=str(tmp_path / "rt.json"), baseline_path=str(tmp_path / "bl.json"))
    fp = Fingerprint(label="查验发票信息", tag="button", type="submit", role="button",
                     action="/verify", fields=["amount", "claim_id"], id="check-invoice-btn",
                     name="check_invoice", ordinal=0)
    proposal = store.propose(VERIFY_INVOICE.key, fp, "#check-invoice-btn")
    store.review(proposal.id, approve=True)

    server, calls = _fake_rpa({"result_status": "VERIFIED"})
    swap_adapter(_adapter(server))

    import agent.agent as agent_mod
    from agent.state import AgentState

    state = AgentState(task="处理报案 BX-2024-0001", claim_id="BX-2024-0001")
    state.runtime["heal_store"] = store
    r = agent_mod.Agent().run(state)
    assert calls[0]["selector"] == "#check-invoice-btn"
    assert any("把人工批准过的修复交给 RPA" in line for line in r.trace.as_list())


def test_mock_hands_never_receive_a_selector_hint():
    """The mock is deliberately brittle -- it must keep ignoring hints, or the demo lies."""
    from rpa.mock_rpa import MockRPAAdapter

    assert MockRPAAdapter.accepts_selector_hint is False
    assert MCPRPAAdapter.accepts_selector_hint is True


def test_provider_selects_hands_from_config(monkeypatch):
    from config import settings
    from rpa.mock_rpa import MockRPAAdapter
    from rpa.provider import get_adapter

    assert isinstance(get_adapter(), MockRPAAdapter)
    monkeypatch.setattr(settings, "rpa_provider", "mcp")
    assert isinstance(get_adapter(), MCPRPAAdapter)
