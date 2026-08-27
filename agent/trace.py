"""Human-readable execution trace.

The trace is a first-class deliverable: it is what a reviewer reads in the UI to
understand *why* the agent did what it did, without opening the source.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

# Status markers used consistently across the whole project.
OK = "✓"
WARN = "⚠"
FAIL = "❌"
RECOVER = "↻"
INFO = "•"


@dataclass
class TraceEvent:
    ts: str
    marker: str
    message: str

    def line(self) -> str:
        return f"{self.ts} {self.marker} {self.message}".rstrip()


@dataclass
class Trace:
    events: List[TraceEvent] = field(default_factory=list)
    _clock: float = field(default_factory=time.time)

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def add(self, message: str, marker: str = INFO) -> TraceEvent:
        ev = TraceEvent(self._now(), marker, message)
        self.events.append(ev)
        return ev

    def ok(self, message: str) -> TraceEvent:
        return self.add(message, OK)

    def warn(self, message: str) -> TraceEvent:
        return self.add(message, WARN)

    def fail(self, message: str) -> TraceEvent:
        return self.add(message, FAIL)

    def recover(self, message: str) -> TraceEvent:
        return self.add(message, RECOVER)

    def as_text(self) -> str:
        return "\n".join(e.line() for e in self.events)

    def as_list(self) -> List[str]:
        return [e.line() for e in self.events]
