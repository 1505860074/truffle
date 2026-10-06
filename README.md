# Truffle

由 AI 驱动的 Windows 桌面修图 / 修视频软件。

用自然语言告诉它你想怎么修，它理解后调用一系列本地图像处理工具，帮你完成人像修饰、体型修饰等工作。

## 设计理念

- **大模型是大脑，不是画笔**：大模型负责理解「把脸修瘦、皮肤磨光滑」这类需求，并调度工具；真正修图的是本地 CV 算法。
- **本地优先**：常规修饰不依赖网络、不上传原图，隐私安全、无按次成本。
- **对话式交互**：面向非专业用户，用大白话就能修图，右侧实时预览。

## 快速开始（一键启动，无终端窗口）

**双击项目根目录的 `Truffle.vbs`** 即可，全程不出现 cmd 黑窗。

- 首次运行会自动创建运行环境并安装依赖（约 1~3 分钟，仅此一次，此时会显示进度窗口），完成后自动打开软件；
- 之后每次双击都是秒开，且没有任何终端窗口；
- 第一次打开软件会自动弹出配置窗口，**在软件内填写大模型 API** 即可开始，无需任何命令行或额外配置。

> 前提：本机已安装 Python 3.10+（安装时勾选 “Add Python to PATH”）。若未安装，启动器会给出提示。
> 备用入口：`Truffle.bat`（会显示控制台，便于排查问题）。
> 若软件无窗口启动失败，错误会记录在 `%APPDATA%\Truffle\error.log`。

### 开发方式手动启动（可选）

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.\.venv\Scripts\python.exe run.py
```

### 配置大模型

在软件内「设置 → 大模型配置」填写，支持任意 OpenAI 兼容服务（OpenAI、DeepSeek、通义、Kimi、智谱、Ollama 等），只改「接口地址」和「模型名称」即可。
配置保存在 `%APPDATA%\Truffle\config.json`，完全由软件自身读写。

## 文档

- [架构设计](docs/architecture.md)
- [开发路线图](docs/roadmap.md)

## 离线自检

不配置大模型也能验证修图引擎是否正常：

```powershell
.\.venv\Scripts\python.exe scripts\selftest.py
# 或用自己的照片
.\.venv\Scripts\python.exe scripts\selftest.py "C:\path\your.jpg"
```

## 当前状态

M0 脚手架阶段：核心闭环（对话 → 工具 → 预览）正在实现中。见路线图。

## 许可证

待定。
