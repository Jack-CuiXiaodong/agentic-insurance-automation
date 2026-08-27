"""逐层导读 / Step-by-step architecture walkthrough.

一次只点亮一层，看清它的输入和输出，最后再把它们串起来。

    python walkthrough.py          # 列出所有步骤
    python walkthrough.py 3        # 只跑第 3 步
    python walkthrough.py 1-6      # 跑第 1~6 步
    python walkthrough.py all      # 全部（第 9 步需要 Flask + Chromium）

Run one layer at a time, see its inputs and outputs, then watch them compose.
"""

from __future__ import annotations

import json
import sys
from typing import Callable, List, Tuple

W = 78


def pad(s: str, width: int) -> str:
    """左对齐补空格，按东亚宽字符算 2 格宽。"""
    import unicodedata
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    return s + " " * max(0, width - w)


def title(n: int, zh: str, en: str, files: str) -> None:
    print()
    print("=" * W)
    print(f" STEP {n}  {zh}")
    print(f"          {en}")
    print(f" 代码:     {files}")
    print("=" * W)


def note(*lines: str) -> None:
    for ln in lines:
        print(f"  │ {ln}")


def out(label: str, value) -> None:
    print(f"\n  ▶ {label}")
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    else:
        text = str(value)
    for ln in text.splitlines():
        print(f"    {ln}")


# ---------------------------------------------------------------- step 1
def step1_config() -> None:
    title(1, "配置层 —— 所有开关都在这里", "Config: every switch lives here", "config.py")
    from config import PROVIDER_PRESETS, settings

    note("这一层不做业务，只回答两个问题：",
         "  1) 用哪个 LLM 后端？   2) 用哪个保险数据后端？",
         "全部来自环境变量，没有任何硬编码密钥。")
    out("当前解析出的 LLM 后端 (resolve_llm_mode)", settings.resolve_llm_mode())
    note("",
         "解析顺序 (LLM_MODE=auto 时)：",
         "  ANTHROPIC_API_KEY 有 → anthropic",
         "  LLM_API_KEY 有       → openai_compatible (DeepSeek/Qwen/Kimi/GLM)",
         "  都没有               → deterministic（无网络、无密钥，也能全流程跑通）")
    out("保险后端 insurance_provider", settings.insurance_provider)
    out("Legacy 系统地址 legacy_base_url", settings.legacy_base_url)
    out("可选的 OpenAI 兼容厂商预设", list(PROVIDER_PRESETS.keys()))
    note("", "★ 记住：deterministic 后端不是「假装有 AI」，",
         "  它走的是和真 LLM 完全相同的 agent 循环和工具集。")


# ---------------------------------------------------------------- step 2
def step2_data() -> None:
    title(2, "数据层 —— 保险业务数据从哪来", "Data: the insurance backend", "insurance/carrier_client.py + data/demo_claims.json")
    from insurance.carrier_client import get_provider

    p = get_provider()
    note(f"当前 provider = {p.name}（抽象类 InsuranceProvider 的一个实现）",
         "换成真实保司 API = 再写一个实现，agent 代码一行不用改。")
    claim = p.get_claim("BX-2024-0001")
    out("get_claim('BX-2024-0001')", claim)
    out("get_policy('BD-2024-0001')", p.get_policy("BD-2024-0001"))
    out("get_claim_history('BD-2024-0001')", p.get_claim_history("BD-2024-0001"))
    note("", "三个 demo 案例的差别只有两个字段：")
    for cid in ("BX-2024-0001", "BX-2024-0002", "BX-2024-0003"):
        c = p.get_claim(cid)
        note(f"  {cid}: 金额=¥{c['amount']:>7,}  查验平台界面={c['invoice_platform_ui']}")
    note("  → BX-2024-0002 金额超 1 万自动核赔限额 → 转人工核赔",
         "  → BX-2024-0003 查验平台改版成 v2 → RPA 脆断 → 浏览器自愈")


# ---------------------------------------------------------------- step 3
def step3_rag() -> None:
    title(3, "知识层 (RAG) —— 决策依据从文档里检索", "RAG: retrieve the governing rules", "rag/ingest.py + rag/retriever.py")
    from rag.ingest import load_chunks
    from rag.retriever import get_retriever

    chunks = load_chunks()
    note("流程：knowledge/*.md  →  按 ## 标题切块  →  TF-IDF 余弦检索",
         "纯 Python，无外部服务、无网络、结果确定。")
    out(f"切出来 {len(chunks)} 个知识块", [f"{c.source} # {c.heading}" for c in chunks])

    q = "赔付金额 86000 元 超过自动核赔限额 转人工核赔"
    r = get_retriever()
    hits = r.search(q, k=3)
    out(f"retriever={r.name}  search({q!r}, k=3)",
        [{"source": h.source, "heading": h.heading, "score": round(h.score, 4)} for h in hits])
    out("命中的第 1 条原文", hits[0].text if hits else "(none)")
    note("", "★ 关键：agent 是拿「检索到的证据」做决策，不是靠模型记忆。",
         "  这条证据后面会原样出现在人工审批面板里，给理赔员看。")


