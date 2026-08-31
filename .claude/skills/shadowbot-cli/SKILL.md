---
name: shadowbot-cli
description: 操作本机影刀 RPA（ShadowBot）客户端的命令行接口。当用户要求登录影刀、查看/运行/停止影刀应用、查询任务状态与日志、管理触发器、消息中心、扩展安装，或打开影刀 Studio 工程时使用。只执行已安装 CLI 真实存在的命令，绝不臆造命令、参数或 ID。
---

# 影刀 ShadowBot CLI

影刀客户端自带一个命令行接口，输出结构化 JSON。它是本仓库把编排层接到**真实**
RPA 执行器的通道（`rpa/shadowbot.py` 走的就是这条路）。

上游来源见 `references/UPSTREAM.md`——本目录下的三份参考文件是 ying-dao/skills
的**逐字副本**，不要手工改，要更新就重新同步。

## 先分平台，再看对应的那一份

CLI 的可执行文件名和调用方式按平台不同，**两套互不通用**：

| 平台 | 可执行文件 | 调用方式 | 照着这份做 |
|---|---|---|---|
| Windows | `shadowbot.shell-cli.exe` | `powershell -NoProfile -ExecutionPolicy Bypass -Command "..."` | `references/windows.md` |
| macOS / 信创（麒麟、统信等 Linux） | `shadowbot-cli` | 直接在 shell 里调用 | `references/posix.md` |

判断平台后**完整读一遍对应的那份参考文件再动手**，它才是权威：登录恢复流程、
Fast Path、失败处理都在里面。两份文件的命令不要交叉借用。

`references/cli-overview.zh-CN.md` 是 CLI 的功能概览，需要跟用户解释「影刀 CLI
能做什么」时读它。

## 三条不能破的底线

1. **只执行真实存在的命令。** 命令、子命令、参数名、ID、凭据一律不臆造。不确定
   就先 `--help` / `-h` 逐级发现，再执行。
2. **可执行文件不在 PATH 上就停。** 报告「未找到 shadowbot CLI」，不要猜安装路径，
   更不要绕过 CLI 去直接调本地 REST API 或翻客户端文件/数据库。
3. **不打印、不落盘、不复述密码与令牌。** 报告里的命令要把密钥位置抹掉。

## 在本仓库里的用法

本项目默认跑 `MockRPAAdapter`（本地模拟查验平台，不需要影刀）。要让编排层真的
去调影刀，设 `RPA_PROVIDER=shadowbot` 并配好 `SHADOWBOT_APP_ID`，见
`rpa/shadowbot.py` 顶部的说明和 `.env.example`。

排查「Agent 调不通影刀」时的顺序：先用本技能手工跑通
`auth current` → `console app` → `console task run --app-id <id>`，
确认 CLI 这一侧是好的，再回头看适配器。
