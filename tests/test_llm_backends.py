"""LLM backend-selection and schema-conversion tests.

No network calls: these test the pure decision logic (which backend gets
picked) and the Anthropic-shape -> OpenAI-shape tool schema converter used by
the OpenAI-compatible backend (DeepSeek / Qwen / Kimi / GLM / custom).
"""

from config import PROVIDER_PRESETS, Settings
from llm.openai_compatible import _to_openai_tool
from tools.registry import tool_schemas


def _settings(**overrides):
    base = dict(
        anthropic_api_key="",
        anthropic_model="claude-sonnet-4-20250514",
        llm_provider="deepseek",
        llm_api_key="",
        llm_model_override="",
        llm_base_url_override="",
        llm_mode="auto",
        insurance_provider="mock",
        facio_base_url="https://api.facio.io",
        facio_api_key="",
        legacy_host="127.0.0.1",
        legacy_port=5001,
        playwright_headless=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_auto_prefers_anthropic_when_both_keys_present():
    s = _settings(anthropic_api_key="sk-ant-x", llm_api_key="sk-deepseek-x")
    assert s.resolve_llm_mode() == "anthropic"


def test_auto_falls_back_to_openai_compatible():
    s = _settings(anthropic_api_key="", llm_api_key="sk-deepseek-x")
    assert s.resolve_llm_mode() == "openai_compatible"


def test_auto_falls_back_to_deterministic_with_no_keys():
    s = _settings()
    assert s.resolve_llm_mode() == "deterministic"


def test_explicit_mode_overrides_auto_detection():
    s = _settings(anthropic_api_key="sk-ant-x", llm_mode="deterministic")
    assert s.resolve_llm_mode() == "deterministic"


def test_deepseek_is_the_default_provider_and_has_a_preset():
    s = _settings()
    assert s.llm_provider == "deepseek"
    endpoint = s.openai_compatible_endpoint()
    assert endpoint["base_url"] == PROVIDER_PRESETS["deepseek"]["base_url"]
    assert endpoint["model"]


def test_model_and_base_url_overrides_win_over_preset():
    s = _settings(llm_provider="qwen", llm_model_override="qwen-max",
                  llm_base_url_override="https://example.com/v1")
    endpoint = s.openai_compatible_endpoint()
    assert endpoint["model"] == "qwen-max"
    assert endpoint["base_url"] == "https://example.com/v1"


def test_all_presets_have_base_url_and_model():
    for name, preset in PROVIDER_PRESETS.items():
        assert preset.get("base_url", "").startswith("http"), name
        assert preset.get("model"), name


def test_tool_schema_converts_to_openai_function_shape():
    anthropic_shape = tool_schemas()[0]
    openai_shape = _to_openai_tool(anthropic_shape)
    assert openai_shape["type"] == "function"
    fn = openai_shape["function"]
    assert fn["name"] == anthropic_shape["name"]
    assert fn["description"] == anthropic_shape["description"]
    assert fn["parameters"] == anthropic_shape["input_schema"]


def test_every_registered_tool_converts_cleanly():
    for schema in tool_schemas():
        converted = _to_openai_tool(schema)
        assert converted["function"]["parameters"]["type"] == "object"
