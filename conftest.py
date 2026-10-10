import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

# Tests must never write to data/heal_runtime.json -- that file is this
# machine's live state (approved fixes, pending proposals), not a fixture.
# browser.healing.HealStore reads this env var lazily (per-instance, not at
# import time), so setting it here before any test runs is enough; individual
# tests that need a *fresh* store per test still pass their own tmp_path.
os.environ.setdefault(
    "HEAL_STORE_PATH",
    os.path.join(tempfile.gettempdir(), "agentic-insurance-automation-test-heal-store.json"),
)
