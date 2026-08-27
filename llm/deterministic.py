"""Deterministic LLM backend.

No API key, no network -- yet it exercises the *identical* agent loop and tool
set as the real-Claude backend. It decides the next tool with the explicit
policy in :mod:`agent.router`. This is what guarantees the demo always runs, and
runs the same way, in a live interview.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agent.router import choose_next_tool
from llm.base import LLMDecision, ToolCall


class DeterministicLLM:
    name = "deterministic"

    def decide(
        self,
        *,
        system_prompt: str,
        transcript: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        state: Any,
    ) -> LLMDecision:
        tool_name, reasoning = choose_next_tool(state)
        if tool_name is None:
            return LLMDecision(final_text=reasoning, reasoning=reasoning)
        return LLMDecision(tool_calls=[ToolCall(name=tool_name)], reasoning=reasoning)
