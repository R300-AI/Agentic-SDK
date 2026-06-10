# Portfolio Optimizer — 專案脈絡（CLAUDE.md）

> 本檔僅承載本專案特有的技術脈絡與決策。跨專案通用的思維框架（Clean Architecture、YAGNI、反硬編碼、手術修改）已封裝於 `.claude/skills/connect-ai-style/SKILL.md`，此處不重述。

---

## 一、Domain 定位

本專案是一個**投資組合策略產生工具**：使用者在 WebUI 調整策略參數、觀察回測成果，滿意後將策略儲存至 `config.yaml`，再手動上傳 `cloud_function/` 至 GCF 部署；部署後 Cloud Scheduler 每日定時觸發，跑當日回測並透過 LINE 推播持倉建議。

### 完整工作流

```
WebUI 調整策略 → 回測視覺化確認
    ↓ 儲存策略
cloud_function/config.yaml（憑證 + 策略參數）
    ↓ 手動上傳整包
GCF（Ubuntu 22.04 Full / Python 3.12）
    ↓ Cloud Scheduler 每日觸發
LINE Bot 推播持倉建議
    ↓ demo.py 驗證 GCF endpoint
確認部署成功
```

### 下游流程（規劃中）

```
GCF 輸出 holdings 陣列
    ↓  Claude Dispatch（規劃中）
    ↓  質化分析：財報、新聞動態、產業趨勢
    ↓
最終決策：當下最值得買進持有的個股
```

**本專案不做股價預測、不評估基本面**—那是 Claude Dispatch 的職責。`holdings` 陣列（symbol、產業、國家、市值、損益、買入日）設計為機器可讀，足以驅動下游 AI Agent。

---

## 二、工作流邊界

```
Portfolio_Optimizer/
├── cloud_function/          ← 唯一 Domain Core（上傳至 GCF 的完整套件）
│   ├── main.py              ← GCF HTTP entry（hello_http）
│   ├── engine.py            ← 回測引擎 + 指標 + 基準 + run_pipeline()
│   ├── data.py              ← 資料層：TradingView / yfinance / FX / 常數（CONFIG_FILE / TPE_TZ）
│   ├── config.yaml          ← 憑證 + 策略參數（WebUI「儲存策略」後寫入此檔）
│   └── requirements.txt     ← GCF 部署相依（PyYAML / pandas / yfinance / …）
│
├── dashboard.py             ← WebUI Adapter（本地 Flask，直接 import cloud_function/engine）
├── webui/                   ← dashboard.py 的前端資產
│   ├── templates/index.html
│   ├── static/app.js
│   └── requirements.txt     ← 本地 Flask 相依（獨立，不上傳 GCF）
│
├── demo.py                  ← GCF HTTP 測試客戶端（驗證已部署的 GCF，不 import engine）
├── docs/
│   └── API_SPEC.md          ← GCF HTTP 介面契約
├── backup/smc/              ← 封存舊 SMC 回測（與本專案無關）
└── CLAUDE.md
```

### 鐵則

| 規則 | 說明 |
|---|---|
| **GCF 平面化** | `cloud_function/` 不得有子目錄，GCF 只支援單層模組結構 |
| **唯一 Domain 來源** | `dashboard.py` 透過 `sys.path.insert` 直接 import `cloud_function/engine`，禁止複製回測邏輯 |
| **demo.py 不 import engine** | `demo.py` 是 HTTP 客戶端，專責驗證 GCF endpoint，不接觸本地 Domain |
| **Domain 純淨** | `engine.py` / `data.py` 不得 import `functions_framework` / `flask` / `argparse` 等 Adapter 框架 |
| **Adapter 不得 import main** | `main.py` 是 GCF HTTP 殼，不是 Domain API |
| **常數單一來源** | `CONFIG_FILE`、`TPE_TZ` 定義於 `data.py`，Adapter（`main.py`、`dashboard.py`）從 `data` import，禁止各自重複定義 |

---

## 三、`config.yaml` 職責

`config.yaml` 是本專案的**唯一配置來源**，隨 `cloud_function/` 整包上傳 GCF。分兩區：

```yaml
# ── 憑證區（不由 WebUI 控制）──────────────────────────
tradingview:
  session_id: "..."         # DevTools → Cookies → sessionid
  watchlist_id: "..."       # TradingView watchlist 數字 ID
  expires_at: "YYYY-MM-DD"  # sessionid 預計到期日（+30 天）

line:
  channel_access_token: ""  # LINE Developers → Messaging API
  group_id: ""              # 從 Webhook event 取得

# ── 策略區（由 WebUI「儲存策略」寫入）────────────────
backtest:
  initial_capital: 1000000
  amount_per_stock: 100000
  max_positions: 10
  market: "us"              # us | tw | global
  start_date: "2025-01-01"
  rebalance_freq: "weekly"  # daily | weekly | monthly
  buy_conditions:
    sharpe_rank:   { enabled: true,  top_n: 15 }
    sharpe_threshold: { enabled: true, threshold: 1.0 }
    growth_streak: { enabled: true,  days: 2, percentile: 30 }
    sort_sharpe:   { enabled: true }
  sell_conditions:
    sharpe_fail:   { enabled: true,  periods: 2, top_n: 15 }
    drawdown:      { enabled: true,  threshold: 0.40 }
  rebalance_strategy:
    type: "delayed"
    top_n: 5
    sharpe_threshold: 0
```

