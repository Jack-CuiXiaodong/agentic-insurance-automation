"""影刀（ShadowBot）RPA 后端：后端选择 + CLI 协议层。

这里不需要装影刀客户端：CLI 调用被一个脚本化的假 runner 顶掉，测的是本仓库自己
写的那部分——后端怎么选、命令怎么拼、JSON 怎么取、失败和超时怎么变成
RPAExecutionError。真机联调是另一回事，测试不假装替代它。
"""

import json

import pytest

from rpa.factory import build_adapter
from rpa.interface import RPAExecutionError
from rpa.mock_rpa import MockRPAAdapter
from rpa.shadowbot import ShadowBotAdapter, _dig

CLAIM_PARAMS = {
    "claim_id": "BX-2024-0001",
    "invoice_code": "3300000000",
    "invoice_no": "12345678",
    "amount": 4800,
    # 只属于本地模拟适配器的三个参数，不该被送进影刀应用。
    "ui_variant": "v1",
    "headless": True,
    "pace": 0.0,
}


class _FakeCLI:
    """脚本化的假影刀 CLI：按子命令关键字回话，并记下每一条真实执行的命令行。"""

    def __init__(self, *, current=None, run=None, status=None, logs=None):
        self.current = current if current is not None else (0, {"username": "demo"})
        self.run = run if run is not None else (0, {"task_id": "T-1"})
        self.status = status if status is not None else [(0, {"status": "success"})]
        self.logs = logs if logs is not None else (0, {"lines": []})
        self.calls = []

    def __call__(self, argv, timeout):
        line = " ".join(argv)
        self.calls.append(line)
        if "auth current" in line:
            code, payload = self.current
        elif "task run" in line:
            code, payload = self.run
        elif "task status" in line:
            code, payload = self.status[0] if len(self.status) == 1 else self.status.pop(0)
        elif "task logs" in line:
            code, payload = self.logs
        else:  # pragma: no cover - a command the adapter should never issue
            raise AssertionError(f"unexpected ShadowBot command: {line}")
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return code, body, ""


def _adapter(cli, **kwargs):
    kwargs.setdefault("app_id", "APP-1")
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("poll_interval", 0.0)
    kwargs.setdefault("input_flag", "")
    kwargs.setdefault("executable", "shadowbot-cli")
    return ShadowBotAdapter(runner=cli, **kwargs)


# -- 后端选择 --------------------------------------------------------------

def test_default_backend_is_still_the_mock():
    """零配置的机器必须照旧跑得起来——影刀是可选项，不是新的前置依赖。"""
    assert isinstance(build_adapter("mock"), MockRPAAdapter)
    assert isinstance(build_adapter(""), MockRPAAdapter)


@pytest.mark.parametrize("name", ["shadowbot", "yingdao", "影刀", "ShadowBot"])
def test_shadowbot_backend_selectable_by_any_of_its_names(name):
    assert isinstance(build_adapter(name), ShadowBotAdapter)


def test_unknown_provider_fails_loudly_instead_of_falling_back():
    """静默退回 mock 是最坏的失败方式：运维以为在跑影刀，其实在跑模拟页面。"""
    with pytest.raises(ValueError, match="RPA_PROVIDER"):
        build_adapter("uipath")


# -- CLI 协议层 ------------------------------------------------------------

def test_happy_path_preflights_runs_and_polls_to_success():
    cli = _FakeCLI(status=[(0, {"status": "running"}), (0, {"status": "success"})])
    result = _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))

    assert result.success is True
    assert result.details["task_id"] == "T-1"
    assert result.details["app_id"] == "APP-1"
    assert result.details["adapter"] == "shadowbot"
    # 顺序即契约：先验会话，再触发，然后轮询到终态。
    assert "auth current" in cli.calls[0]
    assert "console task run --app-id APP-1" in cli.calls[1]
    assert sum("task status" in c for c in cli.calls) == 2


