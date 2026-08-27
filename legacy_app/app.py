"""A local stand-in for a VAT-invoice verification platform.

This exists so the RPA / recovery demo has something real to automate. It is a
**mock**: synthetic data, no branding, and no connection to any real
verification service. It stands in for the class of system that makes this whole
project's point -- a web-only government/utility portal with no data interface,
which back-office RPA has to drive by clicking, and whose page structure changes
without notice.

Two UI variants of the same "查验" screen ship here:

* ``?ui=v1`` -- the original screen. The action control is
  ``#verify-invoice-btn`` labelled **"查验"**.
* ``?ui=v2`` -- the screen *after an unannounced redesign*. The control is now
  ``#check-invoice-btn`` labelled **"查验发票信息"**.

A brittle, selector-based RPA workflow that targets ``#verify-invoice-btn``
works on v1 and breaks on v2 -- which is exactly the failure the agent recovers
from.

Run standalone:  ``python legacy_app/app.py``
"""

from __future__ import annotations

import argparse

from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/", methods=["GET"])
def invoice_check():
    return render_template(
        "invoice_check.html",
        ui=request.args.get("ui", "v1"),
        claim_id=request.args.get("claim_id", ""),
        invoice_code=request.args.get("invoice_code", ""),
        invoice_no=request.args.get("invoice_no", ""),
        amount=request.args.get("amount", ""),
    )


@app.route("/verify", methods=["POST"])
def verify():
    return render_template(
        "verified.html",
        claim_id=request.form.get("claim_id", ""),
        invoice_code=request.form.get("invoice_code", ""),
        invoice_no=request.form.get("invoice_no", ""),
        amount=request.form.get("amount", ""),
        ui=request.form.get("ui", "v1"),
    )


@app.route("/health")
def health():
    return {"status": "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description="增值税发票查验平台（本地模拟）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
