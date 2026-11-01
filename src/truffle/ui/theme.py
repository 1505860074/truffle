"""主题：深色 / 浅色配色。各自定义控件通过 `apply_theme()` 读取当前配色。

用法：
    theme.set_theme("light")
    theme.apply_app_palette(QApplication.instance())
    widget.apply_theme()
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

PALETTES: dict[str, dict[str, object]] = {
    "dark": {
        "window": "#2b2b2b", "window_text": "#e6e6e6",
        "base": "#1a1a1a", "text": "#e6e6e6",
        "button": "#2b2b2b", "button_text": "#e6e6e6",
        "highlight": "#8a6f37", "highlight_text": "#ffffff",
        "panel_bg": "#202020", "border": "#3a3a3a",
        "accent": "#e7c87e", "accent_bg": "#6b4f1d",
        "text_dim": "#8f8f8f",
        "handle": "rgba(231,200,126,55)", "handle_end": "rgba(231,200,126,0)",
        "log_bg": "#141414", "log_text": "#b8b8b8",
        "chat_bg": "#181818",
        "bubble_user": "#3f7a3f", "bubble_user_fg": "#eaf7ea",
        "bubble_other": "#2f2f2f", "bubble_other_fg": "#e6e6e6",
        "canvas_bg": "#1e1e1e",
        "add_bg": "#f3e2a8", "add_fg": "#3a2716",
        "icon_on": "#8a6f37", "icon_off": "#8a8a8a",
        "watermark": "#e7c87e", "watermark_alpha": 30,
    },
    "light": {
        "window": "#f2f2f2", "window_text": "#1f1f1f",
        "base": "#ffffff", "text": "#1f1f1f",
        "button": "#e6e6e6", "button_text": "#1f1f1f",
        "highlight": "#2f6fd0", "highlight_text": "#ffffff",
        "panel_bg": "#f7f7f7", "border": "#c8c8c8",
        "accent": "#1f5fbf", "accent_bg": "#d6e4ff",
        "text_dim": "#6b6b6b",
        "handle": "rgba(47,111,208,80)", "handle_end": "rgba(47,111,208,0)",
        "log_bg": "#ffffff", "log_text": "#333333",
        "chat_bg": "#f7f7f7",
        "bubble_user": "#95ec69", "bubble_user_fg": "#1f1f1f",
        "bubble_other": "#ffffff", "bubble_other_fg": "#1f1f1f",
        "canvas_bg": "#e6e6e6",
        "add_bg": "#d6e4ff", "add_fg": "#1f5fbf",
        "icon_on": "#2f6fd0", "icon_off": "#7a7a7a",
        "watermark": "#1f5fbf", "watermark_alpha": 40,
    },
}

_current = "dark"


def set_theme(name: str) -> None:
    global _current
    if name in PALETTES:
        _current = name


def current_name() -> str:
    return _current


def current() -> dict[str, object]:
    return PALETTES[_current]


def c(key: str) -> QColor:
    return QColor(str(current()[key]))


def apply_app_palette(app) -> None:
    """给标准控件（菜单、对话框、输入框等）设置系统调色板。"""
    t = current()
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(str(t["window"])))
    pal.setColor(QPalette.WindowText, QColor(str(t["window_text"])))
    pal.setColor(QPalette.Base, QColor(str(t["base"])))
    pal.setColor(QPalette.AlternateBase, QColor(str(t["panel_bg"])))
    pal.setColor(QPalette.Text, QColor(str(t["text"])))
    pal.setColor(QPalette.Button, QColor(str(t["button"])))
    pal.setColor(QPalette.ButtonText, QColor(str(t["button_text"])))
    pal.setColor(QPalette.ToolTipBase, QColor(str(t["panel_bg"])))
    pal.setColor(QPalette.ToolTipText, QColor(str(t["text"])))
    pal.setColor(QPalette.Highlight, QColor(str(t["highlight"])))
    pal.setColor(QPalette.HighlightedText, QColor(str(t["highlight_text"])))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(str(t["text_dim"])))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(str(t["text_dim"])))
    app.setPalette(pal)

    # 应用级样式：兜底所有未自定义的控件，避免浅色模式下残留白字
    app.setStyleSheet(
        f"QWidget {{ color: {t['text']}; }}"
        f"QMenuBar {{ background: {t['window']}; color: {t['window_text']}; }}"
        f"QMenuBar::item:selected {{ background: {t['highlight']}; color: {t['highlight_text']}; }}"
        f"QMenu {{ background: {t['window']}; color: {t['window_text']}; "
        f"border: 1px solid {t['border']}; }}"
        f"QMenu::item:selected {{ background: {t['highlight']}; color: {t['highlight_text']}; }}"
        f"QToolTip {{ background: {t['panel_bg']}; color: {t['text']}; "
        f"border: 1px solid {t['border']}; }}"
        f"QStatusBar {{ background: {t['window']}; color: {t['window_text']}; }}"
        f"QPushButton {{ color: {t['button_text']}; }}"
        f"QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ "
        f"background: {t['base']}; color: {t['text']}; }}"
    )
