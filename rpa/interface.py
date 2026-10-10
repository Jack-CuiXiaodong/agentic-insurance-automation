"""RPA execution abstraction.

The Agent talks to an :class:`RPAAdapter`, never to a concrete RPA product. This
is the seam that lets any RPA product act as the agent's hands *without touching
the Agent* -- no product is privileged.

Implementations: :class:`~rpa.mock_rpa.MockRPAAdapter` (default, local demo
platform) and :class:`~rpa.mcp_adapter.MCPRPAAdapter` (any product that exposes
its workflows as MCP tools; 影刀 is the first worked example in docs/rpa_mcp.md).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


class RPAExecutionError(Exception):
    """A deterministic RPA workflow failed (e.g. a selector no longer matches).

    Carries an optional screenshot of the page *as the bot saw it* at the moment
    of failure. Without it, "元素未找到" is a claim; with it, it is evidence.
    """

    def __init__(self, message: str, screenshot: bytes | None = None):
        super().__init__(message)
        self.screenshot = screenshot


@dataclass
class RPAResult:
    success: bool
    workflow: str
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    # PNG of the final page. Never enters as_dict() -- binary has no business in
    # the JSON state; the UI reads this attribute directly.
    screenshot: bytes | None = field(default=None, repr=False)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "workflow": self.workflow,
            "message": self.message,
            "details": self.details,
        }


class RPAAdapter(ABC):
    """Minimal, product-agnostic RPA contract.

    A real enterprise product (影刀开放 API / 艺赛旗 / 来也 / 弘玑 / UiPath) only
    ever needs to implement ``execute_workflow(name, params)`` -- that one
    method is the entire integration surface, by design.

    ``supports_shared_page`` is optional and off by default. It exists for the
    *in-process* case (this mock, or anything else running inside this same
    Python process) where handing the live Playwright ``Page`` object directly
    is possible. A real RPA product runs out-of-process and has no Python
    ``Page`` to hand over -- for that case, the adapter does not implement
    this capability at all; instead, make the product expose its browser's CDP
    (Chrome DevTools Protocol) endpoint, and have the recovery layer attach to
    it with Playwright's ``connect_over_cdp`` to pick up the same page. A
    desktop-app or online-banking target that has no browser at all needs a
    different seam entirely -- the product's own UI-automation capability, or
    a vision model reading the screen -- not this one.
    """

    name: str = "abstract"
    supports_shared_page: bool = False
    # True when the workflow takes an optional ``selector`` parameter: once a
    # human approves a healing proposal, the brain hands the new selector to the
    # hands on the next call, instead of someone re-recording the workflow.
    accepts_selector_hint: bool = False

    @abstractmethod
    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        """Run a named, deterministic workflow. Raise ``RPAExecutionError`` on failure."""
        ...
