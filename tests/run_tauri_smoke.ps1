param(
    [switch]$SkipBuild,
    [int]$CdpPort = 9444
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$appPath = Join-Path $repo "frontend\src-tauri\target\debug\app.exe"
$gatewaySuffix = "target\debug\resources\app\gateway\server.py"
$mcpRootSuffix = "target\debug\resources\mcps\"
$screenshot = Join-Path $repo "build\test-artifacts\tauri-smoke.png"
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
$result = 1
$errorText = $null
$app = $null

if (-not $SkipBuild) {
    & python (Join-Path $repo "packaging\stage_pkg.py")
    if ($LASTEXITCODE -ne 0) {
        throw "stage_pkg.py failed with exit code $LASTEXITCODE"
    }
    $env:PATH = "$cargoBin;$env:PATH"
    & npm --prefix (Join-Path $repo "frontend") exec tauri build -- --debug --no-bundle
    if ($LASTEXITCODE -ne 0) {
        throw "Tauri debug build failed with exit code $LASTEXITCODE"
    }
}

$appPath = (Resolve-Path -LiteralPath $appPath).Path
$existingApp = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq $appPath
})
$existingGateway = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -like "*$gatewaySuffix*"
})
$existingMcp = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*$mcpRootSuffix*" -or $_.ExecutablePath -like "*$mcpRootSuffix*"
})
if ($existingApp.Count -ne 0 -or $existingGateway.Count -ne 0 -or $existingMcp.Count -ne 0) {
    throw "Refusing to start smoke test while a debug app, Gateway, or packaged MCP is running"
}

$env:PRISM_WEBVIEW_BROWSER_ARGS = "--remote-debugging-port=$CdpPort --remote-allow-origins=*"
$app = Start-Process -FilePath $appPath -PassThru -WindowStyle Hidden

try {
    & python (Join-Path $PSScriptRoot "tauri_webview_smoke.py") $CdpPort $screenshot
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright smoke failed with exit code $LASTEXITCODE"
    }

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Process -Id $app.Id -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
    if (Get-Process -Id $app.Id -ErrorAction SilentlyContinue) {
        throw "Tauri app did not exit after the close button was clicked"
    }

    $remainingGateway = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*$gatewaySuffix*"
    })
    if ($remainingGateway.Count -ne 0) {
        throw "Bundled Gateway remained after window close: $($remainingGateway.ProcessId -join ',')"
    }
    $remainingMcp = @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*$mcpRootSuffix*" -or $_.ExecutablePath -like "*$mcpRootSuffix*"
    })
    if ($remainingMcp.Count -ne 0) {
        throw "Packaged MCP remained after window close: $($remainingMcp.ProcessId -join ',')"
    }

    Write-Output "TAURI_SMOKE_PASS app_pid=$($app.Id) remaining_gateway=0 remaining_mcp=0 screenshot=$screenshot"
    $result = 0
}
catch {
    $errorText = $_.Exception.Message
}
finally {
    Remove-Item Env:PRISM_WEBVIEW_BROWSER_ARGS -ErrorAction SilentlyContinue
    if ($app -and (Get-Process -Id $app.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
    }
    if ($result -ne 0) {
        Get-CimInstance Win32_Process | Where-Object {
            ($_.Name -eq "python.exe" -and $_.CommandLine -like "*$gatewaySuffix*") -or
            $_.CommandLine -like "*$mcpRootSuffix*" -or $_.ExecutablePath -like "*$mcpRootSuffix*"
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

if ($errorText) {
    Write-Output "TAURI_SMOKE_FAIL $errorText"
}
exit $result
