"""离线自检：不依赖大模型 API，直接验证 CV 分析与人像修饰工具是否正常。

用法：
    python scripts/selftest.py                # 用内置合成人像测试
    python scripts/selftest.py 照片.jpg        # 用你自己的照片测试
输出：
    在当前目录 out_selftest/ 下生成每个工具的处理结果，便于肉眼比对。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from truffle.cv.analyzer import Analyzer  # noqa: E402
from truffle.tools.base import ToolContext  # noqa: E402
from truffle.tools.registry import build_default_registry  # noqa: E402


def imread_unicode(path: str) -> np.ndarray | None:
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: str, image: np.ndarray) -> None:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, image)
    if ok:
        buf.tofile(path)


def synthetic_portrait(size: int = 480) -> np.ndarray:
    """生成一张合成"人像"：肤色椭圆脸 + 五官阴影 + 噪点 + 斑点。"""
    img = np.full((size, size, 3), (180, 170, 160), dtype=np.uint8)  # 背景
    cv2.ellipse(img, (size // 2, size // 2), (size // 4, size // 3), 0, 0, 360,
                (140, 160, 205), -1)  # 肤色脸
    cv2.circle(img, (size // 2 - 60, size // 2 - 40), 12, (60, 60, 60), -1)  # 左眼
    cv2.circle(img, (size // 2 + 60, size // 2 - 40), 12, (60, 60, 60), -1)  # 右眼
    cv2.ellipse(img, (size // 2, size // 2 + 60), (40, 12), 0, 0, 360, (90, 90, 140), -1)  # 嘴
    rng = np.random.default_rng(0)
    for _ in range(40):  # 斑点
        x = int(rng.integers(size // 3, size * 2 // 3))
        y = int(rng.integers(size // 3, size * 2 // 3))
        cv2.circle(img, (x, y), int(rng.integers(2, 4)), (110, 120, 130), -1)
    noise = rng.integers(-14, 14, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else None
    if source:
        image = imread_unicode(source)
        if image is None:
            print(f"[失败] 无法读取图片：{source}")
            return 1
        print(f"[输入] {source}  尺寸={image.shape[1]}x{image.shape[0]}")
    else:
        image = synthetic_portrait()
        print("[输入] 内置合成人像 480x480（也可传入你自己的照片路径）")

    analyzer = Analyzer()
    registry = build_default_registry()
    ctx = ToolContext(analyzer)

    analysis = ctx.analyze(image)
    print(f"[分析] 检测到人脸数：{len(analysis.faces)}")
    if analysis.skin_mask is not None:
        ratio = float((analysis.skin_mask > 128).mean()) * 100
        print(f"[分析] 皮肤区域占比：{ratio:.1f}%")

    out_dir = Path("out_selftest")
    out_dir.mkdir(exist_ok=True)

    cases = [
        ("skin_smooth", {"strength": 0.7}),
        ("whiten", {"strength": 0.5}),
        ("remove_blemish", {"strength": 0.7, "threshold": 12}),
        ("slim_face", {"strength": 0.5}),
        ("enlarge_eyes", {"strength": 0.4}),
    ]

    ok = 0
    for name, params in cases:
        try:
            result = registry.execute(name, image, ctx, params)
            changed = not np.array_equal(result, image)
            path = out_dir / f"{name}.png"
            imwrite_unicode(str(path), result)
            flag = "生效" if changed else "无变化(可能未检测到所需区域)"
            print(f"[工具] {name:<16} 参数={params}  ->  {flag}  已存 {path}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[工具] {name:<16} 执行异常：{exc}")

    print(f"\n[结果] {ok}/{len(cases)} 个工具正常执行。请打开 out_selftest/ 肉眼比对效果。")
    return 0 if ok == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
