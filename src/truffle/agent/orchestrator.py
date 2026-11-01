"""工具调用编排器：驱动「自然语言 → 工具调用 → 图像更新」的循环。"""

from __future__ import annotations

import base64
import json
from typing import Any, Callable

import cv2
import numpy as np

from ..core.image_doc import ImageDocument
from ..core.session import trim_messages
from ..cv.analyzer import Analyzer
from ..cv.metrics import measure
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry
from .aesthetic import AestheticPrior
from .critic import evaluate
from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT
from .solver import ParamSolver
from .style import PROFILES, resolve_style, style_target_text


def _image_content(image: np.ndarray, max_side: int = 768) -> dict:
    """把图像压成 data URL（供多模态模型查看）。"""
    h, w = image.shape[:2]
    long_side = max(h, w)
    if long_side > max_side:
        scale = max_side / long_side
        image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    data = base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


class Orchestrator:
    def __init__(
        self,
        doc: ImageDocument,
        registry: ToolRegistry,
        llm: LLMClient,
        analyzer: Analyzer,
        max_steps: int = 10,
        style_id: str = "natural",
        auto_solve: bool = True,
    ) -> None:
        self.doc = doc
        self.registry = registry
        self.llm = llm
        self.analyzer = analyzer
        self.max_steps = max_steps
        self.style_id = style_id
        self.auto_solve = auto_solve
        self.solver = ParamSolver(registry, analyzer)
        self.aesthetic = AestheticPrior()
        self.last_state: dict[str, Any] = {}
        self.last_critique: dict[str, Any] | None = None
        self.last_jobs: list[tuple[str, dict[str, Any]]] = []

    def handle(
        self,
        user_text: str,
        on_image: Callable[[], None] | None = None,
        on_tool: Callable[[str, dict[str, Any]], None] | None = None,
        image: np.ndarray | None = None,
        context: str = "",
        manual: list[tuple[str, dict[str, Any]]] | None = None,
        history: list[dict[str, Any]] | None = None,
        summary: str = "",
    ) -> str:
        if not self.doc.is_loaded:
            return "请先打开一张图片，我才能帮你修饰哦。"

        ctx = ToolContext(self.analyzer)
        if image is not None:
            content: Any = [{"type": "text", "text": user_text}, _image_content(image)]
        else:
            content = user_text
        system = SYSTEM_PROMPT
        if context.strip():
            system += "\n\n【用户偏好 / 核心上下文】\n" + context.strip()
        if manual:
            lines = "；".join(f"{name} {params}" for name, params in manual)
            system += "\n\n【用户已手动调节（请在此基础上继续微调，避免重复叠加）】\n" + lines
        if summary.strip():
            system += "\n\n【较早对话摘要（已压缩，供参考）】\n" + summary.strip()
        steps = self.doc.steps_summary()
        if steps:
            system += "\n\n【已完成的编辑步骤（区分 AI / 手动）】\n" + "\n".join(steps)
        info = self._image_info()
        if info:
            system += "\n\n【当前图像】\n" + info
        try:
            current = self.doc.current
            self.last_state = measure(current, self.analyzer)
            style = resolve_style(self.style_id)
            system += "\n\n[IMAGE_STATE]\n" + json.dumps(
                self.last_state, ensure_ascii=False, separators=(",", ":")
            )
            aesthetic = self.aesthetic.score(current, self.last_state)
            system += "\n\n[AESTHETIC]\n" + json.dumps(
                aesthetic, ensure_ascii=False, separators=(",", ":")
            )
            system += "\n\n[STYLE_TARGET]\n" + style_target_text(style)
            system += (
                "\n\n[STYLE_LIBRARY]\n"
                + ", ".join(PROFILES.keys())
                + "\n\n[AGENT_RULES]\n"
                + "你只负责理解需求、选择风格/目标/工具，不要猜具体强度参数。\n"
                + "需要基础调色/人像/形体处理时，优先调用 apply_style，让本地求解器计算参数。\n"
                + "需要确认当前画面指标时调用 inspect_image；不要编造指标。\n"
                + "编辑后评审结果会以 tool 消息返回；若未达标，可再次 apply_style 或改用普通工具微调。\n"
            )
        except Exception:
            self.last_state = {}

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": content})

        reply = "已经帮你处理好啦～"
        tools = self.registry.schemas() + self._agent_schemas()
        for _ in range(self.max_steps):
            message = self.llm.chat(messages, tools=tools)
            tool_calls = getattr(message, "tool_calls", None)

            if not tool_calls:
                reply = (message.content or "").strip() or "已经帮你处理好啦～"
                break

            messages.append(self._assistant_message(message, tool_calls))
            for call in tool_calls:
                name = call.function.name
                if name == "inspect_image":
                    result_text = self._state_text()
                elif name == "apply_style":
                    result_text = self._apply_style(call, ctx, on_image, on_tool)
                else:
                    result_text = self._run_tool(call, ctx, on_image, on_tool)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result_text}
                )
        else:
            reply = "操作步骤有点多，我先停一下～你可以再告诉我想调整的地方。"

        if history is not None:
            # 把本轮（含最终回复）并入对话记忆；不改动已发出的 messages 列表
            history[:] = trim_messages(messages[1:] + [{"role": "assistant", "content": reply}])
        return reply

    # ---------- 内部 ----------
    def _image_info(self) -> str:
        try:
            image = self.doc.current
        except RuntimeError:
            return ""
        h, w = image.shape[:2]
        parts = [f"尺寸 {w}×{h}"]
        try:
            analysis = self.analyzer.analyze(image)
            parts.append(f"人脸 {len(analysis.faces)} 张")
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.analyzer.pose(image) is not None:
                parts.append("检测到人体")
        except Exception:  # noqa: BLE001
            pass
        return "；".join(parts)

    def _agent_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "inspect_image",
                    "description": "读取当前图片的结构化状态：影调、色彩、人脸、人体、质量与风格向量。不修改图片。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "apply_style",
                    "description": (
                        "按指定风格自动调整图片。你只选择风格、强度和允许的工具，"
                        "具体参数由本地求解器计算。可用风格："
                        + ", ".join(PROFILES.keys())
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "style": {
                                "type": "string",
                                "description": "风格 id 或中文名，如 tangshui / 糖水 / cold_white。",
                            },
                            "intensity": {
                                "type": "number",
                                "minimum": 0.2,
                                "maximum": 1.5,
                                "description": "整体强度，默认 1.0。",
                            },
                            "allowed_tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "可选：限制求解器只使用这些工具。",
                            },
                        },
                        "required": ["style"],
                    },
                },
            },
        ]

    @staticmethod
    def _parse_args(call) -> dict[str, Any]:
        try:
            value = json.loads(call.function.arguments or "{}")
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _state_text(self) -> str:
        if not self.last_state:
            try:
                self.last_state = measure(self.doc.current, self.analyzer)
            except Exception:
                return "{}"
        return json.dumps(self.last_state, ensure_ascii=False, separators=(",", ":"))

    def _apply_style(
        self,
        call,
        ctx: ToolContext,
        on_image: Callable[[], None] | None,
        on_tool: Callable[[str, dict[str, Any]], None] | None,
    ) -> str:
        params = self._parse_args(call)
        profile = resolve_style(str(params.get("style", "")), self.style_id)
        self.style_id = profile.id
        try:
            intensity = float(params.get("intensity", 1.0))
        except (TypeError, ValueError):
            intensity = 1.0
        intensity = max(0.2, min(1.5, intensity))
        allowed_raw = params.get("allowed_tools")
        allowed = {str(item) for item in allowed_raw} if isinstance(allowed_raw, list) else None
        try:
            current = self.doc.current
            before = measure(current, self.analyzer)
            result = self.solver.solve(current, profile, before, allowed)
        except Exception as exc:  # noqa: BLE001
            return f"apply_style 失败：{exc}"
        executed: list[tuple[str, dict[str, Any]]] = []
        for name, tool_params in result.jobs:
            scaled = {
                key: (round(float(value) * intensity, 4) if isinstance(value, (int, float)) and not isinstance(value, bool) else value)
                for key, value in tool_params.items()
            }
            try:
                source = self.doc.tool_source() if hasattr(self.doc, "tool_source") else self.doc.current
                new_image = self.registry.execute(name, source, ctx, scaled)
                safe = self.registry.get(name).coerce_params(scaled)
                self._commit(name, safe, new_image)
                executed.append((name, safe))
                if on_tool is not None:
                    on_tool(name, safe)
            except Exception as exc:  # noqa: BLE001
                return f"工具 {name} 执行失败：{exc}"
        if on_image is not None and executed:
            on_image()
        if not executed:
            return json.dumps(
                {"style": profile.id, "jobs": [], "message": "当前已接近目标，无需调整"},
                ensure_ascii=False,
            )
        after = measure(self.doc.current, self.analyzer)
        aesthetic = self.aesthetic.score(self.doc.current, after)
        critique = evaluate(before, after, profile, executed, result.naturalness, aesthetic)
        self.last_state = after
        self.last_jobs = executed
        self.last_critique = critique.to_dict()
        compact = {
            "tone": after.get("tone", {}),
            "color": after.get("color", {}),
            "quality": after.get("quality", {}),
            "style_vec": after.get("style_vec", {}),
            "faces": [
                {"id": item.get("id"), "skin": item.get("skin", {})}
                for item in after.get("faces", [])
            ],
        }
        return json.dumps(
            {
                "style": profile.id,
                "jobs": executed,
                "critique": self.last_critique,
                "after": compact,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _commit(self, name: str, params: dict[str, Any], new_image: np.ndarray) -> None:
        if hasattr(self.doc, "commit_tool"):
            self.doc.commit_tool(name, params, new_image, origin="ai")
        else:
            self.doc.push_op("tool", name, {"name": name, "params": params}, image=new_image, origin="ai")

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
        on_tool: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> str:
        name = call.function.name
        try:
            params = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            params = {}
        try:
            source = self.doc.tool_source() if hasattr(self.doc, "tool_source") else self.doc.current
            new_image = self.registry.execute(name, source, ctx, params)
            safe = self.registry.get(name).coerce_params(params)
            if hasattr(self.doc, "commit_tool"):
                # 图层文档：工具只作用于当前活动图层
                self.doc.commit_tool(name, safe, new_image, origin="ai")
            else:
                # 旧版单图文档：记录为可重放的操作，同时保留即时结果
                self.doc.push_op(
                    "tool", name, {"name": name, "params": safe},
                    image=new_image, origin="ai",
                )
            if on_tool is not None:
                on_tool(name, safe)
            if on_image is not None:
                on_image()
            return f"工具 {name} 执行成功，参数：{params}"
        except Exception as exc:  # 反馈给模型，让它换一种方式重试
            return f"工具 {name} 执行失败：{exc}"
