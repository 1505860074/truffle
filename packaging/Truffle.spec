# -*- mode: python ; coding: utf-8 -*-
"""Truffle 的 PyInstaller 打包配置（onedir）。

用法（在项目根目录执行）：
    python -m PyInstaller packaging/Truffle.spec --noconfirm --clean \
        --distpath dist --workpath build/work

要点：
- 收集 mediapipe / cv2 的原生库与模型数据；
- 激进排除体积大户（jax/jaxlib/scipy/matplotlib、无用 Qt 模块）与用不到的资源；
- 窗口程序（无控制台）。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent          # packaging/ 的上一级 = 项目根
SRC = str(ROOT / "src")

# ---------- 收集原生库与数据 ----------
datas, binaries, hiddenimports = [], [], []
for package in ("mediapipe", "cv2"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# ---------- 资源裁剪 ----------
# 只用 face_mesh，用不到这些 solution 的模型文件
MEDIAPIPE_DROP_MODULES = {
    "hand_landmark", "palm_detection", "pose_landmark", "pose_detection",
    "selfie_segmentation", "objectron", "holistic_landmark",
}
# 视频功能（M4）上线前，去掉 opencv 的 ffmpeg 视频编解码 dll（约 27MB）
DROP_BINARIES = {"opencv_videoio_ffmpeg"}   # 前缀匹配
# 用不到的 Qt 动态库（体积优化）
DROP_QT_DLLS = {"qt6quick.dll", "qt6qml.dll", "qt6pdf.dll"}


def _is_pil(name: str) -> bool:
    return name.startswith("pil/") or "/pil/" in name or name.endswith("_imaging.pyd") \
        or name.endswith("_imaging.cp312-win_amd64.pyd")


def _keep_data(entry):
    name = entry[0].replace("\\", "/").lower()
    if "/mediapipe/modules/" in name:
        module = name.split("/mediapipe/modules/", 1)[1].split("/", 1)[0]
        if module in MEDIAPIPE_DROP_MODULES:
            return False
    if "pyside6/translations/" in name:
        return False
    if _is_pil(name):
        return False
    return True


def _keep_binary(entry):
    name = entry[0].replace("\\", "/").lower()
    base = name.rsplit("/", 1)[-1]
    if any(base.startswith(prefix) for prefix in DROP_BINARIES):
        return False
    if base in DROP_QT_DLLS:
        return False
    if _is_pil(name):
        return False
    return True

# ---------- 排除清单（体积优化） ----------
excludes = [
    # mediapipe 声明依赖但 face_mesh 用不到的体积大户
    "jax", "jaxlib", "scipy", "matplotlib", "PIL", "Pillow",
    # 开发/构建工具
    "tkinter", "pytest", "setuptools", "pip", "wheel", "packaging",
    # Qt 中用不到的模块
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# hook（PySide6/cv2 等）会在 Analysis 阶段追加资源，必须在此之后再过滤
a.datas = [d for d in a.datas if _keep_data(d)]
a.binaries = [b for b in a.binaries if _keep_binary(b)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Truffle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Truffle",
)
