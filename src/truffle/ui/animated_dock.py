"""固定侧栏 + 平移显隐动画（仿 VSCode）。

- 侧栏不可拖动/浮动/关闭（`NoDockWidgetFeatures`），位置固定；
- 显示/隐藏动画通过自定义属性 `animSize` 每帧调用 `QMainWindow.resizeDocks`，
  真正改变侧栏尺寸（只改 maximumWidth 不会生效，会导致显示后变得很窄）；
- 隐藏时记住实际尺寸，显示时复原。
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow

_DURATION = 180


class AnimatedDock(QDockWidget):
    def __init__(self, title: str, horizontal: bool = True, parent=None) -> None:
        super().__init__(title, parent)
        self._horizontal = horizontal
        self._target = 360
        self._saved = 360      # 隐藏前记住的尺寸，显示时复原
        self._anim_size = 360
        self._anim: QPropertyAnimation | None = None
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
            | Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
        )
        if horizontal:
            self.setMinimumWidth(0)
        else:
            self.setMinimumHeight(0)

    # ---------- 自定义动画属性 ----------
    def _main_window(self) -> QMainWindow | None:
        w = self.parentWidget()
        while w is not None:
            if isinstance(w, QMainWindow):
                return w
            w = w.parentWidget()
        return None

    def _orientation(self) -> Qt.Orientation:
        return Qt.Horizontal if self._horizontal else Qt.Vertical

    def _get_anim_size(self) -> float:
        return float(self._anim_size)

    def _set_anim_size(self, value: float) -> None:
        self._anim_size = float(value)
        main = self._main_window()
        if main is not None:
            main.resizeDocks([self], [max(0, int(round(value)))], self._orientation())

    animSize = Property(float, _get_anim_size, _set_anim_size)

    # ---------- 对外 ----------
    def set_target(self, size: int) -> None:
        self._target = size
        self._saved = size
        self._anim_size = size

    def current_size(self) -> int:
        return self.width() if self._horizontal else self.height()

    def saved_size(self) -> int:
        return self._saved

    def is_shown(self) -> bool:
        return self.isVisible() and self.current_size() > 1

    def slide_show(self) -> None:
        self.setVisible(True)
        self._anim_size = 0
        self._set_anim_size(0)
        self._run(0, self._saved, self._finish_show, QEasingCurve.OutCubic)

    def slide_hide(self) -> None:
        current = self.current_size()
        if current > 1:  # 记住隐藏前的实际尺寸（用户可能拖过分隔条）
            self._saved = current
        self._run(current, 0, self._finish_hide, QEasingCurve.InCubic)

    # ---------- 内部 ----------
    def _run(self, start: float, end: float, on_done, curve) -> None:
        anim = QPropertyAnimation(self, b"animSize", self)
        anim.setDuration(_DURATION)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setEasingCurve(curve)
        anim.finished.connect(on_done)
        self._anim = anim
        anim.start()

    def _finish_show(self) -> None:
        self._anim_size = self._saved
        self._set_anim_size(self._saved)

    def _finish_hide(self) -> None:
        self.setVisible(False)
        self._anim_size = self._saved
