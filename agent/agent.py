"""The lightweight, tool-calling Agent loop.

One small loop, backend-agnostic. It:
  * asks the active LLM backend for the next tool (or a finish),
  * enforces governance guardrails in code (not on trust),
  * executes the chosen tool, and
  * pauses cleanly for human-in-the-loop approval.

The same loop drives both the deterministic and the real-Claude backends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.prompts import SYSTEM_PROMPT, render_state
from agent.router import AWAITING_HUMAN, DONE, run_status
from agent.state import HUMAN_REVIEW, AgentState
from agent.trace import Trace
from llm.base import LLMBackend
from llm.provider import get_llm
from tools import registry

MAX_STEPS = 14


@dataclass
class AgentResult:
    status: str  # DONE | AWAITING_HUMAN
    state: AgentState
    trace: Trace
    llm_name: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "llm": self.llm_name,
            "state": self.state.snapshot(),
            "trace": self.trace.as_list(),
        }


class Agent:
    def __init__(self, llm: Optional[LLMBackend] = None, trace: Optional[Trace] = None):
        self.llm = llm or get_llm()
        self.trace = trace or Trace()

    # -- guardrails ---------------------------------------------------------
    def _guard(self, tool_name: str, state: AgentState) -> str:
        """Enforce governance regardless of what the LLM asked for.

        Returns the tool name that will actually run (possibly redirected).
        """
        # Human approval gate: never let RPA run on a HUMAN_REVIEW claim that a
        # human has not explicitly approved.
        if (
            tool_name == "execute_rpa"
            and state.decision == HUMAN_REVIEW
            and state.human_decision != "APPROVE"
        ):
            if state.human_request is None:
                self.trace.warn("Guardrail: RPA blocked -- human approval required first")
                return "request_human_approval"
            self.trace.warn("Guardrail: RPA blocked -- awaiting human decision")
            return "__noop__"
        return tool_name

    # -- main loop ----------------------------------------------------------
    def run(self, state: AgentState) -> AgentResult:
        tools_schema = registry.tool_schemas()
        if not self.trace.events:  # keep one continuous trace across a human pause/resume
            self.trace.add(f"Agent started (LLM backend: {self.llm.name})")

        for _ in range(MAX_STEPS):
            # Clean pause point for human-in-the-loop.
            if run_status(state) == AWAITING_HUMAN:
                break

            transcript = [{"role": "user", "content": render_state(state)}]
            decision = self.llm.decide(
                system_prompt=SYSTEM_PROMPT,
                transcript=transcript,
                tools_schema=tools_schema,
                state=state,
            )

            if decision.is_final:
                break
            if not decision.tool_calls:
                break

            call = decision.tool_calls[0]
            tool_name = self._guard(call.name, state)
            if tool_name == "__noop__":
                break
            registry.execute(tool_name, state, self.trace, call.arguments)

        status = run_status(state)
        state.final_summary = build_final_summary(state)
        if status == DONE:
            self.trace.add(f"Agent finished: {state.final_summary}")
        else:
            self.trace.warn("Paused: awaiting human approval")
        return AgentResult(status=status, state=state, trace=self.trace, llm_name=self.llm.name)


def build_final_summary(state: AgentState) -> str:
    """A deterministic, human-readable outcome line (mode-independent)."""
    cid = state.claim_id or "?"
    if state.decision == "REJECT":
        return f"{cid}: REJECTED -- policy not in force."
    if state.human_decision == "REJECT":
        return f"{cid}: REJECTED by human adjuster."
    if state.recovery_result and state.recovery_result.get("success"):
        return f"{cid}: RPA failed on a changed UI; recovered via browser automation -> SUCCESS."
    if state.rpa_result and state.rpa_result.get("success"):
        via = "after human approval" if state.human_decision == "APPROVE" else "straight-through"
        return f"{cid}: processed via RPA ({via}) -> SUCCESS."
    if run_status(state) == AWAITING_HUMAN:
        amt = (state.human_request or {}).get("amount", "")
        cur = (state.human_request or {}).get("currency", "EUR")
        return f"{cid}: awaiting human approval ({cur} {amt})."
    if state.rpa_result and not state.rpa_result.get("success"):
        return f"{cid}: RPA failed and could not be recovered."
    return f"{cid}: no terminal action taken."


# -- convenience --------------------------------------------------------------
_CLAIM_RE = re.compile(r"(CLM-\d+)", re.IGNORECASE)


def parse_claim_id(task: str) -> str:
    m = _CLAIM_RE.search(task or "")
    return m.group(1).upper() if m else ""


def run_agent(
    task: str,
    claim_id: str | None = None,
    llm: Optional[LLMBackend] = None,
    human_decision: Optional[str] = None,
    trace: Optional[Trace] = None,
    state: Optional[AgentState] = None,
) -> AgentResult:
    """One-call entry point used by the UI, tests and app.py."""
    if state is None:
        state = AgentState(task=task, claim_id=claim_id or parse_claim_id(task))
    if human_decision is not None:
        state.human_decision = human_decision
    return Agent(llm=llm, trace=trace).run(state)
