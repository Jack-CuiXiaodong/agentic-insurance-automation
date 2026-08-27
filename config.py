"""Central configuration.

All runtime configuration is read from environment variables (optionally loaded
from a local ``.env`` file). Nothing secret is ever hard-coded.

The single most important design decision here is the *multi-backend LLM
layer*:

* ``anthropic`` -- real Claude tool-calling (requires ``ANTHROPIC_API_KEY``).
  Anthropic's API is not reliably reachable from mainland China, so this is the
  "if you have it, use it" option rather than the default.
* ``openai_compatible`` -- any provider that speaks the OpenAI
  ``chat.completions`` wire format with tool calling. This covers essentially
  every mainstream Chinese model API: DeepSeek, 通义千问 (Qwen / DashScope
  compatible-mode), Kimi (Moonshot), 智谱 GLM, or a self-hosted vLLM/Ollama
  endpoint. One backend implementation, swapped by base_url + model name.
  ``LLM_PROVIDER`` picks a built-in preset (default: ``deepseek`` -- verified
  cheapest mainstream option with tool-calling support at the time this was
  written; see the docs link in ``PROVIDER_PRESETS`` below and re-check pricing
  before a real deployment, it moves fast).
* ``deterministic`` -- no key, no network, no cost. A fully deterministic
  policy drives the *identical* agent loop and tool set, so the demo always
  runs end-to-end even with zero configuration -- exactly what you want when
  the venue's network can't reach any model API at all.

``LLM_MODE`` can force one of ``auto`` (default), ``anthropic``,
``openai_compatible`` or ``deterministic``. In ``auto``, Anthropic wins if its
key is set, else an OpenAI-compatible key wins, else deterministic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict

try:  # optional dependency; the project runs fine without it
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a convenience only
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Built-in presets for mainstream OpenAI-wire-compatible Chinese model APIs.
# Model IDs and pricing tiers change frequently -- these are sane, working
# defaults as of writing (Aug 2026), not a promise they stay current. Always
# confirm against the linked docs before a real deployment.
PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "docs": "https://api-docs.deepseek.com/quick_start/pricing/",
        "note": "Cheapest verified option with tool-calling support; good default. "
                "DeepSeek renames/replaces model ids across generations (this one "
                "confirmed live as of Aug 2026) -- re-check the docs link if this 404s.",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "docs": "https://bailian.console.aliyun.com/",
        "note": "Alibaba Cloud Bailian, OpenAI compatible-mode endpoint.",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2-turbo-preview",
        "docs": "https://platform.kimi.com/docs/pricing/chat",
        "note": "Moonshot AI. Confirm the current model id in the console.",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.5-flash",
        "docs": "https://open.bigmodel.cn/pricing",
        "note": "Zhipu GLM. Confirm the current model id in the console.",
    },
    # "custom": set LLM_BASE_URL / LLM_MODEL yourself (self-hosted, another
    # provider, etc.) -- no preset needed.
}


@dataclass
class Settings:
    # -- LLM: Anthropic Claude ------------------------------------------------
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(
        default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    )

    # -- LLM: any OpenAI-wire-compatible provider (DeepSeek / Qwen / Kimi / ...)
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "deepseek").lower())
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_model_override: str = field(default_factory=lambda: _env("LLM_MODEL"))
    llm_base_url_override: str = field(default_factory=lambda: _env("LLM_BASE_URL"))

    # auto | anthropic | openai_compatible | deterministic
    llm_mode: str = field(default_factory=lambda: _env("LLM_MODE", "auto").lower())

    # -- Insurance backend --------------------------------------------------
    # mock | core  (core = a carrier's own policy/claims system)
    insurance_provider: str = field(
        default_factory=lambda: _env("INSURANCE_PROVIDER", "mock").lower()
    )
    core_api_base_url: str = field(
        default_factory=lambda: _env("CORE_API_BASE_URL", "http://127.0.0.1:8080")
    )
    core_api_key: str = field(default_factory=lambda: _env("CORE_API_KEY"))

    # -- Mock invoice-verification platform (for the RPA / recovery demo) ---
    legacy_host: str = field(default_factory=lambda: _env("LEGACY_HOST", "127.0.0.1"))
    legacy_port: int = field(default_factory=lambda: int(_env("LEGACY_PORT", "5001")))

    # -- Browser ------------------------------------------------------------
    playwright_headless: bool = field(
        default_factory=lambda: _env("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    )
    # Optional: launch a Chromium/Chrome binary that is already on the machine
    # instead of the build Playwright downloads for itself. Useful in sandboxes
    # and CI images that ship a browser whose build number does not match the
    # installed Playwright. Empty (default) = let Playwright resolve it.
    playwright_chromium_path: str = field(
        default_factory=lambda: _env("PLAYWRIGHT_CHROMIUM_PATH")
    )

    @property
    def legacy_base_url(self) -> str:
        return f"http://{self.legacy_host}:{self.legacy_port}"

    def openai_compatible_endpoint(self) -> Dict[str, str]:
        """Resolve {base_url, model} for the configured OpenAI-compatible provider."""
        preset = PROVIDER_PRESETS.get(self.llm_provider, {})
        base_url = self.llm_base_url_override or preset.get("base_url", "")
        model = self.llm_model_override or preset.get("model", "")
        return {"base_url": base_url, "model": model}

    def resolve_llm_mode(self) -> str:
        """Decide which LLM backend to actually use."""
        if self.llm_mode == "anthropic":
            return "anthropic"
        if self.llm_mode == "openai_compatible":
            return "openai_compatible"
        if self.llm_mode == "deterministic":
            return "deterministic"
        # auto: Anthropic first (if you have working access to it), then any
        # configured OpenAI-compatible provider (DeepSeek etc.), then the
        # deterministic fallback.
        if self.anthropic_api_key:
            return "anthropic"
        if self.llm_api_key:
            return "openai_compatible"
        return "deterministic"


settings = Settings()
