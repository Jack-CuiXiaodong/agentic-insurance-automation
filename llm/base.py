"""Backend-agnostic contract shared by every LLM implementation.

The Agent loop only ever talks to a :class:`LLMBackend`. Whether that backend is
a real Claude model or a deterministic policy is invisible to the loop -- which
is what keeps ``execute_rpa`` / ``browser_recover`` / ``request_human_approval``
tool selection identical in both modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """A single tool the model wants to execute."""

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class LLMDecision:
    """One turn of the agent loop.

    Exactly one of ``tool_calls`` / ``final_text`` is meaningful. ``reasoning``
    is a short human-readable justification surfaced in the execution trace.
    """

    tool_calls: List[ToolCall] = field(default_factory=list)
    final_text: Optional[str] = None
    reasoning: str = ""

    @property
    def is_final(self) -> bool:
        return self.final_text is not None and not self.tool_calls


@runtime_checkable
class LLMBackend(Protocol):
    """Anything that can decide the next agent step."""

    name: str

    def decide(
        self,
        *,
        system_prompt: str,
        transcript: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        state: Any,
    ) -> LLMDecision:
        ...
