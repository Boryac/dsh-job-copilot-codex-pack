"""额度记账（05 第 3、4 节）：每次调用都要留下可核对的明细。

规则：
- `quota_consumed` 缺失 = 契约失败，所以任何输出都必须带它。
- 用户取消 deep = 零调用，`tianyancha_calls` 与 `search_calls` 必须都是 0。
- 单价一律标注 mock / 待官方复核，不硬编码对外承诺的价格。
- **费用上限**：`TIANYANCHA_COST_CAP_YUAN`（默认 5 元）是硬闸门，超过就抛
  `CostCapExceeded`，调用方必须停手，不许"先烧后报"。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from ..schemas import QuotaConsumed, QuotaDetail

CST = timezone(timedelta(hours=8))
CAP_ENV = "TIANYANCHA_COST_CAP_YUAN"
UNIT_COST_ENV = "TIANYANCHA_UNIT_COST_YUAN"
DEFAULT_CAP_YUAN = 5.0


class CostCapExceeded(Exception):
    """调用费用将超过上限。抛这个错就是"立刻停止付费调用"的信号。"""


def unit_cost_yuan() -> float:
    """单次调用单价（元）。单价必须由使用者按合同/官网填，代码里不臆造价格。"""
    raw = (os.environ.get(UNIT_COST_ENV) or "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value >= 0 else 0.0


def default_cap_yuan() -> float:
    raw = (os.environ.get(CAP_ENV) or "").strip()
    if not raw:
        return DEFAULT_CAP_YUAN
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CAP_YUAN
    return value if value >= 0 else DEFAULT_CAP_YUAN


def now_iso() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


@dataclass
class QuotaLedger:
    detail: list[dict] = field(default_factory=list)
    search_calls: int = 0
    cap_yuan: float = field(default_factory=default_cap_yuan)

    def ensure_budget(self, cost: float) -> None:
        """调用前先问一次：这笔钱花了会不会超上限。超了就抛，别等花完再说。"""
        if self.cap_yuan <= 0:
            return
        if self.total_cost + cost > self.cap_yuan + 1e-9:
            raise CostCapExceeded(
                f"天眼查费用将超过上限 {self.cap_yuan} 元（已用 {self.total_cost} 元，本次 {cost} 元），已停止调用"
            )

    def charge_tianyancha(self, api: str, calls: int = 1, cost: float = 0.0, mock: bool = True) -> None:
        if calls <= 0:
            return
        self.ensure_budget(cost)
        self.detail.append({"api": api, "calls": calls, "cost": cost, "at": now_iso(), "mock": mock})

    def charge_search(self, calls: int = 1) -> None:
        if calls > 0:
            self.search_calls += calls

    @property
    def tianyancha_calls(self) -> int:
        return sum(item["calls"] for item in self.detail)

    @property
    def total_cost(self) -> float:
        return round(sum(item["cost"] for item in self.detail), 4)

    def to_model(self) -> QuotaConsumed:
        return QuotaConsumed(
            tianyancha_calls=self.tianyancha_calls,
            tianyancha_detail=[QuotaDetail(**item) for item in self.detail],
            search_calls=self.search_calls,
        )

    def as_dict(self) -> dict:
        return self.to_model().model_dump()
