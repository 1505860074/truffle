"""工具调用编排器：驱动「自然语言 → 工具调用 → 图像更新」的循环。"""

from __future__ import annotations

import json
from typing import Any, Callable

from ..core.image_doc import ImageDocument
from ..cv.analyzer import Analyzer
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry
from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT


class Orchestrator:
    def __init__(
        self,
        doc: ImageDocument,
        registry: ToolRegistry,
        llm: LLMClient,
        analyzer: Analyzer,
        max_steps: int = 6,
    ) -> None:
        self.doc = doc
        self.registry = registry
        self.llm = llm
        self.analyzer = analyzer
        self.max_steps = max_steps

    def handle(
        self, user_text: str, on_image: Callable[[], None] | None = None
    ) -> str:
        if not self.doc.is_loaded:
            return "请先打开一张图片，我才能帮你修饰哦。"

        ctx = ToolContext(self.analyzer)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        for _ in range(self.max_steps):
            message = self.llm.chat(messages, tools=self.registry.schemas())
            tool_calls = getattr(message, "tool_calls", None)

            if not tool_calls:
                return (message.content or "").strip() or "已经帮你处理好啦。"

            messages.append(self._assistant_message(message, tool_calls))

            for call in tool_calls:
                result_text = self._run_tool(call, ctx, on_image)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_text,
                    }
                )

        return "操作步骤有点多，我先停一下～你可以再告诉我想调整的地方。"

    # ---------- 内部 ----------
    @staticmethod
    def _assistant_message(message, tool_calls) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ],
        }

    def _run_tool(
        self,
        call,
        ctx: ToolContext,
        on_image: Callable[[], None] | None,
    ) -> str:
        name = call.function.name
        try:
            params = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            params = {}
        try:
            new_image = self.registry.execute(name, self.doc.current, ctx, params)
            self.doc.push(new_image)
            if on_image is not None:
                on_image()
            return f"工具 {name} 执行成功，参数：{params}"
        except Exception as exc:  # 反馈给模型，让它换一种方式重试
            return f"工具 {name} 执行失败：{exc}"