# ---------------------------------------------------------------- step 4
def step4_risk() -> None:
    title(4, "决策层 —— 确定性风险引擎（LLM 碰不到）", "Risk engine: deterministic, never the LLM", "risk/engine.py")
    from insurance.carrier_client import get_provider
    from risk.engine import AUTO_LIMIT, assess_risk, decide

    note(f"这是纯函数：(报案, 保单, 历史出险) → 分数 + 核赔结论。没有任何 LLM 参与。",
         f"核心业务常量：AUTO_LIMIT = ¥{AUTO_LIMIT:,}（自动核赔金额上限）")
    p = get_provider()
    for cid in ("BX-2024-0001", "BX-2024-0002", "BX-2024-0003"):
        c = p.get_claim(cid)
        pol = p.get_policy(c["policy_id"])
        hist = p.get_claim_history(c["policy_id"])
        risk = assess_risk(c, pol, hist)
        dec = decide(c, pol, risk)
        out(f"{cid}  (¥{c['amount']:,})",
            {"risk": risk, "decision": dec["decision"], "reasons": dec["reasons"]})
    note("", "★ 项目最核心的设计原则：",
         "  「动钱的那个数字，永远不由 LLM 编造。」",
         "  LLM 负责编排和解释；分数和决策由这里算。")


# ---------------------------------------------------------------- step 5
def step5_router() -> None:
    title(5, "路由层 —— 下一步该调哪个工具", "Router: which tool comes next", "agent/router.py")
    from agent.router import ROUTES, choose_next_tool, run_status
    from agent.state import AgentState

    note("router 是一张显式的策略表。它只看 AgentState，推导下一步。",
         "因为是「从状态重新推导」而不是「记住走到第几步」，",
         "所以人工审批中断之后可以干净地续跑。")
    out("路由表 ROUTES", [f"{a}  {b}" for a, b in ROUTES])

    print("\n  ▶ 拿一个空 state，一步步喂数据，看它怎么变化：")
    s = AgentState(task="处理报案 BX-2024-0002", claim_id="BX-2024-0002")
    from insurance.carrier_client import get_provider
    p = get_provider()

    def show(tag: str) -> None:
        tool, why = choose_next_tool(s)
        print(f"    [{pad(tag, 22)}] next = {str(tool):<24} ({why})")

    show("空状态")
    s.claim = p.get_claim("BX-2024-0002");       show("有报案了")
    s.policy = p.get_policy("BD-2024-0002");     show("有保单了")
    s.claim_history = p.get_claim_history("BD-2024-0002"); show("有历史出险了")
    s.retrieved_rules = [];                      show("有 RAG 证据了")
    s.decision = "HUMAN_REVIEW";                 show("算完风险=需人工")
    s.human_request = {"amount": 86000};         show("已发出审批请求")
    print(f"    {'':26}  run_status = {run_status(s)}   ← 循环在这里干净地暂停")
    s.human_decision = "APPROVE";                show("人工点了 APPROVE")
    s.rpa_result = {"success": True};            show("RPA 成功")


# ---------------------------------------------------------------- step 6
def step6_tools() -> None:
    title(6, "工具层 —— agent 能选的工具目录", "Tools: the catalogue the agent picks from", "tools/registry.py + tools/*.py")
    from tools import registry

    note("8 个工具放在一个注册表里，不是写死的流水线。",
         "这正是本项目论点的代码体现：RPA 只是众多工具里的一个。")
    rows = [(t.name, t.fn.__module__.split(".")[-1], t.description.split(".")[0]) for t in registry.TOOLS.values()]
    print()
    print(f"    {pad('工具名', 24)} {pad('实现模块', 18)} 作用")
    print(f"    {'-'*24} {'-'*18} {'-'*30}")
    for name, mod, desc in rows:
        print(f"    {name:<24} {mod:<18} {desc}")
    note("", "每个工具签名统一为 fn(state, trace, **kwargs) → dict：",
         "  · 读/写同一个 AgentState",
         "  · 往同一条 Trace 里写人类可读的日志",
         "  · 失败时返回结构化错误，而不是抛异常炸掉循环",
         "    （RPA 失败必须能被 agent「看到」并决定去自愈，这是关键）")


