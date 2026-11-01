"""程序启动入口。

无控制台（pythonw）启动时看不到报错，因此这里把异常写入
`%APPDATA%/Truffle/error.log`，便于排查。
设置环境变量 TRUFFLE_DEBUG=1 时会额外把导入诊断写入 debug.log。
"""

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# 显式顶层包导入：确保 PyInstaller 收录父包 truffle（只打包子模块会导致导入失败）
try:
    import truffle  # noqa: E402
except Exception:  # noqa: BLE001
    truffle = None  # type: ignore[assignment]


def _appdata_file(name: str) -> Path:
    override = os.environ.get("TRUFFLE_HOME")
    if override:
        path = Path(override) / name
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / "Truffle" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_crash_log(exc: BaseException) -> None:
    try:
        from datetime import datetime

        path = _appdata_file("error.log")
        if path.exists() and path.stat().st_size > 1_000_000:  # 超过 1MB 轮转
            path.replace(path.with_name("error.prev.log"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            handle.write("".join(traceback.format_exception(exc)))
    except Exception:
        pass


def _debug(msg: str) -> None:
    try:
        with _appdata_file("debug.log").open("a", encoding="utf-8") as handle:
            handle.write(msg + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    if os.environ.get("TRUFFLE_DEBUG") == "1":
        import importlib.util

        _debug("frozen=" + str(getattr(sys, "frozen", False)))
        _debug("sys.executable=" + sys.executable)
        _debug("sys.path=" + repr(sys.path))
        _debug("__file__=" + repr(__file__))
        _debug("truffle module=" + repr(truffle))
        _debug("find_spec(truffle)=" + repr(importlib.util.find_spec("truffle")))
        _debug("find_spec(truffle.main)=" + repr(importlib.util.find_spec("truffle.main")))

    try:
        from truffle.main import main

        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        _write_crash_log(exc)
        raise
