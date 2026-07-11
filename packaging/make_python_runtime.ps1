# 重建 MSI 内置的 CPython 运行时（frontend/src-tauri/resources/python）。
# NuGet python 包的 Windows 二进制止于 3.10.11（3.10.12+ 仅源码安全版本）；
# 本机已验收的 v0.1.1 bundle 是手工装配的 3.10.14，网关只用 stdlib + keyring，
# 补丁级差异无行为影响。注意：不装 openai —— 核心 reasoner 走 stdlib HTTP。
param([switch]$Force)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $repo "frontend\src-tauri\resources\python"
$pythonVersion = "3.10.11"

if (Test-Path (Join-Path $dest "python.exe")) {
    if (-not $Force) {
        Write-Output "bundled python already present: $dest  (use -Force to rebuild)"
        exit 0
    }
    Remove-Item -Recurse -Force $dest
}

$work = Join-Path $repo "build\python-runtime"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Path $work -Force | Out-Null

$nupkg = Join-Path $work "python.$pythonVersion.zip"
Write-Output "downloading NuGet python $pythonVersion ..."
Invoke-WebRequest -Uri "https://www.nuget.org/api/v2/package/python/$pythonVersion" `
    -OutFile $nupkg -UseBasicParsing
Expand-Archive -Path $nupkg -DestinationPath (Join-Path $work "pkg")

New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
Copy-Item -Recurse (Join-Path $work "pkg\tools") $dest

& (Join-Path $dest "python.exe") -m ensurepip --default-pip
if ($LASTEXITCODE -ne 0) { throw "ensurepip failed" }
& (Join-Path $dest "python.exe") -m pip install --no-warn-script-location --upgrade pip keyring
if ($LASTEXITCODE -ne 0) { throw "pip install keyring failed" }

$version = & (Join-Path $dest "python.exe") --version
Write-Output "bundled runtime ready: $version at $dest"
