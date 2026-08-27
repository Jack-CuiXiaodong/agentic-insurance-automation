"""Real Claude tool-calling backend.

Each ``decide`` is one Anthropic API call that is shown the task + a structured
snapshot of the current :class:`AgentState` and the available tools, and returns
the next tool to run (or a final answer). Presenting a fresh state snapshot each
step -- rather than accumulating a raw transcript -- keeps the loop re-enterable
across UI reruns (important for the human-in-the-loop pause) while remaining
genuine model-driven tool selection.
"""

from __future__ import annotations

from typing import Any, Dict, List

from config import settings
from llm.base import LLMDecision, ToolCall


class AnthropicLLM:
    name = "anthropic"

    def __init__(self) -> None:
        try:
            import anthropic
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "anthropic package not installed. pip install anthropic, or set "
                "LLM_MODE=deterministic."
            ) from exc
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def decide(
        self,
        *,
        system_prompt: str,
        transcript: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        state: Any,
    ) -> LLMDecision:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            tools=tools_schema,
            messages=transcript,
        )
        tool_calls: List[ToolCall] = []
        texts: List[str] = []
        for block in resp.content:
            if block.type == "tool_use":
                tool_calls.append(
                    ToolCall(name=block.name, arguments=dict(block.input or {}), id=block.id)
                )
            elif block.type == "text":
                texts.append(block.text)

        reasoning = " ".join(texts).strip()
        if tool_calls:
            return LLMDecision(tool_calls=tool_calls[:1], reasoning=reasoning)
        return LLMDecision(final_text=reasoning or "Done.", reasoning=reasoning)
