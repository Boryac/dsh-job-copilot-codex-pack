"""公司背调测试（T2.1 / T4.1）：消歧、缓存、额度记账、deep 零调用与幂等。"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.recon.service import company_recon, estimate_deep
from app.schemas import CompanyRecon, DeepEstimate


def test_basic_resolves_single_candidate(settings):
    result = company_recon("云栖生活", settings)
    assert isinstance(result, CompanyRecon)
    assert result.company_resolved.name == "云栖生活科技（福州）有限公司"
    assert result.company_resolved.disambiguation.needs_user_confirm is False
    assert result.hard_data.founded_at.verified is True


def test_basic_quota_is_recorded(settings):
    result = company_recon("云栖生活", settings)
    assert result.quota_consumed.tianyancha_calls == 2
    assert result.quota_consumed.search_calls == 4
    assert result.quota_consumed.tianyancha_detail
    for detail in result.quota_consumed.tianyancha_detail:
        assert detail.mock is True  # Mock 模式必须标注，不许冒充真实调用


def test_mock_urls_use_mock_scheme(settings):
    result = company_recon("云栖生活", settings)
    assert result.soft_profile.source_urls
    assert all(url.startswith("mock://") for url in result.soft_profile.source_urls)


def test_ambiguous_company_needs_confirmation(settings):
    result = company_recon("星河数据", settings)
    assert isinstance(result, CompanyRecon)
    assert result.company_resolved.disambiguation.needs_user_confirm is True
    assert result.company_resolved.name is None
    assert all(not f.verified for f in result.hard_data.fields().values())
    assert result.quota_consumed.tianyancha_calls == 0
    assert result.quota_consumed.search_calls == 0


def test_unknown_company_is_not_invented(settings):
    result = company_recon("完全不存在的公司名称", settings)
    assert result.company_resolved.name is None
    assert result.company_resolved.disambiguation.candidates == []
    assert result.soft_profile.products == []
    assert result.soft_profile.news == []


def test_cache_hit_costs_nothing(settings):
    first = company_recon("云栖生活", settings)
    assert first.cache.hit is False
    second = company_recon("云栖生活", settings)
    assert second.cache.hit is True
    assert second.quota_consumed.tianyancha_calls == 0
    assert second.quota_consumed.search_calls == 0
    assert second.hard_data.founded_at.value == first.hard_data.founded_at.value


def test_deep_estimate_makes_zero_calls(settings):
    estimate = estimate_deep("云栖生活", settings)
    assert isinstance(estimate, DeepEstimate)
    assert estimate.needs_confirmation is True
    assert estimate.estimate["calls"] > 0
    assert estimate.quota_consumed.tianyancha_calls == 0
    assert estimate.quota_consumed.search_calls == 0


def test_deep_without_confirmation_returns_estimate_only(settings):
    result = company_recon("云栖生活", settings, depth="deep", confirmed_deep=False)
    assert isinstance(result, DeepEstimate)
    assert result.quota_consumed.tianyancha_calls == 0


def test_deep_confirmed_runs_and_is_idempotent(settings):
    first = company_recon("云栖生活", settings, depth="deep", confirmed_deep=True, idempotency_key="case-1")
    assert first.depth_used == "deep"
    assert first.deep_data is not None
    assert first.quota_consumed.tianyancha_calls > 2  # basic + deep
    second = company_recon("云栖生活", settings, depth="deep", confirmed_deep=True, idempotency_key="case-1")
    assert second.cache.hit is True
    assert second.quota_consumed.tianyancha_calls == 0


def test_deep_on_ambiguous_company_is_blocked(settings):
    result = company_recon("星河数据", settings, depth="deep", confirmed_deep=True)
    assert isinstance(result, DeepEstimate)
    assert result.estimate["calls"] == 0
    assert "未唯一确定" in result.note


def test_quota_exhausted_degrades_to_search_only(settings, monkeypatch):
    monkeypatch.setenv("MOCK_QUOTA_EXHAUSTED", "1")
    result = company_recon("云栖生活", settings)
    assert any("额度耗尽" in d for d in result.degradations)
    assert all(not f.verified for f in result.hard_data.fields().values())
    assert result.quota_consumed.tianyancha_calls == 0


def test_invalid_depth_rejected(settings):
    from app.errors import ToolError

    with pytest.raises(ToolError):
        company_recon("云栖生活", settings, depth="ultra")


def test_empty_company_rejected(settings):
    from app.errors import ToolError

    with pytest.raises(ToolError):
        company_recon("   ", settings)


def test_live_mode_without_keys_degrades_and_says_so(tmp_path):
    live = Settings(app_mode="live", cache_dir=tmp_path / "cache")
    result = company_recon("云栖生活", live)
    assert any("降级" in d for d in result.degradations)
    assert live.degraded_modules() == ["llm", "tianyancha", "search"]


def test_mock_hard_data_source_is_not_disguised_as_real(settings):
    """Mock 模式的硬数据不能让报告写成"来源：tianyancha_mcp"。"""
    result = company_recon("云栖生活", settings)
    sources = {key: field.source for key, field in result.hard_data.fields().items() if field.value}
    assert sources
    for key, source in sources.items():
        assert source.startswith("mock://"), f"{key} 的 source={source} 会冒充真实核验结果"