缺少必填欄位時 fail-fast 回傳 `CONFIG_ERROR`，不可靜默套用預設值。

---

## 四、Cloud Function 規格

### 部署環境（不可變）

| 項目 | 值 |
|---|---|
| Runtime | Python 3.12（Ubuntu 22 Full base image） |
| Entry point | `hello_http` |
| 觸發 | HTTP（POST `application/json`） |
| 目錄結構 | `cloud_function/` 平面化（無子目錄）+ `requirements.txt` |

**相依限制**：只允許純 pip 可裝套件，不允許需要 native build 的相依。新增套件前必須確認 GCF 部署可正常安裝。

### Request Schema

```jsonc
POST /  (hello_http)
Content-Type: application/json
{
  "portfolio": {
    "source":  "tradingview" | "manual",
    "symbols": ["AAPL", "TSM", "2330.TW"]   // source=manual 時必填
  },
  "backtest": { /* 覆寫 config.yaml 的 backtest 區，省略欄位沿用 config.yaml */ },
  "notify": {
    "line": false   // 預設 false；Cloud Scheduler 排程才傳 true
  }
}
```

### Response Schema

成功：
```jsonc
{
  "ok": true,
  "result":          { /* BacktestResult */ },
  "holdings":        [ /* 當前持倉 */ ],
  "trades":          [ /* 歷史交易 */ ],
  "equity_curve":    [ /* 權益曲線 */ ],
  "benchmark_curve": [ /* 基準曲線 */ ],
  "benchmark_name":  "NASDAQ",
  "meta": {
    "timestamp":         "2026-06-01T09:00:00+08:00",
    "execution_time_ms": 1234,
    "portfolio_source":  "tradingview",
    "symbols_count":     42,
    "data_range":        ["2025-01-01", "2026-06-01"]
  },
  "notifications": { "line": { "sent": true } }
}
```

失敗：
```jsonc
{
  "ok": false,
  "error": {
    "code":        "TRADINGVIEW_SESSION_EXPIRED" | "INVALID_REQUEST" | "CONFIG_ERROR" | "NO_DATA" | "INTERNAL",
    "message":     "人話描述",
    "remediation": "具體修復步驟",
    "details":     { /* 結構化細節，如 expires_at */ }
  }
}
```

---

## 五、關鍵設計決策

### 5.1 TradingView Session 過期偵測

採「日期 + API 失敗」雙條件：

1. 讀 `config.yaml` 的 `tradingview.expires_at`，今日已過 **且** API 返回 401/403 或缺少 `symbols` 欄位 → 拋 `TradingViewSessionExpired`
2. 日期未過但 API 失敗 → 視為暫時性錯誤，回傳 `NO_DATA`

`remediation` 訊息必須具體：去哪登入、抓哪個 cookie、寫進 `config.yaml` 的哪個欄位。

### 5.2 LINE 通知預設關閉

`notify.line` 預設 `false`，避免 WebUI 或 demo.py 誤推 LINE。Cloud Scheduler 排程為唯一顯式傳 `"line": true` 的消費者。

### 5.3 GCF 執行模型限制

| 禁止做法 | 原因 |
|---|---|
| `pickle` 寫入檔案 | GCF 無持久檔案系統 |
| `logging` 寫入 `run.log` | 改用 `logging.basicConfig(stream=sys.stdout)` |
| 跨呼叫保留記憶體 cache | GCF instance 可能隨時回收 |

---

## 六、部署流程

```
1. WebUI 回測滿意 → 點「儲存策略」→ 更新 cloud_function/config.yaml
2. 手動執行（gcloud CLI 或 GCP 控制台）：
       gcloud functions deploy portfolio-optimizer \
         --gen2 --runtime python312 \
         --entry-point hello_http \
         --source cloud_function/ \
         --trigger-http --allow-unauthenticated
3. python demo.py --url https://<GCF_URL> 驗證 endpoint
4. 設定 Cloud Scheduler：每日 09:00 TPE，POST body 含 "notify": {"line": true}
```

---

## 七、目前狀態

| 項目 | 狀態 |
|---|---|
| `cloud_function/` Domain Core | ✅ 已建立（main / engine / data / config.yaml / requirements.txt） |
| WebUI（dashboard.py + webui/） | ✅ 本地可執行 |
| `demo.py` GCF 測試客戶端 | ✅ HTTP client，不 import engine |
| `backup/smc/` | ✅ 已封存，與本專案隔離 |
| `services_investment-funds-strategy_*/` | 🕐 對照原始碼，GCF 部署驗證後可移至 backup 或刪除 |
| Claude Dispatch 整合介面 | 🕐 待定，`holdings` 陣列格式已預留足夠欄位 |

---

## 八、執行慣例

- **語系**：所有對話、commit message、文件、註解一律繁體中文（台灣）。
- **驗證紀律**：宣稱完成前必須執行 `demo.py` 打一次 GCF endpoint，或本地啟動 `dashboard.py` 確認回測可執行，貼出輸出。
- **變更管理**：發現修改破壞架構時，先 revert 到穩定狀態再重做，禁止在錯誤邏輯上補丁。
