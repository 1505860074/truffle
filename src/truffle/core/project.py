"""项目化工作区：单文件 `.truffle` 的创建、读写、最近项目与封面。

`.truffle` 是 ZIP 容器。打开项目时会安全解压到 `%APPDATA%/Truffle/workspaces/`
下的临时工作区，编辑期间所有图片与状态都读写工作区；保存时再把工作区重新
打包回单文件，因此项目内部不需要引用外部路径。

本模块只依赖 core，不依赖 UI，便于单元测试。
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .. import __version__
from .image_doc import Step
from .layer_doc import LayerDocument
from .layers import Layer, ensure_bgra

SCHEMA = 1
PROJECT_EXT = ".truffle"
MANIFEST = "manifest.json"
CHAT = "chat.json"
MAX_RECENT = 50
COVER_W, COVER_H = 640, 480


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        raise TypeError("ndarray must be encoded before json.dumps")
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def default_project_dir(settings: Any = None) -> Path:
    """默认项目目录：设置里配置优先，否则 `文档/Truffle Projects`。"""
    custom = str(getattr(settings, "project_dir", "") or "").strip()
    if custom:
        path = Path(os.path.expandvars(os.path.expanduser(custom)))
    elif os.environ.get("TRUFFLE_PROJECTS"):
        path = Path(os.environ["TRUFFLE_PROJECTS"])
    elif os.environ.get("TRUFFLE_HOME"):
        path = Path(os.environ["TRUFFLE_HOME"]) / "projects"
    else:
        path = Path.home() / "Documents" / "Truffle Projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recent_store_path() -> Path:
    from ..config import config_dir

    return config_dir() / "projects.json"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ImageEntry:
    id: str
    display_name: str
    source: str
    added_at: str = field(default_factory=_now)
    order: int = 0
    last_edited: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "source": self.source,
            "added_at": self.added_at,
            "order": self.order,
            "last_edited": self.last_edited,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageEntry":
        return cls(
            id=str(data.get("id", "")),
            display_name=str(data.get("display_name", "")),
            source=str(data.get("source", "")),
            added_at=str(data.get("added_at", "")) or _now(),
            order=int(data.get("order", 0) or 0),
            last_edited=str(data.get("last_edited", "")),
        )


@dataclass
class ProjectInfo:
    path: Path
    name: str
    modified: float = 0.0
    cover: bytes | None = None
    missing: bool = False
    error: str = ""
    source: str = "default"


@dataclass
class ImagePayload:
    """内存中某张图片的完整编辑状态。"""

    doc: LayerDocument
    selection: np.ndarray | None = None
    params: Any = None
    view: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 工作区读写
# ---------------------------------------------------------------------------


def _safe_members(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        target = (dest / name).resolve()
        if dest not in target.parents and target != dest:
            raise ValueError(f"项目包含非法路径：{member.filename}")
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"项目包含非法路径：{member.filename}")
    zf.extractall(dest)


def _zip_dir(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
            for path in sorted(src.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(src).as_posix())
        if dst.exists():
            try:
                shutil.copy2(dst, dst.with_name(dst.name + ".bak"))
            except OSError:
                pass
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _encode_png(array: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", array)
    if not ok:
        raise ValueError("无法编码图片")
    return buf.tobytes()


def _decode_png(data: bytes, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    if arr is None:
        raise ValueError("无法解码项目内图片")
    return arr


class _Writer:
    """把一个图片状态写进工作区，并按数组对象去重。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._seen: dict[tuple[int, tuple[int, ...], str], str] = {}
        self._keep: list[np.ndarray] = []

    def write_bytes(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def write_json(self, rel: str, data: Any) -> None:
        _json_dump(self.root / rel, data)

    def write_array(self, array: np.ndarray, rel_dir: str, stem: str) -> str:
        arr = np.asarray(array)
        key = (id(arr), tuple(arr.shape), arr.dtype.str)
        if key in self._seen:
            return self._seen[key]
        self._keep.append(arr)
        if arr.dtype == np.uint8 and arr.ndim in (2, 3):
            rel = f"{rel_dir}/{stem}_{len(self._seen)}.png"
            self.write_bytes(rel, _encode_png(arr))
        else:
            rel = f"{rel_dir}/{stem}_{len(self._seen)}.npy"
            buf = io.BytesIO()
            np.save(buf, arr, allow_pickle=False)
            self.write_bytes(rel, buf.getvalue())
        self._seen[key] = rel
        return rel


def _read_any(root: Path, rel: str) -> np.ndarray:
    path = root / rel
    if path.suffix.lower() == ".npy":
        return np.load(path, allow_pickle=False)
    return _decode_png(path.read_bytes())


def _encode_obj(obj: Any, writer: _Writer, prefix: str) -> Any:
    if isinstance(obj, np.ndarray):
        return {"__ndarray__": writer.write_array(obj, "steps", prefix)}
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _encode_obj(v, writer, f"{prefix}_{k}") for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode_obj(v, writer, f"{prefix}_{i}") for i, v in enumerate(obj)]
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _decode_obj(obj: Any, root: Path) -> Any:
    if isinstance(obj, dict):
        if set(obj.keys()) == {"__ndarray__"}:
            return _read_any(root, str(obj["__ndarray__"]))
        return {k: _decode_obj(v, root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_obj(v, root) for v in obj]
    return obj


def _layer_dict(layer: Layer, writer: _Writer) -> dict[str, Any]:
    data = {
        "id": int(layer.id),
        "name": str(layer.name),
        "image": writer.write_array(layer.image, "layers", f"l{layer.id}"),
        "visible": bool(layer.visible),
        "opacity": float(layer.opacity),
        "blend": str(layer.blend),
        "locked": bool(layer.locked),
        "mask": None,
    }
    if layer.mask is not None:
        data["mask"] = writer.write_array(layer.mask, "layers", f"m{layer.id}")
    return data


def _layer_from_dict(data: dict[str, Any], root: Path) -> Layer:
    image = ensure_bgra(_read_any(root, str(data["image"])))
    mask = None
    if data.get("mask"):
        mask = _read_any(root, str(data["mask"]))
        if mask.ndim == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    return Layer(
        id=int(data.get("id", 1)),
        name=str(data.get("name", "图层")),
        image=image,
        visible=bool(data.get("visible", True)),
        opacity=float(data.get("opacity", 1.0)),
        blend=str(data.get("blend", "normal")),
        mask=mask,
        locked=bool(data.get("locked", False)),
    )


def _limit_history(
    steps: list[Step],
    snapshots: list[tuple[tuple[Layer, ...], int]],
    pointer: int,
    limit: int,
) -> tuple[list[Step], list[tuple[tuple[Layer, ...], int]], int]:
    limit = max(0, min(100, int(limit)))
    if limit == 0:
        return [], [], 0
    if len(steps) <= limit:
        return steps, snapshots, pointer
    start = len(steps) - limit
    return steps[start:], snapshots[start:], max(0, pointer - start)


def _write_image_state(
    project: "Project",
    entry: ImageEntry,
    payload: ImagePayload,
    history_steps: int,
) -> None:
    root = project.workdir / "images" / entry.id
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    writer = _Writer(root)
    doc = payload.doc

    original = None
    try:
        original = doc.original
    except RuntimeError:
        original = None
    if original is not None:
        writer.write_bytes("original.png", _encode_png(original))

    layers = list(doc.layers())
    layer_dicts = [_layer_dict(layer, writer) for layer in layers]
    state = doc.history_state()
    steps, snapshots, pointer = _limit_history(
        list(state["steps"]), list(state["snapshots"]), int(state["pointer"]), history_steps
    )
    snapshot_dicts = [
        {
            "active": int(active),
            "layers": [_layer_dict(layer, writer) for layer in snap_layers],
        }
        for snap_layers, active in snapshots
    ]
    step_dicts = [
        {
            "kind": step.kind,
            "label": step.label,
            "origin": step.origin,
            "data": _encode_obj(step.data, writer, f"s{i}"),
        }
        for i, step in enumerate(steps)
    ]

    selection_rel = None
    if payload.selection is not None:
        selection_rel = "selection.png"
        writer.write_bytes(selection_rel, _encode_png(payload.selection))

    data = {
        "schema": SCHEMA,
        "canvas": {"width": int(doc.width() if doc.is_loaded else 0), "height": int(doc.height() if doc.is_loaded else 0)},
        "active_layer": int(doc.active_index),
        "next_id": int(state["next_id"]),
        "layers": layer_dicts,
        "steps": step_dicts,
        "pointer": int(pointer),
        "snapshots": snapshot_dicts,
        "history_steps": int(history_steps),
        "selection": selection_rel,
        "params": _json_safe(payload.params),
        "view": _json_safe(payload.view),
    }
    writer.write_json("state.json", data)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return None
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def read_image_state(project: "Project", entry: ImageEntry) -> ImagePayload | None:
    root = project.workdir / "images" / entry.id
    state_path = root / "state.json"
    if not state_path.exists():
        return None
    data = _json_load(state_path, {})
    if not isinstance(data, dict):
        return None
    layers = [_layer_from_dict(item, root) for item in data.get("layers", [])]
    if not layers:
        return None
    snapshots: list[tuple[tuple[Layer, ...], int]] = []
    for snap in data.get("snapshots", []):
        try:
            snap_layers = tuple(_layer_from_dict(item, root) for item in snap.get("layers", []))
            snapshots.append((snap_layers, int(snap.get("active", 0))))
        except Exception:  # noqa: BLE001
            continue
    steps = [
        Step(
            kind=str(item.get("kind", "snapshot")),
            label=str(item.get("label", "")),
            data=_decode_obj(item.get("data", {}), root),
            origin=str(item.get("origin", "")),
        )
        for item in data.get("steps", [])
    ]
    original = None
    if (root / "original.png").exists():
        original = _decode_png((root / "original.png").read_bytes())
    doc = LayerDocument()
    doc.restore_history_state(
        original=original,
        layers=layers,
        steps=steps,
        snapshots=snapshots or [(tuple(layers), int(data.get("active_layer", 0)))],
        pointer=int(data.get("pointer", 0)),
        next_id=int(data.get("next_id", 1)),
        max_history=max(1, int(data.get("history_steps", 20) or 20)),
        active_index=int(data.get("active_layer", 0)),
    )
    selection = None
    if data.get("selection"):
        selection = _read_any(root, str(data["selection"]))
        if selection.ndim == 3:
            selection = cv2.cvtColor(selection, cv2.COLOR_BGR2GRAY)
    return ImagePayload(doc=doc, selection=selection, params=data.get("params"), view=data.get("view", {}))


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class Project:
    def __init__(self, path: Path, workdir: Path, manifest: dict[str, Any], chat: dict[str, Any]):
        self.path = Path(path)
        self.workdir = Path(workdir)
        self.manifest = manifest if isinstance(manifest, dict) else {}
        self.chat = chat if isinstance(chat, dict) else {"summary": "", "messages": []}
        self._sync()

    def _sync(self) -> None:
        self.name = str(self.manifest.get("name") or self.path.stem)
        self.created_at = str(self.manifest.get("created_at", ""))
        self.modified_at = str(self.manifest.get("modified_at", ""))
        library = self.manifest.get("library")
        if not isinstance(library, list):
            library = []
        self.images = [
            ImageEntry.from_dict(item)
            for item in library
            if isinstance(item, dict) and item.get("id")
        ]
        self.images.sort(key=lambda item: item.order)
        self.active_image_id = self.manifest.get("active_image_id") or (
            self.images[0].id if self.images else None
        )
        cover = self.manifest.get("cover")
        self.cover = dict(cover) if isinstance(cover, dict) else {"mode": "active"}
        layout = self.manifest.get("layout")
        self.layout = dict(layout) if isinstance(layout, dict) else {}
        self.history_steps = self.manifest.get("history_steps")

    def source_path(self, entry: ImageEntry) -> Path:
        return self.workdir / entry.source

    def image_state_path(self, entry: ImageEntry) -> Path:
        return self.workdir / "images" / entry.id / "state.json"

    def store_payload(self, entry: ImageEntry, payload: ImagePayload, history_steps: int = 20) -> None:
        _write_image_state(self, entry, payload, history_steps)
        entry.last_edited = _now()
        self._touch()

    def entry(self, image_id: str) -> ImageEntry | None:
        for item in self.images:
            if item.id == image_id:
                return item
        return None

    def add_image(self, source: str | Path) -> ImageEntry:
        src = Path(source)
        ext = src.suffix.lower() or ".png"
        index = len(self.images) + 1
        used = {entry.id for entry in self.images}
        while f"img_{index:04d}" in used:
            index += 1
        image_id = f"img_{index:04d}"
        rel = f"sources/{image_id}{ext}"
        dest = self.workdir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        entry = ImageEntry(
            id=image_id,
            display_name=src.name,
            source=rel,
            added_at=_now(),
            order=len(self.images),
            last_edited=_now(),
        )
        self.images.append(entry)
        self._touch()
        return entry

    def remove_image(self, image_id: str) -> None:
        entry = self.entry(image_id)
        if entry is None:
            return
        self.images = [item for item in self.images if item.id != image_id]
        for rel in (entry.source, f"images/{image_id}"):
            target = self.workdir / rel
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
        if self.active_image_id == image_id:
            self.active_image_id = self.images[0].id if self.images else None
        for i, item in enumerate(self.images):
            item.order = i
        self._touch()

    def touch_image(self, image_id: str) -> None:
        entry = self.entry(image_id)
        if entry is not None:
            entry.last_edited = _now()
            self._touch()

    def _touch(self) -> None:
        self.modified_at = _now()
        self.manifest["modified_at"] = self.modified_at

    def save(
        self,
        loaded: dict[str, ImagePayload],
        active_id: str | None,
        conversation: list[dict[str, Any]],
        summary: str,
        layout: dict[str, Any],
        history_steps: int,
        cover_mode: str,
        custom_cover: bytes | None = None,
    ) -> None:
        for image_id, payload in loaded.items():
            entry = self.entry(image_id)
            if entry is not None:
                _write_image_state(self, entry, payload, history_steps)
        self.active_image_id = active_id
        self.layout = dict(layout)
        self.chat = {"summary": summary, "messages": conversation}
        self.history_steps = int(history_steps)
        self.cover = {"mode": cover_mode, "file": "previews/cover.png"}
        self._generate_cover(loaded, cover_mode, custom_cover)
        self.manifest.update(
            {
                "schema": SCHEMA,
                "kind": "truffle-project",
                "name": self.name,
                "created_at": self.created_at or _now(),
                "modified_at": _now(),
                "app_version": __version__,
                "library": [item.to_dict() for item in self.images],
                "active_image_id": self.active_image_id,
                "cover": self.cover,
                "layout": self.layout,
                "history_steps": self.history_steps,
            }
        )
        _json_dump(self.workdir / MANIFEST, self.manifest)
        _json_dump(self.workdir / CHAT, self.chat)
        _zip_dir(self.workdir, self.path)
        self.modified_at = self.manifest["modified_at"]
        self._sync()

    def _image_bgr(self, entry: ImageEntry, loaded: dict[str, ImagePayload]) -> np.ndarray | None:
        payload = loaded.get(entry.id)
        if payload is not None and payload.doc.is_loaded:
            return payload.doc.current
        state_path = self.image_state_path(entry)
        if state_path.exists():
            payload = read_image_state(self, entry)
            if payload is not None and payload.doc.is_loaded:
                return payload.doc.current
        source = self.source_path(entry)
        if not source.exists():
            return None
        data = np.fromfile(str(source), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if image is None:
            return None
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return image

    def _generate_cover(
        self,
        loaded: dict[str, ImagePayload],
        mode: str,
        custom_cover: bytes | None,
    ) -> None:
        previews = self.workdir / "previews"
        previews.mkdir(parents=True, exist_ok=True)
        canvas: np.ndarray | None = None
        if mode == "custom" and custom_cover:
            raw = np.frombuffer(custom_cover, dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
            if image is not None:
                if image.ndim == 2:
                    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                if image.shape[2] == 4:
                    image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
                canvas = image
        elif mode == "first" and self.images:
            canvas = self._image_bgr(self.images[0], loaded)
        elif mode == "tiles":
            ordered = sorted(
                self.images,
                key=lambda item: item.last_edited or item.added_at,
                reverse=True,
            )[:4]
            if not ordered:
                ordered = self.images[:4]
            tiles: list[np.ndarray | None] = [self._image_bgr(item, loaded) for item in ordered]
            while len(tiles) < 4:
                tiles.append(tiles[-1] if tiles else None)
            cell = np.zeros((COVER_H // 2, COVER_W // 2, 3), dtype=np.uint8)
            canvas = np.zeros((COVER_H, COVER_W, 3), dtype=np.uint8)
            for i, tile in enumerate(tiles[:4]):
                small = _letterbox(tile, COVER_W // 2, COVER_H // 2) if tile is not None else cell
                y, x = divmod(i, 2)
                canvas[y * (COVER_H // 2):(y + 1) * (COVER_H // 2),
                       x * (COVER_W // 2):(x + 1) * (COVER_W // 2)] = small
        else:
            entry = self.entry(self.active_image_id) if self.active_image_id else None
            if entry is None and self.images:
                entry = self.images[0]
            if entry is not None:
                canvas = self._image_bgr(entry, loaded)
        if canvas is None:
            return
        if canvas.shape[:2] != (COVER_H, COVER_W):
            canvas = _letterbox(canvas, COVER_W, COVER_H)
        (previews / "cover.png").write_bytes(_encode_png(canvas))

    def close(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


def _letterbox(image: np.ndarray | None, width: int, height: int) -> np.ndarray:
    canvas = np.full((height, width, 3), 32, dtype=np.uint8)
    if image is None or image.size == 0:
        return canvas
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return canvas
    scale = min(width / w, height / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    small = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    x, y = (width - nw) // 2, (height - nh) // 2
    canvas[y:y + nh, x:x + nw] = small[..., :3]
    return canvas


# ---------------------------------------------------------------------------
# 项目文件操作
# ---------------------------------------------------------------------------


def create_project(
    path: str | Path,
    name: str,
    chat: dict[str, Any] | None = None,
    cover_mode: str = "active",
) -> Project:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workdir = _new_workdir(target)
    try:
        manifest = {
            "schema": SCHEMA,
            "kind": "truffle-project",
            "name": name,
            "created_at": _now(),
            "modified_at": _now(),
            "app_version": __version__,
            "library": [],
            "active_image_id": None,
            "cover": {"mode": cover_mode, "file": "previews/cover.png"},
            "layout": {},
            "history_steps": None,
        }
        _json_dump(workdir / MANIFEST, manifest)
        _json_dump(workdir / CHAT, chat or {"summary": "", "messages": []})
        _zip_dir(workdir, target)
        return Project(target, workdir, manifest, chat or {"summary": "", "messages": []})
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def _new_workdir(project_path: Path) -> Path:
    from ..config import config_dir

    base = config_dir() / "workspaces"
    base.mkdir(parents=True, exist_ok=True)
    stamp = f"{project_path.stem}_{int(time.time() * 1000)}"
    workdir = base / stamp
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def open_project(path: str | Path) -> Project:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    workdir = _new_workdir(target)
    try:
        with zipfile.ZipFile(target, "r") as zf:
            _safe_members(zf, workdir)
        manifest = _json_load(workdir / MANIFEST, None)
        if not isinstance(manifest, dict) or manifest.get("kind") != "truffle-project":
            raise ValueError("不是有效的 Truffle 项目文件")
        chat = _json_load(workdir / CHAT, {"summary": "", "messages": []})
        return Project(target, workdir, manifest, chat)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def read_project_info(path: str | Path, source: str = "default") -> ProjectInfo:
    target = Path(path)
    if not target.exists():
        return ProjectInfo(path=target, name=target.stem, missing=True, source=source)
    try:
        with zipfile.ZipFile(target, "r") as zf:
            manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
            cover = None
            try:
                cover = zf.read("previews/cover.png")
            except KeyError:
                pass
        return ProjectInfo(
            path=target,
            name=str(manifest.get("name") or target.stem),
            modified=target.stat().st_mtime,
            cover=cover,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        return ProjectInfo(
            path=target,
            name=target.stem,
            modified=target.stat().st_mtime if target.exists() else 0,
            missing=not target.exists(),
            error=str(exc),
            source=source,
        )


def scan_projects(folder: str | Path) -> list[ProjectInfo]:
    root = Path(folder)
    if not root.exists():
        return []
    infos: list[ProjectInfo] = []
    for path in sorted(root.glob("*" + PROJECT_EXT)):
        if path.is_file():
            infos.append(read_project_info(path))
    return infos


def move_to_recycle_bin(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        return
    if os.name == "nt":
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        FO_DELETE = 3
        FOF_SILENT = 0x0004
        FOF_NOCONFIRMATION = 0x0010
        FOF_ALLOWUNDO = 0x0040
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = str(target.resolve()) + "\0\0"
        op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result == 0:
            return
    target.unlink(missing_ok=True)


def rename_project(path: str | Path, new_name: str) -> Path:
    target = Path(path)
    new_path = target.with_name(new_name + PROJECT_EXT)
    if new_path.exists():
        raise FileExistsError(str(new_path))
    project = open_project(target)
    try:
        project.name = new_name
        project.save(
            {},
            project.active_image_id,
            project.chat.get("messages", []),
            project.chat.get("summary", ""),
            project.layout,
            int(project.history_steps if project.history_steps is not None else 20),
            str(project.cover.get("mode", "active")),
        )
        shutil.move(str(target), str(new_path))
    finally:
        project.close()
    return new_path


def set_project_cover(path: str | Path, mode: str, custom: bytes | None = None) -> None:
    project = open_project(path)
    try:
        project.save(
            {},
            project.active_image_id,
            project.chat.get("messages", []),
            project.chat.get("summary", ""),
            project.layout,
            int(project.history_steps if project.history_steps is not None else 20),
            mode,
            custom,
        )
    finally:
        project.close()


# ---------------------------------------------------------------------------
# 最近项目
# ---------------------------------------------------------------------------


class RecentProjects:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or recent_store_path()
        self.entries: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        data = _json_load(self.path, {"entries": []})
        entries = data.get("entries") if isinstance(data, dict) else []
        self.entries = [item for item in entries if isinstance(item, dict) and item.get("path")]

    def save(self) -> None:
        _json_dump(self.path, {"entries": self.entries[:MAX_RECENT]})

    def add(self, path: str | Path, name: str | None = None) -> None:
        target = os.path.normcase(os.path.abspath(str(path)))
        self.entries = [item for item in self.entries if os.path.normcase(os.path.abspath(str(item["path"]))) != target]
        self.entries.insert(
            0,
            {
                "path": str(Path(path).resolve()),
                "name": name or Path(path).stem,
                "last_opened": _now(),
            },
        )
        self.entries = self.entries[:MAX_RECENT]
        self.save()

    def remove(self, path: str | Path) -> None:
        target = os.path.normcase(os.path.abspath(str(path)))
        self.entries = [item for item in self.entries if os.path.normcase(os.path.abspath(str(item["path"]))) != target]
        self.save()

    def paths(self) -> list[str]:
        return [str(item["path"]) for item in self.entries]


def merged_projects(settings: Any = None, recent: RecentProjects | None = None) -> list[ProjectInfo]:
    folder = default_project_dir(settings)
    recent = recent or RecentProjects()
    by_key: dict[str, ProjectInfo] = {}
    for info in scan_projects(folder):
        by_key[os.path.normcase(os.path.abspath(str(info.path)))] = info
    for entry in recent.entries:
        path = Path(entry["path"])
        key = os.path.normcase(os.path.abspath(str(path)))
        if key in by_key:
            continue
        info = read_project_info(path, source="recent")
        if not info.name or info.name == path.stem:
            info.name = str(entry.get("name") or path.stem)
        by_key[key] = info
    return sorted(by_key.values(), key=lambda item: item.modified, reverse=True)


# ---------------------------------------------------------------------------
# 旧会话迁移
# ---------------------------------------------------------------------------


def migrate_session(settings: Any) -> Path | None:
    """把旧的全局 session.json 迁移成「默认项目」。返回新项目路径或 None。"""
    if getattr(settings, "session_migrated", False):
        return None
    from ..config import config_dir

    session_path = config_dir() / "session.json"
    settings.session_migrated = True
    if not session_path.exists():
        settings.save()
        return None
    chat = _json_load(session_path, {"summary": "", "messages": []})
    if not isinstance(chat, dict):
        chat = {"summary": "", "messages": []}
    folder = default_project_dir(settings)
    target = folder / ("默认项目" + PROJECT_EXT)
    index = 2
    while target.exists():
        target = folder / (f"默认项目 ({index})" + PROJECT_EXT)
        index += 1
    project = create_project(target, target.stem, chat)
    project.close()
    try:
        session_path.replace(session_path.with_name("session.json.migrated"))
    except OSError:
        pass
    RecentProjects().add(target, target.stem)
    settings.save()
    return target


def project_folder(settings: Any = None) -> Path:
    return default_project_dir(settings)


def safe_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return None
