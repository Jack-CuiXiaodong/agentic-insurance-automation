"""Tool router tests -- the heart of 'RPA is one tool, not the workflow'."""

from agent.router import AWAITING_HUMAN, choose_next_tool, run_status
from agent.state import AgentState

CLAIM = {"claim_id": "CLM-001", "policy_id": "POL-001", "amount": 2500,
         "currency": "EUR", "status": "FNOL", "documents": [], "fraud_flag": False,
         "legacy_ui_variant": "v1"}
POLICY = {"policy_id": "POL-001", "status": "ACTIVE", "coverage": "x", "limit": 1, "deductible": 0}


def _loaded(decision):
    s = AgentState(task="t", claim_id="CLM-001")
    s.claim, s.policy, s.claim_history = CLAIM, POLICY, []
    s.retrieved_rules, s.risk, s.decision = [{"source": "a", "heading": "b", "text": "c"}], \
        {"risk_level": "LOW", "risk_score": 0}, decision
    return s


def test_progression_gathers_data_first():
    s = AgentState(task="t", claim_id="CLM-001")
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
    s.rpa_result = {"success": False, "message": "Element not found: #submit-claim-btn"}
    assert choose_next_tool(s)[0] == "browser_recover"


def test_success_ends_run():
    s = _loaded("AUTO_PROCESS")
    s.rpa_result = {"success": True}
    assert choose_next_tool(s)[0] is None


def test_human_review_requests_approval_then_pauses():
    s = _loaded("HUMAN_REVIEW")
    assert choose_next_tool(s)[0] == "request_human_approval"
    s.human_request = {"claim_id": "CLM-001"}
    assert choose_next_tool(s)[0] is None
    assert run_status(s) == AWAITING_HUMAN


def test_human_approve_then_executes_rpa():
    s = _loaded("HUMAN_REVIEW")
    s.human_request = {"claim_id": "CLM-001"}
    s.human_decision = "APPROVE"
    assert choose_next_tool(s)[0] == "execute_rpa"


def test_human_reject_ends_run():
    s = _loaded("HUMAN_REVIEW")
    s.human_request = {"claim_id": "CLM-001"}
    s.human_decision = "REJECT"
    assert choose_next_tool(s)[0] is None
