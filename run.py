"""程序启动入口。

无控制台（pythonw）启动时看不到报错，因此这里把异常写入
`%APPDATA%/Truffle/error.log`，便于排查。
"""

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def _write_crash_log(exc: BaseException) -> None:
    try:
        base = os.environ.get("APPDATA") or str(Path.home())
        log = Path(base) / "Truffle" / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from truffle.main import main

        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        _write_crash_log(exc)
        raise
