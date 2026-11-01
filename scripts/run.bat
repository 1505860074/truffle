@echo off
chcp 65001 >nul
setlocal enableextensions
rem Truffle dev launcher (batch only).
rem
rem Usage:
rem   scripts\run.bat             open the app window
rem   scripts\run.bat -Headless   headless smoke test (offscreen, auto-quits, prints error.log)
rem   scripts\run.bat headless    same as -Headless
rem
rem Normal mode forces QT_QPA_PLATFORM=windows so a leftover "offscreen"
rem in the same shell can never hide the window again.

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
pushd "%ROOT%" >nul
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "LOG=%APPDATA%\Truffle\error.log"

if not exist "%PY%" (
    echo [Truffle] venv not found: %PY%
    echo [Truffle] Run Truffle.bat first to set up the environment.
    popd >nul
    exit /b 1
)

if /i "%~1"=="-Headless" goto :headless
if /i "%~1"=="--headless" goto :headless
if /i "%~1"=="headless" goto :headless

:windowed
set "QT_QPA_PLATFORM=windows"
echo [Truffle] launching (windowed): "%PY%" run.py
"%PY%" run.py
set "CODE=%ERRORLEVEL%"
popd >nul
exit /b %CODE%

:headless
if exist "%LOG%" del /q "%LOG%"
set "QT_QPA_PLATFORM=offscreen"
set "QT_QPA_FONTDIR=%WINDIR%\Fonts"
set "TRUFFLE_SMOKE=1"
echo [Truffle] headless: launching offscreen smoke test...
"%PY%" run.py
set "CODE=%ERRORLEVEL%"
echo [Truffle] headless: exit code %CODE%
if not exist "%LOG%" goto :headless_ok
echo [Truffle] ERROR LOG:
type "%LOG%"
set "CODE=1"
goto :headless_done

:headless_ok
echo [Truffle] no error.log

:headless_done
popd >nul
exit /b %CODE%
