#requires -Version 5.1
<#
.SYNOPSIS
    啟動 Agentic SDK Gateway 與 Multi-Model Dashboard。

.DESCRIPTION
    F-04 — 統一啟動入口。在執行前需確認:
      1. 上游 amd-ryzen-ai-benchmark 的 api.py 已於另一個視窗執行(例: localhost:8000)
      2. 已將 .env.example 複製為 .env 並填好實際值
      3. 已執行過 `uv sync --extra dev`

    本指令會在新視窗啟動 Dashboard(預設 8501),
    並於目前視窗前景跑 Gateway(預設 8080)。
    Gateway 啟動後,健康檢查會自動偵測上游是否就緒,
    上游尚未開啟時 Gateway 仍會持續執行,以利後續上游補開時自動恢復。

    若僅想啟 Gateway,加 -GatewayOnly。
#>

[CmdletBinding()]
param(
    [switch]$SkipEnvCheck,
    [switch]$GatewayOnly
)

$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not $SkipEnvCheck -and -not (Test-Path ".env")) {
        Write-Warning "找不到 .env。請先執行: Copy-Item .env.example .env;再填入實際值。"
        exit 1
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Warning "uv 未安裝。請依 https://github.com/astral-sh/uv 安裝後重試,並執行: uv sync --extra dev"
        exit 1
    }

    if (-not $GatewayOnly) {
        $dashboardScript = Join-Path $PSScriptRoot "start_dashboard.ps1"
        if (Test-Path $dashboardScript) {
            Write-Host "[Agentic SDK] 於新視窗啟動 Dashboard ..." -ForegroundColor Cyan
            Start-Process -FilePath "powershell.exe" -ArgumentList @(
                "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $dashboardScript
            ) | Out-Null
        } else {
            Write-Warning "找不到 $dashboardScript,跳過 Dashboard 啟動。"
        }
    }

    Write-Host "[Agentic SDK] 啟動 Gateway ..." -ForegroundColor Cyan
    uv run python -m agentic_sdk.gateway
}
finally {
    Pop-Location
}