# ---------------------------------------------------------------- step 7
def step7_llm() -> None:
    title(7, "大脑层 —— 三个后端，一个接口", "LLM: three backends, one interface", "llm/base.py + llm/provider.py + llm/*.py")
    from llm.base import LLMDecision, ToolCall
    from llm.provider import get_llm

    note("agent 循环只认 LLMBackend 这个 Protocol，只有一个方法：",
         "    decide(system_prompt, transcript, tools_schema, state) → LLMDecision",
         "",
         "三个实现：",
         "  anthropic_llm.py        真 Claude，原生 tool calling",
         "  openai_compatible.py    DeepSeek / Qwen / Kimi / GLM（同一套 wire format）",
         "  deterministic.py        直接调用 step 5 的 router，无密钥无网络")
    llm = get_llm()
    out("当前激活的后端", llm.name)

    from agent.state import AgentState
    s = AgentState(task="处理报案 BX-2024-0001", claim_id="BX-2024-0001")
    d = llm.decide(system_prompt="", transcript=[], tools_schema=[], state=s)
    out("对空状态问「下一步做什么」",
        {"tool_calls": [c.name for c in d.tool_calls], "reasoning": d.reasoning, "is_final": d.is_final})
    note("", "★ deterministic 后端只有 31 行 —— 它把 router 的输出包成 LLMDecision。",
         "  换成真 Claude，agent/agent.py 一个字都不用改。")


# ---------------------------------------------------------------- step 8
def step8_loop() -> None:
    title(8, "主循环 —— 把上面 7 层串起来", "The agent loop wires it all together", "agent/agent.py")
    from agent.agent import run_agent
    from agent.router import AWAITING_HUMAN

    note("循环体（最多 14 步）：",
         "   1. 问后端：下一步调哪个工具？",
         "   2. 过一遍代码级护栏 _guard()   ← 治理不靠模型自觉",
         "   3. 执行工具，写进 state + trace",
         "   4. 需要人工时干净地 break 出来",
         "",
         "下面跑 Case 1 和 Case 2。最后那步 RPA 需要 Flask + Chromium；",
         "起不来也不影响你看清前面 6 层是怎么串起来的。")

    from legacy_app import manager
    manager.ensure_running()

    print("\n" + "  " + "─" * (W - 4))
    print("  案例 1 · BX-2024-0001 —— 低风险快速直通")
    print("  " + "─" * (W - 4))
    r1 = run_agent("处理报案 BX-2024-0001", claim_id="BX-2024-0001")
    for line in r1.trace.as_list():
        print(f"    {line}")
    print(f"\n    status={r1.status}   tools={' → '.join(r1.state.executed_tools)}")
    print(f"    最终: {r1.state.final_summary}")

    print("\n" + "  " + "─" * (W - 4))
    print("  案例 2 · BX-2024-0002 —— 金额超限，卡在人工核赔")
    print("  " + "─" * (W - 4))
    r2 = run_agent("处理报案 BX-2024-0002", claim_id="BX-2024-0002")
    for line in r2.trace.as_list():
        print(f"    {line}")
    print(f"\n    status={r2.status}  ← {'暂停，等人' if r2.status == AWAITING_HUMAN else r2.status}")
    out("交给核赔员看的审批包 human_request", r2.state.human_request)

    print("\n  ▶ 护栏验证：假装有个不听话的 LLM，硬要在没审批时调 execute_rpa")
    import copy
    from agent.agent import Agent
    from agent.trace import Trace
    a = Agent(trace=Trace())

    # 场景 A：还没发出审批请求 → 护栏把它改道去请求审批
    sA = copy.deepcopy(r2.state)
    sA.human_request = None
    print(f"    A) 尚未请求审批   execute_rpa  →  {a._guard('execute_rpa', sA)}")
    # 场景 B：已请求、人还没点 → 护栏直接掐掉这一步
    sB = copy.deepcopy(r2.state)
    print(f"    B) 已请求待人工   execute_rpa  →  {a._guard('execute_rpa', sB)}   (__noop__ = 循环停在这)")
    # 场景 C：人已批准 → 放行
    sC = copy.deepcopy(r2.state)
    sC.human_decision = "APPROVE"
    print(f"    C) 人工已批准     execute_rpa  →  {a._guard('execute_rpa', sC)}")
    note("", "★ 审批闸门是写在代码里的护栏，不是 prompt 里的请求。",
         "  就算模型完全不听话，也绕不过去。",
         "  tests/test_routing.py::test_guardrail_blocks_rpa_bypass_on_high_value 守着它。")

    print("\n  ▶ 人工点 APPROVE 后续跑（同一个 state、同一条 trace）：")
    seen = len(r2.trace.as_list())          # 先记长度：trace 是同一个对象，续跑后会变长
    r3 = run_agent("处理报案 BX-2024-0002", state=r2.state, trace=r2.trace, human_decision="APPROVE")
    for line in r3.trace.as_list()[seen:]:
        print(f"    {line}")
    print(f"\n    最终: {r3.state.final_summary}")
    note("", "★ 注意：续跑没有重新取报案 / 重新算风险。",
         "  router 从 AgentState 重新推导下一步，已经做过的自动跳过。")


