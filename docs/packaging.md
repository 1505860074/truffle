# Truffle 打包与发布

## 📋 文档说明

- 用途：说明如何把 Truffle 打包成**可发布的 Windows 安装包**，以及体积优化与裁剪策略。
- 体例：先给「一键流程」，再给「产物说明 / 裁剪清单 / 后续优化 / 常见问题」。
- 约定：所有命令在项目根目录执行；发布相关文件统一放在 `packaging/`。
- 禁忌：不要手动删 `dist/Truffle` 里的文件来减体积——要减请改 `packaging/Truffle.spec` 的裁剪清单，并重新打包验证。

## 目标

终端用户**不需要安装 Python、不需要命令行**，只需收到一个 `Truffle-Setup-x.x.x.exe`，双击安装、开始菜单出图标、首启弹 API 配置即可使用。

## 一键流程

```mermaid
flowchart LR
    A[源码] --> B["PyInstaller (Truffle.spec)"]
    B --> C["dist/Truffle 绿色版"]
    C --> D["Inno Setup (installer.iss)"]
    D --> E["dist/installer/Truffle-Setup-x.x.x.exe"]
    E --> F[发给用户]
```

图 1：发布流水线

执行（**打包唯一入口**，每次运行自动递增版本号）：

```powershell
# 默认：在上次版本基础上 patch +1（如 0.0.1 -> 0.0.2）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1

# 递增次版本 / 主版本
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Bump minor
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Bump major

# 强制指定版本（仍会写回并作为下次基准）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Version 1.0.0
```

版本规则：以 `pyproject.toml` 的 `version` 作为「上次打包版本」，每次打包自动 +1；打包前写回（含 `src/truffle/__init__.py`，使 exe 内嵌/显示新版本），**打包失败自动回滚**。因此不要手动改版本号，交给脚本管理。

