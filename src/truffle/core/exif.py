"""JPEG EXIF（APP1）段的读取与注入（不依赖第三方库）。"""

from __future__ import annotations

from pathlib import Path


def read_exif_app1(path: str | Path) -> bytes | None:
    """从 JPEG 文件中取出 EXIF 的 APP1 段（含 0xFFE1 标记与长度）。"""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        if marker == 0xDA:  # 到达图像数据，停止
            break
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        seg = data[i + 4 : i + 2 + seg_len]
        if marker == 0xE1 and seg[:6] == b"Exif\x00\x00":
            return data[i : i + 2 + seg_len]
        i += 2 + seg_len
    return None


def inject_exif_app1(jpeg_bytes: bytes, app1: bytes) -> bytes:
    """把 EXIF APP1 段插到 JPEG 的 SOI 之后。"""
    if jpeg_bytes[:2] != b"\xff\xd8":
        return jpeg_bytes
    return jpeg_bytes[:2] + app1 + jpeg_bytes[2:]
