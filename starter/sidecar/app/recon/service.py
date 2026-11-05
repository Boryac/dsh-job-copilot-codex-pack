"""company-recon 服务层：消歧 -> basic/deep -> 缓存 -> 额度记账（05 全节）。

对外只暴露两个函数：
- `estimate_deep(...)`：只算预估，零外部调用（保证"取消 = 零付费"）。
- `company_recon(...)`：depth=basic 直接返回结果；depth=deep 且未确认时返回预估卡片。
"""
from __future__ import annotations

from ..config import Settings
from ..errors import INVALID_INPUT, QUOTA_EXHAUSTED, UPSTREAM_ERROR, ToolError
from ..logging_utils import text_hash
from ..mockdata import DEEP_FIELD_PLAN
from ..schemas import CacheMeta, CompanyRecon, DeepEstimate, SoftProfile
from ..version import COMPANY_CACHE_VERSION
from .cache import CompanyCache
from .disambiguation import disambiguate
from .providers import SearchProvider, TianyanchaProvider
from .quota import QuotaLedger, now_iso

HARD_FIELD_KEYS = (
    "founded_at",
    "registered_capital",
    "legal_representative",
    "business_scope",
    "registered_address",
    "status",
)


def _empty_hard_data(source: str = "not_fetched") -> dict:
    return {key: {"value": None, "verified": False, "source": source} for key in HARD_FIELD_KEYS}


def _hard_data_from(raw: dict, data_mode: str = "live") -> dict:
    """把天眼查原始字段转成 HardField。

    Mock 模式下 source 必须带 `mock://` scheme：否则报告里的"来源：tianyancha_mcp"
    会让虚构样本看起来像真实核验过的工商数据，这是 06 证据质量明确禁止的混淆。
    """
    source = "mock://tianyancha/basic" if data_mode == "mock" else "tianyancha_mcp"
    out = {}
    for key in HARD_FIELD_KEYS:
        if key in raw:
            out[key] = {"value": raw[key], "verified": True, "source": source}
    for key in HARD_FIELD_KEYS:
        out.setdefault(key, {"value": None, "verified": False, "source": "not_fetched"})
    return out


def _empty_soft() -> dict:
    return {"products": [], "news": [], "financing": [], "hiring_signals": []}


def _aggregate_sources(soft: dict) -> list[str]:
    urls: list[str] = []
    for product in soft.get("products", []):
        urls.extend(product.get("source_urls") or [])
    for item in soft.get("news", []):
        if item.get("url"):
            urls.append(item["url"])
    for item in soft.get("financing", []):
        urls.extend(item.get("source_urls") or [])
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen


def estimate_deep(
    company_input: str,
    settings: Settings,
    resolved_name: str | None = None,
    idempotency_key: str = "",
    blocked_reason: str = "",
) -> DeepEstimate:
    """预估卡片：只读配置 + 静态字段清单，不产生任何外部调用。"""
    fields = [item["field"] for item in DEEP_FIELD_PLAN]
    calls = sum(item["calls"] for item in DEEP_FIELD_PLAN)
    cost = round(sum(item["calls"] * item["unit_cost"] for item in DEEP_FIELD_PLAN), 4)
    note = "Mock 预估：不产生真实调用，费用为 0；真实单价以天眼查 MCP 官方口径复核为准（本包不硬编码承诺价格）。"
    if blocked_reason:
        note = blocked_reason
        fields = []
        calls = 0
        cost = 0.0
    return DeepEstimate(
        company_input=company_input,
        fields=fields,
        estimate={
            "calls": calls,
            "cost_yuan": cost,
            "currency": "CNY",
            "mock": settings.is_mock,
            "price_note": "单价待官方复核",
            "detail": [
                {"field": i["field"], "api": i["api"], "calls": i["calls"], "cost": 0.0}
                for i in DEEP_FIELD_PLAN
            ]
            if not blocked_reason
            else [],
        },
        quota_consumed=QuotaLedger().to_model(),
        idempotency_key=idempotency_key
        or text_hash(f"{resolved_name or company_input}::deep"),
        note=note,
    )


def _cache_key(resolved_name: str, depth: str, data_mode: str, idempotency_key: str = "") -> str:
    """缓存业务 key：同一主体 + 同一数据模式 + 同一深度才算同一条。

    把 `data_mode` 也放进来，是为了不让 live 命中 mock 期间写下的结果
    （否则报告会带着 `mock://` 来源出现在真实配置里，反之亦然）。版本号由
    `CompanyCache` 统一拼在 key 前面，见 `app/version.py`。
    """
    if depth == "deep":
        return idempotency_key or text_hash(f"{resolved_name}::deep")
    return text_hash(f"{data_mode}|{resolved_name}::basic")


