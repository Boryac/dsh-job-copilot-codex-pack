"""Mock 数据源：全部为虚构公司与虚构指标，不含任何真实企业、真实个人或真实价格。

规则（03 / 05 / 11）：
- Mock 的软信息来源一律用 `mock://` scheme，结构上不可能被误当成真实链接；
  live 模式才会出现 http(s) 链接，校验器按 data_mode 分别断言（见 validator 规则 6）。
- 额度与单价一律标注"待官方复核"，不硬编码任何对外承诺的数字。
"""
from __future__ import annotations

MOCK_SCHEME = "mock://"

# 深调字段清单与预估（05 第 3 节）。成本数字是占位假设，标注 mock + 待复核。
DEEP_FIELD_PLAN = [
    {"field": "股东穿透", "api": "tianyancha.shareholder_penetration", "calls": 3, "unit_cost": 0.0},
    {"field": "实际控制人", "api": "tianyancha.actual_controller", "calls": 1, "unit_cost": 0.0},
    {"field": "司法风险", "api": "tianyancha.judicial_risk", "calls": 2, "unit_cost": 0.0},
    {"field": "经营异常", "api": "tianyancha.abnormal_operation", "calls": 1, "unit_cost": 0.0},
]

MOCK_COMPANIES: list[dict] = [
    {
        "aliases": ["云栖生活", "云栖生活科技", "云栖"],
        "resolved": {
            "name": "云栖生活科技（福州）有限公司",
            "unified_credit_code": "91350100MA000MOCK1",
            "region": "福建福州",
        },
        "candidates": [
            {
                "name": "云栖生活科技（福州）有限公司",
                "unified_credit_code": "91350100MA000MOCK1",
                "region": "福建福州",
                "legal_representative": "陈某某",
                "business_scope": "本地生活服务平台运营；餐饮与酒旅商户数字化服务；信息技术咨询",
            }
        ],
        "hard_data": {
            "founded_at": "2019-04-11",
            "registered_capital": "1000 万元人民币",
            "legal_representative": "陈某某",
            "business_scope": "本地生活服务平台运营；餐饮与酒旅商户数字化服务；信息技术咨询",
            "registered_address": "福建省福州市鼓楼区某路 000 号（Mock）",
            "status": "存续",
        },
        "soft_profile": {
            "products": [
                {
                    "name": "云栖到店（Mock 产品）",
                    "users": "未披露",
                    "revenue_model": "商户佣金 + 年费",
                    "relation_to_role": "本岗位直接负责该产品的商户签约与上线",
                    "source_urls": [MOCK_SCHEME + "yunqi/product"],
                },
                {
                    "name": "云栖商家助手（Mock 产品）",
                    "users": "未披露",
                    "revenue_model": "SaaS 订阅",
                    "relation_to_role": "BD 签约后的商家运营工具，与岗位的运营动作落地职责相关",
                    "source_urls": [MOCK_SCHEME + "yunqi/merchant-app"],
                },
            ],
            "news": [
                {
                    "title": "云栖生活宣布进入泉州、莆田两个新城市（Mock 新闻）",
                    "date": "2026-08-20",
                    "url": MOCK_SCHEME + "yunqi/news/expansion-2026",
                    "summary": "Mock 摘要：新增两城意味着 BD 团队扩编，签约目标压力上升。",
                },
                {
                    "title": "云栖生活与本地餐饮协会达成合作（Mock 新闻）",
                    "date": "2026-05-09",
                    "url": MOCK_SCHEME + "yunqi/news/association-2026",
                    "summary": "Mock 摘要：协会渠道可能带来商户资源。",
                },
            ],
            "financing": [
                {
                    "round": "A 轮（Mock）",
                    "date": "2024-11-01",
                    "amount": "未披露",
                    "source_urls": [MOCK_SCHEME + "yunqi/financing/a"],
                }
            ],
            "hiring_signals": [
                "Mock 信号：近 30 天新增 6 个 BD 岗位",
                "Mock 信号：招聘页面强调月度签约目标与城市扩张",
            ],
        },
        "deep_data": {
            "shareholders": [
                {"name": "福州云栖控股（Mock）", "ratio": "62%"},
                {"name": "某产业基金（Mock）", "ratio": "18%"},
            ],
            "actual_controller": "陈某某（Mock）",
            "judicial_risk": ["Mock：1 条合同纠纷，已结案"],
            "abnormal_operation": [],
            "mock": True,
        },
    },
    {
        # 同名多主体：用于消歧与 needs_user_confirm 的失败模式
        "aliases": ["星河数据", "星河"],
        "resolved": None,
        "candidates": [
            {
                "name": "星河数据科技（杭州）有限公司",
                "unified_credit_code": "91330100MA000MOCK2",
                "region": "浙江杭州",
                "legal_representative": "李某某",
                "business_scope": "数据分析服务；增长咨询；软件研发",
            },
            {
                "name": "星河数据服务（北京）有限公司",
                "unified_credit_code": "91110100MA000MOCK3",
                "region": "北京",
                "legal_representative": "王某某",
                "business_scope": "人力资源外包；数据标注服务",
            },
        ],
        "hard_data": {},
        "soft_profile": {"products": [], "news": [], "financing": [], "hiring_signals": []},
        "deep_data": None,
    },
    {
        # 无候选：用于"公司定不到"的失败模式
        "aliases": ["未知示例公司", "不存在的公司"],
        "resolved": None,
        "candidates": [],
        "hard_data": {},
        "soft_profile": {"products": [], "news": [], "financing": [], "hiring_signals": []},
        "deep_data": None,
    },
]


def normalize_company_name(name: str) -> str:
    """去掉常见后缀与空白，用于 Mock 侧的别名匹配（不是真实工商名称归一化）。"""
    text = (name or "").strip().replace(" ", "")
    for suffix in ("股份有限公司", "有限责任公司", "有限公司", "集团", "公司"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def lookup_company(name: str) -> dict | None:
    key = normalize_company_name(name)
    if not key:
        return None
    for item in MOCK_COMPANIES:
        aliases = {normalize_company_name(a) for a in item["aliases"]}
        resolved = item.get("resolved") or {}
        resolved_key = normalize_company_name(resolved.get("name", ""))
        if key in aliases or (resolved_key and key == resolved_key):
            return item
        for cand in item["candidates"]:
            if key == normalize_company_name(cand["name"]):
                return item
    return None


def search_soft_profile(company_name: str) -> dict:
    """Mock 搜索：只接受公司名，绝不接收简历内容（11 第 2 节）。"""
    item = lookup_company(company_name)
    if not item:
        return {"products": [], "news": [], "financing": [], "hiring_signals": []}
    return item["soft_profile"]


def deep_data_for(company_name: str) -> dict | None:
    item = lookup_company(company_name)
    return item.get("deep_data") if item else None
