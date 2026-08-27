"""Tool router tests -- the heart of 'RPA is one tool, not the workflow'."""

from agent.router import AWAITING_HUMAN, choose_next_tool, run_status
from agent.state import AgentState

CLAIM = {"claim_id": "BX-2024-0001", "policy_id": "BD-2024-0001", "amount": 3800,
         "currency": "CNY", "status": "待核赔", "documents": [], "fraud_flag": False,
         "invoice_platform_ui": "v1"}
POLICY = {"policy_id": "BD-2024-0001", "status": "有效", "coverage": "x",
          "limit": 1, "deductible": 0}


def _loaded(decision):
    s = AgentState(task="t", claim_id="BX-2024-0001")
    s.claim, s.policy, s.claim_history = CLAIM, POLICY, []
    s.retrieved_rules, s.risk, s.decision = [{"source": "a", "heading": "b", "text": "c"}], \
        {"risk_level": "LOW", "risk_score": 0}, decision
    return s


def test_progression_gathers_data_first():
    s = AgentState(task="t", claim_id="BX-2024-0001")
    assert choose_next_tool(s)[0] == "get_claim"
    s.claim = CLAIM
    assert choose_next_tool(s)[0] == "get_policy"
    s.policy = POLICY
    assert choose_next_tool(s)[0] == "get_claim_history"
    s.claim_history = []
    assert choose_next_tool(s)[0] == "search_rules"
    s.retrieved_rules = [{"source": "a", "heading": "b", "text": "c"}]
    assert choose_next_tool(s)[0] == "calculate_risk"


def test_auto_process_routes_to_rpa():
    s = _loaded("AUTO_PROCESS")
    assert choose_next_tool(s)[0] == "execute_rpa"


def test_rpa_failure_routes_to_browser_recovery():
    s = _loaded("AUTO_PROCESS")
    s.rpa_result = {"success": False, "message": "元素未找到：#verify-invoice-btn"}
    assert choose_next_tool(s)[0] == "browser_recover"


def test_no_browser_at_all_does_not_attempt_recovery():
    """Recovery drives the same browser, so with no browser there is nothing to
    try. The router must read the explicit flag -- an earlier version matched on
    message text that the driver never actually produces, so this branch was
    dead and the agent burned a step on a doomed recovery."""
    s = _loaded("AUTO_PROCESS")
    s.rpa_result = {
        "success": False,
        "message": "Playwright is not installed. Run: pip install playwright",
        "browser_unavailable": True,
    }
    assert choose_next_tool(s)[0] is None


def test_success_ends_run():
    s = _loaded("AUTO_PROCESS")
    s.rpa_result = {"success": True}
    assert choose_next_tool(s)[0] is None


def test_human_review_requests_approval_then_pauses():
    s = _loaded("HUMAN_REVIEW")
    assert choose_next_tool(s)[0] == "request_human_approval"
    s.human_request = {"claim_id": "BX-2024-0001"}
    assert choose_next_tool(s)[0] is None
    assert run_status(s) == AWAITING_HUMAN


def test_human_approve_then_executes_rpa():
    s = _loaded("HUMAN_REVIEW")
    s.human_request = {"claim_id": "BX-2024-0001"}
    s.human_decision = "APPROVE"
    assert choose_next_tool(s)[0] == "execute_rpa"


def test_human_reject_ends_run():
    s = _loaded("HUMAN_REVIEW")
    s.human_request = {"claim_id": "BX-2024-0001"}
    s.human_decision = "REJECT"
    assert choose_next_tool(s)[0] is None
