"""全局配置：大模型 API 与用户设置的读写。

优先级：`.env`（开发默认） < 用户配置 `config.json`（界面里填写的值）。
配置文件放在 `%APPDATA%/Truffle/config.json`，不会写进仓库。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dotenv import load_dotenv

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
        load_dotenv()
        llm = LLMSettings(
            base_url=os.environ.get("TRUFFLE_LLM_BASE_URL", LLMSettings.base_url),
            api_key=os.environ.get("TRUFFLE_LLM_API_KEY", ""),
            model=os.environ.get("TRUFFLE_LLM_MODEL", LLMSettings.model),
            timeout=int(os.environ.get("TRUFFLE_LLM_TIMEOUT", "60")),
        )
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for k, v in raw.get("llm", {}).items():
                    if hasattr(llm, k) and v not in (None, ""):
                        setattr(llm, k, v)
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
