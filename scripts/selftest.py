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
        # 人像修饰
        ("skin_smooth", {"strength": 0.7}),
        ("whiten", {"strength": 0.5}),
        ("remove_blemish", {"strength": 0.7, "threshold": 12}),
        ("slim_face", {"strength": 0.5}),
        ("enlarge_eyes", {"strength": 0.4}),
        ("teeth_whiten", {"strength": 0.5}),
        ("remove_dark_circles", {"strength": 0.5}),
        ("eye_brighten", {"strength": 0.5, "sclera": 0.3}),
        ("hair_color", {"hue": 0.05, "strength": 0.5}),
        ("lipstick", {"hue": 0.98, "strength": 0.5}),
        ("background_blur", {"strength": 0.6}),
        # 调色 / 影调 / 构图
        ("color_adjust", {"brightness": 0.1, "contrast": 0.1, "saturation": 0.2}),
        ("color_temp", {"temperature": 0.3, "tint": 0.0}),
        ("hsl", {"hue": 0.1, "saturation": 0.2, "lightness": 0.1}),
        ("curves", {"black": 0.1, "shadows": 0.1, "midtones": 0.0, "highlights": -0.1, "white": 0.0}),
        ("tone_recovery", {"highlights": -0.4, "shadows": 0.4}),
        ("dehaze", {"strength": 0.5}),
        ("hdr", {"strength": 0.5, "local_contrast": 0.3}),
        ("sharpen_clarity", {"sharpen": 0.5, "clarity": 0.3}),
        ("vignette", {"amount": 0.5, "softness": 0.6}),
        ("film", {"grain": 0.4, "fade": 0.3}),
        ("rotate_flip", {"rotate": 90, "flip": "none"}),
        # 形体 / 形变
        ("body_slim", {"strength": 0.4}),
        ("leg_lengthen", {"strength": 0.3}),
        ("distort", {"mode": "twirl", "strength": 0.4}),
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

    # 健壮性：在「无人脸/无人体」的噪声图上，所有工具都应安全返回（不崩溃、形状不变）
    noise = np.random.default_rng(1).integers(0, 255, (200, 240, 3), dtype=np.uint8)
    tools = registry.all()
    robust_ok = 0
    for tool in tools:
        params = {p.name: p.default for p in tool.parameters}
        try:
            out = registry.execute(tool.name, noise, ctx, params)
            assert out.shape == noise.shape and out.dtype == np.uint8
            robust_ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[健壮性] {tool.name} 异常：{exc}")

    # 零参数应为无操作
    noop_cases = [
        ("whiten", {"strength": 0.0}),
        ("color_adjust", {"brightness": 0.0, "contrast": 0.0, "saturation": 0.0}),
        ("rotate_flip", {"rotate": 0, "flip": "none"}),
    ]
    noop_ok = sum(
        1 for name, params in noop_cases
        if np.array_equal(registry.execute(name, image, ctx, params), image)
    )

    print(f"[健壮性] {robust_ok}/{len(tools)} 个工具在无人脸图上安全返回")
    print(f"[无操作] {noop_ok}/{len(noop_cases)} 个零参数用例与输入一致")
    print(f"\n[结果] 工具 {ok}/{len(cases)} · 健壮性 {robust_ok}/{len(tools)} · 无操作 {noop_ok}/{len(noop_cases)}")
    return 0 if (ok == len(cases) and robust_ok == len(tools) and noop_ok == len(noop_cases)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
