# Truffle

由 AI 驱动的 Windows 桌面修图 / 修视频软件。

用自然语言告诉它你想怎么修，它理解后调用一系列本地图像处理工具，帮你完成人像修饰、体型修饰等工作。

## 设计理念

- **大模型是大脑，不是画笔**：大模型负责理解「把脸修瘦、皮肤磨光滑」这类需求，并调度工具；真正修图的是本地 CV 算法。
- **本地优先**：常规修饰不依赖网络、不上传原图，隐私安全、无按次成本。
- **对话式交互**：面向非专业用户，用大白话就能修图，右侧实时预览。

## 快速开始

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖（含 PyTorch 无关的轻量依赖）
pip install -e .

# 3. 配置大模型 API
Copy-Item .env.example .env
# 编辑 .env 填入你的 base_url / api_key / model

# 4. 运行
python -m truffle
```

也兼容任意 OpenAI 协议的服务（OpenAI、DeepSeek、通义、Kimi、智谱、Ollama 等），改 `.env` 里的 `TRUFFLE_LLM_BASE_URL` 即可。

## 文档

- [架构设计](docs/architecture.md)
- [开发路线图](docs/roadmap.md)

## 当前状态

M0 脚手架阶段：核心闭环（对话 → 工具 → 预览）正在实现中。见路线图。

## 许可证

待定。
