# CLAUDE.md

给 Claude Code / Cowork 的项目约定。改这个仓库之前先读这里。

---

## 这个项目在主张什么

**不是取代 RPA，而是给 RPA 装上大脑。**

一层 AI 编排跑在既有自动化*上面*：能理解、能规划、能检索出决策依据、能路由到正确的
执行工具，并且在脆弱的自动化断掉时自己想办法。全部本地运行、全合成数据、无需 API Key。

改动如果削弱了这个主张，就是错的改动——哪怕它让代码更短。

---

## 跑起来

```bash
pip install -r requirements.txt
python -m pytest -q          # 期望 40 passed
python app.py                # 起 Streamlit（会自己把自己拉起在 streamlit 下）
python walkthrough.py all    # 自底向上逐层导读，含真实浏览器
```

浏览器层需要 Chromium。装不上（境外 CDN 拉不动）就跑 `python fix_browser.py`，
它会找机器上已有的 Edge / Chrome 并写进 `.env`。

---

## 两个 demo

| | 在哪 | 演示什么 |
|---|---|---|
| **Demo 1** | `demo/storyboard.py` · 界面「案件处理」标签页 | Agent 获取元素：网页改版后自己找回控件 |
| **Demo 2** | `demo/knowledge_qa.py` · 界面「问规则」标签页 | 业务知识库：一句中文问规则，秒回条款与出处 |

`docs/index.html` 是发给外部看的 GitHub Pages 页面，**只放这两个 demo**，
截图由 `demo/storyboard.py` 真实运行导出到 `docs/screenshots/act_*.png`。
不要往这页加第三个 demo，也不要用效果图替代真实截图——这个项目全部的说服力
来自「这是真跑出来的」。

---

## 架构边界（最重要的一条）

```
决策  ← risk/engine.py 的确定性代码。LLM 碰不到。
依据  ← RAG 从 knowledge/*.md 检索出的原文。
编排  ← agent/agent.py 的循环，决定下一步调哪个工具。
护栏  ← agent/agent.py 里的代码级闸门，不是提示词里的请求。
```

`AUTO_LIMIT = 10_000` 是 `risk/engine.py` 里的 Python 常量；
`knowledge/理赔规则.md` 和 `knowledge/核赔权限.md` 里那句「超过 10,000 元」
是**同一个数字的文字表述**，供 RAG 检索出佐证。两边必须手工保持一致。

**不要**把决策逻辑挪进知识库，也不要让检索结果去驱动金额判断。
理由：规则文档应该好改，护栏不应该好改。改了这条，这个项目最值钱的论点就没了。

---

## 视觉设计语言

对齐国内保险门户（服务大厅）：蓝色顶栏 + 面包屑 + 浅灰画布上的白卡片 + 实心蓝主按钮。

```
--brand      #4B76FC    主色（顶栏、主按钮、链接）
--brand-deep #3D38FD    深蓝（渐变、Agent 相关强调）
--brand-dark #2F55D4    hover
--canvas     #EDEFF1    页面底色
--surface    #FFFFFF    卡片
--line       #E3E6EA    描边
--ink        #1F2329    正文
--ink-2      #5A6068    次要文字
--ink-3      #919192    弱化文字
--bad        #E23B3B    失败 / 校验错误
--good       #16A34A    成功
圆角 4px，卡片阴影 0 1px 2px rgba(31,35,41,.04)
```

三处共用这套 token，改配色要三处一起改：
`docs/index.html`（内联 `<style>`）、`ui/streamlit_app.py`（`PORTAL_CSS`）、
`legacy_app/static/legacy.css`（仅 `.ui-v2`）。

---

## 模拟查验平台的两套皮肤

`legacy_app` 有 `?ui=v1` / `?ui=v2` 两个界面版本，由 `<body class="ui-v1|ui-v2">` 切换：

- **v1** 刻意做旧，代表十年没动过的存量系统
- **v2** 换成现代门户设计语言，代表「改版后」

改版**只换皮肤和主按钮的文案 / id**：`#verify-invoice-btn`「查验」→
`#check-invoice-btn`「查验发票信息」。字段名、表单 action、页面结构一律不动。

这两个 id 是 demo 的命脉，`rpa/mock_rpa.py`、`browser/recovery.py`、
`demo/storyboard.py`、测试都依赖它们。**改之前先想清楚为什么。**

---

## 改代码时的坑

**Streamlit 热重载碰不到 import 的模块。** 改了 `ui/`、`agent/`、`demo/` 里的代码，
按 R 没用——必须 `Ctrl+C` 重启 `python app.py`。只有改 `app.py` 本身按 R 才生效。

**装饰性代码一律 try/except 吞异常。** 截图、高亮、旁白横幅、停顿——
演示效果不该有能力让一次真实运行失败。见 `_shoot` / `_highlight` / `_banner`。

**`slow_mo` 和 `linger_ms` 默认 0。** 放慢只服务于有人在看的有头模式；
headless、CI、测试必须全速，否则 40 个测试会莫名其妙变慢。

**二进制不进 JSON 状态。** 截图挂在 `AgentState.evidence`，刻意不进 `snapshot()`——
状态是给机器读的，证据是给人看的。

**Windows 上文件是 CRLF。** 写文件时保持，否则 git 会报满屏无意义 diff。

---

## 测试

`tests/` 里 40 个测试，其中 `test_guardrail_blocks_rpa_bypass_on_high_value`
守着人工核赔闸门——它挂了说明护栏被绕开了，这是最不能妥协的一个。

提交前跑 `python -m pytest -q`。改了浏览器层再跑一次 `python walkthrough.py 9`。

---

## 免责

模拟查验平台是本地 mock，合成数据，非任何真实平台，不含任何真实机构的名称或标识。
视觉上借鉴的是国内保险门户通行的**设计语言**，不是任何一家公司的品牌。
这条底线在 README、页脚和模拟页面横幅里都写着，不要删。
