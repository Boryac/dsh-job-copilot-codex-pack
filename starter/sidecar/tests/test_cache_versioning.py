"""缓存版本绑定（v1 补缺口）：旧缓存不许参与新逻辑的判定。

背景：之前改了硬数据来源标注后，旧缓存仍被读出来，报告照样写着旧来源，
代码改了但结果没变，肉眼完全看不出来。这组测试就是为了让这件事不再发生。
"""
from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.recon import cache as cache_module
from app.recon import service as service_module
from app.recon.cache import CompanyCache
from app.recon.service import _cache_key, company_recon
from app.version import COMPANY_CACHE_VERSION, cache_version


def _settings(tmp_path) -> Settings:
    return Settings(app_mode="mock", cache_dir=tmp_path / "cache")


# ---------------------------------------------------------------- 版本号本身
def test_cache_version_binds_impl_and_schema():
    assert COMPANY_CACHE_VERSION.startswith("recon-")
    assert "+schema" in COMPANY_CACHE_VERSION
    assert cache_version() == COMPANY_CACHE_VERSION


def test_same_key_maps_to_different_file_after_version_change(tmp_path):
    old = CompanyCache(tmp_path, version="recon-1+schema1.0")
    new = CompanyCache(tmp_path, version="recon-2+schema1.0")
    assert old._path("云栖生活::basic") != new._path("云栖生活::basic")


# ---------------------------------------------------------------- 落盘内容可审计
def test_cached_payload_records_version(tmp_path):
    cache = CompanyCache(tmp_path, version="recon-9+schema1.0")
    cache.put("k", {"payload": {"ok": True}})
    raw = json.loads(cache._path("k").read_text(encoding="utf-8"))
    assert raw["cache_version"] == "recon-9+schema1.0"
    assert cache.get("k") is not None


# ---------------------------------------------------------------- 版本不匹配 = 未命中
def test_payload_with_stale_version_is_rejected_and_removed(tmp_path):
    """即使文件被复制到新 key 路径（key 算法变了、人工拷文件），也必须被版本拦住。"""
    new = CompanyCache(tmp_path, version="recon-2+schema1.0")
    path = new._path("k")
    path.write_text(
        json.dumps(
            {
                "cache_version": "recon-1+schema1.0",
                "fetched_at": "2026-11-05T10:00:00+08:00",
                "payload": {"stale": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert new.get("k") is None, "旧版本 payload 不许命中"
    assert not path.exists(), "命中不了的旧文件要删掉，避免长期躺在缓存目录里"


def test_payload_without_version_is_rejected(tmp_path):
    """升级前写下的文件没有 cache_version 字段，同样不能命中。"""
    new = CompanyCache(tmp_path, version="recon-2+schema1.0")
    new._path("k").write_text(
        json.dumps({"fetched_at": "2026-11-05T10:00:00+08:00", "payload": {"legacy": True}}),
        encoding="utf-8",
    )
    assert new.get("k") is None


# ---------------------------------------------------------------- 业务 key 维度
def test_cache_key_separates_data_mode():
    """live 不许读到 mock 期间写下的结果（否则 mock:// 来源会出现在真实配置里）。"""
    assert _cache_key("云栖生活", "basic", "mock") != _cache_key("云栖生活", "basic", "live")


def test_cache_key_separates_company():
    assert _cache_key("云栖生活", "basic", "mock") != _cache_key("星河数据", "basic", "mock")


# ---------------------------------------------------------------- 端到端：改逻辑后旧缓存不复用
def test_version_bump_after_logic_change_invalidates_old_cache(tmp_path, monkeypatch):
    """模拟一次"改了 recon 输出语义但没清缓存"的提交：
    版本递增 + 实现变更后，第二次必须落回真实计算，不能拿旧结果冒充新逻辑。"""
    s = _settings(tmp_path)
    first = company_recon("云栖生活", s)
    assert first.cache.hit is False
    assert first.cache.version == COMPANY_CACHE_VERSION
    assert first.quota_consumed.tianyancha_calls > 0

    # 旧逻辑的快照：命中过缓存的话，下面这些断言语义会全部失效
    monkeypatch.setattr(cache_module, "COMPANY_CACHE_VERSION", "recon-999+schema1.0")
    original = service_module._hard_data_from

    def changed(raw: dict, data_mode: str = "live") -> dict:
        out = original(raw, data_mode)
        for field in out.values():
            if field.get("value"):
                field["source"] = "mock://tianyancha/recon-999"
        return out

    monkeypatch.setattr(service_module, "_hard_data_from", changed)

    second = company_recon("云栖生活", s)
    assert second.cache.hit is False, "版本变了还命中缓存，等于改代码不改结果"
    assert second.cache.version == "recon-999+schema1.0"
    sources = {f.source for f in second.hard_data.fields().values() if f.value}
    assert sources == {"mock://tianyancha/recon-999"}, f"读到了旧逻辑的结果：{sources}"
    assert second.quota_consumed.tianyancha_calls > 0, "未命中缓存却没重新调用，说明数据来源不明"


def test_cache_hit_makes_no_paid_calls_and_keeps_version(tmp_path):
    s = _settings(tmp_path)
    first = company_recon("云栖生活", s)
    second = company_recon("云栖生活", s)

    assert first.cache.hit is False and second.cache.hit is True
    assert second.quota_consumed.tianyancha_calls == 0
    assert second.quota_consumed.search_calls == 0
    assert second.cache.version == COMPANY_CACHE_VERSION
    assert second.cache.fetched_at == first.fetched_at
    # 命中缓存不该改变结果本身（除了 cache 元信息与本次记账）
    assert second.hard_data.model_dump() == first.hard_data.model_dump()
    assert second.soft_profile.model_dump() == first.soft_profile.model_dump()


def test_cache_hit_does_not_leak_previous_quota(tmp_path):
    """上一次调用花了钱，命中缓存时本次必须记 0，否则用户会以为又被扣费。"""
    s = _settings(tmp_path)
    first = company_recon("云栖生活", s)
    assert first.quota_consumed.tianyancha_calls > 0
    second = company_recon("云栖生活", s)
    assert second.quota_consumed.model_dump()["tianyancha_calls"] == 0


@pytest.mark.parametrize("depth", ["basic"])
def test_cache_version_is_visible_in_output(tmp_path, depth):
    s = _settings(tmp_path)
    result = company_recon("云栖生活", s, depth=depth)
    dumped = result.model_dump()
    assert dumped["cache"]["version"] == COMPANY_CACHE_VERSION
