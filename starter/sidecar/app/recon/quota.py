"""额度记账（05 第 3、4 节）：每次调用都要留下可核对的明细。

规则：
- `quota_consumed` 缺失 = 契约失败，所以任何输出都必须带它。
- 用户取消 deep = 零调用，`tianyancha_calls` 与 `search_calls` 必须都是 0。
- 单价一律标注 mock / 待官方复核，不硬编码对外承诺的价格。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from ..schemas import QuotaConsumed, QuotaDetail

CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


@dataclass
class QuotaLedger:
    detail: list[dict] = field(default_factory=list)
    search_calls: int = 0

    def charge_tianyancha(self, api: str, calls: int = 1, cost: float = 0.0, mock: bool = True) -> None:
        if calls <= 0:
            return
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