脚本会：
1. 读取并递增版本号，写回 `pyproject.toml` 与 `src\truffle\__init__.py`；
2. 检查/安装 `pyinstaller`；
3. 用 `packaging\Truffle.spec` 打出绿色版到 `dist\Truffle\`；
4. 若检测到 Inno Setup，则用 `packaging\installer.iss` 生成安装包 `dist\installer\Truffle-Setup-<版本>.exe`（未安装则跳过并提示）。

## 前置条件

- 已初始化虚拟环境（双击过 `Truffle.bat` 或手动建过 `.venv`）；
- 制作安装包需要 **Inno Setup 6**：https://jrsoftware.org/isdl.php （装完后重跑 `build.ps1` 即可）。
  脚本会自动从 PATH、常见路径、注册表三处探测 `ISCC.exe`，**装在任意盘符都能识别**。

## 产物说明

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| 绿色版（onedir） | `dist\Truffle\` | 免安装，双击 `Truffle.exe` 即可跑；用于测试 |
| 安装包 | `dist\installer\Truffle-Setup-<版本>.exe` | 正式发给终端用户 |

安装包为**按用户安装**（`PrivilegesRequired=lowest`），不弹 UAC，默认装到 `%LOCALAPPDATA%\Programs\Truffle`，自动创建开始菜单与可选桌面快捷方式。

## 升级覆盖机制

新版本安装包在旧版本之上安装时，**保证干净覆盖**，不会残留旧文件：

| 机制 | 配置 | 作用 |
| --- | --- | --- |
| 同一 AppId | `[Setup] AppId` 固定 | 识别为同一程序，装回原目录，不另装一份 |
| 同名文件覆盖 | `[Files] ... ignoreversion` | 无论新旧，直接覆盖 |
| 清空旧运行时 | `[InstallDelete]` 删 `{app}\_internal` 与主程序 | 清除上一版独有、这一版已不存在的文件 |
| 关闭占用 | `CloseApplications=yes` | 升级前关闭正在运行的旧程序，避免文件被占用 |
| 版本单一来源 | `build.ps1` 读 `pyproject.toml` 的 `version` | 发版只改一处版本号 |

> 用户数据（大模型 API 配置）在 `%APPDATA%\Truffle\config.json`，**不在**安装目录，升级覆盖不会影响。
>
> 实测：伪造旧版残留文件后重装，`_internal` 内残留被清除；安装目录根下手动放的其它文件按 Inno 默认行为保留。

## 应用图标

图标由 `scripts/make_icon.py` 生成（线框极简 · 深棕 + 金 · 松露），产物在 `assets/`：

- `truffle.ico`：多尺寸（16~256），用于 exe 内嵌图标、运行时窗口图标、安装包图标；
- `truffle.svg` / `truffle_512.png`：矢量源与预览。

重新生成：`.\.venv\Scripts\python.exe scripts\make_icon.py`。改颜色/形状改脚本里的配色常量与 `truffle_path()` 即可。

## 体积构成与优化（当前约 344MB）

| 部分 | 体积 | 说明 |
| --- | --- | --- |
| cv2 | ~96MB | `cv2.pyd` 本身 86MB 是主要来源，暂无法裁剪 |
| mediapipe | ~75MB | 含必需的 `opencv_world3410.dll`（53MB，**不可删**）与 face 模型 |
| PySide6 | ~70MB | 已去掉 WebEngine/Quick/Qml/Pdf/翻译 |
| numpy + numpy.libs | ~41MB | 含 OpenBLAS |

已排除（见 `Truffle.spec`）：

- **媒体库**：`jax` `jaxlib` `scipy` `matplotlib` `PIL`（mediapipe 声明依赖，但 face_mesh 用不到）；
- **Qt 模块**：WebEngine / Qml / Quick / 3D / Charts / Multimedia / Pdf / Sql / Test 等，及翻译文件；
- **mediapipe 无用模型**：hand / pose / palm / selfie / objectron（只用 face_mesh，保留 face_detection、face_landmark、iris_landmark）；
- **cv2 ffmpeg dll**（约 27MB）：视频功能（M4）上线前去掉，**上视频前需要在 spec 里移除该裁剪项**。

> 关键教训：`mediapipe\python\opencv_world3410.dll`（53MB）是 `_framework_bindings` 的运行时依赖，**删了 mediapipe 直接 import 失败**，已验证不可裁。

## 后续可选的进一步优化

1. **自定义精简 OpenCV**：只编 core/imgproc/photo/objdetect，可把 86MB 的 `cv2.pyd` 降到 ~10MB（收益最大，但工作量大）。
2. **换更轻的人脸关键点方案**：用小型 ONNX 模型 + onnxruntime 替代 mediapipe（省掉 75MB + 那个 53MB dll）。
3. **Nuitka**：编译式打包，启动更快、体积略小，但对 mediapipe 兼容坑多，留待后期评估。

## 代码签名（避免 SmartScreen 拦截）

未签名的 exe，用户首次运行会看到「未知发布者」警告。正式发布建议购买代码签名证书（OV 约千元/年，EV 更贵但可即时获得信誉），用 `signtool` 对 `Truffle.exe` 和安装包签名。可在 `build.ps1` 末尾追加签名步骤。

## Windows 兼容性注意

- 目标架构 `x64compatible`；
- 保留了 `opengl32sw.dll`（软件渲染兜底），以兼容无独显/虚拟机环境；
- Qt 为 LGPL，动态链接 + 随包附带许可证即可商用。

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `build.ps1` 提示未找到虚拟环境 | 没初始化 `.venv` | 先双击 `Truffle.bat` |
| 未生成安装包 | 未装 Inno Setup | 安装 Inno Setup 6 后重跑 |
| 打出的程序闪退 | 裁剪过度/依赖缺失 | 看 `%APPDATA%\Truffle\error.log`，回退 `Truffle.spec` 对应裁剪项 |
| 体积仍偏大 | `cv2.pyd` + `opencv_world3410.dll` | 见「后续优化」 |
| 用户被 SmartScreen 拦截 | 未签名 | 见「代码签名」 |
