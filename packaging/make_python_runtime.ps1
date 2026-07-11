# 重建 MSI 内置的 CPython 运行时（frontend/src-tauri/resources/python）。
# 与已验收的 v0.1.1 bundle 保持一致：NuGet python 3.10.14 全量布局 + pip + keyring。
# 注意：不装 openai —— 核心 reasoner 走 stdlib HTTP，已由 v0.1.1 MSI 真机验收证实。
param([switch]$Force)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $repo "frontend\src-tauri\resources\python"
$pythonVersion = "3.10.14"

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
