"""编排器闭环测试：用假 LLM 模拟大模型的工具调用行为（无需真实 API）。"""

import numpy as np

from truffle.agent.orchestrator import Orchestrator
from truffle.core.image_doc import ImageDocument
from truffle.cv.analyzer import Analyzer
from truffle.tools.registry import build_default_registry


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeLLM:
    """按脚本依次返回预设消息，并记录收到的对话。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.seen = []

    def chat(self, messages, tools=None):
        self.seen.append(messages)
        return self._responses.pop(0)


def _loaded_doc() -> ImageDocument:
    doc = ImageDocument()
    img = np.full((120, 120, 3), (140, 160, 205), dtype=np.uint8)
    doc._original = img.copy()
    doc._current = img.copy()
    return doc


def test_tool_call_updates_document():
    doc = _loaded_doc()
    before = doc.current.copy()
    llm = FakeLLM(
        [
            FakeMessage(
                tool_calls=[FakeCall("1", "whiten", '{"strength": 0.8}')]
            ),
            FakeMessage(content="已经帮你美白啦～"),
        ]
    )
    orch = Orchestrator(doc, build_default_registry(), llm, Analyzer())

    updated = {"n": 0}
    reply = orch.handle("帮我美白", on_image=lambda: updated.__setitem__("n", updated["n"] + 1))

    assert reply == "已经帮你美白啦～"
    assert updated["n"] == 1
    assert doc.can_undo
    assert not np.array_equal(doc.current, before)
    # 第二轮请求里应包含 system、user、assistant(tool_calls)、tool 四条消息
    assert len(llm.seen[1]) == 4


def test_plain_reply_without_tools():
    doc = _loaded_doc()
    llm = FakeLLM([FakeMessage(content="你好呀，我是 Truffle～")])
    orch = Orchestrator(doc, build_default_registry(), llm, Analyzer())

    reply = orch.handle("你好")
    assert reply == "你好呀，我是 Truffle～"
    assert not doc.can_undo


def test_no_image_prompts_to_open_one():
    doc = ImageDocument()
    orch = Orchestrator(doc, build_default_registry(), FakeLLM([]), Analyzer())
    reply = orch.handle("磨皮")
    assert "打开" in reply


def test_bad_tool_is_reported_back_to_model():
    doc = _loaded_doc()
    llm = FakeLLM(
        [
            FakeMessage(tool_calls=[FakeCall("1", "not_a_tool", "{}")]),
            FakeMessage(content="换一种方式处理"),
        ]
    )
    orch = Orchestrator(doc, build_default_registry(), llm, Analyzer())
    reply = orch.handle("随便弄一下")
    assert reply == "换一种方式处理"
    # 失败信息必须作为 tool 消息回填给模型
    tool_msg = llm.seen[1][-1]
    assert tool_msg["role"] == "tool"
    assert "失败" in tool_msg["content"]


def test_stops_at_max_steps():
    doc = _loaded_doc()
    looping = [
        FakeMessage(tool_calls=[FakeCall(str(i), "whiten", "{}")]) for i in range(3)
    ]
    orch = Orchestrator(doc, build_default_registry(), FakeLLM(looping), Analyzer(), max_steps=3)
    reply = orch.handle("一直美白")
    assert "停" in reply
