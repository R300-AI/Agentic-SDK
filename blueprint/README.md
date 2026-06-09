# Blueprint — Agentic SDK 實施工程藍圖

> 受眾:本專案執行團隊(3–5 人)
> 目的:把 [docs/](../docs/README.md) 中已凍結的設計,轉換為可被認領、可驗收、可追蹤的工程工作。

## 與 docs/ 的分工

| 資料夾 | 回答的問題 | 文件性質 |
|--------|-----------|----------|
| [docs/](../docs/README.md) | **What & Why** — 系統做什麼、為何這樣設計 | 設計凍結後不常改 |
| `blueprint/` | **How & When** — 如何拆工、依賴順序、驗收條件、決策歷程 | 隨執行進度持續更新 |

藍圖**不重新定義**任何 docs/ 中已決定的事項;若藍圖與 docs/ 衝突,以 docs/ 為準,並回頭修藍圖。

## 起點假設(基於專案啟動前的釐清)

藍圖建立在以下五項假設之上。任一假設變動,對應階段需重新評估。

| 編號 | 假設 | 影響範圍 |
|------|------|----------|
| A1 | 開發期間只有 Ryzen AI PC 可用,TSiP NPU 後續才會到位 | 「跨節點」在 PoC 期間指邏輯節點(同行程內 LangGraph 節點),實體跨機驗證延至 Phase 4 |
| A2 | 上游 [`amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 已提供可用的 OpenAI 相容 `api.py` | SDK **不實作** Runner 容器與 Model Card SHA 驗證;改由使用者依上游 README 啟動推論伺服器,本專案接 `UPSTREAM_API_BASE_URL`(詳見 [risk-decisions.md D1](risk-decisions.md)) |
| A3 | 投入工程人力 3–5 人,可拆兩條主軸並行 | Track A(上下文/工作流)與 Track B(觀測 Dashboard)獨立推進,僅 Phase 3 合流 |
| A4 | 有概略季度目標但非硬時限 | 藍圖以「相對順序與依賴」表達,不綁絕對日期 |
| A5 | PoC 驗收條件 = 單一模型 × 五節點邏輯路由成功 + Streamlit Dashboard 即時看見節點動向 | Phase 3 的驗收腳本以此為終點 |

## 階段地圖

```
   Phase 0              Phase 1              Phase 3            Phase 4         Phase 5
共用基礎就緒        上下文/工作流軸       兩軸合流           TSiP 接入       圖形編排
                       Phase 2                                (延伸)         (延後評估)
                    觀測 Dashboard 軸
       │                  │                    │                  │              │
       ▼                  ▼                    ▼                  ▼              ▼
  ┌─────────┐    ┌────────────────┐    ┌─────────────┐    ┌────────────┐  ┌──────────┐
  │ Gateway │───▶│ Track A (Ctx)  │──┐ │   M3 Demo   │    │ 跨實體節點 │  │ 編排框架 │
  │ 上游接入 │    │                │  ├▶│  驗收腳本   │───▶│  接入測試  │─▶│ 選型+實作 │
  │ + .env  │───▶│ Track B (Obs)  │──┘ │  + README   │    │  + 文件    │  │  (待啟動) │
  └─────────┘    └────────────────┘    └─────────────┘    └────────────┘  └──────────┘
     M0            M1 + M2 (並行)           M3                M4              M5
                                                          (不阻塞 PoC)    (條件未到不展開)
```

- Phase 0:兩軸共同前置
- Phase 1 / Phase 2:完全並行,互不阻塞
- Phase 3:兩軸合流,PoC 對外可驗收的時點
- Phase 4:TSiP 到位後的延伸,**不阻塞 M3 對外宣告 PoC 完成**
- Phase 5:圖形編排能力,啟動條件見 [docs/04-observability-dashboard/visualization-ui.md](../docs/04-observability-dashboard/visualization-ui.md) §四

## 文件導航

| 文件 | 內容 |
|------|------|
| [tracks.md](tracks.md) | 兩條工作軸的工作項分解、共用基礎、整合點定義 |
| [milestones.md](milestones.md) | M0–M5 的量化驗收條件與依賴順序 |
| [source-layout.md](source-layout.md) | 程式碼目錄結構設計、工作項與檔案的對應表 |
| [target-quickstart.md](target-quickstart.md) | Phase 3 完成後,根 README 應呈現的「三步啟動」目標形態 |
| [risk-decisions.md](risk-decisions.md) | 已消除的風險與替代方案紀錄(D1–D4)、仍存活的風險(R6–R8) |

## 變更管理

藍圖修改採與程式碼相同的 PR 流程。任何階段交付物若提早或延後,先在對應文件記錄原因,再調整 [milestones.md](milestones.md) 的依賴順序——避免「沉默漂移」。

任何設計層的決策推翻或重新評估,寫入 [risk-decisions.md](risk-decisions.md) 的 D-N 條目,而非散落於各文件。