# ---------------------------------------------------------------- step 9
def step9_rpa() -> None:
    title(9, "执行层 —— RPA 脆断 → 浏览器自愈", "RPA breaks, the browser recovers", "rpa/mock_rpa.py + browser/recovery.py + legacy_app/")
    note("这一步要真起一个 Flask「增值税发票查验平台（本地模拟）」+ 真开 Chromium。",
         "",
         "  legacy_app  ?ui=v1 → 按钮 #verify-invoice-btn 「查验」",
         "              ?ui=v2 → 按钮 #check-invoice-btn  「查验发票信息」",
         "  mock_rpa    写死了 #verify-invoice-btn —— v1 能跑，v2 必炸（这是故意的）",
         "  recovery    不认死选择器，读实时 DOM，按语义找等价控件")

    from legacy_app import manager
    print("\n  ▶ 启动 legacy 系统 ...")
    if not manager.ensure_running():
        print("    ❌ 起不来（Flask 没装？）—— 跳过这一步")
        return
    print(f"    ✓ 运行中: {__import__('config').settings.legacy_base_url}")

    from agent.agent import run_agent
    print("\n  " + "─" * (W - 4))
    print("  案例 3 · BX-2024-0003 —— 查验平台已改版成 v2")
    print("  " + "─" * (W - 4))
    r = run_agent("处理报案 BX-2024-0003", claim_id="BX-2024-0003")
    for line in r.trace.as_list():
        print(f"    {line}")
    print(f"\n    最终: {r.state.final_summary}")
    if r.state.recovery_result:
        out("recovery 看到的候选控件", r.state.recovery_result.get("candidates"))
    note("", "★ RPA = 认死选择器，界面一改就断。",
         "  Playwright 自愈 = 读页面 + 按语义匹配，同一个改动能扛过去。",
         "  两条路走的是同一个 browser/driver.py，区别只在「怎么找元素」。")


# ---------------------------------------------------------------- step 10
def step10_ui() -> None:
    title(10, "界面层 —— 把 trace 摆给人看", "UI: surface the trace to a human", "ui/streamlit_app.py + app.py")
    note("app.py 是唯一入口，会自己把自己重新拉起在 streamlit 下。",
         "UI 做四件事：",
         "  1. 选报案、跑 agent",
         "  2. 完整渲染执行 trace（本项目的一等交付物）",
         "  3. 摊开 RAG 依据给核赔员看",
         "  4. 人工核赔面板 通过 / 拒赔 → 用同一个 state 续跑",
         "",
         "注意 ui/streamlit_app.py 里的 ThreadPoolExecutor：",
         "  Playwright 的同步 API 不能和 Streamlit 的事件循环同线程，",
         "  所以 agent 被丢到另一个线程里跑。",
         "",
         "启动：  streamlit run app.py    或    python app.py")


STEPS: List[Tuple[str, Callable[[], None]]] = [
    ("配置层 config", step1_config),
    ("数据层 insurance", step2_data),
    ("知识层 rag", step3_rag),
    ("决策层 risk", step4_risk),
    ("路由层 router", step5_router),
    ("工具层 tools", step6_tools),
    ("大脑层 llm", step7_llm),
    ("主循环 agent", step8_loop),
    ("执行层 rpa+browser", step9_rpa),
    ("界面层 ui", step10_ui),
]


def menu() -> None:
    print("\n逐层导读 · Agentic Insurance Automation Lab")
    print("=" * W)
    print("自底向上，一次点亮一层：\n")
    for i, (name, _) in enumerate(STEPS, 1):
        extra = "   (需要 Flask + Chromium)" if i == 9 else ""
        print(f"  {i:>2}. {name}{extra}")
    print(f"\n用法:  python walkthrough.py 3      # 单步")
    print(f"       python walkthrough.py 1-8    # 范围（1-8 不需要浏览器）")
    print(f"       python walkthrough.py all    # 全部\n")


def parse(arg: str) -> List[int]:
    if arg == "all":
        return list(range(1, len(STEPS) + 1))
    if "-" in arg:
        a, b = arg.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(arg)]


def main() -> None:
    if len(sys.argv) < 2:
        menu()
        return
    for n in parse(sys.argv[1]):
        if 1 <= n <= len(STEPS):
            STEPS[n - 1][1]()
    print()


if __name__ == "__main__":
    main()
