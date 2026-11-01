from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from truffle.core.layer_doc import LayerDocument
from truffle.core.project import (
    ImagePayload,
    RecentProjects,
    create_project,
    merged_projects,
    migrate_session,
    open_project,
    read_image_state,
    read_project_info,
    rename_project,
    set_project_cover,
)


class _FakeSettings:
    def __init__(self, folder: Path) -> None:
        self.project_dir = str(folder)
        self.session_migrated = False

    def save(self) -> None:
        pass


def _image(path: Path, h: int = 48, w: int = 64) -> Path:
    image = np.zeros((h, w, 3), dtype=np.uint8)
    image[..., 1] = 180
    cv2.imwrite(str(path), image)
    return path


def test_project_roundtrip(tmp_path: Path) -> None:
    source = _image(tmp_path / "a.png")
    project = create_project(tmp_path / "demo.truffle", "demo")
    entry = project.add_image(source)
    doc = LayerDocument()
    doc.load(str(source))
    doc.add_layer("layer 2")
    doc.push_op("layer", "step", {})
    selection = np.full((48, 64), 255, dtype=np.uint8)
    project.save(
        {entry.id: ImagePayload(doc=doc, selection=selection, params=[["skin", {"a": 1}]])},
        entry.id,
        [{"role": "user", "content": "hi"}],
        "summary",
        {"chat_visible": True},
        20,
        "active",
    )
    path = project.path
    project.close()

    reopened = open_project(path)
    assert reopened.name == "demo"
    assert len(reopened.images) == 1
    assert reopened.active_image_id == entry.id
    assert reopened.chat["summary"] == "summary"
    payload = read_image_state(reopened, reopened.images[0])
    assert payload is not None
    assert len(payload.doc.layers()) == 2
    assert len(payload.doc.steps()) == 2
    assert payload.selection is not None
    assert payload.selection.shape == (48, 64)
    reopened.close()


def test_history_is_limited(tmp_path: Path) -> None:
    source = _image(tmp_path / "a.png")
    project = create_project(tmp_path / "limit.truffle", "limit")
    entry = project.add_image(source)
    doc = LayerDocument()
    doc.load(str(source))
    for i in range(30):
        doc.push(doc.current, f"step {i}")
    project.save({entry.id: ImagePayload(doc=doc)}, entry.id, [], "", {}, 5, "active")
    path = project.path
    project.close()

    reopened = open_project(path)
    payload = read_image_state(reopened, reopened.images[0])
    assert payload is not None
    assert len(payload.doc.steps()) <= 5
    assert payload.doc.pointer() <= len(payload.doc.steps())
    reopened.close()


def test_recent_projects_limit(tmp_path: Path) -> None:
    store = RecentProjects(tmp_path / "projects.json")
    for i in range(60):
        store.add(tmp_path / f"p{i}.truffle", f"p{i}")
    assert len(store.entries) == 50
    store.add(tmp_path / "p59.truffle", "p59")
    assert store.entries[0]["path"].endswith("p59.truffle")
    store.remove(tmp_path / "p59.truffle")
    assert all(not item["path"].endswith("p59.truffle") for item in store.entries)


def test_rename_and_cover(tmp_path: Path) -> None:
    source = _image(tmp_path / "a.png")
    project = create_project(tmp_path / "old.truffle", "old")
    entry = project.add_image(source)
    doc = LayerDocument()
    doc.load(str(source))
    project.save({entry.id: ImagePayload(doc=doc)}, entry.id, [], "", {}, 20, "active")
    project.close()

    renamed = rename_project(tmp_path / "old.truffle", "new")
    assert renamed.name == "new.truffle"
    assert not (tmp_path / "old.truffle").exists()
    info = read_project_info(renamed)
    assert info.name == "new"
    assert info.cover
    set_project_cover(renamed, "first")
    info = read_project_info(renamed)
    assert info.cover
    reopened = open_project(renamed)
    assert reopened.name == "new"
    reopened.close()


def test_merged_projects_marks_missing(tmp_path: Path) -> None:
    settings = _FakeSettings(tmp_path / "default")
    source = _image(tmp_path / "a.png")
    project = create_project(tmp_path / "default" / "ok.truffle", "ok")
    entry = project.add_image(source)
    project.save({}, entry.id, [], "", {}, 20, "active")
    project.close()
    recent = RecentProjects(tmp_path / "recent.json")
    recent.add(tmp_path / "gone.truffle", "gone")
    infos = merged_projects(settings, recent)
    names = {info.name: info for info in infos}
    assert "ok" in names
    assert names["gone"].missing is True


def test_migrate_old_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from truffle.config import config_dir

    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "session.json").write_text(
        json.dumps({"summary": "old", "messages": [{"role": "user", "content": "hello"}]}),
        encoding="utf-8",
    )
    settings = _FakeSettings(tmp_path / "projects")
    path = migrate_session(settings)
    assert path is not None
    assert path.exists()
    assert (config_dir() / "session.json.migrated").exists()
    project = open_project(path)
    assert project.chat["summary"] == "old"
    project.close()
    assert settings.session_migrated is True
