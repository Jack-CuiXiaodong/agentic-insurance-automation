"""Diagnose and repair the Playwright/Chromium setup on this machine.

Prints ASCII only, so it cannot mojibake in a GBK console.
Run:  python fix_browser.py
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
ENV_FILE = REPO / ".env"

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]


def line(msg=""):
    print(msg, flush=True)


def rule():
    line("=" * 58)


def try_launch(executable_path=None):
    """Return (ok, message)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, "playwright package not importable: %s" % exc

    kwargs = {"headless": True}
    if executable_path:
        kwargs["executable_path"] = executable_path
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(**kwargs)
            ver = b.version
            b.close()
        return True, "launched OK, version %s" % ver
    except Exception as exc:
        return False, str(exc).strip().splitlines()[0][:200]


def write_env(path):
    """Add or replace PLAYWRIGHT_CHROMIUM_PATH in .env (kept out of git)."""
    key = "PLAYWRIGHT_CHROMIUM_PATH"
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith(key)]
    lines.append("%s=%s" % (key, path))
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    rule()
    line("  Playwright / Chromium diagnostic")
    rule()
    line("repo: %s" % REPO)
    line("python: %s" % sys.version.split()[0])
    line()

    # 1. package
    try:
        import playwright  # noqa: F401
        line("[1] playwright package .......... INSTALLED")
    except Exception as exc:
        line("[1] playwright package .......... MISSING")
        line("    fix: pip install playwright")
        line("    (%s)" % exc)
        return

    # 2. bundled chromium
    ok, msg = try_launch()
    if ok:
        line("[2] bundled Chromium ............ WORKS")
        line("    %s" % msg)
        line()
        rule()
        line("  Nothing to fix. The browser layer is fine.")
        line("  If case 3 still fails, the problem is elsewhere -")
        line("  send Claude the trace text from the Streamlit page.")
        rule()
        return

    line("[2] bundled Chromium ............ NOT USABLE")
    line("    %s" % msg)
    line()

    # 3. fall back to a browser already on the machine
    line("[3] looking for an existing browser ...")
    found = None
    for c in CANDIDATES:
        if c and Path(c).exists():
            line("    found: %s" % c)
            ok2, msg2 = try_launch(c)
            if ok2:
                line("    -> launches fine (%s)" % msg2)
                found = c
                break
            line("    -> cannot launch: %s" % msg2)
        else:
            line("    absent: %s" % c)

    line()
    if not found:
        rule()
        line("  No usable browser found.")
        line()
        line("  Option A - install Chromium via a domestic mirror:")
        line("     set PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright")
        line("     playwright install chromium")
        line()
        line("  Option B - install Google Chrome normally, then re-run this script.")
        line()
        line("  Cases 1 and 2 work without a browser; only case 3 needs it.")
        rule()
        return

    write_env(found)
    rule()
    line("  FIXED.")
    line("  Wrote PLAYWRIGHT_CHROMIUM_PATH into .env :")
    line("     %s" % found)
    line()
    line("  .env is gitignored, so this stays local.")
    line("  Restart the app to pick it up:")
    line("     python app.py")
    line("  then run case BX-2024-0003 again.")
    rule()


if __name__ == "__main__":
    main()
