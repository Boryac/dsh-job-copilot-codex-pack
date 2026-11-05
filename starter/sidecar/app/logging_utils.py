"""日志与隐私护栏（11 第 2 节）。

硬性规则：日志只记 resume_id / analysis_id 的哈希前缀与步骤耗时，
绝不记姓名、电话、邮箱、简历全文、JD 全文、任何 key。
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from contextlib import contextmanager

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _configure() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(level)


_configure()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def hash_id(value: str, length: int = 12) -> str:
    """把 resume_id / analysis_id 之类标识转成不可逆短哈希，日志里只用它。"""
    if not value:
        return "none"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def text_hash(text: str) -> str:
    """用于幂等缓存 key（简历哈希 + JD 哈希 + 公司 ID + depth 的组成部分）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@contextmanager
def timed(logger: logging.Logger, step: str, sink: dict | None = None, **safe_fields):
    """记录步骤耗时；safe_fields 只允许放哈希/计数/枚举，不许放内容。"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if sink is not None:
            sink[step] = sink.get(step, 0) + elapsed_ms
        extra = " ".join(f"{k}={v}" for k, v in safe_fields.items())
        logger.info("step=%s elapsed_ms=%d %s", step, elapsed_ms, extra)
