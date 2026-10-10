"""python -m heal_bench <cases.json> [--headed] [--delay 3] [--out report.json]"""

from __future__ import annotations

import argparse
import json
import sys

from browser.driver import BrowserSession
from heal_bench.runner import CORRECT, ERROR, WRONG, run, summarize, to_json


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m heal_bench", description="真实网页上的自愈只读测试")
    p.add_argument("cases", help="用例文件（JSON），格式见 heal_bench/cases.example.json")
    p.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    p.add_argument("--delay", type=float, default=3.0, help="两次打开页面之间的间隔秒数（默认 3）")
    p.add_argument("--out", help="把完整结果写成 JSON 报告")
    args = p.parse_args(argv)

    with open(args.cases, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]

    session = BrowserSession(headless=not args.headed)
    try:
        results = run(cases, session, delay=args.delay)
    finally:
        session.close()

    for r in results:
        mark = {"找对": "✓", "停手": "·", "找错": "✗", "出错": "!"}[r.outcome]
        line = f"{mark} {r.outcome}  {r.case} / {r.version}"
        if r.outcome != ERROR:
            line += f"  选中「{r.picked_label}」{r.similarity:.2f} 领先 {r.margin:.2f}  正确答案「{r.expected_label}」"
        print(line)
        for n in r.notes:
            print(f"      {n}")

    s = summarize(results)
    c = s["counts"]
    print(f"\n共 {len(results)} 个版本：找对 {c[CORRECT]} · 停手 {c['停手']} · 找错 {c[WRONG]} · 出错 {c[ERROR]}")
    print(f"找对率 {s['correct_rate']:.0%}　找错率 {s['wrong_rate']:.0%}（找错率才是最要紧的）")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(to_json(results))
        print(f"报告已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
