# Truffle 一键打包脚本
# 用法（在项目根或任意位置）： powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# 流程：PyInstaller 打出绿色版 -> 若装了 Inno Setup 再打出安装包

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # packaging 的上级 = 项目根
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境 ($python)。请先双击 Truffle.vbs 初始化环境。"
}

# 0. 确保打包依赖已安装
& $python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[0/2] 安装打包依赖 pyinstaller ..."
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements-build.txt") `
        -i https://pypi.tuna.tsinghua.edu.cn/simple
    if ($LASTEXITCODE -ne 0) { throw "打包依赖安装失败" }
}

# 1. PyInstaller 打出绿色版
Write-Host "[1/2] PyInstaller 打包（green 版）..."
& $python -m PyInstaller (Join-Path $PSScriptRoot "Truffle.spec") `
    --noconfirm --clean `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build\work")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$green = Join-Path $root "dist\Truffle"
$sizeMB = [math]::Round((Get-ChildItem $green -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "    绿色版输出: $green  (约 $sizeMB MB)"

# 2. 若已安装 Inno Setup，则制作安装包
function Find-Iscc {
    # a) PATH 中
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # b) 常见安装路径
    foreach ($c in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )) { if (Test-Path $c) { return $c } }
    # c) 注册表卸载项里的安装位置
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $entry = Get-ItemProperty $keys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "Inno Setup*" -and $_.InstallLocation } |
        Select-Object -First 1
    if ($entry) {
        $candidate = Join-Path $entry.InstallLocation.TrimEnd('\') "ISCC.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

$iscc = Find-Iscc

if (-not $iscc) {
    Write-Warning "未检测到 Inno Setup 6，跳过安装包制作（绿色版已就绪）。"
    Write-Host "    安装 Inno Setup 后重跑本脚本即可生成安装包: https://jrsoftware.org/isdl.php"
    exit 0
}

Write-Host "[2/2] Inno Setup 制作安装包... (使用 $iscc)"
& $iscc (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败" }

$installer = Join-Path $root "dist\installer"
Write-Host "    安装包输出: $installer"
Get-ChildItem $installer -Filter *.exe | ForEach-Object {
    Write-Host "    -> $($_.Name)  ($([math]::Round($_.Length/1MB,1)) MB)"
}
Write-Host "完成。"
