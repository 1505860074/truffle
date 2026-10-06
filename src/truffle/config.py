"""全局配置：只从软件内部（用户配置文件）读取，无需事先注入环境变量。

配置文件位置：`%APPDATA%/Truffle/config.json`，由软件内的「设置」对话框写入。
首次启动若未配置，软件会自动弹出设置窗口引导填写。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import APP_NAME


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = config_dir() / "config.json"


@dataclass
class LLMSettings:
    """OpenAI 兼容接口配置。改 base_url 即可切到任意兼容服务。"""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout: int = 60


@dataclass
class AppSettings:
    llm: LLMSettings = field(default_factory=LLMSettings)

    # ---------- 读写 ----------
    @classmethod
    def load(cls) -> "AppSettings":
        llm = LLMSettings()
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for key, value in raw.get("llm", {}).items():
                    if hasattr(llm, key) and value not in (None, ""):
                        setattr(llm, key, value)
            except (json.JSONDecodeError, OSError):
                pass
        return cls(llm=llm)

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.llm.api_key)
