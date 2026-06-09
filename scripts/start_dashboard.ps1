<#
.SYNOPSIS
    啟動 Multi-Model Dashboard(Streamlit)。

.DESCRIPTION
    B-08 — 與 Gateway 同 venv、獨立行程。Dashboard 預設讀取 .env 內的
    DASHBOARD_PORT 與 GATEWAY_HOST/PORT,可在 UI 側欄即時切換資料來源至 Mock 模式。

    使用前提:
      1. 已執行 `uv sync --extra dev`
      2. (可選)Gateway 已透過 .\scripts\start.ps1 啟動;否則 sidebar 切到 Mock
#>

$ErrorActionPreference = "Stop"

try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv 未安裝。請依 https://github.com/astral-sh/uv 安裝後執行: uv sync --extra dev"
        exit 1
    }

    # 從 .env 抽 DASHBOARD_PORT(若存在),否則用 Streamlit 預設
    $port = "8501"
    if (Test-Path ".env") {
        $match = Select-String -Path ".env" -Pattern "^\s*DASHBOARD_PORT\s*=\s*(\d+)" -ErrorAction SilentlyContinue
        if ($match) { $port = $match.Matches[0].Groups[1].Value }
    }

    Write-Host "[Agentic SDK] 啟動 Dashboard,port=$port ..." -ForegroundColor Cyan
    uv run streamlit run dashboard\app.py `
        --server.port=$port `
        --server.headless=true `
        --browser.gatherUsageStats=false
} catch {
    Write-Error $_
    exit 1
}
