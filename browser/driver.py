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
def page_session(url: str, headless: bool | None = None) -> Iterator["object"]:
    """Yield a Playwright ``Page`` navigated to ``url``.

    Requires ``playwright`` and a Chromium build (``playwright install chromium``).
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
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception as exc:  # pragma: no cover
            raise BrowserUnavailable(
                "Could not launch Chromium. Run: playwright install chromium"
            ) from exc
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            yield page
        finally:
            browser.close()
