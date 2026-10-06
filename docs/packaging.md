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

执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

脚本会：
1. 检查/安装 `pyinstaller`；
2. 用 `packaging\Truffle.spec` 打出绿色版到 `dist\Truffle\`；
3. 若检测到 Inno Setup，则用 `packaging\installer.iss` 生成安装包到 `dist\installer\`（未安装则跳过并提示）。

## 前置条件

- 已初始化虚拟环境（双击过 `Truffle.vbs` 或手动建过 `.venv`）；
- 制作安装包需要 **Inno Setup 6**：https://jrsoftware.org/isdl.php （装完后重跑 `build.ps1` 即可）。

## 产物说明

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| 绿色版（onedir） | `dist\Truffle\` | 免安装，双击 `Truffle.exe` 即可跑；用于测试 |
| 安装包 | `dist\installer\Truffle-Setup-<版本>.exe` | 正式发给终端用户 |

安装包为**按用户安装**（`PrivilegesRequired=lowest`），不弹 UAC，默认装到 `%LOCALAPPDATA%\Programs\Truffle`，自动创建开始菜单与可选桌面快捷方式。

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
| `build.ps1` 提示未找到虚拟环境 | 没初始化 `.venv` | 先双击 `Truffle.vbs` |
| 未生成安装包 | 未装 Inno Setup | 安装 Inno Setup 6 后重跑 |
| 打出的程序闪退 | 裁剪过度/依赖缺失 | 看 `%APPDATA%\Truffle\error.log`，回退 `Truffle.spec` 对应裁剪项 |
| 体积仍偏大 | `cv2.pyd` + `opencv_world3410.dll` | 见「后续优化」 |
| 用户被 SmartScreen 拦截 | 未签名 | 见「代码签名」 |
