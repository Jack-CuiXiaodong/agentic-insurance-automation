"""A tiny stand-in for a *legacy* claim-management web system.

This exists so the RPA / recovery demo has something real to automate. It ships
two UI variants of the same "Submit claim" screen:

* ``?ui=v1`` -- the original screen. The submit control is
  ``#submit-claim-btn`` labelled **"Submit Claim"**.
* ``?ui=v2`` -- the screen *after an unannounced UI change*. The control is now
  ``#confirm-submit-btn`` labelled **"Confirm & Submit Claim"**.

A brittle, selector-based RPA workflow that targets ``#submit-claim-btn`` works
on v1 and breaks on v2 -- which is exactly the failure the agent recovers from.

Run standalone:  ``python legacy_app/app.py``
"""

from __future__ import annotations

import argparse

from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/", methods=["GET"])
def claim_form():
    ui = request.args.get("ui", "v1")
    claim_id = request.args.get("claim_id", "")
    amount = request.args.get("amount", "")
    return render_template(
        "claim_form.html", ui=ui, claim_id=claim_id, amount=amount
    )


@app.route("/submit", methods=["POST"])
def submit():
    claim_id = request.form.get("claim_id", "")
    amount = request.form.get("amount", "")
    ui = request.form.get("ui", "v1")
    return render_template(
        "submitted.html", claim_id=claim_id, amount=amount, ui=ui
    )


@app.route("/health")
def health():
    return {"status": "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Legacy claim management system")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
