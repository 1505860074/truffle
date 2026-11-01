r"""离线评估一键风格：对一组图片跑求解器，输出可比较的指标。

用法：
    .\.venv\Scripts\python.exe scripts\eval_styles.py images\ --style tangshui --out eval.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from truffle.agent.evaluation import evaluate_paths, summarize  # noqa: E402
from truffle.agent.style import PROFILES, resolve_style  # noqa: E402
from truffle.cv.analyzer import Analyzer  # noqa: E402
from truffle.tools.registry import build_default_registry  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def collect(folder: Path, limit: int = 0) -> list[Path]:
    paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTS and p.is_file())
    return paths[:limit] if limit > 0 else paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--style", default="tangshui", help="风格 id，或 all")
    parser.add_argument("--out", type=Path, default=None, help="输出 CSV 路径")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    paths = collect(args.folder, args.limit)
    if not paths:
        print("没有找到图片")
        return 1
    registry = build_default_registry()
    analyzer = Analyzer()
    styles = list(PROFILES) if args.style == "all" else [args.style]
    rows = []
    for style_id in styles:
        profile = resolve_style(style_id)
        results = evaluate_paths(paths, registry, analyzer, profile)
        summary = summarize(results)
        print(f"\n[{profile.name}] {json.dumps(summary, ensure_ascii=False)}")
        for result in results:
            print(
                f"  {Path(result.path).name}: "
                f"distance {result.style_distance_before:.3f} -> {result.style_distance_after:.3f}, "
                f"natural {result.naturalness:.3f}, jobs {result.jobs}, artifacts {result.artifacts}, "
                f"{result.seconds:.2f}s"
            )
            row = {"style": profile.id, **result.to_dict()}
            rows.append(row)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
