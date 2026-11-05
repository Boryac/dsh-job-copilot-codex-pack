"""版本号：缓存 key 必须同时绑定「实现版本」与「数据契约版本」。

为什么单独抽一个文件：
- 07 阶段的教训是，改了硬数据 source 标注（`tianyancha_mcp` -> `mock://tianyancha/basic`）之后，
  旧缓存照样被读出来，报告仍然写着假来源，肉眼完全看不出来。缓存不绑版本 = 代码改了但结果没变。
- 所以缓存 key 里必须带版本，且写入的 payload 里也记版本；任何一侧对不上就当作未命中。
- 版本号只增不减；只要动了 `recon` 层的输出语义（字段、来源标注、消歧口径），
  就必须递增 `COMPANY_CACHE_IMPL`，否则旧结果会继续冒充新逻辑。
"""
from __future__ import annotations

from .schemas import SCHEMA_VERSION

# 代码实现版本（recon 层输出语义变更时递增）
COMPANY_CACHE_IMPL = "recon-2"

# 缓存版本 = 实现版本 + 契约版本；两者任一变化都让旧缓存失效
COMPANY_CACHE_VERSION = f"{COMPANY_CACHE_IMPL}+schema{SCHEMA_VERSION}"


def cache_version() -> str:
    """当前生效的缓存版本号（供输出与文档引用，避免文档写死一个会过期的字符串）。"""
    return COMPANY_CACHE_VERSION
