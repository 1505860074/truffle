"""Windows 文件关联（写 HKCU，按用户，无需管理员）。

让图片扩展名出现在「打开方式 → Truffle」里（不强制设为默认）。
仅在打包版可用（开发态 sys.executable 是 python.exe）。
"""

from __future__ import annotations

import sys

_PROGID = "Truffle.Image"
_EXTS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"]
_PROJECT_PROGID = "Truffle.Project"
_PROJECT_EXTS = [".truffle"]
_CLASSES = r"Software\Classes"


def _exe_path() -> str:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("文件关联仅在打包版可用")
    return sys.executable


def _write(path: str, name: str, value: str) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _delete_tree(path: str) -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def set_file_association(enable: bool) -> None:
    exe = _exe_path()
    if enable:
        _write(rf"{_CLASSES}\{_PROGID}", "", "Truffle 图片")
        _write(rf"{_CLASSES}\{_PROGID}\DefaultIcon", "", f'"{exe}",0')
        _write(rf"{_CLASSES}\{_PROGID}\shell\open\command", "", f'"{exe}" "%1"')
        _write(rf"{_CLASSES}\Applications\Truffle.exe\shell\open\command", "", f'"{exe}" "%1"')
        for ext in _EXTS:
            _write(rf"{_CLASSES}\{ext}\OpenWithProgids", _PROGID, "")
    else:
        import winreg

        _delete_tree(rf"{_CLASSES}\{_PROGID}")
        _delete_tree(rf"{_CLASSES}\Applications\Truffle.exe")
        for ext in _EXTS:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, rf"{_CLASSES}\{ext}\OpenWithProgids",
                    0, winreg.KEY_ALL_ACCESS,
                ) as key:
                    winreg.DeleteValue(key, _PROGID)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def set_project_association(enable: bool) -> None:
    exe = _exe_path()
    if enable:
        _write(rf"{_CLASSES}\{_PROJECT_PROGID}", "", "Truffle 项目")
        _write(rf"{_CLASSES}\{_PROJECT_PROGID}\DefaultIcon", "", f'"{exe}",0')
        _write(rf"{_CLASSES}\{_PROJECT_PROGID}\shell\open\command", "", f'"{exe}" "%1"')
        for ext in _PROJECT_EXTS:
            _write(rf"{_CLASSES}\{ext}", "", _PROJECT_PROGID)
            _write(rf"{_CLASSES}\{ext}\OpenWithProgids", _PROJECT_PROGID, "")
    else:
        import winreg

        _delete_tree(rf"{_CLASSES}\{_PROJECT_PROGID}")
        for ext in _PROJECT_EXTS:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, rf"{_CLASSES}\{ext}", 0, winreg.KEY_ALL_ACCESS
                ) as key:
                    if winreg.QueryValue(key, "") == _PROJECT_PROGID:
                        winreg.DeleteValue(key, "")
            except FileNotFoundError:
                pass
            except OSError:
                pass
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, rf"{_CLASSES}\{ext}\OpenWithProgids",
                    0, winreg.KEY_ALL_ACCESS,
                ) as key:
                    winreg.DeleteValue(key, _PROJECT_PROGID)
            except FileNotFoundError:
                pass
            except OSError:
                pass

