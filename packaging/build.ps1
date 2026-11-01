# Truffle 打包脚本（唯一入口，自动递增版本号）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#       在上次版本基础上自动递增（默认 patch：0.0.1 -> 0.0.2）
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Bump minor
#       递增次版本（0.0.2 -> 0.1.0）；-Bump major 同理
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Version 1.0.0
#       强制使用指定版本（仍会写回并作为下次的基准）
#
# 版本规则：以 pyproject.toml 的 version 为「上次打包版本」，每次打包自动 +1，
#          打包前写回（使 exe/安装包内嵌新版本），失败则回滚。
# 产物：dist\Truffle\（绿色版）+ dist\installer\Truffle-Setup-<版本>.exe

param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch",
    [string]$Version = "",
    # 增量打包（复用 build\work 缓存，明显更快；但可能残留旧文件，正式发版建议不带）
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # packaging 的上级 = 项目根
$python = Join-Path $root ".venv\Scripts\python.exe"
$pyproject = Join-Path $root "pyproject.toml"
$init_file = Join-Path $root "src\truffle\__init__.py"

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境 ($python)。请先双击 Truffle.bat 初始化环境。"
}

# ---------- 版本号读写 ----------
function Get-CurrentVersion {
    $match = Select-String -Path $pyproject -Pattern '^\s*version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $match) { throw "无法从 pyproject.toml 读取版本号" }
    return $match.Matches[0].Groups[1].Value
}

function Get-NextVersion([string]$current, [string]$kind) {
    $parts = @($current.Split('.'))
    while ($parts.Count -lt 3) { $parts += '0' }
    [int]$major = $parts[0]; [int]$minor = $parts[1]; [int]$patch = $parts[2]
    switch ($kind) {
        "major" { $major++; $minor = 0; $patch = 0 }
        "minor" { $minor++; $patch = 0 }
        default { $patch++ }
    }
    return "$major.$minor.$patch"
}

function Set-Version([string]$value) {
    $content = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
    $content = [regex]::Replace($content, '(?m)^version\s*=\s*"[^"]+"', "version = `"$value`"", 1)
    [System.IO.File]::WriteAllText($pyproject, $content, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path $init_file) {
        $init = Get-Content -LiteralPath $init_file -Raw -Encoding UTF8
        $init = [regex]::Replace($init, '__version__\s*=\s*"[^"]+"', "__version__ = `"$value`"", 1)
        [System.IO.File]::WriteAllText($init_file, $init, (New-Object System.Text.UTF8Encoding($false)))
    }
}

function Find-Iscc {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($c in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )) { if (Test-Path $c) { return $c } }
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

# ---------- 计算并写回新版本 ----------
$current = Get-CurrentVersion
if ($Version) { $next = $Version } else { $next = Get-NextVersion $current $Bump }
Write-Host "版本号：$current -> $next"

Set-Version $next   # 打包前写入，确保产物内嵌新版本

try {
    # 0. 确保打包依赖
    & $python -m pip show pyinstaller *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[0/2] 安装打包依赖 pyinstaller ..."
        & $python -m pip install -r (Join-Path $PSScriptRoot "requirements-build.txt") `
            -i https://pypi.tuna.tsinghua.edu.cn/simple
        if ($LASTEXITCODE -ne 0) { throw "打包依赖安装失败" }
    }

    # 1. PyInstaller 绿色版
    Write-Host "[1/2] PyInstaller 打包（green 版）..."
    $pyiArgs = @(
        "-m", "PyInstaller", (Join-Path $PSScriptRoot "Truffle.spec"), "--noconfirm",
        "--distpath", (Join-Path $root "dist"), "--workpath", (Join-Path $root "build\work")
    )
    if (-not $NoClean) { $pyiArgs += "--clean" } else { Write-Host "    （-NoClean：增量打包）" }
    & $python @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

    $green = Join-Path $root "dist\Truffle"
    $sizeMB = [math]::Round((Get-ChildItem $green -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "    绿色版输出: $green  (约 $sizeMB MB)"

    # 2. Inno Setup 安装包
    $iscc = Find-Iscc
    if (-not $iscc) {
        Write-Warning "未检测到 Inno Setup 6，跳过安装包制作（绿色版已就绪）。"
        Write-Host "    安装 Inno Setup 后重跑本脚本即可生成安装包: https://jrsoftware.org/isdl.php"
    } else {
        Write-Host "[2/2] Inno Setup 制作安装包... (使用 $iscc)"
        & $iscc "/DMyAppVersion=$next" (Join-Path $PSScriptRoot "installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败" }
        $installer = Join-Path $root "dist\installer"
        Write-Host "    安装包输出: $installer"
        Get-ChildItem $installer -Filter "*.exe" | Sort-Object LastWriteTime -Descending |
            Select-Object -First 1 | ForEach-Object {
                Write-Host "    -> $($_.Name)  ($([math]::Round($_.Length/1MB,1)) MB)"
            }
    }

    Write-Host "打包完成：版本 $next"
}
catch {
    Set-Version $current
    Write-Warning "打包失败，版本号已回滚为 $current"
    throw
}
