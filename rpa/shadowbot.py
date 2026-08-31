"""影刀（ShadowBot）RPA 适配器 —— 编排层接真实 RPA 执行器的那条通道。

`rpa/interface.py` 一直把「换成企业 RPA」当作预留的接缝，这里是第一个真的接上去
的实现：不改 Agent、不改工具目录、不改护栏，只把 `RPAAdapter.execute_workflow`
的另一端从本地模拟页面换成影刀客户端。

走的是影刀自带的命令行接口（Windows 上是 ``shadowbot.shell-cli.exe``，macOS 与
信创 Linux 上是 ``shadowbot-cli``），命令集和调用约定见
``.claude/skills/shadowbot-cli/``——那份技能是影刀官方文档的副本，本文件只用其中
**已经写明的**命令：

    auth current                              # 会话预检
    console task run    --app-id  <app_id>    # 触发应用
    console task status --task-id <task_id>   # 轮询
    console task logs   --task-id <task_id>   # 失败时取原因

## 三个刻意的克制

**不自动登录。** 预检发现没有会话就直接失败，并告诉运维去跑技能里的登录恢复流程。
适配器不碰账号密码——无人值守的执行器不该持有凭据，这比「跑得更顺」重要。

**不臆造入参开关。** 官方技能明确要求用 ``console task run --help`` 现场发现入参
写法，没有公开固定的 flag 名，所以这里默认**不传业务参数**，只有配了
``SHADOWBOT_INPUT_FLAG`` 才会追加 ``<flag> <json>``。宁可少传，不可乱猜。

**不假设 JSON 外壳。** CLI 输出结构化 JSON，但外层信封（是否有 ``data`` 包裹、
字段驼峰还是下划线）没有公开约定，所以 ``_dig`` 在整棵解析结果里按候选键名找，
找不到就把原始 payload 挂到 details 上，让人去看，而不是猜一个默认值。

它是不是真的跑得通，取决于本机装的那版 CLI；``tests/test_shadowbot_rpa.py`` 用注入
的假 runner 覆盖了协议层的取值、轮询、失败与超时，但**真机联调仍然要做**。
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Sequence, Tuple

from config import settings
from rpa.interface import RPAAdapter, RPAExecutionError, RPAResult

WINDOWS_EXECUTABLE = "shadowbot.shell-cli.exe"
POSIX_EXECUTABLE = "shadowbot-cli"

# 任务状态的字面量没有公开约定，这里按大小写无关的词根匹配。落不进任何一组的状态
# 视为「还在跑」，继续轮询到超时——把未知状态当成功是最坏的猜法。
SUCCESS_STATES = {"success", "succeeded", "finished", "completed", "complete", "done", "ok"}
FAILURE_STATES = {"failed", "failure", "fail", "error", "cancelled", "canceled",
                  "stopped", "aborted", "timeout", "exception"}

# 只属于本地模拟适配器的参数，不该往影刀应用里传。
_MOCK_ONLY_PARAMS = {"ui_variant", "headless", "pace"}

#: runner(argv, timeout) -> (returncode, stdout, stderr)。测试从这里注入假 CLI。
CommandRunner = Callable[[Sequence[str], float], Tuple[int, str, str]]


def default_executable() -> str:
    return WINDOWS_EXECUTABLE if os.name == "nt" else POSIX_EXECUTABLE


def _subprocess_runner(argv: Sequence[str], timeout: float) -> Tuple[int, str, str]:
    proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _dig(payload: Any, *names: str) -> Any:
    """在解析后的 JSON 里按候选键名深度优先地找第一个非空值。

    信封形状不确定（``{"task_id": ...}`` / ``{"data": {"taskId": ...}}`` / ...），
    与其赌一种，不如按名字找。
    """
    wanted = {n.lower() for n in names}
    stack: List[Any] = [payload]
    while stack:
        node = stack.pop(0)
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() in wanted and value not in (None, "", [], {}):
                    return value
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _as_json(text: str) -> Any:
    """从 CLI 输出里取出 JSON。前后混进日志行也能捞出来，捞不到返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


