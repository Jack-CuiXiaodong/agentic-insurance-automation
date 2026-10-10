"""Read-only self-healing benchmark against real web pages.

Records a control's fingerprint on one version of a page, then asks the healing
decision to find the same control on later versions -- real redesigns, either
archived snapshots or the live page over time -- and scores each answer against
a human label: 找对 (correct), 停手 (abstained), 找错 (wrong).

Never clicks, never submits, never touches a captcha. See heal_bench/README.md.
"""
