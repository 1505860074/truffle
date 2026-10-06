# Truffle 手动测试文档

## 📋 文档说明

- 用途：供你在本机**手动执行并验收** Truffle 当前版本（M0/M1 骨架 + 5 个修饰工具 + 对话闭环）。
- 体例：按「第 0~3 层」由浅入深组织，每层给出**可直接复制的命令**、**预期结果**、**记录栏**。
- 约定：所有命令在项目根目录 `C:\Users\15058\Repos\truffle` 执行；控制台请先切到 UTF-8。
- 禁忌：不要把 `.env`（含真实 Key）提交进 git；仅在本地填写。

> 约定目录：`<ROOT> = C:\Users\15058\Repos\truffle`
> 约定解释器：`<PY> = <ROOT>\.venv\Scripts\python.exe`

---

## 第 0 层 · 环境自检（必做，约 10 秒）

打开 PowerShell，执行：

```powershell
chcp 65001 | Out-Null                      # 让中文正常显示
Set-Location <ROOT>
<PY> -c "import numpy, cv2, mediapipe, PySide6, openai; print('numpy', numpy.__version__); print('cv2', cv2.__version__); print('mediapipe', mediapipe.__version__); print('PySide6', PySide6.__version__); print('依赖全部就绪')"
```

**预期**：打印各版本号并以 `依赖全部就绪` 结尾，无 `ModuleNotFoundError`。
正常版本组合应为：`numpy 1.26.x`、`cv2 4.11.x`、`mediapipe 0.10.21`。

| 检查项 | 结果（你填） |
| --- | --- |
| 是否全部导入成功 | ☐ 是 / ☐ 否 |

若失败，执行修复（先解压后重装，避免 opencv 双包冲突）：

```powershell
<PY> -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

---

## 第 1 层 · 离线引擎自检（不需要 API Key，约 15 秒）

验证「CV 分析 + 5 个修饰工具」本身是否工作。

```powershell
<PY> scripts\selftest.py
```

**预期**：
- 打印 `检测到人脸数`、`皮肤区域占比`
- 5 个工具（skin_smooth / whiten / remove_blemish / slim_face / enlarge_eyes）逐条显示 `生效`
- 结尾 `5/5 个工具正常执行`
- 生成目录 `out_selftest\`（5 张结果图）

**用你自己的照片测**（强烈建议）：

```powershell
<PY> scripts\selftest.py "C:\路径\你的照片.jpg"
```

然后打开 `out_selftest\` 下的图片逐张比对：

| 工具 | 期望肉眼效果 | 你看到的效果 |
| --- | --- | --- |
| skin_smooth | 皮肤变光滑、噪点减少，五官不变糊 | |
| whiten | 肤色更白净透亮 | |
| remove_blemish | 小斑点/痘痘被淡化 | |
| slim_face | 脸型变窄（合成图可能无明显人脸，需真人照） | |
| enlarge_eyes | 眼睛略微放大 | |

> 注意：`slim_face` / `enlarge_eyes` 依赖关键点，**必须是有清晰人脸的真人照**才看得到效果。

| 检查项 | 结果（你填） |
| --- | --- |
| 5 个工具是否都执行成功 | ☐ 是 / ☐ 否 |
| 效果是否自然（无严重伪影） | ☐ 自然 / ☐ 有瑕疵：______ |

---

## 第 2 层 · 图形界面与基础操作（不需要 API Key）

### 2.1 启动

```powershell
<PY> run.py
```

**预期**：弹出窗口「Truffle · AI 修图」，左侧对话区、右侧深灰画布，底部状态栏提示 `就绪 · 请先在「设置」中配置大模型 API`。

| 用例 | 步骤 | 预期结果 | 结果 |
| --- | --- | --- | --- |
| T2.1 启动 | 运行 `run.py` | 窗口正常打开，无报错 | ☐ |
| T2.2 打开图片 | 菜单「文件 → 打开图片…」选一张人像 | 画布居中显示图片，对话区出现「已打开：xxx」 | ☐ |
| T2.3 未配 API 提示 | 未配置 Key 时，在输入框发「磨皮」 | 提示「请先在设置里配置大模型 API Key」，弹设置窗 | ☐ |
| T2.4 无图提示 | 不打开图片直接发指令 | 提示「请先打开一张图片」 | ☐ |
| T2.5 保存 | 菜单「文件 → 另存为…」 | 生成图片文件，对话区提示已保存路径 | ☐ |
| T2.6 撤销/重做 | 见第 3 层操作后按 `Ctrl+Z` / `Ctrl+Y` | 画面在修改前后切换 | ☐ |
| T2.7 恢复原图 | 菜单「编辑 → 恢复原图」 | 画面回到最初打开的图 | ☐ |
| T2.8 关闭 | 关闭窗口 | 进程正常退出，无报错 | ☐ |

---

## 第 3 层 · 端到端对话修图（需要大模型 API Key）

### 3.1 配置 API（二选一）

**方式 A（推荐，界面里填）**：菜单「设置 → 大模型配置…」填写：
- 接口地址：如 `https://api.openai.com/v1`（或 DeepSeek/通义/Kimi/智谱/Ollama 的兼容地址）
- API Key、模型名称（如 `gpt-4o-mini`）