def company_recon(
    company_input: str,
    settings: Settings,
    depth: str = "basic",
    confirmed_deep: bool = False,
    role_keywords: list[str] | None = None,
    idempotency_key: str = "",
) -> CompanyRecon | DeepEstimate:
    name = (company_input or "").strip()
    if not name:
        raise ToolError(code=INVALID_INPUT, message="公司名称不能为空。", retryable=False)
    if depth not in ("basic", "deep"):
        raise ToolError(code=INVALID_INPUT, message="depth 只能是 basic 或 deep。", retryable=False)

    provider = TianyanchaProvider(settings)
    search = SearchProvider(settings)
    ledger = QuotaLedger()
    degradations: list[str] = []
    data_mode = "mock" if settings.is_mock else "live"
    if settings.degraded_modules():
        degradations.append("live 模式缺 key，已降级为 Mock：" + "、".join(settings.degraded_modules()))

    candidates = provider.candidates(name)
    chosen, disambiguation = disambiguate(name, candidates, role_keywords or [])

    # 定不到唯一主体：不许随机挑一个写成事实
    if chosen is None:
        if depth == "deep":
            return estimate_deep(
                name, settings, None, idempotency_key,
                blocked_reason="公司主体未唯一确定，无法发起 deep 查询；请先确认工商主体。",
            )
        degradations.append("公司未能唯一确定，硬数据留空，等待用户确认工商主体")
        return CompanyRecon(
            company_input=name,
            company_resolved={"name": None, "unified_credit_code": None,
                              "disambiguation": disambiguation.model_dump()},
            hard_data=_empty_hard_data(),
            soft_profile=SoftProfile(**_empty_soft()),
            deep_data=None,
            depth_used="basic",
            quota_consumed=ledger.to_model(),
            fetched_at=now_iso(),
            data_mode=data_mode,
            cache=CacheMeta(hit=False, version=COMPANY_CACHE_VERSION),
            degradations=degradations,
        )

    resolved_name = chosen.name
    resolved = {
        "name": resolved_name,
        "unified_credit_code": chosen.unified_credit_code,
        "disambiguation": disambiguation.model_dump(),
    }

    # deep 未确认 = 只出预估卡片，零调用（05 第 3 节第 1、2 步）
    if depth == "deep" and not confirmed_deep:
        return estimate_deep(
            name, settings, resolved_name,
            idempotency_key or text_hash(f"{resolved_name}::deep"),
        )

    cache = CompanyCache(settings.cache_dir, settings.company_cache_days)
    cache_key = _cache_key(resolved_name, depth, data_mode, idempotency_key)
    cached = cache.get(cache_key)
    if cached:
        payload = cached.get("payload")
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["cache"] = {
                "hit": True,
                "fetched_at": cached.get("fetched_at"),
                "version": cache.version,
            }
            payload["quota_consumed"] = QuotaLedger().to_model().model_dump()  # 命中缓存 = 本次零调用
            return CompanyRecon.model_validate(payload)

    # 硬数据
    hard_raw: dict = {}
    try:
        hard_raw = provider.basic(resolved_name, ledger)
    except ToolError as exc:
        if exc.code == QUOTA_EXHAUSTED:
            degradations.append("工商硬数据未获取（额度耗尽），已降级为纯搜索模式")
            hard_raw = {}
        elif exc.code == UPSTREAM_ERROR:
            degradations.append(f"工商硬数据未获取（{exc.code}），硬数据字段留空")
            hard_raw = {}
        else:
            raise

    # 软信息
    try:
        soft_raw = search.soft_profile(resolved_name, ledger)
    except ToolError as exc:
        degradations.append(f"软信息未获取（{exc.code}）：{exc.message}")
        soft_raw = _empty_soft()
    except Exception:  # 搜索异常不许阻塞报告
        degradations.append("软信息未获取（搜索异常）")
        soft_raw = _empty_soft()

    if soft_raw and not soft_raw.get("news") and not soft_raw.get("products"):
        degradations.append("公开渠道未检索到软信息（不等于不存在，报告里写'未检索到'）")

    deep_data = None
    if depth == "deep":
        try:
            deep_data = provider.deep(resolved_name, ledger)
        except ToolError as exc:
            degradations.append(f"deep 数据获取失败（{exc.code}），已降级为 basic 结果")
            depth = "basic"

    model = CompanyRecon(
        company_input=name,
        company_resolved=resolved,
        hard_data=_hard_data_from(hard_raw, data_mode),
        soft_profile=SoftProfile(
            products=soft_raw.get("products", []),
            news=soft_raw.get("news", []),
            financing=soft_raw.get("financing", []),
            hiring_signals=soft_raw.get("hiring_signals", []),
            inferred=True,
            source_urls=_aggregate_sources(soft_raw),
        ),
        deep_data=deep_data,
        depth_used="deep" if depth == "deep" and deep_data is not None else "basic",
        quota_consumed=ledger.to_model(),
        fetched_at=now_iso(),
        data_mode=data_mode,
        cache=CacheMeta(hit=False, version=cache.version),
        degradations=degradations,
    )

    cache.put(cache_key, {"payload": model.model_dump()})
    return model
