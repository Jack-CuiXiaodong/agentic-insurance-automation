"""Backend for any provider that speaks the OpenAI ``chat.completions`` wire
format with tool calling.

This is the practical default for a China-market deployment: Anthropic's API
is not reliably reachable from mainland China, while DeepSeek, 通义千问 (Qwen,
via DashScope's OpenAI compatible-mode), Kimi (Moonshot) and 智谱 GLM all speak
this exact same request/response shape. One implementation, swapped by
``base_url`` + ``model`` + API key -- see ``config.PROVIDER_PRESETS``.

Cost/performance note: at the time this was written, DeepSeek's flash-tier
model was the cheapest mainstream option that still supports tool calling
reliably, which is why it's the default preset. Prices and model ids move
fast in this market -- check the docs link in the preset before relying on it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from config import PROVIDER_PRESETS, settings
from llm.base import LLMDecision, ToolCall


def _to_openai_tool(tool_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Convert our Anthropic-shaped tool schema to the OpenAI function shape.

    Anthropic: {"name", "description", "input_schema"}
    OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
    """
    return {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "openai package not installed. pip install openai, or set "
                "LLM_MODE=deterministic."
            ) from exc

        endpoint = settings.openai_compatible_endpoint()
        base_url, model = endpoint["base_url"], endpoint["model"]
        if not base_url or not model:
            raise RuntimeError(
                f"Unknown LLM_PROVIDER='{settings.llm_provider}' with no LLM_BASE_URL/"
                f"LLM_MODEL override. Set LLM_PROVIDER to one of "
                f"{sorted(PROVIDER_PRESETS.keys())}, or set LLM_BASE_URL + LLM_MODEL "
                f"yourself for a custom endpoint."
            )
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set (needed for LLM_MODE=openai_compatible)."
            )

        self._client = OpenAI(api_key=settings.llm_api_key, base_url=base_url)
        self._model = model
        self.name = f"openai-compatible:{settings.llm_provider}:{model}"

    def decide(
        self,
        *,
        system_prompt: str,
        transcript: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        state: Any,
    ) -> LLMDecision:
        messages = [{"role": "system", "content": system_prompt}, *transcript]
        openai_tools = [_to_openai_tool(t) for t in tools_schema]

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            max_tokens=1024,
        )
        choice = resp.choices[0].message
        text = (choice.content or "").strip()

        if choice.tool_calls:
            tc = choice.tool_calls[0]
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            return LLMDecision(
                tool_calls=[ToolCall(name=tc.function.name, arguments=args, id=tc.id)],
                reasoning=text,
            )
        return LLMDecision(final_text=text or "Done.", reasoning=text)