def test_no_session_stops_instead_of_logging_itself_in():
    """适配器不持有凭据，也不代为登录——无人值守的执行器不该拿着账号密码。"""
    cli = _FakeCLI(current=(1, {"message": "not logged in"}))
    with pytest.raises(RPAExecutionError, match="影刀会话不可用"):
        _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))
    assert not any("auth login" in c for c in cli.calls)


def test_missing_app_id_fails_before_touching_the_cli():
    cli = _FakeCLI()
    with pytest.raises(RPAExecutionError, match="未配置影刀应用 ID"):
        _adapter(cli, app_id="").execute_workflow("verify_invoice", dict(CLAIM_PARAMS))
    assert cli.calls == []


def test_failed_task_raises_with_the_reason_from_the_status_payload():
    cli = _FakeCLI(status=[(0, {"status": "failed", "message": "元素未找到"})])
    with pytest.raises(RPAExecutionError, match="元素未找到"):
        _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))


def test_failed_task_falls_back_to_task_logs_for_the_reason():
    cli = _FakeCLI(
        status=[(0, {"status": "error"})],
        logs=(0, {"lines": ["查验平台超时"]}),
    )
    with pytest.raises(RPAExecutionError, match="查验平台超时"):
        _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))
    assert any("task logs" in c for c in cli.calls)


def test_unknown_status_keeps_polling_and_times_out_rather_than_claiming_success():
    """状态字面量没有公开约定，认不出的状态按「还在跑」处理，绝不当成成功。"""
    cli = _FakeCLI(status=[(0, {"status": "某个没见过的状态"})])
    with pytest.raises(RPAExecutionError, match="仍未结束"):
        _adapter(cli, timeout=0.0).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))


def test_missing_task_id_is_an_error_not_a_silent_success():
    cli = _FakeCLI(run=(0, {"message": "ok"}))
    with pytest.raises(RPAExecutionError, match="task_id"):
        _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))


def test_cli_error_exit_surfaces_the_cli_message():
    cli = _FakeCLI(run=(1, {"message": "app not found"}))
    with pytest.raises(RPAExecutionError, match="app not found"):
        _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))


def test_missing_executable_reports_the_path_instead_of_guessing_one():
    def _missing(argv, timeout):
        raise FileNotFoundError(argv[0])

    with pytest.raises(RPAExecutionError, match="未找到影刀命令行"):
        _adapter(_missing).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))


# -- 入参：宁可少传，不可乱猜 ----------------------------------------------

def test_inputs_are_not_passed_until_the_flag_is_configured():
    """官方文档要求现场 `console task run --help` 确认入参写法，所以默认不传。"""
    cli = _FakeCLI()
    _adapter(cli).execute_workflow("verify_invoice", dict(CLAIM_PARAMS))
    run_call = next(c for c in cli.calls if "task run" in c)
    assert run_call.endswith("console task run --app-id APP-1")


def test_configured_input_flag_passes_business_fields_only():
    cli = _FakeCLI()
    _adapter(cli, input_flag="--params").execute_workflow("verify_invoice", dict(CLAIM_PARAMS))
    run_call = next(c for c in cli.calls if "task run" in c)
    payload = json.loads(run_call.split("--params ", 1)[1])
    assert payload["claim_id"] == "BX-2024-0001"
    # 模拟适配器专有的参数不该泄漏进影刀应用的入参。
    assert not {"ui_variant", "headless", "pace"} & set(payload)


# -- JSON 信封形状不确定，按键名找 ------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {"task_id": "T-9"},
        {"taskId": "T-9"},
        {"data": {"taskId": "T-9"}},
        {"code": 0, "data": {"task": {"task_id": "T-9"}}},
    ],
)
def test_task_id_is_found_whatever_the_envelope_looks_like(payload):
    assert str(_dig(payload, "task_id", "taskId", "taskID", "id")) == "T-9"


def test_dig_skips_empty_values_instead_of_returning_them():
    assert _dig({"status": "", "data": {"status": "success"}}, "status") == "success"


def test_argv_puts_the_subcommand_after_the_executable():
    argv = _adapter(_FakeCLI()).argv(["auth", "current"])
    assert " ".join(argv).endswith("auth current")
    assert any("shadowbot-cli" in part for part in argv)
