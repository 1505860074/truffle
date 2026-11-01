# Truffle

由 AI 驱动的 Windows 桌面修图 / 修视频软件。

用自然语言告诉它你想怎么修，它理解后调用一系列本地图像处理工具，帮你完成人像修饰、体型修饰等工作。

## 设计理念

- **大模型是大脑，不是画笔**：大模型负责理解「把脸修瘦、皮肤磨光滑」这类需求，并调度工具；真正修图的是本地 CV 算法。
- **本地优先**：常规修饰不依赖网络、不上传原图，隐私安全、无按次成本。
- **对话式交互**：面向非专业用户，用大白话就能修图，右侧实时预览。

## 快速开始（一键启动）

**双击项目根目录的 `Truffle.bat`** 即可启动（控制台会短暂出现，随后自动关闭）。

- 首次运行会自动创建运行环境并安装依赖（约 1~3 分钟，仅此一次，此时会显示进度窗口），完成后自动打开软件；
- 之后每次双击都是秒开，控制台自动关闭；
- 启动后直接进入项目加载页；大模型对话默认关闭，只使用本地风格策略。
- 在项目页新建或打开项目后才会进入主界面；关闭主界面会保存并回到项目页。

> 前提：本机已安装 Python 3.10+（安装时勾选 “Add Python to PATH”）。若未安装，启动器会给出提示。
> 若软件无窗口启动失败，错误会记录在 `%APPDATA%\Truffle\error.log`。

### 开发者模式启动（源码运行）

改完代码重启即可生效，适合边改边调试。首次使用前先确保 `.venv` 已准备好（双击过 `Truffle.bat` 即可）：

```bat
rem 打开应用窗口（带控制台输出，便于看报错）
scripts\run.bat

rem 无头冒烟自检：offscreen 运行后自动退出，没崩溃即通过，并打印 error.log
scripts\run.bat -Headless
```

也可以直接双击 `scripts\run.bat`。

手动方式（自己建环境、装依赖、启动）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.\.venv\Scripts\python.exe run.py
```

排错：窗口没出现或启动失败，看 `%APPDATA%\Truffle\error.log`；设置环境变量 `TRUFFLE_DEBUG=1` 会额外写 `debug.log`（导入诊断）；`TRUFFLE_ALLOW_MULTI=1` 可绕过单实例限制，方便同时开多个调试窗口。

## 项目

启动后直接进入项目加载页，选择风格后即可一键修图。

- 新建项目只填名称，默认保存到 `文档\Truffle Projects`（可在设置中改）；
- 项目是单个 `.truffle` 文件，图片会复制进项目，移动/分享项目不依赖原图；
- 每张图片独立保存图层、历史/操作树、参数、选区和变换；
- 左侧「风格栏」选风格 → 应用到当前图片，或一键应用到项目全部图片；参数由本地策略按图计算，不套固定参数。
- 自动分析人脸/人体比例：按风格计算瘦脸、大眼、瘦腰、长腿等参数；成套图会统一肤色、对比、脸型与身材基准。
- 大模型接口保留但默认关闭，未来需要回退时可通过配置开启。
- 自动保存默认每 60 秒一次（可在设置中调整或关闭），`Ctrl+S` 手动保存；
- 关闭主窗口会保存并回到项目页；项目页删除项目会移到回收站；
- 支持导入 `.truffle`、搜索/排序、卡片/列表视图、封面设置；`.truffle` 可注册为文件类型，双击直接打开。

### 配置大模型

在软件内「设置 → 大模型配置」填写，支持任意 OpenAI 兼容服务（OpenAI、DeepSeek、通义、Kimi、智谱、Ollama 等），只改「接口地址」和「模型名称」即可。
配置保存在 `%APPDATA%\Truffle\config.json`，完全由软件自身读写。

## 文档

- [架构设计](docs/architecture.md)
- [开发路线图](docs/roadmap.md)
- [打包与发布](docs/packaging.md)
- [项目化工作区需求](specs/SPEC-001-project-system/requirements.md)
- [AI 修图 Agent 设计](specs/SPEC-002-ai-agent/requirements.md)

## 打包发布（发给终端用户）

终端用户只需一个安装包，无需装 Python：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

- 先打出绿色版到 `dist\Truffle\`；
- 装了 [Inno Setup 6](https://jrsoftware.org/isdl.php) 后自动生成安装包 `dist\installer\Truffle-Setup-<版本>.exe`。
- 详见 [打包与发布](docs/packaging.md)。

## 离线自检

不配置大模型也能验证修图引擎是否正常：

```powershell
.\.venv\Scripts\python.exe scripts\selftest.py
# 或用自己的照片
.\.venv\Scripts\python.exe scripts\selftest.py "C:\path\your.jpg"
```

## 风格离线评估

用一组本地图片对一键风格做可重复评估，不改代码、不调用大模型：

```powershell
.\.venv\Scripts\python.exe scripts\eval_styles.py images\ --style all --out eval.csv
```

输出每张图的风格距离（前/后）、自然度、伪影数、耗时，便于比较风格版本和工具改动。

## 当前状态

已完成 M0 脚手架，并补齐 Photoshop 式基础文档能力：

- 画布缩放/平移（Alt+滚轮缩放、Space 拖动平移、Ctrl+0/1）；
- 矩形/椭圆/套索/多边形/魔棒选区，支持羽化、加/减/交叉；
- 多图层：显隐、顺序、不透明度、混合模式、图层蒙版、复制/合并/拼合；
- 自由变换（Ctrl+T）：移动、缩放、旋转、斜切/透视、翻转；
- 项目化工作区：`.truffle` 单文件项目、项目加载页、每图独立历史、项目级 AI 对话、自动保存、封面与最近项目。
- PS 对齐快捷键（选区、图层、撤销/重做、变换等）。

AI 修饰工具仍作用于**当前活动图层**。完整路线见 [开发路线图](docs/roadmap.md)。

## 许可证

待定。
