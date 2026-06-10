# Portfolio Optimizer

**投資組合策略產生工具**：在本地 WebUI 設計並回測量化策略，滿意後將 `cloud_function/` 整包部署至 Google Cloud Function；GCF 每日由 Cloud Scheduler 觸發，跑當日回測並透過 LINE Bot 推播持倉建議。

---

## 工作流總覽

```
WebUI 調整策略參數 → 回測視覺化確認
        ↓ 儲存策略（寫入 config.yaml）
cloud_function/config.yaml（憑證 + 策略）
        ↓ git push → GitHub Actions 自動部署
Google Cloud Function（Python 3.12）
        ↓ Cloud Scheduler 每日觸發
LINE Bot 推播持倉建議
        ↓ demo.py 驗證 GCF endpoint
確認部署成功
```

下游整合（規劃中）：GCF 輸出的 `holdings` 陣列可接 Claude Dispatch 做質化分析（財報、新聞），輸出最終買進清單。

---

## 目錄結構

```
Portfolio_Optimizer/
├── cloud_function/      ← 上傳至 GCF 的完整套件（單層，無子目錄）
│   ├── main.py              GCF entry point（hello_http）
│   ├── engine.py            回測引擎：指標、再平衡、run_pipeline()
│   ├── data.py              資料層：TradingView / yfinance / FX
│   ├── config.yaml          憑證 + 策略參數（唯一配置來源）
│   └── requirements.txt     GCF 相依套件
│
├── dashboard.py         ← 本地 WebUI 入口（Flask，直接 import engine）
├── webui/               ← WebUI 前端資產（templates / static）
│   └── requirements.txt     本地 Flask 相依（獨立，不上傳 GCF）
│
├── demo.py              ← GCF endpoint 驗證客戶端（HTTP，不 import engine）
└── docs/API_SPEC.md     ← GCF HTTP 介面契約
```

---

## 本地開發環境建置

本專案以 **[uv](https://docs.astral.sh/uv/)** 管理本地 Python 環境，鎖定 Python 3.12 與 GCF 執行環境一致。

### 前置：安裝 uv

```powershell
# Windows（PowerShell）
irm https://astral.sh/uv/install.ps1 | iex
```

### 初始化與安裝相依

```powershell
# 1. 在專案根目錄初始化 Python 3.12 環境
uv init -p 3.12

# 2. 建立虛擬環境（.venv）
uv venv

# 3. 安裝所有相依套件至 .venv
uv pip install -r cloud_function/requirements.txt
```

> 只需安裝一次。後續執行改用 `uv run`，不需要手動 `activate`。

---

## 設定 config.yaml

`cloud_function/config.yaml` 是本專案唯一的配置來源，分憑證區（手動填入）與策略區（WebUI 寫入）：

```yaml
# ── 憑證區 ─────────────────────────────────────────────────────
tradingview:
  session_id: "你的 sessionid cookie"    # DevTools → Application → Cookies
  watchlist_id: "觀察清單數字 ID"          # TradingView watchlist URL 中的數字
  expires_at: "YYYY-MM-DD"               # 更新日 +30 天

line:
  channel_access_token: ""              # LINE Developers → Messaging API
  group_id: ""                          # 從 Webhook event 取得

# ── 策略區（由 WebUI「儲存策略」按鈕寫入）──────────────────────
backtest:
  initial_capital: 1000000
  amount_per_stock: 100000
  max_positions: 10
  market: "us"                          # us | tw | global
  start_date: "2025-01-01"
  rebalance_freq: "weekly"              # daily | weekly | monthly
  # ... 買進/賣出條件由 WebUI 控制
```

**TradingView sessionid 取得方式**：登入 TradingView → 瀏覽器 DevTools（F12）→ Application → Cookies → 複製 `sessionid` 值 → 填入 `tradingview.session_id`，並將 `expires_at` 設為今日 +30 天。


---

## 本地使用

### 啟動 WebUI（設計策略 + 回測視覺化）

```powershell
uv run dashboard.py
```

瀏覽器開啟 `http://127.0.0.1:5000`，調整策略參數後點「執行回測」觀察：
- 組合權益曲線 vs 基準（NASDAQ / 台灣加權）
- Sharpe Ratio、最大回撤、勝率等關鍵指標
- 當前持倉與近期交易訊號

策略調整滿意後，點「儲存策略」—— WebUI 會將回測參數寫回 `cloud_function/config.yaml`。

---

## 部署至 GCF

本專案以 **GitHub Actions** 自動化部署：每次 `cloud_function/` 有任何變動並 push 到 `main` 時，自動觸發 `.github/workflows/deploy.yml` 部署至 `keep-buying-audition-engine`。

### 初次設定（只需做一次）

**1. 建立 GCP Service Account**

在 [GCP Console → IAM → 服務帳戶](https://console.cloud.google.com/iam-admin/serviceaccounts) 建立 SA，授予以下角色：
- `Cloud Functions Developer`
- `Service Account User`

下載 JSON 金鑰。

**2. 設定 GitHub Secrets**

GitHub Repo → Settings → Secrets and variables → Actions，新增：

| Secret 名稱 | 值 |
|---|---|
| `GCP_CREDENTIALS` | 上一步下載的完整 JSON 金鑰內容 |
| `GCP_PROJECT_ID` | GCP 專案 ID（如 `my-project-123456`） |

**3. 設定 Cloud Scheduler（排程觸發，一次性）**

在 [GCP Console → Cloud Scheduler](https://console.cloud.google.com/cloudscheduler) 建立工作：

| 欄位 | 值 |
|---|---|
| 排程 | `0 9 * * 1-5`（每週一至五 09:00 TPE） |
| 目標 | HTTP POST → GCF Trigger URL |
| Body | `{"portfolio": {"source": "tradingview"}, "notify": {"line": true}}` |
| 時區 | `Asia/Taipei` |

GCF Trigger URL 格式：`https://asia-east1-<GCP_PROJECT_ID>.cloudfunctions.net/keep-buying-audition-engine`

---

### 日常部署流程

WebUI 調整策略滿意後：

```powershell
git add cloud_function/config.yaml
git commit -m "update strategy"
git push
# → GitHub Actions 自動部署至 keep-buying-audition-engine
```

也可在 GitHub → Actions → 「部署至 Google Cloud Function」→ **Run workflow** 手動觸發。

### 驗證 endpoint

```powershell
uv run demo.py --url https://asia-east1-<GCP_PROJECT_ID>.cloudfunctions.net/keep-buying-audition-engine
```

---

## HTTP 介面

GCF 接受 `POST application/json`，詳細 schema 見 [docs/API_SPEC.md](docs/API_SPEC.md)。

**快速範例**：

```jsonc
// Request
{
  "portfolio": { "source": "tradingview" },
  "backtest":  { "market": "us", "max_positions": 10 },
  "notify":    { "line": false }
}

// Response（成功）
{
  "ok": true,
  "holdings": [ { "symbol": "AAPL", "pnl_pct": 0.12, ... } ],
  "result":   { "total_return": "23.4%", "sharpe_ratio": "1.85", ... },
  "meta":     { "execution_time_ms": 8200, "symbols_count": 42, ... }
}
```

---

## 延伸閱讀

| 文件 | 內容 |
|---|---|
| [docs/API_SPEC.md](docs/API_SPEC.md) | HTTP 介面完整規格、錯誤碼、Session 過期處理 |
| [CLAUDE.md](CLAUDE.md) | 系統設計脈絡、Domain 邊界、部署細節 |