保存后写入 `%APPDATA%\Truffle\config.json`。

**方式 B（用 .env）**：

```powershell
Copy-Item .env.example .env
notepad .env    # 填入 TRUFFLE_LLM_BASE_URL / TRUFFLE_LLM_API_KEY / TRUFFLE_LLM_MODEL 后保存
```

### 3.2 对话测试用例

打开一张**清晰的真人半身照**，依次输入下列指令，观察右侧画布是否实时变化：

| 用例 | 输入指令 | 预期 | 结果 |
| --- | --- | --- | --- |
| T3.1 磨皮 | 「帮我把皮肤磨光滑一点」 | 皮肤变光滑，AI 回复一句确认 | ☐ |
| T3.2 美白 | 「肤色提亮一点」 | 肤色变白净 | ☐ |
| T3.3 瘦脸 | 「脸修瘦一点」 | 脸型变窄 | ☐ |
| T3.4 大眼 | 「眼睛放大一点」 | 眼睛变大 | ☐ |
| T3.5 祛斑 | 「把脸上的痘痘去掉」 | 斑点变淡 | ☐ |
| T3.6 组合 | 「脸瘦一点，皮肤磨光滑，再美白一下」 | AI 连续调用多个工具，全部生效 | ☐ |
| T3.7 闲聊 | 「你好呀」 | AI 只回复，不修改图片 | ☐ |
| T3.8 越界请求 | 「帮我换个背景」 | AI 说明暂不支持，不误调用工具 | ☐ |
| T3.9 撤销链路 | 上述操作后连续 `Ctrl+Z` | 逐步回退每一步修改 | ☐ |
| T3.10 保存成品 | 修完后「另存为…」 | 保存的图与画布一致 | ☐ |

> 若某条指令 AI 没调用工具：先确认模型支持 function calling（部分小模型不支持）。

| 检查项 | 结果（你填） |
| --- | --- |
| AI 是否理解并调用了正确工具 | ☐ 是 / ☐ 否：______ |
| 效果是否达到「自然可用」 | ☐ 是 / ☐ 否：______ |
| 是否出现程序卡死/崩溃 | ☐ 否 / ☐ 是：______ |

---

## 问题记录模板

发现问题时按下表记录，反馈给我即可定位：

| 编号 | 所在用例 | 复现步骤 | 实际结果 | 期望结果 | 截图/报错 |
| --- | --- | --- | --- | --- | --- |
| 1 | 如 T3.3 | | | | |

---

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 控制台中文乱码 | 控制台非 UTF-8 | 先执行 `chcp 65001` |
| `ModuleNotFoundError` | 依赖未装/装错环境 | 用 `<PY> -m pip install -r requirements.txt` |
| 提示 Key 未配置 | 未填 API | 见 3.1 |
| 瘦脸/大眼无变化 | 图里没检测到人脸 | 换清晰正脸照，或看 selftest 打印的人脸数 |
| 调用 API 报错 | base_url/model 不对 | 核对服务商的 OpenAI 兼容地址与模型名 |
| 效果过重/不自然 | 强度偏高 | 让 AI 说「弱一点」，或后续加手动滑块（M3） |
