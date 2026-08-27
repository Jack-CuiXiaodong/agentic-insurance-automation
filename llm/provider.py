"""Select the active LLM backend from configuration."""

from __future__ import annotations

from config import settings
from llm.base import LLMBackend
from llm.deterministic import DeterministicLLM


def get_llm() -> LLMBackend:
    mode = settings.resolve_llm_mode()
    if mode == "anthropic":
        from llm.anthropic_llm import AnthropicLLM  # lazy import (optional dep)

        return AnthropicLLM()
    if mode == "openai_compatible":
        from llm.openai_compatible import OpenAICompatibleLLM  # lazy import (optional dep)

        return OpenAICompatibleLLM()
    return DeterministicLLM()
