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
