"""Single entry point.

* ``streamlit run app.py``  -> launches the UI directly (recommended).
* ``python app.py``          -> re-launches itself under Streamlit for you.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def main() -> None:
    if _in_streamlit():
        from ui.streamlit_app import main as ui_main

        ui_main()
    else:
        # Convenience: `python app.py` bootstraps Streamlit.
        print("Launching Streamlit UI...  (or run: streamlit run app.py)")
        cmd = [sys.executable, "-m", "streamlit", "run", os.path.abspath(__file__)]
        raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
