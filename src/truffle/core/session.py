"""对话记忆持久化：分段记忆。

- 最近 `_MAX_RECENT_TURNS` 轮对话：完整保留（连同工具调用）；
- 更早的对话：**阶段性压缩**成一份文字摘要，下次自动载入；
- 只存文本（多模态的图片 data URL 会被剥离），避免文件过大。
"""

from __future__ import annotations

import json
from typing import Any

from ..config import config_dir

SESSION_PATH = config_dir() / "session.json"
_MAX_RECENT_TURNS = 5
_SUMMARY_CAP = 4000


def _sanitize(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            content = msg.get("content")
            if isinstance(content, list):
                text = next(
                    (part.get("text", "") for part in content if part.get("type") == "text"), ""
                )
                out.append({"role": "user", "content": text})
            else:
                out.append({"role": "user", "content": content})
        elif role == "assistant":
            out.append(
                {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")}
            )
        elif role == "tool":
            out.append(
                {"role": "tool", "tool_call_id": msg.get("tool_call_id"), "content": msg.get("content")}
            )
    return out


def trim_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留最近若干轮，且从一条 user 消息开始（保证工具调用配对完整）。"""
    user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idx) > _MAX_RECENT_TURNS:
        messages = messages[user_idx[-_MAX_RECENT_TURNS]:]
    while messages and messages[0].get("role") != "user":
        messages.pop(0)
    return messages


def compress(messages: list[dict[str, Any]]) -> str:
    """把若干轮对话压成一份紧凑的文字摘要（规则式）。"""
    lines: list[str] = []
    user_text: str | None = None
    tools: list[str] = []

    def flush() -> None:
        if user_text is None:
            return
        action = "、".join(tools) if tools else "（未调用工具）"
        lines.append(f"- 用户：{user_text} → {action}")

    for msg in messages:
        role = msg.get("role")
        if role == "user":
            flush()
            user_text = str(msg.get("content", ""))
            tools = []
        elif role == "assistant" and msg.get("tool_calls"):
            for call in msg["tool_calls"]:
                fn = call.get("function", {})
                tools.append(f"{fn.get('name', '')}{fn.get('arguments', '')}")
    flush()
    return "\n".join(lines)


def compress_older(
    summary: str, messages: list[dict[str, Any]], keep_turns: int = _MAX_RECENT_TURNS
) -> tuple[str, list[dict[str, Any]]]:
    user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idx) <= keep_turns:
        return summary, messages
    cut = user_idx[-keep_turns]
    older, recent = messages[:cut], messages[cut:]
    compressed = compress(older)
    merged = (summary + "\n" + compressed).strip() if summary else compressed
    return merged[-_SUMMARY_CAP:], recent


def load() -> tuple[str, list[dict[str, Any]]]:
    try:
        raw = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", []
    if not isinstance(raw, dict):
        return "", []
    summary = str(raw.get("summary", ""))
    messages = raw.get("messages", [])
    return summary, _sanitize(messages) if isinstance(messages, list) else []


def save(summary: str, messages: list[dict[str, Any]]) -> str:
    new_summary, recent = compress_older(summary, _sanitize(messages))
    try:
        SESSION_PATH.write_text(
            json.dumps({"summary": new_summary, "messages": recent}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return new_summary


def clear() -> None:
    try:
        SESSION_PATH.unlink(missing_ok=True)
    except OSError:
        pass