class ShadowBotAdapter(RPAAdapter):
    """通过影刀 CLI 触发一个已发布的影刀应用，并等它跑完。

    ``workflow_name`` 映射到 ``app_id``：默认所有流程都指向 ``SHADOWBOT_APP_ID``；
    要按流程分应用就传 ``app_ids={"verify_invoice": "..."}``。
    """

    name = "shadowbot"

    def __init__(
        self,
        app_id: str | None = None,
        *,
        app_ids: Dict[str, str] | None = None,
        executable: str | None = None,
        input_flag: str | None = None,
        timeout: float | None = None,
        poll_interval: float | None = None,
        runner: CommandRunner | None = None,
    ):
        self.app_id = settings.shadowbot_app_id if app_id is None else app_id
        self.app_ids = dict(app_ids or {})
        self.executable = executable or settings.shadowbot_cli or default_executable()
        self.input_flag = (
            settings.shadowbot_input_flag if input_flag is None else input_flag
        ).strip()
        self.timeout = settings.shadowbot_timeout if timeout is None else float(timeout)
        self.poll_interval = (
            settings.shadowbot_poll_interval if poll_interval is None else float(poll_interval)
        )
        self._runner: CommandRunner = runner or _subprocess_runner

    # -- CLI 调用 ---------------------------------------------------------

    def argv(self, args: Sequence[str]) -> List[str]:
        """按平台拼出真正要执行的命令行。

        Windows 侧影刀官方技能要求经 PowerShell 调用；POSIX 侧直接调可执行文件。
        """
        if os.name == "nt" or platform.system() == "Windows":
            inner = subprocess.list2cmdline([self.executable, *args])
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", inner]
        return [self.executable, *args]

    def _cli(self, args: Sequence[str], *, what: str, timeout: float | None = None) -> Any:
        argv = self.argv(args)
        try:
            code, out, err = self._runner(argv, timeout or self.timeout)
        except FileNotFoundError as exc:
            raise RPAExecutionError(
                f"未找到影刀命令行 {self.executable!r}（{what}）。"
                f"确认影刀客户端已安装且 CLI 在 PATH 上，或用 SHADOWBOT_CLI 指定绝对路径。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RPAExecutionError(f"影刀 CLI 超时（{what}）：{' '.join(args)}") from exc

        payload = _as_json(out)
        if code != 0:
            detail = _dig(payload, "message", "msg", "error") or (err or out).strip() or f"exit {code}"
            raise RPAExecutionError(f"影刀 CLI 执行失败（{what}）：{detail}")
        return payload

    # -- 流程 -------------------------------------------------------------

    def _resolve_app_id(self, workflow_name: str) -> str:
        app_id = self.app_ids.get(workflow_name) or self.app_id
        if not app_id:
            raise RPAExecutionError(
                f"未配置影刀应用 ID：流程「{workflow_name}」没有对应的 app_id。"
                f"设置 SHADOWBOT_APP_ID，或用 `console app` 查出应用后传 app_ids。"
            )
        return app_id

    def preflight(self) -> Any:
        """会话预检。没有会话就停——适配器不持有凭据，也不代为登录。"""
        try:
            return self._cli(["auth", "current"], what="会话预检", timeout=min(self.timeout, 60.0))
        except RPAExecutionError as exc:
            raise RPAExecutionError(
                f"影刀会话不可用：{exc}。请先在本机完成登录"
                f"（见 .claude/skills/shadowbot-cli 的 Login Recovery），再重跑本流程。"
            ) from exc

    def _run_args(self, app_id: str, parameters: Dict[str, Any]) -> List[str]:
        args = ["console", "task", "run", "--app-id", app_id]
        if self.input_flag:
            business = {k: v for k, v in parameters.items() if k not in _MOCK_ONLY_PARAMS}
            args += [*shlex.split(self.input_flag), json.dumps(business, ensure_ascii=False)]
        return args

    def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> RPAResult:
        app_id = self._resolve_app_id(workflow_name)
        self.preflight()

        started = self._cli(self._run_args(app_id, parameters), what="触发影刀应用")
        task_id = _dig(started, "task_id", "taskId", "taskID", "id")
        if not task_id:
            raise RPAExecutionError(
                f"影刀应用 {app_id} 已触发，但返回里找不到 task_id，无法跟踪执行结果。"
                f"原始返回：{json.dumps(started, ensure_ascii=False)[:400]}"
            )

        status, payload = self._await_task(str(task_id))
        details = {
            "adapter": self.name,
            "app_id": app_id,
            "task_id": str(task_id),
            "result_status": status,
        }
        if str(status).lower() in FAILURE_STATES:
            raise RPAExecutionError(
                f"影刀任务 {task_id} 以 {status} 结束：{self._failure_reason(str(task_id), payload)}"
            )
        return RPAResult(
            success=True,
            workflow=workflow_name,
            message=f"影刀应用 {app_id} 执行完成（任务 {task_id}）。",
            details=details,
        )

    def _await_task(self, task_id: str) -> Tuple[str, Any]:
        """轮询到终态。未知状态一律按「还在跑」处理，超时即失败。"""
        deadline = time.monotonic() + self.timeout
        last_status = ""
        payload: Any = None
        while True:
            payload = self._cli(
                ["console", "task", "status", "--task-id", task_id],
                what="查询任务状态",
                timeout=min(self.timeout, 60.0),
            )
            last_status = str(_dig(payload, "status", "state", "task_status", "taskStatus") or "")
            normalized = last_status.lower()
            if normalized in SUCCESS_STATES or normalized in FAILURE_STATES:
                return last_status, payload
            if time.monotonic() >= deadline:
                raise RPAExecutionError(
                    f"影刀任务 {task_id} 超过 {self.timeout:.0f} 秒仍未结束"
                    f"（最后状态：{last_status or '未知'}）。任务可能仍在运行，未自动停止。"
                )
            time.sleep(self.poll_interval)

    def _failure_reason(self, task_id: str, status_payload: Any) -> str:
        """失败原因优先取状态里的 message，取不到再去拉日志。日志拉不到不算失败。"""
        reason = _dig(status_payload, "message", "msg", "error", "error_message", "errorMessage")
        if reason:
            return str(reason)[:500]
        try:
            logs = self._cli(
                ["console", "task", "logs", "--task-id", task_id],
                what="查询任务日志",
                timeout=min(self.timeout, 60.0),
            )
        except RPAExecutionError:
            return "未取到失败原因（任务日志不可读）"
        return (json.dumps(logs, ensure_ascii=False)[:500] if logs else "未取到失败原因")


def cli_available(executable: str | None = None) -> bool:
    """CLI 是否在 PATH 上。只用于启动期给出人话提示，不参与执行路径。"""
    return shutil.which(executable or settings.shadowbot_cli or default_executable()) is not None
