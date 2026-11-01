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
    vision: bool = False  # 是否把当前图发给多模态模型
    context: str = ""     # 核心上下文/用户偏好，注入系统提示


CLOSE_BEHAVIORS = ("ask", "minimize", "exit")  # 每次询问 / 最小化到任务栏 / 直接退出
SCHEMA_VERSION = 1  # 配置结构版本，用于升级迁移


@dataclass
class AppSettings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    close_behavior: str = "ask"  # 点击窗口关闭按钮时的行为
    theme: str = "dark"          # dark | light
    language: str = "zh"         # zh | en
    update_url: str = ""         # 更新检查地址（静态 JSON 或 Gitee/GitHub Releases API）；留空则不检查
    auto_check_update: bool = True  # 启动时自动检查更新
    file_assoc: bool = False     # 是否关联图片文件（Windows）
    # LeanCloud 账号
    lc_app_id: str = ""
    lc_app_key: str = ""
    lc_server_url: str = ""
    require_login: bool = False  # 必须登录才能使用
    community_url: str = ""      # 社区入口地址
    account_token: str = ""      # 登录后的 sessionToken
    account_username: str = ""   # 当前登录用户名
    schema_version: int = SCHEMA_VERSION
    # 界面布局记忆
    window_geometry: str = ""    # base64(saveGeometry())
    chat_visible: bool = True
    params_visible: bool = True
    files_visible: bool = True
    history_visible: bool = True
    chat_width: int = 440
    params_width: int = 380
    library_height: int = 200
    # 项目化工作区
    project_dir: str = ""            # 空 = 文档/Truffle Projects
    autosave_interval: int = 60      # 秒；0 = 关闭定时自动保存
    history_steps: int = 20          # 每图保存/可回退的历史步数；0~100
    project_view: str = "card"       # card | list
    default_cover_mode: str = "active"  # active | first | tiles | custom
    project_assoc: bool = False      # 关联 .truffle 项目文件
    session_migrated: bool = False   # 旧 session.json 是否已迁移

    # ---------- 读写 ----------
    @classmethod
    def load(cls) -> "AppSettings":
        llm = LLMSettings()
        data = cls(llm=llm)
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for key, value in raw.get("llm", {}).items():
                    if hasattr(llm, key) and value not in (None, ""):
                        setattr(llm, key, value)
                cb = raw.get("close_behavior")
                if cb in CLOSE_BEHAVIORS:
                    data.close_behavior = cb
                if raw.get("theme") in ("dark", "light"):
                    data.theme = raw["theme"]
                if raw.get("language") in ("zh", "en"):
                    data.language = raw["language"]
                if isinstance(raw.get("update_url"), str):
                    data.update_url = raw["update_url"]
                if isinstance(raw.get("auto_check_update"), bool):
                    data.auto_check_update = raw["auto_check_update"]
                if isinstance(raw.get("file_assoc"), bool):
                    data.file_assoc = raw["file_assoc"]
                for key in ("lc_app_id", "lc_app_key", "lc_server_url", "community_url",
                            "account_token", "account_username"):
                    if isinstance(raw.get(key), str):
                        setattr(data, key, raw[key])
                if isinstance(raw.get("require_login"), bool):
                    data.require_login = raw["require_login"]
                # 迁移：旧配置没有 schema_version，保持默认字段即可
                data.schema_version = SCHEMA_VERSION
                if isinstance(raw.get("window_geometry"), str):
                    data.window_geometry = raw["window_geometry"]
                for key in ("chat_visible", "params_visible", "files_visible", "history_visible"):
                    if isinstance(raw.get(key), bool):
                        setattr(data, key, raw[key])
                for key in ("chat_width", "params_width", "library_height"):
                    value = raw.get(key)
                    if isinstance(value, int) and value > 0:
                        setattr(data, key, value)
                if isinstance(raw.get("project_dir"), str):
                    data.project_dir = raw["project_dir"]
                value = raw.get("autosave_interval")
                if isinstance(value, int) and value >= 0:
                    data.autosave_interval = value
                value = raw.get("history_steps")
                if isinstance(value, int) and 0 <= value <= 100:
                    data.history_steps = value
                if raw.get("project_view") in ("card", "list"):
                    data.project_view = raw["project_view"]
                if raw.get("default_cover_mode") in ("active", "first", "tiles", "custom"):
                    data.default_cover_mode = raw["default_cover_mode"]
                if isinstance(raw.get("project_assoc"), bool):
                    data.project_assoc = raw["project_assoc"]
                if isinstance(raw.get("session_migrated"), bool):
                    data.session_migrated = raw["session_migrated"]
            except (json.JSONDecodeError, OSError):
                pass
        return data

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.llm.api_key)
