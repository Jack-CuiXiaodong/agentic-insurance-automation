"""RPA "hands" reached over MCP -- any vendor, one adapter.

Any RPA product that publishes its workflows as MCP tools (影刀's console "MCP
管理" does this today; others are adding it) plugs in here by configuration
alone: ``RPA_MCP_URL`` / ``RPA_MCP_TOKEN`` / ``RPA_MCP_TOOL``. Nothing in this
module knows or branches on which vendor is on the other end -- vendor
differences live in ``.env`` and in docs/rpa_mcp.md, never in code.

The RPA stays the *hands*. It is called to do one deterministic action
("verify this invoice") and report what happened. Rules, risk, approval and
self-healing all stay on this side. A failed run raises ``RPAExecutionError``,
which the router already sends to browser recovery -- so a broken vendor
workflow is healed exactly like the mock one.

The result contract (see docs/rpa_mcp.md) is a JSON object with at least
``result_status``. Anything that does not parse into that shape counts as a
failure, not a success: an adapter that cannot tell whether the hands did the
job must not report that they did.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from config import settings
from rpa.interface import RPAAdapter, RPAExecutionError, RPAResult

# Only these go over the wire. Mock-only knobs (ui_variant, headless, pace)
# describe the local demo platform and mean nothing to a real RPA product.
CONTRACT_INPUTS = ("claim_id", "invoice_code", "invoice_no", "amount", "selector")


def _payload(result: Any) -> Optional[Dict[str, Any]]:
    structured = getattr(result, "structured_content", None) or (
        getattr(result, "model_extra", None) or {}
    ).get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _text(result: Any) -> str:
    return " ".join(
        t for t in (getattr(b, "text", "") for b in getattr(result, "content", None) or []) if t
    )


class MCPRPAAdapter(RPAAdapter):
    supports_shared_page = False  # the vendor's browser is out of process; recovery opens its own
    accepts_selector_hint = True

    def __init__(
        self,
        server: Any = None,
        tool: Optional[str] = None,
        vendor: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        # ``server`` is a URL in production; tests pass an in-process MCPServer.
        self.server = server if server is not None else settings.rpa_mcp_url
        self.tool = tool or settings.rpa_mcp_tool
        self.vendor = vendor or settings.rpa_mcp_vendor
        self.token = token if token is not None else settings.rpa_mcp_token
        self.timeout = timeout if timeout is not None else settings.rpa_mcp_timeout
        self.name = f"{self.vendor} · MCP"

    def _client(self):
        from mcp import Client  # lazy: optional dependency

        if isinstance(self.server, str):
            from mcp.client.streamable_http import streamable_http_client
            from mcp.shared._httpx_utils import create_mcp_http_client

            headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
            transport = streamable_http_client(
                self.server, http_client=create_mcp_http_client(headers=headers)
            )
            return Client(transport, read_timeout_seconds=self.timeout)
        return Client(self.server, read_timeout_seconds=self.timeout)

    async def _call(self, arguments: Dict[str, Any]):
        async with self._client() as client:
            return await client.call_tool(self.tool, arguments)

    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        if not self.server:
            raise RPAExecutionError("RPA_PROVIDER=mcp 但没有配置 RPA_MCP_URL")
        arguments = {k: parameters[k] for k in CONTRACT_INPUTS if parameters.get(k) not in (None, "")}
        try:
            result = asyncio.run(self._call(arguments))
        except Exception as exc:
            raise RPAExecutionError(f"无法调用 {self.vendor} 的 MCP 工具 {self.tool}：{exc}") from exc

        payload = _payload(result)
        if getattr(result, "is_error", False):
            reason = (payload or {}).get("error") or _text(result) or "未返回原因"
            raise RPAExecutionError(f"{self.vendor} 流程执行失败：{reason}")
        if payload is None:
            raise RPAExecutionError(
                f"{self.vendor} 返回的结果不符合约定（需要 JSON 对象，含 result_status）：{_text(result)[:200]}"
            )
        if payload.get("success") is False or payload.get("error") or not payload.get("result_status"):
            reason = payload.get("error") or payload.get("message") or "未返回 result_status"
            raise RPAExecutionError(f"{self.vendor} 流程执行失败：{reason}")

        return RPAResult(
            success=True,
            workflow=workflow_name,
            message=str(payload.get("message", "")),
            details={**payload, "via": self.name},
        )
