"""自动更新框架：从可配置的 JSON 地址检查新版本，下载并拉起安装器。

JSON 格式（放任意静态地址即可）：
    {"version": "0.1.5", "url": "https://.../Truffle-Setup-0.1.5.exe", "notes": "..."}
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request

from PySide6.QtCore import QThread, Signal


def _parse(version: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for piece in str(version).strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def extract_release(data: dict) -> tuple[str, str, str]:
    """兼容两种更新源格式：
    1) 静态 JSON：{"version","url","notes"}
    2) Gitee / GitHub Releases API：{"tag_name","body","assets":[{"browser_download_url"}]}
    """
    if data.get("version") and data.get("url"):
        return str(data["version"]), str(data["url"]), str(data.get("notes", ""))
    tag = data.get("tag_name") or data.get("name") or ""
    url = ""
    for asset in data.get("assets", []) or []:
        candidate = str(asset.get("browser_download_url", ""))
        if candidate.lower().endswith(".exe"):
            url = candidate
            break
    if tag and url:
        return str(tag), url, str(data.get("body", ""))
    return "", "", ""


class UpdateWorker(QThread):
    found = Signal(object)  # {"version","url","notes"} 或 None
    failed = Signal(str)

    def __init__(self, url: str, current: str) -> None:
        super().__init__()
        self.url = url
        self.current = current

    def run(self) -> None:
        try:
            request = urllib.request.Request(self.url, headers={"User-Agent": "Truffle"})
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            latest, download, notes = extract_release(data)
            if latest and download and is_newer(latest, self.current):
                self.found.emit({"version": latest, "url": download, "notes": notes})
            else:
                self.found.emit(None)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    done = Signal(str)  # 下载到的本地路径
    failed = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            path = os.path.join(tempfile.gettempdir(), "Truffle-Setup-update.exe")
            request = urllib.request.Request(self.url, headers={"User-Agent": "Truffle"})
            with urllib.request.urlopen(request, timeout=30) as response, open(path, "wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    handle.write(chunk)
            self.done.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
