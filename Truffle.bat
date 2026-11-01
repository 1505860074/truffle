@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title Truffle

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "TRUFFLE_HOME=%ROOT%.truffle_dev"
set "TRUFFLE_PROJECTS=%ROOT%projects"
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

if not exist "%PY%" (
    echo [Truffle] 首次运行：正在准备运行环境，请稍候（仅需一次）...
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [错误] 未检测到 Python。请先安装 Python 3.10 或更高版本，
        echo        安装时务必勾选 "Add Python to PATH"，然后重新双击本文件。
        echo.
        pause
        exit /b 1
    )
    python -m venv "%ROOT%.venv"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
    echo [Truffle] 正在安装依赖，约 1~3 分钟，请勿关闭窗口...
    "%PY%" -m pip install --upgrade pip -i %MIRROR% -q
    "%PY%" -m pip install -r "%ROOT%requirements.txt" -i %MIRROR%
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重新双击本文件。
        pause
        exit /b 1
    )
    echo [Truffle] 环境准备完成。
)

echo [Truffle] 正在启动...
start "" "%ROOT%.venv\Scripts\pythonw.exe" "%ROOT%run.py"
