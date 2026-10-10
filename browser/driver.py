"""Thin Playwright helper shared by the RPA adapter and the recovery module.

Isolating the Playwright launch in one place keeps both the (brittle) RPA path
and the (adaptive) recovery path honest and comparable -- the difference between
them is *how they locate elements*, not their plumbing.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from config import settings


class BrowserUnavailable(RuntimeError):
    """Raised when Playwright / Chromium is not installed."""


@contextmanager
def page_session(
    url: str,
    headless: bool | None = None,
    slow_mo: int = 0,
    linger_ms: int = 0,
) -> Iterator["object"]:
    """Yield a Playwright ``Page`` navigated to ``url``.

    Requires ``playwright`` and a Chromium build (``playwright install chromium``).

    ``slow_mo`` and ``linger_ms`` exist purely for *live* demos. Headless runs go
    full speed; when a human is watching a real window, every action needs to be
    slow enough to follow and the final frame needs to stay on screen long enough
    to read. Both default to 0, so CI and tests are unaffected.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise BrowserUnavailable(
            "Playwright is not installed. Run: pip install playwright && "
            "playwright install chromium"
        ) from exc

    headless = settings.playwright_headless if headless is None else headless
    with sync_playwright() as p:
        launch_kwargs = {"headless": headless, "slow_mo": slow_mo}
        if settings.playwright_chromium_path:
            launch_kwargs["executable_path"] = settings.playwright_chromium_path
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            raise BrowserUnavailable(
                "Could not launch Chromium. Run: playwright install chromium "
                "(or set PLAYWRIGHT_CHROMIUM_PATH to an existing browser binary)"
            ) from exc
        page = None
        try:
            # A narrow viewport keeps the evidence screenshots tight: the mock
            # platform's card is ~560px, so a 1280px frame is mostly whitespace.
            page = browser.new_page(viewport={"width": 900, "height": 620})
            page.goto(url, wait_until="domcontentloaded")
            yield page
        finally:
            # Hold the last frame so a human watching can actually read it.
            if page is not None and linger_ms:
                try:
                    page.wait_for_timeout(linger_ms)
                except Exception:  # pragma: no cover - cosmetic only
                    pass
            browser.close()


class BrowserSession:
    """A browser kept open across multiple tool calls, for in-place recovery.

    ``page_session`` opens and closes a browser around a single step -- correct
    for an isolated action, wrong for recovery: a real bot sits on an open
    browser while the page underneath it changes, and reopening a fresh window
    to "recover" is not recovery, it is a retry that happens to look similar.
    ``BrowserSession`` is the version that stays open: ``execute_rpa`` opens one
    and leaves the page exactly as it failed; ``browser_recover`` reuses that
    same tab.

    Lifecycle is owned by the caller (see ``AgentState.runtime`` /
    ``close_runtime``) -- this class never closes itself implicitly.
    """

    def __init__(self, headless: bool | None = None):
        self.headless = settings.playwright_headless if headless is None else headless
        self._pw = None
        self._browser = None
        self.page = None

    @property
    def alive(self) -> bool:
        return self.page is not None and not self.page.is_closed()

    def open(self, url: str) -> "object":
        if self._pw is None:
            try:
                from playwright.sync_api import sync_playwright
            except Exception as exc:  # pragma: no cover
                raise BrowserUnavailable(
                    "Playwright is not installed. Run: pip install playwright && "
                    "playwright install chromium"
                ) from exc
            self._pw = sync_playwright().start()
            launch_kwargs = {"headless": self.headless}
            if settings.playwright_chromium_path:
                launch_kwargs["executable_path"] = settings.playwright_chromium_path
            try:
                self._browser = self._pw.chromium.launch(**launch_kwargs)
            except Exception as exc:  # pragma: no cover
                self._pw.stop()
                self._pw = None
                raise BrowserUnavailable(
                    "Could not launch Chromium. Run: playwright install chromium "
                    "(or set PLAYWRIGHT_CHROMIUM_PATH to an existing browser binary)"
                ) from exc
            self.page = self._browser.new_page(viewport={"width": 900, "height": 620})
        self.page.goto(url, wait_until="domcontentloaded")
        return self.page

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # pragma: no cover
                pass
        self._browser = None
        self._pw = None
        self.page = None
