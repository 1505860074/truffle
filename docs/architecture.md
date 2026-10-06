# Truffle 架构设计

## 📋 文档说明

- 本文档描述 Truffle 的**技术架构与模块边界**，是所有代码实现的依据。
- 体例：每个模块给出「职责 / 输入 / 输出 / 依赖」，流程图用 Mermaid。
- 约定：架构调整必须先改本文档，再改代码；正文与「架构决策记录（ADR）」冲突时以 ADR 为准。
- 禁忌：不要把具体参数调优细节写进本文档（放 `tools/` 注释或 roadmap）。

## 1. 产品定位

Truffle 是一款 **Windows 桌面端的 AI 修图/修视频软件**，面向有修图、修视频需求的女性用户。

- 核心体验：用户用**自然语言**提出修饰需求（如「脸修瘦一点、皮肤磨光滑」），大模型理解后**调度一系列图像处理工具**完成修饰，画布**实时预览**。
- 关键认知：**大模型不直接修图**。它是「大脑」，负责理解意图、拆解步骤、调用工具；真正动手的是本地 CV 算法工具。
- 技术路线：**本地 CV/传统算法为主**，无需联网即可修饰；大模型 API 仅负责意图理解与工具编排。

## 2. 架构总览

```mermaid
flowchart TB
    User([用户]) --> UI[UI 层 PySide6]
    UI -->|自然语言| Agent[Agent 层 编排器]
    UI -->|打开/保存/撤销| Core[Core 层 图像文档]
    Agent -->|OpenAI 兼容协议| LLM[(大模型 API)]
    Agent -->|tool_call| Registry[工具注册表]
    Registry --> Tools[工具层 修饰工具]
    Tools --> CV[CV 层 人脸/皮肤/形变]
    Tools --> Core
    Core --> Canvas[画布预览]
```

图 1：Truffle 分层架构

## 3. 分层职责

### 3.1 UI 层（`src/truffle/ui/`）

- 职责：窗口、对话面板、图像画布、设置对话框、后台线程调度。
- 输入：用户文本、鼠标操作、文件路径。
- 输出：调用 Agent 处理请求；渲染图像；弹出错误/进度。
- 依赖：Core、Agent。
- 关键约束：**所有耗时处理（LLM 调用、CV 算法）必须放后台线程**，UI 线程只做渲染。

### 3.2 Agent 层（`src/truffle/agent/`）

- 职责：把「自然语言 + 当前图像上下文 + 可用工具清单」交给大模型；解析其返回的 `tool_calls`；执行工具；把结果回填给模型，循环直到模型给出最终答复。
- 输入：用户文本、工具注册表、图像文档。
- 输出：工具执行结果 + 面向用户的自然语言回复。
- 依赖：LLM 客户端、工具注册表、Core。
- 关键组件：
  - `llm_client.py`：OpenAI 兼容客户端（可配 base_url / api_key / model）。
  - `orchestrator.py`：工具调用循环（ReAct 风格），带最大轮次保护。
  - `prompts.py`：系统提示词（人设、可用工具、参数取值规范）。

### 3.3 工具层（`src/truffle/tools/`）

- 职责：每个修饰能力实现为**一个工具**，暴露「名称 / 描述 / 参数 JSON Schema / 应用逻辑」。
- 输入：当前图像 ndarray + 参数字典 + CV 分析缓存。
- 输出：修饰后的新图像 ndarray（**不原地修改**）。
- 依赖：CV 层、Core（只读上下文）。
- 关键组件：
  - `base.py`：`BaseTool` 抽象基类 + `ToolParameter`。
  - `registry.py`：工具注册表，负责生成 OpenAI function schema、按名分发。
  - 各具体工具：`skin_smooth.py`、`whiten.py`、`slim_face.py`、`enlarge_eyes.py`、`remove_blemish.py` 等。

### 3.4 CV 层（`src/truffle/cv/`）

- 职责：提供可复用的计算机视觉原语，**无状态、可缓存**。
- 能力：
  - 人脸检测（bounding box）
  - 人脸关键点（landmarks，用于瘦脸/大眼）
  - 皮肤掩膜（skin mask，用于磨皮/美白）
  - 局部形变（liquify warp，基于控制点的位移场）
- 依赖：opencv、numpy、mediapipe（可选降级）。

### 3.5 Core 层（`src/truffle/core/`）

- 职责：图像文档模型（当前图、原图、撤销/重做栈）、文件读写、管线执行。
- 输入：图像 ndarray、工具操作。
- 输出：更新后的状态 + 通知信号。
- 依赖：无（最底层，不依赖 UI/Agent）。

## 4. 核心数据流

```mermaid
sequenceDiagram
    participant U as 用户
    participant UI as UI
    participant A as Orchestrator
    participant L as LLM API
    participant R as ToolRegistry
    participant D as ImageDocument
    U->>UI: "脸修瘦一点，皮肤磨光滑"
    UI->>A: handle(text)
    A->>L: chat(messages, tools=schema)
    L-->>A: tool_calls: slim_face(+whiten?)
    A->>R: execute(slim_face, params)
    R->>D: 读取当前图 / 写回结果
    D-->>UI: imageChanged 信号
    A->>L: 回填工具结果
    L-->>A: 最终自然语言回复
    A-->>UI: reply
    UI-->>U: 展示回复 + 新预览
```

图 2：一次对话式修饰的完整数据流

## 5. 关键技术决策

| 编号 | 决策 | 理由 |
| --- | --- | --- |
| D1 | 本地 CV 算法为主，LLM 只做编排 | 隐私、速度、无按次成本，适配 Windows 桌面 |
| D2 | 工具统一抽象为 `BaseTool` + JSON Schema | 一份定义同时供 LLM 与执行器使用，扩展新工具零改动编排逻辑 |
| D3 | 图像操作为**非破坏式**（返回新图） | 支持撤销/重做，便于 A/B 对比 |
| D4 | 大模型走 **OpenAI 兼容协议** | 一套适配层通吃 OpenAI 及国内兼容模型 |
| D5 | CV 分析结果按图像指纹缓存 | 一张图多次修饰不重复检测人脸 |
| D6 | 显示层与算法层进程/线程分离 | 避免 GUI 卡死 |

（后续新增决策追加到 `docs/adr/`。）

## 6. 目录结构

```
truffle/
├─ docs/                 设计文档
├─ src/truffle/
│  ├─ main.py            程序入口
│  ├─ config.py          配置与 API Key 管理
│  ├─ core/              图像文档、管线
│  ├─ cv/                人脸/皮肤/形变原语
│  ├─ tools/             修饰工具 + 注册表
│  ├─ agent/             LLM 客户端 + 编排器
│  └─ ui/                PySide6 界面
├─ tests/                单元测试
└─ requirements.txt
```

## 7. 视频扩展（后续阶段，先留接口）

视频修图 = 抽帧 → 逐帧调用同一套工具 → 人脸跟踪保证跨帧一致 → ffmpeg 重新编码。

```mermaid
flowchart LR
    V[视频文件] --> Extract[ffmpeg 抽帧]
    Extract --> Track[人脸跟踪/关键点稳定]
    Track --> PerFrame[逐帧工具处理]
    PerFrame --> Encode[ffmpeg 编码]
    Encode --> Out[输出视频]
```

图 3：视频修饰管线（预留，MVP 不实现）

关键难点：帧间一致性（避免闪烁）。方案：跟踪人脸轨迹 + 关键点时间平滑 + 参数锁定。
