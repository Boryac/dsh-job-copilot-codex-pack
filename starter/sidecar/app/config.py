"""运行时配置：只从环境变量读取，绝不把 key 写进代码或文档。

Mock 模式（默认）下所有外部依赖（LLM / 天眼查 / 搜索）走内置 Mock 数据，
deep 路径也走同一张预估卡片逻辑，只是费用为 0 且标注 mock。
live 模式下 key 缺失的模块自动降级为 Mock，并在输出里明示降级原因。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MOCK = "mock"
LIVE = "live"

# 08 第 4 节 / 02 第 4 节的超时预算（毫秒），允许用环境变量覆盖以便实测
DEFAULT_TIMEOUTS_MS: dict[str, int] = {
    "resume_structurer": 30_000,
    "jd_decoder": 20_000,
    "company_recon": 30_000,
    "generate": 45_000,
    "end_to_end": 120_000,
}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_mode: str = MOCK
    sidecar_port: int = 8000
    sidecar_base_url: str = "http://localhost:8000"
    llm_api_key: str = ""
    llm_base_url: str = ""
    tianyancha_mcp_url: str = ""
    tianyancha_api_key: str = ""
    search_api_key: str = ""
    company_cache_days: int = 7
    # 测试与实测用：给 Mock 提供者注入人为延迟，用于验证超时降级真的会触发
    mock_delay_ms: int = 0
    # 测试用：强制某一步超时，取值 resume/jd/company/generate
    mock_force_timeout: str = ""
    timeouts_ms: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TIMEOUTS_MS))
    cache_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / ".cache")

    @property
    def is_mock(self) -> bool:
        return self.app_mode != LIVE

    @property
    def llm_live(self) -> bool:
        return (not self.is_mock) and bool(self.llm_api_key and self.llm_base_url)

    @property
    def tianyancha_live(self) -> bool:
        return (not self.is_mock) and bool(self.tianyancha_mcp_url and self.tianyancha_api_key)

    @property
    def search_live(self) -> bool:
        return (not self.is_mock) and bool(self.search_api_key)

    def degraded_modules(self) -> list[str]:
        """live 模式下因缺 key 而降级为 mock 的模块，用于在卡片/报告上明示。"""
        if self.is_mock:
            return []
        out = []
        if not self.llm_live:
            out.append("llm")
        if not self.tianyancha_live:
            out.append("tianyancha")
        if not self.search_live:
            out.append("search")
        return out

    def timeout_ms(self, step: str) -> int:
        override = _env_int(f"TIMEOUT_{step.upper()}_MS", 0)
        if override > 0:
            return override
        return self.timeouts_ms.get(step, 30_000)


def load_settings() -> Settings:
    """从环境变量构造配置。测试可直接构造 Settings(...) 覆盖。"""
    return Settings(
        app_mode=_env("APP_MODE", MOCK).lower(),
        sidecar_port=_env_int("SIDECAR_PORT", 8000),
        sidecar_base_url=_env("SIDECAR_BASE_URL", "http://localhost:8000"),
        llm_api_key=_env("LLM_API_KEY"),
        llm_base_url=_env("LLM_BASE_URL"),
        tianyancha_mcp_url=_env("TIANYANCHA_MCP_URL"),
        tianyancha_api_key=_env("TIANYANCHA_API_KEY"),
        search_api_key=_env("SEARCH_API_KEY"),
        company_cache_days=_env_int("COMPANY_CACHE_DAYS", 7),
        mock_delay_ms=_env_int("MOCK_DELAY_MS", 0),
        mock_force_timeout=_env("MOCK_FORCE_TIMEOUT").lower(),
    )
