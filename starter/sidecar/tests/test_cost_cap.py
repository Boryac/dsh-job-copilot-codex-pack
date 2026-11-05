"""费用上限闸门测试：超上限必须停手，而不是"先烧完再报账"。

这条约束不是形式检查——live 调用是真花钱的，账本里没有任何闸门时，
一次 deep 就能把预算打穿而输出里只写着 cost=0.0。
"""
from __future__ import annotations

import pytest

from app.recon.quota import (
    CAP_ENV,
    DEFAULT_CAP_YUAN,
    UNIT_COST_ENV,
    CostCapExceeded,
    QuotaLedger,
    default_cap_yuan,
    unit_cost_yuan,
)


def test_cap_blocks_before_overrun(monkeypatch):
    monkeypatch.setenv(UNIT_COST_ENV, "0.01")
    ledger = QuotaLedger(cap_yuan=0.02)
    ledger.charge_tianyancha("tianyancha.company_base", calls=1, cost=0.01, mock=False)
    ledger.charge_tianyancha("tianyancha.registration_info", calls=1, cost=0.01, mock=False)
    assert ledger.total_cost == pytest.approx(0.02)
    # 第三笔会超上限：必须在记账前抛出，且账本里不留这笔
    with pytest.raises(CostCapExceeded):
        ledger.charge_tianyancha("tianyancha.judicial_risk", calls=1, cost=0.01, mock=False)
    assert ledger.tianyancha_calls == 2


def test_ensure_budget_allows_exact_boundary():
    ledger = QuotaLedger(cap_yuan=1.0)
    ledger.charge_tianyancha("a", calls=1, cost=0.6, mock=False)
    ledger.ensure_budget(0.4)  # 正好等于上限，允许
    with pytest.raises(CostCapExceeded):
        ledger.ensure_budget(0.41)


def test_cap_zero_disables_guard():
    ledger = QuotaLedger(cap_yuan=0.0)
    ledger.charge_tianyancha("a", calls=1, cost=100.0, mock=False)
    assert ledger.total_cost == 100.0


def test_cap_and_unit_cost_come_from_env(monkeypatch):
    monkeypatch.setenv(CAP_ENV, "0.5")
    monkeypatch.setenv(UNIT_COST_ENV, "0.25")
    assert default_cap_yuan() == 0.5
    assert unit_cost_yuan() == 0.25
    ledger = QuotaLedger()
    assert ledger.cap_yuan == 0.5


def test_bad_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv(CAP_ENV, "不是数字")
    monkeypatch.setenv(UNIT_COST_ENV, "-3")
    assert default_cap_yuan() == DEFAULT_CAP_YUAN
    assert unit_cost_yuan() == 0.0
