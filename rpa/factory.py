"""挑选 RPA 执行后端。

`RPAAdapter` 一直是「换 RPA 产品不用动 Agent」的接缝，但在此之前只有一个实现，
接缝没被用过。这个工厂就是那一下：`RPA_PROVIDER` 一个环境变量决定编排层背后跑的
是本地模拟页面还是影刀，Agent 循环、工具目录、护栏一行都不改。

默认永远是 ``mock``——这个仓库要能在任何一台机器上零配置跑起来，装了影刀客户端
才是特例。
"""

from __future__ import annotations

from typing import Dict

from config import settings
from rpa.interface import RPAAdapter
from rpa.mock_rpa import MockRPAAdapter

# 别名：中文名和产品英文名指向同一个后端，省得为了拼写去查文档。
_ALIASES: Dict[str, str] = {
    "mock": "mock",
    "": "mock",
    "shadowbot": "shadowbot",
    "yingdao": "shadowbot",
    "影刀": "shadowbot",
}


def build_adapter(provider: str | None = None) -> RPAAdapter:
    """按名字构造适配器。名字不认识就报错——绝不静默退回 mock。

    静默退回是这里最坏的行为：运维以为流程跑在影刀上，实际跑的是本地模拟页面，
    而且一切「正常」。宁可起不来。
    """
    raw = (settings.rpa_provider if provider is None else provider).strip().lower()
    resolved = _ALIASES.get(raw)
    if resolved is None:
        raise ValueError(
            f"未知的 RPA_PROVIDER：{raw!r}。可选：{', '.join(sorted(set(_ALIASES.values())))}"
        )
    if resolved == "shadowbot":
        # 延迟导入：没配影刀的机器不该为了 import 一个用不上的模块付出代价。
        from rpa.shadowbot import ShadowBotAdapter

        return ShadowBotAdapter()
    return MockRPAAdapter()
