"""公司数据缓存（05 第 4 节）：同一 resolved 主体的 basic 硬数据 7 天内复用。

缓存只存公开工商字段与软信息，不存任何简历内容；命中也必须标注 cached + fetched_at。

版本绑定（v1 补缺口）：key 与 payload 都带 `COMPANY_CACHE_VERSION`。
- key 带版本：换版本后落在不同文件名，旧文件压根不会被读到；
- payload 带版本：即使文件被手工复制到新路径、或 key 算法被改，也能被版本校验拦下；
- 版本不匹配的文件直接删除，避免旧逻辑结果长期躺在缓存目录里冒充新结果。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..logging_utils import text_hash
from ..version import COMPANY_CACHE_VERSION

CST = timezone(timedelta(hours=8))


class CompanyCache:
    def __init__(self, cache_dir: str | Path, days: int = 7, version: str | None = None):
        self.dir = Path(cache_dir) / "company"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(days=max(days, 1))
        # 运行时读取模块常量：这样版本递增（或测试里 monkeypatch）能真正影响新建实例，
        # 而不是被默认参数在 import 时就冻住。
        self.version = version or COMPANY_CACHE_VERSION

    def scoped_key(self, key: str) -> str:
        """把业务 key 拼上版本，得到真正参与哈希的缓存 key。"""
        return f"{self.version}|{key}"

    def _path(self, key: str) -> Path:
        return self.dir / f"{text_hash(self.scoped_key(key))!s}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            path.unlink(missing_ok=True)
            return None
        if payload.get("cache_version") != self.version:
            # 旧版本写下的结果不许参与本次判定：删掉，让它自然重新拉取
            path.unlink(missing_ok=True)
            return None
        if datetime.now(CST) - fetched_at > self.ttl:
            return None
        return payload

    def put(self, key: str, payload: dict) -> None:
        data = dict(payload)
        data["cache_version"] = self.version
        data["fetched_at"] = datetime.now(CST).replace(microsecond=0).isoformat()
        self._path(key).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def clear(self) -> None:
        for p in self.dir.glob("*.json"):
            p.unlink(missing_ok=True)
