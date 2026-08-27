"""RPA execution abstraction.

The Agent talks to an :class:`RPAAdapter`, never to a concrete RPA product. This
is the seam that lets an enterprise RPA implementation (UiPath, 艺赛旗 iS-RPA,
影刀, Automation Anywhere, ...) be plugged in later *without touching the Agent*.

In this public PoC the only implementation is :class:`~rpa.mock_rpa.MockRPAAdapter`.
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
    """Minimal, product-agnostic RPA contract."""

    name: str = "abstract"

    @abstractmethod
    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        """Run a named, deterministic workflow. Raise ``RPAExecutionError`` on failure."""
        ...
