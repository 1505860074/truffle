"""让 pytest 能直接找到 src 下的包（无需先安装）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
