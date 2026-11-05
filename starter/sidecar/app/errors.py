"""错误契约（02 第 6 节）：code / message / retryable / fallback。

所有对外失败必须走 ToolError，不允许把原始异常堆栈直接推给用户。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 错误码是契约的一部分，新增需要同步 02_ARCHITECTURE.md 第 6 节
TIMEOUT = "TIMEOUT"
PARSE_FAILED = "PARSE_FAILED"
COMPANY_AMBIGUOUS = "COMPANY_AMBIGUOUS"
QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
UPSTREAM_ERROR = "UPSTREAM_ERROR"
INVALID_INPUT = "INVALID_INPUT"
URL_FETCH_FAILED = "URL_FETCH_FAILED"
NOT_CONFIGURED = "NOT_CONFIGURED"
EVIDENCE_INVALID = "EVIDENCE_INVALID"


@dataclass
class ToolError(Exception):
    code: str
    message: str
    retryable: bool = False
    fallback: str = ""
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "fallback": self.fallback,
            **({"detail": self.detail} if self.detail else {}),
        }


def timeout_error(step: str, budget_ms: int, fallback: str) -> ToolError:
    return ToolError(
        code=TIMEOUT,
        message=f"{step} 超过 {budget_ms / 1000:.0f} 秒预算，已按降级方案继续。",
        retryable=True,
        fallback=fallback,
    )
