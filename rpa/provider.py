"""Select which RPA product acts as the agent's hands."""

from __future__ import annotations

from config import settings
from rpa.interface import RPAAdapter
from rpa.mock_rpa import MockRPAAdapter


def get_adapter() -> RPAAdapter:
    if settings.rpa_provider == "mcp":
        from rpa.mcp_adapter import MCPRPAAdapter  # lazy: optional dependency

        return MCPRPAAdapter()
    return MockRPAAdapter()
