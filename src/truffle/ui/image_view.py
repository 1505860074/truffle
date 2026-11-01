"""图像画布：缩放/平移 + 选区 + 裁剪 + 液化 + 自由变换。

交互对齐 Photoshop：
- 滚轮上下平移，Shift+滚轮左右平移，Alt+滚轮以光标为中心缩放；
- 空格+拖动 / 中键拖动平移；Ctrl+0 适合窗口，Ctrl+1 100%；
- 矩形/椭圆/套索/多边形/魔棒选区，Shift 加选、Alt 减选、Shift+Alt 交叉；
- Ctrl+T 自由变换：角点缩放（Shift 等比、Alt 中心、Ctrl 透视/斜切），
  边中点缩放/斜切，框外旋转（Shift 15° 吸附），框内移动；
- Enter 应用，Esc 取消。
"""

from __future__ import annotations

import math

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QToolButton, QWidget

from ..core import selection as sel
from ..core.transform import (
    center_of, flip_quad, quad_from_rect, rect_from_quad, rotate_quad,
    scale_quad, translate_quad, warp_roi,
)
from ..cv.warp import local_push
from . import theme
from .i18n import tr
from .naming import area_name
from .panel_icons import eye_icon
from .watermark import Watermark


def bgr_to_qimage(image: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


def bgra_to_qimage(image: np.ndarray) -> QImage:
    rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    h, w, ch = rgba.shape
    return QImage(rgba.data, w, h, ch * w, QImage.Format_RGBA8888).copy()


class ImageView(QWidget):
    cropApplied = Signal(int, int, int, int)  # x, y, w, h（图像坐标）
    liquifyCommitted = Signal()
    modeChanged = Signal(str)  # view | select | crop | liquify | transform
    compareToggled = Signal(bool)
    selectionChanged = Signal()
    toolRequested = Signal(str)   # move | rect | ellipse | lasso | polygon | wand | crop | transform | hand | zoom
    transformCommitted = Signal(object, object)  # src_rect, dst_quad
    transformCancelled = Signal()
    zoomChanged = Signal(float)
    nudgeRequested = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._array: np.ndarray | None = None
        self._image: QImage | None = None
        self._scaled: QImage | None = None
        self._scaled_key: tuple | None = None
        self._direct_target: tuple[int, int] | None = None

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._mode = "view"
        self._off = (0.0, 0.0)
        self._scale = 1.0
        self._zoom = 1.0
        self._fit = True
        self._center_img = (0.0, 0.0)
        self._pressed = False
        self._last_pos = QPointF(0, 0)
        self._space = False
        self._panning = False

        # 选区
        self._selection: np.ndarray | None = None
        self._sel_contours: list[np.ndarray] = []
        self._sel_bbox: tuple[int, int, int, int] | None = None
        self._sel_tool = "rect"
        self._sel_mode = "new"
        self._feather = 0.0
        self._tolerance = 32
        self._wand_contiguous = True
        self._sel_start: QPoint | None = None
        self._sel_modifiers = Qt.NoModifier
        self._sel_rect: QRect | None = None
        self._lasso: list[tuple[float, float]] = []
        self._poly: list[tuple[float, float]] = []
        self._ants_phase = 0
        self._ants_timer = QTimer(self)
        self._ants_timer.setInterval(120)
        self._ants_timer.timeout.connect(self._advance_ants)

        # 裁剪
        self._crop_rect: QRect | None = None

        # 液化
        self._brush = 80.0
        self._strength = 0.5
        self._liquify_base: np.ndarray | None = None
        self._hover: QPoint | None = None
        self._strokes: list[tuple[float, float, float, float, float, float]] = []
        self._last_pt: tuple[float, float] | None = None

        # 自由变换
        self._tf_src_rect: tuple[int, int, int, int] | None = None
        self._tf_patch: np.ndarray | None = None
        self._tf_base: np.ndarray | None = None
        self._tf_quad: list[tuple[float, float]] = []
        self._tf_start_quad: list[tuple[float, float]] = []
        self._tf_drag = ""
        self._tf_press_pt = (0.0, 0.0)
        self._tf_center = (0.0, 0.0)
        self._tf_start_angle = 0.0
        self._tf_preview: QImage | None = None
        self._tf_preview_off = (0, 0)

        # 水印
        self.watermark = Watermark(
            area_name("canvas"), self, point_size=44, spacing=10,
            alpha=int(theme.current()["watermark_alpha"]),
            color=str(theme.current()["watermark"]),
        )

        # 看原图开关
        self.compare = QToolButton(self)
        self.compare.setCheckable(True)
        self.compare.setIcon(eye_icon(str(theme.current()["accent"]), 18))
        self.compare.setIconSize(QSize(20, 20))
        self.compare.setFixedSize(34, 34)
        self.compare.setToolTip(tr("看原图"))
        self.compare.setCursor(Qt.PointingHandCursor)
        self.compare.toggled.connect(self.compareToggled)
        self._place_compare()

    # ---------- 外观 ----------
    def apply_theme(self) -> None:
        t = theme.current()
        self.watermark.set_color(str(t["watermark"]), int(t["watermark_alpha"]))
        self.compare.setIcon(eye_icon(str(t["accent"]), 18))
        self.compare.setStyleSheet(
            f"QToolButton {{ background: rgba(30,30,30,180); border:1px solid {t['border']}; "
            f"border-radius:6px; }} "
            f"QToolButton:checked {{ background:{t['accent_bg']}; border-color:{t['accent']}; }}"
        )
        self.update()

    def _place_compare(self) -> None:
        m = 12
        self.compare.move(
            self.width() - self.compare.width() - m,
            self.height() - self.compare.height() - m,
        )
        self.compare.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_compare()
        self._recalc_view()
        self.update()

    # ---------- 对外状态 ----------
    def mode(self) -> str:
        return self._mode

    def array(self) -> np.ndarray | None:
        return self._array

    def strokes(self) -> list[tuple[float, float, float, float, float, float]]:
        return list(self._strokes)

    def zoom_percent(self) -> float:
        return self._scale * 100.0

    def set_array(self, image: np.ndarray) -> None:
        old_shape = None if self._array is None else self._array.shape[:2]
        self._array = np.ascontiguousarray(image.copy())
        self._image = bgr_to_qimage(self._array)
        self._scaled = None
        self._scaled_key = None
        new_shape = self._array.shape[:2]
        if old_shape != new_shape:
            self._center_img = (new_shape[1] / 2.0, new_shape[0] / 2.0)
            self._fit = True
            if self._selection is not None and self._selection.shape[:2] != new_shape:
                self._selection = None
                self._rebuild_selection()
        elif self._fit:
            self._recalc_view()
        self.update()

    def clear(self) -> None:
        self._array = None
        self._image = None
        self._scaled = None
        self._mode = "view"
        self._sel_rect = None
        self._selection = None
        self._rebuild_selection()
        self.update()

    # ---------- 缩放 / 平移 ----------
    def _recalc_view(self, keep_center: bool = True) -> None:
        if self._image is None:
            return
        iw, ih = self._image.width(), self._image.height()
        if iw <= 0 or ih <= 0:
            return
        if self._fit:
            self._scale = min(self.width() / iw, self.height() / ih)
            self._zoom = self._scale
            self._center_img = (iw / 2.0, ih / 2.0)
        else:
            self._scale = max(0.01, self._zoom)
            if not keep_center:
                self._center_img = (iw / 2.0, ih / 2.0)
        self._off = (
            self.width() / 2.0 - self._center_img[0] * self._scale,
            self.height() / 2.0 - self._center_img[1] * self._scale,
        )
        if abs(self._scale - getattr(self, "_last_emitted_scale", -1.0)) > 1e-6:
            self._last_emitted_scale = self._scale
            self.zoomChanged.emit(self._scale)
    def fit_to_view(self) -> None:
        self._fit = True
        self._recalc_view()
        self.update()

    def actual_size(self) -> None:
        self._fit = False
        self._zoom = 1.0
        self._recalc_view()
        self.update()

    def zoom_in(self) -> None:
        self.zoom_to(self._scale * 1.25)

    def zoom_out(self) -> None:
        self.zoom_to(self._scale / 1.25)

    def zoom_to(self, scale: float, anchor: QPointF | None = None) -> None:
        if self._image is None:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        ix = (anchor.x() - self._off[0]) / max(self._scale, 1e-6)
        iy = (anchor.y() - self._off[1]) / max(self._scale, 1e-6)
        self._zoom = max(0.01, min(float(scale), 32.0))
        self._fit = False
        self._scale = self._zoom
        self._off = (anchor.x() - ix * self._scale, anchor.y() - iy * self._scale)
        self._center_img = (
            (self.width() / 2.0 - self._off[0]) / self._scale,
            (self.height() / 2.0 - self._off[1]) / self._scale,
        )
        self.zoomChanged.emit(self._scale)
        self.update()

    def _raw_to_image(self, pos: QPointF | QPoint) -> tuple[float, float]:
        x = (float(pos.x()) - self._off[0]) / max(self._scale, 1e-6)
        y = (float(pos.y()) - self._off[1]) / max(self._scale, 1e-6)
        return x, y

    def _to_image(self, pos: QPointF | QPoint, clamp: bool = True) -> tuple[float, float] | None:
        if self._array is None:
            return None
        x, y = self._raw_to_image(pos)
        if clamp:
            h, w = self._array.shape[:2]
            x = min(max(x, 0.0), w - 1)
            y = min(max(y, 0.0), h - 1)
        return x, y

    def _to_view(self, x: float, y: float) -> QPointF:
        return QPointF(self._off[0] + x * self._scale, self._off[1] + y * self._scale)

    # ---------- 选区 ----------
    def set_selection(self, mask: np.ndarray | None) -> None:
        if mask is None:
            self._selection = None
        else:
            h, w = self._array.shape[:2] if self._array is not None else (0, 0)
            mask = np.asarray(mask)
            if h and w and mask.shape[:2] != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            self._selection = mask.astype(np.uint8)
        self._rebuild_selection()
        self.update()
        self.selectionChanged.emit()

    def selection(self) -> np.ndarray | None:
        return self._selection

    def selection_bbox(self) -> tuple[int, int, int, int] | None:
        return self._sel_bbox

    def set_feather(self, value: float) -> None:
        self._feather = max(0.0, float(value))

    def set_tolerance(self, value: int) -> None:
        self._tolerance = max(0, min(255, int(value)))

    def set_wand_contiguous(self, contiguous: bool) -> None:
        self._wand_contiguous = bool(contiguous)

    def set_selection_mode(self, mode: str) -> None:
        if mode in sel.SELECTION_MODES:
            self._sel_mode = mode

    def selection_mode(self) -> str:
        return self._sel_mode

    def selection_tool(self) -> str:
        return self._sel_tool

    def start_select(self, tool: str = "rect") -> None:
        if self._array is None:
            return
        self._mode = "select"
        self._sel_tool = tool if tool in ("rect", "ellipse", "lasso", "polygon", "wand") else "rect"
        self._sel_start = None
        self._sel_rect = None
        self._lasso = []
        self._poly = []
        self._set_cursor()
        self.modeChanged.emit("select")
        self.update()

    def _advance_ants(self) -> None:
        self._ants_phase = (self._ants_phase + 1) % 16
        self.update()

    def _rebuild_selection(self) -> None:
        if self._selection is None or sel.is_empty(self._selection):
            self._selection = None
            self._sel_contours = []
            self._sel_bbox = None
            self._ants_timer.stop()
            return
        self._sel_contours = sel.contours(self._selection)
        self._sel_bbox = sel.bounds(self._selection)
        if not self._ants_timer.isActive():
            self._ants_timer.start()

    def clear_selection(self) -> None:
        self._selection = None
        self._rebuild_selection()
        self.update()
        self.selectionChanged.emit()

    def select_all(self) -> None:
        if self._array is None:
            return
        h, w = self._array.shape[:2]
        self._selection = np.full((h, w), 255, dtype=np.uint8)
        self._rebuild_selection()
        self.update()
        self.selectionChanged.emit()

    def invert_selection(self) -> None:
        if self._array is None:
            return
        if self._selection is None:
            self.select_all()
            return
        self._selection = sel.invert(self._selection)
        self._rebuild_selection()
        self.update()
        self.selectionChanged.emit()

    def move_selection(self, dx: int, dy: int) -> None:
        if self._selection is None:
            return
        h, w = self._selection.shape[:2]
        matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
        self._selection = cv2.warpAffine(
            self._selection, matrix, (w, h), flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
        self._rebuild_selection()
        self.update()
        self.selectionChanged.emit()

    def _finalize_shape(self, shape: np.ndarray, modifiers) -> None:
        mode = self._sel_mode
        if modifiers & Qt.ShiftModifier and modifiers & Qt.AltModifier:
            mode = "intersect"
        elif modifiers & Qt.ShiftModifier:
            mode = "add"
        elif modifiers & Qt.AltModifier:
            mode = "subtract"
        self._selection = sel.combine(self._selection, shape, mode)
        self._rebuild_selection()
        self.selectionChanged.emit()
        self.update()

    def _finish_rect_selection(self, modifiers) -> None:
        if self._array is None or self._sel_rect is None:
            return
        x, y, w, h = self._selection_in_image(self._sel_rect)
        if w < 1 or h < 1:
            self._sel_rect = None
            self.update()
            return
        if self._sel_tool == "ellipse":
            mask = sel.ellipse_mask(self._array.shape[:2], x, y, w, h, self._feather)
        else:
            mask = sel.rect_mask(self._array.shape[:2], x, y, w, h, self._feather)
        self._finalize_shape(mask, modifiers)
        self._sel_rect = None
        self.update()

    def _finish_lasso(self, modifiers) -> None:
        if self._array is None:
            return
        points = self._lasso
        self._lasso = []
        if len(points) >= 3:
            mask = sel.polygon_mask(self._array.shape[:2], points, self._feather)
            self._finalize_shape(mask, modifiers)
        self.update()

    def _finish_polygon(self, modifiers=Qt.NoModifier) -> None:
        if self._array is None or len(self._poly) < 3:
            self._poly = []
            self.update()
            return
        mask = sel.polygon_mask(self._array.shape[:2], self._poly, self._feather)
        self._poly = []
        self._finalize_shape(mask, modifiers)

    def _selection_in_image(self, rect: QRect) -> tuple[int, int, int, int]:
        r = rect.normalized()
        tl = self._to_image(r.topLeft())
        br = self._to_image(r.bottomRight())
        if tl is None or br is None or self._array is None:
            return 0, 0, 0, 0
        x0, y0 = int(round(tl[0])), int(round(tl[1]))
        x1, y1 = int(round(br[0])), int(round(br[1]))
        h, w = self._array.shape[:2]
        x1 = min(max(x1, 0), w)
        y1 = min(max(y1, 0), h)
        return x0, y0, max(0, x1 - x0), max(0, y1 - y0)

    # ---------- 模式 ----------
    def start_crop(self) -> None:
        if self._array is None:
            return
        self._mode = "crop"
        self._sel_start = None
        self._sel_rect = None
        self._set_cursor()
        self.modeChanged.emit("crop")
        self.update()

    def start_liquify(self, radius: float, strength: float) -> None:
        if self._array is None:
            return
        self._mode = "liquify"
        self._brush = float(radius)
        self._strength = float(strength)
        self._liquify_base = self._array.copy()
        self._last_pt = None
        self._strokes = []
        self._set_cursor()
        self.modeChanged.emit("liquify")
        self.update()

    def set_brush(self, radius: float, strength: float) -> None:
        self._brush = float(radius)
        self._strength = float(strength)

    def set_tool_mode(self, tool: str) -> None:
        if tool == "hand":
            self._mode = "hand"
            self._set_cursor()
            self.modeChanged.emit("hand")
        elif tool == "zoom":
            self._mode = "zoom"
            self._set_cursor()
            self.modeChanged.emit("zoom")
        self.update()

    def apply_mode(self) -> None:
        if self._mode == "crop":
            rect = self._selection_in_image(self._sel_rect) if self._sel_rect else (0, 0, 0, 0)
            self._mode = "view"
            self._sel_rect = None
            self._sel_start = None
            self._set_cursor()
            if rect[2] >= 2 and rect[3] >= 2:
                self.cropApplied.emit(*rect)
            else:
                self.modeChanged.emit("view")
            self.update()
        elif self._mode == "liquify":
            self._mode = "view"
            self._liquify_base = None
            self._set_cursor()
            self.liquifyCommitted.emit()
            self.modeChanged.emit("view")
            self.update()
        elif self._mode == "select":
            self._finish_polygon()
            self._mode = "view"
            self._set_cursor()
            self.modeChanged.emit("view")
            self.update()
        elif self._mode == "transform":
            self.commit_transform()

    def cancel_mode(self) -> None:
        if self._mode == "liquify" and self._liquify_base is not None:
            self._array = self._liquify_base.copy()
            self._image = bgr_to_qimage(self._array)
        if self._mode == "transform":
            self._reset_transform()
            self.transformCancelled.emit()
        self._mode = "view"
        self._sel_rect = None
        self._sel_start = None
        self._lasso = []
        self._poly = []
        self._liquify_base = None
        self._last_pt = None
        self._set_cursor()
        self.modeChanged.emit("view")
        self.update()

    # ---------- 自由变换 ----------
    def start_transform(self, src_rect: tuple[int, int, int, int],
                        patch_bgra: np.ndarray, base_bgr: np.ndarray) -> None:
        if self._array is None:
            return
        self._mode = "transform"
        self._tf_src_rect = tuple(int(v) for v in src_rect)
        self._tf_patch = np.ascontiguousarray(patch_bgra)
        self._tf_base = np.ascontiguousarray(base_bgr)
        self._array = self._tf_base
        self._image = bgr_to_qimage(self._array)
        self._scaled = None
        self._tf_quad = quad_from_rect(self._tf_src_rect)
        self._tf_start_quad = list(self._tf_quad)
        self._tf_center = center_of(self._tf_quad)
        self._tf_drag = ""
        self._update_transform_preview()
        self._set_cursor()
        self.modeChanged.emit("transform")
        self.update()

    def _reset_transform(self) -> None:
        self._tf_src_rect = None
        self._tf_patch = None
        self._tf_base = None
        self._tf_quad = []
        self._tf_start_quad = []
        self._tf_preview = None
        self._tf_drag = ""

    def _update_transform_preview(self) -> None:
        if self._tf_patch is None or self._tf_quad is None or self._array is None:
            self._tf_preview = None
            return
        h, w = self._tf_patch.shape[:2]
        local = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
        H, W = self._array.shape[:2]
        roi, x0, y0 = warp_roi(self._tf_patch, local, self._tf_quad, W, H, margin=1)
        self._tf_preview = bgra_to_qimage(roi)
        self._tf_preview_off = (x0, y0)

    def transform_quad(self) -> list[tuple[float, float]]:
        return list(self._tf_quad)

    def flip_transform(self, horizontal: bool, vertical: bool = False) -> None:
        if self._mode != "transform" or not self._tf_quad:
            return
        self._tf_quad = flip_quad(self._tf_quad, horizontal=horizontal, vertical=vertical,
                                  center=self._tf_center)
        self._update_transform_preview()
        self.update()

    def rotate_transform(self, angle: float) -> None:
        if self._mode != "transform" or not self._tf_quad:
            return
        self._tf_quad = rotate_quad(self._tf_quad, angle, self._tf_center)
        self._update_transform_preview()
        self.update()

    def commit_transform(self) -> None:
        if self._mode != "transform" or self._tf_src_rect is None:
            return
        src = self._tf_src_rect
        quad = list(self._tf_quad)
        self._reset_transform()
        self._mode = "view"
        self._set_cursor()
        self.modeChanged.emit("view")
        self.update()
        self.transformCommitted.emit(src, quad)

    def _transform_handles(self) -> list[QPointF]:
        if not self._tf_quad:
            return []
        pts = [self._to_view(x, y) for x, y in self._tf_quad]
        mids = [
            QPointF((pts[0].x() + pts[1].x()) / 2.0, (pts[0].y() + pts[1].y()) / 2.0),
            QPointF((pts[1].x() + pts[2].x()) / 2.0, (pts[1].y() + pts[2].y()) / 2.0),
            QPointF((pts[2].x() + pts[3].x()) / 2.0, (pts[2].y() + pts[3].y()) / 2.0),
            QPointF((pts[3].x() + pts[0].x()) / 2.0, (pts[3].y() + pts[0].y()) / 2.0),
        ]
        return pts + mids

    @staticmethod
    def _point_in_quad(pt: QPointF, pts: list[QPointF]) -> bool:
        if len(pts) != 4:
            return False
        poly = QPolygonF(pts)
        return poly.containsPoint(pt, Qt.OddEvenFill)

    def _hit_transform(self, pos: QPointF) -> str:
        handles = self._transform_handles()
        for i, hp in enumerate(handles):
            if (hp - pos).manhattanLength() <= 9:
                return f"h{i}"
        if self._point_in_quad(pos, [self._to_view(x, y) for x, y in self._tf_quad]):
            return "move"
        return "rotate"

    def _tf_press(self, pos: QPointF) -> None:
        self._tf_drag = self._hit_transform(pos)
        self._tf_press_pt = self._raw_to_image(pos)
        self._tf_start_quad = list(self._tf_quad)
        self._tf_center = center_of(self._tf_start_quad)
        cx, cy = self._tf_center
        self._tf_start_angle = math.degrees(math.atan2(self._tf_press_pt[1] - cy, self._tf_press_pt[0] - cx))

    def _tf_move(self, pos: QPointF, modifiers) -> None:
        if not self._tf_quad or not self._tf_drag:
            return
        x, y = self._raw_to_image(pos)
        dx, dy = x - self._tf_press_pt[0], y - self._tf_press_pt[1]
        start = list(self._tf_start_quad)

        if self._tf_drag == "move":
            self._tf_quad = translate_quad(start, dx, dy)
        elif self._tf_drag == "rotate":
            cx, cy = self._tf_center
            angle = math.degrees(math.atan2(y - cy, x - cx))
            delta = angle - self._tf_start_angle
            if modifiers & Qt.ShiftModifier:
                delta = round(delta / 15.0) * 15.0
            self._tf_quad = rotate_quad(start, delta, self._tf_center)
        else:
            handle = int(self._tf_drag[1:])
            if modifiers & Qt.ControlModifier:
                self._tf_quad = self._tf_free_handle(start, handle, dx, dy)
            else:
                self._tf_quad = self._tf_scale_handle(start, handle, dx, dy, modifiers)
        self._update_transform_preview()
        self.update()

    def _tf_free_handle(self, quad: list[tuple[float, float]], handle: int,
                        dx: float, dy: float) -> list[tuple[float, float]]:
        out = [list(p) for p in quad]
        if handle < 4:
            out[handle][0] += dx
            out[handle][1] += dy
        else:
            a, b = {4: (0, 1), 5: (1, 2), 6: (2, 3), 7: (3, 0)}[handle]
            out[a][0] += dx
            out[a][1] += dy
            out[b][0] += dx
            out[b][1] += dy
        return [(float(x), float(y)) for x, y in out]

    def _tf_scale_handle(self, quad: list[tuple[float, float]], handle: int,
                         dx: float, dy: float, modifiers) -> list[tuple[float, float]]:
        p = [np.array(pt, dtype=np.float64) for pt in quad]
        u = p[1] - p[0]
        v = p[3] - p[0]
        ulen = max(float(np.linalg.norm(u)), 1e-6)
        vlen = max(float(np.linalg.norm(v)), 1e-6)
        uhat, vhat = u / ulen, v / vlen

        if handle < 4:
            anchor = p[(handle + 2) % 4].copy()
            if modifiers & Qt.AltModifier:
                anchor = p[0] * 0 + np.array(self._tf_center)
            dragged = p[handle]
            proj_u = float(np.dot(dragged - anchor, uhat))
            proj_v = float(np.dot(dragged - anchor, vhat))
            new_u = proj_u + float(np.dot(np.array([dx, dy]), uhat))
            new_v = proj_v + float(np.dot(np.array([dx, dy]), vhat))
            sx = new_u / proj_u if abs(proj_u) > 1e-6 else 1.0
            sy = new_v / proj_v if abs(proj_v) > 1e-6 else 1.0
            if modifiers & Qt.ShiftModifier:
                s = max(min(abs(sx), abs(sy)), 0.02)
                sx = math.copysign(s, sx if sx != 0 else 1.0)
                sy = math.copysign(s, sy if sy != 0 else 1.0)
        else:
            a, b = {4: (0, 1), 5: (1, 2), 6: (2, 3), 7: (3, 0)}[handle]
            opposite = {4: 2, 5: 3, 6: 0, 7: 1}[handle]
            opposite_mid = (p[opposite] + p[(opposite + 1) % 4]) / 2.0
            if modifiers & Qt.AltModifier:
                anchor = np.array(self._tf_center)
            else:
                anchor = opposite_mid
            dragged = (p[a] + p[b]) / 2.0
            proj_u = float(np.dot(dragged - anchor, uhat))
            proj_v = float(np.dot(dragged - anchor, vhat))
            if handle in (4, 6):
                sx = 1.0
                new_v = proj_v + float(np.dot(np.array([dx, dy]), vhat))
                sy = new_v / proj_v if abs(proj_v) > 1e-6 else 1.0
            else:
                sy = 1.0
                new_u = proj_u + float(np.dot(np.array([dx, dy]), uhat))
                sx = new_u / proj_u if abs(proj_u) > 1e-6 else 1.0
            if modifiers & Qt.ShiftModifier:
                s = max(min(abs(sx), abs(sy)), 0.02)
                sx, sy = (s, s) if handle in (4, 6) else (s, s)
        sx = max(abs(sx), 0.02) if sx >= 0 else -max(abs(sx), 0.02)
        sy = max(abs(sy), 0.02) if sy >= 0 else -max(abs(sy), 0.02)

        out = []
        for pt in p:
            rel = pt - anchor
            q = anchor + uhat * (float(np.dot(rel, uhat)) * sx) + vhat * (float(np.dot(rel, vhat)) * sy)
            out.append((float(q[0]), float(q[1])))
        return out

    # ---------- 鼠标 ----------
    def _set_cursor(self) -> None:
        if self._space or self._panning or self._mode == "hand":
            self.setCursor(Qt.OpenHandCursor if not self._panning else Qt.ClosedHandCursor)
        elif self._mode in ("select", "crop"):
            self.setCursor(Qt.CrossCursor)
        elif self._mode == "transform":
            self.setCursor(Qt.SizeAllCursor)
        elif self._mode == "zoom":
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if event.button() == Qt.MiddleButton or self._space or self._mode == "hand":
            self._panning = True
            self._last_pos = pos
            self._set_cursor()
            return
        if event.button() != Qt.LeftButton:
            return
        self._pressed = True
        if self._mode == "select":
            self._selection_press(pos, event.modifiers())
        elif self._mode == "crop":
            self._sel_start = pos.toPoint()
            self._sel_rect = QRect(self._sel_start, self._sel_start)
            self.update()
        elif self._mode == "liquify":
            self._last_pt = self._to_image(pos)
        elif self._mode == "transform":
            self._tf_press(pos)
            self._set_tf_cursor(pos)
        elif self._mode == "zoom":
            if event.modifiers() & Qt.AltModifier:
                self.zoom_out()
            else:
                self.zoom_in()

    def _selection_press(self, pos: QPointF, modifiers) -> None:
        if self._array is None:
            return
        self._sel_modifiers = modifiers
        if self._sel_tool == "wand":
            xy = self._to_image(pos)
            if xy is not None:
                mask = sel.wand_mask(
                    self._array, int(xy[0]), int(xy[1]),
                    self._tolerance, contiguous=self._wand_contiguous,
                    feather=self._feather,
                )
                self._finalize_shape(mask, modifiers)
            return
        if self._sel_tool == "polygon":
            xy = self._to_image(pos)
            if xy is not None:
                self._poly.append((float(xy[0]), float(xy[1])))
                self.update()
            return
        if self._sel_tool == "lasso":
            xy = self._to_image(pos)
            self._lasso = [] if xy is None else [(float(xy[0]), float(xy[1]))]
        self._sel_start = pos.toPoint()
        self._sel_rect = QRect(self._sel_start, self._sel_start)
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._panning:
            dx = pos.x() - self._last_pos.x()
            dy = pos.y() - self._last_pos.y()
            self._last_pos = pos
            self._off = (self._off[0] + dx, self._off[1] + dy)
            self._fit = False
            self._zoom = self._scale
            self._center_img = (
                (self.width() / 2.0 - self._off[0]) / self._scale,
                (self.height() / 2.0 - self._off[1]) / self._scale,
            )
            self.update()
            return
        if self._mode == "liquify":
            self._hover = pos.toPoint()
            if self._pressed and self._last_pt is not None and self._array is not None:
                cur = self._to_image(pos)
                if cur is not None:
                    dx = cur[0] - self._last_pt[0]
                    dy = cur[1] - self._last_pt[1]
                    if abs(dx) > 0.01 or abs(dy) > 0.01:
                        self._array = local_push(
                            self._array, cur[0], cur[1], dx, dy, self._brush, self._strength
                        )
                        self._strokes.append((cur[0], cur[1], dx, dy, self._brush, self._strength))
                        self._image = bgr_to_qimage(self._array)
                        self._scaled = None
                        self._last_pt = cur
            self.update()
            return
        if self._mode == "transform":
            self._set_tf_cursor(pos)
            if self._pressed and self._tf_drag:
                self._tf_move(pos, event.modifiers())
            return
        if self._mode in ("crop", "select") and self._pressed and self._sel_start is not None:
            if self._mode == "select" and self._sel_tool == "lasso":
                xy = self._to_image(pos)
                if xy is not None:
                    if not self._lasso or math.hypot(xy[0] - self._lasso[-1][0], xy[1] - self._lasso[-1][1]) >= 1.0:
                        self._lasso.append((float(xy[0]), float(xy[1])))
            else:
                self._sel_rect = QRect(self._sel_start, pos.toPoint())
                if self._mode == "crop":
                    self._crop_rect = self._sel_rect
            self.update()
            return
        if self._mode == "zoom":
            return
        self._set_cursor()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._panning:
            self._panning = False
            self._set_cursor()
            return
        self._pressed = False
        if self._mode == "liquify":
            self._last_pt = None
        elif self._mode == "crop":
            pass
        elif self._mode == "select":
            mods = self._sel_modifiers or event.modifiers()
            if self._sel_tool in ("rect", "ellipse"):
                self._finish_rect_selection(mods)
            elif self._sel_tool == "lasso":
                self._finish_lasso(mods)
        elif self._mode == "transform":
            self._tf_drag = ""

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        if self._mode == "select" and self._sel_tool == "polygon":
            self._finish_polygon(event.modifiers())
        elif self._mode == "transform":
            self.commit_transform()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if event.modifiers() & Qt.AltModifier:
            factor = 1.15 ** (delta / 120.0)
            self.zoom_to(self._scale * factor, event.position())
        elif event.modifiers() & Qt.ShiftModifier:
            self._off = (self._off[0] + delta * 0.8, self._off[1])
            self._fit = False
            self._zoom = self._scale
            self._center_img = (
                (self.width() / 2.0 - self._off[0]) / self._scale,
                (self.height() / 2.0 - self._off[1]) / self._scale,
            )
            self.update()
        else:
            self._off = (self._off[0], self._off[1] + delta * 0.8)
            self._fit = False
            self._zoom = self._scale
            self._center_img = (
                (self.width() / 2.0 - self._off[0]) / self._scale,
                (self.height() / 2.0 - self._off[1]) / self._scale,
            )
            self.update()
        event.accept()

    # ---------- 键盘 ----------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._space = True
            self._set_cursor()
            event.accept()
            return
        if mods & Qt.ControlModifier:
            if key == Qt.Key_T:
                self.toolRequested.emit("transform")
                event.accept()
                return
            if key == Qt.Key_A:
                self.select_all()
                event.accept()
                return
            if key == Qt.Key_D:
                self.clear_selection()
                event.accept()
                return
            if key == Qt.Key_I and mods & Qt.ShiftModifier:
                self.invert_selection()
                event.accept()
                return
            if key == Qt.Key_0:
                self.fit_to_view()
                event.accept()
                return
            if key == Qt.Key_1:
                self.actual_size()
                event.accept()
                return
            if key in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_in()
                event.accept()
                return
            if key == Qt.Key_Minus:
                self.zoom_out()
                event.accept()
                return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._mode == "select" and self._sel_tool == "polygon":
                self._finish_polygon(mods)
            elif self._mode == "transform":
                self.commit_transform()
            else:
                self.apply_mode()
            event.accept()
            return
        if key == Qt.Key_Escape:
            if self._mode == "select" and self._poly:
                self._poly = []
                self.update()
            else:
                self.cancel_mode()
            event.accept()
            return
        if self._mode == "select" and self._sel_tool == "polygon" and key == Qt.Key_Backspace:
            if self._poly:
                self._poly.pop()
                self.update()
            event.accept()
            return
        if key in (Qt.Key_BracketLeft, Qt.Key_BracketRight):
            factor = 1.1 if key == Qt.Key_BracketRight else 1.0 / 1.1
            self._brush = max(2.0, min(4000.0, self._brush * factor))
            self.update()
            event.accept()
            return
        if mods & Qt.ControlModifier:
            super().keyPressEvent(event)
            return
        if key == Qt.Key_V:
            self.toolRequested.emit("move")
        elif key == Qt.Key_M:
            self.toolRequested.emit("ellipse" if mods & Qt.ShiftModifier else "rect")
        elif key == Qt.Key_L:
            self.toolRequested.emit("polygon" if mods & Qt.ShiftModifier else "lasso")
        elif key == Qt.Key_W:
            self.toolRequested.emit("wand")
        elif key == Qt.Key_C:
            self.toolRequested.emit("crop")
        elif key == Qt.Key_B:
            self.toolRequested.emit("liquify")
        elif key == Qt.Key_Z:
            self.toolRequested.emit("zoom")
        elif key == Qt.Key_H:
            self.toolRequested.emit("hand")
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if mods & Qt.ShiftModifier else 1
            dx = -step if key == Qt.Key_Left else step if key == Qt.Key_Right else 0
            dy = -step if key == Qt.Key_Up else step if key == Qt.Key_Down else 0
            if self._mode == "select" and self._selection is not None:
                self.move_selection(dx, dy)
            else:
                self.nudgeRequested.emit(dx, dy)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space = False
            self._set_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()

    # ---------- 绘制 ----------
    def _ensure_scaled(self) -> None:
        if self._image is None:
            self._scaled = None
            self._direct_target = None
            return
        w = max(1, int(round(self._image.width() * self._scale)))
        h = max(1, int(round(self._image.height() * self._scale)))
        key = (id(self._image), w, h)
        if w * h > 120_000_000:
            self._scaled = None
            self._direct_target = (w, h)
            self._scaled_key = key
            return
        self._direct_target = None
        if self._scaled_key == key and self._scaled is not None:
            return
        smoothing = Qt.SmoothTransformation
        self._scaled = self._image.scaled(w, h, Qt.IgnoreAspectRatio, smoothing)
        self._scaled_key = key

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(str(theme.current()["canvas_bg"])))
        if self._image is None:
            painter.setPen(QColor(str(theme.current()["text_dim"])))
            hint = self.rect().adjusted(0, 76, 0, 76)
            painter.drawText(hint, Qt.AlignCenter, tr("打开一张图片开始修图"))
            return

        self._recalc_view()
        self._ensure_scaled()
        x, y = int(round(self._off[0])), int(round(self._off[1]))
        if self._scaled is not None:
            painter.drawImage(x, y, self._scaled)
        elif self._direct_target is not None:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(
                QRectF(self._off[0], self._off[1],
                       self._direct_target[0], self._direct_target[1]),
                self._image,
            )

        # 变换预览
        if self._mode == "transform" and self._tf_preview is not None:
            px = int(round(self._off[0] + self._tf_preview_off[0] * self._scale))
            py = int(round(self._off[1] + self._tf_preview_off[1] * self._scale))
            pw = max(1, int(round(self._tf_preview.width() * self._scale)))
            ph = max(1, int(round(self._tf_preview.height() * self._scale)))
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(QRectF(px, py, pw, ph), self._tf_preview)

        self._paint_selection(painter)
        self._paint_transform(painter)
        self._paint_crop(painter)
        self._paint_liquify(painter)
        self._paint_status(painter)

    def _paint_selection(self, painter: QPainter) -> None:
        if self._mode == "select" and self._sel_rect is not None:
            r = self._sel_rect.normalized()
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#e7c87e"), 1.5, Qt.DashLine))
            if self._sel_tool == "ellipse":
                painter.drawEllipse(r)
            else:
                painter.drawRect(r)
        if self._mode == "select" and self._lasso:
            pts = [self._to_view(px, py) for px, py in self._lasso]
            if len(pts) >= 2:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#e7c87e"), 1.5))
                painter.drawPolyline(QPolygonF(pts))
        if self._mode == "select" and self._poly:
            pts = [self._to_view(px, py) for px, py in self._poly]
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#e7c87e"), 1.5))
            if len(pts) >= 2:
                painter.drawPolyline(QPolygonF(pts))
            painter.setBrush(QColor("#e7c87e"))
            painter.setPen(Qt.NoPen)
            for p in pts:
                painter.drawEllipse(p, 3, 3)

        if self._selection is None or not self._sel_contours:
            return
        pen = QPen(QColor("#ffffff"), 1.0, Qt.CustomDashLine)
        pen.setDashPattern([4, 4])
        pen.setDashOffset(self._ants_phase)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(pen)
        for contour in self._sel_contours:
            pts = [self._to_view(float(px), float(py)) for px, py in contour]
            if len(pts) >= 2:
                painter.drawPolygon(QPolygonF(pts))
        pen2 = QPen(QColor("#111111"), 1.0, Qt.CustomDashLine)
        pen2.setDashPattern([4, 4])
        pen2.setDashOffset(self._ants_phase + 4)
        painter.setPen(pen2)
        for contour in self._sel_contours:
            pts = [self._to_view(float(px), float(py)) for px, py in contour]
            if len(pts) >= 2:
                painter.drawPolygon(QPolygonF(pts))

    def _paint_transform(self, painter: QPainter) -> None:
        if self._mode != "transform" or not self._tf_quad:
            return
        pts = [self._to_view(x, y) for x, y in self._tf_quad]
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#e7c87e"), 1.5))
        painter.drawPolygon(QPolygonF(pts))
        handles = self._transform_handles()
        painter.setPen(QPen(QColor("#e7c87e"), 1.0))
        painter.setBrush(QColor("#1e1e1e"))
        for hp in handles:
            painter.drawRect(QRectF(hp.x() - 4, hp.y() - 4, 8, 8))
        center = self._to_view(*self._tf_center)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(231, 200, 126, 120), 1, Qt.DotLine))
        painter.drawLine(center + QPointF(-8, 0), center + QPointF(8, 0))
        painter.drawLine(center + QPointF(0, -8), center + QPointF(0, 8))

    def _paint_crop(self, painter: QPainter) -> None:
        if self._mode != "crop" or self._sel_rect is None:
            return
        r = self._sel_rect.normalized()
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.setPen(Qt.NoPen)
        outer = self.rect()
        for band in (
            QRect(outer.left(), outer.top(), outer.width(), r.top() - outer.top()),
            QRect(outer.left(), r.bottom(), outer.width(), outer.bottom() - r.bottom()),
            QRect(outer.left(), r.top(), r.left() - outer.left(), r.height()),
            QRect(r.right(), r.top(), outer.right() - r.right(), r.height()),
        ):
            painter.drawRect(band)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#e7c87e"), 2, Qt.DashLine))
        painter.drawRect(r)
        x, y, w, h = self._selection_in_image(r)
        if w > 0 and h > 0:
            painter.setPen(QColor("#f2e6c0"))
            painter.drawText(r.adjusted(4, 4, 0, 0), Qt.AlignTop | Qt.AlignLeft, f"{w} × {h}")

    def _paint_liquify(self, painter: QPainter) -> None:
        if self._mode == "liquify" and self._hover is not None:
            rad = self._brush * self._scale
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(231, 200, 126, 200), 1.5))
            painter.drawEllipse(self._hover, int(rad), int(rad))

    def _paint_status(self, painter: QPainter) -> None:
        parts = [f"{self._scale * 100:.0f}%"]
        if self._pressed and self._mode in ("crop", "select") and self._sel_rect is not None:
            x, y, w, h = self._selection_in_image(self._sel_rect)
            if w > 0 and h > 0:
                parts.append(f"{w} × {h}")
        if self._mode == "transform":
            w, h = rect_from_quad(self._tf_quad)[2:4] if self._tf_quad else (0, 0)
            parts.append(f"变换 {w} × {h}")
        text = "   ".join(parts)
        painter.setPen(QColor(230, 230, 230, 210))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) + 12
        th = fm.height() + 6
        rect = QRectF(8, self.height() - th - 8, tw, th)
        painter.setBrush(QColor(20, 20, 20, 160))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(235, 235, 235, 230))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _set_tf_cursor(self, pos: QPointF) -> None:
        if not self._tf_quad:
            return
        mode = self._hit_transform(pos)
        if mode == "move":
            self.setCursor(Qt.SizeAllCursor)
        elif mode == "rotate":
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.SizeFDiagCursor)
