# 干净主机 MSI 安装烟雾测试（ROADMAP 施工入口 15）：
# 静默安装 → 校验安装树（含禁入项）→ 启动并确认 bundled Gateway 子进程 → 收口 → 静默卸载。
# 注意（NOTES.md 2026-07-10）：msiexec 无界面客户端可能先于 Installer 服务事务返回，
# 所有状态断言都用轮询而不是相信客户端退出瞬间的文件系统。
param(
    [string]$MsiPath = "",
    [string]$InstallDir = "$env:ProgramFiles\Prism Motif"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if (-not $MsiPath) {
    $MsiPath = Get-ChildItem (Join-Path $repo "frontend\src-tauri\target\release\bundle\msi\*.msi") |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $MsiPath -or -not (Test-Path $MsiPath)) { throw "MSI not found: $MsiPath" }
Write-Output "MSI: $MsiPath"

function Wait-Until([scriptblock]$Condition, [int]$TimeoutSeconds, [string]$What) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return }
        Start-Sleep -Seconds 2
    }
    Write-InstallDiagnostics
    throw "timed out waiting for: $What"
}

# 超时自诊断：把失败原因直接摊在步骤日志里，省得下 artifact 再猜。
function Write-InstallDiagnostics {
    Write-Output "---- diagnostics ----"
    foreach ($log in @("msi-install.log", "msi-uninstall.log")) {
        if (Test-Path $log) {
            Write-Output "== tail of $log =="
            Get-Content $log -Tail 60 | ForEach-Object { $_ }
        }
    }
    Write-Output "== $env:ProgramFiles =="
    Get-ChildItem $env:ProgramFiles -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    Write-Output "== registry uninstall entries matching Prism =="
    foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")) {
        Get-ChildItem $hive -ErrorAction SilentlyContinue | ForEach-Object {
            $name = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName
            if ($name -like "*Prism*") { Write-Output "$name  ($($_.PSChildName))" }
        }
    }
    Write-Output "== msiexec processes =="
    Get-Process msiexec -ErrorAction SilentlyContinue | Select-Object Id, StartTime | Format-Table | Out-String
    Write-Output "---- end diagnostics ----"
}

# WebView2 Evergreen 运行时（干净 runner 可能没有；官方 bootstrapper）
$wv2Key = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
if (-not (Test-Path $wv2Key)) {
    Write-Output "installing WebView2 Evergreen runtime ..."
    $bootstrapper = Join-Path $env:TEMP "MicrosoftEdgeWebview2Setup.exe"
    Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" `
        -OutFile $bootstrapper -UseBasicParsing
    Start-Process -FilePath $bootstrapper -ArgumentList "/silent /install" -Wait
}

# ---- 安装 ----
$install = Start-Process msiexec -ArgumentList "/i `"$MsiPath`" /qn /norestart /L*v msi-install.log" -Wait -PassThru
Write-Output "msiexec client exit: $($install.ExitCode)"
if ($install.ExitCode -ne 0) { Write-InstallDiagnostics; throw "msiexec install exit $($install.ExitCode)" }
$exe = Join-Path $InstallDir "Prism Motif.exe"
Wait-Until { Test-Path $exe } 1200 "installed exe at $exe"

# ---- 安装树校验：必需项存在、禁入项缺席 ----
$bundledPython = Join-Path $InstallDir "resources\python\python.exe"
$gatewayScript = Join-Path $InstallDir "resources\app\gateway\server.py"
$mcpConfig = Join-Path $InstallDir "resources\app\config\mcp_servers.json"
foreach ($required in @($bundledPython, $gatewayScript, $mcpConfig,
        (Join-Path $InstallDir "resources\mcps\reaper-mcp\server\reaper_mcp_server.py"),
        (Join-Path $InstallDir "resources\mcps\music-perception\music_perception.exe"))) {
    if (-not (Test-Path $required)) { throw "missing from install tree: $required" }
}
$configNames = (Get-Content $mcpConfig -Raw | ConvertFrom-Json).servers.name
if ($configNames -match "system") { throw "packaged mcp config contains system mcp: $configNames" }
if (Test-Path (Join-Path $InstallDir "resources\mcps\system-mcp")) { throw "system-mcp bundled into install tree" }
foreach ($forbidden in @("resources\app\config\secrets.json", "resources\app\data\threads", "resources\app\data\memory")) {
    if (Test-Path (Join-Path $InstallDir $forbidden)) { throw "private data leaked into install tree: $forbidden" }
}
Write-Output "install tree OK"

# ---- 启动：app 进程存活 + bundled Gateway 子进程出现 ----
$app = Start-Process -FilePath $exe -PassThru
try {
    Wait-Until {
        @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -like "*resources\app\gateway\server.py*"
        }).Count -gt 0
    } 120 "bundled gateway child process"
    if (-not (Get-Process -Id $app.Id -ErrorAction SilentlyContinue)) { throw "app exited prematurely" }
    Write-Output "launch OK: app pid $($app.Id) + bundled gateway running"
}
finally {
    # release 构建没有 CDP 测试入口（安全决策），收口用进程树终止
    if (Get-Process -Id $app.Id -ErrorAction SilentlyContinue) {
        & taskkill /PID $app.Id /T /F | Out-Null
    }
}
Wait-Until {
    @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq "python.exe" -and $_.CommandLine -like "*resources\app\gateway*") -or
        $_.CommandLine -like "*resources\mcps\*" -or $_.ExecutablePath -like "*resources\mcps\*"
    }).Count -eq 0
} 60 "gateway/MCP process tree to exit"
Write-Output "shutdown OK: no leftover gateway/MCP processes"

# ---- 卸载 ----
$uninstall = Start-Process msiexec -ArgumentList "/x `"$MsiPath`" /qn /norestart /L*v msi-uninstall.log" -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "msiexec uninstall exit $($uninstall.ExitCode)" }
Wait-Until { -not (Test-Path $exe) } 600 "installed exe removal"
Write-Output "MSI_SMOKE_PASS install/launch/uninstall all verified"
