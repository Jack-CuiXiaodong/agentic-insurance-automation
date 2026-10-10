# 接真实 RPA：任何 RPA 都可以当手脚

这个系统的**大脑**是自己的：Agent 编排、业务规则检索、确定性核赔、指纹自愈、人工审批。
RPA 只是**手脚**——被叫去做一个确定的动作（"查验这张发票"），然后汇报结果。

不绑定任何一家 RPA。只要某个 RPA 产品能把它的流程发布成 **MCP 工具**，
改几行配置就能接进来，代码一行不用动。影刀目前做得最完善，下面拿它当第一个示例。

```
Agent → execute_rpa → RPAAdapter
                        ├─ MockRPAAdapter   默认，本地模拟查验平台
                        └─ MCPRPAAdapter    任何支持 MCP 的 RPA（影刀 / 其他）
RPA 失败 → 我们的指纹自愈接手（和 mock 完全同一条路）
```

---

## 1. RPA 侧的统一约定

无论哪家 RPA，发布成 MCP 工具的那个流程按这个约定来，就能接上。

**输入参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `claim_id` | 文本 | 报案号 |
| `invoice_code` | 文本 | 发票代码 |
| `invoice_no` | 文本 | 发票号码 |
| `amount` | 数字 | 开票金额 |
| `selector` | 文本，可选 | 人工批准过的新选择器。**有值就用它定位「查验」按钮，没值就用流程里录制的元素** |

**输出：一个 JSON 对象**

```json
{"result_status": "VERIFIED", "message": "查验一致"}
```

失败时**不要抛异常，返回结构化结果**（MCP 会把异常吞成一句"执行出错"，原因就丢了）：

```json
{"success": false, "error": "元素未找到：#verify-invoice-btn"}
```

我们这边的判定规则（`rpa/mcp_adapter.py`）：

| RPA 返回 | 我们怎么看 |
|---|---|
| JSON 且有 `result_status` | 成功 |
| `success: false` 或带 `error` | 失败 → 转自愈 |
| 不是 JSON、或没有 `result_status` | **按失败处理**——判断不了手脚有没有把事办成，就不能说办成了 |
| 连不上 / 超时（`RPA_MCP_TIMEOUT`，默认 300 秒） | 失败，消息里写明连不上哪家的哪个工具 |

`result_status` 是业务结果（`VERIFIED` 查验一致、`MISMATCH` 不一致……），
流程能跑完就算"执行成功"，业务上是否一致由我们这边判断，不由 RPA 判断。

---

## 2. 配置

```bash
pip install mcp          # 只有接外部 RPA 才需要
```

`.env`：

```
RPA_PROVIDER=mcp
RPA_MCP_URL=<RPA 给出的 MCP 地址>
RPA_MCP_TOKEN=<鉴权令牌，按 Bearer 发送>
RPA_MCP_TOOL=verify_invoice       # RPA 侧发布的工具名
RPA_MCP_VENDOR=影刀               # 只用于执行轨迹里显示，不影响逻辑
```

然后照常 `python app.py`。执行轨迹里会显示「执行 RPA 流程「发票查验」（影刀 · MCP）」。

---

## 3. 示例：影刀

1. 在影刀里新建应用「发票查验」，流程参数按上面的输入参数建；
   最后一步把结果按上面的 JSON 格式作为输出参数返回。
   失败分支用【Try】【Catch】接住，返回 `{"success": false, "error": ...}`，不要让流程直接报错退出。
2. 「查验」按钮的定位：`selector` 有值时用它定位（影刀的元素属性值可以设成变量；
   也可以用【执行JS脚本】按这个 CSS 选择器点击），没值就用元素库里录制的元素。
3. 发版，在控制台「MCP 管理」里把这个应用映射成 MCP 工具，指定执行机器人。
4. 把控制台给出的地址和令牌填进 `.env`。

> 说明：以上影刀步骤按影刀公开的功能写成，具体界面和返回格式以影刀当前版本为准。
> 如果影刀返回的结果外面多包了一层，只需要改 `rpa/mcp_adapter.py` 里的 `_payload()` 一处。

---

## 4. 没有 MCP 的 RPA 怎么接

直接实现 `rpa/interface.py` 的 `RPAAdapter.execute_workflow(name, params)`：
调它的开放 API / 命令行，成功返回 `RPAResult`，失败抛 `RPAExecutionError`。
然后在 `rpa/provider.py` 里加一个分支。Agent、路由、自愈都不用改。

---

## 5. 不变的底线

- **审批不交给 RPA。** 大额案件在 RPA 被调用之前就被 Agent 的代码护栏拦下。
- **自愈不交给 RPA。** RPA 失败后由我们的指纹比对 + 置信度闸门接手，认不准就转人工。
- **修复不偷偷生效。** 自愈成功只生成提案，人工 `python -m browser.healing approve <id>` 之后，
  下一次才会把新选择器通过 `selector` 参数交给 RPA。
