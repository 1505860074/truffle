r"""生成 Truffle 应用图标（线框极简 · 深棕 + 金 · 纯松露）。

产物（assets/）：
  - truffle.svg        矢量源文件（可编辑）
  - truffle_512.png    预览大图
  - truffle.ico        多尺寸图标（16~256），供 exe 与安装包使用

用法： .\.venv\Scripts\python.exe scripts\make_icon.py
"""

from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ASSETS.mkdir(exist_ok=True)

# 配色
BG_TOP = "#3A2716"       # 背景深棕（亮）
BG_BOTTOM = "#231507"    # 背景深棕（暗）
BODY_LIGHT = "#5E4227"   # 松露主体（亮）
BODY_DARK = "#33210F"    # 松露主体（暗）
GOLD = "#E7C87E"         # 描边金
GOLD_SOFT = "#D9B96A"    # 纹理金


def truffle_path(cx: float, cy: float, r: float, n: int = 300) -> str:
    """用低频、非对称的半径扰动，得到一颗有机、凹凸的松露轮廓（避免规则星形）。"""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = r * (
            1
            + 0.075 * math.sin(2 * t + 1.1)     # 整体不对称
            + 0.055 * math.sin(3 * t + 0.2)     # 大起伏，像块菌的疙瘩
            + 0.040 * math.sin(6 * t + 2.6)     # 中起伏
            + 0.020 * math.sin(11 * t + 0.7)    # 细微颗粒
        )
        pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t) * 0.90))
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def texture(cx: float, cy: float, r: float) -> str:
    """平面设计：更大、间距更大的竖向大眼睛；雀斑由眼睛位置推导，偏外侧分布。"""
    # ---- 先确定眼睛 ----
    eye_w = 0.185 * r          # 眼睛宽（窄）
    eye_h = 0.550 * r          # 眼睛高（加大尺寸）
    eye_rx = 0.065 * r         # 圆角
    gap = 0.285 * r            # 两眼中心间距的一半（进一步加大眼距）
    shift_x = 0.085 * r        # 整体向右偏移（看向右侧）
    eye_cy = cy - 0.06 * r     # 略高于中心
    left_eye_cx = cx + shift_x - gap
    right_eye_cx = cx + shift_x + gap

    elements = []

    # ---- 再由眼睛位置确定雀斑 ----
    # 偏向眼睛的外侧下方（不是正下方）；左眼一组间距略大于右眼一组
    freckle_color = "#F1E2A6"
    left_offsets = [
        (-0.13, 0.18, 0.018),
        (-0.27, 0.22, 0.016),
        (-0.41, 0.20, 0.015),
        (-0.18, 0.36, 0.016),
        (-0.32, 0.41, 0.014),
        (-0.46, 0.34, 0.013),
    ]
    right_offsets = [
        (0.12, 0.18, 0.018),
        (0.23, 0.22, 0.016),
        (0.34, 0.20, 0.015),
        (0.16, 0.36, 0.016),
        (0.27, 0.41, 0.014),
        (0.38, 0.34, 0.013),
    ]
    for ecx, offsets in ((left_eye_cx, left_offsets), (right_eye_cx, right_offsets)):
        for dx, dy, sr in offsets:
            x = ecx + dx * r
            y = eye_cy + dy * r
            elements.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{sr * r:.1f}" '
                f'fill="{freckle_color}" opacity="0.85"/>'
            )

    # ---- 眼睛 ----
    for ecx in (left_eye_cx, right_eye_cx):
        x = ecx - eye_w / 2
        y = eye_cy - eye_h / 2
        elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{eye_w:.1f}" height="{eye_h:.1f}" '
            f'rx="{eye_rx:.1f}" ry="{eye_rx:.1f}" fill="{GOLD}"/>'
        )
    return "\n      ".join(elements)


def build_svg(size: int = 512) -> str:
    cx, cy = size / 2, size * 0.54
    r = size * 0.305
    path = truffle_path(cx, cy, r)
    tex = texture(cx, cy, r)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG_TOP}"/>
      <stop offset="1" stop-color="{BG_BOTTOM}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.32" r="0.75">
      <stop offset="0" stop-color="#6B4A28" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="body" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="{BODY_LIGHT}"/>
      <stop offset="1" stop-color="{BODY_DARK}"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{size}" height="{size}" rx="{size*0.225:.0f}" fill="url(#bg)"/>
  <rect x="0" y="0" width="{size}" height="{size}" rx="{size*0.225:.0f}" fill="url(#glow)"/>
  <path d="{path}" fill="url(#body)" stroke="{GOLD}" stroke-width="{size*0.038:.1f}" stroke-linejoin="round"/>
  {tex}
</svg>
'''


def render_png(svg_text: str, size: int, out_path: Path) -> None:
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    image.save(str(out_path))


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])

    svg = build_svg(512)
    (ASSETS / "truffle.svg").write_text(svg, encoding="utf-8")

    render_png(svg, 512, ASSETS / "truffle_512.png")

    # 由 512 大图生成多尺寸 ico
    base = Image.open(ASSETS / "truffle_512.png").convert("RGBA")
    base.save(
        ASSETS / "truffle.ico",
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)],
    )
    # 256 预览（安装包会用到的尺寸）
    render_png(svg, 256, ASSETS / "truffle_256.png")

    print("已生成：")
    for name in ("truffle.svg", "truffle_512.png", "truffle_256.png", "truffle.ico"):
        p = ASSETS / name
        print(f"  {p}  ({p.stat().st_size} bytes)")
    _ = app


if __name__ == "__main__":
    main()
