"""外部数据提供者：天眼查（工商硬数据）+ 搜索（软信息）。

- Mock 是默认模式：数据来自 mockdata.py 的虚构公司，链接用 `mock://` scheme，
  结构上不可能被误当成真实链接。
- live 模式才真的发 HTTP 请求，且 key 只从环境变量读。上游接口契约**未核验**，
  所以 live 失败时一律抛 ToolError，由 service 层降级并在输出里明示，不静默编数据。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from ..config import Settings
from ..errors import QUOTA_EXHAUSTED, UPSTREAM_ERROR, ToolError
from ..mockdata import lookup_company, search_soft_profile
from .quota import QuotaLedger

TIANYANCHA_BASIC_APIS = [
    "tianyancha.company_base",
    "tianyancha.registration_info",
]


def _mock_quota_exhausted() -> bool:
    return os.environ.get("MOCK_QUOTA_EXHAUSTED", "").strip().lower() in {"1", "true", "yes"}


def _maybe_delay(settings: Settings) -> None:
    """测试/实测用：给 Mock 注入人为延迟，用来验证超时降级真的会触发。"""
    if settings.mock_delay_ms > 0:
        time.sleep(settings.mock_delay_ms / 1000)


class TianyanchaProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def candidates(self, company_input: str) -> list[dict]:
        if self.settings.tianyancha_live:
            return self._live_candidates(company_input)
        item = lookup_company(company_input)
        return list(item["candidates"]) if item else []

    def basic(self, resolved_name: str, ledger: QuotaLedger) -> dict:
        if _mock_quota_exhausted():
            raise ToolError(
                code=QUOTA_EXHAUSTED,
                message="天眼查基础字段额度已耗尽，已降级为纯搜索模式。",
                retryable=False,
                fallback="search_only",
            )
        if self.settings.tianyancha_live:
            data = self._live_call("/company/basic", {"name": resolved_name})
            for api in TIANYANCHA_BASIC_APIS:
                ledger.charge_tianyancha(api, calls=1, cost=0.0, mock=False)
            return data
        _maybe_delay(self.settings)
        item = lookup_company(resolved_name)
        if not item or not item.get("hard_data"):
            raise ToolError(
                code=UPSTREAM_ERROR,
                message="Mock 数据源里没有该主体的工商字段。",
                retryable=False,
                fallback="search_only",
            )
        for api in TIANYANCHA_BASIC_APIS:
            ledger.charge_tianyancha(api, calls=1, cost=0.0, mock=True)
        return dict(item["hard_data"])

    def deep(self, resolved_name: str, ledger: QuotaLedger) -> dict:
        if self.settings.tianyancha_live:
            data = self._live_call("/company/deep", {"name": resolved_name})
            ledger.charge_tianyancha("tianyancha.shareholder_penetration", calls=3, cost=0.0, mock=False)
            ledger.charge_tianyancha("tianyancha.judicial_risk", calls=2, cost=0.0, mock=False)
            return data
        item = lookup_company(resolved_name)
        if not item or not item.get("deep_data"):
            raise ToolError(
                code=UPSTREAM_ERROR,
                message="Mock 数据源里没有该主体的深调字段。",
                retryable=False,
                fallback="basic_only",
            )
        ledger.charge_tianyancha("tianyancha.shareholder_penetration", calls=3, cost=0.0, mock=True)
        ledger.charge_tianyancha("tianyancha.actual_controller", calls=1, cost=0.0, mock=True)
        ledger.charge_tianyancha("tianyancha.judicial_risk", calls=2, cost=0.0, mock=True)
        return dict(item["deep_data"])

    # ---------------------------------------------------------------- live 路径（未核验）
    def _live_call(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.settings.tianyancha_mcp_url.rstrip('/')}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.tianyancha_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ToolError(
                code=UPSTREAM_ERROR,
                message=f"天眼查接口调用失败（{type(exc).__name__}），已降级。",
                retryable=True,
                fallback="search_only",
            ) from exc
        if not isinstance(body, dict):
            raise ToolError(code=UPSTREAM_ERROR, message="天眼查返回结构异常，已降级。", retryable=True,
                            fallback="search_only")
        return body

    def _live_candidates(self, company_input: str) -> list[dict]:
        body = self._live_call("/company/search", {"keyword": company_input})
        items = body.get("items") or body.get("data") or []
        return [
            {
                "name": it.get("name", ""),
                "unified_credit_code": it.get("creditCode") or it.get("unified_credit_code"),
                "region": it.get("base") or it.get("region"),
                "legal_representative": it.get("legalPersonName") or it.get("legal_representative"),
                "business_scope": it.get("businessScope") or it.get("business_scope", ""),
            }
            for it in items
            if isinstance(it, dict)
        ]


class SearchProvider:
    """只发公司名与公开关键词，绝不发送简历内容（11 第 2 节）。"""

    QUERIES = ("产品", "融资", "新闻", "招聘")

    def __init__(self, settings: Settings):
        self.settings = settings

    def soft_profile(self, company_name: str, ledger: QuotaLedger) -> dict:
        if self.settings.search_live:
            results = {}
            for q in self.QUERIES:
                results[q] = self._live_search(f"{company_name} {q}")
                ledger.charge_search(1)
            return self._normalize_live(company_name, results)
        _maybe_delay(self.settings)
        data = search_soft_profile(company_name)
        ledger.charge_search(len(self.QUERIES))
        return data

    def _live_search(self, query: str) -> list[dict]:
        # 搜索 API 的请求/响应契约未核验（T1.1 只锁定了仓库，不含搜索服务）。
        # 按 00 的原则选更保守的做法：显式失败并降级，而不是拼一个猜的接口假装成功。
        raise ToolError(
            code=UPSTREAM_ERROR,
            message="搜索 API 契约未核验（见 docs/FORK_LOCK.md），live 搜索路径未启用，已降级为'软信息未获取'。",
            retryable=False,
            fallback="soft_profile_unavailable",
        )

    def _normalize_live(self, company_name: str, results: dict) -> dict:
        """live 搜索启用后在此处把搜索结果映射成 soft_profile；当前返回空结构。"""
        return {"products": [], "news": [], "financing": [], "hiring_signals": []}
