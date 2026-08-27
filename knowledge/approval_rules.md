# Approval Rules

## Human approval thresholds
- Any claim with an amount **greater than EUR 5,000** must be routed to a human
  adjuster for approval before payment.
- Any claim assessed as **HIGH risk** must be routed to a human adjuster,
  regardless of amount.

## Human approval is mandatory and cannot be bypassed
- The agent must **pause** and request explicit human approval for high-value or
  high-risk claims.
- The agent must not auto-approve, auto-pay, or otherwise proceed past a required
  human approval gate.

## Decisions
- `AUTO_PROCESS` -- eligible for straight-through processing.
- `HUMAN_REVIEW` -- requires an adjuster's APPROVE / REJECT decision.
- `REJECT` -- policy not in force; the claim cannot proceed.
