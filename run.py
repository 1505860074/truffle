"""开发用启动脚本：无需安装即可 `python run.py` 运行。

安装过 `pip install -e .` 后，也可以直接用 `python -m truffle`。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from truffle.main import main  # noqa: E402

if __name__ == "__main__":
    main()
