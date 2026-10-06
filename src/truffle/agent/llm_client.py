"""OpenAI 兼容的大模型客户端。

只要服务实现 OpenAI 的 `/chat/completions` 协议即可接入，
改 `base_url` 即可切换到 DeepSeek / 通义 / Kimi / 智谱 / Ollama 等。
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..config import LLMSettings


class LLMClient:
    def __init__(self, settings: LLMSettings) -> None:
        if not settings.api_key:
            raise ValueError("尚未配置大模型 API Key，请在「设置」中填写。")
        self._client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
        )
        self.model = settings.model

    def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None):
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message
