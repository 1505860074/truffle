"""面板显隐图标（仿 VSCode 布局按钮）：圆角外框 + 被填充的一条边。

- kind: "left" / "right" / "bottom" 对应对话栏 / 参数栏 / 文件库；
- on=True 时把该侧填充为实心（面板可见），on=False 只描边（面板隐藏）。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

def _colors() -> tuple[QColor, QColor]:
    from . import theme

    t = theme.current()
    return QColor(str(t["icon_on"])), QColor(str(t["icon_off"]))


def _draw(kind: str, size: int, color: QColor, filled: bool) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    pen = QPen(color)
    pen.setWidthF(max(1.0, size * 0.075))
    pen.setJoinStyle(Qt.RoundJoin)

    # 外框（圆角矩形描边）
    m = size * 0.10
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    r = size * 0.16
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    p.drawRoundedRect(rect, r, r)

    # 内嵌的「面板」圆角矩形（与外框留一道细缝，仿 VSCode）
    gap = size * 0.07
    inner = rect.adjusted(gap, gap, -gap, -gap)
    ri = size * 0.10
    ratio = 0.52
    if kind == "left":
        strip = QRectF(inner.left(), inner.top(), inner.width() * ratio, inner.height())
    elif kind == "right":
        strip = QRectF(
            inner.right() - inner.width() * ratio, inner.top(), inner.width() * ratio, inner.height()
        )
    else:  # bottom
        strip = QRectF(
            inner.left(), inner.bottom() - inner.height() * ratio, inner.width(), inner.height() * ratio
        )

    if filled:
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(strip, ri, ri)
    else:
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawRoundedRect(strip, ri, ri)
    p.end()
    return pm


def panel_icon(kind: str, on: bool, size: int = 18) -> QIcon:
    on_color, off_color = _colors()
    color = on_color if on else off_color
    icon = QIcon()
    icon.addPixmap(_draw(kind, size, color, filled=on))
    icon.addPixmap(_draw(kind, size * 2, color, filled=on))  # HiDPI
    return icon


def _draw_eye(size: int, color: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(max(1.2, size * 0.085))
    pen.setCapStyle(Qt.RoundCap)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(size * 0.10, size * 0.50)
    path.quadTo(size * 0.50, size * 0.16, size * 0.90, size * 0.50)
    path.quadTo(size * 0.50, size * 0.84, size * 0.10, size * 0.50)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(size * 0.5, size * 0.5), size * 0.13, size * 0.13)
    p.end()
    return pm


def _draw_plus(size: int, color: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(max(1.5, size * 0.11))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    m = size * 0.26
    c = size / 2.0
    p.drawLine(QPointF(m, c), QPointF(size - m, c))
    p.drawLine(QPointF(c, m), QPointF(c, size - m))
    p.end()
    return pm


def eye_icon(color: str = "#e7c87e", size: int = 18) -> QIcon:
    c = QColor(color)
    icon = QIcon()
    icon.addPixmap(_draw_eye(size, c))
    icon.addPixmap(_draw_eye(size * 2, c))
    return icon


def plus_icon(color: str = "#3a2716", size: int = 26) -> QIcon:
    c = QColor(color)
    icon = QIcon()
    icon.addPixmap(_draw_plus(size, c))
    icon.addPixmap(_draw_plus(size * 2, c))
    return icon
