"""LLM 客户端：mock 模式返回确定性结果，live 模式才真的发请求。

为什么 mock 不用随机文本：
测试与回归需要可复现，所以 mock 的"生成"由规则化模板完成（EvidenceBoundGenerator），
本模块只负责 live 调用的封装与超时。这样 mock 与 live 走同一条"生成 -> 校验"链路。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import Settings
from ..errors import UPSTREAM_ERROR, ToolError


class LlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.llm_live

    def complete_json(self, system: str, user: str, timeout_ms: int = 30_000) -> dict:
        """返回解析后的 JSON。未配置 key 时抛 NOT_CONFIGURED，由上层降级到规则生成。"""
        if not self.enabled:
            raise ToolError(
                code=UPSTREAM_ERROR,
                message="未配置 LLM（LLM_API_KEY / LLM_BASE_URL 为空），已降级为规则化生成。",
                retryable=False,
                fallback="rule_based_generator",
            )
        payload = {
            "model": "default",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.llm_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ToolError(
                code=UPSTREAM_ERROR,
                message=f"LLM 调用失败：{type(exc).__name__}，已降级为规则化生成。",
                retryable=True,
                fallback="rule_based_generator",
            ) from exc
        try:
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ToolError(
                code=UPSTREAM_ERROR,
                message="LLM 返回结构不符合预期，已降级为规则化生成。",
                retryable=True,
                fallback="rule_based_generator",
            ) from exc
